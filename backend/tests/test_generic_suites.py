"""The four generic suites (docs/testing-strategy.md).

These do not test M01. They enumerate the application and assert a property of *every* route, so a
route added in M07 is covered the moment it is registered and nobody has to remember. That is the
whole point: per-endpoint security tests protect the endpoints somebody thought about.

    1. Tenant isolation   — restaurant A cannot read, write or confirm restaurant B's resources
    2. Permission matrix  — every route x every role, against the declared catalogue
    3. Persona separation — no guest token reaches a staff route (ADR 0009)
    4. Route declaration  — every route declares a permission; default-deny is enforced

Suite 0 is the meta-test below, and it is not optional: all four suites assert "for every route
in ...", so an enumerator returning nothing makes every one of them pass while testing nothing.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import PUBLIC_ROUTES
from app.core.config import get_settings
from app.core.enums import EmploymentType, TableStatus, UserAccountStatus
from app.core.permissions import CATALOGUE, permissions_for_role
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee, UserAccount
from app.models.setup import DiningArea, RestaurantTable, Station, TaxGroup, TaxRate
from app.models.tenancy import Organization, Restaurant
from tests.helpers.routes import RouteInfo, all_routes, staff_routes

PASSWORD = "Staging#2026"  # noqa: S105

# Routes that legitimately take no permission, because they are what produces the identity a
# permission would be checked against. Kept small and explicit — an allow-list of four is
# auditable, whereas "skip routes without a marker" would hide every mistake.
_PUBLIC = PUBLIC_ROUTES | {
    "GET /api/v1/health",
    "GET /api/v1/ready",
    "GET /api/v1/version",
    # Authenticated, but every signed-in employee may read their own profile — there is no
    # permission that could gate it without gating the thing that reports permissions.
    "GET /api/v1/auth/me",
    "POST /api/v1/auth/password",
    # Authenticated, and authorises itself: whether someone may move to a branch depends on where
    # they are employed, which no single permission string can express. The refusal is tested
    # directly in tests/test_auth_switch.py against a two-organization, two-branch fixture (G-17).
    "POST /api/v1/auth/switch",
}


# --------------------------------------------------------------------------- suite 0


class TestTheEnumeratorItself:
    """Not one of the four. It is what stops the other four becoming decorative.

    Every suite below is a loop over routes. If the loop body never runs, the suite passes. This
    class asserts the loop has something to iterate, so a FastAPI upgrade that changes the routing
    internals fails here — loudly, in one place — rather than silently disarming the security
    tests for the rest of the project.
    """

    def test_the_enumerator_finds_routes(self, api: FastAPI) -> None:
        assert len(all_routes(api)) >= 15

    def test_the_enumerator_finds_the_staff_routes(self, api: FastAPI) -> None:
        assert len(staff_routes(api)) >= 8

    def test_the_enumerator_reads_a_declared_permission(self, api: FastAPI) -> None:
        # If permission extraction silently returned () for everything, suite 4 would pass by
        # treating every route as public and suite 2 would have nothing to check.
        listing = next(
            route
            for route in staff_routes(api)
            if route.path == "/api/v1/staff/employees" and route.method == "GET"
        )
        assert listing.permissions == ("employee.view",)

    def test_the_enumerator_finds_the_known_endpoints(self, api: FastAPI) -> None:
        keys = {route.key for route in all_routes(api)}
        for expected in (
            "POST /api/v1/auth/login",
            "POST /api/v1/auth/refresh",
            "GET /api/v1/auth/me",
            "GET /api/v1/staff/employees",
            "POST /api/v1/staff/employees",
            "POST /api/v1/staff/employees/{employee_id}/roles",
            "GET /api/v1/staff/roles",
        ):
            assert expected in keys, f"{expected} missing; enumerator or routing changed"


# --------------------------------------------------------------------------- suite 4


class TestEveryRouteDeclaresAPermission:
    """Suite 4. Default-deny, enforced by the build rather than by review."""

    def test_no_staff_route_is_missing_a_permission(self, api: FastAPI) -> None:
        undeclared = [
            route.key
            for route in staff_routes(api)
            if not route.permissions and route.key not in _PUBLIC
        ]
        assert not undeclared, (
            f"these routes declare no permission and are not on the public allow-list: {undeclared}"
        )

    def test_every_declared_permission_exists_in_the_catalogue(self, api: FastAPI) -> None:
        # A route requiring a permission no role can hold reads as "mysteriously denied" rather
        # than as an error, and would survive review indefinitely.
        known = {permission.code for permission in CATALOGUE.permissions}
        for route in all_routes(api):
            unknown = set(route.permissions) - known
            assert not unknown, f"{route.key} requires unknown permission(s) {sorted(unknown)}"

    def test_the_public_allow_list_has_no_stale_entries(self, api: FastAPI) -> None:
        # An entry left behind after a route is renamed silently exempts nothing — but the next
        # person reads it as "this path is intentionally public", which is worse than useless.
        keys = {route.key for route in all_routes(api)}
        assert not (_PUBLIC - keys), f"allow-list names routes that do not exist: {_PUBLIC - keys}"


# --------------------------------------------------------------------------- fixtures


class Tenant:
    def __init__(self, organization: Organization, restaurant: Restaurant) -> None:
        self.organization = organization
        self.restaurant = restaurant
        self.tokens: dict[str, str] = {}


async def _tenant(session: AsyncSession, slug: str, roles: tuple[str, ...]) -> Tenant:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(organization_id=organization.id, name=slug.title(), code="R1")
    session.add(restaurant)
    await session.flush()
    tenant = Tenant(organization, restaurant)

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
    return tenant


def _guest_token() -> str:
    """A structurally valid token from the guest realm (ADR 0009).

    Signed with the real key on purpose: a token that failed signature verification would be
    rejected for the wrong reason and would prove nothing about persona separation.
    """
    settings = get_settings()
    return jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "typ": "guest",
            "table": "T4",
            "exp": datetime.now(UTC) + timedelta(minutes=15),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def _sample_body(route: RouteInfo) -> dict[str, Any]:
    """Enough of a body to get past validation and reach authorisation.

    A 422 would mean the request never reached the permission check, and the suite would be
    asserting nothing while looking green.
    """
    if route.path.endswith("/roles"):
        return {"role_ids": []}
    if route.path.endswith("/password"):
        return {"new_password": "SomeNewPassword#1"}
    if route.method == "POST" and route.path == "/api/v1/staff/employees":
        return {
            "full_name": "Probe Person",
            "employee_code": "PROBE1",
            "joined_on": "2026-01-01",
        }
    if route.path.endswith("/auth/switch"):
        return {"restaurant_id": str(_PROBE_UUID)}
    if route.path.endswith("/setup/dining-areas"):
        return {"name": "Probe Area"}
    if route.path.endswith("/setup/tables"):
        return {"dining_area_id": str(_PROBE_UUID), "code": "P1", "seats": 2}
    if route.path.endswith("/setup/stations"):
        return {"code": "probe_station", "name": "Probe Station"}
    if route.path.endswith("/setup/tax-groups"):
        return {
            "code": "PROBETAX",
            "name": "Probe Tax",
            "rate": "0.0500",
            "effective_from": "2099-01-01",
        }
    if route.path.endswith("/rates"):
        return {"rate": "0.1200", "effective_from": "2099-06-01"}
    if "/setup/tax-groups/" in route.path or "/setup/dining-areas/" in route.path:
        return {"name": "Probe Rename"}
    if "/setup/stations/" in route.path:
        return {"name": "Probe Rename"}
    if "/setup/tables/" in route.path:
        return {"seats": 4}
    if route.method == "PATCH":
        return {"full_name": "Probe Person"}
    return {}


_PROBE_UUID = uuid.UUID("00000000-0000-0000-0000-0000000000ff")

# Every path parameter the staff surface uses, and the victim resource each one addresses.
#
# **A parameter missing from this map fails suite 1 rather than being skipped**, which is the whole
# point of the map existing. The previous version of the suite matched `{employee_id}` and
# `continue`d past everything else; when M02 added four PATCH routes taking `{area_id}`,
# `{table_id}`, `{station_id}` and `{tax_group_id}`, the suite went on passing while probing none of
# them — the four routes where a cross-tenant *write* would happen. A future module adding
# `{menu_item_id}` now gets a failing build telling it to seed a victim row here.
_VICTIM_PARAMETERS = frozenset({"employee_id", "area_id", "table_id", "station_id", "tax_group_id"})


async def _victim_resources(
    session: AsyncSession, tenant: Tenant, *, prefix: str = "Victim", seq: int = 0, code: str = "V1"
) -> dict[str, str]:
    """One row of every tenant-owned kind, belonging to the victim restaurant.

    These are the things another tenant must not be able to read, write or confirm the existence
    of. Created directly rather than through the API so the fixture does not depend on the
    endpoints it is about to probe.
    """
    restaurant_id = tenant.restaurant.id
    area = DiningArea(restaurant_id=restaurant_id, name=f"{prefix} Hall", seq=seq, is_active=True)
    station = Station(
        restaurant_id=restaurant_id,
        code=f"{prefix.lower()}_pass",
        name=f"{prefix} Pass",
        seq=seq,
        is_active=True,
    )
    tax = TaxGroup(
        restaurant_id=restaurant_id,
        code=f"{prefix.upper()}GST",
        name=f"{prefix} GST",
        is_active=True,
    )
    session.add_all([area, station, tax])
    await session.flush()
    # The rate hangs off the group, so the victim has something a probe could read through
    # `/rates` as well as through the group itself.
    session.add(
        TaxRate(
            restaurant_id=restaurant_id,
            tax_group_id=tax.id,
            rate=Decimal("0.0500"),
            is_inclusive=False,
            effective_from=date(2026, 1, 1),
        )
    )
    table = RestaurantTable(
        restaurant_id=restaurant_id,
        dining_area_id=area.id,
        code=code,
        seats=4,
        status=TableStatus.FREE,
        is_active=True,
    )
    session.add(table)
    await session.flush()

    employee = (
        await session.scalars(
            select(Employee.id).where(Employee.organization_id == tenant.organization.id)
        )
    ).first()
    assert employee is not None, "the victim tenant has no employee to probe"

    return {
        "employee_id": str(employee),
        "area_id": str(area.id),
        "table_id": str(table.id),
        "station_id": str(station.id),
        "tax_group_id": str(tax.id),
    }


# --------------------------------------------------------------------------- suites 1-3


class TestTenantIsolationAcrossEveryStaffRoute:
    """Suite 1. The product's #1 bug class, asserted route by route rather than case by case."""

    async def test_every_path_parameter_has_a_victim_row(self, api: FastAPI) -> None:
        """The guard that stops this suite quietly shrinking.

        Suite 1 is a loop that substitutes a victim id into each route's path. A parameter it has
        no victim for cannot be probed — and the previous version simply skipped those, so adding a
        route with a new parameter name removed it from the product's most important security test
        without changing a single line of this file. M02 added four such routes.

        Now an unknown parameter fails here instead, naming the route and the parameter.
        """
        unknown: dict[str, str] = {}
        for route in staff_routes(api):
            for name in re.findall(r"\{([a-z_]+)\}", route.path):
                if name not in _VICTIM_PARAMETERS:
                    unknown[name] = route.key
        assert not unknown, (
            "these path parameters have no victim row, so suite 1 cannot probe their routes: "
            f"{unknown}. Add the parameter to _VICTIM_PARAMETERS and seed a row for it in "
            "_victim_resources, or the routes below are exempt from tenant-isolation testing."
        )

    async def test_no_staff_route_exposes_another_tenants_resource(
        self, db_session: AsyncSession, api: FastAPI, api_client: AsyncClient
    ) -> None:
        spice = await _tenant(db_session, "spice-garden", ("owner",))
        await _tenant(db_session, "tandoor-house", ("owner",))
        victims = await _victim_resources(db_session, spice)
        await db_session.commit()

        token = await _login(api_client, "owner@tandoor-house.test")
        failures: list[str] = []
        probed = 0
        for route in staff_routes(api):
            if "{" not in route.path:
                continue
            url = route.path
            for name, value in victims.items():
                url = url.replace(f"{{{name}}}", value)
            assert "{" not in url, f"no victim id for {route.key}"
            probed += 1
            response = await api_client.request(
                route.method,
                url,
                json=_sample_body(route),
                headers={"Authorization": f"Bearer {token}"},
            )
            # 422 is acceptable only because a body may fail validation before authorisation;
            # 200 or 201 would mean one tenant reached another's row.
            if response.status_code not in (403, 404, 422):
                failures.append(f"{route.key} -> {response.status_code}")
        assert not failures, f"cross-tenant access succeeded on: {failures}"
        # The loop ran. Without this the suite passes when the enumerator returns nothing, which is
        # the failure mode suite 0 exists to prevent and this is its per-suite half.
        assert probed >= 10, f"suite 1 only probed {probed} routes; it should cover every id route"

    async def test_no_list_route_returns_another_tenants_rows(
        self, db_session: AsyncSession, api: FastAPI, api_client: AsyncClient
    ) -> None:
        """Suite 1's other half: the routes that take no id.

        The loop above substitutes a victim id into each path, so `if "{" not in route.path:
        continue` silently skipped every route without one — which is all four setup lists, the
        employee list and the restaurant settings. Those are where a dropped `restaurant_id`
        predicate leaks in *bulk* rather than one row at a time, so they were the more dangerous
        half and they were exempt. `test_setup_endpoints.py` meanwhile said isolation was "asserted
        for every route at once by suite 1", which is how nobody noticed. Found by external review.

        The victim tenant is furnished and the attacker tenant is bare, so any row at all in an
        attacker's response crossed the boundary.
        """
        spice = await _tenant(db_session, "spice-garden", ("owner",))
        await _tenant(db_session, "tandoor-house", ("owner",))
        await _victim_resources(db_session, spice)
        await db_session.commit()

        token = await _login(api_client, "owner@tandoor-house.test")
        failures: list[str] = []
        probed = 0
        for route in staff_routes(api):
            if "{" in route.path or route.method != "GET":
                continue
            probed += 1
            response = await api_client.get(
                route.path, headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code != 200:
                continue
            # Every seeded victim row is named "Victim …" precisely so this can be a substring
            # check rather than a per-endpoint shape parser.
            if "Victim" in response.text:
                failures.append(f"{route.key} -> {response.text[:160]}")
        assert not failures, f"a list route returned another tenant's rows: {failures}"
        assert probed >= 5, f"suite 1b only probed {probed} list routes"

    async def test_a_cursor_naming_another_tenants_row_does_not_move_the_page(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The leak no row-level check can see.

        Every paged list resolves its cursor's sort key with a subquery. Those subqueries were not
        tenant-scoped, so passing another restaurant's row id returned *that* row's `seq` / `code` /
        `effective_from` and offset the page by it. No row crossed the boundary — the **ordering
        key** did, and feeding ids in and watching where the page starts reads it back out. The tax
        cursor leaked when a competitor last changed their GST rate.

        A foreign cursor must be indistinguishable from a meaningless one: an empty page.

        **The attacker tenant is given rows of its own, and that is the whole test.** The first
        version of this seeded nothing for the attacker, so its page was empty whether the cursor
        leaked or not, and the assertion held against the bug it was written to catch. With rows
        present the two outcomes finally differ: a leaked cursor resolves the victim's low sort key
        and returns the attacker's later rows, while correct scoping yields NULL and an empty page.
        """
        spice = await _tenant(db_session, "spice-garden", ("owner",))
        tandoor = await _tenant(db_session, "tandoor-house", ("owner",))
        victims = await _victim_resources(db_session, spice)
        # The attacker's own floor, deliberately sorting *after* the victim's rows, so a cursor that
        # resolved across the boundary would return these instead of nothing.
        await _victim_resources(db_session, tandoor, prefix="Rival", seq=5, code="Z9")
        await db_session.commit()

        token = await _login(api_client, "owner@tandoor-house.test")
        for path, victim in (
            ("/api/v1/staff/setup/dining-areas", victims["area_id"]),
            ("/api/v1/staff/setup/tables", victims["table_id"]),
            ("/api/v1/staff/setup/stations", victims["station_id"]),
            ("/api/v1/staff/setup/tax-groups", victims["tax_group_id"]),
        ):
            response = await api_client.get(
                f"{path}?cursor={victim}", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200, response.text
            assert response.json()["items"] == [], (
                f"{path} honoured a cursor belonging to another tenant"
            )


class TestPersonaSeparation:
    """Suite 3. A guest token must not reach the employee surface (ADR 0009)."""

    async def test_no_guest_token_satisfies_any_staff_route(
        self, db_session: AsyncSession, api: FastAPI, api_client: AsyncClient
    ) -> None:
        await _tenant(db_session, "spice-garden", ("owner",))
        await db_session.commit()

        failures: list[str] = []
        for route in staff_routes(api):
            url = route.path.replace("{employee_id}", "00000000-0000-0000-0000-000000000002")
            response = await api_client.request(
                route.method,
                url,
                json=_sample_body(route),
                headers={"Authorization": f"Bearer {_guest_token()}"},
            )
            if response.status_code not in (401, 403):
                failures.append(f"{route.key} -> {response.status_code}")
        assert not failures, f"a guest token was accepted by: {failures}"

    async def test_no_token_at_all_is_refused_by_every_staff_route(
        self, api: FastAPI, api_client: AsyncClient
    ) -> None:
        failures: list[str] = []
        for route in staff_routes(api):
            url = route.path.replace("{employee_id}", "00000000-0000-0000-0000-000000000002")
            response = await api_client.request(route.method, url, json=_sample_body(route))
            if response.status_code != 401:
                failures.append(f"{route.key} -> {response.status_code}")
        assert not failures, f"these routes served an unauthenticated request: {failures}"


class TestThePermissionMatrix:
    """Suite 2. Every staff route against every role, checked against the declared catalogue.

    The assertion is not "a waiter gets 403 on the staff list" — it is that the *whole grid* agrees
    with permissions.json. A permission accidentally added to a role shows up here as a route that
    unexpectedly succeeded.
    """

    @pytest.mark.parametrize(
        "role_code", [role.code for role in CATALOGUE.roles if role.code != "owner"]
    )
    async def test_a_role_reaches_exactly_the_routes_its_permissions_allow(
        self, db_session: AsyncSession, api: FastAPI, api_client: AsyncClient, role_code: str
    ) -> None:
        await _tenant(db_session, f"org-{role_code}", (role_code,))
        await db_session.commit()
        granted = permissions_for_role(role_code)

        token = await _login(api_client, f"{role_code}@org-{role_code}.test")
        mismatches: list[str] = []
        for route in staff_routes(api):
            if not route.permissions:
                continue
            url = route.path.replace("{employee_id}", "00000000-0000-0000-0000-000000000002")
            response = await api_client.request(
                route.method,
                url,
                json=_sample_body(route),
                headers={"Authorization": f"Bearer {token}"},
            )
            should_be_allowed = set(route.permissions) <= granted
            was_denied = response.status_code == 403
            if should_be_allowed and was_denied:
                mismatches.append(f"{route.key}: {role_code} holds it but was denied")
            if not should_be_allowed and not was_denied:
                mismatches.append(
                    f"{route.key}: {role_code} lacks {route.permissions} "
                    f"but got {response.status_code}"
                )
        assert not mismatches, "\n".join(mismatches)


async def _login(client: AsyncClient, identifier: str, *, expect_failure: bool = False) -> Any:
    response = await client.post(
        "/api/v1/auth/login", json={"identifier": identifier, "password": PASSWORD}
    )
    if response.status_code != 200:
        if expect_failure:
            return None
        raise AssertionError(
            f"login failed for {identifier}: {response.status_code} {response.text}"
        )
    return response.json()["access_token"]
