"""The guest realm's dependency chain, importing nothing from `app/api/deps.py`.

That last clause is the point, not an aside.

ADR 0009: "Separate route trees, separate middleware stacks, separate dependency chains. No handler
is reachable from both." A shared dependency module is how that separation quietly stops being
true — one helper imported for convenience, and six months later a guest route is one line from an
`Actor`.

So this file constructs no `Actor`, knows no permission string, and cannot be passed to
`require_permission`: `GuestScope` is not an `Actor` and `require_permission` takes an `ActorDep`.
The isolation is a type error, not a convention.

**The token is re-verified against the database on every request**, for the same reason
`current_actor` re-resolves permissions rather than trusting the claim: a token minted before
something changed must stop working now, not in two hours. Here the thing that changes is the
bill. A reprinted bill mints a new order token, and the `tkn` claim is what makes every session
opened from the old QR stop at the next request rather than living out its expiry.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import AppError
from app.core.guest_token import GuestScope, GuestScopeKind, decode_guest_token
from app.core.logging import restaurant_id_var
from app.core.security import ExpiredTokenError, InvalidTokenError
from app.repositories.guest import GuestOrderRepository

# auto_error=False so a missing header produces this application's error envelope rather than
# FastAPI's — the guest surface is the last place to ship a second error shape.
_bearer = HTTPBearer(auto_error=False)

GuestSessionDep = Annotated[AsyncSession, Depends(get_session)]
_CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def _refused() -> AppError:
    """One message for every refusal, deliberately.

    A guest is told that the code has expired and to scan again — never *why*, because the
    difference between "that table does not exist" and "that token is old" is an enumeration oracle
    (`docs/security.md`: "No enumeration").
    """
    return AppError(
        "guest.session_expired",
        "This code is no longer valid. Please scan the QR code again.",
        status_code=401,
    )


async def current_guest(
    session: GuestSessionDep,
    credentials: _CredentialsDep,
) -> GuestScope:
    if credentials is None or not credentials.credentials:
        raise _refused()

    try:
        scope = decode_guest_token(credentials.credentials)
    except (ExpiredTokenError, InvalidTokenError) as exc:
        raise _refused() from exc

    if scope.kind is GuestScopeKind.ORDER:
        await _still_the_current_bill(session, scope)

    # The tenant every log line from here carries. There is no actor: a guest is nobody, by design.
    restaurant_id_var.set(str(scope.restaurant_id))
    return scope


async def _still_the_current_bill(session: AsyncSession, scope: GuestScope) -> None:
    """Through a repository, never a bare select.

    The Definition of Done says tenant scoping goes through the repository layer only, and the
    guest realm is not an exception to that — it is the realm where it matters most.
    `GuestScopedRepository` takes a `GuestScope` and filters on `restaurant_id`, which is all a
    guest token knows.
    """
    orders = GuestOrderRepository(session, scope)
    state = await orders.token_state(scope.subject_id)
    if state is None:
        raise _refused()

    if (
        state.token_hash is None
        or state.expires_at is None
        or state.expires_at <= datetime.now(UTC)
    ):
        raise _refused()
    if scope.token_fingerprint != state.token_hash[:16]:
        # The bill was reprinted. Every session opened from the old QR stops here rather than
        # living out its expiry — which is the whole reason a reprint mints a new token.
        raise _refused()


GuestDep = Annotated[GuestScope, Depends(current_guest)]


def require_order_scope(scope: GuestDep) -> GuestScope:
    """For the two routes that need a bill rather than a table.

    A table token reaching `/guest/order` is not an error a guest can act on — it means they scanned
    the sticker and asked for a bill — so it answers with the same refusal as everything else.
    """
    if scope.kind is not GuestScopeKind.ORDER:
        raise _refused()
    return scope


OrderScopeDep = Annotated[GuestScope, Depends(require_order_scope)]
