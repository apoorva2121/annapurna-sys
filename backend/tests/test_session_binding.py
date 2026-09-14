"""A session knows its own id, and one browser never replays its refresh token (B4, remediation R6).

- **The access token names its session** (`sid`). Before, `switch_restaurant` invented an id it did
  not use (backlog row), and a password change could spare the caller's own session only when the
  browser sent its cookie — a native client that holds its refresh token itself lost its own session
  too (finding M2).
- **No grace window** (owner decision D6, 2026-09-14). A rotated refresh token presented again, even
  a moment later, revokes the whole family. Tabs on one device take turns refreshing instead
  (`frontend/src/shared/api.ts`), so one browser never presents a token twice.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import REFRESH_COOKIE
from app.core.security import decode_access_token
from tests.test_employee_endpoints import PASSWORD, _world

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
SWITCH = "/api/v1/auth/switch"
PASSWORD_CHANGE = "/api/v1/auth/password"  # noqa: S105 - a route, not a password


async def _signed_in(client: AsyncClient) -> tuple[str, str]:
    """The access token and the refresh token a sign-in hands back."""
    response = await client.post(
        LOGIN, json={"identifier": "owner@spice-garden.test", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"]), response.cookies[REFRESH_COOKIE]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestTheTokenNamesItsSession:
    async def test_signing_in_and_refreshing_each_name_the_session_they_made(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        access, _ = await _signed_in(api_client)

        refreshed = await api_client.post(REFRESH)

        first = decode_access_token(access).session_id
        second = decode_access_token(refreshed.json()["access_token"]).session_id
        assert first is not None
        assert second is not None
        # A refresh rotates onto a new session row in the same family.
        assert first != second

    async def test_switching_branch_carries_the_session_it_continues(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """No invented id: the switch continues the session the token already names."""
        world = await _world(
            db_session, "owner", second_branch=True, also_at_second={"owner": "manager"}
        )
        assert world.branch is not None
        access, _ = await _signed_in(api_client)

        switched = await api_client.post(
            SWITCH, json={"restaurant_id": str(world.branch.id)}, headers=_bearer(access)
        )

        assert switched.status_code == 200, switched.text
        continued = decode_access_token(switched.json()["access_token"]).session_id
        assert continued == decode_access_token(access).session_id


class TestAPasswordChangeSparesTheCallersSession:
    async def test_a_client_that_sends_no_cookie_keeps_its_own_session(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A native app holds its refresh token itself. The token's `sid` is how the change knows
        which session is the caller's; without it, the app signed itself out by changing its own
        password."""
        await _world(db_session, "owner")
        access, refresh_token = await _signed_in(api_client)
        api_client.cookies.clear()

        changed = await api_client.post(
            PASSWORD_CHANGE,
            json={"current_password": PASSWORD, "new_password": "NewPassword#2026"},
            headers=_bearer(access),
        )
        kept = await api_client.post(REFRESH, json={"refresh_token": refresh_token})

        assert changed.status_code == 204, changed.text
        assert kept.status_code == 200, kept.text


class TestThereIsNoGraceWindow:
    async def test_a_refresh_token_presented_again_a_moment_later_revokes_the_family(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Owner decision D6, and guardrail G-19 as amended by it: a network retry that presents a
        spent token signs the person out everywhere. What stops one browser doing that to itself is
        the tab lock, not a window on the server."""
        await _world(db_session, "owner")
        _, first = await _signed_in(api_client)
        rotated = await api_client.post(REFRESH)
        assert rotated.status_code == 200, rotated.text
        successor = rotated.cookies[REFRESH_COOKIE]

        api_client.cookies.clear()
        api_client.cookies.set(REFRESH_COOKIE, first)
        again = await api_client.post(REFRESH)
        api_client.cookies.clear()
        api_client.cookies.set(REFRESH_COOKIE, successor)
        afterwards = await api_client.post(REFRESH)

        assert again.status_code == 401, again.text
        assert afterwards.status_code == 401, afterwards.text
