"""A QR code, exchanged for a token. The only route reachable without one.

Two codes, two lifetimes, two powers (`docs/modules/M10-customers-spec.md` decision 1). The sticker
on the table grants the menu — which is on the wall anyway — and the QR on the bill grants that one
bill and one feedback, and dies with it.

**One refusal for everything.** A slug that does not exist, a slug on a deactivated table, a token
that expired, a token for an order that was voided: all answer identically. `docs/security.md`: "No
enumeration — guest lookups return the same response whether or not the [thing] exists." A guest
cannot act on the difference anyway; they scan again or ask a waiter.

**The write tier**, because this is the route an attacker would hammer: it is the only one that can
be reached without already holding a token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.guest_deps import GuestSessionDep
from app.core.errors import AppError
from app.core.rate_limit import rate_limit
from app.schemas.guest import GuestSessionRequest, GuestSessionResponse
from app.services.guest_session import GuestSessionService

router = APIRouter()


@router.post(
    "/session",
    response_model=GuestSessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("write"))],
)
async def open_session(
    session: GuestSessionDep, request: GuestSessionRequest
) -> GuestSessionResponse:
    """One of the two codes, never both and never neither."""
    given = [value for value in (request.table_slug, request.order_token) if value]
    if len(given) != 1:
        raise AppError(
            "guest.session_expired",
            "This code is no longer valid. Please scan the QR code again.",
            status_code=401,
        )

    service = GuestSessionService(session)
    if request.table_slug is not None:
        opened = await service.from_table_slug(request.table_slug)
    else:
        # Exactly one of the two was given, checked above, so this is the order token.
        opened = await service.from_order_token(request.order_token or "")

    await session.commit()
    return GuestSessionResponse(
        token=opened.token,
        expires_at=opened.expires_at,
        # Public: it is on the door. Nothing else about the restaurant is here.
        restaurant_name=opened.restaurant_name,
        scope=opened.scope,
    )
