"""Who is serving a table: the waiter on an order, shown, claimed and moved (2026-09-14).

Found while discussing the order workflow with the owner: `order.waiter_employee_id` has existed
since M07, but it was set to **whoever opened the order** and nothing could change it or show it.
A manager seating a table for Suresh, or a cashier keying in a Swiggy order, was credited as the
waiter — which M17 would one day turn into somebody else's performance score (ADR 0011).

The owner's decisions (`docs/plan/backlog-issues-build-log.md`, D7-D10):

- **A waiter who opens a dine-in order is its waiter.** Anyone holding `order.assign` (owner,
  manager) chooses the waiter when opening, or leaves it unassigned. Takeaway and delivery have
  none.
- **Assign to me** claims a dine-in order that has no waiter, and nothing else.
- **Moving an order from one waiter to another** needs `order.assign` and a reason.
- **Every change is an audit row** — from whom, to whom, by whom, why — so a handover at ten o'clock
  does not erase who served the first two hours.
- **Auto-assignment waits for shifts** (M12): without a roster nobody knows who is on the floor.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EmploymentType
from app.models.access import EmployeeRoleAssignment, Role
from app.models.audit import AuditLog
from app.models.identity import Employee
from tests.test_orders_endpoints import ORDERS, Menu, _open, _setup
from tests.test_setup_endpoints import World, _auth, _token

STAFF = "/api/v1/staff"


async def _person(
    session: AsyncSession,
    world: World,
    name: str,
    role_code: str,
    *,
    active: bool = True,
    restaurant_id: uuid.UUID | None = None,
    takes_tables: bool | None = None,
) -> uuid.UUID:
    """Someone with no login, which is ordinary (ADR 0007): a waiter without a phone, served for by
    a captain, is still the person serving the table.

    `takes_tables` follows the role here for the same reason migration 0057's backfill does — it is
    the product's own system role, and it is what a restaurant would set on day one. Every test
    that wants the other combination sets the flag explicitly.
    """
    role = (
        await session.scalars(
            select(Role).where(Role.code == role_code, Role.organization_id.is_(None))
        )
    ).one()
    employee = Employee(
        organization_id=world.organization.id,
        employee_code=f"X{uuid.uuid4().hex[:6]}",
        full_name=name,
        joined_on=date(2026, 1, 1),
        employment_type=EmploymentType.FULL_TIME,
        takes_tables=takes_tables if takes_tables is not None else role_code == "waiter",
        is_active=active,
    )
    session.add(employee)
    await session.flush()
    session.add(
        EmployeeRoleAssignment(
            employee_id=employee.id,
            restaurant_id=restaurant_id or world.restaurant.id,
            role_id=role.id,
        )
    )
    await session.commit()
    return employee.id


async def _employee_id(session: AsyncSession, full_name: str) -> uuid.UUID:
    found = await session.scalar(select(Employee.id).where(Employee.full_name == full_name))
    assert found is not None
    return found


async def _claim(client: AsyncClient, token: str, order: dict[str, Any]) -> Response:
    return await client.post(
        f"{ORDERS}/{order['id']}/waiter/claim",
        json={"version": order["version"]},
        headers=_auth(token),
    )


async def _move(
    client: AsyncClient,
    token: str,
    order: dict[str, Any],
    employee_id: uuid.UUID | None,
    reason: str = "Shift ended",
) -> Response:
    return await client.post(
        f"{ORDERS}/{order['id']}/waiter",
        json={
            "version": order["version"],
            "employee_id": None if employee_id is None else str(employee_id),
            "reason": reason,
        },
        headers=_auth(token),
    )


async def _waiter_rows(session: AsyncSession, order_id: str) -> list[AuditLog]:
    rows = await session.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_id == uuid.UUID(order_id),
            AuditLog.action == "order.waiter_assigned",
        )
        .order_by(AuditLog.occurred_at)
    )
    return list(rows)


async def _unassigned(client: AsyncClient, menu: Menu) -> dict[str, Any]:
    manager = await _token(client, "manager")
    return await _open(client, manager, menu)


# --------------------------------------------------------------------------- opening


class TestOpeningAnOrder:
    async def test_a_waiter_who_opens_a_table_is_its_waiter_by_name(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)

        order = await _open(api_client, token, menu)

        assert order["waiter"] == {
            "id": str(await _employee_id(db_session, "Waiter Person")),
            "full_name": "Waiter Person",
        }

    async def test_a_manager_who_opens_a_table_is_not_credited_as_its_waiter(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The defect: the person who opened the order was always its waiter."""
        _, menu, _ = await _setup(db_session, api_client)

        order = await _unassigned(api_client, menu)

        assert order["waiter"] is None
        assert order["waiter_employee_id"] is None

    async def test_a_manager_opens_a_table_for_the_waiter_serving_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, _ = await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        waiter = await _employee_id(db_session, "Waiter Person")

        order = await _open(api_client, manager, menu, waiter_employee_id=str(waiter))

        assert order["waiter"]["full_name"] == "Waiter Person"
        (row,) = await _waiter_rows(db_session, order["id"])
        assert row.old_value == {"waiter_employee_id": None}
        assert row.new_value == {"waiter_employee_id": str(waiter)}
        assert row.actor_employee_id == await _employee_id(db_session, "Manager Person")

    async def test_a_waiter_cannot_open_a_table_in_someone_elses_name(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        other = await _person(db_session, world, "Kavita Rane", "waiter")

        response = await api_client.post(
            ORDERS,
            json={
                "type": "dine_in",
                "table_ids": [str(menu.table)],
                "waiter_employee_id": str(other),
            },
            headers=_auth(token),
        )

        assert response.status_code == 403, response.text
        assert response.json()["code"] == "permission.denied"

    async def test_a_takeaway_is_a_counter_order_with_no_waiter(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, token = await _setup(db_session, api_client)

        response = await api_client.post(ORDERS, json={"type": "takeaway"}, headers=_auth(token))

        assert response.status_code == 201, response.text
        assert response.json()["waiter"] is None


# --------------------------------------------------------------------------- assign to me


class TestAssignToMe:
    async def test_a_waiter_claims_an_order_nobody_is_serving(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _unassigned(api_client, menu)

        response = await _claim(api_client, token, order)

        assert response.status_code == 200, response.text
        assert response.json()["waiter"]["full_name"] == "Waiter Person"
        assert response.json()["version"] == order["version"] + 1
        (row,) = await _waiter_rows(db_session, order["id"])
        assert row.old_value == {"waiter_employee_id": None}
        assert row.actor_employee_id == await _employee_id(db_session, "Waiter Person")

    async def test_an_order_someone_is_serving_cannot_be_claimed(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Grabbing a busy table would take its credit. Moving it is a manager's call."""
        world, menu, _ = await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        kavita = await _person(db_session, world, "Kavita Rane", "waiter")
        order = await _open(api_client, manager, menu, waiter_employee_id=str(kavita))
        waiter = await _token(api_client, "waiter")

        response = await _claim(api_client, waiter, order)

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "order.waiter_taken"
        assert "Kavita Rane" in response.json()["message"]

    async def test_the_second_of_two_claims_on_one_version_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Two waiters tapping at once: the order's version decides, never the last write."""
        _, menu, token = await _setup(db_session, api_client)
        order = await _unassigned(api_client, menu)
        manager = await _token(api_client, "manager")

        first = await _claim(api_client, token, order)
        second = await _claim(api_client, manager, order)

        assert first.status_code == 200, first.text
        assert second.status_code == 409, second.text
        assert second.json()["code"] == "order.stale"

    async def test_a_counter_order_has_no_waiter_to_claim(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, token = await _setup(db_session, api_client)
        takeaway = await api_client.post(ORDERS, json={"type": "takeaway"}, headers=_auth(token))

        response = await _claim(api_client, token, takeaway.json())

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "order.counter"


# --------------------------------------------------------------------------- moving


class TestMovingAnOrderToAnotherWaiter:
    async def test_a_manager_moves_an_order_and_the_reason_is_kept(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)
        kavita = await _person(db_session, world, "Kavita Rane", "waiter")
        manager = await _token(api_client, "manager")

        response = await _move(api_client, manager, order, kavita, reason="Suresh's shift ended")

        assert response.status_code == 200, response.text
        assert response.json()["waiter"]["full_name"] == "Kavita Rane"
        (row,) = await _waiter_rows(db_session, order["id"])
        assert row.old_value == {
            "waiter_employee_id": str(await _employee_id(db_session, "Waiter Person"))
        }
        assert row.new_value == {"waiter_employee_id": str(kavita)}
        assert row.audit_metadata == {"reason": "Suresh's shift ended"}

    async def test_a_move_without_a_reason_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)
        kavita = await _person(db_session, world, "Kavita Rane", "waiter")
        manager = await _token(api_client, "manager")

        response = await _move(api_client, manager, order, kavita, reason="")

        assert response.status_code == 422, response.text

    async def test_a_waiter_cannot_move_an_order(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)
        kavita = await _person(db_session, world, "Kavita Rane", "waiter")

        response = await _move(api_client, token, order, kavita)

        assert response.status_code == 403, response.text

    async def test_only_active_staff_who_take_orders_here_can_serve_a_table(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The accountant reads orders and takes none; a deactivated waiter has gone; a waiter at
        another branch is not on this floor. All three are refused the same way."""
        world, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)
        manager = await _token(api_client, "manager")
        accountant = await _employee_id(db_session, "Accountant Person")
        gone = await _person(db_session, world, "Mahesh Bhosale", "waiter", active=False)

        for employee_id in (accountant, gone, uuid.uuid4()):
            response = await _move(api_client, manager, order, employee_id)
            assert response.status_code == 422, response.text
            assert response.json()["code"] == "order.waiter_not_eligible"

    async def test_a_settled_or_cancelled_order_keeps_its_waiter(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)
        kavita = await _person(db_session, world, "Kavita Rane", "waiter")
        manager = await _token(api_client, "manager")
        cancelled = await api_client.post(
            f"{ORDERS}/{order['id']}/cancel",
            json={"version": order["version"], "reason": "Opened by mistake"},
            headers=_auth(manager),
        )
        assert cancelled.status_code == 200, cancelled.text

        response = await _move(api_client, manager, cancelled.json(), kavita)

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "order.final"


# --------------------------------------------------------------------------- showing


class TestTheWaiterIsShownEverywhere:
    async def test_the_waiter_list_holds_active_staff_who_take_orders_here(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, _, _ = await _setup(db_session, api_client)
        await _person(db_session, world, "Kavita Rane", "waiter")
        await _person(db_session, world, "Mahesh Bhosale", "waiter", active=False)
        manager = await _token(api_client, "manager")

        response = await api_client.get(f"{STAFF}/waiters", headers=_auth(manager))

        assert response.status_code == 200, response.text
        names = [person["full_name"] for person in response.json()["items"]]
        assert names == sorted(names)
        assert {"Kavita Rane", "Waiter Person"} <= set(names)
        # The owner's decision of 2026-09-19: only people who take tables are offered as a table's
        # waiter. A manager holds `order.create` — they can take an order — and is no longer
        # *creditable* as the waiter on one, because ADR 0011 scores a waiter on the orders they
        # served and a manager covering the floor entered everyone else's figures.
        assert "Manager Person" not in names
        assert "Accountant Person" not in names
        assert "Mahesh Bhosale" not in names

    async def test_an_owner_is_never_offered_as_a_tables_waiter(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The defect the owner reported on 2026-09-19, and the one a permission could not fix.

        The `owner` role is seeded `["*"]`, which the identity seeder expands into **every**
        permission — 55 today and any new one tomorrow. So the owner held `order.create` and was
        offered as a waiter on every table, and adding an `order.serve` permission would have been
        granted to them automatically. Hence `employee.takes_tables`, which is a fact about the
        person's job rather than a grant of authority.
        """
        _, _, _ = await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")

        response = await api_client.get(f"{STAFF}/waiters", headers=_auth(manager))

        assert response.status_code == 200, response.text
        names = [person["full_name"] for person in response.json()["items"]]
        assert "Owner Person" not in names
        assert "Waiter Person" in names, "this test would otherwise pass vacuously"

    async def test_a_manager_who_does_cover_the_floor_can_be_marked_as_taking_tables(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The flag is per person, which is the point of it being a column rather than a role rule.

        A small restaurant where the manager genuinely waits tables on a Friday sets their flag and
        the product agrees with reality — without granting that to every manager everywhere.
        """
        world, _, _ = await _setup(db_session, api_client)
        covering = await _person(db_session, world, "Sunita Joshi", "manager", takes_tables=True)
        manager = await _token(api_client, "manager")

        response = await api_client.get(f"{STAFF}/waiters", headers=_auth(manager))

        assert response.status_code == 200, response.text
        names = [person["full_name"] for person in response.json()["items"]]
        assert "Sunita Joshi" in names
        # And the one who was not marked is still absent, so the flag is doing the work.
        assert "Manager Person" not in names
        assert covering is not None

    async def test_an_order_cannot_be_moved_to_somebody_who_does_not_take_tables(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The list is a convenience; this is the boundary. A client that names an id directly
        must be refused, or the dropdown is the only thing enforcing the rule."""
        _, menu, waiter = await _setup(db_session, api_client)
        order = await _open(api_client, waiter, menu)
        manager = await _token(api_client, "manager")
        owner_id = await _employee_id(db_session, "Owner Person")

        response = await _move(api_client, manager, order, owner_id, "covering")

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "order.waiter_not_eligible"

    async def test_a_waiter_cannot_read_the_waiter_list(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, token = await _setup(db_session, api_client)

        response = await api_client.get(f"{STAFF}/waiters", headers=_auth(token))

        assert response.status_code == 403, response.text

    async def test_the_floor_and_the_order_list_name_the_waiter(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)

        floor = await api_client.get(f"{STAFF}/floor", headers=_auth(token))
        listed = await api_client.get(ORDERS, headers=_auth(token))

        cell = next(
            table
            for area in floor.json()["areas"]
            for table in area["tables"]
            if table["id"] == str(menu.table)
        )
        assert cell["orders"][0]["waiter_name"] == "Waiter Person"
        (row,) = [item for item in listed.json()["items"] if item["id"] == order["id"]]
        assert row["waiter"]["full_name"] == "Waiter Person"
