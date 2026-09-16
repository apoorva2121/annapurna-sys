"""m04 - close the tenant holes the adversarial review found

Three defects, all found by the M03/M04 review round on 2026-09-12, all of the same family: a
tenant boundary that the code *claimed* was structural and was not.

**1 · `recipe_line` gets `restaurant_id` and a composite foreign key.** Its model docstring said
"The composite foreign key below is what keeps the component on the same tenant as the recipe —
structurally, rather than by service discipline." **There was no composite foreign key.**
`component_id` was a plain single-column reference, and `uq_stock_item_id_restaurant` — created and
commented as "the target of the composite foreign keys below" — was the target of nothing. The
protection was `StockService.save_version`'s `ids_owned` check alone.

That is exactly CLAUDE.md invariant 1's "#1 bug class", and it matters more than usual here because
M04 explicitly hands a *second* write path to a later module: the `library/` matching flow. A second
writer that skipped the service would have had nothing beneath it. `tax_rate` already demonstrated
the right pattern in migration 0008; this applies it where the docstring promised it.

**2 · The three `uq_recipe_current_*` partial indexes were global.** `uq_recipe_current_modifier`
keyed on `modifier_id` alone, with no restaurant. Combined with defect 3, one restaurant could
insert a recipe against another restaurant's modifier and *permanently* prevent the owner from
creating one — the owner's insert would hit the index and, since `IntegrityError` is unmapped, come
back as a 500 with no explanation and no recovery. A cross-tenant denial of service on a tenant's
own data.

**3 · Nothing validated `recipe.modifier_id` at all** — not for existence, not for tenancy. Fixed in
`StockService._require_owner_exists`, not here, but it is the other half of defect 2 and the two
should be read together.

The indexes are rebuilt rather than altered because a partial unique index's predicate cannot be
changed in place.

Revision ID: 0013_m04_review_fixes
Revises: 0012_m04_recipe_permissions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_m04_review_fixes"
down_revision: str | None = "0012_m04_recipe_permissions"
branch_labels: str | None = None
depends_on: str | None = None

_CURRENT_INDEXES = (
    ("uq_recipe_current_variant", "menu_item_variant_id"),
    ("uq_recipe_current_produces", "produces_stock_item_id"),
    ("uq_recipe_current_modifier", "modifier_id"),
)


def upgrade() -> None:
    # ---------------------------------------------------------------- 1 · recipe_line tenancy
    op.add_column(
        "recipe_line", sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    # Backfilled from the parent recipe, which has always carried one. No row can be ambiguous:
    # every `recipe_line` has exactly one `recipe_id` and every recipe has a restaurant.
    op.execute(
        """
        UPDATE recipe_line l
           SET restaurant_id = r.restaurant_id
          FROM recipe r
         WHERE r.id = l.recipe_id
        """
    )
    op.alter_column("recipe_line", "restaurant_id", nullable=False)
    op.create_foreign_key(
        "fk_recipe_line_restaurant", "recipe_line", "restaurant", ["restaurant_id"], ["id"]
    )
    # The two constraints the model docstring promised. `uq_stock_item_id_restaurant` and
    # `uq_recipe_id_restaurant` are their targets — the first already existed and was unused.
    op.create_unique_constraint("uq_recipe_id_restaurant", "recipe", ["id", "restaurant_id"])
    op.create_foreign_key(
        "fk_recipe_line_recipe_same_restaurant",
        "recipe_line",
        "recipe",
        ["recipe_id", "restaurant_id"],
        ["id", "restaurant_id"],
    )
    op.create_foreign_key(
        "fk_recipe_line_component_same_restaurant",
        "recipe_line",
        "stock_item",
        ["component_id", "restaurant_id"],
        ["id", "restaurant_id"],
    )
    # The single-column foreign keys 0011 created are now redundant — the composites above reference
    # the same two tables and say strictly more. Left in place they are two foreign key paths between
    # one pair of tables, which SQLAlchemy cannot resolve into a join at all.
    op.drop_constraint("recipe_line_recipe_id_fkey", "recipe_line", type_="foreignkey")
    op.drop_constraint("recipe_line_component_id_fkey", "recipe_line", type_="foreignkey")

    # ---------------------------------------------------------------- 2 · scope the current-version
    # indexes to a restaurant. A partial index's predicate cannot be altered, so they are rebuilt.
    for name, column in _CURRENT_INDEXES:
        op.drop_index(name, table_name="recipe")
        op.create_index(
            name,
            "recipe",
            ["restaurant_id", column],
            unique=True,
            postgresql_where=sa.text(f"is_current AND {column} IS NOT NULL"),
        )

    # ---------------------------------------------------------------- 3 · the menu tree's hot index
    # `selectinload(MenuCategory.items)` emits `WHERE menu_item.menu_category_id IN (…)` with no
    # `restaurant_id` predicate — selectinload keys only on the relationship's join column. The
    # existing index leads with `restaurant_id`, and Postgres has no index skip-scan, so the hottest
    # query in the product was sequentially scanning `menu_item` on every cache miss. The
    # query-count test could not see it: a sequential scan is one statement.
    op.create_index("ix_menu_item_category", "menu_item", ["menu_category_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_menu_item_category", table_name="menu_item")

    for name, column in _CURRENT_INDEXES:
        op.drop_index(name, table_name="recipe")
        op.create_index(
            name,
            "recipe",
            [column],
            unique=True,
            postgresql_where=sa.text(f"is_current AND {column} IS NOT NULL"),
        )

    op.create_foreign_key(
        "recipe_line_recipe_id_fkey", "recipe_line", "recipe", ["recipe_id"], ["id"]
    )
    op.create_foreign_key(
        "recipe_line_component_id_fkey", "recipe_line", "stock_item", ["component_id"], ["id"]
    )
    op.drop_constraint(
        "fk_recipe_line_component_same_restaurant", "recipe_line", type_="foreignkey"
    )
    op.drop_constraint("fk_recipe_line_recipe_same_restaurant", "recipe_line", type_="foreignkey")
    op.drop_constraint("uq_recipe_id_restaurant", "recipe", type_="unique")
    op.drop_constraint("fk_recipe_line_restaurant", "recipe_line", type_="foreignkey")
    op.drop_column("recipe_line", "restaurant_id")
