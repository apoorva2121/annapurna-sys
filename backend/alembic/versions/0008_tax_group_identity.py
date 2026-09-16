"""m03 - a tax group is an identity; its rates are effective-dated rows beneath it

M02 built `tax_group` as an effective-dated row: a rate change creates a new row and closes the old
one. That is right for the *rate* and wrong for the *identity*, and the gap becomes a bug the moment
something points at a tax group. `docs/schema.md` §3 has `menu_item_variant.tax_group_id NN
FK→tax_group`, and M03 creates that column — so on the first GST change every dish on the menu would
point at a closed row with nothing linking it forward. `docs/backlog.md` filed this twice and both
entries named the wrong module (M06, M04); the foreign key is created in M03.

The split, which is what the schema doc's sentence meant all along:

    tax_group   the identity. "GST 5% (restaurant, no ITC)", code GST5. One row, forever.
    tax_rate    what that group charges, and between which dates. Many rows, superseded in turn.

A menu item references the **group**. The rate effective on a given business date is resolved by
date. Nothing is repointed when a rate changes, and `order_line` still copies the resolved rate at
order time so history cannot move (CLAUDE.md invariant 6).

**No data is copied.** `tax_group` is *renamed* to `tax_rate`, so every existing row keeps its id,
its dates and its audit trail, and the new identity table is built above it. A rename cannot lose a
row; an INSERT ... SELECT can.

**The family key was already `name`.** 0007's exclusion constraint was
`(restaurant_id, name, daterange)` — "what must not overlap is two periods claiming to be the same
rate". Grouping the surviving rows by `(restaurant_id, name)` is therefore a faithful translation of
the rule that was already enforced, not a new guess about which rows belong together.

`code` is backfilled from the name's leading phrase: `"GST 5% (restaurant, no ITC)"` → `GST5`, which
is exactly the code `seed/operations.yaml` already carries and which the seeder could not store
because no column existed. Collisions get a numeric suffix.

Revision ID: 0008_tax_group_identity
Revises: 0007_tax_group_no_overlap
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_tax_group_identity"
down_revision: str | None = "0007_tax_group_no_overlap"
branch_labels: str | None = None
depends_on: str | None = None


# The leading phrase of the name, alphanumerics only, uppercased: everything before the first " ("
# so a parenthetical qualifier does not end up in the code. Written once and substituted in two
# places below, because the SELECT and the PARTITION BY must group by exactly the same expression —
# if they ever drift, the row numbering stops matching the codes it is de-duplicating.
_SLUG = "upper(regexp_replace(split_part(name, ' (', 1), '[^a-zA-Z0-9]', '', 'g'))"

# Substituted with `.replace`, not an f-string. Nothing here is user input — `_SLUG` is the literal
# above — but an f-string around SQL is the shape of the injection bug, and a linter that cannot
# tell the two apart is right to say so. Keeping the statement a plain literal means the rule stays
# switched on for every migration written after this one.
_FAMILIES_SQL = """
INSERT INTO tax_group (restaurant_id, code, name, created_at, updated_at)
SELECT restaurant_id,
       CASE WHEN rn = 1 THEN base_code ELSE base_code || '_' || rn END,
       name,
       first_seen,
       now()
