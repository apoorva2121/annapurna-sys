"""m05 - the inventory ledger

Four tables from `docs/schema.md` §5. This is the spine of the product: M03 said what a restaurant
sells, M04 said what a dish should cost, and this is where theoretical and actual become comparable.
M07 settlement, M09 waste and M13's variance report all write to or read from `stock_movement`.

Three things here are deliberate and argued in `docs/modules/M05-inventory-spec.md`:

**1. `stock_movement` refuses UPDATE and DELETE at the database.** Invariant 2 says the ledger is
append-only. As a repository convention that is one careless `session.merge()` away from silent
violation, and no test can see it afterwards — the row simply looks different. A trigger puts the
guarantee where it cannot be forgotten, which is the same reasoning as guardrail G-13. Corrections
are new `adjustment` movements, which is what invariant 2 already prescribes.

The suite is unaffected: `conftest.py` cleans up by rolling back an outer transaction, not by
issuing DELETEs, and row-level triggers do not fire on TRUNCATE.

**2. Tenant-safe composite foreign keys.** `uq_stock_item_id_restaurant` has existed since 0011
with nothing using it. It exists for this: `stock_batch` references
`stock_item (id, restaurant_id)`, so attaching a batch to another tenant's item is refused by
Postgres rather than by a repository remembering to filter. CLAUDE.md calls cross-tenant leakage
the #1 bug class in this product; this is the one place it can be made structurally impossible.

**3. `supplier_id` and `goods_receipt_line_id` are columns without foreign keys.** Both point at
M06 tables that do not exist yet. `docs/schema.md` anticipates exactly this — *"`stock_batch.
goods_receipt_line_id` ... circular against later steps — add both as a nullable FK in a follow-up
migration"*. The columns are created here so the table's shape matches §5; M06 adds the two
constraints. Nothing in M05 writes either column.

`quantity_delta` is CHECKed non-zero. A zero movement is always a bug and it silently pollutes
every count and average that follows it.

Revision ID: 0015_m05_inventory
Revises: 0014_stock_item_cost_source
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_m05_inventory"
down_revision: str | None = "0014_stock_item_cost_source"
branch_labels: str | None = None
depends_on: str | None = None

_MOVEMENT_TYPES = (
    "receipt",
    "production",
    "consumption",
    "wastage",
    "staff_meal",
    "complimentary",
    "transfer",
    "adjustment",
    "count",
)


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
    # ---------------------------------------------------------------- stock_batch
    op.create_table(
        "stock_batch",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("stock_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_code", sa.Text(), nullable=False),
        # Immutable once written. What is left of it is derived from the movements, never stored —
        # invariant 2. A batch that has been fully consumed still carries what it arrived with.
        sa.Column("quantity_received", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 6), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("storage_location", sa.Text(), nullable=True),
        # No FK: `supplier` is an M06 table. See the module docstring.
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("goods_receipt_line_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["stock_item_id", "restaurant_id"],
            ["stock_item.id", "stock_item.restaurant_id"],
            name="fk_stock_batch_item_tenant",
        ),
        sa.UniqueConstraint("restaurant_id", "batch_code", name="uq_stock_batch_restaurant_code"),
        # So `stock_movement` can carry the same tenant-safe composite reference.
        sa.UniqueConstraint("id", "restaurant_id", name="uq_stock_batch_id_restaurant"),
        sa.CheckConstraint(
            "source IN ('purchase', 'production', 'opening', 'transfer')",
            name="ck_stock_batch_source",
        ),
        # A receipt of nothing is a bug. Zero is allowed for exactly one case, argued in the spec:
        # the placeholder batch created when stock is consumed that nobody recorded receiving.
        sa.CheckConstraint("quantity_received >= 0", name="ck_stock_batch_quantity_received"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_stock_batch_unit_cost"),
    )
    # The FEFO index. `expiry_date` leads because that is what the selection orders by.
    op.create_index(
        "ix_stock_batch_fefo", "stock_batch", ["restaurant_id", "stock_item_id", "expiry_date"]
    )
    # Expiry alerts scan only dated batches, so the partial index keeps the undated ones out of it.
    op.create_index(
        "ix_stock_batch_expiry",
        "stock_batch",
        ["restaurant_id", "expiry_date"],
        postgresql_where=sa.text("expiry_date IS NOT NULL"),
    )

    # ---------------------------------------------------------------- stock_movement
    op.create_table(
        "stock_movement",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("stock_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Denormalised from the batch on purpose (§5): almost every query asks about an item over a
        # date range and never needs the batch, so carrying it here removes a join from the hot path.
        sa.Column("stock_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        # Signed. Negative consumes. On-hand is the sum of this column and is never stored.
        sa.Column("quantity_delta", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 6), nullable=False),
        # INVARIANT 7. `theoretical` is recipe-derived, `actual` is physically observed. On-hand
        # sums both — what must never be summed is a single *consumption* figure across the two,
        # because their difference is the product. See the spec, decision 1.
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        # ADR 0004: the restaurant's business day, which is not midnight to midnight.
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column(
            "actor_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=True,
        ),
        sa.Column("ref_type", sa.Text(), nullable=True),
        sa.Column("ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["stock_batch_id", "restaurant_id"],
            ["stock_batch.id", "stock_batch.restaurant_id"],
            name="fk_stock_movement_batch_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["stock_item_id", "restaurant_id"],
            ["stock_item.id", "stock_item.restaurant_id"],
            name="fk_stock_movement_item_tenant",
        ),
        sa.CheckConstraint(
            "type IN (" + ", ".join(f"'{t}'" for t in _MOVEMENT_TYPES) + ")",
            name="ck_stock_movement_type",
        ),
        sa.CheckConstraint("basis IN ('theoretical', 'actual')", name="ck_stock_movement_basis"),
        sa.CheckConstraint("quantity_delta <> 0", name="ck_stock_movement_quantity_delta"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_stock_movement_unit_cost"),
        sa.CheckConstraint(
            "(ref_type IS NULL) = (ref_id IS NULL)", name="ck_stock_movement_ref_pair"
        ),
    )
    op.create_index(
        "ix_stock_movement_item_date",
        "stock_movement",
        ["restaurant_id", "stock_item_id", "business_date"],
    )
    op.create_index(
        "ix_stock_movement_type_date",
        "stock_movement",
        ["restaurant_id", "type", "business_date"],
    )
    # The connective tissue: "show me the movements this order wrote".
    op.create_index("ix_stock_movement_ref", "stock_movement", ["ref_type", "ref_id"])
    # On-hand per batch is the FEFO selection's inner question, and it groups by batch.
    op.create_index("ix_stock_movement_batch", "stock_movement", ["stock_batch_id"])

    # INVARIANT 2, enforced rather than trusted. The message names the remedy, because the person
    # who hits this is usually mid-change and needs to know what to do instead.
    op.execute(
        """
        CREATE FUNCTION stock_movement_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'stock_movement is append-only (invariant 2): % refused. '
                'Record a correction as a new movement of type ''adjustment''.', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_stock_movement_append_only
        BEFORE UPDATE OR DELETE ON stock_movement
        FOR EACH ROW EXECUTE FUNCTION stock_movement_append_only();
        """
    )

    # ---------------------------------------------------------------- stock_count
    op.create_table(
        "stock_count",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("counted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        # Forward-only: draft -> submitted -> approved. There is no delete endpoint, so a count that
        # came out badly cannot quietly disappear.
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "counted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("employee.id"), nullable=True
        ),
        sa.Column(
            "approved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=True,
        ),
        *_timestamps(),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_stock_count_id_restaurant"),
        sa.CheckConstraint("scope IN ('full', 'partial', 'spot')", name="ck_stock_count_scope"),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'approved')", name="ck_stock_count_status"
        ),
        # Separation of duties: nobody approves their own count. The service checks this too, with a
        # message; the constraint is what makes it true even if a future path forgets to ask.
        sa.CheckConstraint(
            "approved_by IS NULL OR counted_by IS NULL OR approved_by <> counted_by",
            name="ck_stock_count_approver_differs",
        ),
    )
    op.create_index(
        "ix_stock_count_restaurant_date", "stock_count", ["restaurant_id", "business_date"]
    )

    # ---------------------------------------------------------------- stock_count_line
    op.create_table(
        "stock_count_line",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stock_count_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stock_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        # What the ledger said at the moment of counting — frozen, because the ledger keeps moving
        # and a variance recomputed later against a different book is not the variance anyone saw.
        sa.Column("system_quantity", sa.Numeric(14, 4), nullable=False),
        sa.Column("counted_quantity", sa.Numeric(14, 4), nullable=False),
        # The leakage number, in rupees. Negative means less on the shelf than the book claims.
        sa.Column("variance_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["stock_count_id", "restaurant_id"],
            ["stock_count.id", "stock_count.restaurant_id"],
            name="fk_stock_count_line_count_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["stock_item_id", "restaurant_id"],
            ["stock_item.id", "stock_item.restaurant_id"],
            name="fk_stock_count_line_item_tenant",
        ),
        sa.UniqueConstraint(
            "stock_count_id", "stock_item_id", name="uq_stock_count_line_count_item"
        ),
        sa.CheckConstraint("counted_quantity >= 0", name="ck_stock_count_line_counted"),
    )
    op.create_index("ix_stock_count_line_count", "stock_count_line", ["stock_count_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_count_line_count", table_name="stock_count_line")
    op.drop_table("stock_count_line")
    op.drop_index("ix_stock_count_restaurant_date", table_name="stock_count")
    op.drop_table("stock_count")
    op.execute("DROP TRIGGER IF EXISTS trg_stock_movement_append_only ON stock_movement;")
    op.execute("DROP FUNCTION IF EXISTS stock_movement_append_only();")
    for name in (
        "ix_stock_movement_batch",
        "ix_stock_movement_ref",
        "ix_stock_movement_type_date",
        "ix_stock_movement_item_date",
    ):
        op.drop_index(name, table_name="stock_movement")
    op.drop_table("stock_movement")
    for name in ("ix_stock_batch_expiry", "ix_stock_batch_fefo"):
        op.drop_index(name, table_name="stock_batch")
    op.drop_table("stock_batch")
