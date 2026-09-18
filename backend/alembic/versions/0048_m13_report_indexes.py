"""m13 - one index, and it is here because a query plan asked for it

The spec said this migration would be **written last, from measurements**, and that if the plans
showed nothing missing it would not be written at all — "an index added speculatively is a write
cost nobody can justify later". The measurements are in `docs/plan/m13-build-log.md`: ninety days,
1800 bills, 5400 lines, 7200 ledger movements, every report between 6 ms and 32 ms against a budget
of 800 ms. Nothing is slow.

What the plans *did* show is one column filtered with no index on it, and it is not a scale
argument:

    Seq Scan on invoice
      Filter: (business_date >= … AND business_date <= … AND restaurant_id = …)

`invoice` carries `ix_invoice_restaurant_date` on `(restaurant_id, invoice_date)` — the date
printed on the document. The sales report filters on `business_date`, the restaurant's own trading
day, which begins at 05:00 (invariant 4) and is a different column with different values for every
bill settled after midnight. So the table has an index for the column beside the one the product's
most-run report actually uses. That is an oversight to correct rather than an optimisation to
justify, and one btree on a table that takes one insert per bill costs nothing worth arguing about.

**Nothing else is added.** `order`, `payment`, `stock_movement` and `wastage_event` each already
carry `(restaurant_id, business_date)` or better, and the plans confirm the planner uses what it
has. Where it chose a sequential scan anyway it was right to: forty ingredients and 7200 movements
fit in 150 buffers, and an index scan would have been slower.

Revision ID: 0048_m13_report_indexes
Revises: 0047_m13_permissions
"""

from __future__ import annotations

from alembic import op

revision: str = "0048_m13_report_indexes"
down_revision: str | None = "0047_m13_permissions"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_index(
        "ix_invoice_restaurant_business_date",
        "invoice",
        ["restaurant_id", "business_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_invoice_restaurant_business_date", table_name="invoice")
