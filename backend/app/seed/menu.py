"""Seeds M03's menu: categories, dishes, variants, modifier groups and their attachments.

The data has been in `seed/menu.yaml` since M00 — 32 dishes, 36 variants, six categories — and
validated by `seed/validate.py` ever since, but nothing loaded it because the tables did not exist
until now. `make seed` has been producing a restaurant with staff, a floor and no menu, which is a
restaurant nobody can order from and a module nobody can demonstrate. M02's review round found the
same thing about the floor plan; this is that lesson applied one module early.

**Two files, and the join between them is a code.** `menu.yaml` holds categories and dishes;
`operations.yaml` holds modifier groups and attaches them *by category* — `{categories: [MAIN_VEG],
groups: [SPICE_LEVEL]}`. The schema attaches per item, because one dish in a category can
legitimately opt out. So the loader expands the shorthand: every active dish in a named category
gets the named groups. That expansion is the reason `menu_category.code` and `modifier_group.code`
exist at all (M03 spec, defects 1 and 2).

**Prices come from the seed and not from the library.** `library/dishes.yaml` deliberately carries
no price — prices are per-restaurant — while `seed/menu.yaml` is one specific restaurant with a
specific price list and a golden food-cost figure that depends on it. The library is what M04 will
match a *new* restaurant's menu against; this is the demo restaurant's own menu.

**Get-or-create by natural key**, like every other seeder here: `make seed` is run casually and
repeatedly, and the failure to design against is not "it crashed" but "it silently made a second
Butter Chicken".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.menu import (
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    MenuItemVariant,
    Modifier,
    ModifierGroup,
)
from app.models.setup import Station, TaxGroup
from app.models.tenancy import Restaurant
from app.seed.loader import find_seed_directory

logger = logging.getLogger(__name__)

_MENU_FILE = "menu.yaml"
_OPERATIONS_FILE = "operations.yaml"

# The restaurant `menu.yaml` describes — the same one `operations.yaml` gives a floor to.
_FOR_RESTAURANT = "SG_KOREGAON"


# `seed/menu.yaml` writes `gst: 5` on a variant, meaning "the 5% group". The tax group codes live in
# `operations.yaml` as GST5 and GST18, so the two are joined by formatting rather than by a mapping
# nobody would keep in step. A rate the seed names but does not define fails loudly below.
def _tax_code(gst: Any) -> str:
    return f"GST{int(gst)}"


class MissingSeedRestaurantError(RuntimeError):
    """`menu.yaml` describes a restaurant the identity seed did not create."""


class MissingSeedReferenceError(RuntimeError):
    """The menu names a station, category or tax group that the setup seed did not create."""


@dataclass(frozen=True, slots=True)
class MenuSummary:
    categories_created: int = 0
    items_created: int = 0
    variants_created: int = 0
    modifier_groups_created: int = 0
    attachments_created: int = 0

    @property
    def created_nothing(self) -> bool:
        return not any(
            (
                self.categories_created,
                self.items_created,
                self.variants_created,
                self.modifier_groups_created,
                self.attachments_created,
            )
        )


@dataclass
class _Counts:
    categories: int = 0
    items: int = 0
    variants: int = 0
    groups: int = 0
    attachments: int = 0
    by_category: dict[str, list[MenuItem]] = field(default_factory=dict)


def load_menu() -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load(
        (find_seed_directory() / _MENU_FILE).read_text(encoding="utf-8")
    )
    return parsed


def load_operations() -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load(
        (find_seed_directory() / _OPERATIONS_FILE).read_text(encoding="utf-8")
    )
    return parsed


async def seed_menu(
    session: AsyncSession,
    menu: dict[str, Any] | None = None,
    operations: dict[str, Any] | None = None,
) -> MenuSummary:
    """Create the demo menu. Safe to run repeatedly.

    Does not commit — the caller owns the transaction, which is what lets the test suite seed inside
    a transaction it then rolls back.
    """
    menu = menu or load_menu()
    operations = operations or load_operations()

    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == _FOR_RESTAURANT))
    if restaurant is None:
        raise MissingSeedRestaurantError(
            f"{_FOR_RESTAURANT} does not exist. Seed identity first — menu.yaml describes that "
            "restaurant's menu and cannot stand on its own."
        )

    stations = await _by_code(session, Station, restaurant.id)
    taxes = await _by_code(session, TaxGroup, restaurant.id)
    if not stations or not taxes:
        raise MissingSeedReferenceError(
            "The menu needs stations and tax groups. Seed setup first — every dish routes to a "
            "station and every variant is taxed."
        )

    counts = _Counts()
    categories = await _categories(session, restaurant.id, menu.get("categories", []), counts)
    await _items(session, restaurant.id, menu.get("items", []), categories, stations, taxes, counts)
    groups = await _modifier_groups(
        session, restaurant.id, operations.get("modifier_groups", []), counts
    )
    await _attachments(session, operations.get("modifier_attachments", []), groups, counts)

    await session.flush()
    summary = MenuSummary(
        categories_created=counts.categories,
        items_created=counts.items,
        variants_created=counts.variants,
        modifier_groups_created=counts.groups,
        attachments_created=counts.attachments,
    )
    logger.info("seed.menu.complete", extra={"summary": summary})
    return summary


async def _by_code(session: AsyncSession, model: Any, restaurant_id: Any) -> dict[str, Any]:
    rows = await session.scalars(select(model).where(model.restaurant_id == restaurant_id))
    return {row.code: row for row in rows}


async def _categories(
    session: AsyncSession, restaurant_id: Any, records: list[dict[str, Any]], counts: _Counts
) -> dict[str, MenuCategory]:
    existing = await _by_code(session, MenuCategory, restaurant_id)
    for record in records:
        code = str(record["code"])
        if code in existing:
            continue
        category = MenuCategory(
            restaurant_id=restaurant_id,
            code=code,
            name=str(record["name"]),
            # YAML counts from 1 because a human wrote it; `seq` counts from 0 because the reorder
            # arithmetic does. The same off-by-one the M02 seeder handles, for the same reason.
            seq=int(record["seq"]) - 1,
            is_active=True,
        )
        session.add(category)
        existing[code] = category
        counts.categories += 1
    await session.flush()
    return existing


async def _items(
    session: AsyncSession,
    restaurant_id: Any,
    records: list[dict[str, Any]],
    categories: dict[str, MenuCategory],
    stations: dict[str, Station],
    taxes: dict[str, TaxGroup],
    counts: _Counts,
) -> None:
    existing = await _by_code(session, MenuItem, restaurant_id)
    for seq, record in enumerate(records):
        code = str(record["code"])
        category_code = str(record["category"])
        counts.by_category.setdefault(category_code, [])

        item = existing.get(code)
        if item is None:
            category = categories.get(category_code)
            station = stations.get(str(record["station"]))
            if category is None or station is None:
                raise MissingSeedReferenceError(
                    f"{code} names category {category_code!r} and station "
                    f"{record['station']!r}; one of them was not seeded."
                )
            item = MenuItem(
                restaurant_id=restaurant_id,
                menu_category_id=category.id,
                code=code,
                name=str(record["name"]),
                food_type=str(record["food_type"]),
                station_id=station.id,
                seq=seq,
                is_active=True,
            )
            session.add(item)
            await session.flush()
            existing[code] = item
            counts.items += 1
        counts.by_category[category_code].append(item)

        await _variants(session, restaurant_id, item, record.get("variants", []), taxes, counts)


async def _variants(
    session: AsyncSession,
    restaurant_id: Any,
    item: MenuItem,
    records: list[dict[str, Any]],
    taxes: dict[str, TaxGroup],
    counts: _Counts,
) -> None:
    present = {
        row.code
        for row in await session.scalars(
            select(MenuItemVariant).where(MenuItemVariant.menu_item_id == item.id)
        )
    }
    for seq, record in enumerate(records):
        code = str(record["code"])
        if code in present:
            continue
        tax_code = _tax_code(record["gst"])
        tax = taxes.get(tax_code)
        if tax is None:
            raise MissingSeedReferenceError(
                f"{item.code}/{code} is taxed at {record['gst']}%, which is tax group "
                f"{tax_code!r} — not present in operations.yaml."
            )
        session.add(
            MenuItemVariant(
                restaurant_id=restaurant_id,
                menu_item_id=item.id,
                code=code,
                name=str(record["name"]),
                # `Decimal(str(...))` and never `Decimal(float)`: 470.5 as a float is
                # 470.50000000000001, and that is what would be stored (CLAUDE.md invariant 3).
                price=Decimal(str(record["price"])),
                tax_group_id=tax.id,
                prep_minutes=int(record["prep_minutes"]),
                seq=seq,
                is_active=True,
            )
        )
        counts.variants += 1


async def _modifier_groups(
    session: AsyncSession, restaurant_id: Any, records: list[dict[str, Any]], counts: _Counts
) -> dict[str, ModifierGroup]:
    existing = await _by_code(session, ModifierGroup, restaurant_id)
    for record in records:
        code = str(record["code"])
        if code in existing:
            continue
        group = ModifierGroup(
            restaurant_id=restaurant_id,
            code=code,
            name=str(record["name"]),
            min_select=int(record.get("min_select", 0)),
            max_select=int(record.get("max_select", 1)),
            is_required=bool(record.get("is_required", False)),
            is_active=True,
        )
        session.add(group)
        await session.flush()
        existing[code] = group
        counts.groups += 1
        for seq, modifier in enumerate(record.get("modifiers", [])):
            name = str(modifier["name"])
            session.add(
                Modifier(
                    restaurant_id=restaurant_id,
                    modifier_group_id=group.id,
                    # `operations.yaml` gives modifiers a name and no code, because a person writing
                    # "Mild" does not think in codes. One is derived so the row has a stable key —
                    # `uq_modifier_group_code` needs one, and so will M07's order lines.
                    code=_slug(name),
                    name=name,
                    price_delta=Decimal(str(modifier.get("price_delta", 0))),
                    seq=seq,
                    is_active=True,
                )
            )
    await session.flush()
    return existing


async def _attachments(
    session: AsyncSession,
    records: list[dict[str, Any]],
    groups: dict[str, ModifierGroup],
    counts: _Counts,
) -> None:
    """Expand `{categories: [...], groups: [...]}` into one row per dish.

    The YAML says "all main courses get a spice level" because that is how an owner describes a
    menu. The table stores it per dish because one dish in a category can opt out. This is where
    the first becomes the second — at load time, not as a stored rule that would then need
    reconciling against every exception forever.
    """
    for record in records:
        wanted = [groups[code] for code in record.get("groups", []) if code in groups]
        for category_code in record.get("categories", []):
            for item in counts.by_category.get(category_code, []):
                present = {
                    link.modifier_group_id
                    for link in await session.scalars(
                        select(MenuItemModifierGroup).where(
                            MenuItemModifierGroup.menu_item_id == item.id
                        )
                    )
                }
                for seq, group in enumerate(wanted):
                    if group.id in present:
                        continue
                    session.add(
                        MenuItemModifierGroup(
                            menu_item_id=item.id,
                            modifier_group_id=group.id,
                            seq=len(present) + seq,
                        )
                    )
                    counts.attachments += 1


def _slug(name: str) -> str:
    """`"Jain (no onion/garlic)"` → `JAIN_NO_ONION_GARLIC`. Stable for a given name, which is all a
    natural key needs to be."""
    out = [character if character.isalnum() else "_" for character in name.upper()]
    collapsed = "_".join(part for part in "".join(out).split("_") if part)
    return collapsed[:32] or "OPTION"
