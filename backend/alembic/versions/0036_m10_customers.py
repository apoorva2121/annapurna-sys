"""m10 - customers, feedback and complaints: the tables the guest surface hangs off

Six tables from `docs/schema.md` §9, plus the two columns that make a QR mean something, plus the
foreign key M07 left behind.

Five things are deliberate.

**1. Two ids: the organization owns the record, the branch owns the view.** A chain recognises the
same diner across branches - a regular at Koregaon Park who visits Baner is the same person with the
same allergy - so the tenant column is `organization_id`, exactly as it is on `employee`, and the
composite tenant-safe key is `(id, organization_id)`. But scoping the row to the organization must
not silently scope the *view* to it as well: a manager reads the customers of the branches they are
**assigned to** (`employee_role_assignment`, M01's own mechanism), and `home_restaurant_id` is the
attribution that makes a customer with no orders yet still belong somewhere. Decided with the owner
on 2026-09-16; `docs/modules/M10-customers-spec.md` decision 5 carries the reasoning.

**2. `customer_consent` is not in `docs/schema.md`, and it has to exist.** `docs/compliance-rules.md`
§B2 sets the standard M10 builds to: *one consent row per purpose, never a single boolean*, with the
notice version and language retained and withdrawal as easy as granting. None of the five tables in
§9 can hold that. It is append-only - a row per grant and a row per withdrawal, current state being
the latest per purpose - because a consent history that can be rewritten proves nothing, and proof
is the entire mechanism. §9 is updated in the same PR.

**3. `order.customer_id` finally gets its foreign key.** M07 left it a bare column with a comment
saying so: "No foreign key: `customer` is M10's - the same arrangement M05 used for `supplier_id`."
This is M10.

**4. Two different QR codes, with two different lifetimes** (`docs/modules/M10-customers-spec.md`
decision 1). `restaurant_table.guest_slug` is a table's public, rotatable id and grants the menu.
`order.guest_token_hash` is a per-order capability that grants that order's own bill and one
feedback submission - stored **hashed**, like a refresh token, because `docs/security.md` treats a
photographed QR as public and a database dump must not yield live ones.

**5. One feedback per order, enforced by an index rather than by a screen.**
`docs/customer-experience.md`: "Never ask twice in one visit." A unique index on `order_id` is what
makes that true when the same guest taps twice on a slow network - the service returns the first row
rather than erroring, and the index is what guarantees there is only ever one to return.

Revision ID: 0036_m10_customers
Revises: 0035_m09_waste_issues
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_m10_customers"
down_revision: str | None = "0035_m09_waste_issues"
branch_labels: str | None = None
depends_on: str | None = None

# `docs/schema.md` §9. `allergy` is the one that reaches the kitchen; the rest are for the waiter.
_PREFERENCE_TYPES = ("dietary", "allergy", "spice_level", "seating", "other")

# `docs/compliance-rules.md` §B2's purpose limitation, made concrete: "a phone number collected for
# a bill is not marketing consent". Four purposes, each granted and withdrawn independently.
_CONSENT_PURPOSES = ("order_contact", "service_recognition", "feedback_followup", "marketing")

# How a piece of customer input reached us. Shared by `feedback.source` and
# `customer_consent.source`, because the four ways are the same four ways and a `staff` value means
# the same thing in both: an employee entered it on somebody's behalf, which is legitimate and must
# stay visible.
_SOURCES = ("qr", "app", "staff", "call")

_COMPLAINT_CATEGORIES = (
    "food_quality",
    "service",
    "delay",
    "billing",
    "hygiene",
    "staff_conduct",
    "other",
)
_COMPLAINT_SEVERITIES = ("low", "medium", "high", "critical")
_COMPLAINT_STATUSES = ("open", "investigating", "resolved", "closed")


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
    # ---------------------------------------------------------------- customer
    op.create_table(
        "customer",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organization.id"),
            nullable=False,
        ),
        # A diner who has signed in. Almost always null: ADR 0009 says guests are anonymous or
        # phone-verified, and neither makes a `user_account`.
        sa.Column(
            "user_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.id"),
            nullable=True,
        ),
        # The natural key, and the reason erasure writes a placeholder rather than a null: the
        # column is NOT NULL and the uniqueness is what stops one diner becoming four rows.
        # Where this person was first written down. **Branch attribution, decided with the owner on
        # 2026-09-16**: the organization owns the record so a chain recognises one diner across its
        # branches, and the branch owns the *view* so a manager reads their own book. Nullable,
        # because a customer can arrive from a guest QR at a table and be attributed by their order
        # rather than by a counter.
        sa.Column("home_restaurant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("first_visit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_visit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lifetime_value", sa.Numeric(12, 2), nullable=False, server_default="0"),
        # `docs/customer-experience.md`: cheap, high-impact repeat drivers. The reminder the week
        # before is M14's; capturing the date is this module's.
        sa.Column("birthday", sa.Date(), nullable=True),
        sa.Column("anniversary", sa.Date(), nullable=True),
        # DPDP erasure (§B2). Set once, never cleared. The row survives, because every order
        # pointing at it is a financial record; what is gone is everything that named a person.
        sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["home_restaurant_id"], ["restaurant.id"], name="fk_customer_home_restaurant"
        ),
        sa.UniqueConstraint("organization_id", "phone", name="uq_customer_organization_phone"),
        sa.UniqueConstraint("id", "organization_id", name="uq_customer_id_organization"),
        sa.UniqueConstraint("user_account_id", name="uq_customer_user_account"),
        sa.CheckConstraint("visit_count >= 0", name="ck_customer_visit_count"),
        sa.CheckConstraint("lifetime_value >= 0", name="ck_customer_lifetime_value"),
    )
    op.create_index(
        "ix_customer_organization_last_visit", "customer", ["organization_id", "last_visit_at"]
    )
    # The branch list's query: whose customers are these. Paired with the orders index, this is what
    # makes "the customers of the branches I am assigned to" a cheap question rather than a scan.
    op.create_index("ix_customer_home_restaurant", "customer", ["home_restaurant_id"])

    # ---------------------------------------------------------------- customer_preference
    op.create_table(
        "customer_preference",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        # The flag that decides whether the kitchen is told. An allergy is not a preference:
        # `docs/modules/M10-customers-spec.md` decision 9 copies critical preferences onto the
        # order at attach time, frozen, so a ticket's warning is the warning it actually received.
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customer.id", "customer.organization_id"],
            name="fk_customer_preference_customer_tenant",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "customer_id", "type", "value", name="uq_customer_preference_customer_type_value"
        ),
        sa.CheckConstraint(_in("type", _PREFERENCE_TYPES), name="ck_customer_preference_type"),
    )
    op.create_index(
        "ix_customer_preference_critical",
        "customer_preference",
        ["customer_id"],
        postgresql_where=sa.text("is_critical"),
    )

    # ---------------------------------------------------------------- customer_consent
    op.create_table(
        "customer_consent",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        # A withdrawal is a row with `granted = false`, not an update. Append-only, like
        # `stock_movement` and `task_event`: the history is the evidence.
        sa.Column("granted", sa.Boolean(), nullable=False),
        # What they were shown, and in which language. A consent whose words are unrecoverable is
        # not evidence of anything (`docs/compliance-rules.md` §B2: "notice version and language
        # retained").
        sa.Column("notice_version", sa.Text(), nullable=False),
        sa.Column("notice_language", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        # Null when the guest ticked it themselves, which is the case §B2 cares most about.
        sa.Column(
            "captured_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=True,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customer.id", "customer.organization_id"],
            name="fk_customer_consent_customer_tenant",
        ),
        sa.CheckConstraint(_in("purpose", _CONSENT_PURPOSES), name="ck_customer_consent_purpose"),
        sa.CheckConstraint(_in("source", _SOURCES), name="ck_customer_consent_source"),
    )
    # The only query this table serves: what is the current state of each purpose for this person.
    op.create_index(
        "ix_customer_consent_lookup",
        "customer_consent",
        ["customer_id", "purpose", sa.text("occurred_at DESC")],
    )

    # ---------------------------------------------------------------- feedback
    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        # Nullable, and strongly nudged: `docs/customer-experience.md` calls feedback that is not
        # order-linked "nearly worthless", because it cannot reach the dish, the waiter, the station
        # or the prep time. The QR path always has one; a phone call may not.
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Null for anonymous feedback, which is the default and fully supported. A guest submits
        # three taps and leaves; the order link is what makes it useful, not their name.
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer.id"),
            nullable=True,
        ),
        # The three questions the QR form asks are `food_rating`, `service_rating` and
        # `would_return`. `overall_rating` and `cleanliness_rating` exist for a manager recording a
        # conversation - a person on the phone is not filling a three-tap form.
        sa.Column("overall_rating", sa.SmallInteger(), nullable=True),
        sa.Column("food_rating", sa.SmallInteger(), nullable=True),
        sa.Column("service_rating", sa.SmallInteger(), nullable=True),
        sa.Column("cleanliness_rating", sa.SmallInteger(), nullable=True),
        # M10's addition to §9: the question that predicts revenue, and the one no existing column
        # holds. `docs/customer-experience.md`: "Food, service, would-you-return."
        sa.Column("would_return", sa.Boolean(), nullable=True),
        sa.Column("waiter_employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        # Recorded, and visible in every view. A manager filling the form for a customer is a
        # legitimate act; hiding that it happened is not.
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["order_id", "restaurant_id"],
            ["order.id", "order.restaurant_id"],
            name="fk_feedback_order_tenant",
        ),
        sa.ForeignKeyConstraint(["waiter_employee_id"], ["employee.id"], name="fk_feedback_waiter"),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_feedback_id_restaurant"),
        sa.CheckConstraint(_in("source", _SOURCES), name="ck_feedback_source"),
        sa.CheckConstraint(
            "overall_rating IS NULL OR overall_rating BETWEEN 1 AND 5",
            name="ck_feedback_overall_rating",
        ),
        sa.CheckConstraint(
            "food_rating IS NULL OR food_rating BETWEEN 1 AND 5", name="ck_feedback_food_rating"
        ),
        sa.CheckConstraint(
            "service_rating IS NULL OR service_rating BETWEEN 1 AND 5",
            name="ck_feedback_service_rating",
        ),
        sa.CheckConstraint(
            "cleanliness_rating IS NULL OR cleanliness_rating BETWEEN 1 AND 5",
            name="ck_feedback_cleanliness_rating",
        ),
        # A feedback row that says nothing is a row that cost somebody three taps and told the
        # restaurant nothing. At least one answer, or it is not feedback.
        sa.CheckConstraint(
            "overall_rating IS NOT NULL OR food_rating IS NOT NULL "
            "OR service_rating IS NOT NULL OR cleanliness_rating IS NOT NULL "
            "OR would_return IS NOT NULL OR comment IS NOT NULL",
            name="ck_feedback_says_something",
        ),
    )
    # "Never ask twice in one visit", as an index rather than a screen rule. The service returns the
    # existing row when a guest taps twice on a slow network; this is what guarantees there is one.
    op.create_index(
        "uq_feedback_order",
        "feedback",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("order_id IS NOT NULL"),
    )
    op.create_index("ix_feedback_restaurant_date", "feedback", ["restaurant_id", "business_date"])
    op.create_index(
        "ix_feedback_restaurant_waiter", "feedback", ["restaurant_id", "waiter_employee_id"]
    )

    # ---------------------------------------------------------------- feedback_line
    op.create_table(
        "feedback_line",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feedback_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("menu_item_variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["feedback_id", "restaurant_id"],
            ["feedback.id", "feedback.restaurant_id"],
            name="fk_feedback_line_feedback_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["order_line_id", "restaurant_id"],
            ["order_line.id", "order_line.restaurant_id"],
            name="fk_feedback_line_order_line_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["menu_item_variant_id", "restaurant_id"],
            ["menu_item_variant.id", "menu_item_variant.restaurant_id"],
            name="fk_feedback_line_variant_tenant",
        ),
        sa.UniqueConstraint("feedback_id", "order_line_id", name="uq_feedback_line_once_per_line"),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_feedback_line_rating"),
    )
    # M13 reads this: which dish is rated badly, across every order that ever contained it.
    op.create_index("ix_feedback_line_variant", "feedback_line", ["menu_item_variant_id"])

    # ---------------------------------------------------------------- complaint
    op.create_table(
        "complaint",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer.id"),
            nullable=True,
        ),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("order_line_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("feedback_id", postgresql.UUID(as_uuid=True), nullable=True),
        # What a person says out loud. "Complaint 47" is quotable on a phone call and a UUID is not,
        # which is the same reason `order.order_number` and `employee_code` exist beside their ids.
        # Short and per restaurant per business year, so it restarts small rather than reaching six
        # digits in the second year; the year is on the row already via `business_date`.
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        # Null when the customer raised it directly.
        sa.Column(
            "reported_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=True,
        ),
        # `docs/customer-experience.md`: a logged complaint nobody owns is worse than no system.
        sa.Column(
            "assigned_to",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("compensation_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        # The Indian financial year the reference belongs to, in the "2026-27" form
        # `app/core/business_day.py` already produces for invoice numbering. Stored rather than
        # derived so the uniqueness is a constraint the database enforces, not a rule a service
        # remembers.
        sa.Column("financial_year", sa.Text(), nullable=False),
        *_timestamps(),
        # No `customer_returned` column, deliberately, and `docs/schema.md` §9 is amended to match.
        # It is derived at read time from the order ledger (spec decision 8): a column nothing
        # writes, sitting beside a derivation that is always right, is an invitation for somebody to
        # write it - and then the only honest measure of recovery has a stale copy disagreeing
        # with it.
        sa.ForeignKeyConstraint(
            ["order_id", "restaurant_id"],
            ["order.id", "order.restaurant_id"],
            name="fk_complaint_order_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["order_line_id", "restaurant_id"],
            ["order_line.id", "order_line.restaurant_id"],
            name="fk_complaint_order_line_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["feedback_id", "restaurant_id"],
            ["feedback.id", "feedback.restaurant_id"],
            name="fk_complaint_feedback_tenant",
        ),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_complaint_id_restaurant"),
        sa.UniqueConstraint(
            "restaurant_id", "financial_year", "reference", name="uq_complaint_reference_per_year"
        ),
        sa.CheckConstraint(_in("category", _COMPLAINT_CATEGORIES), name="ck_complaint_category"),
        sa.CheckConstraint(_in("severity", _COMPLAINT_SEVERITIES), name="ck_complaint_severity"),
        sa.CheckConstraint(_in("status", _COMPLAINT_STATUSES), name="ck_complaint_status"),
        # Resolved means somebody wrote down what was done and when. A complaint that reached
        # `resolved` with an empty resolution is the paperwork this module exists to refuse.
        sa.CheckConstraint(
            "status NOT IN ('resolved', 'closed') "
            "OR (resolved_at IS NOT NULL AND resolution IS NOT NULL)",
            name="ck_complaint_resolution_pair",
        ),
        sa.CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL)", name="ck_complaint_closed_pair"
        ),
        sa.CheckConstraint(
            "compensation_amount IS NULL OR compensation_amount >= 0",
            name="ck_complaint_compensation_not_negative",
        ),
    )
    op.create_index("ix_complaint_restaurant_status", "complaint", ["restaurant_id", "status"])
    op.create_index("ix_complaint_restaurant_date", "complaint", ["restaurant_id", "business_date"])

    # ---------------------------------------------------------------- the two QR codes
    #
    # The table's public id. Opaque, rotatable, and worth exactly one thing: the menu. A sticker on
    # a table is photographed once and is then permanently public, so what it grants is the document
    # already hanging on the wall.
    #
    # Added nullable, backfilled row by row, then made NOT NULL. A single `ADD COLUMN ... NOT NULL
    # DEFAULT gen_random_uuid()` would *probably* give every row a distinct value - PostgreSQL
    # rewrites the table for a volatile default rather than storing one - but "probably" is the
    # wrong word for the uniqueness of a public credential. The explicit UPDATE cannot be wrong.
    op.add_column("restaurant_table", sa.Column("guest_slug", sa.Text(), nullable=True))
    op.execute("UPDATE restaurant_table SET guest_slug = replace(gen_random_uuid()::text, '-', '')")
    op.alter_column(
        "restaurant_table",
        "guest_slug",
        nullable=False,
        server_default=sa.text("replace(gen_random_uuid()::text, '-', '')"),
    )
    op.create_unique_constraint(
        "uq_restaurant_table_guest_slug", "restaurant_table", ["guest_slug"]
    )

    # The order's capability, stored hashed - `hash_refresh_token`'s reasoning applied to a second
    # bearer token: a stolen dump yields no live ones. Minted when the bill is requested, returned
    # once to the client that draws the QR, and never readable again; a reprint mints a new one and
    # the old photograph stops working.
    op.add_column("order", sa.Column("guest_token_hash", sa.Text(), nullable=True))
    op.add_column(
        "order", sa.Column("guest_token_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_order_guest_token_hash", "order", ["guest_token_hash"], unique=True)
    op.create_check_constraint(
        "ck_order_guest_token_pair",
        "order",
        "(guest_token_hash IS NULL) = (guest_token_expires_at IS NULL)",
    )

    # ---------------------------------------------------------------- the FK M07 left for M10
    op.create_foreign_key("fk_order_customer", "order", "customer", ["customer_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_order_customer", "order", type_="foreignkey")
    op.drop_constraint("ck_order_guest_token_pair", "order", type_="check")
    op.drop_index("ix_order_guest_token_hash", table_name="order")
    op.drop_column("order", "guest_token_expires_at")
    op.drop_column("order", "guest_token_hash")
    op.drop_constraint("uq_restaurant_table_guest_slug", "restaurant_table", type_="unique")
    op.drop_column("restaurant_table", "guest_slug")
    op.drop_table("complaint")
    op.drop_table("feedback_line")
    op.drop_table("feedback")
    op.drop_table("customer_consent")
    op.drop_table("customer_preference")
    op.drop_table("customer")
