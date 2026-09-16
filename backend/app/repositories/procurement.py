"""Queries over suppliers, orders and deliveries. Business rules live in the service, not here.

Two of these carry the module's weight.

**`accepted_by_item` is one aggregate, not a walk.** "How much of this order has actually arrived?"
is asked on every receipt and on every PO detail screen, and the honest answer sums the accepted
quantity across *every* receipt booked against the order — partial deliveries are the ordinary
case. Loading the receipts and adding them up in Python would be a query per receipt and would be
wrong the moment somebody books two deliveries in parallel.

**`supplier_variance` is the report the module exists for** (`docs/waste-model.md` §1), so it is a
single grouped aggregate bounded by `business_date` on `ix_goods_receipt_restaurant_date`. It never
touches the stock ledger: the variance between what a supplier billed and what a scale said lives
entirely in `goods_receipt_line`, which is exactly why those two quantities are stored side by side
rather than reconciled into one.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, literal, select
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.models.procurement import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.stock import StockItem
from app.repositories.base import RestaurantScopedRepository, page_size

# Two-int advisory lock keys: a namespace, then the restaurant. The namespace is an arbitrary but
# fixed constant so that this lock can never collide with a different kind of lock taken elsewhere
# on the same restaurant id.
_PO_LOCK_NAMESPACE = 60_001

# `po_number` is compared as text, so the padding is what makes `max()` mean "the highest number".
# `PO-000009` sorts before `PO-000010` only because both are six digits wide. Past a million orders
# the width would grow and the ordering would silently invert, so the service refuses to allocate
# past it rather than producing a number that breaks the next allocation.
PO_NUMBER_WIDTH = 6
PO_NUMBER_PREFIX = "PO-"
MAX_PO_SEQUENCE = 10**PO_NUMBER_WIDTH - 1


@dataclass(frozen=True, slots=True)
class VarianceRow:
    """One stock item's delivery record with one supplier, over a window.

    Quantities in base units; `short_delivery_value` in rupees. `short_delivery` is
    `invoiced - received`: what was billed and did not arrive. It is signed, because over-delivery
    happens too and a supplier who consistently sends *more* than they bill is also worth knowing
    about — usually it means somebody is guessing at the gate rather than weighing.
    """

    stock_item_id: uuid.UUID
    code: str
    name: str
    base_unit: str
    deliveries: int
    invoiced: Decimal
    received: Decimal
    rejected: Decimal
    short_delivery: Decimal
    short_delivery_value: Decimal


class SupplierRepository(RestaurantScopedRepository[Supplier]):
    model = Supplier

    async def list_all(
        self, *, include_inactive: bool = True, limit: int | None = None
    ) -> Sequence[Supplier]:
        """Name order, because that is how a supplier list is read and searched."""
        query = self.scoped().order_by(Supplier.name)
        if not include_inactive:
            query = query.where(Supplier.is_active.is_(True))
        result = await self.session.scalars(query.limit(page_size(limit)))
        return result.all()

    async def by_name(self, name: str) -> Supplier | None:
        """The duplicate check the unique constraint backs up.

        Checked here so the caller gets a sentence naming the existing supplier rather than an
        integrity error, and constrained in the database so the check-then-insert race cannot
        create the second row anyway (G-18).
        """
        result = await self.session.scalars(self.scoped().where(Supplier.name == name))
        return result.first()

    async def get_for_update(self, supplier_id: uuid.UUID) -> Supplier | None:
        result = await self.session.scalars(
            self.scoped().where(Supplier.id == supplier_id).with_for_update()
        )
        return result.first()


class PurchaseOrderRepository(RestaurantScopedRepository[PurchaseOrder]):
    model = PurchaseOrder

    async def get_with_lines(self, order_id: uuid.UUID) -> PurchaseOrder | None:
        result = await self.session.scalars(
            self.scoped()
            .where(PurchaseOrder.id == order_id)
            .options(selectinload(PurchaseOrder.lines))
        )
        return result.first()

    async def get_for_update(self, order_id: uuid.UUID) -> PurchaseOrder | None:
        """Locked, because receiving reads the status, posts stock and writes the status back."""
        result = await self.session.scalars(
            self.scoped().where(PurchaseOrder.id == order_id).with_for_update()
        )
        return result.first()

    async def list_recent(
        self,
        *,
        status: str | None = None,
        supplier_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> Sequence[PurchaseOrder]:
        query = self.scoped().order_by(PurchaseOrder.po_number.desc())
        if status is not None:
            query = query.where(PurchaseOrder.status == status)
        if supplier_id is not None:
            query = query.where(PurchaseOrder.supplier_id == supplier_id)
        result = await self.session.scalars(
            query.limit(page_size(limit)).options(selectinload(PurchaseOrder.lines))
        )
        return result.all()

    async def next_number(self) -> str:
        """Allocate the next `PO-000000` for this restaurant, safely.

        `SELECT max(...) + 1` on its own is a race: two managers raising an order in the same second
        both read 41 and both try to write `PO-000042`. The unique constraint would save the data
        and hand one of them a 500.

        So a transaction-scoped advisory lock is taken on `(namespace, restaurant)` first. It is
        released by the commit or the rollback, so it cannot be leaked by a failed request, and it
        serialises allocation per restaurant — a throughput ceiling of one order at a time, which is
        entirely right for a document a human types once or twice a day.

        **This is deliberately the mechanism M07 will need for GST invoice numbers**, where
        `docs/modules.md` requires a gapless sequence per financial year and gaplessness is law
        rather than tidiness. Rehearsing it here, on a document where a gap costs nothing, is much
        cheaper than debugging it on one where a gap is a compliance breach. M07 will need the same
        proof at a very different rate: invoices are issued per bill, during service.
        """
        await self.session.execute(
            select(
                func.pg_advisory_xact_lock(
                    literal(_PO_LOCK_NAMESPACE), func.hashtext(str(self.scope.restaurant_id))
                )
            )
        )
        highest = await self.session.execute(
            select(func.max(PurchaseOrder.po_number)).where(
                PurchaseOrder.restaurant_id == self.scope.restaurant_id
            )
        )
        current = highest.scalar_one_or_none()
        sequence = 1 if current is None else int(current.removeprefix(PO_NUMBER_PREFIX)) + 1
        if sequence > MAX_PO_SEQUENCE:  # pragma: no cover - a million orders at one restaurant
            raise AppError(
                "purchase_order.sequence_exhausted",
                "This restaurant has reached the last purchase-order number this format can "
                "hold. Widening it changes how every existing number sorts, so it needs a "
                "migration rather than a retry.",
            )
        return f"{PO_NUMBER_PREFIX}{sequence:0{PO_NUMBER_WIDTH}d}"

    async def lines_of(self, order_id: uuid.UUID) -> Sequence[PurchaseOrderLine]:
        result = await self.session.scalars(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.restaurant_id == self.scope.restaurant_id,
                PurchaseOrderLine.purchase_order_id == order_id,
            )
        )
        return result.all()


class GoodsReceiptRepository(RestaurantScopedRepository[GoodsReceipt]):
    model = GoodsReceipt

    async def get_with_lines(self, receipt_id: uuid.UUID) -> GoodsReceipt | None:
        result = await self.session.scalars(
            self.scoped()
            .where(GoodsReceipt.id == receipt_id)
            .options(selectinload(GoodsReceipt.lines))
        )
        return result.first()

    async def list_recent(
        self, *, supplier_id: uuid.UUID | None = None, limit: int | None = None
    ) -> Sequence[GoodsReceipt]:
        query = self.scoped().order_by(GoodsReceipt.received_at.desc())
        if supplier_id is not None:
            query = query.where(GoodsReceipt.supplier_id == supplier_id)
        result = await self.session.scalars(
            query.limit(page_size(limit)).options(selectinload(GoodsReceipt.lines))
        )
        return result.all()

    async def by_invoice(self, supplier_id: uuid.UUID, invoice_number: str) -> GoodsReceipt | None:
        """Has this supplier's invoice already been booked?

        The partial unique index is the real guard; this exists so the caller can say *which*
        receipt already holds it, because "invoice 4471 was booked on 11 March" is actionable and
        "duplicate key value violates unique constraint" is not.
        """
        result = await self.session.scalars(
            self.scoped().where(
                GoodsReceipt.supplier_id == supplier_id,
                GoodsReceipt.invoice_number == invoice_number,
            )
        )
        return result.first()

    def _accepted(self) -> Select[tuple[uuid.UUID, object]]:
        """Scoped on the **line**, and that is enough — deliberately, not by omission.

        The join to `goods_receipt` carries no `restaurant_id` predicate of its own, which looks
        like the #1 bug class until you check why it is safe: `fk_gr_line_receipt_tenant` is a
        composite foreign key on `(goods_receipt_id, restaurant_id)`, so a line and its receipt
        cannot belong to different restaurants. Postgres guarantees it rather than this query
        remembering to. The same argument covers the `stock_item` join in `supplier_variance`.
        """
        accepted = func.sum(GoodsReceiptLine.quantity_received - GoodsReceiptLine.quantity_rejected)
        return (
            select(GoodsReceiptLine.stock_item_id, accepted.label("accepted"))
            .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
            .where(GoodsReceiptLine.restaurant_id == self.scope.restaurant_id)
            .group_by(GoodsReceiptLine.stock_item_id)
        )

    async def accepted_by_item(self, order_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
        """What has actually arrived against one order, per item, across every receipt.

        *Accepted*, not received: a quality rejection arrived and was refused, so it never entered
        stock and it does not fill the order either. A supplier who delivers 50 kg of which 6 are
        rotten has delivered 44 against the order, and the PO stays open for the rest.
        """
        rows = await self.session.execute(
            self._accepted().where(GoodsReceipt.purchase_order_id == order_id)
        )
        return {row[0]: Decimal(str(row[1])) for row in rows.all()}

    async def supplier_variance(
        self, supplier_id: uuid.UUID, *, start: date, end: date
    ) -> list[VarianceRow]:
        """The three-way report, per item, for one supplier over a business-date window.

        Ordered by money lost, descending, because the first row is the one worth a phone call.
        `deliveries` counts distinct receipts rather than lines, so an item appearing on eight
        deliveries reads as eight and not as however many lines those receipts happened to carry.
        """
        short = GoodsReceiptLine.quantity_invoiced - GoodsReceiptLine.quantity_received
        short_value = func.sum(short * GoodsReceiptLine.unit_price).label("short_value")
        rows = await self.session.execute(
            select(
                GoodsReceiptLine.stock_item_id,
                StockItem.code,
                StockItem.name,
                StockItem.base_unit,
                func.count(func.distinct(GoodsReceipt.id)),
                func.sum(GoodsReceiptLine.quantity_invoiced),
                func.sum(GoodsReceiptLine.quantity_received),
                func.sum(GoodsReceiptLine.quantity_rejected),
                func.sum(short),
                short_value,
            )
            .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
            .join(StockItem, StockItem.id == GoodsReceiptLine.stock_item_id)
            .where(
                GoodsReceiptLine.restaurant_id == self.scope.restaurant_id,
                GoodsReceipt.supplier_id == supplier_id,
                GoodsReceipt.business_date >= start,
                GoodsReceipt.business_date <= end,
            )
            .group_by(
                GoodsReceiptLine.stock_item_id, StockItem.code, StockItem.name, StockItem.base_unit
            )
            .order_by(short_value.desc())
        )
        return [
            VarianceRow(
                stock_item_id=row[0],
                code=row[1],
                name=row[2],
                base_unit=row[3],
                deliveries=row[4],
                invoiced=Decimal(str(row[5])),
                received=Decimal(str(row[6])),
                rejected=Decimal(str(row[7])),
                short_delivery=Decimal(str(row[8])),
                short_delivery_value=Decimal(str(row[9])),
            )
            for row in rows.all()
        ]
