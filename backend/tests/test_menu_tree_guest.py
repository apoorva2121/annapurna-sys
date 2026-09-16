"""The guest view of the menu, which ships with no screen and must still be right.

M03 spec decision 3: build the persona filter now, ship no guest screen. The reasoning was that
retrofitting it later means re-deciding what a diner may see at a point when something already
depends on the answer. The cost of deciding early is that the code exists untested unless something
tests it — which is this file.

What a diner may **not** see, and why each one matters:

- **the kitchen station.** One dish's station is harmless; a whole menu's stations describe how the
  kitchen is laid out and how many lines it runs.
- **`prep_minutes`.** An internal standard. A guest shown "11 minutes" will hold the restaurant to
  it, and M08 measures the actual against it precisely because the two differ.
- **internal codes.** `BUTTER_CHICKEN` is a join key, not a label.
- **anything inactive.** A dish that cannot be ordered must not appear at all.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.menu import (
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    MenuItemVariant,
    Modifier,
    ModifierGroup,
)
from app.services.menu_tree import guest_tree, staff_tree


def _variant(*, code: str = "FULL", active: bool = True) -> MenuItemVariant:
    return MenuItemVariant(
        id=uuid.uuid4(),
        restaurant_id=uuid.uuid4(),
        menu_item_id=uuid.uuid4(),
        code=code,
        name=code.title(),
        price=Decimal("470.00"),
        tax_group_id=uuid.uuid4(),
        prep_minutes=11,
        seq=0,
        is_active=active,
    )


def _group(*, active: bool = True, modifier_active: bool = True) -> ModifierGroup:
    group = ModifierGroup(
        id=uuid.uuid4(),
        restaurant_id=uuid.uuid4(),
        code="SPICE_LEVEL",
        name="Spice level",
        min_select=0,
        max_select=1,
        is_required=False,
        is_active=active,
    )
    group.modifiers = [
        Modifier(
            id=uuid.uuid4(),
            restaurant_id=group.restaurant_id,
            modifier_group_id=group.id,
            code="MILD",
            name="Mild",
            price_delta=Decimal("0.00"),
            seq=0,
            is_active=modifier_active,
        )
    ]
    return group


def _item(
    *,
    active: bool = True,
    variants: list[MenuItemVariant] | None = None,
    groups: list[ModifierGroup] | None = None,
) -> MenuItem:
    item = MenuItem(
        id=uuid.uuid4(),
        restaurant_id=uuid.uuid4(),
        menu_category_id=uuid.uuid4(),
        code="BUTTER_CHICKEN",
        name="Butter Chicken",
        description="Creamy tomato gravy",
        food_type="non_veg",
        station_id=uuid.uuid4(),
        image_url=None,
        seq=0,
        is_active=active,
    )
    item.variants = variants if variants is not None else [_variant()]
    item.modifier_links = [
        MenuItemModifierGroup(menu_item_id=item.id, modifier_group_id=group.id, seq=seq)
        for seq, group in enumerate(groups or [])
    ]
    for link, group in zip(item.modifier_links, groups or [], strict=True):
        link.group = group
    return item


def _category(*, active: bool = True, items: list[MenuItem] | None = None) -> MenuCategory:
    category = MenuCategory(
        id=uuid.uuid4(),
        restaurant_id=uuid.uuid4(),
        code="MAIN_NONVEG",
        name="Non-Veg Main Course",
        seq=0,
        is_active=active,
    )
    category.items = items if items is not None else [_item()]
    return category


class TestWhatAGuestMayNotSee:
    def test_a_guest_sees_no_kitchen_station(self) -> None:
        """One dish's station is harmless. A whole menu's stations describe the kitchen."""
        tree = guest_tree(3, [_category()])

        dish = tree.categories[0].items[0]
        assert not hasattr(dish, "station_id")

    def test_a_guest_sees_no_prep_time(self) -> None:
        """An internal standard. A diner shown "11 minutes" will hold the restaurant to it."""
        tree = guest_tree(3, [_category()])

        variant = tree.categories[0].items[0].variants[0]
        assert not hasattr(variant, "prep_minutes")

    def test_a_guest_sees_no_internal_code_on_a_dish(self) -> None:
        tree = guest_tree(3, [_category()])

        assert not hasattr(tree.categories[0].items[0], "code")

    def test_a_deactivated_dish_is_absent_entirely(self) -> None:
        tree = guest_tree(3, [_category(items=[_item(active=False)])])

        assert tree.categories == []

    def test_a_deactivated_category_is_absent_entirely(self) -> None:
        tree = guest_tree(3, [_category(active=False)])

        assert tree.categories == []

    def test_a_dish_with_no_orderable_variant_is_absent(self) -> None:
        """The service refuses to create this state, but a menu read mid-edit can still show it —
        and a dish a diner cannot order is worse than one that is not there."""
        tree = guest_tree(3, [_category(items=[_item(variants=[_variant(active=False)])])])

        assert tree.categories == []

    def test_an_empty_category_is_dropped_rather_than_rendered(self) -> None:
        """A section heading with nothing under it tells a diner the kitchen has run out, which may
        not be true and is not ours to imply."""
        tree = guest_tree(3, [_category(items=[]), _category()])

        assert len(tree.categories) == 1


class TestWhatAGuestDoesSee:
    def test_the_price_and_the_food_type_survive(self) -> None:
        """The two things a diner actually reads. `food_type` is legally required on the menu."""
        tree = guest_tree(7, [_category()])

        dish = tree.categories[0].items[0]
        assert dish.name == "Butter Chicken"
        assert dish.food_type == "non_veg"
        assert dish.variants[0].price == Decimal("470.00")
        assert tree.version == 7

    def test_an_inactive_modifier_group_is_hidden_from_a_guest(self) -> None:
        """Deactivating "Add-ons" should stop it being offered without anyone unpicking it from
        ninety dishes."""
        tree = guest_tree(1, [_category(items=[_item(groups=[_group(active=False)])])])

        assert tree.categories[0].items[0].modifier_groups == []

    def test_an_inactive_option_inside_a_live_group_is_hidden(self) -> None:
        tree = guest_tree(1, [_category(items=[_item(groups=[_group(modifier_active=False)])])])

        groups = tree.categories[0].items[0].modifier_groups
        assert len(groups) == 1
        assert groups[0].modifiers == []


class TestTheStaffViewIsDifferent:
    def test_staff_see_the_station_and_the_prep_time(self) -> None:
        tree = staff_tree(1, [_category()], include_inactive=True)

        dish = tree.categories[0].items[0]
        assert dish.station_id is not None
        assert dish.variants[0].prep_minutes == 11
        assert dish.code == "BUTTER_CHICKEN"

    def test_staff_keep_inactive_rows_when_they_ask_for_them(self) -> None:
        tree = staff_tree(1, [_category(items=[_item(active=False)])], include_inactive=True)

        assert len(tree.categories[0].items) == 1
        assert tree.categories[0].items[0].is_active is False


# --------------------------------------------------------------------------- M10 regression
#
# Written before the fix, per CLAUDE.md. The tests above assert about the fields somebody thought to
# look at — `test_a_guest_sees_no_internal_code_on_a_dish` checks the *dish* — and two internal
# codes were reaching a guest anyway, three levels down. Nothing shipped them, because there was no
# guest route until M10; routing the tree is exactly what would have.


def _fields_everywhere(model: object, seen: set[type] | None = None) -> set[str]:
    """Every field name reachable from a model, at any depth.

    A rule that walks the graph does not have the failure mode a hand-written list has: it does not
    need somebody to think of `code` on a modifier inside a group inside an item.
    """
    from typing import get_args

    from pydantic import BaseModel

    seen = set() if seen is None else seen
    if not isinstance(model, type) or not issubclass(model, BaseModel) or model in seen:
        return set()
    seen.add(model)

    names: set[str] = set(model.model_fields)

    def walk(annotation: object) -> None:
        names.update(_fields_everywhere(annotation, seen))
        for argument in get_args(annotation):
            walk(argument)

    for field in model.model_fields.values():
        walk(field.annotation)
    return names


def test_no_internal_code_reaches_a_guest_at_any_depth() -> None:
    """`BUTTER_CHICKEN` is a join key, not a label — and so is `EXTRA_CHEESE`.

    `GuestItem` used to carry the *staff* `ModifierGroupResponse`, which has `code` and `is_active`
    on the group and on every modifier inside it, and `GuestVariant` carried a `code` of its own. A
    menu that carefully withheld the dish's code handed over the modifier's.
    """
    from app.schemas.guest import GuestMenuResponse

    reachable = _fields_everywhere(GuestMenuResponse)

    assert "code" not in reachable
    assert "is_active" not in reachable


def test_a_guest_still_gets_the_modifier_choices_themselves() -> None:
    """The fix removes the codes, not the feature. A guest still sees what they may choose, what it
    costs and how many they may pick — which is everything needed to order."""
    from app.schemas.guest import GuestModifier, GuestModifierGroup

    assert set(GuestModifierGroup.model_fields) == {
        "id",
        "name",
        "min_select",
        "max_select",
        "is_required",
        "modifiers",
    }
    assert set(GuestModifier.model_fields) == {"id", "name", "price_delta"}
