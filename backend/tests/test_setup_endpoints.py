"""Endpoint tests for restaurant setup: happy path, validation, permission, not-found, conflict.

The Definition of Done asks for those five per endpoint. Cross-tenant isolation is asserted for
every route at once by suite 1 in `test_generic_suites.py`, which M02 had to harden before it
covered these routes at all — so it is not repeated here.

The tests that earn their place are the ones about **things that must not change**:

- a tax rate is superseded, never edited, because the rate is copied onto every order line and
  cited by an invoice;
- `effective_from` is validated against the *restaurant's* business date, not the server's;
- a station `code` is a contract with `seed/menu.yaml` and M08's routing, so the display name is
  editable and the identifier is not;
- nothing here is ever deleted (ADR 0008).

Each of those is a rule whose violation looks completely normal at the moment it happens and
becomes visible months later, in an invoice or a kitchen ticket that nobody can explain.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EmploymentType, TableStatus, UserAccountStatus
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.audit import AuditLog
from app.models.identity import Employee, UserAccount
from app.models.tenancy import Organization, Restaurant

PASSWORD = "Staging#2026"  # noqa: S105

SETUP = "/api/v1/staff/setup"


class World:
    def __init__(self, organization: Organization, restaurant: Restaurant) -> None:
        self.organization = organization
        self.restaurant = restaurant


async def _world(
    session: AsyncSession, *roles: str, timezone: str = "Asia/Kolkata", slug: str = "spice-garden"
) -> World:
    """One organization, one restaurant, and a person per role asked for.

    Smaller than M01's fixture on purpose: nothing in this module depends on a second branch,
    because setup data belongs to one restaurant by definition. The tenant boundary that does
    matter here is between organizations, and suite 1 tests it across every route at once.
    """
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name=slug.title(),
        code="R1",
        timezone=timezone,
        business_day_start=time(5, 0),
    )
    session.add(restaurant)
    await session.flush()

    for index, role_code in enumerate(roles):
        role = (
            await session.scalars(
                select(Role).where(Role.code == role_code, Role.organization_id.is_(None))
            )
        ).first()
        assert role is not None, f"system role {role_code} was not seeded"
        account = UserAccount(
            organization_id=organization.id,
            email=f"{role_code}@{slug}.test",
            password_hash=hash_password(PASSWORD),
            status=UserAccountStatus.ACTIVE,
        )
        session.add(account)
        await session.flush()
        employee = Employee(
            organization_id=organization.id,
            user_account_id=account.id,
            employee_code=f"E{index:03d}",
            full_name=f"{role_code.title()} Person",
            joined_on=date(2026, 1, 1),
            employment_type=EmploymentType.FULL_TIME,
        )
        session.add(employee)
        await session.flush()
        session.add(
            EmployeeRoleAssignment(
                employee_id=employee.id, restaurant_id=restaurant.id, role_id=role.id
            )
        )
    await session.flush()
    await session.commit()
    return World(organization, restaurant)


async def _token(client: AsyncClient, role_code: str, slug: str = "spice-garden") -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"identifier": f"{role_code}@{slug}.test", "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _area(client: AsyncClient, token: str, name: str = "AC Hall") -> dict[str, Any]:
    response = await client.post(f"{SETUP}/dining-areas", json={"name": name}, headers=_auth(token))
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _table(
    client: AsyncClient, token: str, area_id: str, code: str = "T1", seats: int = 4
) -> dict[str, Any]:
    response = await client.post(
        f"{SETUP}/tables",
        json={"dining_area_id": area_id, "code": code, "seats": seats},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _tomorrow() -> str:
    return (datetime.now(UTC).date() + timedelta(days=2)).isoformat()


# --------------------------------------------------------------------------- the restaurant


class TestRestaurantSettings:
    async def test_an_owner_reads_the_settings(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.get("/api/v1/staff/restaurant", headers=_auth(token))

        assert response.status_code == 200
        body = response.json()
        assert body["timezone"] == "Asia/Kolkata"
        assert body["business_day_start"] == "05:00:00"

    async def test_a_manager_may_not_read_them(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """M02 spec decision 1. A manager runs a shift; changing what a day means is not that."""
        await _world(db_session, "owner", "manager")
        token = await _token(api_client, "manager")

        response = await api_client.get("/api/v1/staff/restaurant", headers=_auth(token))

        assert response.status_code == 403

    async def test_an_owner_changes_the_business_day_start(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            "/api/v1/staff/restaurant",
            json={"business_day_start": "04:30:00"},
            headers=_auth(token),
        )

        assert response.status_code == 200
        assert response.json()["business_day_start"] == "04:30:00"

    async def test_changing_the_business_day_start_is_audited_with_before_and_after(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """M02 spec threat table. It moves takings between days without touching a single order,
        which is exactly why it needs a trail — there is no other trace of it."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        await api_client.patch(
            "/api/v1/staff/restaurant",
            json={"business_day_start": "04:30:00"},
            headers=_auth(token),
        )

        entry = (
            await db_session.scalars(
                select(AuditLog).where(AuditLog.action == "restaurant.settings_changed")
            )
        ).first()
        assert entry is not None, "changing the business day start wrote no audit row"
        assert entry.old_value == {"business_day_start": "05:00:00"}
        assert entry.new_value == {"business_day_start": "04:30:00"}

    async def test_an_unknown_timezone_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Stored as typed, this surfaces as `business_date_of` raising on the next order taken —
        in the middle of service, with nothing connecting it to a settings change made last week."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            "/api/v1/staff/restaurant",
            json={"timezone": "Asia/Kolkta"},
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "restaurant.unknown_timezone"

    async def test_a_real_but_unusual_timezone_is_accepted(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The check must accept the whole IANA database, not a list of zones someone thought of.
        `Asia/Calcutta` is a real alias and refusing it would be the check being too clever."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            "/api/v1/staff/restaurant",
            json={"timezone": "Asia/Calcutta"},
            headers=_auth(token),
        )

        assert response.status_code == 200

    async def test_a_currency_is_normalised_rather_than_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            "/api/v1/staff/restaurant", json={"currency": "inr"}, headers=_auth(token)
        )

        assert response.status_code == 200
        assert response.json()["currency"] == "INR"

    async def test_an_unknown_field_is_refused_rather_than_ignored(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`extra="forbid"`. A misspelled field that returns 200 and changes nothing is the bug
        somebody spends an afternoon on."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            "/api/v1/staff/restaurant", json={"timezon": "Asia/Kolkata"}, headers=_auth(token)
        )

        assert response.status_code == 422

    async def test_the_name_cannot_be_changed_here(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            "/api/v1/staff/restaurant", json={"name": "Something Else"}, headers=_auth(token)
        )

        assert response.status_code == 422


