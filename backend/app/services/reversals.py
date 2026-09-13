"""After a bill is settled: cancelling an invoice issued in error, and credit notes with refunds.

Chunk H of M07. A settled order is never edited (invariant 6); everything here is a new document.

**1 · Cancelling an invoice is for one issued in error, on its business day of issue, and only
while nothing has been credited against it** (spec decision 2; R8). The invoice keeps its number
and is reported as cancelled; the order becomes `voided`. **Cancelling moves no money and no
stock.** It withdraws the legal document — "billed to the wrong table" — and the bill is raised
again where it belonged. Money going back is always a credit note with a refund, because that is
the only path that reduces what was charged, and the only one that has to carry a reason and a name.

**2 · A credit note reduces an invoice by whole dishes** (CGST Act s.34; Rule 53): its own series,
its lines naming which dishes and how many, each carrying its share of the original line's taxable
value and tax, with CGST and SGST kept equal. A dish cannot be credited more times than it was
billed across every note against the invoice, and **the note that credits a dish's last unit takes
the exact remainder**, so crediting three portions one at a time can never drift a paisa from the
bill.

**3 · A refund is a negative payment that names its credit note.** Migration 0019 refuses one that
does not, and this service refuses one larger than the note.

**4 · Neither reverses stock.** A dish sent back was cooked, so its theoretical consumption
happened; if it went in the bin, that is wastage, not un-consumption.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.business_day import business_date_of, calendar_date_of, financial_year_of
from app.core.enums import (
    InvoiceStatus,
    OrderLineStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    TaxRegime,
)
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.tax import ZERO, credit_note_number, to_paisa
from app.core.tenancy import TenantScope
from app.models.audit import AuditLog
from app.models.orders import CreditNote, CreditNoteLine, Invoice, OrderLine, Payment
from app.models.tenancy import Restaurant
from app.repositories.orders import (
    CashSessionRepository,
    CreditedSoFar,
    CreditNoteRepository,
    InvoiceRepository,
    OrderRepository,
    PaymentRepository,
)
from app.repositories.setup import RestaurantRepository

logger = logging.getLogger(__name__)

_NOT_BILLED = frozenset({OrderLineStatus.CANCELLED, OrderLineStatus.RETURNED})


def _dec(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class CreditLineInput:
    order_line_id: uuid.UUID
    quantity: int


@dataclass(frozen=True, slots=True)
class RefundInput:
    method: PaymentMethod
    amount: Decimal
    reference: str | None = None


@dataclass(frozen=True, slots=True)
class _Credit:
    order_line_id: uuid.UUID
    quantity: int
    taxable: Decimal
    cgst: Decimal
    sgst: Decimal
    tax: Decimal
    non_gst: bool


class ReversalService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._invoices = InvoiceRepository(session, scope)
        self._notes = CreditNoteRepository(session, scope)
        self._orders = OrderRepository(session, scope)
        self._payments = PaymentRepository(session, scope)

    # ------------------------------------------------------------------ cancellation

    async def cancel_invoice(self, actor: Actor, invoice_id: uuid.UUID, *, reason: str) -> None:
        invoice = await self._locked_invoice(invoice_id)
        if invoice.status == InvoiceStatus.CANCELLED:
            raise ConflictError(
                "invoice.already_cancelled",
                f"Invoice {invoice.invoice_number} is already cancelled.",
            )
        restaurant = await self._restaurant()
        now = datetime.now(UTC)
        today = business_date_of(now, restaurant.timezone, restaurant.business_day_start)
        if invoice.business_date != today:
            raise ConflictError(
                "invoice.cancel_window_closed",
                f"Invoice {invoice.invoice_number} was issued on business day "
                f"{invoice.business_date.isoformat()}. After its own day, a reduction is "
                "a credit note.",
            )
        if await self._notes.credited_so_far(invoice.id):
            raise ConflictError(
                "invoice.has_credit_notes",
                f"Invoice {invoice.invoice_number} already has a credit note against it, so it "
                "cannot be cancelled as though it had been issued in error.",
            )

        await self._orders.lock(invoice.order_id)
        order = await self._orders.get_detail(invoice.order_id, refresh=True)
        if order is None or order.status != OrderStatus.SETTLED:  # pragma: no cover - 0019 holds it
            raise ConflictError(
                "order.not_settled", "Only a settled order's invoice can be cancelled."
            )

        invoice.status = InvoiceStatus.CANCELLED
        invoice.cancelled_at = now
        invoice.cancel_reason = reason
        invoice.cancelled_by = actor.employee_id
        order.status = OrderStatus.VOIDED
        order.cancel_reason = reason
        order.cancelled_at = now
        order.voided_by = actor.employee_id
        order.updated_at = now
        await self.session.flush()

        paid = sum(
            (_dec(payment.amount) for payment in await self._payments.for_order(order.id)), ZERO
        )
        self._audit(
            actor,
            "invoice.cancel",
            "invoice",
            invoice.id,
            {
                "invoice_number": invoice.invoice_number,
                "order_number": order.order_number,
                "grand_total": str(invoice.grand_total),
                "payments_against_it": str(paid),
                "reason": reason,
            },
        )
        await self.session.flush()
        logger.info(
            "invoice.cancelled",
            extra={"invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number},
        )

    # ------------------------------------------------------------------ credit notes

    async def issue_credit_note(
        self,
        actor: Actor,
        invoice_id: uuid.UUID,
        *,
        reason: str,
        lines: Sequence[CreditLineInput],
        refunds: Sequence[RefundInput],
    ) -> uuid.UUID:
        invoice = await self._locked_invoice(invoice_id)
        if invoice.status == InvoiceStatus.CANCELLED:
            raise ConflictError(
                "invoice.cancelled",
                f"Invoice {invoice.invoice_number} is cancelled, so there is nothing on it "
                "to credit.",
            )
        order = await self._orders.get_detail(invoice.order_id, refresh=True)
        if order is None:  # pragma: no cover - the invoice's foreign key holds it
            raise NotFoundError("order.not_found", "That order does not exist.")

        billed = {line.id: line for line in order.lines if line.status not in _NOT_BILLED}
        so_far = await self._notes.credited_so_far(invoice.id)
        credits = [self._credit_for(billed, so_far, request) for request in lines]

        taxable = sum((credit.taxable for credit in credits), ZERO)
        cgst = sum((credit.cgst for credit in credits), ZERO)
        sgst = sum((credit.sgst for credit in credits), ZERO)
        non_gst = sum((credit.tax for credit in credits if credit.non_gst), ZERO)
        grand = sum((credit.taxable + credit.tax for credit in credits), ZERO)
        if grand <= 0:
            raise AppError(
                "credit_note.nothing_to_credit",
                "Those dishes carried nothing on the bill, so there is nothing to credit.",
                status_code=422,
            )
        refunded = sum((refund.amount for refund in refunds), ZERO)
        if refunded > grand:
            raise AppError(
                "credit_note.refund_exceeds",
                f"A refund of ₹{refunded} is more than the ₹{grand} this credit note reduces "
                "the bill by.",
                details={"credit_note_total": str(grand), "refund": str(refunded)},
                status_code=422,
            )

        restaurant = await self._restaurant()
        now = datetime.now(UTC)
        note_date = calendar_date_of(now, restaurant.timezone)
        financial_year = financial_year_of(note_date)
        sequence = await self._notes.next_sequence(financial_year)
        business_date = business_date_of(now, restaurant.timezone, restaurant.business_day_start)
        note = CreditNote(
            restaurant_id=self.scope.restaurant_id,
            invoice_id=invoice.id,
            financial_year=financial_year,
            sequence=sequence,
            credit_note_number=credit_note_number(financial_year, sequence),
            issued_at=now,
            note_date=note_date,
            business_date=business_date,
            reason=reason,
            issued_by=actor.employee_id,
            taxable_total=taxable,
            cgst_total=cgst,
            sgst_total=sgst,
            non_gst_tax_total=non_gst,
            grand_total=grand,
        )
        self.session.add(note)
        await self.session.flush()
        for credit in credits:
            self.session.add(
                CreditNoteLine(
                    restaurant_id=self.scope.restaurant_id,
                    credit_note_id=note.id,
                    order_line_id=credit.order_line_id,
                    quantity=credit.quantity,
                    taxable_value=credit.taxable,
                    cgst_amount=credit.cgst,
                    sgst_amount=credit.sgst,
                    tax_amount=credit.tax,
                    line_total=credit.taxable + credit.tax,
                )
            )
        # A cash refund leaves whichever till is open *now*, not the one the bill was paid into, so
        # a closed till's variance never moves (acceptance criterion 16).
        till_id = await CashSessionRepository(self.session, self.scope).open_id()
        for refund in refunds:
            self.session.add(
                Payment(
                    restaurant_id=self.scope.restaurant_id,
                    order_id=order.id,
                    invoice_id=invoice.id,
                    credit_note_id=note.id,
                    cash_session_id=till_id if refund.method == PaymentMethod.CASH else None,
                    method=refund.method,
                    amount=-refund.amount,
                    reference=refund.reference,
                    status=PaymentStatus.SUCCESS,
                    paid_at=now,
                    business_date=business_date,
                    received_by=actor.employee_id,
                )
            )
        await self.session.flush()

        self._audit(
            actor,
            "invoice.credit_note",
            "credit_note",
            note.id,
            {
                "invoice_number": invoice.invoice_number,
                "credit_note_number": note.credit_note_number,
                "grand_total": str(grand),
                "refunded": str(refunded),
                "reason": reason,
                "lines": [
                    {"order_line_id": str(credit.order_line_id), "quantity": credit.quantity}
                    for credit in credits
                ],
            },
        )
        await self.session.flush()
        logger.info(
            "invoice.credit_note_issued",
            extra={"credit_note_id": str(note.id), "grand_total": str(grand)},
        )
        return note.id

    async def get_credit_note(
        self, credit_note_id: uuid.UUID
    ) -> tuple[CreditNote, Sequence[Payment]]:
        note = await self._notes.get_detail(credit_note_id)
        if note is None:
            raise NotFoundError("credit_note.not_found", "That credit note does not exist.")
        return note, await self._payments.for_credit_note(note.id)

    # ------------------------------------------------------------------ plumbing

    @staticmethod
    def _credit_for(
        billed: Mapping[uuid.UUID, OrderLine],
        so_far: dict[uuid.UUID, CreditedSoFar],
        request: CreditLineInput,
    ) -> _Credit:
        """This dish's share of the bill, or the exact remainder when it is the last of it."""
        line = billed.get(request.order_line_id)
        if line is None:
            raise AppError(
                "credit_note.line_not_on_invoice",
                "That dish is not on this invoice.",
                details={"order_line_id": str(request.order_line_id)},
                status_code=422,
            )
        previous = so_far.get(request.order_line_id, CreditedSoFar())
        billed_quantity = int(line.quantity)
        remaining = billed_quantity - previous.quantity
        if request.quantity > remaining:
            raise AppError(
                "credit_note.more_than_billed",
                f"Only {remaining} of that dish is left to credit on this invoice.",
                details={"order_line_id": str(request.order_line_id), "remaining": remaining},
                status_code=422,
            )
        taxable_billed = _dec(line.taxable_value)
        cgst_billed = _dec(line.cgst_amount)
        tax_billed = _dec(line.tax_amount)
        non_gst = line.tax_regime == TaxRegime.NON_GST

        if request.quantity == remaining:
            taxable = taxable_billed - previous.taxable
            half = cgst_billed - previous.cgst
            tax = half + half if not non_gst else tax_billed - previous.tax
        else:
            share = Decimal(request.quantity) / Decimal(billed_quantity)
            taxable = to_paisa(taxable_billed * share)
            half = to_paisa(cgst_billed * share)
            tax = half + half if not non_gst else to_paisa(tax_billed * share)
        cgst = ZERO if non_gst else half
        return _Credit(
            order_line_id=request.order_line_id,
            quantity=request.quantity,
            taxable=taxable,
            cgst=cgst,
            sgst=cgst,
            tax=tax,
            non_gst=non_gst,
        )

    async def _locked_invoice(self, invoice_id: uuid.UUID) -> Invoice:
        invoice = await self._invoices.get_for_update(invoice_id)
        if invoice is None:
            raise NotFoundError("invoice.not_found", "That invoice does not exist.")
        return invoice

    async def _restaurant(self) -> Restaurant:
        restaurant = await RestaurantRepository(self.session, self.scope).get()
        if restaurant is None:
            raise NotFoundError("restaurant.not_found", "This restaurant no longer exists.")
        return restaurant

    def _audit(
        self,
        actor: Actor,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        new: dict[str, object],
    ) -> None:
        self.session.add(
            AuditLog(
                restaurant_id=actor.restaurant_id,
                actor_employee_id=actor.employee_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                new_value=new,
            )
        )
