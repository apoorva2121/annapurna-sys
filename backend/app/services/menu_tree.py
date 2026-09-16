"""Turning the loaded menu into what a caller may see.

Separate from `MenuService` because it is the one part of the menu surface with **two audiences**.
ADR 0009 splits staff and guest into two applications, and a diner may not see everything a waiter
sees: not the kitchen station a dish routes to (which, across a whole menu, describes how the
kitchen is laid out), not `prep_minutes` (an internal standard a guest would hold the restaurant
to), not internal codes, and never an inactive row.

**Filtering happens here, in memory, not in the query.** The repository loads the tree in a fixed
number of statements; adding `is_active` predicates at three levels would either multiply the
queries or make the loader take a flag it then has to thread through every relationship. A menu is
hundreds of rows, not millions, so loading and discarding is cheap — and it keeps the one property
that actually matters, which is that the query count does not grow with the menu.

The guest view is built now and no guest screen ships in M03 (spec decision 3). Retrofitting it
later would mean re-deciding what a diner may see at a point when something already depends on the
answer; deciding it once, here, costs almost nothing.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.models.menu import MenuCategory, MenuItem, ModifierGroup
from app.schemas.guest import (
    GuestCategory,
    GuestItem,
    GuestMenuResponse,
    GuestModifier,
    GuestModifierGroup,
    GuestVariant,
)
from app.schemas.menu import (
    MenuItemVariantResponse,
    MenuTreeResponse,
    ModifierGroupResponse,
    StaffCategory,
    StaffItem,
)


def _guest_groups_of(item: MenuItem) -> list[GuestModifierGroup]:
    """The same groups, in the shape a diner may see.

    **Built separately from `_groups_of` on purpose.** ADR 0009: "some serialisation logic is
    duplicated between staff and guest schemas — that duplication is the feature", and this is the
    case that proves it. While the guest tree reused the staff builder, every modifier's `code` and
    `is_active` travelled with it, three levels below the field anybody was checking.
    """
    out: list[GuestModifierGroup] = []
    for link in item.modifier_links:
        group: ModifierGroup = link.group
        if not group.is_active:
            continue
        out.append(
            GuestModifierGroup(
                id=group.id,
                name=group.name,
                min_select=group.min_select,
                max_select=group.max_select,
                is_required=group.is_required,
                modifiers=[
                    GuestModifier(
                        id=modifier.id, name=modifier.name, price_delta=modifier.price_delta
                    )
                    for modifier in group.modifiers
                    if modifier.is_active
                ],
            )
        )
    return out


def _groups_of(item: MenuItem, *, include_inactive: bool) -> list[ModifierGroupResponse]:
    """The modifier groups attached to a dish, in attachment order.

    An inactive group is dropped from a guest's view even though the link survives: deactivating
    "Add-ons" should stop it being offered without anyone having to unpick it from ninety dishes.
    """
    out: list[ModifierGroupResponse] = []
    for link in item.modifier_links:
        group: ModifierGroup = link.group
        if not include_inactive and not group.is_active:
            continue
        modifiers = [
            modifier for modifier in group.modifiers if include_inactive or modifier.is_active
        ]
        out.append(
            ModifierGroupResponse.model_validate(group).model_copy(update={"modifiers": modifiers})
        )
    return out


def staff_tree(
    version: int, categories: Sequence[MenuCategory], *, include_inactive: bool
) -> MenuTreeResponse:
    """Everything, for anyone holding `menu.view`.

    **The flag has to reach here, not only the query.** The repository filters *categories* by
    `is_active`, because that is what its `WHERE` can reach without multiplying the statements — the
    items and variants hanging off them are not filtered by the loader at all. A first version of
    this function ignored the flag entirely and returned deactivated dishes to a waiter, which is
    acceptance criterion 4 and was caught by `test_the_tree_hides_deactivated_dishes_by_default`
    rather than by review.
    """
    out: list[StaffCategory] = []
    for category in categories:
        items: list[StaffItem] = []
        for item in category.items:
            if not include_inactive and not item.is_active:
                continue
            items.append(
                StaffItem(
                    id=item.id,
                    code=item.code,
                    name=item.name,
                    description=item.description,
                    food_type=item.food_type,
                    allergen_statement=item.allergen_statement,
                    calories_kcal=item.calories_kcal,
                    serving_size=item.serving_size,
                    station_id=item.station_id,
                    image_url=item.image_url,
                    is_active=item.is_active,
                    variants=[
                        MenuItemVariantResponse.model_validate(variant)
                        for variant in item.variants
                        if include_inactive or variant.is_active
                    ],
                    modifier_groups=_groups_of(item, include_inactive=include_inactive),
                )
            )
        out.append(
            StaffCategory(
                id=category.id,
                code=category.code,
                name=category.name,
                is_active=category.is_active,
                items=items,
            )
        )
    return MenuTreeResponse(version=version, categories=out)


def guest_tree(version: int, categories: Sequence[MenuCategory]) -> GuestMenuResponse:
    """What a diner may see. Active rows only, and no internal fields at all.

    An empty category is dropped rather than rendered: a section heading with nothing under it tells
    a diner the kitchen has run out, which may not be true and is not ours to imply.
    """
    out: list[GuestCategory] = []
    for category in categories:
        if not category.is_active:
            continue
        items: list[GuestItem] = []
        for item in category.items:
            if not item.is_active:
                continue
            variants = [
                # No `code`: `FULL` is a join key, not a label, and M03's own test file says so.
                GuestVariant(id=v.id, name=v.name, price=v.price)
                for v in item.variants
                if v.is_active
            ]
            if not variants:
                # Nothing orderable. The service refuses to create this state, but a menu loaded
                # mid-edit can still show it, and a dish a diner cannot order is worse than absent.
                continue
            items.append(
                GuestItem(
                    id=item.id,
                    name=item.name,
                    description=item.description,
                    food_type=item.food_type,
                    allergen_statement=item.allergen_statement,
                    calories_kcal=item.calories_kcal,
                    serving_size=item.serving_size,
                    image_url=item.image_url,
                    variants=variants,
                    modifier_groups=_guest_groups_of(item),
                )
            )
        if not items:
            continue
        out.append(GuestCategory(id=category.id, name=category.name, items=items))
    return GuestMenuResponse(version=version, categories=out)
