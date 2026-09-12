"""The stock ledger's endpoints. Every handler is authorise-call-shape and nothing else.

Five permissions, and the split between them comes from `seed/organization.yaml`'s P1 design
rather than from convenience:

- `stock.view` — everyone in the kitchen. Seeing what is on the shelf is the job.
- `stock.receive` — the store manager takes the delivery. **Not the chef.**
- `stock.produce` — the chef makes the gravy. A kitchen turns ingredients into preparations; it
  does not sign for the sack at the door.
- `stock.adjust` — the one movement nobody observed, so it is its own permission, always carries a
  reason, and always writes an audit row.
- `stock.count` — open, record and approve. Approval is refused when the approver is the counter,
  in the service and again by a CHECK constraint, which is a stronger control than a permission
  split would have been: one person holding both permissions is ordinary, one person being both
  people is not.

**There is no PUT and no DELETE anywhere in this file.** The ledger is append-only and the database
enforces it, so a route implying otherwise would be advertising something the server refuses.

**Every write route commits; the service only flushes.** That is this codebase's convention (see
`app/api/v1/staff/employees.py`) and the reason is that a route is the only layer that knows a
request succeeded end to end. The first draft of this module omitted the commits, and the effect
was not a crash but something quieter: every write returned `201` with a populated body and then
vanished, because the session closed without committing. The endpoint tests caught it; no unit test
could have, since inside one transaction the write is visible to the code that made it.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.errors import NotFoundError
from app.core.permissions import PermissionCode
from app.core.tenancy import TenantScope
from app.schemas.inventory import (
    AdjustmentRequest,
    BatchResponse,
    ConsumptionLineResponse,
    ConsumptionResponse,
    CountListResponse,
    CountOpenRequest,
    CountRecordRequest,
    CountResponse,
    ExpiringBatchResponse,
    ExpiringListResponse,
    MovementResponse,
    OnHandListResponse,
    OnHandResponse,
    ProductionRequest,
    ReceiptRequest,
)
from app.services.inventory import InventoryService

router = APIRouter(tags=["stock-ledger"])

_ViewDep = Annotated[Actor, Depends(require_permission(PermissionCode.STOCK_VIEW))]
_ReceiveDep = Annotated[Actor, Depends(require_permission(PermissionCode.STOCK_RECEIVE))]
_ProduceDep = Annotated[Actor, Depends(require_permission(PermissionCode.STOCK_PRODUCE))]
_AdjustDep = Annotated[Actor, Depends(require_permission(PermissionCode.STOCK_ADJUST))]
_CountDep = Annotated[Actor, Depends(require_permission(PermissionCode.STOCK_COUNT))]


def _service(session: SessionDep, actor: Actor) -> InventoryService:
    """The scope comes from the *actor*, never from the request body.

    `docs/security.md` A04: a client that could name its own restaurant_id would be choosing its
    own tenant, which is the #1 bug class in this product wearing a convenient disguise.
    """
    return InventoryService(
        session,
        TenantScope(organization_id=actor.organization_id, restaurant_id=actor.restaurant_id),
    )


# ---------------------------------------------------------------- reads


@router.get("/stock/on-hand", response_model=OnHandListResponse)
async def on_hand(
    session: SessionDep,
    actor: _ViewDep,
    include_zero: Annotated[bool, Query()] = False,
) -> OnHandListResponse:
    rows = await _service(session, actor).on_hand(include_zero=include_zero)
    items = [
        OnHandResponse(
            stock_item_id=row.stock_item_id,
            code=row.code,
            name=row.name,
            base_unit=row.base_unit,
            quantity=row.quantity,
            value=row.value,
            is_negative=row.quantity < 0,
        )
        for row in rows
    ]
    return OnHandListResponse(
        items=items, negative_count=sum(1 for item in items if item.is_negative)
    )


@router.get("/stock/expiring", response_model=ExpiringListResponse)
async def expiring(
    session: SessionDep,
    actor: _ViewDep,
    within_days: Annotated[int, Query(ge=0, le=365)] = 7,
) -> ExpiringListResponse:
    positions = await _service(session, actor).expiring(within_days=within_days)
    return ExpiringListResponse(
        batches=[
            ExpiringBatchResponse(
                batch_id=position.batch_id,
                unit_cost=position.unit_cost,
                remaining=position.remaining,
                expiry_date=position.expiry_date,
            )
            for position in positions
        ]
    )


@router.get("/stock/items/{stock_item_id}/movements", response_model=list[MovementResponse])
async def movements_for_item(
    stock_item_id: uuid.UUID,
    session: SessionDep,
    actor: _ViewDep,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> list[MovementResponse]:
    """Every metric in M13 must drill through to the rows behind it; this is that path.

    The item is resolved before the movements are read, and that is not a formality. Without it
    another tenant's item id returns `200 []` — indistinguishable from an item that exists here and
    has never moved, but a 200 on somebody else's identifier is the shape suite 1 refuses, and it
    is how "does this id exist?" becomes answerable by anyone. The generic suite caught this
    exactly as it was designed to.
    """
    service = _service(session, actor)
    if await service.items.get(stock_item_id) is None:
        raise NotFoundError(
            "stock_item_not_found",
            "That stock item does not exist at this restaurant.",
            {"stock_item_id": str(stock_item_id)},
        )
    rows = await service.movements.for_item(stock_item_id, limit=limit)
    return [MovementResponse.model_validate(row) for row in rows]


# ---------------------------------------------------------------- writes


@router.post("/stock/receipts", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
async def receive(
    payload: ReceiptRequest, session: SessionDep, actor: _ReceiveDep
) -> BatchResponse:
    batch = await _service(session, actor).receive_stock(
        actor,
        stock_item_id=payload.stock_item_id,
        quantity=payload.quantity,
        unit_cost=payload.unit_cost,
        batch_code=payload.batch_code,
        expiry_date=payload.expiry_date,
        storage_location=payload.storage_location,
    )
    await session.commit()
    return BatchResponse.model_validate(batch)


@router.post("/stock/production", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
async def produce(
    payload: ProductionRequest, session: SessionDep, actor: _ProduceDep
) -> BatchResponse:
    batch = await _service(session, actor).produce_batch(
        actor, stock_item_id=payload.stock_item_id, quantity=payload.quantity
    )
    await session.commit()
    return BatchResponse.model_validate(batch)


@router.post(
    "/stock/adjustments", response_model=MovementResponse, status_code=status.HTTP_201_CREATED
)
async def adjust(
    payload: AdjustmentRequest, session: SessionDep, actor: _AdjustDep
) -> MovementResponse:
    movement = await _service(session, actor).adjust(
        actor,
        stock_item_id=payload.stock_item_id,
        quantity_delta=payload.quantity_delta,
        reason=payload.reason,
    )
    await session.commit()
    return MovementResponse.model_validate(movement)


@router.post(
    "/stock/consumption", response_model=ConsumptionResponse, status_code=status.HTTP_201_CREATED
)
async def consume(
    payload: ProductionRequest, session: SessionDep, actor: _AdjustDep
) -> ConsumptionResponse:
    """Take stock out without producing anything — the path M09 (waste) and M07 will use.

    It sits behind `stock.adjust` rather than its own permission because until M07 and M09 exist,
    a hand-written consumption *is* a correction by another name, and inventing a permission the
    design does not name is what `tests/test_permissions_catalogue.py` exists to refuse.
    """
    result = await _service(session, actor).consume(
        actor,
        stock_item_id=payload.stock_item_id,
        quantity=payload.quantity,
        basis="actual",
    )
    await session.commit()
    return ConsumptionResponse(
        lines=[
            ConsumptionLineResponse(
                batch_id=line.batch_id, quantity=line.quantity, unit_cost=line.unit_cost
            )
            for line in result.lines
        ],
        shortfall=result.shortfall,
        total_value=result.total_value,
    )


# ---------------------------------------------------------------- counts


def _count_response(count: object) -> CountResponse:
    return CountResponse.model_validate(count)


@router.post("/stock/counts", response_model=CountResponse, status_code=status.HTTP_201_CREATED)
async def open_count(
    payload: CountOpenRequest, session: SessionDep, actor: _CountDep
) -> CountResponse:
    service = _service(session, actor)
    count = await service.open_count(
        actor, stock_item_ids=payload.stock_item_ids, count_scope=payload.scope
    )
    await session.commit()
    return _count_response(await service.counts.get_with_lines(count.id))


@router.get("/stock/counts", response_model=CountListResponse)
async def list_counts(
    session: SessionDep,
    actor: _ViewDep,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> CountListResponse:
    service = _service(session, actor)
    rows = await service.counts.list_recent(limit=limit)
    counts = [await service.counts.get_with_lines(row.id) for row in rows]
    return CountListResponse(counts=[_count_response(count) for count in counts if count])


@router.get("/stock/counts/{count_id}", response_model=CountResponse)
async def get_count(count_id: uuid.UUID, session: SessionDep, actor: _ViewDep) -> CountResponse:
    count = await _service(session, actor).counts.get_with_lines(count_id)
    if count is None:
        raise NotFoundError("stock_count_not_found", "That stock count does not exist here.")
    return _count_response(count)


@router.patch("/stock/counts/{count_id}", response_model=CountResponse)
async def record_count(
    count_id: uuid.UUID, payload: CountRecordRequest, session: SessionDep, actor: _CountDep
) -> CountResponse:
    service = _service(session, actor)
    await service.record_counted(
        count_id,
        counts={line.stock_item_id: line.counted_quantity for line in payload.lines},
    )
    await session.commit()
    return _count_response(await service.counts.get_with_lines(count_id))


@router.post("/stock/counts/{count_id}/submit", response_model=CountResponse)
async def submit_count(count_id: uuid.UUID, session: SessionDep, actor: _CountDep) -> CountResponse:
    service = _service(session, actor)
    await service.submit_count(count_id)
    await session.commit()
    return _count_response(await service.counts.get_with_lines(count_id))


@router.post("/stock/counts/{count_id}/approve", response_model=CountResponse)
async def approve_count(
    count_id: uuid.UUID, session: SessionDep, actor: _CountDep
) -> CountResponse:
    """Approval is what reaches the ledger, and it is refused when the approver is the counter."""
    service = _service(session, actor)
    await service.approve_count(actor, count_id)
    await session.commit()
    return _count_response(await service.counts.get_with_lines(count_id))
