"""Authentication endpoints.

These are the only routes in the staff surface without a declared permission, because they are what
produces the token a permission could be checked against. `PUBLIC_ROUTES` names them explicitly, so
the route-declaration suite can tell "deliberately public" apart from "somebody forgot" — an
allow-list of four is auditable in a way that a suite skipping unmarked routes would not be.

The refresh token goes in an httpOnly cookie rather than the response body. Script on the page
cannot read it, which is the difference between an XSS bug costing one 15-minute session and
costing a permanent account takeover.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status

from app.api.deps import ActorDep, SessionDep
from app.core.config import get_settings

# Request-shape only: no cookie and no body is a malformed request, which is the route's concern.
# Everything about whether a *valid* token is still good belongs to AuthService.
from app.core.errors import AppError
from app.schemas.identity import (
    ChooseOrganizationRequest,
    LoginRequest,
    MeResponse,
    OrganizationChoiceResponse,
    OrganizationOption,
    PasswordChangeRequest,
    RefreshRequest,
    RestaurantPageResponse,
    RestaurantSummary,
    SessionResponse,
    SwitchRestaurantRequest,
)
from app.services.auth import AuthService, LoginResult, OrganizationChoiceNeeded

router = APIRouter(tags=["auth"])

REFRESH_COOKIE = "restaurant_os_refresh"

# The deliberate exceptions to "every route declares a permission". Kept as data so the generic
# suite asserts against this list rather than against a habit.
PUBLIC_ROUTES = frozenset(
    {
        "POST /api/v1/auth/login",
        "POST /api/v1/auth/login/choose",
        "POST /api/v1/auth/refresh",
        "POST /api/v1/auth/logout",
    }
)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        httponly=True,
        # Lax rather than Strict: Strict would drop the cookie when someone follows a link into
        # the app from WhatsApp, which is how staff will actually open it.
        samesite="lax",
        secure=not settings.is_local,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        path="/api/v1/auth",
    )


def _session_response(result: LoginResult) -> SessionResponse:
    settings = get_settings()
    return SessionResponse(
        access_token=result.access_token,
        expires_in_seconds=settings.access_token_ttl_minutes * 60,
        employee_id=result.employee.id,
        full_name=result.employee.full_name,
        restaurant=RestaurantSummary.of(result.restaurant),
        roles=list(result.role_codes),
        permissions=sorted(result.permissions),
        password_change_required=result.password_change_required,
    )


def _device(request: Request) -> dict[str, object]:
    return {"user_agent": request.headers.get("user-agent", "")[:200]}


@router.post("/login", response_model=SessionResponse | OrganizationChoiceResponse)
async def login(
    payload: LoginRequest, request: Request, response: Response, session: SessionDep
) -> SessionResponse | OrganizationChoiceResponse:
    """Sign in. When the password opens accounts in more than one organization, the answer is a
    single-use pass and the organizations to choose from — no token and no cookie (B4, D1a)."""
    try:
        result = await AuthService(session).login(
            payload.identifier,
            payload.password,
            ip_address=_client_ip(request),
            device_info=_device(request),
        )
    except OrganizationChoiceNeeded as choice:
        await session.commit()
        return OrganizationChoiceResponse(
            ticket=choice.ticket,
            expires_in_seconds=choice.expires_in_seconds,
            organizations=[
                OrganizationOption(id=each.id, name=each.name) for each in choice.organizations
            ],
        )
    await session.commit()
    _set_refresh_cookie(response, result.refresh_token)
    return _session_response(result)


@router.post("/login/choose", response_model=SessionResponse)
async def choose_organization(
    payload: ChooseOrganizationRequest, request: Request, response: Response, session: SessionDep
) -> SessionResponse:
    """The second step of signing in: the organization chosen, and the pass (B4, D1a)."""
    result = await AuthService(session).choose_organization(
        payload.ticket,
        payload.organization_id,
        ip_address=_client_ip(request),
        device_info=_device(request),
    )
    await session.commit()
    _set_refresh_cookie(response, result.refresh_token)
    return _session_response(result)


@router.post("/refresh", response_model=SessionResponse)
async def refresh(
    request: Request, response: Response, session: SessionDep, payload: RefreshRequest | None = None
) -> SessionResponse:
    # Cookie first, body second: the browser app never sends a body, and a native client that
    # cannot hold cookies can.
    token = request.cookies.get(REFRESH_COOKIE) or (payload.refresh_token if payload else None)
    if not token:
        raise AppError("auth.session_invalid", "Please sign in again.", status_code=401)

    result = await AuthService(session).refresh(token, ip_address=_client_ip(request))
    await session.commit()
    _set_refresh_cookie(response, result.refresh_token)
    return _session_response(result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, session: SessionDep, payload: RefreshRequest | None = None
) -> None:
    token = request.cookies.get(REFRESH_COOKIE) or (payload.refresh_token if payload else None)
    if token:
        await AuthService(session).logout(token)
        await session.commit()
    # Cleared even when there was no token: the outcome a caller wants from logout is "no
    # credential left in this browser", and that must hold however they got here.
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


@router.get("/me", response_model=MeResponse)
async def me(actor: ActorDep, session: SessionDep) -> MeResponse:
    """Everything the client needs to render permission-aware navigation.

    Without this the client would infer what to show from a role name, which ADR 0007 forbids —
    and which breaks the moment an owner customises a role.
    """
    profile = await AuthService(session).profile(actor)
    return MeResponse(
        employee_id=profile.employee.id,
        full_name=profile.employee.full_name,
        employee_code=profile.employee.employee_code,
        restaurant=RestaurantSummary.of(profile.restaurant),
        restaurants=[RestaurantSummary.of(each) for each in profile.restaurants],
        has_more_restaurants=profile.has_more_restaurants,
        roles=list(profile.access.role_codes),
        permissions=sorted(profile.access.permissions),
    )


@router.get("/restaurants", response_model=RestaurantPageResponse)
async def my_restaurants(
    actor: ActorDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[uuid.UUID | None, Query()] = None,
) -> RestaurantPageResponse:
    """Every branch this person may switch to, a page at a time (backlog-issues B3).

    `/auth/me` embeds the first twenty; this is the rest. Authorises itself for the reason
    `/auth/switch` does, and can only ever return the caller's own branches.
    """
    page, next_cursor = await AuthService(session).branches(actor, limit=limit, after=cursor)
    return RestaurantPageResponse(
        items=[RestaurantSummary.of(each) for each in page], next_cursor=next_cursor
    )


@router.post("/switch", response_model=SessionResponse)
async def switch_restaurant(
    payload: SwitchRestaurantRequest,
    actor: ActorDep,
    session: SessionDep,
    request: Request,
) -> SessionResponse:
    """Move this session to another branch the same person works at (finding S12).

    No permission is declared, and that is deliberate rather than an omission: this is authenticated
    and authorises *itself* — the answer depends on where the person is employed, which no single
    permission string can express. It is on the public allow-list in the route-declaration suite for
    the same reason `GET /auth/me` is.

    The refresh cookie is passed down so the choice can be recorded on the session row. Without
    that, the next token refresh would return the person to their home branch mid-task, with
    nothing on screen to explain it.
    """
    result = await AuthService(session).switch_restaurant(
        actor, payload.restaurant_id, request.cookies.get(REFRESH_COOKIE)
    )
    await session.commit()
    # No `_set_refresh_cookie`: the refresh token is unchanged and still valid. Re-issuing the
    # cookie here would be harmless but would imply a rotation that did not happen.
    return _session_response(result)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChangeRequest,
    actor: ActorDep,
    session: SessionDep,
    request: Request,
) -> None:
    service = AuthService(session)
    profile = await service.profile(actor)
    # *This* session is the one the change must not revoke. The access token names it (`sid`,
    # backlog-issues B4), which is what keeps a native client that sends no cookie signed in; the
    # cookie is the fallback for a token minted before tokens carried it.
    session_id = actor.session_id or await service.session_id_for_token(
        request.cookies.get(REFRESH_COOKIE)
    )

    await service.change_own_password(
        profile.employee, session_id, payload.current_password, payload.new_password
    )
    await session.commit()
