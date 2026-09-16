"""Races and 500s (backlog-issues B3).

Four backlog rows, all found by the M02 external review, all the same complaint: an ordinary moment
in a restaurant — two admins adding "Terrace" at once, a double-tap on a slow connection, an owner
and a manager editing the floor from two devices — reaches the catch-all handler as "Something went
wrong" with a reference number.

- "`IntegrityError` is unmapped, so every check-then-insert race is a 500"
- "Deactivating an area races a table being created in it"
- "Reordering costs two requests and is not atomic"
- "`MeResponse.restaurants` is unbounded" (tests in test_me_restaurants.py)
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import date, time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.actor import Actor
from app.core.errors import ConflictError
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.setup import DiningArea, RestaurantTable
from app.models.tenancy import Organization, Restaurant
from app.repositories.setup import DiningAreaRepository, RestaurantTableRepository
from app.schemas.setup import DiningAreaCreateRequest, DiningAreaUpdateRequest, TableCreateRequest
from app.services.setup import SetupService
from tests.test_setup_endpoints import SETUP, _area, _auth, _token, _world

MENU = "/api/v1/staff/menu"


# --------------------------------------------------------------------------- the handler


class _Cause(Exception):  # noqa: N818 - mirrors asyncpg's `__cause__`, not an error of ours
    """asyncpg's violation classes carry the constraint name (probed 2026-09-13)."""

    def __init__(self, constraint_name: str) -> None:
        super().__init__("cause")
        self.constraint_name = constraint_name


class _DriverError(Exception):
    """The shape SQLAlchemy's asyncpg adapter puts in `IntegrityError.orig`: a `sqlstate`, with the
    driver's own exception as its cause."""

    def __init__(self, sqlstate: str, constraint_name: str) -> None:
        super().__init__("driver")
        self.sqlstate = sqlstate
        self.__cause__ = _Cause(constraint_name)


def _refusal(sqlstate: str, constraint: str) -> IntegrityError:
    return IntegrityError(
        "INSERT INTO dining_area (name) VALUES ($1)", {}, _DriverError(sqlstate, constraint)
    )


@pytest.fixture
async def refusal_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    cases = {
        "unique": ("23505", "uq_dining_area_restaurant_name"),
        "exclusion": ("23P01", "ex_tax_rate_no_overlap"),
        "check": ("23514", "ck_restaurant_table_seats_positive"),
        "missing": ("23503", "fk_order_table_table_tenant"),
        "other": ("23000", "something_else"),
    }
    for name, (sqlstate, constraint) in cases.items():

        async def _raise(sqlstate: str = sqlstate, constraint: str = constraint) -> None:
            raise _refusal(sqlstate, constraint)

        app.add_api_route(f"/api/v1/_refusal/{name}", _raise, methods=["GET"])

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


class TestADatabaseRefusalIsNotAnInternalError:
    @pytest.mark.parametrize("case", ["unique", "exclusion"])
    async def test_a_duplicate_is_a_conflict_that_names_no_constraint(
        self, refusal_client: AsyncClient, case: str
    ) -> None:
        response = await refusal_client.get(f"/api/v1/_refusal/{case}")

        assert response.status_code == 409
        assert response.json()["code"] == "conflict.duplicate"
        # The constraint name belongs in the log; SQL belongs nowhere.
        assert "uq_" not in response.text and "ex_" not in response.text
        assert "INSERT" not in response.text

    async def test_a_failed_check_is_refused_in_words(self, refusal_client: AsyncClient) -> None:
        response = await refusal_client.get("/api/v1/_refusal/check")

        assert response.status_code == 422
        assert response.json()["code"] == "request.rejected"
        assert "ck_" not in response.text

    async def test_a_reference_that_vanished_is_a_conflict(
        self, refusal_client: AsyncClient
    ) -> None:
        response = await refusal_client.get("/api/v1/_refusal/missing")

        assert response.status_code == 409
        assert response.json()["code"] == "conflict.missing"

    async def test_any_other_integrity_error_is_still_an_internal_error(
        self, refusal_client: AsyncClient
    ) -> None:
        """Only the refusals with a known meaning are mapped. Anything else stays a 500 with a
        reference, so an unexpected failure is investigated rather than dressed up."""
        response = await refusal_client.get("/api/v1/_refusal/other")

        assert response.status_code == 500
        assert response.json()["code"] == "internal.error"


# --------------------------------------------------------------------------- the real race


async def _restaurant_and_owner(session: AsyncSession) -> tuple[TenantScope, Actor]:
    organization = Organization(name="Race", slug="race")
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name="Race",
        code="RACE",
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
    )
    session.add(restaurant)
    await session.flush()
    employee = Employee(
        organization_id=organization.id,
        employee_code="RACE-1",
        full_name="Owner",
        joined_on=date(2026, 1, 1),
        employment_type="full_time",
        is_active=True,
    )
    session.add(employee)
    await session.flush()
    scope = TenantScope(organization_id=organization.id, restaurant_id=restaurant.id)
    actor = Actor(
        employee_id=employee.id,
        organization_id=organization.id,
        restaurant_id=restaurant.id,
        full_name="Owner",
        permissions=frozenset(),
        rank=0,
    )
    return scope, actor


