"""m02 - the floor, the stations, the tax rates, and the FSSAI licence

Four tables from `docs/schema.md` §2, plus finding S13.

Two of these carry more weight than their column lists suggest:

- `tax_group` is effective-dated because a GST rate is copied onto every order line at order time
  and cited by an invoice. Editing a rate in place would silently restate tax already charged and
  reported, which is a filing problem rather than a data-quality one (ADR 0004). A change is a new
  row; the old row keeps its dates. The CHECK constraints here are the floor under that rule — the
  service adds the part SQL cannot express, which is that `effective_from` may not predate today.
- `restaurant_table` is the only row in this module that changes during service rather than during
  setup, which is why `status` has a CHECK and an index rather than being a loose string.

**S13 — the FSSAI licence moves out of `settings` and into a column.** M01's seed wrote it as a
JSON key because no column existed. It prints on every bill and is a legal requirement for a food
business in India; that is not configuration. The data move below is the point of doing it here
rather than in a later module: every restaurant already seeded carries the value, and losing it
silently would be worse than never having stored it.

Revision ID: 0004_m02_restaurant_setup
Revises: 0003_password_reset_required
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004_m02_restaurant_setup"
down_revision: str | None = "0003_password_reset_required"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ---------------------------------------------------------------- S13
    op.add_column("restaurant", sa.Column("fssai_licence", sa.Text(), nullable=True))
    # Move what the seed put in `settings`, then remove the key so there is one home for the value
    # rather than two that can disagree.
    op.execute(
        """
        UPDATE restaurant
           SET fssai_licence = settings ->> 'fssai_licence',
               settings      = settings - 'fssai_licence'
         WHERE settings ? 'fssai_licence'
        """
    )

    # ---------------------------------------------------------------- the floor
    op.create_table(
        "dining_area",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("restaurant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("restaurant_id", "name", name="uq_dining_area_restaurant_name"),
    )
    op.create_index(
        "ix_dining_area_restaurant_seq", "dining_area", ["restaurant_id", "seq"], unique=False
    )

    op.create_table(
        "restaurant_table",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("restaurant_id", sa.UUID(), nullable=False),
        sa.Column("dining_area_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("seats", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('free', 'occupied', 'reserved', 'cleaning', 'out_of_service')",
            name="ck_restaurant_table_status",
        ),
        sa.CheckConstraint("seats > 0", name="ck_restaurant_table_seats_positive"),
        sa.ForeignKeyConstraint(["dining_area_id"], ["dining_area.id"]),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("restaurant_id", "code", name="uq_restaurant_table_code"),
    )
    # "What is free right now?" — asked every time a waiter opens the table map in M07.
    op.create_index(
        "ix_restaurant_table_restaurant_status",
        "restaurant_table",
        ["restaurant_id", "status"],
        unique=False,
    )

    # ---------------------------------------------------------------- the kitchen
    op.create_table(
        "station",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("restaurant_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("restaurant_id", "code", name="uq_station_restaurant_code"),
    )
    op.create_index("ix_station_restaurant_seq", "station", ["restaurant_id", "seq"], unique=False)

    # ---------------------------------------------------------------- tax
    op.create_table(
        "tax_group",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("restaurant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        # NUMERIC, never float: 0.0500 is five percent (CLAUDE.md invariant 3).
        sa.Column("rate", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("is_inclusive", sa.Boolean(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rate >= 0 AND rate <= 1", name="ck_tax_group_rate_is_a_fraction"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_tax_group_period_is_ordered",
        ),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tax_group_restaurant_effective",
        "tax_group",
        ["restaurant_id", "effective_from"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tax_group_restaurant_effective", table_name="tax_group")
    op.drop_table("tax_group")
    op.drop_index("ix_station_restaurant_seq", table_name="station")
    op.drop_table("station")
    op.drop_index("ix_restaurant_table_restaurant_status", table_name="restaurant_table")
    op.drop_table("restaurant_table")
    op.drop_index("ix_dining_area_restaurant_seq", table_name="dining_area")
    op.drop_table("dining_area")

    # Put the licence back where it came from, so down→up is genuinely reversible rather than
    # lossy. A downgrade that silently drops a legally required number is not a downgrade.
    op.execute(
        """
        UPDATE restaurant
           SET settings = settings || jsonb_build_object('fssai_licence', fssai_licence)
         WHERE fssai_licence IS NOT NULL
        """
    )
    op.drop_column("restaurant", "fssai_licence")
