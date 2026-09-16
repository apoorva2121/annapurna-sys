"""Regressions for the defects an independent review of M01 found.

Each of these was a real hole, not a style preference, and each is written here before its fix so
that the test is known to catch the thing it claims to catch.

The one worth reading twice is `TestIdentifierSquatting`. Login resolved an identifier across the
whole product and refused one that matched twice, so a trial tenant could lock a real tenant's
owner out using nothing but that owner's email. M01 closed it with a global uniqueness check;
backlog-issues B4 (decision D1) closed it for good by asking which organization only after the
password matches, and the class now proves the attack no longer works rather than that it is
refused.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.errors import AppError, PermissionDeniedError
from app.models.access import EmployeeRoleAssignment
from app.models.identity import Employee, LoginAttempt
from app.repositories.access import AccessRepository
from app.services.auth import AuthService
from app.services.employee import EmployeeService
from tests.test_employee_endpoints import PASSWORD, World, _auth, _role, _token, _world


class TestIdentifierSquatting:
    """Another tenant holding the same identifier must take nothing from its owner.

    Since backlog-issues B4 a login is unique per organization (D1), so a second holder is allowed.
    It is harmless because sign-in matches the *password* before it considers a second account: the
    owner's password matches only the owner's account and goes straight in.
    """

    async def test_a_tenant_may_hold_an_identifier_another_tenant_uses(
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

        assert response.status_code == 201, response.text
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

    async def test_the_refusal_inside_one_organization_does_not_reveal_who_holds_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Inside one organization a login is still unique. The refusal may say it is taken, never
        by whom."""
        await _world(db_session, "manager", slug="tandoor-house")
        attacker_token = await _token(api_client, "manager", slug="tandoor-house")
        first = await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(attacker_token),
            json={
                "full_name": "Sameer Joshi",
                "employee_code": "TAKEN1",
                "joined_on": "2026-01-01",
                "login_identifier": "owner@spice-garden.test",
                "initial_password": "squatted-password",
            },
        )
        assert first.status_code == 201, first.text

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

        assert response.status_code == 409, response.text
        body = response.text.lower()
        for leak in ("sameer", "joshi", "taken1", "organization", "restaurant"):
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

    async def test_five_wrong_passwords_over_http_are_remembered_and_lock_nobody_out(
        self, db_session: AsyncSession, api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P1-1's lockout half, as backlog-issues B5 left it (G-15, decision D28).

        Wrong passwords no longer lock anyone out, but each one must still outlive the request that
        failed: the growing delay is computed from them. Counted here over HTTP, where the rollback
        that first broke the lockout actually happens.
        """

        async def no_wait(_seconds: float) -> None:
            return None

        monkeypatch.setattr("app.services.auth._pause", no_wait)
        await _world(db_session, "owner")

        for _ in range(5):
            refused = await api_client.post(
                "/api/v1/auth/login",
                json={"identifier": "owner@spice-garden.test", "password": "wrong"},
            )
            assert refused.status_code == 401

        signed_in = await api_client.post(
            "/api/v1/auth/login",
            json={"identifier": "owner@spice-garden.test", "password": PASSWORD},
        )

        assert signed_in.status_code == 200, signed_in.text
        failures = await db_session.scalar(
            select(func.count()).select_from(LoginAttempt).where(LoginAttempt.succeeded.is_(False))
        )
        assert failures == 5, (
            "the failed attempts were rolled back with the requests that failed, so the delay "
            "never grows"
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


class TestSeniorityIsOrganizationWide:
    """Authority over a global resource is judged across the whole organization (G-4, P1-2).

    Roles are per branch. A **password**, a **login** and an **employment** are not — they are one
    account, and whoever controls them controls the person everywhere. Judging those by the rank the
    target happens to hold *at the actor's branch* is the bug.

    The attack it allowed: an org admin (rank 10 at head office) who also helps out as a `waiter`
    (rank 40) at branch B is visible to B's managers and resolves to rank 40 there. A manager at B
    resets their password — `may_assign_rank(20, 40)` is true — signs in as them, and arrives at
    head office holding admin permissions. Every audit row afterwards names the victim.

    Every test here is run against the two-branch fixture (G-17). Against a single-branch fixture
    they all pass while the hole is open, which is precisely what happened.
    """

    async def _senior_at_head_office_junior_at_the_branch(
        self, session: AsyncSession
    ) -> tuple[World, str]:
        """The owner is an owner at R1 and a waiter at R2. A manager exists only at R2."""
        world = await _world(
            session,
            "owner",
            second_branch=True,
            at_second={"branch_manager": "manager"},
            also_at_second={"owner": "waiter"},
        )
        return world, "branch_manager"

    async def test_a_branch_manager_cannot_reset_a_senior_person_s_password(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The takeover itself. This is the one that matters."""
        world, attacker = await self._senior_at_head_office_junior_at_the_branch(db_session)
        token = await _token(api_client, attacker)

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['owner'].id}/password",
            headers=_auth(token),
            json={"new_password": "i-am-taking-over"},
        )

        assert response.status_code == 403, (
            "a branch manager reset the password of someone who outranks them organization-wide — "
            "they can now sign in as that person"
        )

    async def test_the_victim_s_password_still_works_afterwards(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A 403 that changed the password anyway would satisfy the test above and lose the
        account, so this asserts the victim can still sign in."""
        world, attacker = await self._senior_at_head_office_junior_at_the_branch(db_session)
        token = await _token(api_client, attacker)

        await api_client.post(
            f"/api/v1/staff/employees/{world.employees['owner'].id}/password",
            headers=_auth(token),
            json={"new_password": "i-am-taking-over"},
        )

        assert await _token(api_client, "owner")

    async def test_a_branch_manager_cannot_deactivate_a_senior_person(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, attacker = await self._senior_at_head_office_junior_at_the_branch(db_session)
        token = await _token(api_client, attacker)

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['owner'].id}/deactivate",
            headers=_auth(token),
        )

        assert response.status_code == 403

    async def test_a_branch_manager_cannot_strip_a_senior_person_s_roles(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Asserted on the surviving roles, not only on the status code.

        A status-only assertion is unsafe here: stripping the victim's last role at this branch
        makes them invisible to the very next read, so a *successful* attack answers 404. The test
        would then pass on the symptom of the thing it is meant to prevent.
        """
        world, attacker = await self._senior_at_head_office_junior_at_the_branch(db_session)
        owner_id = world.employees["owner"].id
        token = await _token(api_client, attacker)

        response = await api_client.post(
            f"/api/v1/staff/employees/{owner_id}/roles",
            headers=_auth(token),
            json={"role_ids": []},
        )

        surviving = (
            await db_session.scalars(
                select(EmployeeRoleAssignment).where(EmployeeRoleAssignment.employee_id == owner_id)
            )
        ).all()
        assert len(list(surviving)) == 2, (
            "the branch manager deleted the owner's role assignments — including the owner role at "
            "head office, which they can neither see nor hold"
        )
        assert response.status_code == 403

    async def test_a_branch_manager_cannot_edit_a_senior_person_s_details(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`update_employee` had no seniority check at all (P1-6). A name and a phone number are
        not harmless: they are how a person is identified on a bill and reached by a supplier."""
        world, attacker = await self._senior_at_head_office_junior_at_the_branch(db_session)
        token = await _token(api_client, attacker)

        response = await api_client.patch(
            f"/api/v1/staff/employees/{world.employees['owner'].id}",
            headers=_auth(token),
            json={"full_name": "Not Their Name"},
        )

        assert response.status_code == 403


class TestPasswordResetRequiresStrictSeniority:
    """Resetting a peer's password is a lateral takeover (P1-6).

    `may_assign_rank` permits equal rank, which is right for appointing: a manager may appoint
    another manager, and lateral appointment is not escalation. It is wrong for a password, because
    acting *as* a peer is indistinguishable in the audit trail from that peer acting.
    """

    async def test_a_manager_cannot_reset_another_manager_s_password(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        # The peer is at the actor's own branch, deliberately: a person the actor cannot see is
        # refused by visibility, and a 404 would let this test pass without the guard existing.
        world = await _world(db_session, "owner", "manager", at_first={"peer": "manager"})
        token = await _token(api_client, "manager")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['peer'].id}/password",
            headers=_auth(token),
            json={"new_password": "acting-as-my-peer"},
        )

        assert response.status_code == 403, (
            "a manager reset a peer manager's password — every action they take as that person is "
            "attributed to the victim"
        )

    async def test_an_owner_may_still_reset_another_owner_s_password(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The deliberate exception. Rank 0 is the top, so 'strictly more senior' would leave two
        owners unable to help each other and a locked-out owner with no recovery at all."""
        world = await _world(db_session, "owner", at_first={"co": "owner"})
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['co'].id}/password",
            headers=_auth(token),
            json={"new_password": "a-fine-new-password"},
        )

        assert response.status_code == 204, response.text

    async def test_an_owner_may_reset_a_junior_password(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}/password",
            headers=_auth(token),
            json={"new_password": "a-fine-new-password"},
        )

        assert response.status_code == 204, response.text


