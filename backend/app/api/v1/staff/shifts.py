"""The roster and the clock. Authorise, call, shape — nothing else.

**Two permissions, and the P1 design has both.** `shift.view` is held by every role, which is one
deliberate widening of the design's grant and the M12 spec records why: a roster nobody can read is
a noticeboard in a locked room, and the clock-in button is useless to the person it exists for if a
permission stands in front of it. The widening is safe because **the permission opens the screen
and the scope decides the content** — a front-line role sees its own assignments and who is
covering which section, while staffing, statuses and corrections stay behind `shift.manage`.

**There is no `shift.clock`.** Clocking in declares `shift.view`, and the service enforces that the
assignment is the actor's own. A permission cannot express "your row, not his"; a service can, and
that is the only control that matters here.

**Every write route commits; the service only flushes.** This codebase's convention.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.enums import ShiftAssignmentStatus
from app.core.permissions import PermissionCode
from app.core.shift_window import crosses_midnight
from app.models.shifts import Shift, ShiftAssignment
from app.schemas.shifts import (
    AssignmentCreateRequest,
    AssignmentResponse,
    AssignmentStatusRequest,
    AssignmentUpdateRequest,
    OnNowEntry,
    OnNowResponse,
    RosterResponse,
    ShiftCreateRequest,
    ShiftListResponse,
    ShiftResponse,
    ShiftUpdateRequest,
)
from app.services.people import Person, people
from app.services.shifts import ShiftService

router = APIRouter(tags=["shifts"])

_VIEW = Annotated[Actor, Depends(require_permission(PermissionCode.SHIFT_VIEW))]
_MANAGE = Annotated[Actor, Depends(require_permission(PermissionCode.SHIFT_MANAGE))]


def _service(session: SessionDep, actor: Actor) -> ShiftService:
    """The scope comes from the *actor*, never from the request (`docs/security.md` A04)."""
    return ShiftService(session, actor.scope)


def _shift(shift: Shift) -> ShiftResponse:
    return ShiftResponse(
        id=shift.id,
        name=shift.name,
        start_time=shift.start_time,
        end_time=shift.end_time,
        crosses_midnight=crosses_midnight(shift.start_time, shift.end_time),
        is_active=shift.is_active,
    )


async def _assignments(
    session: SessionDep,
    actor: Actor,
    service: ShiftService,
    rows: Sequence[ShiftAssignment],
) -> list[AssignmentResponse]:
    """Names and shifts for a whole page in two queries, not two per row."""
    names = await people(session, actor.scope, [row.employee_id for row in rows])
    shifts = {shift.id: shift for shift in await service.shifts(include_inactive=True)}
    return [_assignment(row, shifts[row.shift_id], names) for row in rows]


def _assignment(
    assignment: ShiftAssignment, shift: Shift, names: dict[uuid.UUID, Person]
) -> AssignmentResponse:
    person = names.get(assignment.employee_id)
    return AssignmentResponse(
        id=assignment.id,
        shift_id=assignment.shift_id,
        shift_name=shift.name,
        start_time=shift.start_time,
        end_time=shift.end_time,
        employee_id=assignment.employee_id,
        employee_name=person.full_name if person else None,
        dining_area_id=assignment.dining_area_id,
        business_date=assignment.business_date,
        status=ShiftAssignmentStatus(assignment.status),
        clock_in_at=assignment.clock_in_at,
        clock_out_at=assignment.clock_out_at,
        is_open=assignment.clock_in_at is not None and assignment.clock_out_at is None,
    )


# --------------------------------------------------------------------------- shifts


@router.get("/shifts", response_model=ShiftListResponse)
async def list_shifts(
    session: SessionDep,
    actor: _VIEW,
    include_inactive: Annotated[bool, Query()] = False,
) -> ShiftListResponse:
    shifts = await _service(session, actor).shifts(include_inactive=include_inactive)
    return ShiftListResponse(items=[_shift(shift) for shift in shifts])


@router.post("/shifts", response_model=ShiftResponse, status_code=status.HTTP_201_CREATED)
async def create_shift(
    payload: ShiftCreateRequest, session: SessionDep, actor: _MANAGE
) -> ShiftResponse:
    shift = await _service(session, actor).create_shift(
        name=payload.name, start=payload.start_time, end=payload.end_time
    )
    response = _shift(shift)
    await session.commit()
    return response


@router.patch("/shifts/{shift_id}", response_model=ShiftResponse)
async def update_shift(
    shift_id: uuid.UUID, payload: ShiftUpdateRequest, session: SessionDep, actor: _MANAGE
) -> ShiftResponse:
    shift = await _service(session, actor).update_shift(
        shift_id,
        name=payload.name,
        start=payload.start_time,
        end=payload.end_time,
        is_active=payload.is_active,
    )
    response = _shift(shift)
    await session.commit()
    return response


# ---------------------------------------------------------------------- the roster


@router.get("/shifts/roster", response_model=RosterResponse)
async def roster(
    session: SessionDep,
    actor: _VIEW,
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
) -> RosterResponse:
    """A date range of assignments. Bounded like every other list here."""
    service = _service(session, actor)
    rows = await service.roster(since=since, until=until)
    items = await _assignments(session, actor, service, rows)
    return RosterResponse(
        since=since or await service.today(),
        until=until or (items[-1].business_date if items else await service.today()),
        items=items,
    )


@router.get("/shifts/me", response_model=RosterResponse)
async def my_shifts(session: SessionDep, actor: _VIEW) -> RosterResponse:
    """Mine, today first. The screen a waiter opens at eleven in the morning."""
    service = _service(session, actor)
    rows = await service.mine(actor)
    items = await _assignments(session, actor, service, rows)
    today = await service.today()
    return RosterResponse(since=today, until=today, items=items)


@router.get("/shifts/on-now", response_model=OnNowResponse)
async def on_now(session: SessionDep, actor: _VIEW) -> OnNowResponse:
    """Who is covering which section right now — the manager's glance, and the lookup that
    auto-assignment uses when an order is opened."""
    service = _service(session, actor)
    rows = await service.on_now()
    names = await people(session, actor.scope, [row.assignment.employee_id for row in rows])
    return OnNowResponse(
        business_date=await service.today(),
        items=[
            OnNowEntry(
                assignment_id=row.assignment.id,
                employee_id=row.assignment.employee_id,
                employee_name=(
                    names[row.assignment.employee_id].full_name
                    if row.assignment.employee_id in names
                    else None
                ),
                shift_name=row.shift.name,
                dining_area_id=row.assignment.dining_area_id,
                status=ShiftAssignmentStatus(row.assignment.status),
            )
            for row in rows
        ],
    )


@router.post(
    "/shifts/assignments", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED
)
async def create_assignment(
    payload: AssignmentCreateRequest, session: SessionDep, actor: _MANAGE
) -> AssignmentResponse:
    service = _service(session, actor)
    assignment = await service.assign(
        shift_id=payload.shift_id,
        employee_id=payload.employee_id,
        business_date=payload.business_date,
        dining_area_id=payload.dining_area_id,
    )
    response = (await _assignments(session, actor, service, [assignment]))[0]
    await session.commit()
    return response


@router.patch("/shifts/assignments/{assignment_id}", response_model=AssignmentResponse)
async def correct_assignment(
    assignment_id: uuid.UUID,
    payload: AssignmentUpdateRequest,
    session: SessionDep,
    actor: _MANAGE,
) -> AssignmentResponse:
    """A manager fixing a time. Needs a reason, and writes an audit row naming both values —
    because asserting somebody else's attendance is not the same act as clocking in, and the
    record must not make the two look alike."""
    service = _service(session, actor)
    assignment = await service.correct(
        actor,
        assignment_id,
        clock_in_at=payload.clock_in_at,
        clock_out_at=payload.clock_out_at,
        dining_area_id=payload.dining_area_id,
        reason=payload.reason,
    )
    response = (await _assignments(session, actor, service, [assignment]))[0]
    await session.commit()
    return response


@router.post("/shifts/assignments/{assignment_id}/status", response_model=AssignmentResponse)
async def set_assignment_status(
    assignment_id: uuid.UUID,
    payload: AssignmentStatusRequest,
    session: SessionDep,
    actor: _MANAGE,
) -> AssignmentResponse:
    service = _service(session, actor)
    assignment = await service.set_status(actor, assignment_id, payload.status)
    response = (await _assignments(session, actor, service, [assignment]))[0]
    await session.commit()
    return response


@router.delete("/shifts/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(
    assignment_id: uuid.UUID, session: SessionDep, actor: _MANAGE
) -> Response:
    """Only before it starts. Afterwards it is a record, and the way to say somebody did not work
    is `absent` — which has an author."""
    await _service(session, actor).unassign(assignment_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------------- the clock


@router.post("/shifts/assignments/{assignment_id}/clock-in", response_model=AssignmentResponse)
async def clock_in(
    assignment_id: uuid.UUID, session: SessionDep, actor: _VIEW
) -> AssignmentResponse:
    """**No body, and no employee id in it.** Clocking somebody else in is not a permission that
    could be granted by mistake; it is an endpoint that does not exist."""
    service = _service(session, actor)
    assignment = await service.clock_in(actor, assignment_id)
    response = (await _assignments(session, actor, service, [assignment]))[0]
    await session.commit()
    return response


@router.post("/shifts/assignments/{assignment_id}/clock-out", response_model=AssignmentResponse)
async def clock_out(
    assignment_id: uuid.UUID, session: SessionDep, actor: _VIEW
) -> AssignmentResponse:
    service = _service(session, actor)
    assignment = await service.clock_out(actor, assignment_id)
    response = (await _assignments(session, actor, service, [assignment]))[0]
    await session.commit()
    return response
