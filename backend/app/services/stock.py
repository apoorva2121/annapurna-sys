"""The rules for stock items and recipes.

Four rules, and they are why this file exists rather than the routes calling repositories:

**1 · A recipe is never edited, only versioned.** `order_line` (M07) cites the version live when the
line was added, so moving a version's lines would restate what every past order cost — the same
class of error as an edited tax rate, with the same answer. `save_version` is the only write, and
it stands the previous version down under a lock.

**2 · Depth and cycles are refused at save time, not at cost time.** ADR 0006 asks for both. The
cost engine would raise the same errors, but only when somebody asked for a cost, which could be
weeks later with the recipe already in use.

**3 · Cost is frozen on the version.** Finding X8: a version is immutable, so what it cost when it
became current is a fact worth storing, and it is what M13 reads instead of
`stock_item.current_unit_cost` — which finding S16 flags as unsafe for a historical question.

**4 · Every component of a recipe must belong to the caller's restaurant.** `recipe_line` has no
`restaurant_id` for the repository base class to filter on, so the check is here and a test holds
it — exactly the shape M03's modifier attachment has.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.errors import AppError, ConflictError, NotFoundError
from app.models.audit import AuditLog
from app.models.menu import MenuItem, MenuItemVariant
from app.models.stock import (
    IngredientProfile,
    PreparationProfile,
    Recipe,
    RecipeLine,
    StockItem,
)
from app.repositories.menu import (
    MenuItemRepository,
    MenuItemVariantRepository,
    ModifierRepository,
)
from app.repositories.stock import CostingRepository, RecipeRepository, StockItemRepository
from app.schemas.stock import (
    IngredientProfileRequest,
    PreparationProfileRequest,
    RecipeVersionRequest,
    StockItemCreateRequest,
    StockItemUpdateRequest,
)
from app.services.costing import Component, Cost, CostEngine, Line, food_cost_percentage


def _same_lines(recipe: Recipe, lines: Sequence[Line]) -> bool:
    """Whether a recipe already says exactly this (owner defect sheet, row 24).

    Compared as a set of component and quantity, because `seq` is presentation: reordering the
    same lines is not a new recipe, and neither is retyping "40" as "40.0000".
    """

    def key(component_id: object, quantity: object) -> tuple[str, Decimal]:
        return str(component_id), Decimal(str(quantity))

    have = sorted(key(line.component_id, line.quantity) for line in recipe.lines)
    want = sorted(key(line.component_id, line.quantity) for line in lines)
    return have == want


class StockService:
    """Stock items, recipes and what they cost. The caller owns the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ repositories

    def _items(self, actor: Actor) -> StockItemRepository:
        return StockItemRepository(self.session, actor.scope)

    def _recipes(self, actor: Actor) -> RecipeRepository:
        return RecipeRepository(self.session, actor.scope)

    def _costing(self, actor: Actor) -> CostingRepository:
        return CostingRepository(self.session, actor.scope)

    # ------------------------------------------------------------------ stock items

    async def list_items(
        self,
        actor: Actor,
        *,
        kind: str | None = None,
        category: str | None = None,
        limit: int | None = None,
        after: uuid.UUID | None = None,
        include_inactive: bool = True,
    ) -> Sequence[StockItem]:
        return await self._items(actor).list_all(
            kind=kind,
            category=category,
            limit=limit,
            after=after,
            include_inactive=include_inactive,
        )

    async def get_item(self, actor: Actor, item_id: uuid.UUID) -> StockItem:
        item = await self._items(actor).get_with_profile(item_id)
        if item is None:
            raise NotFoundError("stock_item.not_found", "That stock item does not exist.")
        return item

    async def create_item(self, actor: Actor, request: StockItemCreateRequest) -> StockItem:
        repo = self._items(actor)
        if await repo.code_exists(request.code):
            raise ConflictError(
                "stock_item.code_taken",
                f"A stock item with code {request.code!r} already exists. The code is how recipes "
                "and the starter library find it, so it is permanent — pick another.",
            )
        self._require_matching_profile(request.kind, request.ingredient, request.preparation)

        item = StockItem(
            restaurant_id=actor.restaurant_id,
            kind=request.kind,
            code=request.code,
            name=request.name,
            base_unit=request.base_unit,
            category=request.category,
            storage_type=request.storage_type,
            current_unit_cost=request.current_unit_cost,
            is_active=True,
        )
        self.session.add(item)
        await self.session.flush()

        if request.ingredient is not None:
            self.session.add(self._ingredient_profile(item.id, request.ingredient))
        if request.preparation is not None:
            self.session.add(self._preparation_profile(item.id, request.preparation))
        await self.session.flush()
        return await self.get_item(actor, item.id)

    async def update_item(
        self, actor: Actor, item_id: uuid.UUID, request: StockItemUpdateRequest
    ) -> StockItem:
        repo = self._items(actor)
        item = await repo.get_for_update(item_id)
        if item is None:
            raise NotFoundError("stock_item.not_found", "That stock item does not exist.")

        changes = request.model_dump(exclude_unset=True)
        profile_ingredient = changes.pop("ingredient", None)
        profile_preparation = changes.pop("preparation", None)
        if profile_ingredient is not None and item.kind != "ingredient":
            raise AppError(
                "stock_item.wrong_profile",
                f"{item.name!r} is a preparation, so it has no purchase unit or shelf "
                "life in days.",
                status_code=422,
            )
        if profile_preparation is not None and item.kind != "preparation":
            raise AppError(
                "stock_item.wrong_profile",
                f"{item.name!r} is an ingredient, so it has no batch yield or station.",
                status_code=422,
            )

        before = {
            "current_unit_cost": item.current_unit_cost,
            "is_active": item.is_active,
        }
        for field, value in changes.items():
            setattr(item, field, value)

        full = await repo.get_with_profile(item_id)
        if profile_ingredient is not None and full is not None and full.ingredient is not None:
            for field, value in profile_ingredient.items():
                setattr(full.ingredient, field, value)
        if profile_preparation is not None and full is not None and full.preparation is not None:
            for field, value in profile_preparation.items():
                setattr(full.preparation, field, value)
        await self.session.flush()

        if "current_unit_cost" in changes and before["current_unit_cost"] != item.current_unit_cost:
            # A price change moves every dish that uses this. Audited for the same reason a menu
            # reprice is: it changes money and leaves no other trace (invariant 6).
            await self._audit(
                actor,
                action="stock_item.repriced",
                entity_id=item.id,
                old_value={"current_unit_cost": before["current_unit_cost"]},
                new_value={"current_unit_cost": item.current_unit_cost},
            )
        return await self.get_item(actor, item_id)

    async def used_by(
        self, actor: Actor, item_id: uuid.UUID
    ) -> tuple[list[StockItem], list[MenuItem]]:
        await self.get_item(actor, item_id)
        return await self._costing(actor).used_by(item_id)

    # ------------------------------------------------------------------ recipes

    async def get_recipe(self, actor: Actor, recipe_id: uuid.UUID) -> Recipe:
        recipe = await self._recipes(actor).get_with_lines(recipe_id)
        if recipe is None:
            raise NotFoundError("recipe.not_found", "That recipe does not exist.")
        return recipe

    async def current_recipe_for_variant(self, actor: Actor, variant_id: uuid.UUID) -> Recipe:
        recipe = await self._recipes(actor).current_for_variant(variant_id)
        if recipe is None:
            raise NotFoundError("recipe.not_found", "That dish has no recipe yet.")
        return recipe

    async def save_version(self, actor: Actor, request: RecipeVersionRequest) -> Recipe:
        """Create the next version of a recipe. The only write this table has.

        Creating the first version and changing an existing one are deliberately the same call:
        there is no "edit", so there is no path that could accidentally become one.
        """
        owner = self._require_one_owner(request)
        await self._require_owner_exists(actor, request)

        component_ids = [line.component_id for line in request.lines]
        if len(set(component_ids)) != len(component_ids):
            raise AppError(
                "recipe.duplicate_component",
                "The same ingredient is listed twice. Combine the quantities into one line.",
                status_code=422,
            )
        # Rule 4. `recipe_line` has no `restaurant_id`, so this is the tenant check.
        owned = await self._items(actor).ids_owned(component_ids)
        missing = sorted(str(item) for item in set(component_ids) - owned)
        if missing:
            raise NotFoundError(
                "stock_item.not_found",
                f"{len(missing)} of those ingredients do not exist.",
                details={"missing": missing},
            )

        components, prep_lines = await self._costing(actor).load_snapshot()
        lines = [
            Line(component_id=line.component_id, quantity=line.quantity) for line in request.lines
        ]

        # Rule 2. Refused before it is saved, with the chain named. `owner_code` is what appears at
        # the head of a cycle message, so a person reading it knows where to start unpicking.
        owner_code = await self._owner_code(actor, request)
        engine = CostEngine(components, prep_lines)
        engine.check_depth_and_cycles(
            lines,
            owner_code=owner_code,
            owner_is_preparation=request.produces_stock_item_id is not None,
        )

        repo = self._recipes(actor)
        # Rule 1, and the lock has to be taken on a row that **always exists**.
        #
        # An earlier version locked inside `clear_current`, over `WHERE is_current` — which for a
        # recipe's *first* version matches nothing, so two concurrent creates both computed version
        # 1 and one hit the unique index as a 500. For later versions it was no better: under READ
        # COMMITTED the blocked statement re-checks only the locked row rather than re-running
        # against a new snapshot, so the second writer never saw the version the first had just
        # committed. `SetupService.add_tax_rate` had this right — it locks the `tax_group` row —
        # and this is the same fix. Found by review.
        await self._lock_owner(actor, request)

        # The owner's defect sheet, row 24. Veg Manchurian Dry had five versions with identical
        # lines, alternating confirmed and unconfirmed: Save stayed enabled with nothing changed
        # and the screen offered no other way out, so Save was pressed to leave. The screen is
        # fixed too, but a rule that only a screen enforces is a rule until the next screen.
        #
        # After the lock, deliberately: two identical saves racing would otherwise both read the
        # old current version and both pass.
        if request.menu_item_variant_id is not None:
            live = await repo.current_for_variant(request.menu_item_variant_id)
        elif request.produces_stock_item_id is not None:
            live = await repo.current_for_preparation(request.produces_stock_item_id)
        elif request.modifier_id is not None:
            live = await repo.current_for_modifier(request.modifier_id)
        else:  # pragma: no cover - _require_one_owner has already refused an ownerless request
            live = None
        if live is not None and _same_lines(live, lines):
            raise ConflictError(
                "recipe.unchanged",
                "Nothing has changed in this recipe, so there is no new version to save.",
            )

        await repo.clear_current(
            variant_id=request.menu_item_variant_id,
            produces_id=request.produces_stock_item_id,
            modifier_id=request.modifier_id,
        )
        version = (
            await repo.highest_version(
                variant_id=request.menu_item_variant_id,
                produces_id=request.produces_stock_item_id,
                modifier_id=request.modifier_id,
            )
            + 1
        )

        # Rule 3. Computed against the snapshot loaded above, which does not yet contain this
        # recipe — correct for a dish, and for a preparation it means the cost is of its *inputs*,
        # which is what a unit cost is.
        cost = engine.cost_of(lines)
        now = datetime.now(UTC)
        recipe = Recipe(
            restaurant_id=actor.restaurant_id,
            menu_item_variant_id=request.menu_item_variant_id,
            produces_stock_item_id=request.produces_stock_item_id,
            modifier_id=request.modifier_id,
            version=version,
            is_current=True,
            effective_from=now,
            notes=request.notes,
            unit_cost=self._unit_cost_for(request, cost, components),
            source=request.source,
            confirmed_at=now if request.confirmed else None,
        )
        self.session.add(recipe)
        await self.session.flush()
        for seq, line in enumerate(request.lines):
            self.session.add(
                RecipeLine(
                    # Redundant with the recipe's own, and deliberately so: it is what the composite
                    # foreign keys key on, and what makes "this line's component belongs to this
                    # line's tenant" a database guarantee rather than a service convention.
                    restaurant_id=actor.restaurant_id,
                    recipe_id=recipe.id,
                    component_id=line.component_id,
                    quantity=line.quantity,
                    seq=seq,
                )
            )
        await self.session.flush()

        await self._audit(
            actor,
            action="recipe.version_created",
            entity_id=recipe.id,
            old_value={"owner": owner, "version": version - 1} if version > 1 else None,
            new_value={"owner": owner, "version": version, "unit_cost": recipe.unit_cost},
        )
        return await self.get_recipe(actor, recipe.id)

    async def confirm_recipe(self, actor: Actor, recipe_id: uuid.UUID) -> Recipe:
        """A chef saying "yes, this is what we actually make".

        Separate from saving, because a recipe matched from `library/` arrives unconfirmed by
        definition — `library/PROVENANCE.md` says most of the library is `estimated` — and a cost
        computed from an unconfirmed recipe is a proposal that the screen must be able to label.
        """
        recipe = await self.get_recipe(actor, recipe_id)
        if recipe.confirmed_at is None:
            recipe.confirmed_at = datetime.now(UTC)
            await self.session.flush()
            await self._audit(
                actor,
                action="recipe.confirmed",
                entity_id=recipe.id,
                old_value=None,
                new_value={"confirmed_at": recipe.confirmed_at},
            )
        return recipe

    # ------------------------------------------------------------------ costing

    async def variant_for_cost(self, actor: Actor, variant_id: uuid.UUID) -> MenuItemVariant:
        """The variant, so the cost endpoint can report a margin against its price.

        A separate read rather than threading the price through `cost_of_variant`: the cost engine
        knows nothing about what a dish sells for, and it should stay that way — cost and price meet
        in the response, not in the arithmetic.
        """
        variant = await MenuItemVariantRepository(self.session, actor.scope).get(variant_id)
        if variant is None:
            raise NotFoundError("menu_item_variant.not_found", "That variant does not exist.")
        return variant

    async def cost_of_variant(self, actor: Actor, variant_id: uuid.UUID) -> tuple[Cost, bool]:
        """What one dish costs, line by line. `False` when it has no recipe yet.

        A dish with no recipe returns an empty cost rather than raising: the cost screen shows every
        dish, and one uncosted row must not take the screen down. The flag is what lets it say "not
        costed yet" instead of "₹0.00", which would read as a dish that is free to make.
        """
        recipe = await self._recipes(actor).current_for_variant(variant_id)
        if recipe is None:
            return Cost(total=Decimal(0), lines=()), False
        components, prep_lines = await self._costing(actor).load_snapshot()
        engine = CostEngine(components, prep_lines)
        lines = [
            Line(component_id=line.component_id, quantity=Decimal(str(line.quantity)))
            for line in recipe.lines
        ]
        return engine.cost_of(lines), True

    async def menu_costs(self, actor: Actor) -> tuple[list[dict[str, Any]], bool]:
        """Every dish's cost and margin — the day-1 screen the audit asked for in M04, not M13.

        **One snapshot, one engine, one pass.** The engine memoises preparations across every dish
        in the sweep, so makhani gravy is walked once for the six dishes that use it rather than six
        times. That is what makes this affordable at 400 dishes, and a query-count test holds it.
        """
        components, prep_lines = await self._costing(actor).load_snapshot()
        variant_lines = await self._costing(actor).variant_recipes()
        engine = CostEngine(components, prep_lines)

        confirmed = await self._confirmed_variants(actor)
        rows: list[dict[str, Any]] = []
        # The whole menu, not a page. A worst-first list that stopped at fifty rows would hide the
        # dish it exists to surface. `list_all(limit=100)` was the first version of this and it
        # truncated silently at the hundredth item.
        items, truncated = await MenuItemRepository(self.session, actor.scope).all_for_report()
        for item in items:
            for variant in item.variants:
                lines = variant_lines.get(variant.id)
                cost = engine.cost_of(lines) if lines else Cost(total=Decimal(0), lines=())
                price = Decimal(str(variant.price))
                rows.append(
                    {
                        "menu_item_id": item.id,
                        "menu_item_name": item.name,
                        "menu_item_variant_id": variant.id,
                        "variant_name": variant.name,
                        "cost": cost.rupees,
                        "price": price,
                        "food_cost_percent": (
                            food_cost_percentage(cost.total, price) if lines else None
                        ),
                        "margin": (price - cost.total).quantize(Decimal("0.01")),
                        "has_recipe": bool(lines),
                        "recipe_confirmed": variant.id in confirmed,
                    }
                )
        # Worst first. An owner opening this screen is looking for the dish that is losing money,
        # not reading an alphabetical list.
        rows.sort(key=lambda row: row["food_cost_percent"] or Decimal(-1), reverse=True)
        return rows, truncated

    async def _confirmed_variants(self, actor: Actor) -> set[uuid.UUID]:
        recipes = await self.session.scalars(
            RecipeRepository(self.session, actor.scope)
            .scoped()
            .where(Recipe.is_current.is_(True), Recipe.confirmed_at.is_not(None))
        )
        return {
            recipe.menu_item_variant_id
            for recipe in recipes
            if recipe.menu_item_variant_id is not None
        }

    # ------------------------------------------------------------------ shared

    def _require_matching_profile(
        self,
        kind: str,
        ingredient: IngredientProfileRequest | None,
        preparation: PreparationProfileRequest | None,
    ) -> None:
        """An ingredient needs an ingredient profile and a preparation needs a preparation one.

        Refused rather than defaulted: a preparation with no `batch_yield` has no unit cost, and
        inventing one would put a wrong number on every dish that uses it.

        **The wrong-profile check runs first**, because when somebody sends a preparation profile
        under `kind: ingredient` both refusals are true and only one is diagnostic. "You sent a
        batch yield for something that is bought" names the mistake; "an ingredient needs a purchase
        unit" describes a symptom and leaves them to work out why.
        """
        if kind == "ingredient" and preparation is not None:
            raise AppError(
                "stock_item.wrong_profile",
                "An ingredient has no batch yield or station — those belong to a preparation.",
                status_code=422,
            )
        if kind == "preparation" and ingredient is not None:
            raise AppError(
                "stock_item.wrong_profile",
                "A preparation is not bought, so it has no purchase unit.",
                status_code=422,
            )
        if kind == "ingredient" and ingredient is None:
            raise AppError(
                "stock_item.profile_required",
                "An ingredient needs a purchase unit, a conversion to base units and a shelf life.",
                status_code=422,
            )
        if kind == "preparation" and preparation is None:
            raise AppError(
                "stock_item.profile_required",
                "A preparation needs a batch yield, a shelf life in hours and a station.",
                status_code=422,
            )

    def _ingredient_profile(
        self, item_id: uuid.UUID, request: IngredientProfileRequest
    ) -> IngredientProfile:
        return IngredientProfile(
            stock_item_id=item_id,
            purchase_unit=request.purchase_unit,
            purchase_to_base=request.purchase_to_base,
            yield_factor=request.yield_factor,
            shelf_life_days=request.shelf_life_days,
            reorder_level=request.reorder_level,
            reorder_quantity=request.reorder_quantity,
        )

    def _preparation_profile(
        self, item_id: uuid.UUID, request: PreparationProfileRequest
    ) -> PreparationProfile:
        return PreparationProfile(
            stock_item_id=item_id,
            batch_yield=request.batch_yield,
            shelf_life_hours=request.shelf_life_hours,
            station_id=request.station_id,
            prep_minutes=request.prep_minutes,
        )

    async def _lock_owner(self, actor: Actor, request: RecipeVersionRequest) -> None:
        """Serialise every writer for one recipe owner on a row that is guaranteed to be there.

        The variant, the produced stock item or the modifier — whichever owns this recipe. All three
        exist by the time this runs (`_require_owner_exists` has resolved one), so the lock always
        has something to take, which is precisely what locking `WHERE is_current` did not.
        """
        if request.menu_item_variant_id is not None:
            await MenuItemVariantRepository(self.session, actor.scope).get_for_update(
                request.menu_item_variant_id
            )
        elif request.produces_stock_item_id is not None:
            await self._items(actor).get_for_update(request.produces_stock_item_id)
        elif request.modifier_id is not None:
            await ModifierRepository(self.session, actor.scope).get_for_update(request.modifier_id)

    def _require_one_owner(self, request: RecipeVersionRequest) -> str:
        owners = [
            ("variant", request.menu_item_variant_id),
            ("preparation", request.produces_stock_item_id),
            ("modifier", request.modifier_id),
        ]
        named = [label for label, value in owners if value is not None]
        if len(named) != 1:
            raise AppError(
                "recipe.owner_required",
                "A recipe belongs to exactly one of: a dish variant, a preparation it makes, or a "
                f"modifier. This one names {len(named)}.",
                status_code=422,
            )
        return named[0]

    async def _require_owner_exists(self, actor: Actor, request: RecipeVersionRequest) -> None:
        if request.menu_item_variant_id is not None:
            variant = await MenuItemVariantRepository(self.session, actor.scope).get(
                request.menu_item_variant_id
            )
            if variant is None:
                raise NotFoundError("menu_item_variant.not_found", "That variant does not exist.")
        elif request.produces_stock_item_id is not None:
            item = await self._items(actor).get(request.produces_stock_item_id)
            if item is None:
                raise NotFoundError("stock_item.not_found", "That preparation does not exist.")
            if item.kind != "preparation":
                raise AppError(
                    "recipe.not_a_preparation",
                    f"{item.name!r} is an ingredient. Only a preparation is made from a recipe.",
                    status_code=422,
                )
        elif request.modifier_id is not None:
            # **This branch did not exist**, and its absence was the worst defect the M03/M04 review
            # found. `modifier_id` was never checked for existence *or* tenancy, so one restaurant
            # could post a recipe against another's modifier: the row landed with the attacker's
            # `restaurant_id`, and the (then global) `uq_recipe_current_modifier` index permanently
            # blocked the owner from creating their own — a 500 with no recovery, forever.
            # Migration 0013 scoped the index; this closes the other half.
            modifier = await ModifierRepository(self.session, actor.scope).get(request.modifier_id)
            if modifier is None:
                raise NotFoundError("modifier.not_found", "That option does not exist.")

    async def _owner_code(self, actor: Actor, request: RecipeVersionRequest) -> str:
        """A label for the head of a cycle or depth message."""
        if request.produces_stock_item_id is not None:
            item = await self._items(actor).get(request.produces_stock_item_id)
            return item.code if item is not None else "this preparation"
        if request.modifier_id is not None:
            return "this option"
        return "this dish"

    def _unit_cost_for(
        self,
        request: RecipeVersionRequest,
        cost: Cost,
        components: dict[uuid.UUID, Component],
    ) -> Decimal:
        """What to freeze on the version.

        For a dish, the cost of one plate. For a preparation, the cost of **one base unit** of what
        it yields — the batch total divided by the batch yield — because that is the number every
        recipe consuming it multiplies by.
        """
        if request.produces_stock_item_id is None:
            return cost.total
        component = components.get(request.produces_stock_item_id)
        batch_yield = component.batch_yield if component is not None else None
        if not batch_yield:
            return cost.total
        return cost.total / batch_yield

    async def _audit(
        self,
        actor: Actor,
        *,
        action: str,
        entity_id: uuid.UUID,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any],
    ) -> None:
        self.session.add(
            AuditLog(
                restaurant_id=actor.restaurant_id,
                actor_employee_id=actor.employee_id,
                action=action,
                entity_type="recipe" if action.startswith("recipe") else "stock_item",
                entity_id=entity_id,
                old_value=_jsonable(old_value),
                new_value=_jsonable(new_value),
            )
        )


def _jsonable(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """`Decimal` and `UUID` are not JSON. Stringified, never floated — a cost in an audit row that
    reads `126.7000000001` is worse than useless in a dispute."""
    if value is None:
        return None
    return {key: str(item) if item is not None else None for key, item in value.items()}
