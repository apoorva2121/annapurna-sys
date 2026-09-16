"""`/auth/me`'s branch list, bounded (backlog-issues B3).

Backlog row: "`MeResponse.restaurants` is unbounded". `/auth/me` is called on every app load, and
its restaurant list had no limit and no cursor — and was built with one `session.get` per branch.
Invisible
for a single-branch pilot; the product's stated direction is restaurant groups.

What must hold:

- at most 20 branches embedded, and **the current branch is always among them**, because the branch
  switcher shows the current one as selected and a list without it would render an empty control;
- the rest are reachable, a page at a time, from `GET /auth/restaurants`;
- building the list costs the same number of statements for 2 branches as for 25.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access import EmployeeRoleAssignment
from app.models.tenancy import Restaurant
from tests.helpers.queries import count_queries
from tests.test_employee_endpoints import World, _auth, _role, _token, _world

ME = "/api/v1/auth/me"
BRANCHES = "/api/v1/auth/restaurants"


async def _owner_at(db_session: AsyncSession, branches: int) -> World:
    """The owner at R1, plus `branches - 1` more branches in the same organization."""
    world = await _world(db_session, "owner")
    owner = world.employees["owner"]
    role = await _role(db_session, "owner")
    for number in range(2, branches + 1):
        branch = Restaurant(
            organization_id=world.organization.id,
            name=f"Spice Garden {number:02d}",
            code=f"R{number}",
        )
        db_session.add(branch)
        await db_session.flush()
        db_session.add(
            EmployeeRoleAssignment(employee_id=owner.id, restaurant_id=branch.id, role_id=role.id)
        )
    await db_session.commit()
    return world


class TestTheBranchListIsBounded:
    async def test_twenty_five_branches_embed_twenty_including_the_current_one(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _owner_at(db_session, 25)
        token = await _token(api_client, "owner")

        body = (await api_client.get(ME, headers=_auth(token))).json()

        assert len(body["restaurants"]) == 20
        assert body["restaurant"]["id"] in {branch["id"] for branch in body["restaurants"]}
        assert body["has_more_restaurants"] is True

    async def test_a_small_group_is_embedded_whole(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _owner_at(db_session, 2)
        token = await _token(api_client, "owner")

        body = (await api_client.get(ME, headers=_auth(token))).json()

        assert len(body["restaurants"]) == 2
        assert body["has_more_restaurants"] is False

    async def test_every_branch_is_reachable_a_page_at_a_time(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _owner_at(db_session, 25)
        token = await _token(api_client, "owner")

        seen: list[str] = []
        cursor: str | None = None
        for _ in range(10):  # a bound, so a cursor that never ends fails instead of hanging
            query = {"limit": 10} | ({"cursor": cursor} if cursor else {})
            response = await api_client.get(BRANCHES, params=query, headers=_auth(token))
            assert response.status_code == 200, response.text
            page = response.json()
            seen.extend(branch["id"] for branch in page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break

        assert len(seen) == 25
        assert len(set(seen)) == 25


class TestTheBranchListCostsTheSame:
    async def test_building_it_does_not_grow_with_the_number_of_branches(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """One statement for the list, not a `session.get` per branch — the shape `/auth/me` had."""
        engine = db_session.get_bind().engine

        await _owner_at(db_session, 2)
        token = await _token(api_client, "owner")
        with count_queries(engine) as small:
            assert (await api_client.get(ME, headers=_auth(token))).status_code == 200

        await _owner_at_more(db_session, api_client)
        with count_queries(engine) as large:
            assert (await api_client.get(ME, headers=_auth(token))).status_code == 200

        assert large.count == small.count


async def _owner_at_more(db_session: AsyncSession, api_client: AsyncClient) -> None:
    """23 more branches for the owner already signed in above, so the token stays valid."""
    del api_client  # the token taken before still names the same employee and home branch
    from sqlalchemy import select

    from app.models.identity import Employee

    owner = (await db_session.scalars(select(Employee).where(Employee.full_name == "Owner"))).one()
    role = await _role(db_session, "owner")
    for number in range(3, 26):
        branch = Restaurant(
            organization_id=owner.organization_id,
            name=f"Spice Garden {number:02d}",
            code=f"R{number}",
        )
        db_session.add(branch)
        await db_session.flush()
        db_session.add(
            EmployeeRoleAssignment(employee_id=owner.id, restaurant_id=branch.id, role_id=role.id)
        )
    await db_session.commit()
