"""Complaints and feedback. `complaint.manage` and `feedback.view`, from the P1 design.

`docs/customer-experience.md`: **"A logged complaint that nobody resolves is worse than no
system."** It is worse because it manufactures evidence that somebody was told and nothing happened.
So the routes here are shaped around the two fields that make a complaint recoverable rather than
recorded — who owns it, and what was done — and `resolved` without a written resolution is refused
by the database, not by a screen.

**A waiter reads feedback and does not own complaints.** A rating is about a table they served, and
somebody who cannot see how their service landed cannot improve it; owning a complaint is an
accountable act that belongs to a manager. The P1 design draws that line and this module follows it.

**`customer_returned` is derived on read and no route writes it.** It becomes true weeks after
everyone has forgotten the complaint; a field somebody must remember to tick would be false for
ever.

**Every write route commits; the service only flushes.**
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.core.tenancy import TenantScope
from app.models.customers import Complaint, Feedback
from app.schemas.customers import (
    ComplaintAssignRequest,
    ComplaintCreateRequest,
    ComplaintListResponse,
    ComplaintResolveRequest,
    ComplaintResponse,
    FeedbackLineResponse,
    FeedbackListResponse,
    FeedbackResponse,
    StaffFeedbackCreateRequest,
)
from app.services.complaints import ComplaintService
from app.services.feedback import StaffFeedbackService

router = APIRouter()

_FeedbackDep = Annotated[Actor, Depends(require_permission(PermissionCode.FEEDBACK_VIEW))]
_ComplaintDep = Annotated[Actor, Depends(require_permission(PermissionCode.COMPLAINT_MANAGE))]


def _scope(actor: Actor) -> TenantScope:
    return TenantScope(organization_id=actor.organization_id, restaurant_id=actor.restaurant_id)


def _feedback(session: SessionDep, actor: Actor) -> StaffFeedbackService:
    return StaffFeedbackService(session, _scope(actor))


def _complaints(session: SessionDep, actor: Actor) -> ComplaintService:
    return ComplaintService(session, _scope(actor))


def _feedback_response(row: Feedback) -> FeedbackResponse:
    return FeedbackResponse(
        id=row.id,
        order_id=row.order_id,
        customer_id=row.customer_id,
        overall_rating=row.overall_rating,
        food_rating=row.food_rating,
        service_rating=row.service_rating,
        cleanliness_rating=row.cleanliness_rating,
        would_return=row.would_return,
        waiter_employee_id=row.waiter_employee_id,
        comment=row.comment,
        source=row.source,
        submitted_at=row.submitted_at,
        business_date=row.business_date,
        lines=[
            FeedbackLineResponse(
                id=line.id,
                order_line_id=line.order_line_id,
                menu_item_variant_id=line.menu_item_variant_id,
                rating=line.rating,
                comment=line.comment,
            )
            for line in row.lines
        ],
    )


def _complaint_response(row: Complaint, *, returned: bool | None) -> ComplaintResponse:
    return ComplaintResponse(
        id=row.id,
        reference=row.reference,
        customer_id=row.customer_id,
        order_id=row.order_id,
        order_line_id=row.order_line_id,
        feedback_id=row.feedback_id,
        category=row.category,
        severity=row.severity,
        description=row.description,
        reported_by=row.reported_by,
        assigned_to=row.assigned_to,
        status=row.status,
        resolution=row.resolution,
        compensation_amount=row.compensation_amount,
        resolved_at=row.resolved_at,
        closed_at=row.closed_at,
        business_date=row.business_date,
        customer_returned=returned,
    )


# --------------------------------------------------------------------------- feedback


@router.get("/feedback", response_model=FeedbackListResponse)
async def list_feedback(
    actor: _FeedbackDep,
    session: SessionDep,
    business_date: Annotated[date, Query()],
    waiter_employee_id: Annotated[uuid.UUID | None, Query()] = None,
) -> FeedbackListResponse:
    """A business day's ratings.

    Not a calendar day: a table that ordered at 1am belongs to the night it ate
    (CLAUDE.md invariant 4).
    """
    rows = await _feedback(session, actor).list_day(
        business_date=business_date, waiter_employee_id=waiter_employee_id
    )
    return FeedbackListResponse(items=[_feedback_response(row) for row in rows])


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def record_feedback(
    actor: _ComplaintDep, session: SessionDep, request: StaffFeedbackCreateRequest
) -> FeedbackResponse:
    """A manager writing down a conversation.

    `source` is fixed by the route and never sent: a `staff` rating is visibly different from a `qr`
    one in every view, because filling the form for a customer is legitimate and hiding that it
    happened is not.
    """
    service = _feedback(session, actor)
    row = await service.record(
        order_id=request.order_id,
        customer_id=request.customer_id,
        overall_rating=request.overall_rating,
        food_rating=request.food_rating,
        service_rating=request.service_rating,
        cleanliness_rating=request.cleanliness_rating,
        would_return=request.would_return,
        comment=request.comment,
    )
    await session.commit()
    return _feedback_response(await service.get(row.id))


# --------------------------------------------------------------------------- complaints


@router.get("/complaints", response_model=ComplaintListResponse)
async def list_complaints(actor: _ComplaintDep, session: SessionDep) -> ComplaintListResponse:
    """What is still open, worst first. A closed complaint is history and belongs to a report."""
    service = _complaints(session, actor)
    rows = await service.list_open()
    return ComplaintListResponse(
        items=[
            _complaint_response(row, returned=await service.returned_after_resolution(row))
            for row in rows
        ]
    )


@router.post("/complaints", response_model=ComplaintResponse, status_code=status.HTTP_201_CREATED)
async def log_complaint(
    actor: _ComplaintDep, session: SessionDep, request: ComplaintCreateRequest
) -> ComplaintResponse:
    service = _complaints(session, actor)
    complaint = await service.create(
        actor,
        category=request.category,
        severity=request.severity,
        description=request.description,
        customer_id=request.customer_id,
        order_id=request.order_id,
        order_line_id=request.order_line_id,
        feedback_id=request.feedback_id,
        assigned_to=request.assigned_to,
    )
    await session.commit()
    fresh = await service.get(complaint.id)
    return _complaint_response(fresh, returned=await service.returned_after_resolution(fresh))


@router.post("/complaints/{complaint_id}/assign", response_model=ComplaintResponse)
async def assign_complaint(
    actor: _ComplaintDep,
    session: SessionDep,
    complaint_id: uuid.UUID,
    request: ComplaintAssignRequest,
) -> ComplaintResponse:
    service = _complaints(session, actor)
    await service.assign(complaint_id, request.assigned_to)
    await session.commit()
    fresh = await service.get(complaint_id)
    return _complaint_response(fresh, returned=await service.returned_after_resolution(fresh))


@router.post("/complaints/{complaint_id}/resolve", response_model=ComplaintResponse)
async def resolve_complaint(
    actor: _ComplaintDep,
    session: SessionDep,
    complaint_id: uuid.UUID,
    request: ComplaintResolveRequest,
) -> ComplaintResponse:
    """What was actually done — a comp, a remake, a refund, an apology.

    Required, and the database agrees: a complaint cannot reach `resolved` with an empty resolution,
    which is the paperwork this module exists to refuse.
    """
    service = _complaints(session, actor)
    await service.resolve(
        complaint_id,
        resolution=request.resolution,
        compensation_amount=request.compensation_amount,
    )
    await session.commit()
    fresh = await service.get(complaint_id)
    return _complaint_response(fresh, returned=await service.returned_after_resolution(fresh))


@router.post("/complaints/{complaint_id}/close", response_model=ComplaintResponse)
async def close_complaint(
    actor: _ComplaintDep, session: SessionDep, complaint_id: uuid.UUID
) -> ComplaintResponse:
    service = _complaints(session, actor)
    await service.close(complaint_id)
    await session.commit()
    fresh = await service.get(complaint_id)
    return _complaint_response(fresh, returned=await service.returned_after_resolution(fresh))
