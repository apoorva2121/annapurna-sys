"""`POST /auth/switch` — moving a session to another branch of the same organization.

Finding S12. `_home_restaurant` picks a person's *first* restaurant, so someone employed at two
branches could never reach the second one at all.

**Guardrail G-17 applies to every test here.** This is identity-touching, and identity bugs in this
product have twice been invisible to a single-branch fixture: rank is per branch while a password, a
login and an employment are not. So the world below is two organizations with two branches each,
and the interesting person is senior at one branch and junior at another — the shape P1-2 exploited.

The four things that must hold, in order of how badly they fail:

1. **A restaurant in another organization is refused.** This is the tenant boundary. A 404, not a
   403, because a 403 would confirm the id names something real.
2. **A branch in my own organization that I hold no role at is refused.** Being employed by the
   company is not the same as working at that branch.
3. **Permissions are re-resolved at the target.** An owner at R1 who is a waiter at R2 must act as a
   waiter at R2. Carrying the old permissions across would be privilege escalation by navigation.
4. **The switch survives a token refresh.** Access tokens live fifteen minutes; if `refresh` went
   back to picking the first restaurant, switching would appear to work and silently undo itself
   within the quarter hour — which reads as flakiness rather than as a bug and would be found by a
   confused manager rather than by a test.
"""

from __future__ import annotations

import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EmploymentType, UserAccountStatus
from app.core.security import decode_access_token, hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee, UserAccount
from app.models.tenancy import Organization, Restaurant

PASSWORD = "Staging#2026"  # noqa: S105


class World:
    def __init__(self) -> None:
        self.organizations: dict[str, Organization] = {}
        self.restaurants: dict[str, Restaurant] = {}
        self.employees: dict[str, Employee] = {}


async def _role(session: AsyncSession, code: str) -> Role:
    role = (
        await session.scalars(select(Role).where(Role.code == code, Role.organization_id.is_(None)))
    ).first()
    assert role is not None, f"system role {code} was not seeded"
    return role


async def _world(session: AsyncSession) -> World:
    """Two organizations, two branches each, and one person with a role at two of them.

    `priya` is the interesting one: **owner at spice-r1 and waiter at spice-r2**. Every escalation
    question in this file is asked of her, because a bug that carried her R1 permissions to R2 would
    be indistinguishable from success on a fixture where she held the same role at both.
    """
    world = World()
    for slug in ("spice-garden", "tandoor-house"):
        organization = Organization(name=slug.title(), slug=slug)
        session.add(organization)
        await session.flush()
        world.organizations[slug] = organization
        for branch in ("r1", "r2"):
            restaurant = Restaurant(
                organization_id=organization.id,
                name=f"{slug.title()} {branch.upper()}",
                code=branch.upper(),
            )
            session.add(restaurant)
            await session.flush()
            world.restaurants[f"{slug}-{branch}"] = restaurant

    world.employees["priya"] = await _person(
        session,
        world,
        "priya",
        "spice-garden",
        [("spice-garden-r1", "owner"), ("spice-garden-r2", "waiter")],
    )
    # One branch only, so "employed here but not there" is testable.
    world.employees["arjun"] = await _person(
        session, world, "arjun", "spice-garden", [("spice-garden-r1", "manager")]
    )
    # Another tenant entirely.
    world.employees["rival"] = await _person(
        session, world, "rival", "tandoor-house", [("tandoor-house-r1", "owner")]
    )
    await session.commit()
    return world


async def _person(
    session: AsyncSession,
    world: World,
    name: str,
    slug: str,
    postings: list[tuple[str, str]],
) -> Employee:
    organization = world.organizations[slug]
    account = UserAccount(
        organization_id=organization.id,
        email=f"{name}@{slug}.test",
        password_hash=hash_password(PASSWORD),
        status=UserAccountStatus.ACTIVE,
    )
    session.add(account)
    await session.flush()
    employee = Employee(
        organization_id=organization.id,
        user_account_id=account.id,
        employee_code=name.upper()[:6],
        full_name=name.title(),
        joined_on=date(2026, 1, 1),
        employment_type=EmploymentType.FULL_TIME,
    )
    session.add(employee)
    await session.flush()
    for restaurant_key, role_code in postings:
        role = await _role(session, role_code)
        session.add(
            EmployeeRoleAssignment(
                employee_id=employee.id,
                restaurant_id=world.restaurants[restaurant_key].id,
                role_id=role.id,
            )
        )
    await session.flush()
    return employee


