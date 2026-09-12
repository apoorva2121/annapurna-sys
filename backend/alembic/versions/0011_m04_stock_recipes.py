"""m04 - stock items and recipes

Five tables from `docs/schema.md` §4. ADR 0006's unification: an ingredient and a preparation share
one `stock_item` identity, with the things that differ in a 1:1 profile beside it — which is what
lets `recipe_line.component_id` be a single foreign key instead of a nullable pair, and what lets
recipes nest.

Three deliberate departures from §4 as written, each argued in `docs/modules/M04-recipes-spec.md`:

- **`stock_item.category` takes eight values, not six.** §4's comment lists
  `meat|dairy|veg|grain|spice|oil`; `library/ingredients.yaml` already uses `bakery` (pav, bread,
  brownie) and `sweet` (honey, jaggery, chocolate sauce), and `library/validate.py` has validated
  against all eight since the library was built. A six-value CHECK would refuse the product's own
  starter library on first load.
- **`recipe` gains `modifier_id`**, so the owner CHECK is over three columns. M03 handed this over:
  "extra cheese" is 40 g of cheese that no recipe accounts for, and every one ordered makes
  theoretical consumption wrong — which invariant 7 says is the thing this product sells.
- **`recipe` gains `unit_cost`, `source` and `confirmed_at`.** `unit_cost` is finding X8's persisted
  half: a version is immutable, so what it cost when it became current is a fact, and it is what
  M13 reads instead of `stock_item.current_unit_cost` (which finding S16 flags as unsafe for a
  historical question). `source`/`confirmed_at` exist because `library/PROVENANCE.md` says most of
  the starter library is `estimated` — a recipe matched from it must not look like one a chef wrote.

**`is_current` is enforced by three partial unique indexes**, not by a service that remembers to
clear the old flag. Two current versions of one recipe would make "what does this dish cost" return
whichever row the planner happened to pick.

Revision ID: 0011_m04_stock_recipes
Revises: 0010_m03_menu_permissions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_m04_stock_recipes"
down_revision: str | None = "0010_m03_menu_permissions"
branch_labels: str | None = None
depends_on: str | None = None


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
    op.create_table(
        "stock_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("base_unit", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("storage_type", sa.Text(), nullable=True),
        sa.Column("current_unit_cost", sa.Numeric(14, 6), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("restaurant_id", "code", name="uq_stock_item_restaurant_code"),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_stock_item_id_restaurant"),
        sa.CheckConstraint("kind IN ('ingredient', 'preparation')", name="ck_stock_item_kind"),
        # ADR 0004, invariant 5: three base units, and conversion happens at the boundary.
        sa.CheckConstraint("base_unit IN ('g', 'ml', 'unit')", name="ck_stock_item_base_unit"),
        sa.CheckConstraint(
            "category IS NULL OR category IN "
            "('meat', 'dairy', 'veg', 'grain', 'spice', 'oil', 'bakery', 'sweet')",
            name="ck_stock_item_category",
        ),
        sa.CheckConstraint(
            "storage_type IS NULL OR storage_type IN ('ambient', 'chilled', 'frozen')",
            name="ck_stock_item_storage_type",
        ),
    )
    op.create_index(
        "ix_stock_item_restaurant_kind", "stock_item", ["restaurant_id", "kind", "is_active"]
    )

    op.create_table(
        "ingredient_profile",
        sa.Column(
            "stock_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stock_item.id"),
            primary_key=True,
        ),
        sa.Column("purchase_unit", sa.Text(), nullable=False),
        sa.Column("purchase_to_base", sa.Numeric(14, 4), nullable=False),
        sa.Column("yield_factor", sa.Numeric(6, 4), nullable=False, server_default="1"),
        sa.Column("shelf_life_days", sa.SmallInteger(), nullable=False),
        sa.Column("reorder_level", sa.Numeric(14, 4), nullable=True),
        sa.Column("reorder_quantity", sa.Numeric(14, 4), nullable=True),
        # The fraction of what you buy that reaches the pan. Zero would make an ingredient
        # infinitely expensive (the cost divides by it); above one would make it free.
        sa.CheckConstraint(
            "yield_factor > 0 AND yield_factor <= 1", name="ck_ingredient_yield_factor"
        ),
        sa.CheckConstraint("purchase_to_base > 0", name="ck_ingredient_purchase_to_base"),
        sa.CheckConstraint("shelf_life_days > 0", name="ck_ingredient_shelf_life"),
    )

    op.create_table(
        "preparation_profile",
        sa.Column(
            "stock_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stock_item.id"),
            primary_key=True,
        ),
        sa.Column("batch_yield", sa.Numeric(14, 4), nullable=False),
        # HOURS. A gravy made from seven-day cream dies in thirty-six (ADR 0006).
        sa.Column("shelf_life_hours", sa.SmallInteger(), nullable=False),
        sa.Column(
            "station_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("station.id"),
            nullable=False,
        ),
        sa.Column("prep_minutes", sa.SmallInteger(), nullable=False),
        # The denominator of the unit cost. Zero would divide by nothing.
        sa.CheckConstraint("batch_yield > 0", name="ck_preparation_batch_yield"),
        sa.CheckConstraint("shelf_life_hours > 0", name="ck_preparation_shelf_life"),
        sa.CheckConstraint("prep_minutes > 0", name="ck_preparation_prep_minutes"),
    )

    op.create_table(
        "recipe",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column(
            "menu_item_variant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_item_variant.id"),
            nullable=True,
        ),
        sa.Column(
            "produces_stock_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stock_item.id"),
            nullable=True,
        ),
        sa.Column(
            "modifier_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("modifier.id"),
            nullable=True,
        ),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("unit_cost", sa.Numeric(14, 6), nullable=False, server_default="0"),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        # Exactly one owner. A recipe owned by two things has no defined cost; one owned by none is
        # unreachable and will never be costed at all.
        sa.CheckConstraint(
            "num_nonnulls(menu_item_variant_id, produces_stock_item_id, modifier_id) = 1",
            name="ck_recipe_exactly_one_owner",
        ),
        sa.CheckConstraint("version > 0", name="ck_recipe_version"),
        sa.CheckConstraint("source IN ('typed', 'seeded', 'library')", name="ck_recipe_source"),
        sa.UniqueConstraint("menu_item_variant_id", "version", name="uq_recipe_variant_version"),
        sa.UniqueConstraint("produces_stock_item_id", "version", name="uq_recipe_produces_version"),
        sa.UniqueConstraint("modifier_id", "version", name="uq_recipe_modifier_version"),
    )
    op.create_index("ix_recipe_restaurant", "recipe", ["restaurant_id", "is_current"])
    # One current version per owner, as a database guarantee rather than a service that remembers to
    # clear the old flag. Partial, because `is_current = false` rows are exactly what there are many
    # of and a full unique index over a nullable column would not express this at all.
    for name, column in (
        ("uq_recipe_current_variant", "menu_item_variant_id"),
        ("uq_recipe_current_produces", "produces_stock_item_id"),
        ("uq_recipe_current_modifier", "modifier_id"),
    ):
        op.create_index(
            name,
            "recipe",
            [column],
            unique=True,
            postgresql_where=sa.text(f"is_current AND {column} IS NOT NULL"),
        )

    op.create_table(
        "recipe_line",
        sa.Column(
            "recipe_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recipe.id"), primary_key=True
        ),
        sa.Column(
            "component_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stock_item.id"),
            primary_key=True,
        ),
        sa.Column("quantity", sa.Numeric(14, 4), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_recipe_line_quantity"),
        # No unique constraint on (recipe_id, component_id): that pair *is* the primary key, and a
        # second index over the same columns would be dead weight on every write.
    )
    # The reverse index, and the reason `docs/schema.md` §4 puts one here: "what uses paneer?" is
    # the question an owner asks first when a price moves, and without this it is a full scan.
    op.create_index("ix_recipe_line_component", "recipe_line", ["component_id"])


def downgrade() -> None:
    op.drop_index("ix_recipe_line_component", table_name="recipe_line")
    op.drop_table("recipe_line")
    for name in (
        "uq_recipe_current_modifier",
        "uq_recipe_current_produces",
        "uq_recipe_current_variant",
        "ix_recipe_restaurant",
    ):
        op.drop_index(name, table_name="recipe")
    op.drop_table("recipe")
    op.drop_table("preparation_profile")
    op.drop_table("ingredient_profile")
    op.drop_index("ix_stock_item_restaurant_kind", table_name="stock_item")
    op.drop_table("stock_item")
