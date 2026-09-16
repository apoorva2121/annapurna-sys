"""The inventory ledger — `docs/schema.md` §5, migration 0015.

**On-hand is never stored.** It is `SUM(stock_movement.quantity_delta)`, always. There is no
`quantity_on_hand` column anywhere in this file and adding one would be invariant 2's exact
failure mode: two sources of truth that agree right up until the moment one of them matters.

**`basis` is the product.** `theoretical` is what a recipe says was used; `actual` is what somebody
physically observed. On-hand sums both, because both genuinely move the book. What must never be
summed across the two is a single *consumption* figure — their difference is the leakage number
this product exists to surface (invariant 7). See `docs/modules/M05-inventory-spec.md` decision 1.

**`StockMovement` cannot be updated or deleted.** Migration 0015 installs a trigger that refuses
both. Mutating one of these objects and flushing raises `ProgrammingError` from Postgres, which is
deliberate: the guarantee lives where it cannot be forgotten rather than in a repository somebody
has to remember. Corrections are new `adjustment` rows.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import MovementBasis, MovementType, StockCountScope, StockCountStatus
from app.models.base import Base, TimestampedUUIDMixin

_MOVEMENT_TYPES = ", ".join(f"'{t.value}'" for t in MovementType)


class StockBatch(TimestampedUUIDMixin, Base):
    """A quantity of one stock item that arrived together, at one cost.

    `quantity_received` is immutable and is *not* what is left — what is left is derived from the
    movements against it. A fully consumed batch still records what it arrived with, because that
    is a fact about the past and the FEFO selection needs to know it happened.
    """

    __tablename__ = "stock_batch"
    __table_args__ = (
        # Tenant safety in the schema rather than in a filter somebody has to remember. CLAUDE.md
        # calls cross-tenant leakage the #1 bug class here; the composite key makes attaching a
        # batch to another restaurant's item impossible rather than merely tested-against.
        ForeignKeyConstraint(
            ["stock_item_id", "restaurant_id"],
            ["stock_item.id", "stock_item.restaurant_id"],
            name="fk_stock_batch_item_tenant",
        ),
        UniqueConstraint("restaurant_id", "batch_code", name="uq_stock_batch_restaurant_code"),
        UniqueConstraint("id", "restaurant_id", name="uq_stock_batch_id_restaurant"),
        CheckConstraint(
            "source IN ('purchase', 'production', 'opening', 'transfer')",
            name="ck_stock_batch_source",
        ),
        CheckConstraint("quantity_received >= 0", name="ck_stock_batch_quantity_received"),
        CheckConstraint("unit_cost >= 0", name="ck_stock_batch_unit_cost"),
        Index("ix_stock_batch_fefo", "restaurant_id", "stock_item_id", "expiry_date"),
        Index(
            "ix_stock_batch_expiry",
            "restaurant_id",
            "expiry_date",
            postgresql_where=lambda: StockBatch.expiry_date.isnot(None),
        ),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    stock_item_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    batch_code: Mapped[str] = mapped_column(Text, nullable=False)
    quantity_received: Mapped[object] = mapped_column(Numeric(14, 4), nullable=False)
    # Frozen at receipt or production. Every movement against this batch copies it, so the cost of
    # a consumption is the cost of what was actually consumed rather than today's price.
    unit_cost: Mapped[object] = mapped_column(Numeric(14, 6), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Drives FEFO. NULL means "no expiry known", which sorts last — a dated batch is always used
    # before an undated one.
    expiry_date: Mapped[date | None] = mapped_column(Date)
    storage_location: Mapped[str | None] = mapped_column(Text)
    # No foreign keys: both target M06 tables that do not exist yet. `docs/schema.md` anticipates
    # this and asks for the constraints in a follow-up migration. Nothing in M05 writes them.
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(postgresql.UUID(as_uuid=True))
    goods_receipt_line_id: Mapped[uuid.UUID | None] = mapped_column(postgresql.UUID(as_uuid=True))
    source: Mapped[str] = mapped_column(Text, nullable=False)

    movements: Mapped[list[StockMovement]] = relationship(
        back_populates="batch", lazy="raise", order_by="StockMovement.occurred_at"
    )


class StockMovement(TimestampedUUIDMixin, Base):
    """One line of the append-only ledger. Never updated, never deleted — the database refuses.

    `quantity_delta` is signed: a receipt is positive, a consumption negative. Summing this column
    over an item is the definition of on-hand, and it is the only definition.
    """

    __tablename__ = "stock_movement"
    __table_args__ = (
        ForeignKeyConstraint(
            ["stock_batch_id", "restaurant_id"],
            ["stock_batch.id", "stock_batch.restaurant_id"],
            name="fk_stock_movement_batch_tenant",
        ),
        ForeignKeyConstraint(
            ["stock_item_id", "restaurant_id"],
            ["stock_item.id", "stock_item.restaurant_id"],
            name="fk_stock_movement_item_tenant",
        ),
        CheckConstraint(f"type IN ({_MOVEMENT_TYPES})", name="ck_stock_movement_type"),
        CheckConstraint("basis IN ('theoretical', 'actual')", name="ck_stock_movement_basis"),
        # A zero movement is always a bug, and it pollutes every count and average downstream.
        CheckConstraint("quantity_delta <> 0", name="ck_stock_movement_quantity_delta"),
        CheckConstraint("unit_cost >= 0", name="ck_stock_movement_unit_cost"),
        CheckConstraint("(ref_type IS NULL) = (ref_id IS NULL)", name="ck_stock_movement_ref_pair"),
        Index("ix_stock_movement_item_date", "restaurant_id", "stock_item_id", "business_date"),
        Index("ix_stock_movement_type_date", "restaurant_id", "type", "business_date"),
        Index("ix_stock_movement_ref", "ref_type", "ref_id"),
        Index("ix_stock_movement_batch", "stock_batch_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    stock_batch_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    # Denormalised from the batch: nearly every query asks about an item over a date range and never
    # needs the batch, so this removes a join from the hot path (`docs/schema.md` §5).
    stock_item_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    quantity_delta: Mapped[object] = mapped_column(Numeric(14, 4), nullable=False)
    unit_cost: Mapped[object] = mapped_column(Numeric(14, 6), nullable=False)
    basis: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # ADR 0004. Not `occurred_at::date` — a restaurant closing at 2am books that sale to the day
    # before, and every aggregate in M13 groups by this column.
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    actor_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("employee.id")
    )
    ref_type: Mapped[str | None] = mapped_column(Text)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(postgresql.UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)

    batch: Mapped[StockBatch] = relationship(back_populates="movements", lazy="raise")


class StockCount(TimestampedUUIDMixin, Base):
    """A physical count. Forward-only: draft -> submitted -> approved.

    Nothing posts to the ledger until approval. A submitted count is a worksheet; an approved one
    writes the `adjustment` movements that bring the book to what was on the shelf.

    There is deliberately no delete endpoint. A count that came out badly is exactly the count
    somebody would want to lose.
    """

    __tablename__ = "stock_count"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_stock_count_id_restaurant"),
        CheckConstraint("scope IN ('full', 'partial', 'spot')", name="ck_stock_count_scope"),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'approved')", name="ck_stock_count_status"
        ),
        # Separation of duties. The service checks this too and says why; the constraint is what
        # keeps it true if a future path forgets to ask.
        CheckConstraint(
            "approved_by IS NULL OR counted_by IS NULL OR approved_by <> counted_by",
            name="ck_stock_count_approver_differs",
        ),
        Index("ix_stock_count_restaurant_date", "restaurant_id", "business_date"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    counted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False, default=StockCountScope.FULL)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=StockCountStatus.DRAFT)
    counted_by: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("employee.id")
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("employee.id")
    )

    lines: Mapped[list[StockCountLine]] = relationship(
        back_populates="count", lazy="raise", cascade="all, delete-orphan"
    )


class StockCountLine(TimestampedUUIDMixin, Base):
    """One item on a count sheet, with the book position frozen beside what was on the shelf.

    `system_quantity` is captured when the line is written, not recomputed at approval. The ledger
    keeps moving during a count, and a variance recalculated later against a different book is not
    the variance anybody actually observed.
    """

    __tablename__ = "stock_count_line"
    __table_args__ = (
        ForeignKeyConstraint(
            ["stock_count_id", "restaurant_id"],
            ["stock_count.id", "stock_count.restaurant_id"],
            name="fk_stock_count_line_count_tenant",
        ),
        ForeignKeyConstraint(
            ["stock_item_id", "restaurant_id"],
            ["stock_item.id", "stock_item.restaurant_id"],
            name="fk_stock_count_line_item_tenant",
        ),
        UniqueConstraint("stock_count_id", "stock_item_id", name="uq_stock_count_line_count_item"),
        CheckConstraint("counted_quantity >= 0", name="ck_stock_count_line_counted"),
        Index("ix_stock_count_line_count", "stock_count_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    stock_count_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    stock_item_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    system_quantity: Mapped[object] = mapped_column(Numeric(14, 4), nullable=False)
    counted_quantity: Mapped[object] = mapped_column(Numeric(14, 4), nullable=False)
    # Negative means less on the shelf than the book claims — the direction that costs money.
    variance_value: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)

    count: Mapped[StockCount] = relationship(back_populates="lines", lazy="raise")


__all__ = [
    "MovementBasis",
    "MovementType",
    "StockBatch",
    "StockCount",
    "StockCountLine",
    "StockCountScope",
    "StockCountStatus",
    "StockMovement",
]
