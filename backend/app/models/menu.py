"""The menu — `docs/schema.md` §3. Six tables, and the spine of everything commercial.

`order_line` points at a variant forever, `recipe` hangs off a variant, and every margin number in
M13 resolves through here. Three things are worth reading before changing anything:

- **Price lives on the variant, never the item.** A half plate is a different price, a different
  recipe and a different food cost. The item is the dish; the variant is the thing sold.
- **`menu_item.code` is a contract, not a label.** `seed/menu.yaml` and `library/dishes.yaml` both
  key on `BUTTER_CHICKEN`, and that code is how M04's onboarding does "match, don't create"
  (`docs/onboarding-cold-start.md`). It is immutable after creation, exactly as `station.code` is.
- **`food_type` is legally required in India**, not a convenience. FSSAI requires the veg/non-veg
  declaration, which is why it is `NOT NULL` with a CHECK rather than an optional tag.

`menu_item_modifier_group` is the one table here without `restaurant_id`, and that is deliberate:
it is a pure join keyed `(menu_item_id, modifier_group_id)` whose two parents are already
tenant-scoped, so a third copy of the tenant is a third thing that can disagree. The cost is that
`RestaurantScopedRepository` cannot filter it, so the service checks both sides by hand and a test
asserts that attaching another tenant's group is refused (M03 spec, schema checklist Q7).

Deactivation everywhere, deletion nowhere (ADR 0008): an order line from last year must still
resolve to the variant it sold.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampedUUIDMixin

# Kept in one place so the migration, the model and the validator cannot drift. The values are the
# ones `seed/menu.yaml` and `library/dishes.yaml` already use.
FOOD_TYPES = ("veg", "non_veg", "egg")


class MenuCategory(TimestampedUUIDMixin, Base):
    """A section of the menu. Ordered, because a printed menu has an order and the screen does
    too."""

    __tablename__ = "menu_category"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "code", name="uq_menu_category_restaurant_code"),
        Index("ix_menu_category_restaurant_seq", "restaurant_id", "seq"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    # `docs/schema.md` §3 does not list a code on this table, and the seed needs one: both
    # `seed/menu.yaml` and `library/dishes.yaml` key categories as MAIN_VEG, RICE_BREAD and so on,
    # and `operations.yaml` attaches modifier groups *by category code*. Without it the loader would
    # join on a display name, which is how renaming "Veg Main Course" silently drops its modifiers.
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Ordered, like every other relationship in this file. Without it the tree's `selectinload`
    # returns whatever order the scan yields, so a dish repriced at 11am moves down its category at
    # 11:01 — and `menu_item.seq` exists, is maintained, and is indexed. Found by review.
    items: Mapped[list[MenuItem]] = relationship(
        back_populates="category", order_by="MenuItem.seq, MenuItem.id", lazy="raise"
    )


class MenuItem(TimestampedUUIDMixin, Base):
    """A dish. What it costs is on its variants; what it is, is here."""

    __tablename__ = "menu_item"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "code", name="uq_menu_item_restaurant_code"),
        CheckConstraint("food_type IN ('veg', 'non_veg', 'egg')", name="ck_menu_item_food_type"),
        Index("ix_menu_item_restaurant_category", "restaurant_id", "menu_category_id", "is_active"),
        # The tree's `selectinload` emits `WHERE menu_category_id IN (…)` with no `restaurant_id`
        # predicate, and Postgres has no index skip-scan — so the index above was unusable on the
        # hottest read in the product and it sequentially scanned. A query-count test cannot see
        # this: a sequential scan is one statement. Found by review (0013).
        Index("ix_menu_item_category", "menu_category_id", "is_active"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    menu_category_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("menu_category.id"), nullable=False
    )
    # Immutable after creation. It is the join key to `library/dishes.yaml`, to `seed/menu.yaml` and
    # to every recipe M04 will attach — renaming it breaks cost tracking while sales carry on.
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # FSSAI requires this declaration on menus. NOT NULL and checked, not an optional tag.
    food_type: Mapped[str] = mapped_column(Text, nullable=False)
    # Where the KOT goes (M08). `seed/menu.yaml` already names stations by code, which is why
    # `station.code` is immutable.
    station_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("station.id"), nullable=False
    )
    image_url: Mapped[str | None] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    category: Mapped[MenuCategory] = relationship(back_populates="items", lazy="raise")
    variants: Mapped[list[MenuItemVariant]] = relationship(
        back_populates="item", order_by="MenuItemVariant.seq", lazy="raise"
    )
    modifier_links: Mapped[list[MenuItemModifierGroup]] = relationship(
        back_populates="item", order_by="MenuItemModifierGroup.seq", lazy="raise"
    )


class MenuItemVariant(TimestampedUUIDMixin, Base):
    """Half, Full, Per piece. **Price lives here**, and so will the recipe (M04).

    The price is deliberately *mutable*. A menu price genuinely changes, and effective-dating it
    would double the tax machinery to answer a question `order_line` already answers: it copies the
    price at the moment the line is added (M07), so a reprice cannot rewrite a past bill, and price
    history is derivable from orders when M13 asks "did the reprice work?".

    `tax_group_id` points at a tax *group*, not a rate. The rate in force on a business date is
    resolved by date, so a GST change repoints nothing here (M03 spec decision 1).
    """

    __tablename__ = "menu_item_variant"
    __table_args__ = (
        UniqueConstraint("menu_item_id", "code", name="uq_menu_item_variant_code"),
        # M07: the target of order_line's tenant-safe composite foreign key.
        UniqueConstraint("id", "restaurant_id", name="uq_menu_item_variant_id_restaurant"),
        CheckConstraint("price >= 0", name="ck_menu_item_variant_price_not_negative"),
        CheckConstraint("prep_minutes > 0", name="ck_menu_item_variant_prep_minutes"),
        Index("ix_menu_item_variant_item", "menu_item_id", "is_active"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("menu_item.id"), nullable=False
    )
    # HALF | FULL | PIECE, and whatever else a restaurant sells by. Free text rather than an enum:
    # `library/dishes.yaml` already carries variant codes this product did not invent.
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # NUMERIC, never float (CLAUDE.md invariant 3).
    price: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    tax_group_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("tax_group.id"), nullable=False
    )
    # The *standard*. M08's `kot_ticket` carries actuals, and the gap between them is a real
    # operational metric — never overwrite one with the other (CLAUDE.md invariant 7's shape).
    prep_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    item: Mapped[MenuItem] = relationship(back_populates="variants", lazy="raise")


class ModifierGroup(TimestampedUUIDMixin, Base):
    """ "Choose spice level", "Add-ons". A question asked about a dish when it is ordered."""

    __tablename__ = "modifier_group"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "code", name="uq_modifier_group_restaurant_code"),
        CheckConstraint("min_select >= 0", name="ck_modifier_group_min_select"),
        CheckConstraint("max_select >= min_select", name="ck_modifier_group_max_ge_min"),
        # A required group that permits zero selections is a contradiction the UI cannot render:
        # it would show a mandatory question with no answer that satisfies it.
        CheckConstraint(
            "NOT is_required OR min_select >= 1", name="ck_modifier_group_required_needs_one"
        ),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    # Not in `docs/schema.md` §3, and needed: `seed/operations.yaml` attaches groups to categories
    # by code (SPICE_LEVEL, JAIN_PREF). Joining on the display name instead means renaming
    # "Spice level" silently breaks every attachment. Immutable after creation (M03 spec, defect 1).
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    min_select: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    max_select: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    modifiers: Mapped[list[Modifier]] = relationship(
        back_populates="group", order_by="Modifier.seq", lazy="raise"
    )


class Modifier(TimestampedUUIDMixin, Base):
    """One answer to a modifier group's question.

    `price_delta` may be negative — "no rice" can be a discount — which is why there is no
    non-negative check on it. **It models a price change and not a consumption change**: "extra
    cheese" is 40 g of cheese that no recipe currently accounts for. That link belongs to M04's
    `recipe`, whose owner CHECK has to grow a third column (M03 spec, inherited obligations).
    """

    __tablename__ = "modifier"
    __table_args__ = (
        UniqueConstraint("modifier_group_id", "code", name="uq_modifier_group_code"),
        # M07: the target of order_line_modifier's tenant-safe composite foreign key.
        UniqueConstraint("id", "restaurant_id", name="uq_modifier_id_restaurant"),
        Index("ix_modifier_group", "modifier_group_id", "is_active"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    modifier_group_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("modifier_group.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price_delta: Mapped[object] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0"
    )
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    group: Mapped[ModifierGroup] = relationship(back_populates="modifiers", lazy="raise")


class MenuItemModifierGroup(Base):
    """Which questions get asked about which dish.

    **No `restaurant_id`, deliberately** — see this module's docstring. Both parents are already
    tenant-scoped, and a third copy of the tenant is a third thing that can disagree with the other
    two. The service checks both sides belong to the caller before inserting, because the repository
    base class cannot do it for this one table.

    Not `TimestampedUUIDMixin`: the pair *is* the identity, so a surrogate id would be a second way
    to name the same row.
    """

    __tablename__ = "menu_item_modifier_group"

    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("menu_item.id"), primary_key=True
    )
    modifier_group_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("modifier_group.id"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    item: Mapped[MenuItem] = relationship(back_populates="modifier_links", lazy="raise")
    group: Mapped[ModifierGroup] = relationship(lazy="raise")
