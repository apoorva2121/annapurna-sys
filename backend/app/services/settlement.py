"""Settlement: the moment an order becomes a tax document, money, and stock. Chunk G of M07.

Everything here happens in one transaction or not at all (ADR 0010 §Transaction boundaries; spec
decision 10), and in this order, because the order matters:

1. **Lock the order**, check its version, and refuse a restaurant that cannot issue the document
   its scheme requires — before anything is written.
2. **Re-freeze tax from Section 14's date.** The rate every line takes is the one in force on the
   calendar date of the median of served, invoiced and paid (decision 5). Lines and charges are
   repriced while the order is still live: migration 0019 refuses to touch them one statement
   after it settles.
3. **Freeze what the plate should have cost**, from the current recipe at today's unit costs, with
   the costing snapshot loaded once for the whole bill.
4. **Post theoretical consumption:** each dish recipe's *direct* components, and each modifier
   recipe's, times the quantity, summed per stock item. A preparation is consumed as itself; its
   onions were consumed when it was produced. Never refused for want of stock (M05 decision 2).
5. **The payments must cover the bill exactly** — the figure after the re-freeze, not before.
6. **Number the invoice** under a lock, snapshot the restaurant's identity onto it, and write the
   payments against it.
7. **Settle the order last**, then send its tables to cleaning, and audit.

`SettlementService` extends `OrderService` rather than calling into it, because settling is the last
thing that happens to an order and needs the same lock and the same reprice — reached as its own
methods, not as another class's private ones.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.actor import Actor
from app.core.business_day import business_date_of, calendar_date_of, financial_year_of
from app.core.enums import (
    DocumentType,
    InvoiceStatus,
    MovementBasis,
    MovementType,
    OrderLineStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    TableStatus,
)
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.tax import ZERO, collects_tax, document_type_for, invoice_number, rate_date, to_paisa
from app.models.orders import Invoice, Order, OrderLine, Payment
from app.models.tenancy import Restaurant
from app.repositories.orders import CashSessionRepository, InvoiceRepository, PaymentRepository
from app.repositories.stock import CostingRepository, RecipeRepository
from app.services.costing import CostEngine, Line
from app.services.inventory import InventoryService
from app.services.orders import OrderService

logger = logging.getLogger(__name__)

_NOT_BILLED = frozenset({OrderLineStatus.CANCELLED, OrderLineStatus.RETURNED})
_UNIT_COST = Decimal("0.000001")
# How far a payment's reported time may run ahead of the server's clock. A phone a minute fast is
# ordinary; a payment "received" tomorrow is not.
_CLOCK_SKEW = timedelta(minutes=2)


def _dec(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class PaymentInput:
    method: PaymentMethod
    amount: Decimal
    tip_amount: Decimal = ZERO
    reference: str | None = None
    # When the money was actually received — a UPI payment confirmed before the bill was printed.
    # Section 14 counts it; None means "now".
    paid_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Recipient:
    """A registered customer asking for their GSTIN on the invoice (Rule 46(d))."""

    name: str | None
    gstin: str | None
    address: str | None


class SettlementService(OrderService):
    async def settle(
        self,
        actor: Actor,
        order_id: uuid.UUID,
        *,
        version: int,
        payments: Sequence[PaymentInput],
        recipient: Recipient | None = None,
    ) -> uuid.UUID:
        """Settle the order and return its invoice's id."""
        order = await self._locked(order_id, version)
        restaurant = await self._restaurant()
        billed = [line for line in order.lines if line.status not in _NOT_BILLED]
        if not billed:
            raise ConflictError("order.empty", f"Order {order.order_number} has nothing on it.")

        document_type = document_type_for(restaurant.gst_scheme)
        if document_type == DocumentType.TAX_INVOICE and not restaurant.gstin:
            raise ConflictError(
                "restaurant.gstin_required",
                "A tax invoice has to carry the restaurant's GSTIN (CGST Rules, Rule 46). "
                "The owner can add it in settings.",
            )

        now = datetime.now(UTC)
        paid_at = self._received_at(order, payments, now)
        await self._refreeze_tax(
            order, restaurant, served=order.served_at or now, paid=paid_at, now=now
        )
        order = await self._reprice(order.id)
        billed = [line for line in order.lines if line.status not in _NOT_BILLED]

        food_cost, uncosted, consumption = await self._cost_and_consumption(billed)
        order.theoretical_food_cost = to_paisa(food_cost)

        paid = sum((payment.amount for payment in payments), ZERO)
        if paid != _dec(order.grand_total):
            raise AppError(
                "settlement.payments_do_not_match",
                f"The payments come to ₹{paid} and the bill is ₹{_dec(order.grand_total)}.",
                details={"grand_total": str(order.grand_total), "paid": str(paid)},
                status_code=422,
            )

        inventory = InventoryService(self.session, self.scope)
        # A fixed order, so two settlements consuming the same items take their batch locks in the
        # same sequence and cannot deadlock each other.
        for stock_item_id, quantity in sorted(consumption.items(), key=lambda entry: str(entry[0])):
            await inventory.consume(
                actor,
                stock_item_id=stock_item_id,
                quantity=quantity,
                basis=MovementBasis.THEORETICAL,
                movement_type=MovementType.CONSUMPTION,
                ref_type="order",
                ref_id=order.id,
                occurred_at=now,
            )

        invoice = await self._issue_invoice(order, restaurant, document_type, recipient, now)
        # Cash goes into whichever till is open, so the cash-up can derive what should be in it.
        till_id = await CashSessionRepository(self.session, self.scope).open_id()
        for payment in payments:
            moment = payment.paid_at or now
            self.session.add(
                Payment(
                    restaurant_id=self.scope.restaurant_id,
                    order_id=order.id,
                    invoice_id=invoice.id,
                    cash_session_id=till_id if payment.method == PaymentMethod.CASH else None,
                    method=payment.method,
                    amount=payment.amount,
                    tip_amount=payment.tip_amount,
                    reference=payment.reference,
                    status=PaymentStatus.SUCCESS,
                    paid_at=moment,
                    business_date=business_date_of(
                        moment, restaurant.timezone, restaurant.business_day_start
                    ),
                    received_by=actor.employee_id,
                )
            )

        # Last. Once this flush lands, 0019's triggers freeze every figure written above.
        order.status = OrderStatus.SETTLED
        order.settled_at = now
        order.updated_at = now
        await self.session.flush()
        await self._release_tables(order, to=TableStatus.CLEANING)

        self._audit(
            actor,
            "order.settle",
            "order",
            order.id,
            new={
                "order_number": order.order_number,
                "invoice_number": invoice.invoice_number,
                "document_type": str(document_type),
                "grand_total": str(order.grand_total),
                "payments": [
                    {"method": str(payment.method), "amount": str(payment.amount)}
                    for payment in payments
                ],
                "theoretical_food_cost": str(order.theoretical_food_cost),
                "lines_without_a_recipe": uncosted,
            },
        )
        await self.session.flush()
        logger.info(
            "order.settled",
            extra={
                "order_id": str(order.id),
                "invoice_number": invoice.invoice_number,
                "lines_without_a_recipe": uncosted,
            },
        )
        return invoice.id

    async def get_invoice(self, invoice_id: uuid.UUID) -> tuple[Invoice, Sequence[Payment]]:
        invoice = await InvoiceRepository(self.session, self.scope).get(invoice_id)
        if invoice is None:
            raise NotFoundError("invoice.not_found", "That invoice does not exist.")
        payments = await PaymentRepository(self.session, self.scope).for_order(invoice.order_id)
        return invoice, payments

    # ------------------------------------------------------------------ steps

    @staticmethod
    def _received_at(order: Order, payments: Sequence[PaymentInput], now: datetime) -> datetime:
        """The earliest moment money was received, bounded by the order and the clock."""
        if not payments:
            raise AppError(
                "settlement.no_payment",
                "A bill is settled by at least one payment.",
                status_code=422,
            )
        moments = [payment.paid_at or now for payment in payments]
        for moment in moments:
            if moment > now + _CLOCK_SKEW or moment < order.placed_at:
                raise AppError(
                    "settlement.payment_time",
                    "A payment cannot be received before the order was placed or after now.",
                    status_code=422,
                )
        return min(moments)

    async def _refreeze_tax(
        self,
        order: Order,
        restaurant: Restaurant,
        *,
        served: datetime,
        paid: datetime,
        now: datetime,
    ) -> None:
        """Every line and charge takes the rate in force on Section 14's date (decision 5)."""
        on = calendar_date_of(rate_date(served, now, paid), restaurant.timezone)
        charging = collects_tax(restaurant.gst_scheme)
        for line in order.lines:
            if line.status in _NOT_BILLED:
                continue
            rate = await self._pricing.rate_on(line.tax_group_id, on)
            if rate is None:
                raise ConflictError(
                    "tax.no_rate",
                    f"A dish on this bill has no tax rate in force on {on.isoformat()}.",
                )
            line.tax_regime = rate.regime
            line.tax_rate = rate.rate if charging else ZERO
            line.tax_inclusive = rate.inclusive
        for charge in order.charges:
            if charge.tax_group_id is None:
                continue
            rate = await self._pricing.rate_on(charge.tax_group_id, on)
            if rate is None:
                raise ConflictError(
                    "tax.no_rate",
                    f"A charge on this bill has no tax rate in force on {on.isoformat()}.",
                )
            charge.tax_rate = rate.rate if charging else ZERO

    async def _cost_and_consumption(
        self, billed: Sequence[OrderLine]
    ) -> tuple[Decimal, int, dict[uuid.UUID, Decimal]]:
        """What the plates should have cost, how many had no recipe, and what they consumed.

        The recipe version used is frozen on each line and each modifier, so "what did this bill
        cost in March" is answered from March's recipe rather than today's.
        """
        components, preparation_lines = await CostingRepository(
            self.session, self.scope
        ).load_snapshot()
        engine = CostEngine(components, preparation_lines)
        recipes = RecipeRepository(self.session, self.scope)
        consumption: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
        food_cost = Decimal(0)
        uncosted = 0

        for line in billed:
            unit = Decimal(0)
            recipe = await recipes.current_for_variant(line.menu_item_variant_id)
            if recipe is None:
                uncosted += 1
            else:
                line.recipe_id = recipe.id
                unit += self._plate(engine, recipe.lines, line.quantity, consumption)
            for chosen in line.modifiers:
                modifier_recipe = await recipes.current_for_modifier(chosen.modifier_id)
                if modifier_recipe is not None:
                    chosen.recipe_id = modifier_recipe.id
                    unit += self._plate(engine, modifier_recipe.lines, line.quantity, consumption)
            line.theoretical_unit_cost = unit.quantize(_UNIT_COST)
            food_cost += unit * line.quantity
        return food_cost, uncosted, consumption

    @staticmethod
    def _plate(
        engine: CostEngine,
        recipe_lines: Sequence[object],
        quantity: int,
        consumption: dict[uuid.UUID, Decimal],
    ) -> Decimal:
        lines = [
            Line(component_id=row.component_id, quantity=_dec(row.quantity))  # type: ignore[attr-defined]
            for row in recipe_lines
        ]
        for entry in lines:
            consumption[entry.component_id] += entry.quantity * quantity
        return engine.cost_of(lines).total

    async def _issue_invoice(
        self,
        order: Order,
        restaurant: Restaurant,
        document_type: DocumentType,
        recipient: Recipient | None,
        now: datetime,
    ) -> Invoice:
        """The legal document. Numbered here and never before (decision 1).

        The financial year follows the **calendar date of issue** in the restaurant's timezone, not
        the business date: a bill at 01:30 on 1 April is business day 31 March and the new year's
        series.
        """
        invoice_date = calendar_date_of(now, restaurant.timezone)
        financial_year = financial_year_of(invoice_date)
        sequence = await InvoiceRepository(self.session, self.scope).next_sequence(financial_year)
        taxable = sum(
            (_dec(line.taxable_value) for line in order.lines if line.status not in _NOT_BILLED),
            ZERO,
        )
        taxable += sum((_dec(charge.amount) for charge in order.charges), ZERO)
        cgst = sum(
            (_dec(line.cgst_amount) for line in order.lines if line.status not in _NOT_BILLED), ZERO
        )
        cgst += sum((_dec(charge.cgst_amount) for charge in order.charges), ZERO)
        sgst = sum(
            (_dec(line.sgst_amount) for line in order.lines if line.status not in _NOT_BILLED), ZERO
        )
        sgst += sum((_dec(charge.sgst_amount) for charge in order.charges), ZERO)
        non_gst = sum(
            (
                _dec(line.tax_amount)
                for line in order.lines
                if line.status not in _NOT_BILLED and line.tax_regime == "non_gst"
            ),
            ZERO,
        )
        invoice = Invoice(
            restaurant_id=self.scope.restaurant_id,
            order_id=order.id,
            document_type=document_type,
            financial_year=financial_year,
            sequence=sequence,
            invoice_number=invoice_number(financial_year, sequence),
            status=InvoiceStatus.ISSUED,
            issued_at=now,
            invoice_date=invoice_date,
            business_date=business_date_of(now, restaurant.timezone, restaurant.business_day_start),
            supplier_name=restaurant.name,
            supplier_address=restaurant.address,
            supplier_gstin=restaurant.gstin,
            fssai_licence=restaurant.fssai_licence,
            recipient_name=None if recipient is None else recipient.name,
            recipient_gstin=None if recipient is None else recipient.gstin,
            recipient_address=None if recipient is None else recipient.address,
            taxable_total=taxable,
            cgst_total=cgst,
            sgst_total=sgst,
            non_gst_tax_total=non_gst,
            discount_total=_dec(order.discount_total),
            charge_total=_dec(order.charge_total),
            round_off=_dec(order.round_off),
            grand_total=_dec(order.grand_total),
        )
        self.session.add(invoice)
        await self.session.flush()
        return invoice
