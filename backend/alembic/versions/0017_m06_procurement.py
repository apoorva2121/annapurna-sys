"""m06 - procurement, and the two foreign keys M05 left dangling

Five tables from `docs/schema.md` §6. The point of the module is one sentence from
`docs/waste-model.md` §1 — *"ordered 50 kg, delivered 47 kg, invoiced 50 kg"* — and it is
unanswerable unless those are three separate columns. They are, and there is a fourth
(`quantity_rejected`), because quality refusal at the gate is a different fact from short delivery.

Four things here are deliberate and argued in `docs/modules/M06-procurement-spec.md`:

**1. `goods_receipt` and `goods_receipt_line` refuse UPDATE and DELETE.** ADR 0008 does not name
them, so the spec assigns them to the *ledger* tier alongside `stock_movement`, and for the threat
rather than the taxonomy: a receipt writes stock movements the database already refuses to change,
so an editable receipt is one `UPDATE` away from "receive 47, take 3 home, edit the receipt to say
50 so the invoice reconciles". The movements would still say 47 and nothing could say which record
had been altered. The correction path is a `stock.adjust` movement with `ref_type='goods_receipt'`
— a reference `stock_movement`'s CHECK constraint already permits, because M05 designed for this.

**2. `restaurant_id` on `purchase_order_line` and `goods_receipt_line`**, which the §6 sketch does
not give them. Same reason `stock_count_line` carries one: every parent reference is a composite
foreign key on `(id, restaurant_id)`, so attaching a receipt line to another restaurant's stock
item is refused by Postgres rather than by a repository remembering to filter.

**3. `tax_amount` on `goods_receipt`**, also beyond the sketch. `docs/compliance-rules.md` §A6: a
restaurant on the 5% composition scheme *bears* input GST and cannot reclaim it, so a quoted price
is not a cost. Storing only the pre-tax price understates food cost by the whole tax rate, on the
product's headline number. Storing only the tax-inclusive total makes "how much input GST did we
bear last year" permanently unanswerable. Both are captured; the landed cost is derived in the
service, pro rata by line value.

**4. The two `stock_batch` foreign keys.** `supplier_id` and `goods_receipt_line_id` have been bare
columns since 0015 because they pointed at tables that did not exist. `docs/schema.md` §5 asks for
the constraints "in a follow-up migration"; this is it. Nothing has ever written either column, and
the migration asserts that rather than assuming it.

Revision ID: 0017_m06_procurement
Revises: 0016_m05_inventory_permissions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_m06_procurement"
down_revision: str | None = "0016_m05_inventory_permissions"
branch_labels: str | None = None
depends_on: str | None = None

_PO_STATUSES = ("draft", "sent", "partial", "received", "cancelled")


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def _append_only(table: str) -> None:
    """Refuse UPDATE and DELETE on a table, the way 0015 does for `stock_movement`.

    One function per table rather than a shared one, because the exception message names the
    correction path, and "record an adjustment against the receipt" is only good advice for these
    two tables.

    The suite is unaffected: `conftest.py` rolls back an outer transaction instead of issuing
    DELETEs, and row-level triggers do not fire on TRUNCATE.
    """
    op.execute(
        f"""
        CREATE FUNCTION {table}_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                '{table} is append-only: % refused. A receipt records what arrived, and it '
                'wrote stock movements that cannot be changed either. Correct it with a stock '
                'adjustment referencing the receipt.', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_{table}_append_only
        BEFORE UPDATE OR DELETE ON {table}
        FOR EACH ROW EXECUTE FUNCTION {table}_append_only();
        """
    )


def upgrade() -> None:
    # ---------------------------------------------------------------- supplier
    op.create_table(
        "supplier",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("contact_person", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("gstin", sa.Text(), nullable=True),
        sa.Column("payment_terms_days", sa.SmallInteger(), nullable=True),
        # Master-data tier (ADR 0008): deactivated, never deleted. Every historical receipt points
        # at this row for ever, and a variance report over a supplier nobody buys from any more is
        # still the report that explains last quarter.
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        # One name, one supplier. Two spellings of "Sharma Traders" are two rows that cannot be
        # summed, which is a variance report quietly halved. Normalised at the boundary (G-18) and
        # made unique here, because a check-then-insert is never the only guard.
        sa.UniqueConstraint("restaurant_id", "name", name="uq_supplier_restaurant_name"),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_supplier_id_restaurant"),
        sa.CheckConstraint(
            "payment_terms_days IS NULL OR payment_terms_days >= 0",
            name="ck_supplier_payment_terms",
        ),
    )
    op.create_index("ix_supplier_restaurant_active", "supplier", ["restaurant_id", "is_active"])

    # ---------------------------------------------------------------- purchase_order
    op.create_table(
        "purchase_order",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Human-facing, allocated server-side under an advisory lock (spec decision 3). Separate
        # from the UUID per ADR 0008: business-readable identifiers are their own column.
        sa.Column("po_number", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("expected_at", sa.DateTime(timezone=True), nullable=True),
        # Computed from the lines by the service, never accepted from a client
        # (`docs/security.md` A04).
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("employee.id"), nullable=True
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["supplier_id", "restaurant_id"],
            ["supplier.id", "supplier.restaurant_id"],
            name="fk_purchase_order_supplier_tenant",
        ),
        sa.UniqueConstraint("restaurant_id", "po_number", name="uq_purchase_order_restaurant_num"),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_purchase_order_id_restaurant"),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in _PO_STATUSES) + ")",
            name="ck_purchase_order_status",
        ),
        sa.CheckConstraint("total_amount >= 0", name="ck_purchase_order_total"),
        # A cancellation with no reason is a cancellation nobody has to explain, which is exactly
        # the one somebody would use to make an over-order disappear.
        sa.CheckConstraint(
            "(cancelled_at IS NULL) = (cancel_reason IS NULL)",
            name="ck_purchase_order_cancel_pair",
        ),
    )
    op.create_index(
        "ix_purchase_order_restaurant_status", "purchase_order", ["restaurant_id", "status"]
    )

    # ---------------------------------------------------------------- purchase_order_line
    op.create_table(
        "purchase_order_line",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Beyond the §6 sketch, for the composite foreign keys below.
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stock_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Base units, always (invariant 5). Conversion from the supplier's sack or crate happens at
        # the boundary, so nothing downstream has to know what a "bag" was.
        sa.Column("quantity_ordered", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 6), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["purchase_order_id", "restaurant_id"],
            ["purchase_order.id", "purchase_order.restaurant_id"],
            name="fk_po_line_order_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stock_item_id", "restaurant_id"],
            ["stock_item.id", "stock_item.restaurant_id"],
            name="fk_po_line_item_tenant",
        ),
        # An item appears once on an order. This is also what makes the receipt-to-order-line match
        # exact without a `purchase_order_line_id` column on the receipt line.
        sa.UniqueConstraint("purchase_order_id", "stock_item_id", name="uq_po_line_order_item"),
        sa.CheckConstraint("quantity_ordered > 0", name="ck_po_line_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_po_line_unit_price"),
    )
    op.create_index("ix_po_line_order", "purchase_order_line", ["purchase_order_id"])

    # ---------------------------------------------------------------- goods_receipt
    op.create_table(
        "goods_receipt",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        # Nullable, and that null is the channel marker (G-13 checklist item 2): a receipt with no
        # order behind it is a market purchase at market prices, which is a different cost story
        # from contracted supply.
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        # ADR 0004. Not `received_at::date` — a delivery at 01:30 belongs to the previous business
        # day, and every aggregate in the variance report groups on this column.
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("invoice_number", sa.Text(), nullable=True),
        # What the supplier billed in total, tax included — the figure that leaves the bank.
        sa.Column("invoice_amount", sa.Numeric(12, 2), nullable=True),
        # What of that was tax. Nullable: an unregistered market trader charges none.
        sa.Column("tax_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "received_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=True,
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["purchase_order_id", "restaurant_id"],
            ["purchase_order.id", "purchase_order.restaurant_id"],
            name="fk_goods_receipt_order_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id", "restaurant_id"],
            ["supplier.id", "supplier.restaurant_id"],
            name="fk_goods_receipt_supplier_tenant",
        ),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_goods_receipt_id_restaurant"),
        sa.CheckConstraint(
            "invoice_amount IS NULL OR invoice_amount >= 0", name="ck_goods_receipt_invoice_amount"
        ),
        sa.CheckConstraint(
            "tax_amount IS NULL OR tax_amount >= 0", name="ck_goods_receipt_tax_amount"
        ),
    )
    op.create_index(
        "ix_goods_receipt_restaurant_date", "goods_receipt", ["restaurant_id", "business_date"]
    )
    op.create_index("ix_goods_receipt_supplier", "goods_receipt", ["restaurant_id", "supplier_id"])
    op.create_index("ix_goods_receipt_order", "goods_receipt", ["purchase_order_id"])
    # One supplier invoice, booked once. The most ordinary error in accounts payable and the most
    # ordinary small fraud — pay it once for real and once to somebody's cousin — and it silently
    # doubles stock, which makes every food-cost figure built on it wrong by more than the money.
    # Partial, because `invoice_number` is legitimately null: the market purchase this module
    # exists to accommodate arrives with no paperwork at all.
    op.create_index(
        "uq_goods_receipt_invoice",
        "goods_receipt",
        ["restaurant_id", "supplier_id", "invoice_number"],
        unique=True,
        postgresql_where=sa.text("invoice_number IS NOT NULL"),
    )
    _append_only("goods_receipt")

    # ---------------------------------------------------------------- goods_receipt_line
    op.create_table(
        "goods_receipt_line",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goods_receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stock_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The three numbers, and never one. `invoiced` is what the bill says; `received` is what the
        # scale says; `rejected` is what arrived and was refused on quality. Collapse any two of
        # them and `docs/waste-model.md` §1's report becomes unanswerable for ever.
        sa.Column("quantity_invoiced", sa.Numeric(14, 4), nullable=False),
        sa.Column("quantity_received", sa.Numeric(14, 4), nullable=False),
        sa.Column("quantity_rejected", sa.Numeric(14, 4), nullable=False, server_default="0"),
        # Excluding tax, per base unit — directly comparable to the order line's quoted price. The
        # landed cost that reaches `stock_batch.unit_cost` adds apportioned tax in the service.
        sa.Column("unit_price", sa.Numeric(14, 6), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["goods_receipt_id", "restaurant_id"],
            ["goods_receipt.id", "goods_receipt.restaurant_id"],
            name="fk_gr_line_receipt_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["stock_item_id", "restaurant_id"],
            ["stock_item.id", "stock_item.restaurant_id"],
            name="fk_gr_line_item_tenant",
        ),
        sa.UniqueConstraint("goods_receipt_id", "stock_item_id", name="uq_gr_line_receipt_item"),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_gr_line_id_restaurant"),
        # Zero is allowed for all three: "they billed 50 kg and delivered nothing for this line" is
        # a real and important row. What is not allowed is refusing more than arrived.
        sa.CheckConstraint("quantity_invoiced >= 0", name="ck_gr_line_invoiced"),
        sa.CheckConstraint("quantity_received >= 0", name="ck_gr_line_received"),
        sa.CheckConstraint("quantity_rejected >= 0", name="ck_gr_line_rejected"),
        sa.CheckConstraint(
            "quantity_rejected <= quantity_received", name="ck_gr_line_rejected_within_received"
        ),
        sa.CheckConstraint(
            "quantity_rejected = 0 OR rejection_reason IS NOT NULL",
            name="ck_gr_line_rejection_reason",
        ),
        sa.CheckConstraint("unit_price >= 0", name="ck_gr_line_unit_price"),
    )
    op.create_index("ix_gr_line_receipt", "goods_receipt_line", ["goods_receipt_id"])
    op.create_index(
        "ix_gr_line_item_date", "goods_receipt_line", ["restaurant_id", "stock_item_id"]
    )
    _append_only("goods_receipt_line")

    # ------------------------------------------------- the two FKs 0015 could not create
    # Both columns have existed since 0015 as bare uuids because they pointed at the tables above.
    # `docs/schema.md` §5 asks for the constraints here. Asserted rather than assumed: if anything
    # has written either column, the constraint below would fail on a value with no parent, and a
    # migration that fails loudly beats one that silently validates nothing.
    orphans = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM stock_batch "
                " WHERE supplier_id IS NOT NULL OR goods_receipt_line_id IS NOT NULL"
            )
        )
        .scalar_one()
    )
    if orphans:  # pragma: no cover - no code path writes these columns before this migration
        raise RuntimeError(
            f"{orphans} stock_batch rows already carry supplier_id or goods_receipt_line_id, "
            "which nothing before 0017 was supposed to write. Reconcile them before adding the "
            "foreign keys, or they will point at nothing."
        )
    op.create_foreign_key(
        "fk_stock_batch_supplier_tenant",
        "stock_batch",
        "supplier",
        ["supplier_id", "restaurant_id"],
        ["id", "restaurant_id"],
    )
    op.create_foreign_key(
        "fk_stock_batch_gr_line_tenant",
        "stock_batch",
        "goods_receipt_line",
        ["goods_receipt_line_id", "restaurant_id"],
        ["id", "restaurant_id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_stock_batch_gr_line_tenant", "stock_batch", type_="foreignkey")
    op.drop_constraint("fk_stock_batch_supplier_tenant", "stock_batch", type_="foreignkey")

    op.execute("DROP TRIGGER IF EXISTS trg_goods_receipt_line_append_only ON goods_receipt_line;")
    op.execute("DROP FUNCTION IF EXISTS goods_receipt_line_append_only();")
    for name in ("ix_gr_line_item_date", "ix_gr_line_receipt"):
        op.drop_index(name, table_name="goods_receipt_line")
    op.drop_table("goods_receipt_line")

    op.execute("DROP TRIGGER IF EXISTS trg_goods_receipt_append_only ON goods_receipt;")
    op.execute("DROP FUNCTION IF EXISTS goods_receipt_append_only();")
    for name in (
        "uq_goods_receipt_invoice",
        "ix_goods_receipt_order",
        "ix_goods_receipt_supplier",
        "ix_goods_receipt_restaurant_date",
    ):
        op.drop_index(name, table_name="goods_receipt")
    op.drop_table("goods_receipt")

    op.drop_index("ix_po_line_order", table_name="purchase_order_line")
    op.drop_table("purchase_order_line")
    op.drop_index("ix_purchase_order_restaurant_status", table_name="purchase_order")
    op.drop_table("purchase_order")
    op.drop_index("ix_supplier_restaurant_active", table_name="supplier")
    op.drop_table("supplier")
