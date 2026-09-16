"""m03 - the menu: categories, items, variants, modifiers

Six tables from `docs/schema.md` §3, plus two columns the schema doc does not list and the product
cannot work without:

- **`menu_category.code` and `modifier_group.code`.** `seed/menu.yaml` and `library/dishes.yaml`
  key categories as `MAIN_VEG`; `seed/operations.yaml` attaches modifier groups to categories by
  code (`SPICE_LEVEL`, `JAIN_PREF`). Without the columns both loaders would join on a display name,
  and renaming "Veg Main Course" would silently drop its modifiers. Same class of defect
  `station.code` was created to avoid in M02.
- **`restaurant.menu_version`.** Bumped by every menu write and served as the `ETag` on `GET /menu`.
  The waiter PWA loads the whole menu on every app start on a bad network; without a version to
  compare against, "cached" is the client guessing.

`menu_item_variant.tax_group_id` references `tax_group`, which migration 0008 made an *identity*
rather than a dated row — so a GST change adds a `tax_rate` and repoints nothing here.

`menu_item_modifier_group` deliberately has no `restaurant_id`: it is a pure join whose two parents
are both tenant-scoped, and a third copy of the tenant is a third thing that can disagree. The
service checks both sides and a test asserts the refusal (M03 spec, schema checklist Q7).

Revision ID: 0009_m03_menu
Revises: 0008_tax_group_identity
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_m03_menu"
down_revision: str | None = "0008_tax_group_identity"
branch_labels: str | None = None
depends_on: str | None = None


def _uuid_pk() -> sa.Column[object]:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


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
    # 0008 left two server defaults behind that its models do not declare: `tax_group.is_active`,
    # and `tax_group.id`, where `gen_random_uuid()` existed only so that migration's INSERT...SELECT
    # could mint family rows. Every table built before them uses Python-side defaults — ids are
    # UUIDv7 from the application (`app/core/ids.py`), not uuid4 from Postgres — so these are
    # dropped here rather than left to make every future `alembic revision` noisy.
    op.alter_column("tax_group", "id", server_default=None)
    op.alter_column("tax_group", "is_active", server_default=None)

    op.add_column(
        "restaurant",
        sa.Column("menu_version", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_table(
        "menu_category",
        _uuid_pk(),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("restaurant_id", "code", name="uq_menu_category_restaurant_code"),
    )
    op.create_index("ix_menu_category_restaurant_seq", "menu_category", ["restaurant_id", "seq"])

    op.create_table(
        "menu_item",
        _uuid_pk(),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column(
            "menu_category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_category.id"),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("food_type", sa.Text(), nullable=False),
        sa.Column(
            "station_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("station.id"),
            nullable=False,
        ),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("restaurant_id", "code", name="uq_menu_item_restaurant_code"),
        # Legally required in India, so a CHECK rather than a convention. A menu that cannot say
        # whether a dish is vegetarian is not a menu that may be printed.
        sa.CheckConstraint("food_type IN ('veg', 'non_veg', 'egg')", name="ck_menu_item_food_type"),
    )
    op.create_index(
        "ix_menu_item_restaurant_category",
        "menu_item",
        ["restaurant_id", "menu_category_id", "is_active"],
    )

    op.create_table(
        "menu_item_variant",
        _uuid_pk(),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column(
            "menu_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_item.id"),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        # NUMERIC, never float. This number is copied onto an order line and printed on a bill.
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "tax_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tax_group.id"),
            nullable=False,
        ),
        sa.Column("prep_minutes", sa.SmallInteger(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("menu_item_id", "code", name="uq_menu_item_variant_code"),
        # Zero is allowed — a complimentary side is a real menu line — negative is not.
        sa.CheckConstraint("price >= 0", name="ck_menu_item_variant_price_not_negative"),
        sa.CheckConstraint("prep_minutes > 0", name="ck_menu_item_variant_prep_minutes"),
    )
    op.create_index("ix_menu_item_variant_item", "menu_item_variant", ["menu_item_id", "is_active"])

    op.create_table(
        "modifier_group",
        _uuid_pk(),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("min_select", sa.SmallInteger(), nullable=False),
        sa.Column("max_select", sa.SmallInteger(), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("restaurant_id", "code", name="uq_modifier_group_restaurant_code"),
        sa.CheckConstraint("min_select >= 0", name="ck_modifier_group_min_select"),
        sa.CheckConstraint("max_select >= min_select", name="ck_modifier_group_max_ge_min"),
        # A required group permitting zero selections is a question the UI cannot render: mandatory,
        # with no answer that satisfies it.
        sa.CheckConstraint(
            "NOT is_required OR min_select >= 1", name="ck_modifier_group_required_needs_one"
        ),
    )

    op.create_table(
        "modifier",
        _uuid_pk(),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column(
            "modifier_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("modifier_group.id"),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        # No non-negative check: "no rice" can legitimately be a discount.
        sa.Column("price_delta", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("modifier_group_id", "code", name="uq_modifier_group_code"),
    )
    op.create_index("ix_modifier_group", "modifier", ["modifier_group_id", "is_active"])

    op.create_table(
        "menu_item_modifier_group",
        sa.Column(
            "menu_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("menu_item.id"),
            primary_key=True,
        ),
        sa.Column(
            "modifier_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("modifier_group.id"),
            primary_key=True,
        ),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tax_group ALTER COLUMN id SET DEFAULT gen_random_uuid()")
    op.alter_column("tax_group", "is_active", server_default=sa.true())
    op.drop_table("menu_item_modifier_group")
    op.drop_index("ix_modifier_group", table_name="modifier")
    op.drop_table("modifier")
    op.drop_table("modifier_group")
    op.drop_index("ix_menu_item_variant_item", table_name="menu_item_variant")
    op.drop_table("menu_item_variant")
    op.drop_index("ix_menu_item_restaurant_category", table_name="menu_item")
    op.drop_table("menu_item")
    op.drop_index("ix_menu_category_restaurant_seq", table_name="menu_category")
    op.drop_table("menu_category")
    op.drop_column("restaurant", "menu_version")
