"""Waste — `docs/schema.md` §8, migration 0033.

Argued in `docs/modules/M09-waste-spec.md`. Three things here are load-bearing:

**1 · A reason is a row, because rows carry policy.** Which of `docs/waste-model.md`'s four stages
the waste belongs to, whether a photograph is wanted, whether somebody senior signs it off — all of
it is a restaurant's decision rather than a constant this product knows. Lumping the four stages
together "produces a number nobody can act on", which is the sentence the `stage` column exists for.

**2 · `cost_value` is NOT NULL, and that is the schema's half of a UI rule.** `docs/waste-model.md`:
never require the person logging waste to know the cost — the system knows — and show the rupee
value only *after*, because showing it before suppresses honest reporting. NOT NULL means an event
cannot be written without the server having computed one, so no "fill the cost in later" path can
exist.

**3 · The event is the human record; the movement is the ledger.** `stock_movement` is append-only
by trigger and holds what actually left the shelf, batch by batch. This table holds who, why, which
stage and which shift. Neither is derivable from the other, and an event without its movement is
waste that everybody can see and that never left the stock book.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
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

from app.core.enums import WastageStage
from app.models.base import Base, TimestampedUUIDMixin


def _uuid() -> Any:
    return postgresql.UUID(as_uuid=True)


class WastageReason(TimestampedUUIDMixin, Base):
    """Why something was thrown away, and what that implies.

    A lookup **table**, never an enum: `requires_photo` and `requires_approval` are policy a
    restaurant sets, and a tandoor's "burnt" wants different handling from a store's "expired".
    """

    __tablename__ = "wastage_reason"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "code", name="uq_wastage_reason_code"),
        UniqueConstraint("id", "restaurant_id", name="uq_wastage_reason_id_restaurant"),
        CheckConstraint(
            "stage IN (" + ", ".join(f"'{stage}'" for stage in WastageStage) + ")",
            name="ck_wastage_reason_stage",
        ),
        Index("ix_wastage_reason_restaurant_stage", "restaurant_id", "stage"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    # **Stored and deliberately not enforced in M09.** Photographs live in `attachment`, which is
    # M11's table. `seed/operations.yaml` sets this on six of its twelve reasons and is right to —
    # those are the six where a photograph is what makes the reason code honest — but a flag
    # nothing can satisfy would leave a cook standing in front of a bin of spoiled paneer with no
    # way to record it. `[planned: M11]`, with a test holding the gap visible (G-7).
    requires_photo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Master-data tier (ADR 0008): deactivated, never deleted. Every historical event points here
    # for ever, and a report over a reason nobody uses any more still explains last quarter.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WastageEvent(TimestampedUUIDMixin, Base):
    """One thing thrown away: what, how much, why, by whom, and what it cost."""

    __tablename__ = "wastage_event"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_wastage_event_id_restaurant"),
        ForeignKeyConstraint(
            ["stock_item_id", "restaurant_id"],
            ["stock_item.id", "stock_item.restaurant_id"],
            name="fk_wastage_event_item_tenant",
        ),
        ForeignKeyConstraint(
            ["stock_batch_id", "restaurant_id"],
            ["stock_batch.id", "stock_batch.restaurant_id"],
            name="fk_wastage_event_batch_tenant",
        ),
        ForeignKeyConstraint(
            ["wastage_reason_id", "restaurant_id"],
            ["wastage_reason.id", "wastage_reason.restaurant_id"],
            name="fk_wastage_event_reason_tenant",
        ),
        ForeignKeyConstraint(
            ["station_id", "restaurant_id"],
            ["station.id", "station.restaurant_id"],
            name="fk_wastage_event_station_tenant",
        ),
        ForeignKeyConstraint(
            ["menu_item_variant_id", "restaurant_id"],
            ["menu_item_variant.id", "menu_item_variant.restaurant_id"],
            name="fk_wastage_event_variant_tenant",
        ),
        ForeignKeyConstraint(
            ["order_line_id", "restaurant_id"],
            ["order_line.id", "order_line.restaurant_id"],
            name="fk_wastage_event_order_line_tenant",
        ),
        CheckConstraint("quantity > 0", name="ck_wastage_event_quantity"),
        CheckConstraint("cost_value >= 0", name="ck_wastage_event_cost_not_negative"),
        # An approval is a person and a time together, or neither. A row claiming to be approved by
        # nobody, or at no time, cannot be audited.
        CheckConstraint(
            "(approved_by IS NULL) = (approved_at IS NULL)", name="ck_wastage_event_approval_pair"
        ),
        Index("ix_wastage_event_restaurant_date", "restaurant_id", "business_date"),
        Index("ix_wastage_event_item_date", "restaurant_id", "stock_item_id", "business_date"),
        Index("ix_wastage_event_order_line", "restaurant_id", "order_line_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    stock_item_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    # FEFO may span several batches, in which case this holds the first and the movements hold the
    # truth. They are the ledger; this is the human record.
    stock_batch_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    wastage_reason_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    # Base units, always (CLAUDE.md invariant 5). Converted at the boundary, never here.
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    # Computed by the server from the batch costs FEFO actually consumed at that moment. There is
    # no field for it in the request schema, so a client that sends one gets a 422 rather than
    # having it quietly dropped.
    cost_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    reported_by: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    # No foreign key: `shift` is M12's table, and nothing waits for a roster to record that
    # something was thrown away. Same shape as `cash_session.shift_id`.
    shift_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    station_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    # When a specific dish caused it, and when a specific plate did. Both optional, and both filled
    # in by a person rather than by the server: M08 deliberately does not book waste when a dish is
    # remade, because it may be reheated rather than binned.
    menu_item_variant_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    order_line_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    approved_by: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)

    reason: Mapped[WastageReason] = relationship(
        primaryjoin="and_(WastageEvent.wastage_reason_id == WastageReason.id, "
        "WastageEvent.restaurant_id == WastageReason.restaurant_id)",
        foreign_keys="[WastageEvent.wastage_reason_id, WastageEvent.restaurant_id]",
        viewonly=True,
        lazy="raise",
    )
