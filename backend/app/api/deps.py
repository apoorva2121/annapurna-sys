"""Authentication and authorisation dependencies — the gate every staff route sits behind.

`require_permission()` both *declares* and *enforces*. The declaration matters as much as the
enforcement: it is what lets a test walk the application's own routing table and prove that no
route was registered without a permission. A check written inside a handler body would enforce just
as well and be invisible to that test, which is how the one route that forgot gets shipped.

The handler body still contains no authorisation logic, which is the layering rule's actual
concern (engineering-standards §1). Services receive the `Actor` for rules a single permission
string cannot express — "may this person appoint that role" being the M01 example.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.db import get_session
from app.core.errors import AppError, PermissionDeniedError
from app.core.logging import actor_id_var, restaurant_id_var
from app.core.permissions import PermissionCode
from app.core.security import ExpiredTokenError, InvalidTokenError, decode_access_token
from app.core.tenancy import TenantScope
from app.repositories.access import AccessRepository
from app.repositories.employee import EmployeeRepository

# The attribute a declared permission is stamped with. The route-declaration suite looks for
# exactly this, so renaming it without updating that suite turns the whole guarantee off.
PERMISSION_MARKER = "__required_permission__"

# auto_error=False so a missing header produces our own error envelope rather than FastAPI's,
# which would be the one response in the application with a different shape.
_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
_CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def _unauthenticated() -> AppError:
    return AppError("auth.required", "Please sign in.", status_code=401)


def _session_id(value: str | None) -> uuid.UUID | None:
    """The token's `sid`, or None for a token issued before tokens carried one (B4)."""
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def current_actor(
    session: SessionDep,
    credentials: _CredentialsDep,
) -> Actor:
    """Rebuild the actor from the token, then verify it against the database.

    The permissions in the token are *not* trusted as the final word — they are re-resolved here.
    A token minted before a role change would otherwise keep working until it expired, and
    "revoked immediately" would quietly mean "revoked within fifteen minutes".
    """
    if credentials is None or not credentials.credentials:
        raise _unauthenticated()

    try:
        claims = decode_access_token(credentials.credentials)
    except ExpiredTokenError as exc:
        # A distinct code, because the client's correct response is to refresh rather than to
        # send the user back to the login screen.
        raise AppError("auth.token_expired", "Your session has expired.", status_code=401) from exc
    except InvalidTokenError as exc:
        raise _unauthenticated() from exc

    try:
        employee_id = uuid.UUID(claims.employee_id)
        organization_id = uuid.UUID(claims.organization_id)
        restaurant_id = uuid.UUID(claims.restaurant_id)
    except ValueError as exc:
        raise _unauthenticated() from exc

    scope = TenantScope(organization_id=organization_id, restaurant_id=restaurant_id)
    employee = await EmployeeRepository(session, scope).get_assigned_here(employee_id)
    if employee is None or not employee.is_active:
        # Covers dismissal, and covers a token whose restaurant no longer matches the employee.
        raise _unauthenticated()

    resolved = await AccessRepository(session).resolve(employee.id, restaurant_id)
    # **Set here, and never anywhere before 2026-09-13.** `app/core/logging.py` declared these two
    # variables and its formatter reads them, but nothing ever set them — so every business event
    # and security warning was written with no tenant, while `docs/observability.md` said every line
    # carried one "automatically". This is the one place both facts become known, so it is the one
    # place they are set.
    #
    # They used to be copied onto `request.state` as well, because `BaseHTTPMiddleware` ran the
    # handler in a child task whose context the access line could not see. M08 replaced that
    # middleware with a pure-ASGI one sharing this context (external review M4), so the copy is
    # gone: these two `set` calls are what the access line reads, and the middleware resets them
    # when the request ends.
    restaurant_id_var.set(str(restaurant_id))
    actor_id_var.set(str(employee.id))
    return Actor(
        employee_id=employee.id,
        organization_id=organization_id,
        restaurant_id=restaurant_id,
        full_name=employee.full_name,
        permissions=resolved.permissions,
        rank=resolved.rank,
        session_id=_session_id(claims.session_id),
    )


ActorDep = Annotated[Actor, Depends(current_actor)]


def require_permission(permission: PermissionCode | str) -> Callable[..., Awaitable[Actor]]:
    """Declare and enforce the permission a route needs.

    Returns the dependency function itself rather than a `Depends(...)`, so a route can write
    `actor: Annotated[Actor, Depends(require_permission(...))]` and receive the actor it just
    authorised — no second lookup, and no chance of authorising one actor and acting as another.
    """
    code = str(permission)

    async def dependency(actor: ActorDep) -> Actor:
        if not actor.holds(code):
            # Deliberately does not say which permission is missing. Telling a waiter the exact
            # string that would unlock a screen is a map of the permission model.
            raise PermissionDeniedError("permission.denied", "You do not have access to this.")
        return actor

    setattr(dependency, PERMISSION_MARKER, code)
    return dependency
