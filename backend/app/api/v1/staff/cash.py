"""The till. Every route is `cash.manage`, the permission the M07 spec added to the P1 design.

A waiter holds `order.settle` and takes cash; a waiter never opens, pays out of, closes or adjusts
the till that cash goes into. Owner and manager hold `cash.manage`.

**Payouts and adjustments are idempotent** (ADR 0010): each moves money, and a double tap would move
it twice. Opening and closing need no key — a second open meets the one-open-till index, and a
second close finds the till already closed.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import SessionDep, require_permission
from app.api.idempotency import begin_idempotent
from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.models.orders import CashCount, CashMovement
from app.repositories.base import DEFAULT_PAGE_SIZE
from app.schemas.cash import (
    CashAdjustmentRequest,
    CashCloseRequest,
    CashCountResponse,
    CashMovementResponse,
    CashOpenRequest,
    CashOutsideTillResponse,
    CashPayoutRequest,
    CashSessionListResponse,
    CashSessionResponse,
    CashSessionSummary,
)
from app.schemas.people import AdjusterResponse, PersonResponse
from app.services.cash import CashService, TillPosition
from app.services.people import Person

router = APIRouter(tags=["cash"])

_CashDep = Annotated[Actor, Depends(require_permission(PermissionCode.CASH_MANAGE))]
_LimitDep = Annotated[int | None, Query(ge=1, le=100)]
_CursorDep = Annotated[uuid.UUID | None, Query()]


def _summary_fields(position: TillPosition) -> dict[str, object]:
    till = position.till
    return {
        "id": till.id,
        "status": till.status,
        "opened_at": till.opened_at,
        "opened_by": till.opened_by,
        "opening_float": till.opening_float,
        "business_date": till.business_date,
        "closed_at": till.closed_at,
        "closed_by": till.closed_by,
        "counted_cash": till.counted_cash,
        "variance": till.variance,
        "cash_taken": position.totals.cash_taken,
        "payouts": position.totals.payouts,
        "adjustments": position.totals.adjustments,
        "expected_cash": position.expected,
        "adjusted_variance": position.adjusted_variance,
        "closed_by_person": PersonResponse.of(position.closer),
        "adjusted_by": [
            AdjusterResponse(
                full_name=person.full_name,
                employee_code=person.employee_code,
                roles=list(person.roles),
                by_closer=person.id == till.closed_by,
            )
            for person in position.adjusters
        ],
    }


def _detail(
    position: TillPosition,
    counts: list[CashCount],
    movements: list[CashMovement],
    named: dict[uuid.UUID, Person],
) -> CashSessionResponse:
    return CashSessionResponse.model_validate(
        _summary_fields(position)
        | {
            "counts": [CashCountResponse.model_validate(row) for row in counts],
            "movements": [
                CashMovementResponse.model_validate(row).model_copy(
                    update={
                        "recorded_by_person": PersonResponse.of(named.get(row.recorded_by)),
                        "by_closer": row.recorded_by == position.till.closed_by,
                    }
                )
                for row in movements
            ],
        }
    )


async def _read(service: CashService, till_id: uuid.UUID) -> CashSessionResponse:
    position, counts, movements, named = await service.detail(till_id)
    return _detail(position, list(counts), list(movements), named)


@router.get("/cash/sessions", response_model=CashSessionListResponse)
async def list_sessions(
    actor: _CashDep, session: SessionDep, limit: _LimitDep = None, cursor: _CursorDep = None
) -> CashSessionListResponse:
    positions = await CashService(session, actor.scope).list_tills(limit=limit, after=cursor)
    full = len(positions) >= (limit or DEFAULT_PAGE_SIZE)
    return CashSessionListResponse(
        items=[CashSessionSummary.model_validate(_summary_fields(p)) for p in positions],
        next_cursor=positions[-1].till.id if full and positions else None,
    )


@router.get("/cash/outside-till", response_model=CashOutsideTillResponse)
async def cash_outside_any_till(actor: _CashDep, session: SessionDep) -> CashOutsideTillResponse:
    """Decision D3: cash taken today while no till was open, which no cash-up will ever expect."""
    business_date, amount, payments = await CashService(session, actor.scope).outside_any_till()
    return CashOutsideTillResponse(
        business_date=business_date, cash_taken=amount, payments=payments
    )


@router.post(
    "/cash/sessions", response_model=CashSessionResponse, status_code=status.HTTP_201_CREATED
)
async def open_session(
    actor: _CashDep, session: SessionDep, payload: CashOpenRequest
) -> CashSessionResponse:
    service = CashService(session, actor.scope)
    till_id = await service.open(actor, opening_float=payload.opening_float)
    await session.commit()
    return await _read(service, till_id)


@router.get("/cash/sessions/{session_id}", response_model=CashSessionResponse)
async def get_session(
    actor: _CashDep, session: SessionDep, session_id: uuid.UUID
) -> CashSessionResponse:
    return await _read(CashService(session, actor.scope), session_id)


@router.post("/cash/sessions/{session_id}/close", response_model=CashSessionResponse)
async def close_session(
    actor: _CashDep, session: SessionDep, session_id: uuid.UUID, payload: CashCloseRequest
) -> CashSessionResponse:
    service = CashService(session, actor.scope)
    await service.close(
        actor,
        session_id,
        counts=[(count.denomination, count.quantity) for count in payload.counts],
    )
    await session.commit()
    return await _read(service, session_id)


@router.post(
    "/cash/sessions/{session_id}/payouts",
    response_model=CashSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_payout(
    actor: _CashDep,
    session: SessionDep,
    session_id: uuid.UUID,
    payload: CashPayoutRequest,
    request: Request,
) -> CashSessionResponse | JSONResponse:
    call = await begin_idempotent(request, session, actor)
    if call.replay is not None:
        return call.replay
    service = CashService(session, actor.scope)
    await service.payout(actor, session_id, amount=payload.amount, reason=payload.reason)
    response = await _read(service, session_id)
    await call.complete(status.HTTP_201_CREATED, response)
    await session.commit()
    return response


@router.post(
    "/cash/sessions/{session_id}/adjustments",
    response_model=CashSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_adjustment(
    actor: _CashDep,
    session: SessionDep,
    session_id: uuid.UUID,
    payload: CashAdjustmentRequest,
    request: Request,
) -> CashSessionResponse | JSONResponse:
    call = await begin_idempotent(request, session, actor)
    if call.replay is not None:
        return call.replay
    service = CashService(session, actor.scope)
    await service.adjust(actor, session_id, amount=payload.amount, reason=payload.reason)
    response = await _read(service, session_id)
    await call.complete(status.HTTP_201_CREATED, response)
    await session.commit()
    return response