FROM (
    SELECT restaurant_id,
           name,
           {slug} AS base_code,
           min(created_at) AS first_seen,
           row_number() OVER (
               PARTITION BY restaurant_id, {slug}
               ORDER BY min(effective_from), min(name)
           ) AS rn
    FROM tax_rate
    GROUP BY restaurant_id, name
) families
"""


def upgrade() -> None:
    # --------------------------------------------------------------- 1 · rate rows keep their ids
    # The exclusion constraint goes first: it names `name`, which moves to the identity table.
    op.execute("ALTER TABLE tax_group DROP CONSTRAINT ex_tax_group_no_overlapping_period")
    op.execute("ALTER TABLE tax_group RENAME TO tax_rate")

    # A table rename leaves constraint and index names behind, and a name that describes the wrong
    # table is how the next person reads the schema wrongly.
    for old, new in (
        ("tax_group_pkey", "tax_rate_pkey"),
        ("ck_tax_group_rate_is_a_fraction", "ck_tax_rate_rate_is_a_fraction"),
        ("ck_tax_group_period_is_ordered", "ck_tax_rate_period_is_ordered"),
        ("tax_group_restaurant_id_fkey", "tax_rate_restaurant_id_fkey"),
    ):
        op.execute(f"ALTER TABLE tax_rate RENAME CONSTRAINT {old} TO {new}")
    op.execute(
        "ALTER INDEX ix_tax_group_restaurant_effective RENAME TO ix_tax_rate_restaurant_effective"
    )

    # --------------------------------------------------------------- 2 · the identity table
    op.create_table(
        "tax_group",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("restaurant_id", "code", name="uq_tax_group_restaurant_code"),
        # The target of tax_rate's composite foreign key below. Without it Postgres will not accept
        # a two-column reference, and the tenant agreement between a rate and its group goes back
        # to being a convention.
        sa.UniqueConstraint("id", "restaurant_id", name="uq_tax_group_id_restaurant"),
    )

    # --------------------------------------------------------------- 3 · one identity per family
    # `name` is the family key 0007 already enforced. Codes are de-duplicated per restaurant, so a
    # restaurant with "GST 5% (food)" and "GST 5% (packaged)" gets GST5 and GST5_2 rather than a
    # constraint violation on a migration nobody can rerun.
    op.execute(_FAMILIES_SQL.replace("{slug}", _SLUG))

    # --------------------------------------------------------------- 4 · point the rates at them
    op.add_column(
        "tax_rate", sa.Column("tax_group_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.execute(
        """
        UPDATE tax_rate r
           SET tax_group_id = g.id
          FROM tax_group g
         WHERE g.restaurant_id = r.restaurant_id
           AND g.name = r.name
        """
    )
    # If the backfill missed a row the join above was wrong, and a NOT NULL that fails here is a
    # migration that stops rather than a table that quietly loses its tax.
    op.alter_column("tax_rate", "tax_group_id", nullable=False)
    op.drop_column("tax_rate", "name")

    op.create_foreign_key(
        "fk_tax_rate_group_same_restaurant",
        "tax_rate",
        "tax_group",
        ["tax_group_id", "restaurant_id"],
        ["id", "restaurant_id"],
    )
    op.create_index("ix_tax_rate_group", "tax_rate", ["tax_group_id", "effective_from"])

    # --------------------------------------------------------------- 5 · the rule, moved across
    # Same guarantee as 0007, now keyed on the group rather than on a display string. Renaming a
    # group can no longer change which rows are considered the same rate.
    op.execute(
        """
        ALTER TABLE tax_rate
          ADD CONSTRAINT ex_tax_rate_no_overlapping_period
          EXCLUDE USING gist (
              tax_group_id WITH =,
              daterange(effective_from, effective_to, '[]') WITH &&
          )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tax_rate DROP CONSTRAINT ex_tax_rate_no_overlapping_period")
    op.drop_index("ix_tax_rate_group", table_name="tax_rate")
    op.drop_constraint("fk_tax_rate_group_same_restaurant", "tax_rate", type_="foreignkey")

    # The name comes back from the group it points at, which is where it went.
    op.add_column("tax_rate", sa.Column("name", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE tax_rate r
           SET name = g.name
          FROM tax_group g
         WHERE g.id = r.tax_group_id
        """
    )
    op.alter_column("tax_rate", "name", nullable=False)
    op.drop_column("tax_rate", "tax_group_id")
    op.drop_table("tax_group")

    op.execute(
        "ALTER INDEX ix_tax_rate_restaurant_effective RENAME TO ix_tax_group_restaurant_effective"
    )
    for new, old in (
        ("tax_rate_pkey", "tax_group_pkey"),
        ("ck_tax_rate_rate_is_a_fraction", "ck_tax_group_rate_is_a_fraction"),
        ("ck_tax_rate_period_is_ordered", "ck_tax_group_period_is_ordered"),
        ("tax_rate_restaurant_id_fkey", "tax_group_restaurant_id_fkey"),
    ):
        op.execute(f"ALTER TABLE tax_rate RENAME CONSTRAINT {new} TO {old}")
    op.execute("ALTER TABLE tax_rate RENAME TO tax_group")
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
