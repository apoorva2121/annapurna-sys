"""Stock items and recipes — `docs/schema.md` §4, and the heart of the product.

**One identity table for two kinds of thing.** ADR 0006's central move: an ingredient and a
preparation both hold stock, both expire and both have a cost, so they share `stock_item` and the
things that differ live in a 1:1 profile beside it. That is what lets `recipe_line.component_id` be
a single clean foreign key instead of a nullable pair, and it is what lets recipes nest — a line can
reference a preparation exactly as easily as an ingredient.

**A recipe is versioned and never edited.** `order_line` (M07) cites the version that was current
when the line was added, so a recipe change must leave every past order's cost alone. The same rule
a tax rate follows, for the same reason: history that moves is a filing problem, not a data-quality
one.

**A recipe belongs to exactly one of three things** — a menu variant (Half is a different recipe
from Full), a preparation it produces (makhani gravy has a recipe too), or a modifier (extra cheese
is 40 g of cheese that would otherwise be consumed by nobody). The CHECK enforces "exactly one",
because a recipe owned by two things has no defined cost and a recipe owned by none is unreachable.

Deletion: `stock_item` is deactivated, never deleted (ADR 0008). **`recipe` is neither** — an order
from last year cites a version and that version must resolve forever. `is_current` moves; rows stay.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampedUUIDMixin

# `g`, `ml`, `unit` — ADR 0004, CLAUDE.md invariant 5. Convert at the boundary, store base units.
BASE_UNITS = ("g", "ml", "unit")

# Eight, not the six `docs/schema.md` §4 comments. `library/ingredients.yaml` already uses `bakery`
# (pav, bread, brownie) and `sweet` (honey, jaggery, chocolate sauce), so a six-value CHECK would
# refuse the product's own starter library the first time anyone loaded it.
STOCK_CATEGORIES = ("meat", "dairy", "veg", "grain", "spice", "oil", "bakery", "sweet")

STORAGE_TYPES = ("ambient", "chilled", "frozen")

# Where a recipe came from, and whether anyone has checked it. `library/PROVENANCE.md` is explicit
# that most of the starter library is `estimated` — domain knowledge a chef has not confirmed — so a
# matched recipe must never be indistinguishable from one a chef wrote. Without this, the dish-cost
# screen states a number with confidence nobody has earned.
RECIPE_SOURCES = ("typed", "seeded", "library")


class StockItem(TimestampedUUIDMixin, Base):
    """Anything that holds stock: an ingredient bought in, or a preparation made in-house."""

    __tablename__ = "stock_item"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "code", name="uq_stock_item_restaurant_code"),
        CheckConstraint("kind IN ('ingredient', 'preparation')", name="ck_stock_item_kind"),
        CheckConstraint("base_unit IN ('g', 'ml', 'unit')", name="ck_stock_item_base_unit"),
        CheckConstraint(
            "category IS NULL OR category IN "
            "('meat', 'dairy', 'veg', 'grain', 'spice', 'oil', 'bakery', 'sweet')",
            name="ck_stock_item_category",
        ),
        CheckConstraint(
            "storage_type IS NULL OR storage_type IN ('ambient', 'chilled', 'frozen')",
            name="ck_stock_item_storage_type",
        ),
        # The target of the composite foreign keys below: a profile, and every recipe line, must
        # belong to the same restaurant as the item they point at, and that is a database
        # guarantee rather than something a service remembers.
        UniqueConstraint("id", "restaurant_id", name="uq_stock_item_id_restaurant"),
        Index("ix_stock_item_restaurant_kind", "restaurant_id", "kind", "is_active"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    # Immutable after creation, like every other code in this product: `seed/ingredients.yaml`,
    # `library/ingredients.yaml` and every recipe line in both join on it.
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_unit: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    storage_type: Mapped[str | None] = mapped_column(Text)
    # **A cache, and never a historical answer.** Finding S16: reading this to cost a past order
    # reports today's price for yesterday's consumption. `recipe.unit_cost` (frozen per version)
    # and M05's per-batch cost are the truths; this is what a screen shows for "roughly, now".
    current_unit_cost: Mapped[object] = mapped_column(
        Numeric(14, 6), nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    ingredient: Mapped[IngredientProfile | None] = relationship(
        back_populates="item", uselist=False, lazy="raise"
    )
    preparation: Mapped[PreparationProfile | None] = relationship(
        back_populates="item", uselist=False, lazy="raise"
    )


class IngredientProfile(Base):
    """What is true of a bought-in ingredient and not of a preparation.

    `stock_item_id` is the primary key, not a surrogate: the profile *is* the item, seen from one
    side. A second id would be a second way to name the same thing.
    """

    __tablename__ = "ingredient_profile"
    __table_args__ = (
        # `yield_factor` is the fraction of what you buy that reaches the pan: trim loss for a
        # weight, breakage and spoilage for a count. It applies to every base unit — see the M04
        # spec's S15 discussion, which is the one open decision in that module.
        CheckConstraint(
            "yield_factor > 0 AND yield_factor <= 1", name="ck_ingredient_yield_factor"
        ),
        CheckConstraint("purchase_to_base > 0", name="ck_ingredient_purchase_to_base"),
        CheckConstraint("shelf_life_days > 0", name="ck_ingredient_shelf_life"),
    )

    stock_item_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("stock_item.id"), primary_key=True
    )
    # "kg", "litre", "dozen" — what the supplier's bill says.
    purchase_unit: Mapped[str] = mapped_column(Text, nullable=False)
    # 1 kg = 1000 g. The conversion happens once, here, at the boundary (invariant 5).
    purchase_to_base: Mapped[object] = mapped_column(Numeric(14, 4), nullable=False)
    yield_factor: Mapped[object] = mapped_column(
        Numeric(6, 4), nullable=False, default=1, server_default="1"
    )
    shelf_life_days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reorder_level: Mapped[object | None] = mapped_column(Numeric(14, 4))
    reorder_quantity: Mapped[object | None] = mapped_column(Numeric(14, 4))

    item: Mapped[StockItem] = relationship(back_populates="ingredient", lazy="raise")


class PreparationProfile(Base):
    """What is true of something the kitchen makes rather than buys.

    `shelf_life_hours`, not days, and that is the point of the column existing separately: raw
    cream lasts a week, and the makhani gravy made from it dies in thirty-six hours (ADR 0006).
    """

    __tablename__ = "preparation_profile"
    __table_args__ = (
        CheckConstraint("batch_yield > 0", name="ck_preparation_batch_yield"),
        CheckConstraint("shelf_life_hours > 0", name="ck_preparation_shelf_life"),
        CheckConstraint("prep_minutes > 0", name="ck_preparation_prep_minutes"),
    )

    stock_item_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("stock_item.id"), primary_key=True
    )
    # One standard production batch, in the item's base unit. The denominator of the unit cost.
    batch_yield: Mapped[object] = mapped_column(Numeric(14, 4), nullable=False)
    shelf_life_hours: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    station_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("station.id"), nullable=False
    )
    prep_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    item: Mapped[StockItem] = relationship(back_populates="preparation", lazy="raise")


class Recipe(TimestampedUUIDMixin, Base):
    """What a thing is made of, at a point in time.

    Owned by exactly one of three: a menu variant, a preparation, or a modifier. The third is M03's
    inherited obligation — "extra cheese" is 40 g of cheese that no recipe accounted for, and every
    one of those ordered makes theoretical consumption wrong (CLAUDE.md invariant 7).
    """

    __tablename__ = "recipe"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(menu_item_variant_id, produces_stock_item_id, modifier_id) = 1",
            name="ck_recipe_exactly_one_owner",
        ),
        CheckConstraint("version > 0", name="ck_recipe_version"),
        CheckConstraint("source IN ('typed', 'seeded', 'library')", name="ck_recipe_source"),
        UniqueConstraint("menu_item_variant_id", "version", name="uq_recipe_variant_version"),
        UniqueConstraint("produces_stock_item_id", "version", name="uq_recipe_produces_version"),
        UniqueConstraint("modifier_id", "version", name="uq_recipe_modifier_version"),
        # One current version per owner, enforced by three partial unique indexes rather than by a
        # service that remembers to clear the old flag. Partial, because `is_current = false` rows
        # are exactly what there are many of.
        Index(
            "uq_recipe_current_variant",
            "menu_item_variant_id",
            unique=True,
            postgresql_where=text("is_current AND menu_item_variant_id IS NOT NULL"),
        ),
        Index(
            "uq_recipe_current_produces",
            "produces_stock_item_id",
            unique=True,
            postgresql_where=text("is_current AND produces_stock_item_id IS NOT NULL"),
        ),
        Index(
            "uq_recipe_current_modifier",
            "modifier_id",
            unique=True,
            postgresql_where=text("is_current AND modifier_id IS NOT NULL"),
        ),
        Index("ix_recipe_restaurant", "restaurant_id", "is_current"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    menu_item_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("menu_item_variant.id")
    )
    produces_stock_item_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("stock_item.id")
    )
    modifier_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("modifier.id")
    )
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    # **Frozen when this version became current** (finding X8). A version is immutable, so what it
    # cost at that moment is a fact — and it is what M13 reads to answer "what did this dish cost in
    # March" without replaying March's ingredient prices or trusting today's cached unit cost.
    unit_cost: Mapped[object] = mapped_column(
        Numeric(14, 6), nullable=False, default=0, server_default="0"
    )
    # Where this recipe came from, and whether a human has confirmed it. A recipe matched from
    # `library/` carries quantities nobody at this restaurant has checked.
    source: Mapped[str] = mapped_column(Text, nullable=False, default="typed")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list[RecipeLine]] = relationship(
        back_populates="recipe", order_by="RecipeLine.seq", lazy="raise"
    )


class RecipeLine(Base):
    """One component and how much of it.

    `component_id` points at `stock_item` and not at "ingredient or preparation", which is the whole
    reason ADR 0006 unified them: a line does not care which it is, and that is what makes nesting
    work without a nullable pair of foreign keys.

    No `restaurant_id`, like M03's `menu_item_modifier_group`: the parent recipe carries one and a
    third copy is a third thing that can disagree. The composite foreign key below is what keeps the
    component on the same tenant as the recipe — structurally, rather than by service discipline.
    """

    __tablename__ = "recipe_line"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_recipe_line_quantity"),
        # The reverse index. `docs/schema.md` §4 puts it here specifically to answer "what uses
        # paneer?", which is the question an owner asks first when a price moves.
        Index("ix_recipe_line_component", "component_id"),
    )

    recipe_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("recipe.id"), primary_key=True
    )
    component_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("stock_item.id"), primary_key=True
    )
    # In the component's base unit. `numeric(14,4)` because a recipe line can legitimately be 0.05 g
    # of saffron, and rounding that to two places would make it free.
    quantity: Mapped[object] = mapped_column(Numeric(14, 4), nullable=False)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    recipe: Mapped[Recipe] = relationship(back_populates="lines", lazy="raise")
    component: Mapped[StockItem] = relationship(lazy="raise")
