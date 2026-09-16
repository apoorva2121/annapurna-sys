"""The kitchen — `docs/schema.md` §7's second half, migration 0030.

Argued in `docs/modules/M08-kitchen-spec.md`. Three things here are load-bearing:

**1 · A ticket is a round.** One per send, per station — never one per order per station, which is
what the §7 sketch said. A second send is a second piece of paper in every real kitchen, and
folding it into the first ticket would either destroy that ticket's `ready_at` or hide the new
dishes from the chef. `sequence_in_order` says which round this is.

**2 · The kitchen never writes money.** Nothing in this file is a `Numeric`. That is not an
accident of scope: `ready` is cheap to press, and the control against a cook clearing a rail of
food that never left the pass is that clearing it settles nothing. `served` belongs to the floor.

**3 · `revision` is how a dropped connection loses nothing.** Every kitchen write bumps
`KotStreamCursor` and stamps the tickets it touched, so `GET /kot/stream` can replay from a
client's `Last-Event-ID` rather than from a queue nobody kept. Per restaurant rather than a global
sequence, so a kitchen screen cannot infer the platform's cross-tenant write volume from its own
event ids.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import KotLineStatus, KotTicketStatus
from app.models.base import Base, TimestampedUUIDMixin
from app.models.orders import Order


def _uuid() -> Any:
    """`Any` for the reason `app/models/orders.py` uses it: `postgresql.UUID` is generic, and
    spelling the parameter out here buys nothing a reader wants."""
    return postgresql.UUID(as_uuid=True)


def _in(column: str, enum: type[KotTicketStatus] | type[KotLineStatus]) -> str:
    return f"{column} IN (" + ", ".join(f"'{member}'" for member in enum) + ")"


class KotStreamCursor(Base):
    """One row per restaurant: the counter `GET /kot/stream` replays against.

    Not a Postgres sequence, and not `updated_at`. A sequence is global, and a global cursor handed
    to a client leaks how busy every other tenant is. `updated_at` is not monotonic under
    concurrency, and "the kitchen display lost a ticket" is the one failure this module may not
    have.
    """

    __tablename__ = "kot_stream_cursor"
    __table_args__ = (CheckConstraint("last_revision >= 0", name="ck_kot_stream_cursor_revision"),)

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), primary_key=True
    )
    # Bumped once per transaction, not once per row: a send that creates three tickets is one
    # kitchen event and all three carry the same revision. Which is also why the stream replays
    # *inclusively* from a client's cursor — see the service.
    last_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # Written out rather than taken from `TimestampedUUIDMixin`, because that mixin brings a UUID
    # primary key with it and this table's key is the restaurant.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class KotTicket(TimestampedUUIDMixin, Base):
    """One round of dishes, at one station, for one order."""

    __tablename__ = "kot_ticket"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_kot_ticket_id_restaurant"),
        UniqueConstraint(
            "restaurant_id", "business_date", "ticket_number", name="uq_kot_ticket_number_per_day"
        ),
        UniqueConstraint("order_id", "station_id", "sequence_in_order", name="uq_kot_ticket_round"),
        ForeignKeyConstraint(
            ["order_id", "restaurant_id"],
            ["order.id", "order.restaurant_id"],
            name="fk_kot_ticket_order_tenant",
        ),
        ForeignKeyConstraint(
            ["station_id", "restaurant_id"],
            ["station.id", "station.restaurant_id"],
            name="fk_kot_ticket_station_tenant",
        ),
        CheckConstraint(_in("status", KotTicketStatus), name="ck_kot_ticket_status"),
        CheckConstraint("target_minutes > 0", name="ck_kot_ticket_target_minutes"),
        CheckConstraint("sequence_in_order > 0", name="ck_kot_ticket_sequence"),
        CheckConstraint("revision > 0", name="ck_kot_ticket_revision"),
        CheckConstraint(
            "started_at IS NULL OR acknowledged_at IS NOT NULL", name="ck_kot_ticket_started_order"
        ),
        CheckConstraint(
            "ready_at IS NULL OR started_at IS NOT NULL", name="ck_kot_ticket_ready_order"
        ),
        CheckConstraint(
            "served_at IS NULL OR ready_at IS NOT NULL", name="ck_kot_ticket_served_order"
        ),
        Index("ix_kot_ticket_rail", "restaurant_id", "station_id", "status"),
        Index("ix_kot_ticket_printed", "restaurant_id", "printed_at"),
        Index("ix_kot_ticket_revision", "restaurant_id", "revision"),
        Index("ix_kot_ticket_order", "restaurant_id", "order_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    # Copied from `menu_item.station_id` at the send and never recomputed: moving a dish to another
    # station next month must not re-route last night's tickets.
    station_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    ticket_number: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_in_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=KotTicketStatus.NEW)
    is_remake: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # The standard, frozen. The actual is `ready_at - printed_at`. Invariant 7's shape: the gap
    # between them is the measurement, so neither may ever overwrite the other.
    target_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    printed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    ready_by: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list[KotTicketLine]] = relationship(
        back_populates="ticket",
        order_by="KotTicketLine.seq",
        lazy="raise",
        cascade="all, delete-orphan",
    )
    # The rail shows an order number and which tables to carry the food to. The dish names are on
    # the line already, so this is the only thing a ticket has to join for — and the tables are
    # deliberately read live rather than snapshotted: a party that pushes two tables together
    # halfway through the meal has to be found where they are now.
    #
    # `viewonly`, because the kitchen may read an order and must never write one. The composite
    # foreign key is tenant-safe, so this cannot reach another restaurant's order even if a query
    # forgot to scope itself.
    order: Mapped[Order] = relationship(
        primaryjoin="and_(KotTicket.order_id == Order.id, "
        "KotTicket.restaurant_id == Order.restaurant_id)",
        foreign_keys="[KotTicket.order_id, KotTicket.restaurant_id]",
        viewonly=True,
        lazy="raise",
    )


class KotTicketLine(TimestampedUUIDMixin, Base):
    """One dish on a ticket, with the three timestamps external review S2 asked for.

    The ticket knows when its *slowest* dish finished. Only these columns can say how long the dal
    took, which is what M13's prep-time work and M17's fairness work both read.
    """

    __tablename__ = "kot_ticket_line"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_kot_ticket_line_id_restaurant"),
        UniqueConstraint(
            "kot_ticket_id", "order_line_id", name="uq_kot_ticket_line_once_per_ticket"
        ),
        ForeignKeyConstraint(
            ["kot_ticket_id", "restaurant_id"],
            ["kot_ticket.id", "kot_ticket.restaurant_id"],
            name="fk_kot_ticket_line_ticket_tenant",
        ),
        ForeignKeyConstraint(
            ["order_line_id", "restaurant_id"],
            ["order_line.id", "order_line.restaurant_id"],
            name="fk_kot_ticket_line_order_line_tenant",
        ),
        CheckConstraint(_in("status", KotLineStatus), name="ck_kot_ticket_line_status"),
        CheckConstraint("quantity > 0", name="ck_kot_ticket_line_quantity"),
        CheckConstraint(
            "status <> 'remake' OR remake_reason IS NOT NULL",
            name="ck_kot_ticket_line_remake_reason",
        ),
        CheckConstraint(
            "served_at IS NULL OR ready_at IS NOT NULL", name="ck_kot_ticket_line_served_order"
        ),
        Index("ix_kot_ticket_line_ticket", "restaurant_id", "kot_ticket_id"),
        Index("ix_kot_ticket_line_order_line", "restaurant_id", "order_line_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    kot_ticket_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    order_line_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    quantity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Copied from the menu at the send. A KOT is a printed instruction: it says what it said when
    # it printed, even after the dish is renamed or withdrawn. It also keeps the rail query — the
    # only one here with a latency budget — free of any join to the menu.
    item_name: Mapped[str] = mapped_column(Text, nullable=False)
    variant_name: Mapped[str] = mapped_column(Text, nullable=False)
    modifier_summary: Mapped[str | None] = mapped_column(Text)
    special_instructions: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=KotLineStatus.PENDING)
    remake_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    ticket: Mapped[KotTicket] = relationship(back_populates="lines", lazy="raise")
