"""m02 - one live rate per name, enforced by the database

`create_tax_group` guarantees non-overlap only when `supersedes_id` is passed. Without it, two rows
of the same name can be open at once — and an order line then takes whichever the planner returns,
which makes the tax on a bill nondeterministic and the GST filing wrong. The service comment said
so ("an order line would take whichever the query happened to return") while enforcing it on one
path of two. Found by external review, 2026-09-11.

**Per name, not per restaurant.** `seed/operations.yaml` ships `GST 5% (restaurant, no ITC)` and
`GST 18% (packaged/beverage)` both open-ended from the same date, and that is correct: they are
different tax *classes* applied to different menu items, not a supersession chain. A constraint on
`(restaurant_id, daterange)` alone — which is the obvious reading of "one live rate" — would refuse
the product's own demo data on the first `make seed`. What must not overlap is two periods claiming
to be *the same rate*.

`daterange(effective_from, effective_to, '[]')` is inclusive at both ends because `effective_to` is
the last day the rate applies, not the first day it does not: a superseded row ends the day *before*
its replacement begins, so adjacent periods must not read as overlapping. A NULL upper bound becomes
unbounded, which is exactly "still current".

Revision ID: 0007_tax_group_no_overlap
Revises: 0006_session_restaurant
"""

from __future__ import annotations

from alembic import op

revision: str = "0007_tax_group_no_overlap"
down_revision: str | None = "0006_session_restaurant"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # btree_gist is what lets a GiST exclusion constraint mix equality on scalars with overlap on a
    # range. Core Postgres, shipped with every supported version, not a third-party extension.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        ALTER TABLE tax_group
          ADD CONSTRAINT ex_tax_group_no_overlapping_period
          EXCLUDE USING gist (
              restaurant_id WITH =,
              name          WITH =,
              daterange(effective_from, effective_to, '[]') WITH &&
          )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tax_group DROP CONSTRAINT ex_tax_group_no_overlapping_period")
    # btree_gist is deliberately left installed. Dropping an extension a later migration may depend
    # on is a worse downgrade than leaving a harmless one behind.
