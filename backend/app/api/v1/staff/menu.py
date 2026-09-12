"""Menu endpoints: categories, dishes, variants, modifiers, and the tree.

Every handler is authorise-call-shape and nothing else (engineering-standards §1). Three permissions
rather than one, because `seed/organization.yaml`'s P1 design draws a line a single permission
cannot:

- `menu.view` — everyone who works a shift. A waiter cannot take an order without reading the menu.
- `menu.manage` — owner and manager. Structure: categories, dishes, modifiers, which dish goes to
  which station.
- `menu.price` — owner only. What a variant costs and which tax group it belongs to. The design
  withholds this from a manager by name, and the M03 threat table says why: a quiet reprice on cash
  orders leaves no other trace.

The split shows up twice in this file. `POST /menu/items` takes `menu.price` even though most of
what it sends is structure, because it may carry variants and a variant carries a price — a
`menu.manage` holder creating a dish priced at ₹1 would be the whole permission boundary walked
around. `PATCH .../variants/{id}` takes `menu.price` for the same reason.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.repositories.base import DEFAULT_PAGE_SIZE
from app.schemas.menu import (
    AttachModifierGroupsRequest,
    BulkAttachRequest,
    MenuCategoryCreateRequest,
    MenuCategoryListResponse,
    MenuCategoryResponse,
    MenuCategoryUpdateRequest,
    MenuItemCreateRequest,
    MenuItemListResponse,
    MenuItemResponse,
    MenuItemUpdateRequest,
    MenuItemVariantCreateRequest,
    MenuItemVariantUpdateRequest,
    MenuTreeResponse,
    ModifierCreateRequest,
    ModifierGroupCreateRequest,
    ModifierGroupListResponse,
    ModifierGroupResponse,
    ModifierGroupUpdateRequest,
    ModifierUpdateRequest,
)
from app.services.menu import MenuService
from app.services.menu_tree import staff_tree

router = APIRouter(tags=["menu"])

_ViewDep = Annotated[Actor, Depends(require_permission(PermissionCode.MENU_VIEW))]
_ManageDep = Annotated[Actor, Depends(require_permission(PermissionCode.MENU_MANAGE))]
_PriceDep = Annotated[Actor, Depends(require_permission(PermissionCode.MENU_PRICE))]

_LimitDep = Annotated[int | None, Query(ge=1, le=100)]
_CursorDep = Annotated[uuid.UUID | None, Query()]


def _next_cursor(items: list[object], limit: int | None) -> uuid.UUID | None:
    """Only offer a cursor when the page was full — see `setup.py` for the reasoning."""
    if len(items) < (limit or DEFAULT_PAGE_SIZE):
        return None
    last = items[-1]
    return getattr(last, "id", None)


# --------------------------------------------------------------------------- the tree


@router.get("/menu", response_model=MenuTreeResponse)
async def get_menu(
    actor: _ViewDep,
    session: SessionDep,
    response: Response,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    include_inactive: Annotated[bool, Query()] = False,
) -> MenuTreeResponse | Response:
    """The whole menu, in a fixed number of queries and behind an `ETag`.

    **Active-only by default.** A waiter must never see a deactivated dish; a manager must always be
    able to find one, which is what `include_inactive` is for.
    """
    version, categories = await MenuService(session).load_tree(
        actor, include_inactive=include_inactive
    )
    etag = f'W/"{version}"'
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return staff_tree(version, categories, include_inactive=include_inactive)


# --------------------------------------------------------------------------- categories


@router.get("/menu/categories", response_model=MenuCategoryListResponse)
async def list_categories(
    actor: _ViewDep,
    session: SessionDep,
    limit: _LimitDep = None,
    cursor: _CursorDep = None,
    include_inactive: Annotated[bool, Query()] = True,
) -> MenuCategoryListResponse:
    rows = await MenuService(session).list_categories(
        actor, limit=limit, after=cursor, include_inactive=include_inactive
    )
    items = [MenuCategoryResponse.model_validate(row) for row in rows]
    return MenuCategoryListResponse(items=items, next_cursor=_next_cursor(list(rows), limit))


@router.post(
    "/menu/categories",
    response_model=MenuCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    actor: _ManageDep, session: SessionDep, request: MenuCategoryCreateRequest
) -> MenuCategoryResponse:
    category = await MenuService(session).create_category(actor, request)
    await session.commit()
    return MenuCategoryResponse.model_validate(category)


@router.patch("/menu/categories/{category_id}", response_model=MenuCategoryResponse)
async def update_category(
    actor: _ManageDep,
    session: SessionDep,
    category_id: uuid.UUID,
    request: MenuCategoryUpdateRequest,
) -> MenuCategoryResponse:
    """Name, order and active flag. Never the code — `seed/menu.yaml` joins on it."""
    category = await MenuService(session).update_category(actor, category_id, request)
    await session.commit()
    return MenuCategoryResponse.model_validate(category)


# --------------------------------------------------------------------------- items


@router.get("/menu/items", response_model=MenuItemListResponse)
async def list_items(
    actor: _ViewDep,
    session: SessionDep,
    category_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: _LimitDep = None,
    cursor: _CursorDep = None,
    include_inactive: Annotated[bool, Query()] = True,
) -> MenuItemListResponse:
    rows = await MenuService(session).list_items(
        actor,
        category_id=category_id,
        limit=limit,
        after=cursor,
        include_inactive=include_inactive,
    )
    items = [MenuItemResponse.model_validate(row) for row in rows]
    return MenuItemListResponse(items=items, next_cursor=_next_cursor(list(rows), limit))


@router.get("/menu/items/{item_id}", response_model=MenuItemResponse)
async def get_item(actor: _ViewDep, session: SessionDep, item_id: uuid.UUID) -> MenuItemResponse:
    item = await MenuService(session).get_item(actor, item_id)
    return MenuItemResponse.model_validate(item)


@router.post("/menu/items", response_model=MenuItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    actor: _PriceDep, session: SessionDep, request: MenuItemCreateRequest
) -> MenuItemResponse:
    """A dish and the variants it is sold as.

    **`menu.price`, not `menu.manage`**, because the request may carry variants and a variant
    carries a price. Letting a `menu.manage` holder create a dish at ₹1 would walk around the
    permission boundary the P1 design drew.
    """
    item = await MenuService(session).create_item(actor, request)
    await session.commit()
    return MenuItemResponse.model_validate(item)


@router.patch("/menu/items/{item_id}", response_model=MenuItemResponse)
async def update_item(
    actor: _ManageDep, session: SessionDep, item_id: uuid.UUID, request: MenuItemUpdateRequest
) -> MenuItemResponse:
    """Everything about a dish except its code and its price. A manager holds this."""
    item = await MenuService(session).update_item(actor, item_id, request)
    await session.commit()
    return MenuItemResponse.model_validate(item)


@router.post(
    "/menu/items/{item_id}/variants",
    response_model=MenuItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_variant(
    actor: _PriceDep,
    session: SessionDep,
    item_id: uuid.UUID,
    request: MenuItemVariantCreateRequest,
) -> MenuItemResponse:
    item = await MenuService(session).add_variant(actor, item_id, request)
    await session.commit()
    return MenuItemResponse.model_validate(item)


@router.patch("/menu/variants/{variant_id}", response_model=MenuItemResponse)
async def update_variant(
    actor: _PriceDep,
    session: SessionDep,
    variant_id: uuid.UUID,
    request: MenuItemVariantUpdateRequest,
) -> MenuItemResponse:
    """A reprice writes an `audit_log` row with before and after (CLAUDE.md invariant 6).

    Returns the whole dish, because the thing a person needs to see after changing one variant's
    price is that variant *beside its siblings* — a half plate priced above a full one is the error
    this catches.
    """
    item = await MenuService(session).update_variant(actor, variant_id, request)
    await session.commit()
    return MenuItemResponse.model_validate(item)


# --------------------------------------------------------------------------- modifiers


@router.get("/menu/modifier-groups", response_model=ModifierGroupListResponse)
async def list_modifier_groups(
    actor: _ViewDep,
    session: SessionDep,
    limit: _LimitDep = None,
    cursor: _CursorDep = None,
) -> ModifierGroupListResponse:
    rows = await MenuService(session).list_modifier_groups(actor, limit=limit, after=cursor)
    items = [ModifierGroupResponse.model_validate(row) for row in rows]
    return ModifierGroupListResponse(items=items, next_cursor=_next_cursor(list(rows), limit))


@router.post(
    "/menu/modifier-groups",
    response_model=ModifierGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_modifier_group(
    actor: _ManageDep, session: SessionDep, request: ModifierGroupCreateRequest
) -> ModifierGroupResponse:
    group = await MenuService(session).create_modifier_group(actor, request)
    await session.commit()
    return ModifierGroupResponse.model_validate(group)


@router.patch("/menu/modifier-groups/{group_id}", response_model=ModifierGroupResponse)
async def update_modifier_group(
    actor: _ManageDep,
    session: SessionDep,
    group_id: uuid.UUID,
    request: ModifierGroupUpdateRequest,
) -> ModifierGroupResponse:
    group = await MenuService(session).update_modifier_group(actor, group_id, request)
    await session.commit()
    return ModifierGroupResponse.model_validate(group)


@router.post(
    "/menu/modifier-groups/{group_id}/modifiers",
    response_model=ModifierGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_modifier(
    actor: _ManageDep, session: SessionDep, group_id: uuid.UUID, request: ModifierCreateRequest
) -> ModifierGroupResponse:
    group = await MenuService(session).add_modifier(actor, group_id, request)
    await session.commit()
    return ModifierGroupResponse.model_validate(group)


@router.patch("/menu/modifiers/{modifier_id}", response_model=ModifierGroupResponse)
async def update_modifier(
    actor: _ManageDep,
    session: SessionDep,
    modifier_id: uuid.UUID,
    request: ModifierUpdateRequest,
) -> ModifierGroupResponse:
    group = await MenuService(session).update_modifier(actor, modifier_id, request)
    await session.commit()
    return ModifierGroupResponse.model_validate(group)


@router.put("/menu/items/{item_id}/modifier-groups", response_model=MenuItemResponse)
async def attach_modifier_groups(
    actor: _ManageDep,
    session: SessionDep,
    item_id: uuid.UUID,
    request: AttachModifierGroupsRequest,
) -> MenuItemResponse:
    """The whole list, in order. `PUT` because attachment is a set, not a log."""
    item = await MenuService(session).attach_modifier_groups(actor, item_id, request)
    await session.commit()
    return MenuItemResponse.model_validate(item)


@router.post("/menu/categories/{category_id}/modifier-groups", response_model=dict[str, int])
async def bulk_attach_modifier_groups(
    actor: _ManageDep,
    session: SessionDep,
    category_id: uuid.UUID,
    request: BulkAttachRequest,
) -> dict[str, int]:
    """Apply modifier groups to every active dish in a category.

    "All main courses get a spice level" is how an owner describes a menu; the data model is per
    dish so one of them can opt out. This expands the first into the second.
    """
    changed = await MenuService(session).bulk_attach_to_category(actor, category_id, request)
    await session.commit()
    return {"items_updated": changed}
