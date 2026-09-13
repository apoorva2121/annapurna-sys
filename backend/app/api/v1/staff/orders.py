"""Orders at the table. Every handler is authorise-call-shape.

Three permissions, from `seed/organization.yaml`'s P1 design:

- `order.view` — read orders and their provisional bills. The accountant holds this and nothing else
  on this path.
- `order.create` — open an order.
- `order.modify` — everything that changes a live order: its lines, sending, serving, asking for the
  bill, and cancelling an order that never settled.

Discounts, charges and splitting arrive with the second half of chunk E; settlement
(`order.settle`) and voids (`order.void`) are later chunks. None is registered yet, so no route can
exist without its permission.

**Every write returns the whole order, re-read after the commit.** The waiter's screen replaces its
copy with what the server now believes, version included, so the next change is made against the
right version without another request.

**There is no DELETE.** Taking a dish off is `POST .../lines/{line_id}/remove`, because what it does
depends on the kitchen: an unsent line is deleted, a sent one is cancelled with a reason. A method
name that sometimes deletes and sometimes does not would be a lie, and a DELETE carrying a body is
one many clients will not send.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.enums import OrderStatus
from app.core.permissions import PermissionCode
from app.models.orders import Order
from app.repositories.base import DEFAULT_PAGE_SIZE
from app.schemas.orders import (
    OrderCancelRequest,
    OrderCreateRequest,
    OrderLineAddRequest,
    OrderLineRemoveRequest,
    OrderLineResponse,
    OrderLineUpdateRequest,
    OrderListResponse,
    OrderResponse,
    OrderSummaryResponse,
    OrderVersionRequest,
)
from app.services.orders import OrderService

router = APIRouter(tags=["orders"])

_ViewDep = Annotated[Actor, Depends(require_permission(PermissionCode.ORDER_VIEW))]
_CreateDep = Annotated[Actor, Depends(require_permission(PermissionCode.ORDER_CREATE))]
_ModifyDep = Annotated[Actor, Depends(require_permission(PermissionCode.ORDER_MODIFY))]
_LimitDep = Annotated[int | None, Query(ge=1, le=100)]
_CursorDep = Annotated[uuid.UUID | None, Query()]

_SUMMARY_FIELDS = tuple(name for name in OrderSummaryResponse.model_fields if name != "table_ids")


def _service(session: SessionDep, actor: Actor) -> OrderService:
    """The scope comes from the *actor*, never from the request (`docs/security.md` A04)."""
    return OrderService(session, actor.scope)


def _table_ids(order: Order) -> list[uuid.UUID]:
    primary_first = sorted(order.tables, key=lambda link: (not link.is_primary, link.id))
    return [link.restaurant_table_id for link in primary_first]


def _summary(order: Order) -> OrderSummaryResponse:
    fields = {name: getattr(order, name) for name in _SUMMARY_FIELDS}
    return OrderSummaryResponse.model_validate(fields | {"table_ids": _table_ids(order)})


def _detail(order: Order) -> OrderResponse:
    fields = {name: getattr(order, name) for name in _SUMMARY_FIELDS}
    return OrderResponse.model_validate(
        fields
        | {
            "table_ids": _table_ids(order),
            "lines": [OrderLineResponse.model_validate(line) for line in order.lines],
        }
    )


def _next_cursor(items: list[Order], limit: int | None) -> uuid.UUID | None:
    """Only offer a cursor when the page was full, for the reason `api/v1/staff/setup.py` gives."""
    if len(items) < (limit or DEFAULT_PAGE_SIZE):
        return None
    return items[-1].id


# --------------------------------------------------------------------------- reading


@router.get("/orders", response_model=OrderListResponse)
async def list_orders(
    actor: _ViewDep,
    session: SessionDep,
    statuses: Annotated[list[OrderStatus] | None, Query(alias="status")] = None,
    business_date: Annotated[date | None, Query()] = None,
    limit: _LimitDep = None,
    cursor: _CursorDep = None,
) -> OrderListResponse:
    orders = await _service(session, actor).list_orders(
        statuses=statuses, business_date=business_date, limit=limit, after=cursor
    )
    return OrderListResponse(
        items=[_summary(order) for order in orders],
        next_cursor=_next_cursor(list(orders), limit),
    )


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(actor: _ViewDep, session: SessionDep, order_id: uuid.UUID) -> OrderResponse:
    return _detail(await _service(session, actor).get(order_id))


# --------------------------------------------------------------------------- opening


@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    actor: _CreateDep, session: SessionDep, request: OrderCreateRequest
) -> OrderResponse:
    service = _service(session, actor)
    order_id = await service.create(
        actor,
        order_type=request.type,
        table_ids=request.table_ids,
        covers=request.covers,
        channel=request.channel,
        external_order_id=request.external_order_id,
    )
    await session.commit()
    return _detail(await service.get(order_id))


# --------------------------------------------------------------------------- lines


@router.post(
    "/orders/{order_id}/lines", response_model=OrderResponse, status_code=status.HTTP_201_CREATED
)
async def add_line(
    actor: _ModifyDep, session: SessionDep, order_id: uuid.UUID, request: OrderLineAddRequest
) -> OrderResponse:
    service = _service(session, actor)
    await service.add_line(
        order_id,
        version=request.version,
        variant_id=request.menu_item_variant_id,
        quantity=request.quantity,
        modifier_ids=request.modifier_ids,
        special_instructions=request.special_instructions,
    )
    await session.commit()
    return _detail(await service.get(order_id))


@router.patch("/orders/{order_id}/lines/{line_id}", response_model=OrderResponse)
async def update_line(
    actor: _ModifyDep,
    session: SessionDep,
    order_id: uuid.UUID,
    line_id: uuid.UUID,
    request: OrderLineUpdateRequest,
) -> OrderResponse:
    service = _service(session, actor)
    await service.update_line(
        order_id,
        line_id,
        version=request.version,
        changes=request.model_dump(exclude_unset=True, exclude={"version"}),
    )
    await session.commit()
    return _detail(await service.get(order_id))


@router.post("/orders/{order_id}/lines/{line_id}/remove", response_model=OrderResponse)
async def remove_line(
    actor: _ModifyDep,
    session: SessionDep,
    order_id: uuid.UUID,
    line_id: uuid.UUID,
    request: OrderLineRemoveRequest,
) -> OrderResponse:
    service = _service(session, actor)
    await service.remove_line(
        actor, order_id, line_id, version=request.version, reason=request.reason
    )
    await session.commit()
    return _detail(await service.get(order_id))


# --------------------------------------------------------------------------- the evening


@router.post("/orders/{order_id}/send", response_model=OrderResponse)
async def send_order(
    actor: _ModifyDep, session: SessionDep, order_id: uuid.UUID, request: OrderVersionRequest
) -> OrderResponse:
    service = _service(session, actor)
    await service.send(order_id, version=request.version)
    await session.commit()
    return _detail(await service.get(order_id))


@router.post("/orders/{order_id}/served", response_model=OrderResponse)
async def mark_served(
    actor: _ModifyDep, session: SessionDep, order_id: uuid.UUID, request: OrderVersionRequest
) -> OrderResponse:
    service = _service(session, actor)
    await service.mark_served(order_id, version=request.version)
    await session.commit()
    return _detail(await service.get(order_id))


@router.post("/orders/{order_id}/bill", response_model=OrderResponse)
async def request_bill(
    actor: _ModifyDep, session: SessionDep, order_id: uuid.UUID, request: OrderVersionRequest
) -> OrderResponse:
    service = _service(session, actor)
    await service.request_bill(order_id, version=request.version)
    await session.commit()
    return _detail(await service.get(order_id))


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    actor: _ModifyDep, session: SessionDep, order_id: uuid.UUID, request: OrderCancelRequest
) -> OrderResponse:
    service = _service(session, actor)
    await service.cancel(actor, order_id, version=request.version, reason=request.reason)
    await session.commit()
    return _detail(await service.get(order_id))
