"""Queries for stock items and recipes.

Two things here carry the module's weight:

**`load_costing_snapshot` is two queries, not two hundred.** The cost engine works on plain
mappings, and this is what builds them: every stock item with its profile, and every current
preparation recipe's lines, in a fixed number of statements. Loading them lazily as the recursion
walked would be an N+1 shaped exactly like M03's menu tree, with the same property that it looks
fine against a twelve-ingredient fixture.

**`used_by` is the reason `recipe_line` has an index on `component_id`.** `docs/schema.md` §4 puts
it there deliberately: "paneer went up 12%, which dishes changed?" is the question an owner asks
first when a price moves, and without the index it is a full scan of every recipe line in the
restaurant. It is transitive — paneer is in makhani gravy, which is in six dishes — so the answer
is a walk, not a single select.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import Select, func, literal, select, tuple_
from sqlalchemy.orm import selectinload

from app.models.menu import MenuItem, MenuItemVariant
from app.models.stock import (
    IngredientProfile,
    PreparationProfile,
    Recipe,
    RecipeLine,
    StockItem,
)
from app.repositories.base import (
    RestaurantScopedRepository,
    ScopedRepository,
    page_size,
)
from app.repositories.menu import _as_uuid
from app.services.costing import Component, Line


class StockItemRepository(RestaurantScopedRepository[StockItem]):
    model = StockItem

    def _with_profiles(self) -> Select[tuple[StockItem]]:
        return self.scoped().options(
            selectinload(StockItem.ingredient), selectinload(StockItem.preparation)
        )

    async def list_all(
        self,
        *,
        kind: str | None = None,
        category: str | None = None,
        limit: int | None = None,
        after: uuid.UUID | None = None,
        include_inactive: bool = True,
    ) -> Sequence[StockItem]:
        """Code order, because that is how an ingredient master is read and searched.

        The cursor compares `(code, id)` rather than the id alone: two items cannot share a code
        within a restaurant, so `code` is already total — but the pair keeps the shape identical to
        every other cursor in this codebase, and a future per-category ordering will need it.
        """
        query = self._with_profiles()
        if kind is not None:
            query = query.where(StockItem.kind == kind)
        if category is not None:
            query = query.where(StockItem.category == category)
        if not include_inactive:
            query = query.where(StockItem.is_active.is_(True))
        if after is not None:
            cursor_code = (
                select(StockItem.code)
                .where(StockItem.id == after, StockItem.restaurant_id == self.scope.restaurant_id)
                .scalar_subquery()
            )
            query = query.where(
                tuple_(StockItem.code, StockItem.id) > tuple_(cursor_code, _as_uuid(after))
            )
        query = query.order_by(StockItem.code, StockItem.id)
        return (await self.session.scalars(query.limit(page_size(limit)))).all()

    async def get_with_profile(self, item_id: uuid.UUID) -> StockItem | None:
        result = await self.session.scalars(self._with_profiles().where(StockItem.id == item_id))
        return result.first()

    async def get_for_update(self, item_id: uuid.UUID) -> StockItem | None:
        result = await self.session.scalars(
            self.scoped().where(StockItem.id == item_id).with_for_update()
        )
        return result.first()

    async def code_exists(self, code: str) -> bool:
        found = await self.session.scalar(
            self.scoped()
            .with_only_columns(literal(1))
            .where(StockItem.code == code.strip())
            .limit(1)
        )
        return found is not None

    async def ids_owned(self, item_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        """Which of these stock items belong to the caller's restaurant.

        Asked once per recipe save rather than once per line. `recipe_line` has no `restaurant_id`
        for the base class to filter on — its parent carries one — so this is the check that keeps a
        recipe from referencing another tenant's ingredient.
        """
        if not item_ids:
            return set()
        found = await self.session.scalars(
            select(StockItem.id).where(
                StockItem.restaurant_id == self.scope.restaurant_id,
                StockItem.id.in_(list(item_ids)),
            )
        )
        return set(found.all())


class RecipeRepository(RestaurantScopedRepository[Recipe]):
    model = Recipe

    async def current_for_variant(self, variant_id: uuid.UUID) -> Recipe | None:
        result = await self.session.scalars(
            self.scoped()
            .options(selectinload(Recipe.lines))
            .where(Recipe.menu_item_variant_id == variant_id, Recipe.is_current.is_(True))
        )
        return result.first()

    async def current_for_preparation(self, stock_item_id: uuid.UUID) -> Recipe | None:
        result = await self.session.scalars(
            self.scoped()
            .options(selectinload(Recipe.lines))
            .where(Recipe.produces_stock_item_id == stock_item_id, Recipe.is_current.is_(True))
        )
        return result.first()

    async def current_for_modifier(self, modifier_id: uuid.UUID) -> Recipe | None:
        result = await self.session.scalars(
            self.scoped()
            .options(selectinload(Recipe.lines))
            .where(Recipe.modifier_id == modifier_id, Recipe.is_current.is_(True))
        )
        return result.first()

    async def get_with_lines(self, recipe_id: uuid.UUID) -> Recipe | None:
        result = await self.session.scalars(
            self.scoped().options(selectinload(Recipe.lines)).where(Recipe.id == recipe_id)
        )
        return result.first()

    async def versions_of(self, recipe: Recipe) -> Sequence[Recipe]:
        """Every version of the same owner, newest first. The history a person needs when asking
        why a dish's cost moved."""
        query = self.scoped()
        if recipe.menu_item_variant_id is not None:
            query = query.where(Recipe.menu_item_variant_id == recipe.menu_item_variant_id)
        elif recipe.produces_stock_item_id is not None:
            query = query.where(Recipe.produces_stock_item_id == recipe.produces_stock_item_id)
        else:
            query = query.where(Recipe.modifier_id == recipe.modifier_id)
        return (await self.session.scalars(query.order_by(Recipe.version.desc()))).all()

    async def highest_version(
        self,
        *,
        variant_id: uuid.UUID | None,
        produces_id: uuid.UUID | None,
        modifier_id: uuid.UUID | None,
    ) -> int:
        query = select(func.coalesce(func.max(Recipe.version), 0)).where(
            Recipe.restaurant_id == self.scope.restaurant_id
        )
        if variant_id is not None:
            query = query.where(Recipe.menu_item_variant_id == variant_id)
        elif produces_id is not None:
            query = query.where(Recipe.produces_stock_item_id == produces_id)
        else:
            query = query.where(Recipe.modifier_id == modifier_id)
        return int(await self.session.scalar(query) or 0)

    async def clear_current(
        self,
        *,
        variant_id: uuid.UUID | None,
        produces_id: uuid.UUID | None,
        modifier_id: uuid.UUID | None,
    ) -> None:
        """Stand the previous version down, **locked**.

        `FOR UPDATE`, because the partial unique index is the authority and two concurrent
        `POST /recipes/{id}/version` calls would otherwise both read "version 3 is current", both
        try to insert version 4, and one would come back as a 500 from a constraint rather than as
        a conflict a caller can act on.
        """
        query = self.scoped().where(Recipe.is_current.is_(True))
        if variant_id is not None:
            query = query.where(Recipe.menu_item_variant_id == variant_id)
        elif produces_id is not None:
            query = query.where(Recipe.produces_stock_item_id == produces_id)
        else:
            query = query.where(Recipe.modifier_id == modifier_id)
        for recipe in (await self.session.scalars(query.with_for_update())).all():
            recipe.is_current = False