# --------------------------------------------------------------------------- dining areas


class TestDiningAreas:
    async def test_an_owner_creates_one(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/dining-areas", json={"name": "AC Hall"}, headers=_auth(token)
        )

        assert response.status_code == 201
        assert response.json()["name"] == "AC Hall"
        assert response.json()["is_active"] is True

    async def test_a_manager_may_not(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "manager")
        token = await _token(api_client, "manager")

        response = await api_client.post(
            f"{SETUP}/dining-areas", json={"name": "AC Hall"}, headers=_auth(token)
        )

        assert response.status_code == 403

    async def test_a_duplicate_name_is_a_conflict_not_a_500(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        await _area(api_client, token, "Terrace")

        response = await api_client.post(
            f"{SETUP}/dining-areas", json={"name": "Terrace"}, headers=_auth(token)
        )

        assert response.status_code == 409
        assert response.json()["code"] == "dining_area.name_taken"

    async def test_a_blank_name_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/dining-areas", json={"name": "   "}, headers=_auth(token)
        )

        assert response.status_code == 422

    async def test_new_areas_go_to_the_end_of_the_list(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Defaulting `seq` to 0 would put every new area first, so a floor plan would reorder
        itself every time somebody added a section."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        first = await _area(api_client, token, "AC Hall")
        second = await _area(api_client, token, "Terrace")
        third = await _area(api_client, token, "Garden")

        assert [first["seq"], second["seq"], third["seq"]] == [0, 1, 2]

    async def test_the_list_is_in_seq_order_not_alphabetical(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        for name in ("Terrace", "AC Hall", "Garden"):
            await _area(api_client, token, name)

        response = await api_client.get(f"{SETUP}/dining-areas", headers=_auth(token))

        assert [item["name"] for item in response.json()["items"]] == [
            "Terrace",
            "AC Hall",
            "Garden",
        ]

    async def test_renaming_one(self, db_session: AsyncSession, api_client: AsyncClient) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        area = await _area(api_client, token)

        response = await api_client.patch(
            f"{SETUP}/dining-areas/{area['id']}",
            json={"name": "Air-Conditioned Hall"},
            headers=_auth(token),
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Air-Conditioned Hall"

    async def test_an_unknown_area_is_a_404(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            f"{SETUP}/dining-areas/{uuid.uuid4()}", json={"name": "Nowhere"}, headers=_auth(token)
        )

        assert response.status_code == 404

    async def test_an_area_with_tables_cannot_be_deactivated(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Refused with the count, because "move or deactivate its 2 tables first" tells someone
        what to do next and "cannot deactivate" does not."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        area = await _area(api_client, token)
        await _table(api_client, token, area["id"], "T1")
        await _table(api_client, token, area["id"], "T2")

        response = await api_client.patch(
            f"{SETUP}/dining-areas/{area['id']}", json={"is_active": False}, headers=_auth(token)
        )

        assert response.status_code == 409
        assert response.json()["code"] == "dining_area.has_tables"
        assert response.json()["details"]["active_tables"] == 2

    async def test_an_empty_area_can_be_deactivated_and_then_hides_from_the_list(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        area = await _area(api_client, token)

        deactivated = await api_client.patch(
            f"{SETUP}/dining-areas/{area['id']}", json={"is_active": False}, headers=_auth(token)
        )
        listed = await api_client.get(f"{SETUP}/dining-areas", headers=_auth(token))
        including = await api_client.get(
            f"{SETUP}/dining-areas?include_inactive=true", headers=_auth(token)
        )

        assert deactivated.status_code == 200
        assert listed.json()["items"] == []
        # Deactivated, never deleted (ADR 0008): the row is still there for the order that used it.
        assert len(including.json()["items"]) == 1


# --------------------------------------------------------------------------- tables


class TestTables:
    async def test_creating_one(self, db_session: AsyncSession, api_client: AsyncClient) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        area = await _area(api_client, token)

        response = await api_client.post(
            f"{SETUP}/tables",
            json={"dining_area_id": area["id"], "code": "T4", "seats": 4},
            headers=_auth(token),
        )

        assert response.status_code == 201
        assert response.json()["status"] == TableStatus.FREE
        assert response.json()["seats"] == 4

    async def test_a_table_cannot_be_created_in_an_area_that_does_not_exist(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/tables",
            json={"dining_area_id": str(uuid.uuid4()), "code": "T4", "seats": 4},
            headers=_auth(token),
        )

        assert response.status_code == 404
        assert response.json()["code"] == "dining_area.not_found"

    async def test_a_table_cannot_be_created_in_a_deactivated_area(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        area = await _area(api_client, token)
        await api_client.patch(
            f"{SETUP}/dining-areas/{area['id']}", json={"is_active": False}, headers=_auth(token)
        )

        response = await api_client.post(
            f"{SETUP}/tables",
            json={"dining_area_id": area["id"], "code": "T4", "seats": 4},
            headers=_auth(token),
        )

        assert response.status_code == 409
        assert response.json()["code"] == "dining_area.inactive"

    async def test_a_duplicate_code_is_a_conflict(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        area = await _area(api_client, token)
        await _table(api_client, token, area["id"], "T4")

        response = await api_client.post(
            f"{SETUP}/tables",
            json={"dining_area_id": area["id"], "code": "T4", "seats": 2},
            headers=_auth(token),
        )

        assert response.status_code == 409
        assert response.json()["code"] == "table.code_taken"

    async def test_zero_seats_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        area = await _area(api_client, token)

        response = await api_client.post(
            f"{SETUP}/tables",
            json={"dining_area_id": area["id"], "code": "T4", "seats": 0},
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_a_manager_may_not_create_one(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "manager")
        owner = await _token(api_client, "owner")
        area = await _area(api_client, owner)
        manager = await _token(api_client, "manager")

        response = await api_client.post(
            f"{SETUP}/tables",
            json={"dining_area_id": area["id"], "code": "T4", "seats": 4},
            headers=_auth(manager),
        )

        assert response.status_code == 403

    async def test_marking_a_table_reserved(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """M02 spec decision 3: set by hand by a manager taking a walk-in booking. There is no
        reservation system behind it and it does not pretend to be one."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        area = await _area(api_client, token)
        table = await _table(api_client, token, area["id"])

        response = await api_client.patch(
            f"{SETUP}/tables/{table['id']}",
            json={"status": TableStatus.RESERVED},
            headers=_auth(token),
        )

        assert response.status_code == 200
        assert response.json()["status"] == TableStatus.RESERVED

    async def test_an_invalid_status_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        area = await _area(api_client, token)
        table = await _table(api_client, token, area["id"])

        response = await api_client.patch(
            f"{SETUP}/tables/{table['id']}", json={"status": "on_fire"}, headers=_auth(token)
        )

        assert response.status_code == 422

    async def test_moving_a_table_to_an_unknown_area_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The area is re-checked on every move, not only on create — otherwise a table could be
        moved into an area belonging to another restaurant."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        area = await _area(api_client, token)
        table = await _table(api_client, token, area["id"])

        response = await api_client.patch(
            f"{SETUP}/tables/{table['id']}",
            json={"dining_area_id": str(uuid.uuid4())},
            headers=_auth(token),
        )

        assert response.status_code == 404

    async def test_the_list_filters_by_area(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        hall = await _area(api_client, token, "AC Hall")
        terrace = await _area(api_client, token, "Terrace")
        await _table(api_client, token, hall["id"], "T1")
        await _table(api_client, token, terrace["id"], "T2")

        response = await api_client.get(
            f"{SETUP}/tables?dining_area_id={terrace['id']}", headers=_auth(token)
        )

        assert [item["code"] for item in response.json()["items"]] == ["T2"]


# --------------------------------------------------------------------------- stations


class TestStations:
    async def test_creating_one(self, db_session: AsyncSession, api_client: AsyncClient) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/stations",
            json={"code": "tandoor", "name": "Tandoor"},
            headers=_auth(token),
        )

        assert response.status_code == 201
        assert response.json()["code"] == "tandoor"

    async def test_a_code_with_capitals_or_spaces_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`seed/menu.yaml` routes dishes by these values and M08 renders a column per station, so
        the code is an identifier with a shape, not a label."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/stations", json={"code": "Main Kitchen", "name": "x"}, headers=_auth(token)
        )

        assert response.status_code == 422

    async def test_a_duplicate_code_is_a_conflict(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        await api_client.post(
            f"{SETUP}/stations", json={"code": "tandoor", "name": "Tandoor"}, headers=_auth(token)
        )

        response = await api_client.post(
            f"{SETUP}/stations", json={"code": "tandoor", "name": "Second"}, headers=_auth(token)
        )

        assert response.status_code == 409
        assert response.json()["code"] == "station.code_taken"

    async def test_the_name_is_editable(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        created = await api_client.post(
            f"{SETUP}/stations", json={"code": "tandoor", "name": "Tandoor"}, headers=_auth(token)
        )

        response = await api_client.patch(
            f"{SETUP}/stations/{created.json()['id']}",
            json={"name": "Tandoor & Grill"},
            headers=_auth(token),
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Tandoor & Grill"

    async def test_the_code_is_not_editable(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Renaming a code orphans the menu routing that points at it. The schema offers no field
        for it, so the attempt is refused rather than silently ignored."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        created = await api_client.post(
            f"{SETUP}/stations", json={"code": "tandoor", "name": "Tandoor"}, headers=_auth(token)
        )

        response = await api_client.patch(
            f"{SETUP}/stations/{created.json()['id']}",
            json={"code": "grill"},
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_an_unknown_station_is_a_404(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            f"{SETUP}/stations/{uuid.uuid4()}", json={"name": "Nowhere"}, headers=_auth(token)
        )

        assert response.status_code == 404


# --------------------------------------------------------------------------- tax


class TestTaxGroups:
    async def test_creating_a_rate(self, db_session: AsyncSession, api_client: AsyncClient) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={"name": "GST 5%", "rate": "0.0500", "effective_from": _tomorrow()},
            headers=_auth(token),
        )

        assert response.status_code == 201
        # A string, never a float: no JavaScript number ever touches a tax rate.
        assert response.json()["rate"] == "0.0500"
        assert response.json()["effective_to"] is None

    async def test_a_rate_cannot_start_in_the_past(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Back-dating is how a change that looks legitimate reaches invoices already issued."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={"name": "GST 5%", "rate": "0.0500", "effective_from": "2020-01-01"},
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "tax_group.back_dated"

    async def test_today_is_the_restaurants_today_not_the_servers(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """ADR 0004. A restaurant in Kiribati (UTC+14) is already on tomorrow's date while the
        server is still on today's, so a rate starting on its "today" must be accepted. Validating
        against the server's UTC date would refuse a legitimate change.
        """
        await _world(db_session, "owner", timezone="Pacific/Kiritimati")
        token = await _token(api_client, "owner")
        local_today = datetime.now(UTC).astimezone(ZoneInfo("Pacific/Kiritimati"))

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={
                "name": "GST 5%",
                "rate": "0.0500",
                "effective_from": local_today.date().isoformat(),
            },
            headers=_auth(token),
        )

        assert response.status_code == 201, response.text

    async def test_a_rate_above_one_hundred_percent_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={"name": "Absurd", "rate": "1.5000", "effective_from": _tomorrow()},
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_a_rate_is_superseded_rather_than_edited(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The rule this table exists for. The old row keeps its dates; the new row starts the day
        after the old one ends, so an order on any date resolves to exactly one rate."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        start = date.fromisoformat(_tomorrow())
        first = await api_client.post(
            f"{SETUP}/tax-groups",
            json={"name": "GST 5%", "rate": "0.0500", "effective_from": start.isoformat()},
            headers=_auth(token),
        )
        changeover = (start + timedelta(days=30)).isoformat()

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={
                "name": "GST 12%",
                "rate": "0.1200",
                "effective_from": changeover,
                "supersedes_id": first.json()["id"],
            },
            headers=_auth(token),
        )

        assert response.status_code == 201
        listed = (await api_client.get(f"{SETUP}/tax-groups", headers=_auth(token))).json()["items"]
        by_name = {item["name"]: item for item in listed}
        # The old rate is still there, now closed — an invoice from before the changeover cites it.
        assert by_name["GST 5%"]["rate"] == "0.0500"
        assert (
            by_name["GST 5%"]["effective_to"]
            == (date.fromisoformat(changeover) - timedelta(days=1)).isoformat()
        )
        assert by_name["GST 12%"]["effective_to"] is None

    async def test_the_two_periods_meet_without_a_gap_or_an_overlap(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """One day belongs to exactly one rate. A gap leaves an order with no rate; an overlap
        leaves it with whichever the query happened to return first."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        start = date.fromisoformat(_tomorrow())
        first = await api_client.post(
            f"{SETUP}/tax-groups",
            json={"name": "GST 5%", "rate": "0.0500", "effective_from": start.isoformat()},
            headers=_auth(token),
        )
        changeover = start + timedelta(days=30)
        await api_client.post(
            f"{SETUP}/tax-groups",
            json={
                "name": "GST 12%",
                "rate": "0.1200",
                "effective_from": changeover.isoformat(),
                "supersedes_id": first.json()["id"],
            },
            headers=_auth(token),
        )

        listed = (await api_client.get(f"{SETUP}/tax-groups", headers=_auth(token))).json()["items"]
        closed = next(item for item in listed if item["name"] == "GST 5%")
        opened = next(item for item in listed if item["name"] == "GST 12%")

        assert date.fromisoformat(closed["effective_to"]) + timedelta(days=1) == date.fromisoformat(
            opened["effective_from"]
        )

    async def test_a_rate_cannot_be_superseded_twice(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        start = date.fromisoformat(_tomorrow())
        first = await api_client.post(
            f"{SETUP}/tax-groups",
            json={"name": "GST 5%", "rate": "0.0500", "effective_from": start.isoformat()},
            headers=_auth(token),
        )
        replacement = {
            "name": "GST 12%",
            "rate": "0.1200",
            "effective_from": (start + timedelta(days=30)).isoformat(),
            "supersedes_id": first.json()["id"],
        }
        await api_client.post(f"{SETUP}/tax-groups", json=replacement, headers=_auth(token))

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={**replacement, "name": "GST 18%", "rate": "0.1800"},
            headers=_auth(token),
        )

        assert response.status_code == 409
        assert response.json()["code"] == "tax_group.already_superseded"

    async def test_a_replacement_cannot_start_before_what_it_replaces(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        start = date.fromisoformat(_tomorrow()) + timedelta(days=10)
        first = await api_client.post(
            f"{SETUP}/tax-groups",
            json={"name": "GST 5%", "rate": "0.0500", "effective_from": start.isoformat()},
            headers=_auth(token),
        )

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={
                "name": "GST 12%",
                "rate": "0.1200",
                "effective_from": (start - timedelta(days=1)).isoformat(),
                "supersedes_id": first.json()["id"],
            },
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "tax_group.starts_too_early"

    async def test_superseding_something_that_does_not_exist_is_a_404(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={
                "name": "GST 12%",
                "rate": "0.1200",
                "effective_from": _tomorrow(),
                "supersedes_id": str(uuid.uuid4()),
            },
            headers=_auth(token),
        )

        assert response.status_code == 404

    @pytest.mark.parametrize("field", ["rate", "effective_from", "effective_to", "is_inclusive"])
    async def test_nothing_but_the_name_can_be_patched(
        self, db_session: AsyncSession, api_client: AsyncClient, field: str
    ) -> None:
        """Immutability asserted field by field, because "the schema does not have it" is only true
        until someone adds it back for a good-sounding reason."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        created = await api_client.post(
            f"{SETUP}/tax-groups",
            json={"name": "GST 5%", "rate": "0.0500", "effective_from": _tomorrow()},
            headers=_auth(token),
        )

        response = await api_client.patch(
            f"{SETUP}/tax-groups/{created.json()['id']}",
            json={"name": "GST 5%", field: "0.1800" if field == "rate" else "2030-01-01"},
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_the_name_can_be_corrected(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A typo in a label is not a restatement of tax — the rate and the dates are what must
        not move."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        created = await api_client.post(
            f"{SETUP}/tax-groups",
            json={"name": "GTS 5%", "rate": "0.0500", "effective_from": _tomorrow()},
            headers=_auth(token),
        )

        response = await api_client.patch(
            f"{SETUP}/tax-groups/{created.json()['id']}",
            json={"name": "GST 5%"},
            headers=_auth(token),
        )

        assert response.status_code == 200
        assert response.json()["name"] == "GST 5%"
        assert response.json()["rate"] == "0.0500"

    async def test_a_manager_may_not_change_tax(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "manager")
        token = await _token(api_client, "manager")

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={"name": "GST 0%", "rate": "0.0000", "effective_from": _tomorrow()},
            headers=_auth(token),
        )

        assert response.status_code == 403