async def test_two_admins_adding_the_same_area_at_once_meet_the_constraint_not_a_crash(
    fresh_database: str,
) -> None:
    """The race itself, on real transactions (G-2: the shared test transaction never contends).

    Both requests pass the name check — forced here, because a real race wins it only some of the
    time — and the unique constraint refuses the second. What that refusal reaches is an
    `IntegrityError` with SQLSTATE 23505, which the handler above turns into a 409. Before B3 it
    reached the catch-all as a 500.
    """
    engine = create_async_engine(fresh_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as setup:
            _, actor = await _restaurant_and_owner(setup)
            await setup.commit()

        async def add() -> str:
            async with factory() as session:
                try:
                    await SetupService(session).create_dining_area(
                        actor, DiningAreaCreateRequest(name="Terrace")
                    )
                    await session.commit()
                except IntegrityError as error:
                    return f"refused:{getattr(error.orig, 'sqlstate', None)}"
                return "created"

        with patch.object(DiningAreaRepository, "name_exists", new=AsyncMock(return_value=False)):
            results = await asyncio.gather(add(), add())

        assert sorted(results) == ["created", "refused:23505"]
    finally:
        await engine.dispose()


async def test_deactivating_an_area_and_adding_a_table_to_it_cannot_both_win(
    fresh_database: str,
) -> None:
    """An owner on a laptop deactivates Terrace while a manager on a tablet adds T9 to it — which is
    what a restaurant opening looks like.

      without a lock  the deactivation counts zero active tables, the insert sees the area still
                      active, and both commit: an active table in an inactive area, missing from
                      every area-filtered list and seated by M07 anyway.
      with the lock   whichever reads the area first holds it; the other waits, then sees the
                      committed state and is refused in words.

    The window is held open deliberately — a real race lands in it only sometimes — by pausing the
    deactivation right after its count. **To re-verify this test is not decorative:** remove the
    lock from `update_dining_area` and `_require_area`. It must go red.
    """
    engine = create_async_engine(fresh_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as setup:
            _, actor = await _restaurant_and_owner(setup)
            area = await SetupService(setup).create_dining_area(
                actor, DiningAreaCreateRequest(name="Terrace")
            )
            await setup.commit()
            area_id = area.id

        counted = asyncio.Event()
        original_count = RestaurantTableRepository.count_in_area

        async def count_then_pause(
            self: RestaurantTableRepository, dining_area_id: uuid.UUID
        ) -> int:
            total = await original_count(self, dining_area_id)
            counted.set()
            await asyncio.sleep(0.5)
            return total

        async def deactivate() -> str:
            async with factory() as session:
                try:
                    await SetupService(session).update_dining_area(
                        actor, area_id, DiningAreaUpdateRequest(is_active=False)
                    )
                    await session.commit()
                except ConflictError:
                    return "refused"
                return "deactivated"

        async def add_table() -> str:
            await counted.wait()
            async with factory() as session:
                try:
                    await SetupService(session).create_table(
                        actor, TableCreateRequest(dining_area_id=area_id, code="T9", seats=4)
                    )
                    await session.commit()
                except ConflictError:
                    return "refused"
                return "added"

        with patch.object(RestaurantTableRepository, "count_in_area", new=count_then_pause):
            outcomes = await asyncio.gather(deactivate(), add_table())

        async with factory() as check:
            stored = await check.get(DiningArea, area_id)
            active_tables = await check.scalar(
                select(func.count())
                .select_from(RestaurantTable)
                .where(
                    RestaurantTable.dining_area_id == area_id,
                    RestaurantTable.is_active.is_(True),
                )
            )
        assert stored is not None
        assert stored.is_active or not active_tables, (
            f"{outcomes}: an active table sits in a deactivated area"
        )
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- reordering


class TestReorderingIsOneRequest:
    async def test_the_floor_plan_order_is_saved_whole(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        hall = await _area(api_client, token, "AC Hall")
        terrace = await _area(api_client, token, "Terrace")
        roof = await _area(api_client, token, "Rooftop")

        response = await api_client.post(
            f"{SETUP}/dining-areas/reorder",
            json={"area_ids": [roof["id"], hall["id"], terrace["id"]]},
            headers=_auth(token),
        )

        assert response.status_code == 200, response.text
        listed = (await api_client.get(f"{SETUP}/dining-areas", headers=_auth(token))).json()
        assert [(area["name"], area["seq"]) for area in listed["items"]] == [
            ("Rooftop", 0),
            ("AC Hall", 1),
            ("Terrace", 2),
        ]

    @pytest.mark.parametrize("shape", ["leaves_one_out", "names_one_twice"])
    async def test_a_list_that_is_not_the_whole_floor_is_refused_and_changes_nothing(
        self, db_session: AsyncSession, api_client: AsyncClient, shape: str
    ) -> None:
        """A partial list would leave two areas sharing a position — the very state a half-failed
        two-request swap used to produce."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        hall = await _area(api_client, token, "AC Hall")
        terrace = await _area(api_client, token, "Terrace")
        ids = [terrace["id"]] if shape == "leaves_one_out" else [terrace["id"], terrace["id"]]

        response = await api_client.post(
            f"{SETUP}/dining-areas/reorder", json={"area_ids": ids}, headers=_auth(token)
        )

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "dining_area.reorder_incomplete"
        listed = (await api_client.get(f"{SETUP}/dining-areas", headers=_auth(token))).json()
        assert [area["id"] for area in listed["items"]] == [hall["id"], terrace["id"]]

    async def test_menu_sections_are_reordered_the_same_way(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        ids = []
        for code, name in (("STARTERS", "Starters"), ("MAINS", "Mains"), ("BREADS", "Breads")):
            created = await api_client.post(
                f"{MENU}/categories", json={"code": code, "name": name}, headers=_auth(token)
            )
            assert created.status_code == 201, created.text
            ids.append(created.json()["id"])

        response = await api_client.post(
            f"{MENU}/categories/reorder",
            json={"category_ids": [ids[2], ids[0], ids[1]]},
            headers=_auth(token),
        )

        assert response.status_code == 200, response.text
        listed = (await api_client.get(f"{MENU}/categories", headers=_auth(token))).json()
        assert [section["name"] for section in listed["items"]] == ["Breads", "Starters", "Mains"]