class CostingRepository(ScopedRepository[StockItem]):
    """Builds the snapshot the cost engine runs on.

    Not `RestaurantScopedRepository`, because it returns plain dataclasses rather than models — the
    scope is applied by hand in each query and is visible at the point it is used.
    """

    model = StockItem

    async def load_snapshot(
        self,
    ) -> tuple[dict[uuid.UUID, Component], dict[uuid.UUID, list[Line]]]:
        """Every stock item and every current preparation recipe, in three statements.

        Three and not one: a join across items, both profiles and recipe lines would multiply rows
        and then have to be de-duplicated in Python, which is slower and much harder to read than
        three selects the planner can each use an index for.
        """
        items = (
            await self.session.scalars(
                select(StockItem)
                .options(selectinload(StockItem.ingredient), selectinload(StockItem.preparation))
                .where(StockItem.restaurant_id == self.scope.restaurant_id)
            )
        ).all()

        components: dict[uuid.UUID, Component] = {}
        for item in items:
            ingredient: IngredientProfile | None = item.ingredient
            preparation: PreparationProfile | None = item.preparation
            components[item.id] = Component(
                id=item.id,
                code=item.code,
                kind=item.kind,
                base_unit=item.base_unit,
                price=Decimal(str(item.current_unit_cost)),
                yield_factor=(
                    Decimal(str(ingredient.yield_factor)) if ingredient is not None else None
                ),
                batch_yield=(
                    Decimal(str(preparation.batch_yield)) if preparation is not None else None
                ),
            )

        rows = (
            await self.session.execute(
                select(Recipe.produces_stock_item_id, RecipeLine.component_id, RecipeLine.quantity)
                .join(RecipeLine, RecipeLine.recipe_id == Recipe.id)
                .where(
                    Recipe.restaurant_id == self.scope.restaurant_id,
                    Recipe.is_current.is_(True),
                    Recipe.produces_stock_item_id.is_not(None),
                )
                .order_by(RecipeLine.seq)
            )
        ).all()

        prep_lines: dict[uuid.UUID, list[Line]] = {}
        for produces_id, component_id, quantity in rows:
            prep_lines.setdefault(produces_id, []).append(
                Line(component_id=component_id, quantity=Decimal(str(quantity)))
            )
        return components, prep_lines

    async def variant_recipes(self) -> dict[uuid.UUID, list[Line]]:
        """Every dish's current recipe, for the menu-wide cost screen. One statement."""
        rows = (
            await self.session.execute(
                select(Recipe.menu_item_variant_id, RecipeLine.component_id, RecipeLine.quantity)
                .join(RecipeLine, RecipeLine.recipe_id == Recipe.id)
                .where(
                    Recipe.restaurant_id == self.scope.restaurant_id,
                    Recipe.is_current.is_(True),
                    Recipe.menu_item_variant_id.is_not(None),
                )
                .order_by(RecipeLine.seq)
            )
        ).all()
        out: dict[uuid.UUID, list[Line]] = {}
        for variant_id, component_id, quantity in rows:
            out.setdefault(variant_id, []).append(
                Line(component_id=component_id, quantity=Decimal(str(quantity)))
            )
        return out

    async def used_by(self, component_id: uuid.UUID) -> tuple[list[StockItem], list[MenuItem]]:
        """What consumes this, transitively.

        Paneer is in makhani gravy, and makhani gravy is in six dishes — so a single select over
        `recipe_line` finds the gravy and misses the dishes, which is the answer an owner actually
        wants. The walk is breadth-first over preparations, then one pass to the dishes that use
        any of them. Bounded by ADR 0006's depth cap, so it terminates.
        """
        reached: set[uuid.UUID] = {component_id}
        frontier = [component_id]
        preparations: list[StockItem] = []

        while frontier:
            parents = (
                await self.session.scalars(
                    select(Recipe.produces_stock_item_id)
                    .join(RecipeLine, RecipeLine.recipe_id == Recipe.id)
                    .where(
                        Recipe.restaurant_id == self.scope.restaurant_id,
                        Recipe.is_current.is_(True),
                        Recipe.produces_stock_item_id.is_not(None),
                        RecipeLine.component_id.in_(frontier),
                    )
                )
            ).all()
            # `produces_stock_item_id` is nullable on the model, so mypy sees `UUID | None` even
            # though the query filters nulls out. Narrowed here rather than cast, because a None
            # slipping through would silently widen the walk to every recipe in the restaurant.
            frontier = [
                parent for parent in set(parents) if parent is not None and parent not in reached
            ]
            reached.update(frontier)

        if len(reached) > 1:
            preparations = list(
                (
                    await self.session.scalars(
                        select(StockItem)
                        # Eager, because `StockItem.ingredient`/`preparation` are `lazy="raise"`
                        # and the response schema serialises both. Without this the endpoint raises
                        # rather than silently N+1-ing, which is what caught it here.
                        .options(
                            selectinload(StockItem.ingredient),
                            selectinload(StockItem.preparation),
                        )
                        .where(
                            StockItem.restaurant_id == self.scope.restaurant_id,
                            StockItem.id.in_(reached - {component_id}),
                        )
                    )
                ).all()
            )

        dishes = (
            await self.session.scalars(
                select(MenuItem)
                .join(MenuItemVariant, MenuItemVariant.menu_item_id == MenuItem.id)
                .join(Recipe, Recipe.menu_item_variant_id == MenuItemVariant.id)
                .join(RecipeLine, RecipeLine.recipe_id == Recipe.id)
                .where(
                    MenuItem.restaurant_id == self.scope.restaurant_id,
                    Recipe.is_current.is_(True),
                    RecipeLine.component_id.in_(reached),
                )
                .distinct()
                .order_by(MenuItem.name)
            )
        ).all()
        return preparations, list(dishes)
