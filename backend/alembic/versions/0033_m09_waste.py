"""m09 - waste: a reason that carries policy, and an event that cannot exist without its movement

Two tables from `docs/schema.md` §8. The module is small because M05 built the hard part - FEFO,
per-batch cost, the shortfall placeholder, the append-only ledger - and `stock_movement.ref_type`
already lists `wastage_event`, so nothing here touches the ledger's own schema.

Four things are deliberate.

**1. `wastage_reason` is a table, not an enum.** Its rows carry policy a restaurant sets: which of
the four stages the waste belongs to (`docs/waste-model.md` - receiving, storage, prep, service),
whether a photograph is wanted, whether somebody senior has to approve it. A tandoor's "burnt" and
a store's "expired" want different handling, and that is data rather than a constant this product
knows.

**2. `cost_value` is NOT NULL, which is the schema's half of "never ask the person logging".**
`docs/waste-model.md`: never require the person logging waste to know the cost - the system knows -
and show the rupee value only *after*, because showing it before suppresses honest reporting. The
column being NOT NULL means an event cannot be written without the server having computed it, so
there is no shape of this table that a "we'll fill the cost in later" code path could use.

**3. `shift_id` is a bare column with no foreign key**, exactly as `cash_session.shift_id` is. The
`shift` table is M12's, and M09 does not wait for a roster to record that something was thrown away.
The constraint arrives with M12.

**4. No append-only trigger, and the reason is different from M08's.** A `wastage_event` genuinely
should not change - but the thing that must not change is the *stock movement*, and 0015 already
refuses UPDATE and DELETE on `stock_movement` at the database. An event whose movement cannot move
is an event whose correction has to be a new adjustment movement, which is the path M05 designed.
Adding a second trigger here would protect the descriptive row while the authoritative one was
already protected, and would block the one legitimate update: an approver signing an event off.

Revision ID: 0033_m09_waste
Revises: 0032_m08_kitchen_issues
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_m09_waste"
down_revision: str | None = "0032_m08_kitchen_issues"
branch_labels: str | None = None
depends_on: str | None = None

# `docs/waste-model.md`'s four stages. Lumping them produces a number nobody can act on, which is
# the whole reason the column exists.
_STAGES = ("receiving", "storage", "prep", "service")


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
    # ---------------------------------------------------------------- wastage_reason
    op.create_table(
        "wastage_reason",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        # Stored and, in M09, deliberately not enforced: photographs live in `attachment`, which is
        # M11's table. `seed/operations.yaml` sets this on six of its twelve reasons and is right
        # to - those are the six where a photograph is what makes the reason code honest - but
        # enforcing a flag nothing can satisfy would leave a cook standing in front of a bin of
        # spoiled paneer with no way to record it. Tagged [planned: M11]; a test holds the gap
        # visible so it cannot quietly read as built (G-7).
        sa.Column("requires_photo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        # Master-data tier (ADR 0008): deactivated, never deleted. Every historical event points
        # here for ever, and a waste report over a reason nobody uses any more is still the report
        # that explains last quarter.
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.UniqueConstraint("restaurant_id", "code", name="uq_wastage_reason_code"),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_wastage_reason_id_restaurant"),
        sa.CheckConstraint(
            "stage IN (" + ", ".join(f"'{stage}'" for stage in _STAGES) + ")",
            name="ck_wastage_reason_stage",
        ),
    )
    op.create_index(
        "ix_wastage_reason_restaurant_stage", "wastage_reason", ["restaurant_id", "stage"]
    )

    # ---------------------------------------------------------------- wastage_event
    op.create_table(
        "wastage_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("stock_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Which batch it came out of, when the service knows. FEFO may span several, in which case
        # this holds the first and the movements hold the truth - they are the ledger, this is the
        # human record.
        sa.Column("stock_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("wastage_reason_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 4), nullable=False),
        # Computed by the server from the batch costs FEFO actually consumed. Never sent by a
        # client: there is no field for it in the request schema, so a client that tries gets a 422
        # from `extra="forbid"` rather than having it silently dropped.
        sa.Column("cost_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column(
            "reported_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=False,
        ),
        # No foreign key: `shift` is M12's table, and nothing waits for a roster to record that
        # something was thrown away. Same shape as `cash_session.shift_id`.
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("station_id", postgresql.UUID(as_uuid=True), nullable=True),
        # When a specific dish caused it, and when a specific plate did. Both optional and both
        # filled in by a person, never by the server: M08 deliberately does not book waste when a
        # dish is remade, because it may be reheated rather than binned.
        sa.Column("menu_item_variant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("order_line_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("employee.id")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["stock_item_id", "restaurant_id"],
            ["stock_item.id", "stock_item.restaurant_id"],
            name="fk_wastage_event_item_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["stock_batch_id", "restaurant_id"],
            ["stock_batch.id", "stock_batch.restaurant_id"],
            name="fk_wastage_event_batch_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["wastage_reason_id", "restaurant_id"],
            ["wastage_reason.id", "wastage_reason.restaurant_id"],
            name="fk_wastage_event_reason_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["station_id", "restaurant_id"],
            ["station.id", "station.restaurant_id"],
            name="fk_wastage_event_station_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["menu_item_variant_id", "restaurant_id"],
            ["menu_item_variant.id", "menu_item_variant.restaurant_id"],
            name="fk_wastage_event_variant_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["order_line_id", "restaurant_id"],
            ["order_line.id", "order_line.restaurant_id"],
            name="fk_wastage_event_order_line_tenant",
        ),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_wastage_event_id_restaurant"),
        sa.CheckConstraint("quantity > 0", name="ck_wastage_event_quantity"),
        sa.CheckConstraint("cost_value >= 0", name="ck_wastage_event_cost_not_negative"),
        # An approval is a person and a time together, or neither. A row claiming to be approved by
        # nobody, or at no time, is a row that cannot be audited.
        sa.CheckConstraint(
            "(approved_by IS NULL) = (approved_at IS NULL)", name="ck_wastage_event_approval_pair"
        ),
    )
    op.create_index(
        "ix_wastage_event_restaurant_date", "wastage_event", ["restaurant_id", "business_date"]
    )
    # The summary's query: what did this item cost us, over this range.
    op.create_index(
        "ix_wastage_event_item_date",
        "wastage_event",
        ["restaurant_id", "stock_item_id", "business_date"],
    )
    # M10 reads this: a returned dish is a waste event and a customer-experience signal at once.
    op.create_index(
        "ix_wastage_event_order_line", "wastage_event", ["restaurant_id", "order_line_id"]
    )


def downgrade() -> None:
    op.drop_table("wastage_event")
    op.drop_table("wastage_reason")
