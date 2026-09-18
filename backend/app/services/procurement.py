"""The rules for buying things. Suppliers, orders, and the delivery door.

Five rules, and they are why this file exists rather than routes calling repositories.

**1 · Ordered, invoiced and received are three numbers and stay three numbers.**
`docs/waste-model.md` §1 is the whole argument: *ordered 50 kg, delivered 47 kg,
invoiced 50 kg* happens constantly and nobody notices, because nobody weighs. Nothing here
reconciles them; the derivations are computed and named (`accepted`, `short_delivery`,
`order_shortfall`) so a caller cannot reach for the wrong one by accident.

**2 · Only `accepted` enters stock.** `received - rejected`. A quality rejection arrived and was
refused, so it never goes on a shelf — and it does not fill the order either, which is why the PO
stays open for the difference.

**3 · The ledger has exactly one write path, and it is M05's.** Receiving calls
`InventoryService.receive_stock` rather than creating batches itself. That service already computes
the business date in the restaurant's own timezone, allocates the batch code and writes the paired
movement; a second implementation here is how the two drift, and the one that drifts is the one
nobody is testing.

**4 · Landed cost includes tax the restaurant cannot reclaim.** `docs/compliance-rules.md` §A6: on
the 5% composition scheme input GST is borne, not credited, so a quoted price is not a cost. The
invoice's tax is apportioned across the lines pro rata by value and frozen onto the batch. Exact
for a single-rate invoice; an approximation when one invoice mixes rates, recorded as such in the
spec's Risks rather than discovered later.

**5 · Money is never taken from the client.** `purchase_order.total_amount` is computed from the
lines here (`docs/security.md` A04). `invoice_amount` and `tax_amount` are the exception and are not
a computation at all — they are what the supplier wrote on a piece of paper, which is a fact the
restaurant is reporting rather than a figure the server could derive.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.audit import record
from app.core.enums import CostSource, PurchaseOrderStatus
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.tenancy import TenantScope
from app.models.procurement import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.repositories.procurement import (
    GoodsReceiptRepository,
    PurchaseOrderRepository,
    SupplierRepository,
    VarianceRow,
)
from app.repositories.stock import StockItemRepository
from app.services.inventory import InventoryService
from app.services.people import Person, people

# Rupees, when a figure reaches a person. Unit costs keep their six places, for the same reason
# `services/costing.py` gives: 0.1489 per ml rounded to two is a 0.7% error on every gram.
_RUPEES = Decimal("0.01")

# Six places, because that is what `NUMERIC(14,6)` holds (ADR 0008). The landed cost is quantized
# **where it is computed**, not left to the column, so the figure the confirmation panel reports is
# the same number the batch was frozen at. Without this, apportioning 1/3 of a rupee of tax yields
# a 28-digit Decimal in the response and a 6-place value in `stock_batch.unit_cost`, and the two
# disagree about what the stock cost — on the one field every food-cost figure is built from.
# Rounding is Decimal's default half-even, matching `services/costing.py`: two rounding modes in
# one product is a discrepancy nobody would find.
_UNIT_COST = Decimal("0.000001")

# States from which an order may still be cancelled, and from which a delivery may be received.
_CANCELLABLE = frozenset({PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.SENT})
_RECEIVABLE = frozenset({PurchaseOrderStatus.SENT, PurchaseOrderStatus.PARTIAL})

_WHITESPACE = re.compile(r"\s+")


def _dec(value: object) -> Decimal:
    """Numeric columns are `Mapped[object]` across this codebase, so a value read off a model is
    statically `object` though always a `Decimal` at runtime. Via `str`, so a float that somehow
    reached a column becomes an exact Decimal rather than a binary approximation."""
    return value if isinstance(value, Decimal) else Decimal(str(value))


def normalise_supplier_name(name: str) -> str:
    """Collapse internal whitespace and strip, so one supplier cannot become two.

    G-18: identifiers are normalised at the boundary and uniqueness is a database constraint.
    `"Sharma  Traders "` and `"Sharma Traders"` are the same business, and two rows for it means a
    variance report split in half — which understates the leak by exactly the amount that would
    have made somebody pick up the phone.
    """
    return _WHITESPACE.sub(" ", name).strip()


@dataclass(frozen=True, slots=True)
class OrderLineInput:
    stock_item_id: uuid.UUID
    quantity_ordered: Decimal
    unit_price: Decimal


@dataclass(frozen=True, slots=True)
class ReceiptLineInput:
    """One line of a delivery as the person at the gate reports it.

    `unit_price` is optional: against a purchase order the quoted price is the default, because
    retyping it is how a transcription error enters the one figure the variance report multiplies
    by. Supplying it is how a price change on the invoice gets recorded.
    """

    stock_item_id: uuid.UUID
    quantity_invoiced: Decimal
    quantity_received: Decimal
    quantity_rejected: Decimal = Decimal("0")
    unit_price: Decimal | None = None
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class LineVariance:
    """What one delivered line actually said, with every derivation named.

    `ordered` and `order_shortfall` are `None` for an ad-hoc market purchase, and `None` rather
    than zero on purpose: nothing was ordered, so nothing was under-supplied, and "no order" and
    "delivered in full" are different claims about the world.
    """

    stock_item_id: uuid.UUID
    ordered: Decimal | None
    invoiced: Decimal
    received: Decimal
    rejected: Decimal
    unit_price: Decimal
    landed_unit_cost: Decimal
    rejection_reason: str | None

    @property
    def accepted(self) -> Decimal:
        """The only quantity with a physical meaning: what went on a shelf."""
        return self.received - self.rejected

    @property
    def short_delivery(self) -> Decimal:
        """Billed and not delivered. Signed — over-delivery happens, and it means somebody is
        guessing at the gate rather than weighing."""
        return self.invoiced - self.received

    @property
    def order_shortfall(self) -> Decimal | None:
        return None if self.ordered is None else self.ordered - self.accepted

    @property
    def short_delivery_value(self) -> Decimal:
        return (self.short_delivery * self.unit_price).quantize(_RUPEES)

    @property
    def accepted_value(self) -> Decimal:
        """What the accepted stock cost, landed. This is what reached `stock_batch`."""
        return (self.accepted * self.landed_unit_cost).quantize(_RUPEES)


@dataclass(frozen=True, slots=True)
class ReceiptResult:
    """A posted delivery and the figures a screen may show **after** it is posted.

    Never before. `docs/waste-model.md` is explicit that showing the rupee value of a loss before
    it is recorded suppresses honest reporting, and a receiving screen announcing *"this weight
    will flag your supplier for ₹4,200"* while somebody holds the scale is asking them to choose
    between an accurate number and an awkward conversation.
    """

    # The receipt's **id**, not the ORM object. `GoodsReceipt.lines` is `lazy="raise"`, so an
    # instance handed out of here cannot be serialised without a second, eager read — and the
    # caller commits between the two, which expires it. Returning the id makes that second read
    # explicit rather than a lazy load waiting to raise on whoever calls this next (M09, M15).
    receipt_id: uuid.UUID
    lines: tuple[LineVariance, ...]
    invoice_line_total: Decimal

    @property
    def short_delivery_value(self) -> Decimal:
        return sum((line.short_delivery_value for line in self.lines), Decimal("0"))

    @property
    def accepted_value(self) -> Decimal:
        return sum((line.accepted_value for line in self.lines), Decimal("0"))


@dataclass(frozen=True, slots=True)
class SupplierVariance:
    """The report the module exists for, with its headline already computed."""

    supplier_id: uuid.UUID
    supplier_name: str
    start: date
    end: date
    rows: tuple[VarianceRow, ...]

    @property
    def invoiced(self) -> Decimal:
        return sum((row.invoiced for row in self.rows), Decimal("0"))

    @property
    def received(self) -> Decimal:
        return sum((row.received for row in self.rows), Decimal("0"))

    @property
    def short_delivery_value(self) -> Decimal:
        return sum((row.short_delivery_value for row in self.rows), Decimal("0")).quantize(_RUPEES)

    @property
    def deliveries(self) -> int:
        """Distinct receipts is not summable across items, so the maximum is the honest answer:
        every item was delivered on some subset of the supplier's deliveries, and the item
        appearing most often appeared on all of them."""
        return max((row.deliveries for row in self.rows), default=0)


class ProcurementService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self.suppliers = SupplierRepository(session, scope)
        self.orders = PurchaseOrderRepository(session, scope)
        self.receipts = GoodsReceiptRepository(session, scope)
        self.items = StockItemRepository(session, scope)
        # The ledger's only write path (rule 3), and the owner of the business-date computation.
        self.inventory = InventoryService(session, scope)

    # ------------------------------------------------------------------ helpers

    async def _require_supplier(self, supplier_id: uuid.UUID) -> Supplier:
        supplier = await self.suppliers.get(supplier_id)
        if supplier is None:
            raise NotFoundError(
                "supplier.not_found",
                "That supplier does not exist at this restaurant.",
                {"supplier_id": str(supplier_id)},
            )
        return supplier

    async def _require_order(self, order_id: uuid.UUID) -> PurchaseOrder:
        order = await self.orders.get_for_update(order_id)
        if order is None:
            raise NotFoundError(
                "purchase_order.not_found",
                "That purchase order does not exist at this restaurant.",
                {"purchase_order_id": str(order_id)},
            )
        return order

    async def _require_item(self, stock_item_id: uuid.UUID) -> Any:
        item = await self.items.get(stock_item_id)
        if item is None:
            raise NotFoundError(
                "stock_item.not_found",
                "That stock item does not exist at this restaurant.",
                {"stock_item_id": str(stock_item_id)},
            )
        return item

    # ------------------------------------------------------------------ suppliers

    async def list_suppliers(
        self, *, include_inactive: bool = True, limit: int | None = None
    ) -> Sequence[Supplier]:
        return await self.suppliers.list_all(include_inactive=include_inactive, limit=limit)

    async def get_supplier(self, supplier_id: uuid.UUID) -> Supplier:
        return await self._require_supplier(supplier_id)

    async def create_supplier(self, actor: Actor, *, name: str, **fields: Any) -> Supplier:
        """Add a supplier. The duplicate name is refused with a sentence, not an integrity error."""
        normalised = normalise_supplier_name(name)
        existing = await self.suppliers.by_name(normalised)
        if existing is not None:
            raise ConflictError(
                "supplier.name_taken",
                f"{normalised!r} is already a supplier here. Two rows for one business cannot be "
                "summed, so the variance report would understate what they owe you.",
                {"supplier_id": str(existing.id)},
            )
        supplier = Supplier(restaurant_id=self.scope.restaurant_id, name=normalised, **fields)
        self.session.add(supplier)
        await self.session.flush()
        record(
            self.session,
            actor,
            action="supplier.created",
            entity="supplier",
            entity_id=supplier.id,
            new={"name": normalised},
        )
        return supplier

    async def update_supplier(
        self, actor: Actor, supplier_id: uuid.UUID, changes: dict[str, Any]
    ) -> Supplier:
        """Change a supplier's details, or deactivate it. Never delete it.

        Master-data tier (ADR 0008): every historical receipt points here for ever, and a variance
        report over a supplier nobody buys from any more is still the report that explains last
        quarter.
        """
        supplier = await self.suppliers.get_for_update(supplier_id)
        if supplier is None:
            raise NotFoundError("supplier.not_found", "That supplier does not exist here.")

        if "name" in changes:
            changes["name"] = normalise_supplier_name(changes["name"])
            clash = await self.suppliers.by_name(changes["name"])
            if clash is not None and clash.id != supplier.id:
                raise ConflictError(
                    "supplier.name_taken", f"{changes['name']!r} is already a supplier here."
                )

        before = {"name": supplier.name, "is_active": supplier.is_active}
        if changes.get("is_active") is False and supplier.is_active:
            supplier.deactivated_at = datetime.now(UTC)
        elif changes.get("is_active") is True:
            supplier.deactivated_at = None
        for field, value in changes.items():
            setattr(supplier, field, value)
        await self.session.flush()

        record(
            self.session,
            actor,
            action="supplier.updated",
            entity="supplier",
            entity_id=supplier.id,
            old=before,
            new={"name": supplier.name, "is_active": supplier.is_active},
        )
        return supplier

    # ------------------------------------------------------------------ orders

    async def list_orders(
        self,
        *,
        status: str | None = None,
        supplier_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> Sequence[PurchaseOrder]:
        return await self.orders.list_recent(status=status, supplier_id=supplier_id, limit=limit)

    async def get_order(self, order_id: uuid.UUID) -> PurchaseOrder:
        order = await self.orders.get_with_lines(order_id)
        if order is None:
            raise NotFoundError("purchase_order.not_found", "That purchase order does not exist.")
        return order

    async def create_order(
        self,
        actor: Actor,
        *,
        supplier_id: uuid.UUID,
        lines: Sequence[OrderLineInput],
        expected_at: datetime | None = None,
    ) -> PurchaseOrder:
        """Raise a draft order. Nothing is sent and nothing is committed to a supplier yet."""
        supplier = await self._require_supplier(supplier_id)
        if not supplier.is_active:
            raise AppError(
                "supplier.inactive",
                f"{supplier.name} is no longer an active supplier here. Reactivate them before "
                "ordering.",
            )
        order = PurchaseOrder(
            restaurant_id=self.scope.restaurant_id,
            supplier_id=supplier_id,
            po_number=await self.orders.next_number(),
            status=PurchaseOrderStatus.DRAFT,
            expected_at=expected_at,
            total_amount=Decimal("0"),
            created_by=actor.employee_id,
        )
        self.session.add(order)
        await self.session.flush()
        order.total_amount = await self._replace_lines(order, lines)
        await self.session.flush()
        record(
            self.session,
            actor,
            action="purchase_order.created",
            entity="purchase_order",
            entity_id=order.id,
            new={"po_number": order.po_number, "total_amount": str(order.total_amount)},
        )
        return order

    async def _replace_lines(
        self, order: PurchaseOrder, lines: Sequence[OrderLineInput]
    ) -> Decimal:
        """Write the order's lines and return the total. The total is never sent by a client.

        Duplicate items are refused rather than merged. `uq_po_line_order_item` would refuse them
        anyway, and merging would silently change what somebody typed: two lines of 10 kg might be
        a mistake or might be two crates, and the server is not the thing that knows which.
        """
        if not lines:
            raise AppError("purchase_order.empty", "An order needs at least one line.")
        seen: set[uuid.UUID] = set()
        total = Decimal("0")
        for line in lines:
            if line.stock_item_id in seen:
                raise AppError(
                    "purchase_order.duplicate_item",
                    "That order lists the same item twice. Put the whole quantity on one line.",
                    {"stock_item_id": str(line.stock_item_id)},
                )
            seen.add(line.stock_item_id)
            await self._require_item(line.stock_item_id)
            self.session.add(
                PurchaseOrderLine(
                    restaurant_id=self.scope.restaurant_id,
                    purchase_order_id=order.id,
                    stock_item_id=line.stock_item_id,
                    quantity_ordered=line.quantity_ordered,
                    unit_price=line.unit_price,
                )
            )
            total += line.quantity_ordered * line.unit_price
        return total.quantize(_RUPEES)

    async def update_order(
        self,
        actor: Actor,
        order_id: uuid.UUID,
        *,
        lines: Sequence[OrderLineInput] | None = None,
        expected_at: datetime | None = None,
        set_expected: bool = False,
    ) -> PurchaseOrder:
        """Change a **draft** order. Once sent, a supplier has seen it and it is a commitment."""
        order = await self._require_order(order_id)
        if order.status != PurchaseOrderStatus.DRAFT:
            raise ConflictError(
                "purchase_order.not_draft",
                f"{order.po_number} has already been sent, so its lines cannot change. Cancel it "
                "and raise another if the order was wrong.",
                {"status": order.status},
            )
        if set_expected:
            order.expected_at = expected_at
        if lines is not None:
            for existing in await self.orders.lines_of(order_id):
                await self.session.delete(existing)
            await self.session.flush()
            order.total_amount = await self._replace_lines(order, lines)
        await self.session.flush()
        record(
            self.session,
            actor,
            action="purchase_order.updated",
            entity="purchase_order",
            entity_id=order.id,
        )
        return order

    async def send_order(self, actor: Actor, order_id: uuid.UUID) -> PurchaseOrder:
        order = await self._require_order(order_id)
        if order.status != PurchaseOrderStatus.DRAFT:
            raise ConflictError(
                "purchase_order.not_draft",
                f"{order.po_number} is {order.status}, so it cannot be sent again.",
                {"status": order.status},
            )
        order.status = PurchaseOrderStatus.SENT
        await self.session.flush()
        record(
            self.session,
            actor,
            action="purchase_order.sent",
            entity="purchase_order",
            entity_id=order.id,
            old={"status": PurchaseOrderStatus.DRAFT.value},
            new={"status": order.status},
        )
        return order

    async def cancel_order(
        self, actor: Actor, order_id: uuid.UUID, *, reason: str
    ) -> PurchaseOrder:
        """Cancel an order, with a reason. The row stays: ADR 0008's transactional tier.

        The reason is mandatory and the CHECK constraint pairs it with `cancelled_at`, because a
        cancellation nobody has to explain is exactly the one somebody would use to make an
        over-order disappear.
        """
        if not reason.strip():
            raise AppError(
                "purchase_order.reason_required",
                "Cancelling an order needs a reason. It is a commitment somebody is withdrawing.",
            )
        order = await self._require_order(order_id)
        if order.status not in _CANCELLABLE:
            raise ConflictError(
                "purchase_order.not_cancellable",
                f"{order.po_number} is {order.status}. An order that has been delivered against "
                "cannot be cancelled — the stock is already on the shelf.",
                {"status": order.status},
            )
        previous = order.status
        order.status = PurchaseOrderStatus.CANCELLED
        order.cancelled_at = datetime.now(UTC)
        order.cancel_reason = reason.strip()
        await self.session.flush()
        record(
            self.session,
            actor,
            action="purchase_order.cancelled",
            entity="purchase_order",
            entity_id=order.id,
            old={"status": previous},
            new={"status": order.status, "reason": order.cancel_reason},
        )
        return order

    # ------------------------------------------------------------------ receiving

    async def receive(
        self,
        actor: Actor,
        *,
        supplier_id: uuid.UUID | None = None,
        purchase_order_id: uuid.UUID | None = None,
        lines: Sequence[ReceiptLineInput],
        invoice_number: str | None = None,
        invoice_amount: Decimal | None = None,
        tax_amount: Decimal | None = None,
        received_at: datetime | None = None,
    ) -> ReceiptResult:
        """Post a delivery. The money screen's engine, and all of it or none of it.

        Against a purchase order, `supplier_id` comes from the order — a delivery cannot be
        attributed to a different supplier than the one it was ordered from, and letting a client
        name both is inviting exactly that. Without an order, the supplier is named explicitly and
        the receipt is a market purchase.
        """
        if not lines:
            raise AppError("goods_receipt.empty", "A delivery needs at least one line.")

        order, supplier_id = await self._resolve_source(purchase_order_id, supplier_id)
        await self._assert_invoice_unbooked(supplier_id, invoice_number)

        moment = received_at or datetime.now(UTC)
        receipt = GoodsReceipt(
            restaurant_id=self.scope.restaurant_id,
            purchase_order_id=purchase_order_id,
            supplier_id=supplier_id,
            received_at=moment,
            business_date=await self.inventory.business_date_now(moment),
            invoice_number=invoice_number,
            invoice_amount=invoice_amount,
            tax_amount=tax_amount,
            received_by=actor.employee_id,
        )
        self.session.add(receipt)
        await self.session.flush()

        # One read of the order's lines, not two. The first draft called `_ordered_quantities`
        # and `_ordered_prices` separately and issued the same SELECT twice per delivery, which is
        # the shape of an N+1 even at n=2 — and the kind that grows quietly when a third caller
        # wants a third field off the same rows.
        order_lines = await self._order_lines(order)
        ordered = {item_id: quantity for item_id, (quantity, _) in order_lines.items()}
        priced = self._price_lines(
            lines, ordered_prices={item_id: price for item_id, (_, price) in order_lines.items()}
        )
        variances = self._apportion(priced, ordered=ordered, tax_amount=tax_amount)
        await self._post_lines(actor, receipt, variances, moment=moment)

        if order is not None:
            await self._refresh_order_status(actor, order)
        await self.session.flush()
        record(
            self.session,
            actor,
            action="goods_receipt.posted",
            entity="goods_receipt",
            entity_id=receipt.id,
            new={
                "supplier_id": str(supplier_id),
                "invoice_number": invoice_number,
                "lines": len(variances),
            },
        )
        return ReceiptResult(
            receipt_id=receipt.id,
            lines=tuple(variances),
            invoice_line_total=_invoice_line_total(variances),
        )

    async def _resolve_source(
        self, purchase_order_id: uuid.UUID | None, supplier_id: uuid.UUID | None
    ) -> tuple[PurchaseOrder | None, uuid.UUID]:
        """Where this delivery came from: an order, or a supplier named directly.

        Against a purchase order the supplier comes **from the order**, and the caller's own
        `supplier_id` is ignored rather than checked. A delivery cannot be attributed to a
        different supplier than the one it was ordered from, and a parameter that could say
        otherwise is an invitation to try.
        """
        order = None
        if purchase_order_id is not None:
            order = await self._require_order(purchase_order_id)
            self._assert_receivable(order)
            supplier_id = order.supplier_id
        if supplier_id is None:
            raise AppError(
                "goods_receipt.supplier_required",
                "A delivery with no purchase order behind it has to say who it came from.",
            )
        await self._require_supplier(supplier_id)
        return order, supplier_id

    def _assert_receivable(self, order: PurchaseOrder) -> None:
        if order.status in _RECEIVABLE:
            return
        if order.status == PurchaseOrderStatus.DRAFT:
            raise ConflictError(
                "purchase_order.not_sent",
                f"{order.po_number} has not been sent yet, so nothing can have arrived against "
                "it. Send it first, or book this as a market purchase with no order.",
                {"status": order.status},
            )
        raise ConflictError(
            "purchase_order.closed",
            f"{order.po_number} is {order.status} and cannot take another delivery.",
            {"status": order.status},
        )

    async def _assert_invoice_unbooked(
        self, supplier_id: uuid.UUID, invoice_number: str | None
    ) -> None:
        """One supplier invoice, booked once.

        The partial unique index is the real guard; this exists so the caller is told *which*
        receipt already holds it. Double-booking is the most ordinary error in accounts payable and
        the most ordinary small fraud, and it silently doubles stock — which makes every food-cost
        figure built on it wrong by considerably more than the money.
        """
        if invoice_number is None:
            return
        existing = await self.receipts.by_invoice(supplier_id, invoice_number)
        if existing is not None:
            raise ConflictError(
                "goods_receipt.invoice_already_booked",
                f"Invoice {invoice_number} from this supplier was already booked on "
                f"{existing.business_date}. Booking it twice would double the stock it brought in.",
                {
                    "goods_receipt_id": str(existing.id),
                    "business_date": str(existing.business_date),
                },
            )

    async def _order_lines(
        self, order: PurchaseOrder | None
    ) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
        """What was ordered and at what price, per item, in one query.

        Empty for a market purchase, and that emptiness is what makes `LineVariance.ordered` null
        rather than zero: nothing was ordered, so nothing was under-supplied.
        """
        if order is None:
            return {}
        return {
            line.stock_item_id: (_dec(line.quantity_ordered), _dec(line.unit_price))
            for line in await self.orders.lines_of(order.id)
        }

    def _price_lines(
        self,
        lines: Sequence[ReceiptLineInput],
        *,
        ordered_prices: dict[uuid.UUID, Decimal],
    ) -> list[tuple[ReceiptLineInput, Decimal]]:
        """Resolve each line's pre-tax unit price, and refuse a line nobody can price.

        Against an order the quoted price is the default, so the person at the gate types weights
        rather than retyping prices — which is the single figure the variance report multiplies by,
        and therefore the worst one to transcribe twice.
        """
        priced: list[tuple[ReceiptLineInput, Decimal]] = []
        seen: set[uuid.UUID] = set()
        for line in lines:
            if line.stock_item_id in seen:
                raise AppError(
                    "goods_receipt.duplicate_item",
                    "That delivery lists the same item twice. Put the whole quantity on one line.",
                    {"stock_item_id": str(line.stock_item_id)},
                )
            seen.add(line.stock_item_id)
            price = (
                line.unit_price
                if line.unit_price is not None
                else ordered_prices.get(line.stock_item_id)
            )
            if price is None:
                raise AppError(
                    "goods_receipt.price_required",
                    "That item is not on the order, so the delivery has to say what it cost.",
                    {"stock_item_id": str(line.stock_item_id)},
                )
            priced.append((line, price))
        return priced

    def _apportion(
        self,
        priced: Sequence[tuple[ReceiptLineInput, Decimal]],
        *,
        ordered: dict[uuid.UUID, Decimal],
        tax_amount: Decimal | None,
    ) -> list[LineVariance]:
        """Spread the invoice's tax across the lines, pro rata by value, and build the variances.

        `docs/compliance-rules.md` §A6: a restaurant on the 5% composition scheme bears input GST
        and cannot reclaim it, so the landed cost is what the stock actually cost and it is what
        `stock_batch.unit_cost` must freeze. Exact when every line carries one rate — the ordinary
        case for one supplier's invoice — and an approximation otherwise, because `stock_item`
        carries no tax rate and `library/market-rates.yaml`'s is research about a national market
        rather than this invoice.

        A zero-value invoice (everything free, or every line at zero price) apportions nothing
        rather than dividing by zero.
        """
        line_total = sum((line.quantity_invoiced * price for line, price in priced), Decimal("0"))
        multiplier = 1 + tax_amount / line_total if tax_amount and line_total > 0 else Decimal("1")
        return [
            LineVariance(
                stock_item_id=line.stock_item_id,
                ordered=ordered.get(line.stock_item_id),
                invoiced=line.quantity_invoiced,
                received=line.quantity_received,
                rejected=line.quantity_rejected,
                unit_price=price,
                landed_unit_cost=(price * multiplier).quantize(_UNIT_COST),
                rejection_reason=line.rejection_reason,
            )
            for line, price in priced
        ]

    async def _post_lines(
        self,
        actor: Actor,
        receipt: GoodsReceipt,
        variances: Sequence[LineVariance],
        *,
        moment: datetime,
    ) -> None:
        """Write each receipt line, then the stock it brought in, then the item's new cost.

        **A line that delivered nothing creates no batch and no movement.** `accepted == 0` is a
        real and important row — *"they billed 50 kg and delivered nothing"* — but a zero-quantity
        movement is refused by `ck_stock_movement_quantity_delta`, and rightly: it would pollute
        every average after it. So the receipt line is written and the ledger is left alone.
        """
        for variance in variances:
            item = await self._require_item(variance.stock_item_id)
            line = GoodsReceiptLine(
                restaurant_id=self.scope.restaurant_id,
                goods_receipt_id=receipt.id,
                stock_item_id=variance.stock_item_id,
                quantity_invoiced=variance.invoiced,
                quantity_received=variance.received,
                quantity_rejected=variance.rejected,
                unit_price=variance.unit_price,
                rejection_reason=variance.rejection_reason,
            )
            self.session.add(line)
            await self.session.flush()

            if variance.accepted > 0:
                batch = await self.inventory.receive_stock(
                    actor,
                    stock_item_id=variance.stock_item_id,
                    quantity=variance.accepted,
                    unit_cost=variance.landed_unit_cost,
                    source="purchase",
                    occurred_at=moment,
                    item=item,
                )
                batch.supplier_id = receipt.supplier_id
                batch.goods_receipt_line_id = line.id
                self._reprice(actor, item, variance.landed_unit_cost)
        await self.session.flush()

    def _reprice(self, actor: Actor, item: Any, landed: Decimal) -> None:
        """A real purchase is this restaurant's own truth, so it wins.

        `CostSource` is a confidence ordering — `purchase` beats `manual` beats `market_rate` — and
        its docstring says M06 is what starts writing the top of it. Before this module every
        restaurant's food cost rested on a researched national average; after it, on their own
        supplier's bill.

        Audited for the same reason a menu reprice is: it moves every dish that uses this
        ingredient and leaves no other trace (invariant 6).
        """
        before_cost = _dec(item.current_unit_cost)
        before_source = str(item.cost_source)
        if before_cost == landed and before_source == CostSource.PURCHASE:
            return
        item.current_unit_cost = landed
        item.cost_source = CostSource.PURCHASE
        record(
            self.session,
            actor,
            action="stock_item.repriced",
            entity="stock_item",
            entity_id=item.id,
            old={"current_unit_cost": str(before_cost), "cost_source": before_source},
            new={"current_unit_cost": str(landed), "cost_source": CostSource.PURCHASE.value},
        )

    async def _refresh_order_status(self, actor: Actor, order: PurchaseOrder) -> None:
        """Recompute the order's state from every receipt booked against it.

        The only stored derived value in this module (spec decision 7). Fully received when every
        line's accepted quantity has reached what was ordered; partial when anything has arrived.
        A test asserts the stored value equals this computation after each transition, because a
        stored derived value with no test is a bug waiting.
        """
        ordered = {
            item_id: quantity for item_id, (quantity, _) in (await self._order_lines(order)).items()
        }
        accepted = await self.receipts.accepted_by_item(order.id)
        complete = all(
            accepted.get(item_id, Decimal("0")) >= quantity for item_id, quantity in ordered.items()
        )
        anything = any(value > 0 for value in accepted.values())
        previous = order.status
        if complete:
            order.status = PurchaseOrderStatus.RECEIVED
        elif anything:
            order.status = PurchaseOrderStatus.PARTIAL
        if order.status != previous:
            record(
                self.session,
                actor,
                action="purchase_order.status_changed",
                entity="purchase_order",
                entity_id=order.id,
                old={"status": previous},
                new={"status": order.status},
            )

    # ------------------------------------------------------------------ reads

    async def list_receipts(
        self, *, supplier_id: uuid.UUID | None = None, limit: int | None = None
    ) -> Sequence[GoodsReceipt]:
        return await self.receipts.list_recent(supplier_id=supplier_id, limit=limit)

    async def receivers(self, receipts: Sequence[GoodsReceipt]) -> dict[uuid.UUID, Person]:
        """Who received each delivery, by name, code and role (defect sheet row 22)."""
        return await people(self.session, self.scope, [receipt.received_by for receipt in receipts])

    async def get_receipt(self, receipt_id: uuid.UUID) -> GoodsReceipt:
        receipt = await self.receipts.get_with_lines(receipt_id)
        if receipt is None:
            raise NotFoundError("goods_receipt.not_found", "That delivery does not exist here.")
        return receipt

    async def supplier_variance(
        self, supplier_id: uuid.UUID, *, start: date, end: date
    ) -> SupplierVariance:
        """*"Supplier A short-delivered 4.2% across 31 deliveries this quarter — ₹18,400."*

        That sentence is why this module exists (`docs/waste-model.md` §1), and it is unanswerable
        unless invoiced and received are two columns. They are.
        """
        supplier = await self._require_supplier(supplier_id)
        rows = await self.receipts.supplier_variance(supplier_id, start=start, end=end)
        return SupplierVariance(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            start=start,
            end=end,
            rows=tuple(rows),
        )


def _invoice_line_total(variances: Sequence[LineVariance]) -> Decimal:
    """What the invoice's own lines add up to, before tax.

    Worth returning beside `invoice_amount`: when the two disagree by more than the tax, the
    supplier's arithmetic does not match their own line items, which is a different and more
    interesting problem than a short delivery.
    """
    return sum((line.invoiced * line.unit_price for line in variances), Decimal("0")).quantize(
        _RUPEES
    )
