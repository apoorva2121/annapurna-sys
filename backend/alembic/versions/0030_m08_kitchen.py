"""m08 - the kitchen: tickets, their lines, and the cursor the display recovers from

Three tables from `docs/schema.md` §7, two of them sketched there since P1 and one that is new.
Every decision below is argued in `docs/modules/M08-kitchen-spec.md`; what follows is why the
database looks like this rather than like the sketch.

**1. A ticket is a round, not an order** (spec decision 1). The §7 sketch says "one per order per
station". A table that orders starters and then, twenty minutes later, mains, produces two pieces
of paper in every real kitchen. Folding the second send into the first ticket means either dragging
a ticket that was already `ready` back to `new` - destroying the `ready_at` that M13 and M17 are
built on - or adding dishes to a ticket the chef has already cleared off the rail. So there is no
unique constraint on `(order_id, station_id)`, and `sequence_in_order` records which round this is.

**2. `target_minutes` is copied, not joined** (spec decision 6). It is the maximum `prep_minutes`
of the variants on the ticket, frozen at creation, for the same reason `order_line.unit_price` is
copied: re-deriving it later from a menu that has since been edited would rewrite history. The gap
between it and `ready_at - printed_at` is the kitchen-performance number, and neither value is ever
allowed to overwrite the other (CLAUDE.md invariant 7's shape, applied to time).

**3. `kot_stream_cursor` and `kot_ticket.revision` are the whole recovery story** (spec decision 3).
Every kitchen write bumps a per-restaurant counter and stamps the tickets it touched. `GET
/kot/stream` replays from a client's `Last-Event-ID`, so a dropped connection loses nothing because
nothing was ever only in flight. The counter is **per restaurant** rather than a global sequence:
a global one leaks cross-tenant write volume to every kitchen screen, since a client can watch its
own event ids jump by four hundred and learn how busy the rest of the platform is.

**4. `kot_ticket_line` carries three timestamps the sketch does not have.** External review finding
S2: without `started_at`, `ready_at` and `served_at` on the *line*, per-dish prep time is
unmeasurable and cannot be reconstructed from any other row. They cost nothing today and are the
input to M13 and M17.

**5. `station` gains `UNIQUE (id, restaurant_id)`.** It is the target `kot_ticket`'s tenant-safe
composite foreign key needs, and every other parent in this codebase already has one. Safe on
existing data by construction: `id` is the primary key, so it is already unique.

**No append-only trigger here, and that is deliberate.** A ticket is a live working row - it moves
through its states for the whole time a dish is being cooked. Its immutability is the service's
state machine, not a trigger, and the *order* side is already protected: 0019's trigger refuses
every change to a settled order except its kitchen columns, which is precisely what this module
writes.

Revision ID: 0030_m08_kitchen
Revises: 0029_issue_catalogue
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_m08_kitchen"
down_revision: str | None = "0029_issue_catalogue"
branch_labels: str | None = None
depends_on: str | None = None

_TICKET_STATUSES = ("new", "acknowledged", "preparing", "ready", "served", "cancelled")
_LINE_STATUSES = ("pending", "preparing", "ready", "served", "cancelled", "remake")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def upgrade() -> None:
    # ------------------------------------------------- the target the composite keys below need
    op.create_unique_constraint("uq_station_id_restaurant", "station", ["id", "restaurant_id"])

    # ---------------------------------------------------------------- kot_stream_cursor
    op.create_table(
        "kot_stream_cursor",
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            primary_key=True,
        ),
        # Bumped with UPDATE ... RETURNING, once per transaction rather than once per row: a send
        # that creates three tickets is one kitchen event and they share one revision.
        sa.Column("last_revision", sa.BigInteger(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.CheckConstraint("last_revision >= 0", name="ck_kot_stream_cursor_revision"),
    )

    # ---------------------------------------------------------------- kot_ticket
    op.create_table(
        "kot_ticket",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Snapshotted from `menu_item.station_id` at the send and never recomputed (spec decision
        # 2). A restaurant that moves biryani to another station next month must not rewrite last
        # night's tickets.
        sa.Column("station_id", postgresql.UUID(as_uuid=True), nullable=False),
        # What is printed and what a person says out loud. Restarts every business day, like
        # `order.order_number`, because a counter that never resets is not something anyone calls.
        sa.Column("ticket_number", sa.Text(), nullable=False),
        sa.Column("sequence_in_order", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text(), nullable=False, server_default="new"),
        # Fresh work that repeats earlier work. Without it M13's "how long do mains take" silently
        # averages remakes into standards.
        sa.Column("is_remake", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("target_minutes", sa.SmallInteger(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("served_at", sa.DateTime(timezone=True), nullable=True),
        # Attribution, because M17's workload fairness is built on who actually did the work and
        # cannot be backfilled from anywhere.
        sa.Column(
            "acknowledged_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=True,
        ),
        sa.Column(
            "ready_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("employee.id"), nullable=True
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["order_id", "restaurant_id"],
            ["order.id", "order.restaurant_id"],
            name="fk_kot_ticket_order_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["station_id", "restaurant_id"],
            ["station.id", "station.restaurant_id"],
            name="fk_kot_ticket_station_tenant",
        ),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_kot_ticket_id_restaurant"),
        sa.UniqueConstraint(
            "restaurant_id",
            "business_date",
            "ticket_number",
            name="uq_kot_ticket_number_per_day",
        ),
        sa.UniqueConstraint(
            "order_id", "station_id", "sequence_in_order", name="uq_kot_ticket_round"
        ),
        sa.CheckConstraint(_in("status", _TICKET_STATUSES), name="ck_kot_ticket_status"),
        sa.CheckConstraint("target_minutes > 0", name="ck_kot_ticket_target_minutes"),
        sa.CheckConstraint("sequence_in_order > 0", name="ck_kot_ticket_sequence"),
        sa.CheckConstraint("revision > 0", name="ck_kot_ticket_revision"),
        # The clock only ever runs forwards. Held here rather than only in the service, because a
        # ticket with a `ready_at` and no `started_at` is an unanswerable prep-time question, and
        # the answer is needed years after whoever wrote the bug has gone. Cancellation is exempt
        # by construction: these say nothing about `status`.
        sa.CheckConstraint(
            "started_at IS NULL OR acknowledged_at IS NOT NULL", name="ck_kot_ticket_started_order"
        ),
        sa.CheckConstraint(
            "ready_at IS NULL OR started_at IS NOT NULL", name="ck_kot_ticket_ready_order"
        ),
        sa.CheckConstraint(
            "served_at IS NULL OR ready_at IS NOT NULL", name="ck_kot_ticket_served_order"
        ),
    )
    # The KDS query, and the only one with a latency budget (50 ms with 200 open tickets).
    op.create_index("ix_kot_ticket_rail", "kot_ticket", ["restaurant_id", "station_id", "status"])
    op.create_index("ix_kot_ticket_printed", "kot_ticket", ["restaurant_id", "printed_at"])
    # The stream query: everything at or after a client's cursor.
    op.create_index("ix_kot_ticket_revision", "kot_ticket", ["restaurant_id", "revision"])
    op.create_index("ix_kot_ticket_order", "kot_ticket", ["restaurant_id", "order_id"])

    # ---------------------------------------------------------------- kot_ticket_line
    op.create_table(
        "kot_ticket_line",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("kot_ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        # **What to cook, spelled out and frozen.** Copied from the menu at the send, for the same
        # reason `order_line.unit_price` is copied and for one more: a KOT is a printed
        # instruction, and it must still say what it said when it printed even after the dish is
        # renamed or deactivated. It also takes three joins off the one query in this module with
        # a latency budget - the display resolves nothing.
        sa.Column("item_name", sa.Text(), nullable=False),
        sa.Column("variant_name", sa.Text(), nullable=False),
        # "No onion, Extra spicy". The half of a ticket that gets a dish sent back when it is
        # missed, so it is a column rather than something the display joins for.
        sa.Column("modifier_summary", sa.Text(), nullable=True),
        sa.Column("special_instructions", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("remake_reason", sa.Text(), nullable=True),
        # External review S2. Per-dish prep time is unmeasurable without these and cannot be
        # reconstructed from the ticket, which only knows when its slowest dish finished.
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("served_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("seq", sa.SmallInteger(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["kot_ticket_id", "restaurant_id"],
            ["kot_ticket.id", "kot_ticket.restaurant_id"],
            name="fk_kot_ticket_line_ticket_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["order_line_id", "restaurant_id"],
            ["order_line.id", "order_line.restaurant_id"],
            name="fk_kot_ticket_line_order_line_tenant",
        ),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_kot_ticket_line_id_restaurant"),
        # A dish appears once on a ticket. A second helping of the same dish is a second order
        # line, which is how M07 already models it.
        sa.UniqueConstraint(
            "kot_ticket_id", "order_line_id", name="uq_kot_ticket_line_once_per_ticket"
        ),
        sa.CheckConstraint(_in("status", _LINE_STATUSES), name="ck_kot_ticket_line_status"),
        sa.CheckConstraint("quantity > 0", name="ck_kot_ticket_line_quantity"),
        # A remake without a reason is a remake nobody can learn from (spec decision 8).
        sa.CheckConstraint(
            "status <> 'remake' OR remake_reason IS NOT NULL",
            name="ck_kot_ticket_line_remake_reason",
        ),
        sa.CheckConstraint(
            "served_at IS NULL OR ready_at IS NOT NULL", name="ck_kot_ticket_line_served_order"
        ),
    )
    op.create_index(
        "ix_kot_ticket_line_ticket", "kot_ticket_line", ["restaurant_id", "kot_ticket_id"]
    )
    # M09 and M13 both ask "what happened to this dish", and the answer starts here.
    op.create_index(
        "ix_kot_ticket_line_order_line", "kot_ticket_line", ["restaurant_id", "order_line_id"]
    )


def downgrade() -> None:
    op.drop_table("kot_ticket_line")
    op.drop_table("kot_ticket")
    op.drop_table("kot_stream_cursor")
    op.drop_constraint("uq_station_id_restaurant", "station", type_="unique")
