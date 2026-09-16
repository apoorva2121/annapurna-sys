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
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EmploymentType, TableStatus, UserAccountStatus
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.audit import AuditLog
from app.models.identity import Employee, UserAccount
from app.models.setup import TaxGroup, TaxRate
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
            password_hash=await hash_password(PASSWORD),
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

        response = await api_client.post(
            f"{SETUP}/tables/{table['id']}/status",
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

        response = await api_client.post(
            f"{SETUP}/tables/{table['id']}/status",
            json={"status": "on_fire"},
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_status_is_not_a_field_of_the_general_table_edit(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """M07. Status has a transition rule, so a PATCH carrying it is refused rather than
        applied around the rule — an extra field is a 422 under `extra="forbid"`."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        area = await _area(api_client, token)
        table = await _table(api_client, token, area["id"])

        response = await api_client.patch(
            f"{SETUP}/tables/{table['id']}",
            json={"status": TableStatus.FREE},
            headers=_auth(token),
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


async def _tax_group(
    client: AsyncClient,
    token: str,
    *,
    code: str = "GST5",
    name: str = "GST 5% (restaurant, no ITC)",
    rate: str = "0.0500",
    effective_from: str | None = None,
) -> str:
    """A group charging `rate` from tomorrow, returning its id. Most tax tests start here."""
    response = await client.post(
        f"{SETUP}/tax-groups",
        json={
            "code": code,
            "name": name,
            "rate": rate,
            "effective_from": effective_from or _tomorrow(),
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    created: str = response.json()["id"]
    return created


class TestTaxGroups:
    """A tax group is an identity; its rates are dated rows beneath it (M03 spec decision 1).

    M02 had one table doing both jobs, and these tests were written against it: they looked rates up
    by `name`, and a "supersession" created a second row with a *different* name — which is not what
    a rate change is. `GST 5%` becoming `GST 12%` is the same tax class charging a new rate, not a
    new class. The old shape could not express that, and the tests inherited the confusion.
    """

    async def test_creating_a_group_creates_the_rate_it_charges(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={
                "code": "GST5",
                "name": "GST 5% (restaurant, no ITC)",
                "rate": "0.0500",
                "effective_from": _tomorrow(),
            },
            headers=_auth(token),
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["code"] == "GST5"
        assert len(body["rates"]) == 1
        # A string, never a float: no JavaScript number ever touches a tax rate.
        assert body["rates"][0]["rate"] == "0.0500"
        assert body["rates"][0]["effective_to"] is None

    async def test_a_group_cannot_be_created_without_a_rate(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A group charging nothing is a trap: a menu item could be attached to it and M07 would
        find no rate at order time. The two are created together or not at all."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={"code": "GST5", "name": "GST 5%", "effective_from": _tomorrow()},
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_a_rate_cannot_start_in_the_past(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Back-dating is how a change that looks legitimate reaches invoices already issued."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={
                "code": "GST5",
                "name": "GST 5%",
                "rate": "0.0500",
                "effective_from": "2020-01-01",
            },
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "tax_group.back_dated"

    async def test_a_new_rate_cannot_be_back_dated_either(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The rule applied to creation in M02 and to one path only. Adding a rate to an existing
        group is the path that actually matters — it is the one a real restaurant uses."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        group = await _tax_group(api_client, token)

        response = await api_client.post(
            f"{SETUP}/tax-groups/{group}/rates",
            json={"rate": "0.1200", "effective_from": "2020-01-01"},
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "tax_group.back_dated"

    async def test_today_is_the_restaurants_today_not_the_servers(
        self, db_session: AsyncSession, api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ADR 0004, asserted in the direction that can actually fail.

        This used `Pacific/Kiritimati` and proved nothing. Kiribati is UTC+14, so its local date is
        never *behind* UTC - and the guard only refuses dates in the **past**. A server-UTC
        implementation therefore returns 201 for it at every hour of every day, which is exactly the
        implementation the test claimed to rule out. Found by external review.

        New York at 22:00 local is the case that discriminates: it is already tomorrow in UTC, so
        the restaurant's own today would be refused as back-dated by a server-clock implementation.

        The clock is pinned because a date rule that is correct only during part of the UTC day is
        not correct, and a test that is green only during part of the day is not a test.
        """
        await _world(db_session, "owner", timezone="America/New_York")
        token = await _token(api_client, "owner")

        # 03:00 UTC on the 12th is 22:00 EST on the 11th. Business date the 11th; UTC date the 12th.
        pinned = datetime(2026, 1, 12, 3, 0, tzinfo=UTC)

        # A stand-in rather than a `datetime` subclass: subclassing makes mypy demand that `now`
        # return the subclass. The module only ever calls `datetime.now(...)`, so this is the whole
        # surface it needs.
        class _Clock:
            @staticmethod
            def now(tz: object = None) -> datetime:  # noqa: ARG004
                return pinned

        monkeypatch.setattr("app.services.setup.datetime", _Clock)

        accepted = await api_client.post(
            f"{SETUP}/tax-groups",
            json={
                "code": "GST5",
                "name": "GST 5%",
                "rate": "0.0500",
                "effective_from": "2026-01-11",
            },
            headers=_auth(token),
        )
        refused = await api_client.post(
            f"{SETUP}/tax-groups",
            json={
                "code": "GST12",
                "name": "GST 12%",
                "rate": "0.1200",
                "effective_from": "2026-01-10",
            },
            headers=_auth(token),
        )

        # The restaurant's today, which UTC already calls yesterday.
        assert accepted.status_code == 201, accepted.text
        # And the day before it is still refused, so the guard has not simply been switched off.
        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "tax_group.back_dated"

    async def test_a_rate_above_one_hundred_percent_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={
                "code": "ABSURD",
                "name": "Absurd",
                "rate": "1.5000",
                "effective_from": _tomorrow(),
            },
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_a_code_cannot_be_reused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        await _tax_group(api_client, token, code="GST5")

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={
                "code": "GST5",
                "name": "Something else",
                "rate": "0.1800",
                "effective_from": _tomorrow(),
            },
            headers=_auth(token),
        )

        assert response.status_code == 409
        assert response.json()["code"] == "tax_group.code_taken"

    async def test_a_rate_change_keeps_the_group_a_menu_item_points_at(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """**The whole reason for M03 decision 1.**

        `menu_item_variant.tax_group_id` references the group. A rate change must therefore leave
        that id alone — otherwise every dish on the menu points at a closed period the first time
        GST moves, and somebody has to repoint two hundred rows by hand.

        Under M02's shape this was not merely unasserted, it was *false*: a supersession created a
        second `tax_group` row with a new id, so the id a dish held stopped being current.
        """
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        group = await _tax_group(api_client, token)
        changeover = (date.fromisoformat(_tomorrow()) + timedelta(days=30)).isoformat()

        response = await api_client.post(
            f"{SETUP}/tax-groups/{group}/rates",
            json={"rate": "0.1200", "effective_from": changeover},
            headers=_auth(token),
        )

        assert response.status_code == 201, response.text
        # Same group. This is the assertion the module exists for.
        assert response.json()["id"] == group

        listed = (await api_client.get(f"{SETUP}/tax-groups", headers=_auth(token))).json()["items"]
        assert [item["id"] for item in listed] == [group], "a rate change must not create a group"
        rates = {item["rate"]: item for item in listed[0]["rates"]}
        # The old rate is still there, now closed — an invoice from before the changeover cites it.
        assert (
            rates["0.0500"]["effective_to"]
            == (date.fromisoformat(changeover) - timedelta(days=1)).isoformat()
        )
        assert rates["0.1200"]["effective_to"] is None

    async def test_the_two_periods_meet_without_a_gap_or_an_overlap(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """One day belongs to exactly one rate. A gap leaves an order with no rate; an overlap
        leaves it with whichever the query happened to return first."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        group = await _tax_group(api_client, token)
        changeover = date.fromisoformat(_tomorrow()) + timedelta(days=30)

        body = (
            await api_client.post(
                f"{SETUP}/tax-groups/{group}/rates",
                json={"rate": "0.1200", "effective_from": changeover.isoformat()},
                headers=_auth(token),
            )
        ).json()

        rates = {item["rate"]: item for item in body["rates"]}
        assert date.fromisoformat(rates["0.0500"]["effective_to"]) + timedelta(
            days=1
        ) == date.fromisoformat(rates["0.1200"]["effective_from"])

    async def test_a_rate_cannot_start_on_the_day_another_one_starts(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Two rates of one group opening on the same date is the overlap that makes tax
        nondeterministic — an order line would take whichever the planner returned.

        This began life asserting a separate `starts_too_early` refusal and came back 409 instead of
        422, which was the test doing its job: the scheduled-rate check already covered this case,
        so the second branch was unreachable. One situation, one code.
        """
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        start = date.fromisoformat(_tomorrow()) + timedelta(days=10)
        group = await _tax_group(api_client, token, effective_from=start.isoformat())

        response = await api_client.post(
            f"{SETUP}/tax-groups/{group}/rates",
            json={"rate": "0.1200", "effective_from": start.isoformat()},
            headers=_auth(token),
        )

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "tax_group.rate_already_scheduled"

    async def test_a_second_scheduled_rate_is_refused_readably(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Schedule a change, then schedule another one before it. The periods would overlap.

        The exclusion constraint refuses it either way — but an `IntegrityError` reaches the
        catch-all handler as a `500` with a reference number (`docs/backlog.md`: "IntegrityError is
        unmapped"). An owner scheduling two GST changes in a week is an ordinary Tuesday, not an
        internal error, so the service asks first and names the date in the way.
        """
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        group = await _tax_group(api_client, token)
        far = (date.fromisoformat(_tomorrow()) + timedelta(days=60)).isoformat()
        near = (date.fromisoformat(_tomorrow()) + timedelta(days=30)).isoformat()
        await api_client.post(
            f"{SETUP}/tax-groups/{group}/rates",
            json={"rate": "0.1200", "effective_from": far},
            headers=_auth(token),
        )

        response = await api_client.post(
            f"{SETUP}/tax-groups/{group}/rates",
            json={"rate": "0.1800", "effective_from": near},
            headers=_auth(token),
        )

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "tax_group.rate_already_scheduled"
        assert far in response.json()["message"]

    async def test_adding_a_rate_to_a_group_that_does_not_exist_is_a_404(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/tax-groups/{uuid.uuid4()}/rates",
            json={"rate": "0.1200", "effective_from": _tomorrow()},
            headers=_auth(token),
        )

        assert response.status_code == 404

    @pytest.mark.parametrize("field", ["code", "rate", "effective_from", "is_inclusive"])
    async def test_neither_the_code_nor_a_rate_can_be_patched(
        self, db_session: AsyncSession, api_client: AsyncClient, field: str
    ) -> None:
        """Immutability asserted field by field, because "the schema does not have it" is only true
        until someone adds it back for a good-sounding reason.

        `code` joins `menu_item_variant`, `seed/operations.yaml` and every future recipe to this row
        — the same contract `station.code` carries. A rate is immutable because it is copied onto
        order lines and cited by invoices.
        """
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        group = await _tax_group(api_client, token)

        response = await api_client.patch(
            f"{SETUP}/tax-groups/{group}",
            json={"name": "GST 5%", field: "0.1800" if field == "rate" else "OTHER"},
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_the_name_can_be_corrected(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A typo in a label is not a restatement of tax — the code and the rates are what must
        not move.

        Under M02 the display name was also the family key: the exclusion constraint was
        `(restaurant_id, name, daterange)`, so this rename silently changed which rows counted as
        the same rate. Now it changes a label and nothing else.
        """
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        group = await _tax_group(api_client, token, name="GTS 5%")

        response = await api_client.patch(
            f"{SETUP}/tax-groups/{group}",
            json={"name": "GST 5%"},
            headers=_auth(token),
        )

        assert response.status_code == 200
        assert response.json()["name"] == "GST 5%"
        assert response.json()["code"] == "GST5"
        assert response.json()["rates"][0]["rate"] == "0.0500"

    async def test_a_manager_may_not_change_tax(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "manager")
        token = await _token(api_client, "manager")

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={
                "code": "GST0",
                "name": "GST 0%",
                "rate": "0.0000",
                "effective_from": _tomorrow(),
            },
            headers=_auth(token),
        )

        assert response.status_code == 403

    async def test_a_manager_may_not_add_a_rate_either(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The new route needs its own assertion: a permission is declared per route, and the one
        that was added last is the one nobody checked."""
        await _world(db_session, "owner", "manager")
        owner_token = await _token(api_client, "owner")
        group = await _tax_group(api_client, owner_token)
        token = await _token(api_client, "manager")

        response = await api_client.post(
            f"{SETUP}/tax-groups/{group}/rates",
            json={"rate": "0.1200", "effective_from": _tomorrow()},
            headers=_auth(token),
        )

        assert response.status_code == 403


class TestThemeSettings:
    """The restaurant-wide look, deferred into M02 from the UI work.

    Stored in `settings` rather than in columns, because unlike the FSSAI licence that finding S13
    moved *out* of settings, a theme genuinely is configuration — nothing legal or operational
    depends on it.

    The rule worth testing is the one the client cannot sensibly enforce: two festive windows must
    not claim the same day. There is no right answer for a date covered twice, and resolving it by
    precedence would make the second window silently disappear on a date nobody is looking at.
    """

    async def test_a_restaurant_with_no_theme_settings_still_reads(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Every restaurant seeded before this existed has no `theme` key at all. The settings
        screen has to render for them rather than 500."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.get("/api/v1/staff/restaurant", headers=_auth(token))

        assert response.status_code == 200
        assert response.json()["theme"] == {"default": None, "schedule": []}

    async def test_setting_a_restaurant_wide_default(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            "/api/v1/staff/restaurant",
            json={"theme": {"default": "jamun-dark", "schedule": []}},
            headers=_auth(token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["theme"]["default"] == "jamun-dark"

    async def test_an_unknown_theme_id_is_accepted_rather_than_validated_here(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Deliberate. The themes live in `frontend/src/shared/theme/themes.ts`, and a copy of their
        ids here would be the second catalogue finding M12 is about — two lists, free to disagree,
        with the server authoritative over a file it cannot see.

        The client falls back to the default look for an id it does not know, which is a degradation
        rather than a failure, and the settings screen offers a picker so a typo is not reachable
        through the UI.
        """
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            "/api/v1/staff/restaurant",
            json={"theme": {"default": "not-a-real-theme", "schedule": []}},
            headers=_auth(token),
        )

        assert response.status_code == 200

    async def test_a_festive_window_is_stored_with_its_dates(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            "/api/v1/staff/restaurant",
            json={
                "theme": {
                    "default": None,
                    "schedule": [
                        {"theme": "deepavali", "starts_on": "2026-11-06", "ends_on": "2026-11-12"}
                    ],
                }
            },
            headers=_auth(token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["theme"]["schedule"] == [
            {"theme": "deepavali", "starts_on": "2026-11-06", "ends_on": "2026-11-12"}
        ]

    async def test_a_window_that_ends_before_it_starts_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            "/api/v1/staff/restaurant",
            json={
                "theme": {
                    "schedule": [
                        {"theme": "deepavali", "starts_on": "2026-11-12", "ends_on": "2026-11-06"}
                    ]
                }
            },
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_two_windows_covering_the_same_day_are_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """No right answer exists for a date claimed twice, and picking one silently would make the
        other vanish on a day nobody is watching."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            "/api/v1/staff/restaurant",
            json={
                "theme": {
                    "schedule": [
                        {"theme": "deepavali", "starts_on": "2026-11-06", "ends_on": "2026-11-12"},
                        {"theme": "monsoon", "starts_on": "2026-11-10", "ends_on": "2026-11-20"},
                    ]
                }
            },
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_two_windows_that_merely_touch_are_allowed(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """One ending the day before the next begins is a normal calendar, not an overlap — and an
        off-by-one here would refuse a schedule a restaurant legitimately wants."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            "/api/v1/staff/restaurant",
            json={
                "theme": {
                    "schedule": [
                        {"theme": "deepavali", "starts_on": "2026-11-06", "ends_on": "2026-11-12"},
                        {"theme": "monsoon", "starts_on": "2026-11-13", "ends_on": "2026-11-20"},
                    ]
                }
            },
            headers=_auth(token),
        )

        assert response.status_code == 200, response.text

    async def test_saving_the_theme_does_not_disturb_the_fssai_licence(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`settings` is reassigned rather than mutated when the theme is written. Mutating the dict
        in place would flush nothing; replacing it carelessly would drop every other key."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        await api_client.patch(
            "/api/v1/staff/restaurant",
            json={"fssai_licence": "11223344556677"},
            headers=_auth(token),
        )

        await api_client.patch(
            "/api/v1/staff/restaurant",
            json={"theme": {"default": "deepavali", "schedule": []}},
            headers=_auth(token),
        )

        after = await api_client.get("/api/v1/staff/restaurant", headers=_auth(token))
        assert after.json()["fssai_licence"] == "11223344556677"
        assert after.json()["theme"]["default"] == "deepavali"

    async def test_a_manager_may_not_change_the_theme(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "manager")
        token = await _token(api_client, "manager")

        response = await api_client.patch(
            "/api/v1/staff/restaurant",
            json={"theme": {"default": "deepavali", "schedule": []}},
            headers=_auth(token),
        )

        assert response.status_code == 403


class TestTwoLiveRatesOfOneGroup:
    """The guarantee that lived on only one of two code paths.

    Every non-overlap check sat inside `if supersedes_id is not None`, so the *simpler* call —
    create without superseding — could put two live rows of one rate on the same date, and M07's
    "which rate applies?" would take whichever the planner returned: nondeterministic tax on a bill,
    which is a filing problem rather than a data-quality one. Found by external review of M02.

    **The family key has changed and the guarantee has not.** M02 keyed it on the display *name*,
    because that was the only thing distinguishing one rate lineage from another. Renaming a rate
    therefore silently changed which rows counted as the same rate — the bug under the bug. The key
    is now `tax_group_id`, so this class asserts the same rule against an identity instead of a
    string.

    Two *different* groups being current at once is legitimate and must keep working — the seed
    ships GST 5% for restaurant food and GST 18% for packaged goods, both open-ended from the same
    day. A constraint on the restaurant alone would have refused the product's own demo data.
    """

    async def test_a_second_live_rate_for_one_group_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        group = await _tax_group(api_client, token)

        response = await api_client.post(
            f"{SETUP}/tax-groups/{group}/rates",
            json={"rate": "0.1200", "effective_from": _tomorrow()},
            headers=_auth(token),
        )

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "tax_group.rate_already_scheduled"

    async def test_the_database_refuses_it_even_when_the_service_does_not(
        self, db_session: AsyncSession
    ) -> None:
        """The service check is a readable message; the exclusion constraint is the guarantee.

        Written against the model directly, bypassing every service rule, because a guard that only
        exists in Python is one refactor away from not existing. 0008 moved this constraint from
        `(restaurant_id, name, daterange)` to `(tax_group_id, daterange)` and this is the assertion
        that the move kept its teeth.
        """
        world = await _world(db_session, "owner")
        group = TaxGroup(
            restaurant_id=world.restaurant.id, code="GST5", name="GST 5%", is_active=True
        )
        db_session.add(group)
        await db_session.flush()
        overlapping = [
            TaxRate(
                restaurant_id=world.restaurant.id,
                tax_group_id=group.id,
                rate=Decimal(rate),
                is_inclusive=False,
                effective_from=date(2030, 1, 1),
                effective_to=None,
            )
            for rate in ("0.0500", "0.1200")
        ]
        db_session.add_all(overlapping)

        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_two_different_groups_may_be_current_at_once(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The seed's own shape: food and packaged goods are taxed differently on the same day."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        await _tax_group(api_client, token, code="GST5", name="GST 5% (food)", rate="0.0500")

        response = await api_client.post(
            f"{SETUP}/tax-groups",
            json={
                "code": "GST18",
                "name": "GST 18% (packaged)",
                "rate": "0.1800",
                "effective_from": _tomorrow(),
            },
            headers=_auth(token),
        )

        assert response.status_code == 201, response.text
        listed = (await api_client.get(f"{SETUP}/tax-groups", headers=_auth(token))).json()["items"]
        assert {item["code"] for item in listed} == {"GST5", "GST18"}

    async def test_a_future_rate_is_not_caught_by_the_guard(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The guard must refuse overlaps and permit the ordinary case, or it is just an outage.

        A rate change starting after the current one is the whole point of the table.
        """
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        group = await _tax_group(api_client, token)

        response = await api_client.post(
            f"{SETUP}/tax-groups/{group}/rates",
            json={
                "rate": "0.1200",
                "effective_from": (
                    date.fromisoformat(_tomorrow()) + timedelta(days=30)
                ).isoformat(),
            },
            headers=_auth(token),
        )

        assert response.status_code == 201, response.text
        assert len(response.json()["rates"]) == 2
