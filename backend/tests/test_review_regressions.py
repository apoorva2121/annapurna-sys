"""Regressions for the defects an independent review of M01 found.

Each of these was a real hole, not a style preference, and each is written here before its fix so
that the test is known to catch the thing it claims to catch.

The one worth reading twice is `TestIdentifierSquatting`. Login resolves an identifier across the
whole product, but the clash check when creating a login only looked inside the actor's own
organization — so a trial tenant could permanently lock a real tenant's owner out of their account
using nothing but that owner's email address.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.errors import AppError, PermissionDeniedError
from app.models.identity import Employee
from app.repositories.access import AccessRepository
from app.services.auth import AuthService
from app.services.employee import EmployeeService
from tests.test_employee_endpoints import PASSWORD, World, _auth, _token, _world


class TestIdentifierSquatting:
    """One tenant must not be able to take an identifier that belongs to another.

    `AuthService._find_account` searches every organization and refuses a match that appears
    twice. That is safe by itself. It stops being safe the moment another tenant can *create* the
    second match on purpose.
    """

    async def test_a_tenant_cannot_claim_an_identifier_another_tenant_already_uses(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The attack, end to end.

        A manager at Tandoor House adds an employee whose login is the Spice Garden owner's email.
        Nothing about it looks unusual; they are entitled to create employees in their own
        organization. From that moment the Spice Garden owner cannot sign in — two accounts match
        the identifier, the lookup refuses an ambiguous match, and there is no self-service repair.
        """
        victim = await _world(db_session, "owner", slug="spice-garden")
        await _world(db_session, "manager", slug="tandoor-house")
        attacker_token = await _token(api_client, "manager", slug="tandoor-house")

        response = await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(attacker_token),
            json={
                "full_name": "Not A Real Person",
                "employee_code": "SQUAT1",
                "joined_on": "2026-01-01",
                # The victim's identifier, in the attacker's organization.
                "login_identifier": "owner@spice-garden.test",
                "initial_password": "squatted-password",
            },
        )

        assert response.status_code == 409, (
            "a login identifier already in use by another tenant must be refused; "
            f"the server answered {response.status_code}"
        )
        assert victim.employees["owner"] is not None

    async def test_the_victim_can_still_sign_in_afterwards(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The property that actually matters. The test above could be satisfied by any 409; this
        one fails unless the owner's account is genuinely untouched."""
        await _world(db_session, "owner", slug="spice-garden")
        await _world(db_session, "manager", slug="tandoor-house")
        attacker_token = await _token(api_client, "manager", slug="tandoor-house")

        await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(attacker_token),
            json={
                "full_name": "Not A Real Person",
                "employee_code": "SQUAT2",
                "joined_on": "2026-01-01",
                "login_identifier": "owner@spice-garden.test",
                "initial_password": "squatted-password",
            },
        )

        result = await AuthService(db_session).login("owner@spice-garden.test", PASSWORD)
        assert result.access_token

    async def test_the_refusal_does_not_reveal_which_tenant_holds_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Closing the lockout must not open an enumeration oracle in its place: the message may
        say the identifier is taken, never by whom."""
        await _world(db_session, "owner", slug="spice-garden")
        await _world(db_session, "manager", slug="tandoor-house")
        attacker_token = await _token(api_client, "manager", slug="tandoor-house")

        response = await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(attacker_token),
            json={
                "full_name": "Not A Real Person",
                "employee_code": "SQUAT3",
                "joined_on": "2026-01-01",
                "login_identifier": "owner@spice-garden.test",
                "initial_password": "squatted-password",
            },
        )

        body = response.text.lower()
        for leak in ("spice", "garden", "organization", "another tenant", "restaurant"):
            assert leak not in body, f"the refusal named {leak!r}"


class TestReactivationRespectsSeniority:
    """`deactivate_employee` refuses to touch someone more senior. `reactivate_employee` did not.

    Not an escalation on its own — sessions stay revoked — but it lets a junior insider undo an
    offboarding decision an owner made, which is attacker 1 and 4 in docs/security.md.
    """

    async def test_a_manager_cannot_reactivate_an_owner(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "owner", "manager")
        service = EmployeeService(db_session)
        owner = world.employees["owner"]
        owner.is_active = False
        await db_session.flush()

        actor = await _actor_for(db_session, world, "manager")

        with pytest.raises(PermissionDeniedError):
            await service.reactivate_employee(actor, owner.id)

    async def test_an_owner_can_still_reactivate_a_manager(self, db_session: AsyncSession) -> None:
        """The guard must not break the legitimate direction."""
        world = await _world(db_session, "owner", "manager")
        service = EmployeeService(db_session)
        manager = world.employees["manager"]
        manager.is_active = False
        await db_session.flush()

        actor = await _actor_for(db_session, world, "owner")
        reactivated = await service.reactivate_employee(actor, manager.id)

        assert reactivated.is_active is True


class TestSeedRefusesRealEnvironments:
    """The seed creates active logins whose password is committed to this repository.

    Exactly the shape of defect 5 in this module's build log — the committed JWT secret that would
    have shipped to staging. `is_demo` keeps these organizations out of reports; it does nothing to
    stop anyone who has read the repository signing in as an owner.
    """

    async def test_it_refuses_to_seed_a_non_local_environment(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core.config import Environment, get_settings
        from app.seed.identity import seed_identity

        monkeypatch.setenv("ENV", Environment.STAGING.value)
        monkeypatch.setenv("JWT_SECRET", "a-real-staging-secret-at-least-32-bytes-long")
        get_settings.cache_clear()
        try:
            with pytest.raises(AppError) as caught:
                await seed_identity(db_session)
            assert "local" in str(caught.value).lower()
        finally:
            get_settings.cache_clear()

    async def test_it_still_seeds_locally(self, db_session: AsyncSession) -> None:
        from app.seed.identity import seed_identity

        summary = await seed_identity(db_session)

        assert summary.organizations_created == 2


class TestSeedDoesNotResurrectRemovedRoles:
    """Re-running the seed must not re-grant a role a human deliberately removed.

    The assignment key is (employee, restaurant, role), so a removed grant looks exactly like one
    that was never created. Demote someone through the UI, re-run `make seed`, and they are
    promoted again — with no audit row, because the seed does not write one.
    """

    async def test_a_removed_role_stays_removed(self, db_session: AsyncSession) -> None:
        from app.models.access import EmployeeRoleAssignment
        from app.seed.identity import seed_identity

        await seed_identity(db_session)
        employee = await db_session.scalar(
            select(Employee).where(Employee.employee_code == "EMP003")
        )
        assert employee is not None
        for assignment in (
            await db_session.scalars(
                select(EmployeeRoleAssignment).where(
                    EmployeeRoleAssignment.employee_id == employee.id
                )
            )
        ).all():
            await db_session.delete(assignment)
        await db_session.flush()

        await seed_identity(db_session)

        remaining = (
            await db_session.scalars(
                select(EmployeeRoleAssignment).where(
                    EmployeeRoleAssignment.employee_id == employee.id
                )
            )
        ).all()
        assert list(remaining) == [], (
            "the seed re-granted a role that had been deliberately removed"
        )


REFRESH_COOKIE = "restaurant_os_refresh"


def _present(client: AsyncClient, token: str) -> None:
    """Make the client send exactly this refresh token on the next request.

    Set on the jar rather than passed per-request: httpx deprecated per-request cookies because the
    persistence semantics are ambiguous, and this suite turns warnings into errors.
    """
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, token)


class TestFailedRequestsPersistTheirBookkeeping:
    """A write that must survive a failed request is committed by the service before it raises.

    Guardrail G-1. Every route in this application follows *service flushes, route commits*, which
    is correct until the request fails: the route never reaches `commit()`, FastAPI re-raises at the
    dependency's `yield`, and `get_session` closes the session — rolling the flush back.

    Both halves of P1-1 live here. The lockout half was found by running the manual script by hand
    and fixed in `b01a8b0`; `tests/test_lockout_persistence.py` proves it at the service level and
    this class proves it over HTTP. The replay half was found by an external audit and is fixed
    here.

    These tests are only meaningful because the `api` fixture opens one session per request. Under
    the shared session it replaced, both would pass against the broken code.
    """

    async def test_five_wrong_passwords_over_http_lock_the_account(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")

        for _ in range(5):
            refused = await api_client.post(
                "/api/v1/auth/login",
                json={"identifier": "owner@spice-garden.test", "password": "wrong"},
            )
            assert refused.status_code == 401

        locked = await api_client.post(
            "/api/v1/auth/login",
            json={"identifier": "owner@spice-garden.test", "password": PASSWORD},
        )

        assert locked.status_code == 429, (
            "the correct password signed in after five failures — the failure counter was rolled "
            "back with the request that failed, so the threshold is never reached"
        )

    async def test_a_replayed_refresh_token_kills_the_family_over_http(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The half that was still open.

        `_handle_replay` revokes every session descended from one login, then the caller raises 401
        — and the revocation dies with the request. The consequence is backwards: the thief who
        presents the stolen token *first* gets a working session, and the revocation that was
        supposed to protect the real user is discarded. Only the real user is inconvenienced, and
        only by having their own later refresh rejected.
        """
        await _world(db_session, "owner")
        signed_in = await api_client.post(
            "/api/v1/auth/login",
            json={"identifier": "owner@spice-garden.test", "password": PASSWORD},
        )
        assert signed_in.status_code == 200
        stolen = signed_in.cookies[REFRESH_COOKIE]

        rotated = await api_client.post("/api/v1/auth/refresh")
        assert rotated.status_code == 200
        successor = rotated.cookies[REFRESH_COOKIE]
        assert successor != stolen, "the refresh token did not rotate"

        # The thief presents the token that was already spent. This is detected — and the whole
        # family is supposed to die with it.
        _present(api_client, stolen)
        replayed = await api_client.post("/api/v1/auth/refresh")
        assert replayed.status_code == 401

        # The legitimate successor must now be dead too. If it still works, the revocation was
        # rolled back and a stolen token costs the victim nothing but buys the thief a session.
        _present(api_client, successor)
        after = await api_client.post("/api/v1/auth/refresh")

        assert after.status_code == 401, (
            "the session family survived a replayed refresh token — the revocation was rolled back "
            "with the 401 that reported it"
        )


