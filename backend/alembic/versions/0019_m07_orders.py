"""m07 - orders, invoices, payments, credit notes and the till

Fourteen tables, two new columns, three parent constraints and the triggers that make settled money
immutable. Argued in `docs/modules/M07-orders-spec.md`.

**The three parent constraints come first.** Every order table references its parents on
`(id, restaurant_id)`, so attaching an order line to another restaurant's dish is refused by Postgres
rather than by a repository remembering to filter — the same arrangement M05 and M06 use. That needs a
`UNIQUE (id, restaurant_id)` on each parent, and `menu_item_variant`, `modifier` and `restaurant_table`
never had one. Adding it is safe on any existing data by construction: `id` is already the primary
key, so the pair is already unique.

**`order` is a reserved word.** SQLAlchemy quotes it in the DDL it generates; every hand-written
statement below writes `"order"`.

**Settled money does not move, and the database says so.** An open order is edited constantly, so
`order` cannot take the blanket append-only trigger `stock_movement` uses. Its trigger refuses DELETE
always (ADR 0008) and any change to a cancelled or voided order. A settled order may be voided, and
otherwise only its kitchen timestamps may move, because a counter-service restaurant takes the money
before it cooks. The comparison is every column *except* the allowed ones, so a money column a later
migration adds is frozen without anybody remembering to list it.

Lines, discounts, charges, tables and modifiers follow their order on INSERT as well as UPDATE and
DELETE: adding a line to a paid bill is the edit that matters most. A settled line may still move
through the kitchen. A line may be deleted only while unsent; after that it is cancelled with a
reason, because deleting a sent line is how a served dish disappears from a bill. Payments, credit
notes, their lines, cash counts and cash movements are append-only outright. An invoice may only be
cancelled or registered for e-invoicing, never deleted: its number must survive (GSTR-1 Table 13). A
closed cash session is frozen.

The suite is unaffected: `conftest.py` rolls back an outer transaction rather than issuing DELETEs,
and row triggers do not fire on TRUNCATE.

Revision ID: 0019_m07_orders
Revises: 0018_m06_procurement_permissions
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_m07_orders"
down_revision: str | None = "0018_m06_procurement_permissions"
branch_labels: str | None = None
depends_on: str | None = None


def _uuid() -> postgresql.UUID[uuid.UUID]:
    return postgresql.UUID(as_uuid=True)


def _timestamps() -> tuple[sa.Column[Any], sa.Column[Any]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def _money(name: str, *, nullable: bool = False, default: bool = False) -> sa.Column[Any]:
    return sa.Column(
        name,
        sa.Numeric(12, 2),
        nullable=nullable,
        server_default="0" if default else None,
    )


def _tenant_fk(
    columns: list[str], parent: str, name: str, *, ondelete: str | None = None
) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [*columns, "restaurant_id"],
        [f"{parent}.id", f"{parent}.restaurant_id"],
        name=name,
        ondelete=ondelete,
    )


def _in(column: str, *values: str) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


_APPEND_ONLY = {
    "payment": "A refund is a new negative payment referencing a credit note.",
    "credit_note": "A further reduction is another credit note.",
    "credit_note_line": "A further reduction is another credit note.",
    "cash_count": "Record a cash adjustment against the session instead.",
    "cash_movement": "Record another cash adjustment instead.",
}

# The tables whose rows follow their order's status and nothing more. `order_line` has its own
# trigger because a settled line may still move through the kitchen; `order_line_modifier` has
# its own because its order is two hops away.
_ORDER_CHILDREN = ("order_discount", "order_charge", "order_table")


def upgrade() -> None:
    # ------------------------------------------------------------ parents gain (id, restaurant_id)
    for table in ("menu_item_variant", "modifier", "restaurant_table"):
        op.create_unique_constraint(f"uq_{table}_id_restaurant", table, ["id", "restaurant_id"])

    # ------------------------------------------------------------ columns on existing tables
    op.add_column(
        "restaurant",
        sa.Column("gst_scheme", sa.Text(), nullable=False, server_default="regular"),
    )
    op.create_check_constraint(
        "ck_restaurant_gst_scheme",
        "restaurant",
        _in("gst_scheme", "regular", "composition", "unregistered"),
    )
    # NULL means service charge is disabled, which is the default (spec decision 7).
    op.add_column("restaurant", sa.Column("service_charge_rate", sa.Numeric(6, 4), nullable=True))
    op.create_check_constraint(
        "ck_restaurant_service_charge_rate",
        "restaurant",
        "service_charge_rate IS NULL OR (service_charge_rate > 0 AND service_charge_rate <= 1)",
    )
    op.add_column("tax_group", sa.Column("regime", sa.Text(), nullable=False, server_default="gst"))
    op.create_check_constraint("ck_tax_group_regime", "tax_group", _in("regime", "gst", "non_gst"))

    # ------------------------------------------------------------ cash_session
    op.create_table(
        "cash_session",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), sa.ForeignKey("restaurant.id"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_by", _uuid(), sa.ForeignKey("employee.id"), nullable=False),
        _money("opening_float"),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", _uuid(), sa.ForeignKey("employee.id"), nullable=True),
        _money("counted_cash", nullable=True),
        _money("variance", nullable=True),
        sa.Column("shift_id", _uuid(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_cash_session_id_restaurant"),
        sa.CheckConstraint(_in("status", "open", "closed"), name="ck_cash_session_status"),
        sa.CheckConstraint("opening_float >= 0", name="ck_cash_session_float"),
        sa.CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL AND closed_by IS NOT NULL "
            "AND counted_cash IS NOT NULL AND variance IS NOT NULL)",
            name="ck_cash_session_closed_complete",
        ),
    )
    op.create_index(
        "uq_cash_session_one_open",
        "cash_session",
        ["restaurant_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "ix_cash_session_restaurant_date", "cash_session", ["restaurant_id", "business_date"]
    )

    # ------------------------------------------------------------ order
    op.create_table(
        "order",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), sa.ForeignKey("restaurant.id"), nullable=False),
        sa.Column("order_number", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("external_order_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("customer_id", _uuid(), nullable=True),
        sa.Column("waiter_employee_id", _uuid(), sa.ForeignKey("employee.id"), nullable=True),
        sa.Column("covers", sa.SmallInteger(), nullable=True),
        sa.Column("parent_order_id", _uuid(), nullable=True),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("served_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bill_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        _money("subtotal", default=True),
        _money("discount_total", default=True),
        _money("charge_total", default=True),
        _money("tax_total", default=True),
        _money("round_off", default=True),
        _money("grand_total", default=True),
        _money("theoretical_food_cost", nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("voided_by", _uuid(), sa.ForeignKey("employee.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *_timestamps(),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_order_id_restaurant"),
        sa.UniqueConstraint(
            "restaurant_id", "business_date", "order_number", name="uq_order_number_per_day"
        ),
        _tenant_fk(["parent_order_id"], "order", "fk_order_parent_tenant"),
        sa.CheckConstraint(_in("type", "dine_in", "takeaway", "delivery"), name="ck_order_type"),
        sa.CheckConstraint(_in("channel", "pos", "qr", "aggregator"), name="ck_order_channel"),
        sa.CheckConstraint(
            _in("status", "open", "sent", "served", "settled", "cancelled", "voided"),
            name="ck_order_status",
        ),
        sa.CheckConstraint("covers IS NULL OR covers > 0", name="ck_order_covers"),
        sa.CheckConstraint(
            "subtotal >= 0 AND discount_total >= 0 AND charge_total >= 0 AND tax_total >= 0 "
            "AND grand_total >= 0",
            name="ck_order_money_not_negative",
        ),
        sa.CheckConstraint("discount_total <= subtotal", name="ck_order_discount_within_subtotal"),
        sa.CheckConstraint("round_off BETWEEN -0.50 AND 0.50", name="ck_order_round_off"),
        sa.CheckConstraint(
            "status NOT IN ('cancelled', 'voided') OR cancel_reason IS NOT NULL",
            name="ck_order_final_has_reason",
        ),
    )
    op.create_index("ix_order_restaurant_date", "order", ["restaurant_id", "business_date"])
    op.create_index(
        "ix_order_live",
        "order",
        ["restaurant_id", "status"],
        postgresql_where=sa.text("status IN ('open', 'sent', 'served')"),
    )
    op.create_index("ix_order_customer", "order", ["restaurant_id", "customer_id"])
    op.create_index(
        "ix_order_waiter_date", "order", ["restaurant_id", "waiter_employee_id", "business_date"]
    )

    # ------------------------------------------------------------ order_table
    op.create_table(
        "order_table",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("order_id", _uuid(), nullable=False),
        sa.Column("restaurant_table_id", _uuid(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        _tenant_fk(["order_id"], "order", "fk_order_table_order_tenant"),
        _tenant_fk(["restaurant_table_id"], "restaurant_table", "fk_order_table_table_tenant"),
        sa.UniqueConstraint("order_id", "restaurant_table_id", name="uq_order_table_pair"),
    )
    op.create_index(
        "uq_order_table_one_primary",
        "order_table",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )
    op.create_index("ix_order_table_table", "order_table", ["restaurant_id", "restaurant_table_id"])

    # ------------------------------------------------------------ order_line
    op.create_table(
        "order_line",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("order_id", _uuid(), nullable=False),
        sa.Column("menu_item_variant_id", _uuid(), nullable=False),
        sa.Column("recipe_id", _uuid(), nullable=True),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        _money("unit_price"),
        _money("line_subtotal"),
        _money("line_discount", default=True),
        sa.Column("tax_group_id", _uuid(), nullable=False),
        sa.Column("tax_regime", sa.Text(), nullable=False, server_default="gst"),
        sa.Column("tax_rate", sa.Numeric(6, 4), nullable=False),
        _money("taxable_value"),
        _money("cgst_amount", default=True),
        _money("sgst_amount", default=True),
        _money("tax_amount", default=True),
        _money("line_total"),
        sa.Column("theoretical_unit_cost", sa.Numeric(14, 6), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("special_instructions", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("seq", sa.SmallInteger(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_order_line_id_restaurant"),
        _tenant_fk(["order_id"], "order", "fk_order_line_order_tenant"),
        _tenant_fk(["menu_item_variant_id"], "menu_item_variant", "fk_order_line_variant_tenant"),
        _tenant_fk(["recipe_id"], "recipe", "fk_order_line_recipe_tenant"),
        _tenant_fk(["tax_group_id"], "tax_group", "fk_order_line_tax_group_tenant"),
        sa.CheckConstraint("quantity > 0", name="ck_order_line_quantity"),
        sa.CheckConstraint(
            _in(
                "status", "pending", "sent", "preparing", "ready", "served", "cancelled", "returned"
            ),
            name="ck_order_line_status",
        ),
        sa.CheckConstraint(_in("tax_regime", "gst", "non_gst"), name="ck_order_line_regime"),
        sa.CheckConstraint(
            "unit_price >= 0 AND line_subtotal >= 0 AND line_discount >= 0 AND taxable_value >= 0 "
            "AND cgst_amount >= 0 AND sgst_amount >= 0 AND tax_amount >= 0 AND line_total >= 0",
            name="ck_order_line_money_not_negative",
        ),
        sa.CheckConstraint("line_discount <= line_subtotal", name="ck_order_line_discount_within"),
        sa.CheckConstraint("tax_rate >= 0 AND tax_rate <= 1", name="ck_order_line_rate_fraction"),
        sa.CheckConstraint("line_total = taxable_value + tax_amount", name="ck_order_line_total"),
        sa.CheckConstraint(
            "(tax_regime = 'gst' AND cgst_amount = sgst_amount "
            "AND tax_amount = cgst_amount + sgst_amount) "
            "OR (tax_regime = 'non_gst' AND cgst_amount = 0 AND sgst_amount = 0)",
            name="ck_order_line_gst_split",
        ),
        sa.CheckConstraint(
            "status <> 'cancelled' OR cancel_reason IS NOT NULL",
            name="ck_order_line_cancel_reason",
        ),
    )
    op.create_index("ix_order_line_order", "order_line", ["order_id"])
    op.create_index(
        "ix_order_line_variant", "order_line", ["restaurant_id", "menu_item_variant_id"]
    )

    # ------------------------------------------------------------ order_line_modifier
    op.create_table(
        "order_line_modifier",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("order_line_id", _uuid(), nullable=False),
        sa.Column("modifier_id", _uuid(), nullable=False),
        _money("price_delta"),
        sa.Column("recipe_id", _uuid(), nullable=True),
        *_timestamps(),
        _tenant_fk(
            ["order_line_id"],
            "order_line",
            "fk_order_line_modifier_line_tenant",
            ondelete="CASCADE",
        ),
        _tenant_fk(["modifier_id"], "modifier", "fk_order_line_modifier_modifier_tenant"),
        _tenant_fk(["recipe_id"], "recipe", "fk_order_line_modifier_recipe_tenant"),
        sa.UniqueConstraint("order_line_id", "modifier_id", name="uq_order_line_modifier_pair"),
    )
    op.create_index("ix_order_line_modifier_line", "order_line_modifier", ["order_line_id"])

    # ------------------------------------------------------------ order_discount
    op.create_table(
        "order_discount",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("order_id", _uuid(), nullable=False),
        sa.Column("order_line_id", _uuid(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("rate", sa.Numeric(6, 4), nullable=True),
        _money("flat_amount", nullable=True),
        _money("amount"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("authorised_by", _uuid(), sa.ForeignKey("employee.id"), nullable=False),
        *_timestamps(),
        _tenant_fk(["order_id"], "order", "fk_order_discount_order_tenant"),
        _tenant_fk(["order_line_id"], "order_line", "fk_order_discount_line_tenant"),
        sa.CheckConstraint(
            _in("type", "percentage", "flat", "comp"), name="ck_order_discount_type"
        ),
        sa.CheckConstraint(
            "(type = 'flat') = (flat_amount IS NOT NULL) AND (type <> 'flat') = (rate IS NOT NULL)",
            name="ck_order_discount_shape",
        ),
        sa.CheckConstraint(
            "rate IS NULL OR (rate > 0 AND rate <= 1)", name="ck_order_discount_rate"
        ),
        sa.CheckConstraint("flat_amount IS NULL OR flat_amount > 0", name="ck_order_discount_flat"),
        sa.CheckConstraint("amount >= 0", name="ck_order_discount_amount"),
    )
    op.create_index("ix_order_discount_order", "order_discount", ["order_id"])
    op.create_index(
        "ix_order_discount_authoriser", "order_discount", ["restaurant_id", "authorised_by"]
    )

    # ------------------------------------------------------------ order_charge
    op.create_table(
        "order_charge",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("order_id", _uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        _money("amount"),
        sa.Column("tax_group_id", _uuid(), nullable=True),
        sa.Column("tax_rate", sa.Numeric(6, 4), nullable=True),
        _money("cgst_amount", default=True),
        _money("sgst_amount", default=True),
        _money("tax_amount", default=True),
        sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        _tenant_fk(["order_id"], "order", "fk_order_charge_order_tenant"),
        _tenant_fk(["tax_group_id"], "tax_group", "fk_order_charge_tax_group_tenant"),
        sa.CheckConstraint(
            _in("type", "packaging", "service_charge", "delivery"), name="ck_order_charge_type"
        ),
        sa.CheckConstraint(
            "type <> 'service_charge' OR is_optional", name="ck_order_charge_service_optional"
        ),
        sa.CheckConstraint(
            "amount >= 0 AND cgst_amount >= 0 AND sgst_amount >= 0 AND tax_amount >= 0",
            name="ck_order_charge_money_not_negative",
        ),
        sa.CheckConstraint(
            "cgst_amount = sgst_amount AND tax_amount = cgst_amount + sgst_amount",
            name="ck_order_charge_gst_split",
        ),
        sa.CheckConstraint(
            "tax_group_id IS NOT NULL OR tax_amount = 0", name="ck_order_charge_untaxed"
        ),
    )
    op.create_index("ix_order_charge_order", "order_charge", ["order_id"])

    # ------------------------------------------------------------ invoice
    op.create_table(
        "invoice",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("order_id", _uuid(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("financial_year", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("invoice_number", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("supplier_name", sa.Text(), nullable=False),
        sa.Column("supplier_address", postgresql.JSONB(), nullable=True),
        sa.Column("supplier_gstin", sa.Text(), nullable=True),
        sa.Column("fssai_licence", sa.Text(), nullable=True),
        sa.Column("recipient_name", sa.Text(), nullable=True),
        sa.Column("recipient_gstin", sa.Text(), nullable=True),
        sa.Column("recipient_address", sa.Text(), nullable=True),
        sa.Column("sac_code", sa.Text(), nullable=False, server_default="996331"),
        _money("taxable_total"),
        _money("cgst_total", default=True),
        _money("sgst_total", default=True),
        _money("non_gst_tax_total", default=True),
        _money("discount_total", default=True),
        _money("charge_total", default=True),
        _money("round_off", default=True),
        _money("grand_total"),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_by", _uuid(), sa.ForeignKey("employee.id"), nullable=True),
        sa.Column("irn", sa.Text(), nullable=True),
        sa.Column("irn_ack_no", sa.Text(), nullable=True),
        sa.Column("irn_ack_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_invoice_id_restaurant"),
        sa.UniqueConstraint("order_id", name="uq_invoice_one_per_order"),
        sa.UniqueConstraint(
            "restaurant_id", "financial_year", "sequence", name="uq_invoice_sequence_per_fy"
        ),
        sa.UniqueConstraint("restaurant_id", "invoice_number", name="uq_invoice_number"),
        _tenant_fk(["order_id"], "order", "fk_invoice_order_tenant"),
        sa.CheckConstraint(
            _in("document_type", "tax_invoice", "bill_of_supply"), name="ck_invoice_document_type"
        ),
        sa.CheckConstraint(_in("status", "issued", "cancelled"), name="ck_invoice_status"),
        sa.CheckConstraint("char_length(invoice_number) <= 16", name="ck_invoice_number_length"),
        sa.CheckConstraint("financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="ck_invoice_fy_format"),
        sa.CheckConstraint("sequence > 0", name="ck_invoice_sequence"),
        sa.CheckConstraint(
            "document_type <> 'bill_of_supply' OR (cgst_total = 0 AND sgst_total = 0)",
            name="ck_invoice_bill_of_supply_untaxed",
        ),
        sa.CheckConstraint(
            "document_type <> 'tax_invoice' OR supplier_gstin IS NOT NULL",
            name="ck_invoice_tax_invoice_has_gstin",
        ),
        sa.CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL AND cancel_reason IS NOT NULL)",
            name="ck_invoice_cancel_complete",
        ),
        sa.CheckConstraint(
            "taxable_total >= 0 AND cgst_total >= 0 AND sgst_total >= 0 AND non_gst_tax_total >= 0 "
            "AND discount_total >= 0 AND charge_total >= 0 AND grand_total >= 0",
            name="ck_invoice_money_not_negative",
        ),
        sa.CheckConstraint("round_off BETWEEN -0.50 AND 0.50", name="ck_invoice_round_off"),
    )
    op.create_index("ix_invoice_restaurant_date", "invoice", ["restaurant_id", "invoice_date"])

    # ------------------------------------------------------------ credit_note
    op.create_table(
        "credit_note",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("invoice_id", _uuid(), nullable=False),
        sa.Column("financial_year", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("credit_note_number", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note_date", sa.Date(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("issued_by", _uuid(), sa.ForeignKey("employee.id"), nullable=False),
        _money("taxable_total"),
        _money("cgst_total", default=True),
        _money("sgst_total", default=True),
        _money("non_gst_tax_total", default=True),
        _money("grand_total"),
        *_timestamps(),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_credit_note_id_restaurant"),
        sa.UniqueConstraint(
            "restaurant_id", "financial_year", "sequence", name="uq_credit_note_sequence_per_fy"
        ),
        sa.UniqueConstraint("restaurant_id", "credit_note_number", name="uq_credit_note_number"),
        _tenant_fk(["invoice_id"], "invoice", "fk_credit_note_invoice_tenant"),
        sa.CheckConstraint(
            "char_length(credit_note_number) <= 16", name="ck_credit_note_number_length"
        ),
        sa.CheckConstraint(
            "financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="ck_credit_note_fy_format"
        ),
        sa.CheckConstraint("sequence > 0", name="ck_credit_note_sequence"),
        sa.CheckConstraint(
            "taxable_total >= 0 AND cgst_total >= 0 AND sgst_total >= 0 AND non_gst_tax_total >= 0 "
            "AND grand_total > 0",
            name="ck_credit_note_money",
        ),
    )
    op.create_index("ix_credit_note_invoice", "credit_note", ["invoice_id"])

    # ------------------------------------------------------------ credit_note_line
    op.create_table(
        "credit_note_line",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("credit_note_id", _uuid(), nullable=False),
        sa.Column("order_line_id", _uuid(), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        _money("taxable_value"),
        _money("cgst_amount", default=True),
        _money("sgst_amount", default=True),
        _money("tax_amount", default=True),
        _money("line_total"),
        *_timestamps(),
        _tenant_fk(["credit_note_id"], "credit_note", "fk_credit_note_line_note_tenant"),
        _tenant_fk(["order_line_id"], "order_line", "fk_credit_note_line_order_line_tenant"),
        sa.UniqueConstraint("credit_note_id", "order_line_id", name="uq_credit_note_line_pair"),
        sa.CheckConstraint("quantity > 0", name="ck_credit_note_line_quantity"),
        sa.CheckConstraint(
            "taxable_value >= 0 AND cgst_amount >= 0 AND sgst_amount >= 0 AND tax_amount >= 0 "
            "AND line_total >= 0",
            name="ck_credit_note_line_money",
        ),
        sa.CheckConstraint(
            "line_total = taxable_value + tax_amount", name="ck_credit_note_line_total"
        ),
    )
    op.create_index("ix_credit_note_line_note", "credit_note_line", ["credit_note_id"])

    # ------------------------------------------------------------ payment
    op.create_table(
        "payment",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("order_id", _uuid(), nullable=False),
        sa.Column("invoice_id", _uuid(), nullable=True),
        sa.Column("credit_note_id", _uuid(), nullable=True),
        sa.Column("cash_session_id", _uuid(), nullable=True),
        sa.Column("method", sa.Text(), nullable=False),
        _money("amount"),
        _money("tip_amount", default=True),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("received_by", _uuid(), sa.ForeignKey("employee.id"), nullable=True),
        *_timestamps(),
        _tenant_fk(["order_id"], "order", "fk_payment_order_tenant"),
        _tenant_fk(["invoice_id"], "invoice", "fk_payment_invoice_tenant"),
        _tenant_fk(["credit_note_id"], "credit_note", "fk_payment_credit_note_tenant"),
        _tenant_fk(["cash_session_id"], "cash_session", "fk_payment_cash_session_tenant"),
        sa.CheckConstraint(
            _in("method", "cash", "card", "upi", "wallet", "online", "due"),
            name="ck_payment_method",
        ),
        sa.CheckConstraint(_in("status", "success", "failed"), name="ck_payment_status"),
        sa.CheckConstraint("amount <> 0", name="ck_payment_amount_not_zero"),
        sa.CheckConstraint("tip_amount >= 0", name="ck_payment_tip"),
        sa.CheckConstraint(
            "amount > 0 OR credit_note_id IS NOT NULL", name="ck_payment_refund_has_credit_note"
        ),
    )
    op.create_index("ix_payment_restaurant_date", "payment", ["restaurant_id", "business_date"])
    op.create_index("ix_payment_order", "payment", ["order_id"])
    op.create_index("ix_payment_cash_session", "payment", ["restaurant_id", "cash_session_id"])

    # ------------------------------------------------------------ cash_count
    op.create_table(
        "cash_count",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("cash_session_id", _uuid(), nullable=False),
        _money("denomination"),
        sa.Column("quantity", sa.Integer(), nullable=False),
        *_timestamps(),
        _tenant_fk(["cash_session_id"], "cash_session", "fk_cash_count_session_tenant"),
        sa.UniqueConstraint("cash_session_id", "denomination", name="uq_cash_count_denomination"),
        sa.CheckConstraint("denomination > 0", name="ck_cash_count_denomination"),
        sa.CheckConstraint("quantity >= 0", name="ck_cash_count_quantity"),
    )

    # ------------------------------------------------------------ cash_movement
    op.create_table(
        "cash_movement",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("cash_session_id", _uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        _money("amount"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("recorded_by", _uuid(), sa.ForeignKey("employee.id"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        *_timestamps(),
        _tenant_fk(["cash_session_id"], "cash_session", "fk_cash_movement_session_tenant"),
        sa.CheckConstraint(_in("type", "payout", "adjustment"), name="ck_cash_movement_type"),
        sa.CheckConstraint("amount <> 0", name="ck_cash_movement_amount_not_zero"),
        sa.CheckConstraint(
            "type <> 'payout' OR amount > 0", name="ck_cash_movement_payout_positive"
        ),
    )
    op.create_index(
        "ix_cash_movement_session", "cash_movement", ["restaurant_id", "cash_session_id"]
    )

    # ------------------------------------------------------------ idempotency_key
    op.create_table(
        "idempotency_key",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("restaurant_id", _uuid(), sa.ForeignKey("restaurant.id"), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_employee_id", _uuid(), sa.ForeignKey("employee.id"), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("restaurant_id", "key", name="uq_idempotency_key_per_restaurant"),
        sa.CheckConstraint(
            _in("state", "in_progress", "completed", "failed"), name="ck_idempotency_key_state"
        ),
        sa.CheckConstraint("char_length(key) BETWEEN 16 AND 128", name="ck_idempotency_key_length"),
    )
    op.create_index("ix_idempotency_key_expires", "idempotency_key", ["expires_at"])

    _install_triggers()


# Columns that may still change once an order is settled. The comparison is "every column except
# these", never a list of protected ones, so a money column a later migration adds is frozen by
# default rather than by somebody remembering.
_SETTLED_ORDER_MUTABLE = (
    "status",
    "cancel_reason",
    "cancelled_at",
    "voided_by",
    # A counter-service restaurant takes the money before it cooks, so service happens afterwards.
    "first_sent_at",
    "served_at",
    "version",
    "updated_at",
)
# A settled line may still move through the kitchen, for the same reason. Nothing else about it may.
_SETTLED_LINE_MUTABLE = ("status", "sent_at", "updated_at")
_KITCHEN_PROGRESS = "('pending', 'sent', 'preparing', 'ready', 'served')"
# An issued invoice may be cancelled, and registered for e-invoicing later. Nothing else.
_INVOICE_MUTABLE = (
    "status",
    "cancelled_at",
    "cancel_reason",
    "cancelled_by",
    "irn",
    "irn_ack_no",
    "irn_ack_at",
    "updated_at",
)
_FINAL = "('settled', 'cancelled', 'voided')"


def _changed_beyond(allowed: tuple[str, ...]) -> str:
    """A SQL condition, true when any column outside `allowed` differs between OLD and NEW."""
    keep = "ARRAY[" + ", ".join(f"'{name}'" for name in allowed) + "]::text[]"
    return f"(to_jsonb(NEW) - {keep}) IS DISTINCT FROM (to_jsonb(OLD) - {keep})"


def _install_triggers() -> None:
    order_changed = _changed_beyond(_SETTLED_ORDER_MUTABLE)
    line_changed = _changed_beyond(_SETTLED_LINE_MUTABLE)
    invoice_changed = _changed_beyond(_INVOICE_MUTABLE)

    # ---- order: a live order is edited constantly; a settled one may only be voided
    op.execute(
        f"""
        CREATE FUNCTION order_immutable_when_final() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'An order is never deleted (ADR 0008). Cancel or void it.';
            END IF;
            IF OLD.status IN ('cancelled', 'voided') THEN
                RAISE EXCEPTION 'Order % is % and cannot change.', OLD.id, OLD.status;
            END IF;
            IF OLD.status = 'settled' THEN
                IF NEW.status NOT IN ('settled', 'voided') OR {order_changed} THEN
                    RAISE EXCEPTION
                        'A settled order is immutable (invariant 6). Void it or credit-note it.';
                END IF;
                IF NEW.status = 'settled' AND (
                    NEW.cancel_reason IS DISTINCT FROM OLD.cancel_reason
                    OR NEW.cancelled_at IS DISTINCT FROM OLD.cancelled_at
                    OR NEW.voided_by IS DISTINCT FROM OLD.voided_by
                ) THEN
                    RAISE EXCEPTION 'A void reason is recorded only by voiding the order.';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_order_immutable_when_final
        BEFORE UPDATE OR DELETE ON "order"
        FOR EACH ROW EXECUTE FUNCTION order_immutable_when_final();
        """
    )

    # ---- order_line: follows its order, may progress through the kitchen, deleted only unsent
    op.execute(
        f"""
        CREATE FUNCTION order_line_follows_order() RETURNS trigger AS $$
        DECLARE
            parent_status text;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                SELECT status INTO parent_status FROM "order" WHERE id = OLD.order_id;
                IF parent_status IN ('cancelled', 'voided') THEN
                    RAISE EXCEPTION 'A line on a % order cannot change.', parent_status;
                END IF;
                IF TG_OP = 'DELETE' THEN
                    IF OLD.status <> 'pending' OR parent_status = 'settled' THEN
                        RAISE EXCEPTION
                            'Only an unsent line on a live order can be removed. Cancel it.';
                    END IF;
                    RETURN OLD;
                END IF;
                IF parent_status = 'settled'
                    AND (NEW.status NOT IN {_KITCHEN_PROGRESS} OR {line_changed})
                THEN
                    RAISE EXCEPTION
                        'A settled line may only move through the kitchen (invariant 6).';
                END IF;
                IF NEW.order_id IS NOT DISTINCT FROM OLD.order_id THEN
                    RETURN NEW;
                END IF;
            END IF;
            SELECT status INTO parent_status FROM "order" WHERE id = NEW.order_id;
            IF parent_status IN {_FINAL} THEN
                RAISE EXCEPTION 'Cannot add a line to a % order (invariant 6).', parent_status;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """  # noqa: S608 - only module constants are interpolated, never input
    )
    op.execute(
        """
        CREATE TRIGGER trg_order_line_follows_order
        BEFORE INSERT OR UPDATE OR DELETE ON order_line
        FOR EACH ROW EXECUTE FUNCTION order_line_follows_order();
        """
    )

    # ---- discounts, charges, tables: follow their order, on insert as well
    op.execute(
        f"""
        CREATE FUNCTION order_child_follows_order() RETURNS trigger AS $$
        DECLARE
            parent_status text;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                SELECT status INTO parent_status FROM "order" WHERE id = OLD.order_id;
                IF parent_status IN {_FINAL} THEN
                    RAISE EXCEPTION '% on a % order cannot change.', TG_TABLE_NAME, parent_status;
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
            END IF;
            SELECT status INTO parent_status FROM "order" WHERE id = NEW.order_id;
            IF parent_status IN {_FINAL} THEN
                RAISE EXCEPTION 'Cannot add % to a % order.', TG_TABLE_NAME, parent_status;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """  # noqa: S608 - only module constants are interpolated, never input
    )
    for table in _ORDER_CHILDREN:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_follows_order
            BEFORE INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION order_child_follows_order();
            """
        )

    # ---- order_line_modifier: its order is two hops away
    op.execute(
        f"""
        CREATE FUNCTION order_line_modifier_follows_order() RETURNS trigger AS $$
        DECLARE
            parent_status text;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                SELECT o.status INTO parent_status
                  FROM order_line l JOIN "order" o ON o.id = l.order_id
                 WHERE l.id = OLD.order_line_id;
                IF parent_status IN {_FINAL} THEN
                    RAISE EXCEPTION 'A modifier on a % order cannot change.', parent_status;
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
            END IF;
            SELECT o.status INTO parent_status
              FROM order_line l JOIN "order" o ON o.id = l.order_id
             WHERE l.id = NEW.order_line_id;
            IF parent_status IN {_FINAL} THEN
                RAISE EXCEPTION 'Cannot add a modifier to a % order.', parent_status;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """  # noqa: S608 - only module constants are interpolated, never input
    )
    op.execute(
        """
        CREATE TRIGGER trg_order_line_modifier_follows_order
        BEFORE INSERT OR UPDATE OR DELETE ON order_line_modifier
        FOR EACH ROW EXECUTE FUNCTION order_line_modifier_follows_order();
        """
    )

    # ---- invoice: cancel or register for e-invoicing, never edit, never delete
    op.execute(
        f"""
        CREATE FUNCTION invoice_cancel_only() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'An invoice is never deleted; its number must survive (Rule 46).';
            END IF;
            IF OLD.status = 'cancelled' THEN
                RAISE EXCEPTION 'Invoice % is cancelled and cannot change.', OLD.invoice_number;
            END IF;
            IF {invoice_changed} THEN
                RAISE EXCEPTION
                    'An issued invoice is immutable. Cancel it, or issue a credit note (s.34).';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_invoice_cancel_only
        BEFORE UPDATE OR DELETE ON invoice
        FOR EACH ROW EXECUTE FUNCTION invoice_cancel_only();
        """
    )

    # ---- cash_session: never deleted, frozen once closed
    op.execute(
        """
        CREATE FUNCTION cash_session_frozen_when_closed() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'A cash session is never deleted.';
            END IF;
            IF OLD.status = 'closed' THEN
                RAISE EXCEPTION 'Cash session % is closed. Record a cash adjustment instead.', OLD.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_cash_session_frozen_when_closed
        BEFORE UPDATE OR DELETE ON cash_session
        FOR EACH ROW EXECUTE FUNCTION cash_session_frozen_when_closed();
        """
    )

    # ---- append-only outright
    for table, remedy in _APPEND_ONLY.items():
        op.execute(
            f"""
            CREATE FUNCTION {table}_append_only() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION '{table} is append-only: % refused. {remedy}', TG_OP;
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


def downgrade() -> None:
    for table in _APPEND_ONLY:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table};")
        op.execute(f"DROP FUNCTION IF EXISTS {table}_append_only();")
    op.execute("DROP TRIGGER IF EXISTS trg_cash_session_frozen_when_closed ON cash_session;")
    op.execute("DROP FUNCTION IF EXISTS cash_session_frozen_when_closed();")
    op.execute("DROP TRIGGER IF EXISTS trg_invoice_cancel_only ON invoice;")
    op.execute("DROP FUNCTION IF EXISTS invoice_cancel_only();")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_order_line_modifier_follows_order ON order_line_modifier;"
    )
    op.execute("DROP FUNCTION IF EXISTS order_line_modifier_follows_order();")
    for table in _ORDER_CHILDREN:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_follows_order ON {table};")
    op.execute("DROP FUNCTION IF EXISTS order_child_follows_order();")
    op.execute("DROP TRIGGER IF EXISTS trg_order_line_follows_order ON order_line;")
    op.execute("DROP FUNCTION IF EXISTS order_line_follows_order();")
    op.execute('DROP TRIGGER IF EXISTS trg_order_immutable_when_final ON "order";')
    op.execute("DROP FUNCTION IF EXISTS order_immutable_when_final();")

    op.drop_index("ix_idempotency_key_expires", table_name="idempotency_key")
    op.drop_table("idempotency_key")
    op.drop_index("ix_cash_movement_session", table_name="cash_movement")
    op.drop_table("cash_movement")
    op.drop_table("cash_count")
    for name in ("ix_payment_cash_session", "ix_payment_order", "ix_payment_restaurant_date"):
        op.drop_index(name, table_name="payment")
    op.drop_table("payment")
    op.drop_index("ix_credit_note_line_note", table_name="credit_note_line")
    op.drop_table("credit_note_line")
    op.drop_index("ix_credit_note_invoice", table_name="credit_note")
    op.drop_table("credit_note")
    op.drop_index("ix_invoice_restaurant_date", table_name="invoice")
    op.drop_table("invoice")
    op.drop_index("ix_order_charge_order", table_name="order_charge")
    op.drop_table("order_charge")
    for name in ("ix_order_discount_authoriser", "ix_order_discount_order"):
        op.drop_index(name, table_name="order_discount")
    op.drop_table("order_discount")
    op.drop_index("ix_order_line_modifier_line", table_name="order_line_modifier")
    op.drop_table("order_line_modifier")
    for name in ("ix_order_line_variant", "ix_order_line_order"):
        op.drop_index(name, table_name="order_line")
    op.drop_table("order_line")
    for name in ("ix_order_table_table", "uq_order_table_one_primary"):
        op.drop_index(name, table_name="order_table")
    op.drop_table("order_table")
    for name in (
        "ix_order_waiter_date",
        "ix_order_customer",
        "ix_order_live",
        "ix_order_restaurant_date",
    ):
        op.drop_index(name, table_name="order")
    op.drop_table("order")
    for name in ("ix_cash_session_restaurant_date", "uq_cash_session_one_open"):
        op.drop_index(name, table_name="cash_session")
    op.drop_table("cash_session")

    op.drop_constraint("ck_tax_group_regime", "tax_group", type_="check")
    op.drop_column("tax_group", "regime")
    op.drop_constraint("ck_restaurant_service_charge_rate", "restaurant", type_="check")
    op.drop_column("restaurant", "service_charge_rate")
    op.drop_constraint("ck_restaurant_gst_scheme", "restaurant", type_="check")
    op.drop_column("restaurant", "gst_scheme")

    for table in ("restaurant_table", "modifier", "menu_item_variant"):
        op.drop_constraint(f"uq_{table}_id_restaurant", table, type_="unique")
