"""Seeds M04's stock items and recipes — and with them, the first food cost this product computes.

`seed/ingredients.yaml` (61 rows), `seed/preparations.yaml` (11) and the recipes embedded in
`seed/menu.yaml` have all been validated by `seed/validate.py` since M00 with nothing to load them
into. After this, `make seed` produces a restaurant whose Butter Chicken costs **₹126.70** through
the API — the same figure the validator prints, and the first moment this product does the thing it
is for.

**Order matters and is enforced rather than assumed.** Ingredients first, because preparations
consume them; preparations next, because dishes consume those; recipes last. A preparation's recipe
may reference another preparation (`PREP_BIRISTA` inside `PREP_YELLOW`), so preparation *rows* are
all created before any preparation *recipe* is.

**Prices are per base unit and `current_unit_cost` holds them.** `seed/ingredients.yaml` gives
`price: 0.280` meaning ₹0.28 per gram — already in base units, because the seed was written against
invariant 5. `purchase_to_base` is derived from the base unit rather than stored in the YAML: a
gram-based ingredient is bought by the kilo, an ml-based one by the litre, a counted one by the
piece. That is an assumption, it is stated here, and a restaurant that buys paneer by the 200 g
packet corrects it on the ingredient screen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.tenancy import TenantScope
from app.models.menu import MenuItem, MenuItemVariant
from app.models.setup import Station
from app.models.stock import (
    IngredientProfile,
    PreparationProfile,
    Recipe,
    RecipeLine,
    StockItem,
)
from app.models.tenancy import Restaurant
from app.repositories.stock import CostingRepository
from app.seed.loader import find_seed_directory
from app.services.costing import CostEngine, Line

logger = logging.getLogger(__name__)

_FOR_RESTAURANT = "SG_KOREGAON"

# How much of a base unit one purchase unit holds. Stated rather than guessed per row: a gram-based
# ingredient is bought by the kilo, an ml-based one by the litre, a counted one one at a time.
_PURCHASE = {
    "g": ("kg", Decimal("1000")),
    "ml": ("litre", Decimal("1000")),
    "unit": ("piece", Decimal("1")),
}


class MissingSeedRestaurantError(RuntimeError):
    """The identity seed has not run."""


class MissingSeedReferenceError(RuntimeError):
    """A recipe names something that was not seeded."""


@dataclass(frozen=True, slots=True)
class StockSummary:
    ingredients_created: int = 0
    preparations_created: int = 0
    recipes_created: int = 0

    @property
    def created_nothing(self) -> bool:
        return not any((self.ingredients_created, self.preparations_created, self.recipes_created))


def _load(name: str) -> Any:
    return yaml.safe_load((find_seed_directory() / name).read_text(encoding="utf-8"))


async def seed_stock(
    session: AsyncSession,
    ingredients: list[dict[str, Any]] | None = None,
    preparations: list[dict[str, Any]] | None = None,
    menu: dict[str, Any] | None = None,
) -> StockSummary:
    """Create the demo ingredients, preparations and recipes. Safe to run repeatedly.

    Does not commit — the caller owns the transaction, which is what lets the test suite seed inside
    one it then rolls back.
    """
    ingredients = (
        ingredients if ingredients is not None else _load("ingredients.yaml")["ingredients"]
    )
    preparations = (
        preparations if preparations is not None else _load("preparations.yaml")["preparations"]
    )
    menu = menu if menu is not None else _load("menu.yaml")

    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == _FOR_RESTAURANT))
    if restaurant is None:
        raise MissingSeedRestaurantError(
            f"{_FOR_RESTAURANT} does not exist. Seed identity first — the recipes describe that "
            "restaurant's kitchen and cannot stand on their own."
        )

    stations = {
        station.code: station
        for station in await session.scalars(
            select(Station).where(Station.restaurant_id == restaurant.id)
        )
    }
    if not stations:
        raise MissingSeedReferenceError("Every preparation is made at a station. Seed setup first.")

    items = {
        item.code: item
        for item in await session.scalars(
            select(StockItem).where(StockItem.restaurant_id == restaurant.id)
        )
    }

    created_ingredients = await _ingredients(session, restaurant.id, ingredients, items)
    created_preparations = await _preparations(
        session, restaurant.id, preparations, items, stations
    )
    created_recipes = await _recipes(session, restaurant.id, preparations, menu, items)
    await session.flush()
    await _freeze_costs(session, restaurant.id)

    await session.flush()
    summary = StockSummary(
        ingredients_created=created_ingredients,
        preparations_created=created_preparations,
        recipes_created=created_recipes,
    )
    logger.info("seed.stock.complete", extra={"summary": summary})
    return summary


async def _ingredients(
    session: AsyncSession,
    restaurant_id: Any,
    records: list[dict[str, Any]],
    items: dict[str, StockItem],
) -> int:
    created = 0
    for record in records:
        code = str(record["code"])
        if code in items:
            continue
        base_unit = str(record["base_unit"])
        purchase_unit, purchase_to_base = _PURCHASE[base_unit]
        item = StockItem(
            restaurant_id=restaurant_id,
            kind="ingredient",
            code=code,
            name=str(record["name"]),
            base_unit=base_unit,
            category=str(record["category"]),
            storage_type=str(record["storage"]),
            # `Decimal(str(...))` and never `Decimal(float)`: 0.28 as a float is
            # 0.2800000000000000266, and the golden figures are to the paisa.
            current_unit_cost=Decimal(str(record["price"])),
            is_active=True,
        )
        session.add(item)
        await session.flush()
        session.add(
            IngredientProfile(
                stock_item_id=item.id,
                purchase_unit=purchase_unit,
                purchase_to_base=purchase_to_base,
                yield_factor=Decimal(str(record["yield_factor"])),
                shelf_life_days=int(record["shelf_life_days"]),
            )
        )
        items[code] = item
        created += 1
    return created


async def _preparations(
    session: AsyncSession,
    restaurant_id: Any,
    records: list[dict[str, Any]],
    items: dict[str, StockItem],
    stations: dict[str, Station],
) -> int:
    """Every preparation *row*, before any preparation *recipe*.

    `PREP_YELLOW` consumes `PREP_BIRISTA`, so a pass that created each row and its recipe together
    would fail on whichever came first in the file.
    """
    created = 0
    for record in records:
        code = str(record["code"])
        if code in items:
            continue
        station = stations.get(str(record["station"]))
        if station is None:
            raise MissingSeedReferenceError(
                f"{code} is made at station {record['station']!r}, which was not seeded."
            )
        item = StockItem(
            restaurant_id=restaurant_id,
            kind="preparation",
            code=code,
            name=str(record["name"]),
            base_unit=str(record["yield_unit"]),
            category=None,
            storage_type="chilled",
            # Filled in by the recipe pass below, once its inputs exist and can be costed.
            current_unit_cost=Decimal(0),
            is_active=True,
        )
        session.add(item)
        await session.flush()
        session.add(
            PreparationProfile(
                stock_item_id=item.id,
                batch_yield=Decimal(str(record["batch_yield"])),
                shelf_life_hours=int(record["shelf_life_hours"]),
                station_id=station.id,
                prep_minutes=int(record["prep_minutes"]),
            )
        )
        items[code] = item
        created += 1
    return created


async def _recipes(
    session: AsyncSession,
    restaurant_id: Any,
    preparations: list[dict[str, Any]],
    menu: dict[str, Any],
    items: dict[str, StockItem],
) -> int:
    """Preparation recipes, then dish recipes.

    `source="seeded"` and `confirmed_at` set: this is a real restaurant's own recipe list, not a
    proposal matched from the starter library. The distinction is what `library/PROVENANCE.md`
    exists for, and a seeded recipe that looked unconfirmed would make the demo's cost screen hedge
    about numbers it should state plainly.
    """
    now = datetime.now(UTC)
    created = 0

    existing = {
        recipe.produces_stock_item_id
        for recipe in await session.scalars(
            select(Recipe).where(
                Recipe.restaurant_id == restaurant_id, Recipe.produces_stock_item_id.is_not(None)
            )
        )
    }
    for record in preparations:
        item = items[str(record["code"])]
        if item.id in existing:
            continue
        recipe = Recipe(
            restaurant_id=restaurant_id,
            produces_stock_item_id=item.id,
            version=1,
            is_current=True,
            effective_from=now,
            source="seeded",
            confirmed_at=now,
        )
        session.add(recipe)
        await session.flush()
        _add_lines(session, recipe, record["lines"], items, "qty", str(record["code"]))
        created += 1

    variants = {
        (variant.menu_item_id, variant.code): variant
        for variant in await session.scalars(
            select(MenuItemVariant).where(MenuItemVariant.restaurant_id == restaurant_id)
        )
    }
    menu_items = {
        item.code: item
        for item in await session.scalars(
            select(MenuItem).where(MenuItem.restaurant_id == restaurant_id)
        )
    }
    costed = {
        recipe.menu_item_variant_id
        for recipe in await session.scalars(
            select(Recipe).where(
                Recipe.restaurant_id == restaurant_id, Recipe.menu_item_variant_id.is_not(None)
            )
        )
    }

    for record in menu["items"]:
        menu_item = menu_items.get(str(record["code"]))
        if menu_item is None:
            raise MissingSeedReferenceError(
                f"{record['code']} has a recipe but no menu item. Seed the menu first."
            )
        for variant_record in record["variants"]:
            variant = variants.get((menu_item.id, str(variant_record["code"])))
            if variant is None or variant.id in costed:
                continue
            recipe = Recipe(
                restaurant_id=restaurant_id,
                menu_item_variant_id=variant.id,
                version=1,
                is_current=True,
                effective_from=now,
                source="seeded",
                confirmed_at=now,
            )
            session.add(recipe)
            await session.flush()
            _add_lines(
                session,
                recipe,
                variant_record["recipe"],
                items,
                "qty",
                f"{record['code']}/{variant_record['code']}",
            )
            created += 1

    return created


async def _freeze_costs(session: AsyncSession, restaurant_id: Any) -> None:
    """Compute every cost once the graph is complete, and store it.

    Two things are written: `recipe.unit_cost`, frozen per version because a version is immutable
    and what it cost when it became current is a fact (finding X8); and a preparation's
    `current_unit_cost`, which is the cache a screen reads for "roughly, now".

    It runs *after* every row exists, not per row, because a preparation cannot be costed until the
    preparations it consumes have their recipes — `PREP_BIRISTA` inside `PREP_YELLOW` is exactly
    that case, and a per-row pass would have costed yellow gravy at zero.
    """
    # A real scope, not a stand-in: `CostingRepository` filters on `restaurant_id` and the
    # organization is carried so nothing here can widen it later. The restaurant's own
    # `organization_id` is the honest value.
    restaurant = await session.get(Restaurant, restaurant_id)
    if restaurant is None:  # pragma: no cover - seed_stock verified this above
        raise MissingSeedRestaurantError("The restaurant vanished between seeding and costing.")
    costing = CostingRepository(
        session,
        TenantScope(organization_id=restaurant.organization_id, restaurant_id=restaurant.id),
    )
    components, prep_lines = await costing.load_snapshot()
    engine = CostEngine(components, prep_lines)

    recipes = (
        await session.scalars(
            select(Recipe)
            .options(selectinload(Recipe.lines))
            .where(Recipe.restaurant_id == restaurant_id, Recipe.is_current.is_(True))
        )
    ).all()
    for recipe in recipes:
        lines = [
            Line(component_id=line.component_id, quantity=Decimal(str(line.quantity)))
            for line in recipe.lines
        ]
        cost = engine.cost_of(lines)
        if recipe.produces_stock_item_id is not None:
            # A preparation's unit cost is what one base unit of its *yield* costs, so the batch
            # total divides by the batch yield. That is the number every consuming recipe multiplies
            # by, and storing the batch total instead would overstate every dish using it.
            unit = engine.unit_cost(recipe.produces_stock_item_id)
            recipe.unit_cost = unit
            item = await session.get(StockItem, recipe.produces_stock_item_id)
            if item is not None:
                item.current_unit_cost = unit
        else:
            recipe.unit_cost = cost.total


def _add_lines(
    session: AsyncSession,
    recipe: Recipe,
    records: list[dict[str, Any]],
    items: dict[str, StockItem],
    quantity_key: str,
    owner: str,
) -> None:
    """One line per component, de-duplicated by reference.

    A YAML recipe listing the same ingredient twice would violate the primary key rather than
    summing, so the quantities are combined here — and the seed does not currently do it, which is
    why this is a guard rather than a feature.
    """
    combined: dict[str, Decimal] = {}
    for record in records:
        ref = str(record["ref"])
        if ref not in items:
            raise MissingSeedReferenceError(f"{owner} uses {ref!r}, which was not seeded.")
        combined[ref] = combined.get(ref, Decimal(0)) + Decimal(str(record[quantity_key]))
    for seq, (ref, quantity) in enumerate(combined.items()):
        session.add(
            RecipeLine(
                # Taken from the recipe rather than from the component, which is the whole point of
                # the column: the composite foreign keys then refuse any component that does not
                # share it. Passing the whole recipe instead of its id is what makes that automatic.
                restaurant_id=recipe.restaurant_id,
                recipe_id=recipe.id,
                component_id=items[ref].id,
                quantity=quantity,
                seq=seq,
            )
        )
