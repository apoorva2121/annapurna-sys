"""Withdrawal, and only withdrawal.

`docs/compliance-rules.md` §B2 asks that withdrawing be as easy as granting, and this is that route:
one tap, on the screen the guest is already looking at, with no email and no waiter in between.

**It cannot grant, and the request schema has nowhere to say so.** An anonymous surface cannot know
whose phone is in whose hand, and a grant is a claim about a person. The only place a guest grants
anything is the feedback form they typed their own number into
(`docs/modules/M10-customers-spec.md` decision 4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.guest_deps import GuestSessionDep, OrderScopeDep
from app.core.rate_limit import rate_limit
from app.schemas.guest import GuestConsentResponse, GuestConsentWithdrawRequest
from app.services.feedback import GuestFeedbackService

router = APIRouter()


@router.post(
    "/consent", response_model=GuestConsentResponse, dependencies=[Depends(rate_limit("write"))]
)
async def withdraw_consent(
    session: GuestSessionDep, scope: OrderScopeDep, request: GuestConsentWithdrawRequest
) -> GuestConsentResponse:
    consent = await GuestFeedbackService(session, scope).withdraw(
        scope.subject_id,
        purpose=request.purpose,
        notice_version=request.notice_version,
        notice_language=request.notice_language,
    )
    await session.commit()
    return GuestConsentResponse(
        purpose=consent.purpose,
        granted=consent.granted,
        occurred_at=consent.occurred_at,
    )
