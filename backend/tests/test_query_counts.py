"""Acceptance criterion 12, and the Definition of Done's "no N+1" line, made enforceable.

`assert_max_queries` existed from M00 but nothing used it against a real endpoint, so the guarantee
it was built for was never actually claimed. This module claims it.

The assertion is deliberately *not* a magic number. A budget like "at most 6" passes for a list of
five people and still hides a per-row query, because five rows is under budget. What matters is the
shape: the same number of statements whether the page holds two people or twenty. That is the only
formulation an N+1 cannot satisfy.
"""

from __future__ import annotations

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EmploymentType
from app.models.access import EmployeeRoleAssignment
from app.models.identity import Employee
from tests.helpers.queries import count_queries
from tests.test_employee_endpoints import _auth, _role, _token, _world


async def _add_people(session: AsyncSession, world: object, count: int, prefix: str) -> None:
    """Extra staff, each with a role, so the per-row role lookup has something to repeat over."""
    from tests.test_employee_endpoints import World

    assert isinstance(world, World)
    role = await _role(session, "waiter")
    for index in range(count):
        employee = Employee(
            organization_id=world.organization.id,
            employee_code=f"{prefix}{index:03d}",
            full_name=f"{prefix} Person {index}",
            joined_on=date(2026, 1, 1),
            employment_type=EmploymentType.FULL_TIME,
        )
        session.add(employee)
        await session.flush()
        session.add(
            EmployeeRoleAssignment(
                employee_id=employee.id, restaurant_id=world.restaurant.id, role_id=role.id
            )
        )
    await session.commit()


async def test_the_staff_list_costs_the_same_whatever_the_page_size(
    db_session: AsyncSession, api_client: AsyncClient
) -> None:
    """The N+1 guard on the list endpoint.

    Rendering a row needs that person's roles. Asking for them per row is the obvious
    implementation and it turns one screen into fifty-one queries on a restaurant with fifty
    staff — on the connection of a business whose database is a managed instance three
    milliseconds away, fifty times.
    """
    world = await _world(db_session, "owner")
    token = await _token(api_client, "owner")
    headers = _auth(token)
    engine = db_session.get_bind().engine

    await _add_people(db_session, world, 2, "SMALL")
    with count_queries(engine) as small:
        small_response = await api_client.get("/api/v1/staff/employees", headers=headers)
    assert small_response.status_code == 200

    await _add_people(db_session, world, 18, "LARGE")
    with count_queries(engine) as large:
        large_response = await api_client.get("/api/v1/staff/employees", headers=headers)
    assert large_response.status_code == 200

    # Twenty-one people rather than three, and the same number of statements.
    assert len(large_response.json()["items"]) > len(small_response.json()["items"])
    assert large.count == small.count, (
        f"the list issued {small.count} queries for "
        f"{len(small_response.json()['items'])} people and {large.count} for "
        f"{len(large_response.json()['items'])} — the cost is scaling with the page"
    )


async def test_the_staff_list_still_reports_each_person_s_roles(
    db_session: AsyncSession, api_client: AsyncClient
) -> None:
    """The obvious way to make the test above pass is to stop returning roles. This is what stops
    that being an option."""
    world = await _world(db_session, "owner", "waiter")
    await _add_people(db_session, world, 2, "EXTRA")
    token = await _token(api_client, "owner")

    response = await api_client.get("/api/v1/staff/employees", headers=_auth(token))

    by_name = {item["full_name"]: item for item in response.json()["items"]}
    assert by_name["Waiter"]["roles"] == ["waiter"]
    assert by_name["EXTRA Person 0"]["roles"] == ["waiter"]
    # The owner holds a different role; a batched lookup that returned one set for everyone would
    # otherwise pass the line above.
    assert by_name["Owner"]["roles"] == ["owner"]


async def test_an_employee_with_no_roles_is_still_listed(
    db_session: AsyncSession, api_client: AsyncClient
) -> None:
    """A batched lookup keyed by employee id drops anyone the join finds nothing for, unless it is
    written not to. That person is the one a manager just created (M01 spec, isolation note)."""
    world = await _world(db_session, "owner")
    session_world = world
    employee = Employee(
        organization_id=session_world.organization.id,
        employee_code="NOROLE",
        full_name="Not Yet Assigned",
        joined_on=date(2026, 1, 1),
        employment_type=EmploymentType.FULL_TIME,
    )
    db_session.add(employee)
    await db_session.commit()
    token = await _token(api_client, "owner")

    response = await api_client.get("/api/v1/staff/employees", headers=_auth(token))

    by_name = {item["full_name"]: item for item in response.json()["items"]}
    assert by_name["Not Yet Assigned"]["roles"] == []
