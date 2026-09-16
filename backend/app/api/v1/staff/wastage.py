"""Waste. Every handler is authorise-call-shape and nothing else.

Three permissions, and the split between them is the module's main internal control rather than a
convenience:

- `stock.view` — read the reasons, the log and the summary. Everyone in the kitchen and the store.
- `wastage.log` — record something thrown away. Chef, kitchen staff, manager, store manager.
  **A waiter does not hold it**: waste is a kitchen and storeroom event, and a dish a customer sent
  back is recorded by whoever takes it off the bill.
- `wastage.approve` — sign off the expensive reasons. Manager and store manager, and deliberately
  **not** the people who log most of the waste. Logging theft as waste is the one thing this module
  cannot prevent, only make visible and expensive, and an approver who is never the person logging
  is what makes that cost somebody a conversation.

Configuring reasons sits behind `restaurant.configure`, with the tax rates and the floor plan: a
reason carries the *stage* every report groups by, so inventing one is a change to what the
restaurant's numbers mean, not a day-to-day act.

**`POST /wastage` is idempotent** (ADR 0010). It writes the stock ledger, and a double-tapped Log
on a phone in a kitchen is exactly the situation the key exists for.

**Every write route commits; the service only flushes.** This codebase's convention, and the one
M08 broke *again* after `app/api/v1/staff/inventory.py` had documented the symptom in full — every
write returning 201 with a populated body and then vanishing. No unit test catches it, because
inside one transaction the write is visible to the code that made it.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import SessionDep, require_permission
from app.api.idempotency import begin_idempotent
from app.core.actor import Actor
from app.core.enums import WastageStage
from app.core.permissions import PermissionCode
from app.models.waste import WastageEvent, WastageReason
from app.repositories.base import DEFAULT_PAGE_SIZE
from app.repositories.waste import StageTotal
from app.schemas.waste import (
    WastageEventListResponse,
    WastageEventResponse,
    WastageLogRequest,
    WastageReasonCreateRequest,
    WastageReasonListResponse,
    WastageReasonResponse,
    WastageReasonUpdateRequest,
    WastageSummaryLine,
    WastageSummaryResponse,
)
from app.services.waste import WastageService

router = APIRouter(tags=["wastage"])

_VIEW = Annotated[Actor, Depends(require_permission(PermissionCode.STOCK_VIEW))]
_LOG = Annotated[Actor, Depends(require_permission(PermissionCode.WASTAGE_LOG))]
_APPROVE = Annotated[Actor, Depends(require_permission(PermissionCode.WASTAGE_APPROVE))]
_CONFIGURE = Annotated[Actor, Depends(require_permission(PermissionCode.RESTAURANT_CONFIGURE))]

# How far back the summary looks when nobody says. A week, because that is the span of the report
# `docs/waste-model.md` is written around — "this week you lost ₹31,200" — and because a chef
# fixing a batch size wants to see the effect by the next one.
_DEFAULT_DAYS = 7


def _service(session: SessionDep, actor: Actor) -> WastageService:
    """The scope comes from the *actor*, never from the request (`docs/security.md` A04)."""
    return WastageService(session, actor.scope)


def _reason(reason: WastageReason) -> WastageReasonResponse:
    return WastageReasonResponse(
        id=reason.id,
        code=reason.code,
        name=reason.name,
        stage=WastageStage(reason.stage),
        requires_photo=reason.requires_photo,
        requires_approval=reason.requires_approval,
        is_active=reason.is_active,
    )


def _event(event: WastageEvent) -> WastageEventResponse:
    return WastageEventResponse(
        id=event.id,
        stock_item_id=event.stock_item_id,
        stock_batch_id=event.stock_batch_id,
        wastage_reason_id=event.wastage_reason_id,
        reason_code=event.reason.code,
        reason_name=event.reason.name,
        stage=WastageStage(event.reason.stage),
        quantity=Decimal(str(event.quantity)),
        cost_value=Decimal(str(event.cost_value)),
        occurred_at=event.occurred_at,
        business_date=event.business_date,
        reported_by=event.reported_by,
        approved_by=event.approved_by,
        approved_at=event.approved_at,
        awaiting_approval=event.reason.requires_approval and event.approved_at is None,
        note=event.note,
    )


# --------------------------------------------------------------------------- reasons


@router.get("/wastage/reasons", response_model=WastageReasonListResponse)
async def list_reasons(
    session: SessionDep,
    actor: _VIEW,
    include_inactive: Annotated[bool, Query()] = False,
) -> WastageReasonListResponse:
    reasons = await _service(session, actor).reasons(include_inactive=include_inactive)
    return WastageReasonListResponse(items=[_reason(reason) for reason in reasons])


@router.post(
    "/wastage/reasons",
    response_model=WastageReasonResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reason(
    payload: WastageReasonCreateRequest, session: SessionDep, actor: _CONFIGURE
) -> WastageReasonResponse:
    reason = await _service(session, actor).create_reason(
        code=payload.code,
        name=payload.name,
        stage=payload.stage,
        requires_photo=payload.requires_photo,
        requires_approval=payload.requires_approval,
    )
    await session.commit()
    return _reason(reason)


@router.patch("/wastage/reasons/{reason_id}", response_model=WastageReasonResponse)
async def update_reason(
    reason_id: uuid.UUID,
    payload: WastageReasonUpdateRequest,
    session: SessionDep,
    actor: _CONFIGURE,
) -> WastageReasonResponse:
    """Neither the code nor the stage may change — see `WastageReasonUpdateRequest`."""
    reason = await _service(session, actor).update_reason(
        reason_id,
        name=payload.name,
        requires_photo=payload.requires_photo,
        requires_approval=payload.requires_approval,
        is_active=payload.is_active,
    )
    await session.commit()
    return _reason(reason)


# --------------------------------------------------------------------------- the log


@router.post("/wastage", response_model=WastageEventResponse, status_code=status.HTTP_201_CREATED)
async def log_wastage(
    payload: WastageLogRequest, request: Request, session: SessionDep, actor: _LOG
) -> WastageEventResponse | JSONResponse:
    """Record something thrown away, and take it out of stock, in one transaction.

    Idempotent (ADR 0010): a second tap on a stalled connection replays the first record rather
    than booking the waste twice — and double-booked waste is not merely a duplicate row, it is a
    second consumption against the ledger and a food-cost figure that is wrong all month.
    """
    call = await begin_idempotent(request, session, actor)
    if call.replay is not None:
        return call.replay
    service = _service(session, actor)
    event = await service.log(
        actor,
        stock_item_id=payload.stock_item_id,
        wastage_reason_id=payload.wastage_reason_id,
        quantity=payload.quantity,
        per_purchase_unit=payload.per_purchase_unit,
        station_id=payload.station_id,
        menu_item_variant_id=payload.menu_item_variant_id,
        order_line_id=payload.order_line_id,
        note=payload.note,
    )
    response = _event(await service.get(event.id))
    await call.complete(status.HTTP_201_CREATED, response)
    await session.commit()
    return response


@router.post("/wastage/{event_id}/approve", response_model=WastageEventResponse)
async def approve_wastage(
    event_id: uuid.UUID, session: SessionDep, actor: _APPROVE
) -> WastageEventResponse:
    """Sign off waste logged against a reason that wants it.

    Refused when the approver is the person who logged it — the whole value of requiring approval
    on the expensive reasons is that a second person had to look.
    """
    service = _service(session, actor)
    await service.approve(actor, event_id)
    response = _event(await service.get(event_id))
    await session.commit()
    return response


# --------------------------------------------------------------------------- reads


@router.get("/wastage", response_model=WastageEventListResponse)
async def list_wastage(
    session: SessionDep,
    actor: _VIEW,
    business_date: Annotated[date | None, Query()] = None,
    stage: Annotated[WastageStage | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = DEFAULT_PAGE_SIZE,
    after: Annotated[uuid.UUID | None, Query()] = None,
) -> WastageEventListResponse:
    events = await _service(session, actor).list_events(
        business_date=business_date, stage=stage, limit=limit, after=after
    )
    return WastageEventListResponse(
        items=[_event(event) for event in events],
        next_cursor=str(events[-1].id) if len(events) == limit else None,
    )


@router.get("/wastage/summary", response_model=WastageSummaryResponse)
async def wastage_summary(
    session: SessionDep,
    actor: _VIEW,
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
) -> WastageSummaryResponse:
    """What was lost, by stage and then by reason, over a business-date range.

    Never a single total. `docs/waste-model.md`: four stages, each with a different owner and a
    different fix, and "lumping them produces a number nobody can act on".
    """
    service = _service(session, actor)
    end = until or await service.business_date_now()
    start = since or end - timedelta(days=_DEFAULT_DAYS - 1)
    lines = await service.summary(since=start, until=end)
    total = sum((line.cost_value for line in lines), Decimal("0.00"))
    return WastageSummaryResponse(
        since=start,
        until=end,
        total_cost=total,
        lines=[_summary_line(line, total) for line in lines],
    )


def _summary_line(line: StageTotal, total: Decimal) -> WastageSummaryLine:
    """The share is computed here from `Decimal` rather than in SQL.

    A window function would round each row independently and the stages would not add to a hundred,
    which is the first thing anybody checks and the fastest way to lose their trust in the report.
    """
    share = Decimal("0.0") if total == 0 else (line.cost_value / total * 100)
    return WastageSummaryLine(
        stage=WastageStage(line.stage),
        reason_code=line.reason_code,
        reason_name=line.reason_name,
        events=line.events,
        cost_value=line.cost_value,
        share_percent=f"{share:.1f}",
    )