async def _login(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/login", json={"identifier": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _restaurant_in(token: str) -> str:
    """The restaurant the token actually authorises, read from the token rather than the response.

    The response body is what the server *says*; the token is what every later request will be
    scoped by. A switch that updated one and not the other would pass a test reading only the body.
    """
    return decode_access_token(token).restaurant_id


class TestSwitchingBranch:
    async def test_a_person_can_reach_their_second_branch(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Finding S12: before this endpoint, `_home_restaurant` picked the first restaurant and the
        second was unreachable by any means."""
        world = await _world(db_session)
        token = await _login(api_client, "priya@spice-garden.test")
        target = world.restaurants["spice-garden-r2"]

        response = await api_client.post(
            "/api/v1/auth/switch",
            json={"restaurant_id": str(target.id)},
            headers=_auth(token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["restaurant"]["id"] == str(target.id)
        assert _restaurant_in(response.json()["access_token"]) == str(target.id)

    async def test_the_new_token_carries_the_permissions_of_the_target_branch(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The escalation question, and the reason the fixture is shaped the way it is.

        Priya is an owner at R1 and a waiter at R2. If switching carried her R1 permissions across,
        she would be an owner at a branch where she waits tables — privilege escalation performed by
        navigating, with nothing in any log to suggest it happened.
        """
        world = await _world(db_session)
        token = await _login(api_client, "priya@spice-garden.test")
        assert "employee.view" in decode_access_token(token).permissions

        response = await api_client.post(
            "/api/v1/auth/switch",
            json={"restaurant_id": str(world.restaurants["spice-garden-r2"].id)},
            headers=_auth(token),
        )

        switched = decode_access_token(response.json()["access_token"])
        assert not switched.permissions, "a waiter at R2 holds nothing in M01's catalogue"
        assert response.json()["roles"] == ["waiter"]

    async def test_the_switched_token_is_actually_refused_where_it_should_be(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The permissions in the token are a claim; this proves the claim is enforced.

        A token can say anything. What matters is that the API refuses her at R2, which it does by
        re-resolving her access on every request rather than trusting what she is carrying.
        """
        world = await _world(db_session)
        token = await _login(api_client, "priya@spice-garden.test")
        assert (
            await api_client.get("/api/v1/staff/employees", headers=_auth(token))
        ).status_code == 200

        switched = (
            await api_client.post(
                "/api/v1/auth/switch",
                json={"restaurant_id": str(world.restaurants["spice-garden-r2"].id)},
                headers=_auth(token),
            )
        ).json()["access_token"]

        after = await api_client.get("/api/v1/staff/employees", headers=_auth(switched))
        assert after.status_code == 403


class TestTheTenantBoundary:
    async def test_another_organizations_restaurant_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """CLAUDE.md invariant 1, at the one endpoint whose entire job is to change tenant scope.

        404 rather than 403: a 403 would confirm that the id names a real restaurant, which is the
        same leak the employee lookup avoids by scoping rather than by checking.
        """
        world = await _world(db_session)
        token = await _login(api_client, "priya@spice-garden.test")

        response = await api_client.post(
            "/api/v1/auth/switch",
            json={"restaurant_id": str(world.restaurants["tandoor-house-r1"].id)},
            headers=_auth(token),
        )

        assert response.status_code == 404
        # The *code*, not just the status. A route that does not exist also answers 404, so
        # asserting the status alone would let every test in this class pass against an
        # unimplemented endpoint — which is exactly what they did before this line was added.
        assert response.json()["code"] == "auth.restaurant_not_available"

    async def test_a_branch_in_my_own_organization_that_i_do_not_work_at_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Employment by the company is not employment at the branch. Arjun manages R1; R2 is his
        employer's, not his."""
        world = await _world(db_session)
        token = await _login(api_client, "arjun@spice-garden.test")

        response = await api_client.post(
            "/api/v1/auth/switch",
            json={"restaurant_id": str(world.restaurants["spice-garden-r2"].id)},
            headers=_auth(token),
        )

        assert response.status_code == 404
        assert response.json()["code"] == "auth.restaurant_not_available"

    async def test_an_unknown_restaurant_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session)
        token = await _login(api_client, "priya@spice-garden.test")

        response = await api_client.post(
            "/api/v1/auth/switch",
            json={"restaurant_id": str(uuid.uuid4())},
            headers=_auth(token),
        )

        assert response.status_code == 404
        assert response.json()["code"] == "auth.restaurant_not_available"

    async def test_switching_requires_a_token(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)

        response = await api_client.post(
            "/api/v1/auth/switch",
            json={"restaurant_id": str(world.restaurants["spice-garden-r2"].id)},
        )

        assert response.status_code == 401


class TestItSurvivesARefresh:
    async def test_refreshing_after_a_switch_stays_at_the_new_branch(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The failure this endpoint would otherwise ship with.

        Access tokens last fifteen minutes. `refresh` resolved the restaurant through
        `_home_restaurant`, which returns the *first* one — so a manager who switched to R2 would be
        silently returned to R1 within the quarter hour, mid-task, with no error and nothing on
        screen to explain it. It would be reported as "the app keeps jumping back", which is not a
        sentence anyone can debug.
        """
        world = await _world(db_session)
        token = await _login(api_client, "priya@spice-garden.test")
        target = world.restaurants["spice-garden-r2"]
        await api_client.post(
            "/api/v1/auth/switch",
            json={"restaurant_id": str(target.id)},
            headers=_auth(token),
        )

        refreshed = await api_client.post("/api/v1/auth/refresh")

        assert refreshed.status_code == 200, refreshed.text
        assert _restaurant_in(refreshed.json()["access_token"]) == str(target.id)
        assert refreshed.json()["roles"] == ["waiter"]

    async def test_a_session_that_never_switched_still_lands_at_the_home_branch(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _login(api_client, "priya@spice-garden.test")
        home = _restaurant_in(token)

        refreshed = await api_client.post("/api/v1/auth/refresh")

        assert _restaurant_in(refreshed.json()["access_token"]) == home
        assert home == str(world.restaurants["spice-garden-r1"].id)

    async def test_losing_the_role_at_the_switched_branch_ends_the_session_there(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A remembered restaurant must not outlive the right to be there.

        Storing the choice on the session makes this the question: if her waiter role at R2 is
        removed while she is there, the next refresh must not keep handing her R2. It falls back to
        a branch she does have — which is the same rule login follows.
        """
        world = await _world(db_session)
        token = await _login(api_client, "priya@spice-garden.test")
        target = world.restaurants["spice-garden-r2"]
        await api_client.post(
            "/api/v1/auth/switch", json={"restaurant_id": str(target.id)}, headers=_auth(token)
        )

        assignment = (
            await db_session.scalars(
                select(EmployeeRoleAssignment).where(
                    EmployeeRoleAssignment.employee_id == world.employees["priya"].id,
                    EmployeeRoleAssignment.restaurant_id == target.id,
                )
            )
        ).first()
        assert assignment is not None
        await db_session.delete(assignment)
        await db_session.commit()

        refreshed = await api_client.post("/api/v1/auth/refresh")

        assert refreshed.status_code == 200, refreshed.text
        assert _restaurant_in(refreshed.json()["access_token"]) == str(
            world.restaurants["spice-garden-r1"].id
        )


class TestWhereICanWork:
    async def test_the_session_reports_the_branches_a_person_can_switch_to(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The UI cannot offer a switcher it has no list for, and guessing one client-side would
        mean a second implementation of the rule the server already enforces."""
        world = await _world(db_session)
        token = await _login(api_client, "priya@spice-garden.test")

        response = await api_client.get("/api/v1/auth/me", headers=_auth(token))

        ids = {item["id"] for item in response.json()["restaurants"]}
        assert ids == {
            str(world.restaurants["spice-garden-r1"].id),
            str(world.restaurants["spice-garden-r2"].id),
        }

    async def test_it_lists_only_branches_the_person_actually_works_at(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _login(api_client, "arjun@spice-garden.test")

        response = await api_client.get("/api/v1/auth/me", headers=_auth(token))

        assert [item["id"] for item in response.json()["restaurants"]] == [
            str(world.restaurants["spice-garden-r1"].id)
        ]