class TestSeedRespectsIdentifiersItDidNotCreate:
    """The seed writes `UserAccount` rows directly, so it bypasses `_create_login`'s global check.

    Bounded by `_refuse_outside_local`, so this is demo breakage rather than a security hole — but
    the failure is the silent kind: `make seed` reports success and the owner it just "created"
    can never sign in, because two accounts now match that identifier.
    """

    async def test_it_refuses_when_another_account_already_holds_a_seeded_identifier(
        self, db_session: AsyncSession
    ) -> None:
        from app.core.enums import UserAccountStatus
        from app.models.identity import UserAccount
        from app.models.tenancy import Organization
        from app.seed.identity import ConflictingSeedIdentifierError, seed_identity

        squatter = Organization(name="Somebody Else", slug="somebody-else")
        db_session.add(squatter)
        await db_session.flush()
        db_session.add(
            UserAccount(
                organization_id=squatter.id,
                email="owner@spicegarden.test",
                status=UserAccountStatus.ACTIVE,
            )
        )
        await db_session.flush()

        with pytest.raises(ConflictingSeedIdentifierError) as caught:
            await seed_identity(db_session)

        # The message has to name the identifier, or the person running `make seed` has no way to
        # find the row that is blocking it.
        assert "owner@spicegarden.test" in str(caught.value)


async def _actor_for(session: AsyncSession, world: World, role_code: str) -> Actor:
    """Build the Actor the service expects, the way current_actor would."""
    employee = world.employees[role_code]
    resolved = await AccessRepository(session).resolve(employee.id, world.restaurant.id)
    return Actor(
        employee_id=employee.id,
        organization_id=world.organization.id,
        restaurant_id=world.restaurant.id,
        full_name=employee.full_name,
        permissions=resolved.permissions,
        rank=resolved.rank,
    )
