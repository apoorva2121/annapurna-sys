"""stock_item.cost_source - say where a price came from, so the UI can say how much to trust it

`docs/onboarding-cold-start.md` makes a promise this schema could not keep:

    **Prices** - bootstrap from a market-rate table by city, then correct on first real purchase.
    Wrong-but-close prices on day one beat empty fields, *as long as they are visibly marked
    estimated*.

Nothing on `stock_item` could express "estimated". `current_unit_cost` is a bare NUMERIC, so a
price bootstrapped from a national average and a price copied off this restaurant's own supplier
bill were the same column with the same authority. That matters more here than it would in most
products, because the day-1 commercial pitch - "here are the eleven dishes on your menu that lose
money on every plate" - is computed entirely from these numbers, before the restaurant has recorded
a single purchase. Stating that sentence from an unmarked guess is how you lose the room.

**Why the default is `market_rate` and not `manual`.** A price whose provenance nobody set is a
price nobody vouched for. Defaulting to `manual` would claim a human typed it; defaulting to
`market_rate` claims only that it came from somewhere generic. The first failure mode is a guess
that gets believed, the second is a real price that gets double-checked - so the default fails
toward honesty, which is the direction this column exists to enforce.

Existing rows are backfilled to `market_rate` for the same reason: every price in the database
today came from `seed/ingredients.yaml`, which is hand-set demo data for a synthetic restaurant.
None of it is any real restaurant's confirmed cost.

No `audit_log` entry is written here. This migration adds a column and touches no price (CLAUDE.md
invariant 6 covers changes to price, not to its metadata). The write paths that *move* a cost
between sources - the onboarding bootstrap, and M06's purchase-driven update - do owe an audit
entry, and neither exists yet.

Revision ID: 0014_stock_item_cost_source
Revises: 0013_m04_review_fixes
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0014_stock_item_cost_source"
down_revision: str | None = "0013_m04_review_fixes"
branch_labels: str | None = None
depends_on: str | None = None

_CHECK = "cost_source IN ('market_rate', 'manual', 'purchase')"


def upgrade() -> None:
    op.add_column(
        "stock_item",
        sa.Column(
            "cost_source",
            sa.Text(),
            nullable=False,
            server_default="market_rate",
        ),
    )
    # ADR 0008: text column with a CHECK constraint, never a Postgres native enum - adding a value
    # to a native enum is a lock, and this list will grow (a supplier-quote source is already
    # foreseeable with M06).
    op.create_check_constraint("ck_stock_item_cost_source", "stock_item", _CHECK)

    # Partial index on the un-vouched-for rows. The onboarding flow's "confirm your prices" screen
    # and the day-1 cost screens both need exactly this set, and on a restaurant that has been
    # running a while it is the small minority of the table.
    op.create_index(
        "ix_stock_item_unconfirmed_cost",
        "stock_item",
        ["restaurant_id"],
        postgresql_where=sa.text("cost_source = 'market_rate'"),
    )


def downgrade() -> None:
    op.drop_index("ix_stock_item_unconfirmed_cost", table_name="stock_item")
    op.drop_constraint("ck_stock_item_cost_source", "stock_item", type_="check")
    op.drop_column("stock_item", "cost_source")
