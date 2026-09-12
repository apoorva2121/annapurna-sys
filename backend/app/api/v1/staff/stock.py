"""Stock items, recipes, and what a dish costs.

Every handler is authorise-call-shape and nothing else (engineering-standards §1). Three
permissions, and the separation of duties between them is the point:

- `recipe.view` — chef, kitchen staff, store manager, manager. Reading a recipe is the job.
- `recipe.manage` — **chef and owner.** The chef owns the recipe. Not the manager.
- `cost.view` — **manager and owner.** Not the chef: `seed/organization.yaml` says "a chef sees
  grams, not rupees".

So the person who writes the recipe cannot see what it costs, and the person who sees the cost
cannot change the recipe that produces it. That is deliberate, it comes from the P1 design, and it
is why the cost endpoints live behind their own dependency rather than sharing `recipe.view`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.repositories.base import DEFAULT_PAGE_SIZE
from app.schemas.stock import (
    CostedLineResponse,
    DishCostResponse,
    MenuCostResponse,
    MenuCostRow,
    RecipeResponse,
    RecipeVersionRequest,
    StockItemCreateRequest,
    StockItemListResponse,
    StockItemResponse,
    StockItemUpdateRequest,
    UsedByResponse,
)
from app.services.costing import food_cost_percentage
from app.services.stock import StockService

router = APIRouter(tags=["stock"])

_ViewDep = Annotated[Actor, Depends(require_permission(PermissionCode.RECIPE_VIEW))]
_ManageDep = Annotated[Actor, Depends(require_permission(PermissionCode.RECIPE_MANAGE))]
_CostDep = Annotated[Actor, Depends(require_permission(PermissionCode.COST_VIEW))]

_LimitDep = Annotated[int | None, Query(ge=1, le=100)]
_CursorDep = Annotated[uuid.UUID | None, Query()]


def _next_cursor(items: list[object], limit: int | None) -> uuid.UUID | None:
    if len(items) < (limit or DEFAULT_PAGE_SIZE):
        return None
    return getattr(items[-1], "id", None)


# --------------------------------------------------------------------------- stock items


@router.get("/stock-items", response_model=StockItemListResponse)
async def list_stock_items(
    actor: _ViewDep,
    session: SessionDep,
    kind: Annotated[str | None, Query(pattern=r"^(ingredient|preparation)$")] = None,
    category: Annotated[str | None, Query()] = None,
    limit: _LimitDep = None,
    cursor: _CursorDep = None,
    include_inactive: Annotated[bool, Query()] = True,
) -> StockItemListResponse:
    rows = await StockService(session).list_items(
        actor,
        kind=kind,
        category=category,
        limit=limit,
        after=cursor,
        include_inactive=include_inactive,
    )
    items = [StockItemResponse.model_validate(row) for row in rows]
    return StockItemListResponse(items=items, next_cursor=_next_cursor(list(rows), limit))


@router.get("/stock-items/{item_id}", response_model=StockItemResponse)
async def get_stock_item(
    actor: _ViewDep, session: SessionDep, item_id: uuid.UUID
) -> StockItemResponse:
    item = await StockService(session).get_item(actor, item_id)
    return StockItemResponse.model_validate(item)


@router.post("/stock-items", response_model=StockItemResponse, status_code=status.HTTP_201_CREATED)
async def create_stock_item(
    actor: _ManageDep, session: SessionDep, request: StockItemCreateRequest
) -> StockItemResponse:
    """An ingredient or a preparation, with the profile that makes it one.

    Refused without the matching profile: a preparation with no `batch_yield` has no unit cost, and
    inventing one would put a wrong number on every dish that uses it.
    """
    item = await StockService(session).create_item(actor, request)
    await session.commit()
    return StockItemResponse.model_validate(item)


@router.patch("/stock-items/{item_id}", response_model=StockItemResponse)
async def update_stock_item(
    actor: _ManageDep,
    session: SessionDep,
    item_id: uuid.UUID,
    request: StockItemUpdateRequest,
) -> StockItemResponse:
    """Never the `kind` and never the `code`. A price change writes an `audit_log` row, because it
    moves every dish that uses this and leaves no other trace."""
    item = await StockService(session).update_item(actor, item_id, request)
    await session.commit()
    return StockItemResponse.model_validate(item)


@router.get("/stock-items/{item_id}/used-by", response_model=UsedByResponse)
async def used_by(actor: _ViewDep, session: SessionDep, item_id: uuid.UUID) -> UsedByResponse:
    """What consumes this, **transitively**.

    Paneer is in makhani gravy and makhani gravy is in six dishes. A single query over `recipe_line`
    finds the gravy and misses the dishes, which is the answer nobody wanted. `docs/schema.md` §4
    puts an index on `recipe_line.component_id` specifically so this walk is affordable.
    """
    preparations, dishes = await StockService(session).used_by(actor, item_id)
    return UsedByResponse(
        preparations=[StockItemResponse.model_validate(row) for row in preparations],
        dishes=[dish.id for dish in dishes],
        dish_names=[dish.name for dish in dishes],
    )


# --------------------------------------------------------------------------- recipes


@router.get("/recipes/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(actor: _ViewDep, session: SessionDep, recipe_id: uuid.UUID) -> RecipeResponse:
    recipe = await StockService(session).get_recipe(actor, recipe_id)
    return RecipeResponse.model_validate(recipe)


@router.post("/recipes", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
async def save_recipe_version(
    actor: _ManageDep, session: SessionDep, request: RecipeVersionRequest
) -> RecipeResponse:
    """The next version of a recipe. **The only write this table has.**

    Creating the first version and changing an existing one are the same call, deliberately: there
    is no "edit", so there is no path that could quietly become one. `order_line` cites a version,
    and a version whose lines moved would restate what every past order cost.
    """
    recipe = await StockService(session).save_version(actor, request)
    await session.commit()
    return RecipeResponse.model_validate(recipe)


@router.post("/recipes/{recipe_id}/confirm", response_model=RecipeResponse)
async def confirm_recipe(
    actor: _ManageDep, session: SessionDep, recipe_id: uuid.UUID
) -> RecipeResponse:
    """A chef saying "yes, this is what we actually make".

    A recipe matched from `library/` arrives unconfirmed by definition — `library/PROVENANCE.md`
    says most of the library is `estimated` — and a cost computed from an unconfirmed recipe is a
    proposal the screen must be able to label as one.
    """
    recipe = await StockService(session).confirm_recipe(actor, recipe_id)
    await session.commit()
    return RecipeResponse.model_validate(recipe)


# --------------------------------------------------------------------------- cost


@router.get("/menu-variants/{variant_id}/cost", response_model=DishCostResponse)
async def variant_cost(
    actor: _CostDep, session: SessionDep, variant_id: uuid.UUID
) -> DishCostResponse:
    """One dish's cost, line by line.

    The breakdown is the product. "Butter Chicken costs ₹126.70" is not actionable; the line saying
    ₹63 of it is chicken tikka is what an owner uses when the price of chicken moves.
    """
    service = StockService(session)
    variant = await service.variant_for_cost(actor, variant_id)
    cost, has_recipe = await service.cost_of_variant(actor, variant_id)
    # The column is `Mapped[object]` on the model — SQLAlchemy's typing for NUMERIC — so it is
    # narrowed here rather than everywhere it is used. `str()` and not `float()`: the round trip
    # through a float is precisely what invariant 3 forbids.
    price = Decimal(str(variant.price))
    return DishCostResponse(
        menu_item_variant_id=variant_id,
        cost=cost.rupees,
        price=price,
        food_cost_percent=food_cost_percentage(cost.total, price) if has_recipe else None,
        margin=price - cost.rupees,
        lines=[
            CostedLineResponse(
                component_id=line.component_id,
                code=line.code,
                quantity=line.quantity,
                unit_cost=line.unit_cost,
                cost=line.cost,
            )
            for line in cost.lines
        ],
        has_recipe=has_recipe,
    )


@router.get("/menu/costs", response_model=MenuCostResponse)
async def menu_costs(actor: _CostDep, session: SessionDep) -> MenuCostResponse:
    """Every dish's cost and margin, worst first. **The day-1 screen.**

    `docs/audit/2026-09-11-findings.md`: "Build the day-1 dish-margin screen in M04, not M13." It is
    the first thing this product can tell an owner that they did not already know, and it needs no
    orders, no history and no machine learning — only a menu and a recipe.
    """
    rows = await StockService(session).menu_costs(actor)
    costed: list[Decimal] = [
        row["food_cost_percent"] for row in rows if row["food_cost_percent"] is not None
    ]
    # A plain average across costed dishes, and labelled as one in the schema. The seed's 25.6%
    # figure is weighted by popularity; this cannot be, because popularity is observed demand and
    # no orders exist until M07. Two different numbers that must not be confused for each other.
    average = (sum(costed, Decimal(0)) / len(costed)).quantize(Decimal("0.1")) if costed else None
    return MenuCostResponse(
        rows=[MenuCostRow(**row) for row in rows],
        average_food_cost_percent=average,
        uncosted=sum(1 for row in rows if not row["has_recipe"]),
    )
