"""Three questions, once per order.

`docs/customer-experience.md`: "Three questions maximum. Food, service, would-you-return. Free text
optional. **Every extra question halves completion.**" The request schema has no room for a fourth,
which is the cheapest possible way to keep that true.

A second submission returns the first row with `already_submitted: true` rather than an error. The
guest tapped twice on a slow network, and an error screen telling somebody they have already done
the thing they are trying to do is a rudeness.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.guest_deps import GuestSessionDep, OrderScopeDep
from app.core.rate_limit import rate_limit
from app.schemas.guest import GuestFeedbackRequest, GuestFeedbackResponse
from app.services.feedback import GuestFeedbackService

router = APIRouter()


@router.post(
    "/feedback",
    response_model=GuestFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("write"))],
)
async def submit_feedback(
    session: GuestSessionDep, scope: OrderScopeDep, request: GuestFeedbackRequest
) -> GuestFeedbackResponse:
    feedback, already = await GuestFeedbackService(session, scope).submit(
        scope.subject_id,
        food_rating=request.food_rating,
        service_rating=request.service_rating,
        would_return=request.would_return,
        comment=request.comment,
        phone=request.phone,
        consents=request.consents,
        notice_version=request.notice_version,
        notice_language=request.notice_language,
    )
    await session.commit()
    return GuestFeedbackResponse(
        id=feedback.id, submitted_at=feedback.submitted_at, already_submitted=already
    )
