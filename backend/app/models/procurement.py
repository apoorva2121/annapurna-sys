"""Procurement — `docs/schema.md` §6, migration 0017.

**The three numbers are three columns and they are never collapsed.** `quantity_ordered` on the
order line, `quantity_invoiced` and `quantity_received` on the receipt line, plus
`quantity_rejected` for quality refusal at the gate. `docs/waste-model.md` §1 is the whole argument:
*ordered 50 kg, delivered 47 kg, invoiced 50 kg* happens constantly and nobody notices, because
nobody weighs — and a spreadsheet with one `quantity` column makes it invisible for ever. Nothing
in this module writes a single quantity, and the derivations (`accepted`, `short_delivery`,
`order_shortfall`) are computed in the service and named there, so a caller cannot reach for the
wrong one.

**`GoodsReceipt` and `GoodsReceiptLine` cannot be updated or deleted.** Migration 0017 installs the
same trigger 0015 put on `StockMovement`. A receipt writes stock movements the database refuses to
change, so an editable receipt would let somebody weigh honestly and then edit the document to
match the invoice, leaving two records that disagree with nothing able to say which was altered.
Corrections are `adjustment` movements carrying `ref_type='goods_receipt'`.

**`unit_price` excludes tax.** The landed cost — what `stock_batch.unit_cost` freezes and therefore
what every food-cost figure is built on — adds `GoodsReceipt.tax_amount` back, apportioned pro rata
by line value, in `services/procurement.py`. `docs/compliance-rules.md` §A6: a restaurant on the 5%
composition scheme bears input GST and cannot reclaim it, so a quoted price is not a cost.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import PurchaseOrderStatus
from app.models.base import Base, TimestampedUUIDMixin

_PO_STATUSES = ", ".join(f"'{status.value}'" for status in PurchaseOrderStatus)


class Supplier(TimestampedUUIDMixin, Base):
    """Who the restaurant buys from. Master-data tier: deactivated, never deleted.

    The unique name is a data-quality control rather than a nicety. Two spellings of "Sharma
    Traders" are two rows whose deliveries cannot be summed, and a supplier variance report split
    across them understates the leak by exactly the amount that would have made somebody act.
    """

    __tablename__ = "supplier"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "name", name="uq_supplier_restaurant_name"),
        UniqueConstraint("id", "restaurant_id", name="uq_supplier_id_restaurant"),
        CheckConstraint(
            "payment_terms_days IS NULL OR payment_terms_days >= 0",
            name="ck_supplier_payment_terms",
        ),
        Index("ix_supplier_restaurant_active", "restaurant_id", "is_active"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_person: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    gstin: Mapped[str | None] = mapped_column(Text)
    payment_terms_days: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PurchaseOrder(TimestampedUUIDMixin, Base):
    """What was ordered. A commercial document, not a statutory one.

    `status` is the one derived value in this module that is stored, argued in the spec's decision
    7: a PO's state is a function of its receipts, which is cheap for one order and quadratic for
    the list screen a store manager lives on. The service maintains it on every receipt and a test
    asserts the stored value equals a recomputation, because a stored derived value with no test is
    a bug waiting.

    `po_number` is unique per restaurant and monotonic, allocated under a transaction-scoped
    advisory lock. **Gaps carry no legal weight here** — that is M07's invoice numbers, where GST
    law requires a gapless sequence per financial year. The mechanism is rehearsed here on purpose,
    on a document where getting it wrong costs nothing.
    """

    __tablename__ = "purchase_order"
    __table_args__ = (
        ForeignKeyConstraint(
            ["supplier_id", "restaurant_id"],
            ["supplier.id", "supplier.restaurant_id"],
            name="fk_purchase_order_supplier_tenant",
        ),
        UniqueConstraint("restaurant_id", "po_number", name="uq_purchase_order_restaurant_num"),
        UniqueConstraint("id", "restaurant_id", name="uq_purchase_order_id_restaurant"),
        CheckConstraint(f"status IN ({_PO_STATUSES})", name="ck_purchase_order_status"),
        CheckConstraint("total_amount >= 0", name="ck_purchase_order_total"),
        CheckConstraint(
            "(cancelled_at IS NULL) = (cancel_reason IS NULL)",
            name="ck_purchase_order_cancel_pair",
        ),
        Index("ix_purchase_order_restaurant_status", "restaurant_id", "status"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    po_number: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=PurchaseOrderStatus.DRAFT)
    expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Computed from the lines, never sent by a client (`docs/security.md` A04).
    total_amount: Mapped[object] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("employee.id")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)

    lines: Mapped[list[PurchaseOrderLine]] = relationship(
        back_populates="order",
        lazy="raise",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderLine.created_at",
    )


class PurchaseOrderLine(TimestampedUUIDMixin, Base):
    """One item on an order, in base units (invariant 5).

    `restaurant_id` is carried although it is reachable through the order, so both parent
    references can be composite and tenant-safe. Attaching a line to another restaurant's stock
    item is refused by Postgres rather than by a repository remembering to filter.
    """

    __tablename__ = "purchase_order_line"
    __table_args__ = (
        ForeignKeyConstraint(
            ["purchase_order_id", "restaurant_id"],
            ["purchase_order.id", "purchase_order.restaurant_id"],
            name="fk_po_line_order_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["stock_item_id", "restaurant_id"],
            ["stock_item.id", "stock_item.restaurant_id"],
            name="fk_po_line_item_tenant",
        ),
        # An item appears once on an order — which is also what makes the receipt-to-order-line
        # match exact without the receipt line carrying a `purchase_order_line_id`.
        UniqueConstraint("purchase_order_id", "stock_item_id", name="uq_po_line_order_item"),
        CheckConstraint("quantity_ordered > 0", name="ck_po_line_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_po_line_unit_price"),
        Index("ix_po_line_order", "purchase_order_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False
    )
    stock_item_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    quantity_ordered: Mapped[object] = mapped_column(Numeric(14, 4), nullable=False)
    unit_price: Mapped[object] = mapped_column(Numeric(14, 6), nullable=False)

    order: Mapped[PurchaseOrder] = relationship(back_populates="lines", lazy="raise")


class GoodsReceipt(TimestampedUUIDMixin, Base):
    """What actually arrived. Append-only — the database refuses UPDATE and DELETE.

    `purchase_order_id` is nullable and that null is load-bearing (G-13 checklist item 2): a
    receipt with no order behind it is a market purchase at market prices, a different cost story
    from contracted supply, and M13 will want to split the two.

    `invoice_amount` is the total payable, tax included. `tax_amount` is how much of it was tax —
    captured because `docs/compliance-rules.md` §A6 makes it part of the cost of stock for a
    restaurant that cannot reclaim it, and because without the split "how much input GST did we
    bear last year" is permanently unanswerable.
    """

    __tablename__ = "goods_receipt"
    __table_args__ = (
        ForeignKeyConstraint(
            ["purchase_order_id", "restaurant_id"],
            ["purchase_order.id", "purchase_order.restaurant_id"],
            name="fk_goods_receipt_order_tenant",
        ),
        ForeignKeyConstraint(
            ["supplier_id", "restaurant_id"],
            ["supplier.id", "supplier.restaurant_id"],
            name="fk_goods_receipt_supplier_tenant",
        ),
        UniqueConstraint("id", "restaurant_id", name="uq_goods_receipt_id_restaurant"),
        CheckConstraint(
            "invoice_amount IS NULL OR invoice_amount >= 0", name="ck_goods_receipt_invoice_amount"
        ),
        CheckConstraint(
            "tax_amount IS NULL OR tax_amount >= 0", name="ck_goods_receipt_tax_amount"
        ),
        Index("ix_goods_receipt_restaurant_date", "restaurant_id", "business_date"),
        Index("ix_goods_receipt_supplier", "restaurant_id", "supplier_id"),
        Index("ix_goods_receipt_order", "purchase_order_id"),
        # One supplier invoice, booked once. Partial, because a market purchase has no invoice
        # number at all.
        Index(
            "uq_goods_receipt_invoice",
            "restaurant_id",
            "supplier_id",
            "invoice_number",
            unique=True,
            postgresql_where=text("invoice_number IS NOT NULL"),
        ),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(postgresql.UUID(as_uuid=True))
    supplier_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # ADR 0004. A delivery at 01:30 belongs to the previous business day, and the variance report
    # groups on this column.
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    invoice_number: Mapped[str | None] = mapped_column(Text)
    invoice_amount: Mapped[object | None] = mapped_column(Numeric(12, 2))
    tax_amount: Mapped[object | None] = mapped_column(Numeric(12, 2))
    received_by: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("employee.id")
    )

    lines: Mapped[list[GoodsReceiptLine]] = relationship(
        back_populates="receipt", lazy="raise", order_by="GoodsReceiptLine.created_at"
    )


class GoodsReceiptLine(TimestampedUUIDMixin, Base):
    """One item on a delivery, with what was billed beside what was weighed.

    Exactly the shape of `stock_count_line` — `expected` next to `counted`, both stored, never
    reconciled into one. That is invariant 7 pointed at the delivery door instead of the storeroom.

    All three quantities may be zero: *"they billed 50 kg and delivered nothing for this line"* is
    a real and important row. What may not happen is refusing more than arrived, and a rejection
    with no reason.
    """

    __tablename__ = "goods_receipt_line"
    __table_args__ = (
        ForeignKeyConstraint(
            ["goods_receipt_id", "restaurant_id"],
            ["goods_receipt.id", "goods_receipt.restaurant_id"],
            name="fk_gr_line_receipt_tenant",
        ),
        ForeignKeyConstraint(
            ["stock_item_id", "restaurant_id"],
            ["stock_item.id", "stock_item.restaurant_id"],
            name="fk_gr_line_item_tenant",
        ),
        UniqueConstraint("goods_receipt_id", "stock_item_id", name="uq_gr_line_receipt_item"),
        UniqueConstraint("id", "restaurant_id", name="uq_gr_line_id_restaurant"),
        CheckConstraint("quantity_invoiced >= 0", name="ck_gr_line_invoiced"),
        CheckConstraint("quantity_received >= 0", name="ck_gr_line_received"),
        CheckConstraint("quantity_rejected >= 0", name="ck_gr_line_rejected"),
        CheckConstraint(
            "quantity_rejected <= quantity_received", name="ck_gr_line_rejected_within_received"
        ),
        CheckConstraint(
            "quantity_rejected = 0 OR rejection_reason IS NOT NULL",
            name="ck_gr_line_rejection_reason",
        ),
        CheckConstraint("unit_price >= 0", name="ck_gr_line_unit_price"),
        Index("ix_gr_line_receipt", "goods_receipt_id"),
        Index("ix_gr_line_item_date", "restaurant_id", "stock_item_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False
    )
    stock_item_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    # What the bill says.
    quantity_invoiced: Mapped[object] = mapped_column(Numeric(14, 4), nullable=False)
    # What the scale says. The variance between these two is the cheapest money in the product.
    quantity_received: Mapped[object] = mapped_column(Numeric(14, 4), nullable=False)
    quantity_rejected: Mapped[object] = mapped_column(
        Numeric(14, 4), nullable=False, server_default=text("0")
    )
    # Excluding tax. The landed cost adds the receipt's apportioned tax back, in the service.
    unit_price: Mapped[object] = mapped_column(Numeric(14, 6), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    receipt: Mapped[GoodsReceipt] = relationship(back_populates="lines", lazy="raise")


__all__ = [
    "GoodsReceipt",
    "GoodsReceiptLine",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "PurchaseOrderStatus",
    "Supplier",
]