class TestAResetPasswordMustBeChanged:
    """A reset hands someone else's account to whoever performed it, until it is changed.

    Without this, an owner who resets a waiter's password to something temporary can sign in as
    that waiter indefinitely — and every order, void and discount is attributed to the waiter. The
    reset is legitimate; the standing ability to impersonate is not.
    """

    async def test_the_next_login_says_the_password_must_change(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")

        reset = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}/password",
            headers=_auth(owner),
            json={"new_password": "a-temporary-password"},
        )
        assert reset.status_code == 204, reset.text

        signed_in = await api_client.post(
            "/api/v1/auth/login",
            json={"identifier": "waiter@spice-garden.test", "password": "a-temporary-password"},
        )

        assert signed_in.status_code == 200, signed_in.text
        assert signed_in.json()["password_change_required"] is True

    async def test_changing_it_clears_the_requirement(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")
        await api_client.post(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}/password",
            headers=_auth(owner),
            json={"new_password": "a-temporary-password"},
        )
        api_client.cookies.clear()
        first = await api_client.post(
            "/api/v1/auth/login",
            json={"identifier": "waiter@spice-garden.test", "password": "a-temporary-password"},
        )

        changed = await api_client.post(
            "/api/v1/auth/password",
            headers=_auth(first.json()["access_token"]),
            json={
                "current_password": "a-temporary-password",
                "new_password": "one-only-i-know",
            },
        )
        assert changed.status_code == 204, changed.text

        api_client.cookies.clear()
        again = await api_client.post(
            "/api/v1/auth/login",
            json={"identifier": "waiter@spice-garden.test", "password": "one-only-i-know"},
        )

        assert again.json()["password_change_required"] is False

    async def test_a_password_set_at_creation_must_also_be_changed(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The path people actually use, and the one the flag originally missed.

        `reset_password` set `password_reset_required`; creating an employee *with* an initial
        password did not — so the ordinary onboarding flow left the owner holding a working
        credential for that person indefinitely, with nothing on screen to say so. Identical harm to
        P1-6, on the more common path, while the docstring next to the column claimed the rule held.
        """
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")

        created = await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(owner),
            json={
                "full_name": "New Waiter",
                "employee_code": "NEW01",
                "joined_on": "2026-01-01",
                "login_identifier": "new.waiter@spice-garden.test",
                "initial_password": "owner-chose-this",
            },
        )
        assert created.status_code == 201, created.text

        # Assign a role, because a person with none cannot sign in at all (auth.no_restaurant) —
        # create-then-assign is the real onboarding sequence, not a test artefact.
        waiter_role = await _role(db_session, "waiter")
        assigned = await api_client.post(
            f"/api/v1/staff/employees/{created.json()['id']}/roles",
            headers=_auth(owner),
            json={"role_ids": [str(waiter_role.id)]},
        )
        assert assigned.status_code == 200, assigned.text

        signed_in = await api_client.post(
            "/api/v1/auth/login",
            json={"identifier": "new.waiter@spice-garden.test", "password": "owner-chose-this"},
        )

        assert signed_in.status_code == 200, signed_in.text
        assert signed_in.json()["password_change_required"] is True, (
            "the owner chose this password and still knows it, but the person was never asked to "
            "change it"
        )

    async def test_an_employee_created_without_a_login_is_not_flagged(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """ADR 0007's cleaner: no account, so nothing to flag and nothing to prompt."""
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")

        created = await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(owner),
            json={"full_name": "A Cleaner", "employee_code": "CLN01", "joined_on": "2026-01-01"},
        )

        assert created.status_code == 201, created.text
        assert created.json()["has_login"] is False

    async def test_an_ordinary_login_is_not_flagged(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The flag must mean something. If every login carried it, the client would learn to
        ignore it."""
        await _world(db_session, "owner")

        signed_in = await api_client.post(
            "/api/v1/auth/login",
            json={"identifier": "owner@spice-garden.test", "password": PASSWORD},
        )

        assert signed_in.json()["password_change_required"] is False


class TestSeedRespectsIdentifiersItDidNotCreate:
    """Another organization holding a seeded identifier no longer blocks the seed (backlog-issues
    B4, D1): a login is unique per organization, and sign-in asks which one only when the password
    matches both. The seeded owner must still sign straight in."""

    async def test_another_organization_holding_a_seeded_identifier_does_not_block_it(
        self, db_session: AsyncSession
    ) -> None:
        from app.core.enums import UserAccountStatus
        from app.models.identity import UserAccount
        from app.models.tenancy import Organization
        from app.seed.identity import seed_identity

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

        await seed_identity(db_session)

        result = await AuthService(db_session).login("owner@spicegarden.test", "Staging#2026")
        assert result.access_token


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
