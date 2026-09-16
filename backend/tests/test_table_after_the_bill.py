"""A table's life after the bill.

Found in the M07 manual pass on 2026-09-13 (backlog: "After a bill, a table cannot be cleared from
the floor, and tapping it opens an empty order"): T2 and T4 stayed Occupied after their bills
settled.
Settlement correctly sends a table to `cleaning`, but nothing on the floor ever cleared it, and
`set_table_status` sits behind `restaurant.configure`, which neither a waiter nor a manager holds.

The owner's decisions, 2026-09-13:

1. **Mark ready** — one tap on the floor frees a table being cleared, for anyone who seats tables.
2. **A cleaning time**, five minutes unless the restaurant says otherwise, after which a table
   being cleared counts as free without anybody tapping. Derived when the floor is read; no
   background job.
3. **Busy hours skip cleaning** — set as windows in the restaurant's settings, or switched on from
   the floor by a manager for an unexpected rush. A switch left on turns itself off at the next
   business day, so a forgotten toggle cannot skip cleaning for ever.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_day import business_date_of
from app.models.setup import RestaurantTable
from app.models.tenancy import Restaurant
from tests.test_orders_endpoints import Menu, _added, _open, _setup
from tests.test_settlement import _registered, _settle
from tests.test_setup_endpoints import World, _auth, _token

STAFF = "/api/v1/staff"
FLOOR = f"{STAFF}/floor"
RESTAURANT = f"{STAFF}/restaurant"


async def _settled_table(
    db_session: AsyncSession, api_client: AsyncClient, **settings: Any
) -> tuple[World, Menu, str]:
    """A restaurant whose bill on `menu.table` has just been settled."""
    world, menu, token = await _setup(db_session, api_client)
    await _registered(db_session, world)
    if settings:
        await _set_tables(db_session, world, **settings)
    order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
    assert (await _settle(api_client, token, order)).status_code == 201
    return world, menu, token


async def _set_tables(db_session: AsyncSession, world: World, **tables: Any) -> None:
    restaurant = await db_session.get(Restaurant, world.restaurant.id)
    assert restaurant is not None
    restaurant.settings = {**restaurant.settings, "tables": tables}
    await db_session.commit()


async def _floor_table(api_client: AsyncClient, token: str, menu: Menu) -> dict[str, Any]:
    response = await api_client.get(FLOOR, headers=_auth(token))
    assert response.status_code == 200, response.text
    cells = [table for area in response.json()["areas"] for table in area["tables"]]
    return next(table for table in cells if table["id"] == str(menu.table))


async def _cleaning_for(db_session: AsyncSession, menu: Menu, minutes: int) -> None:
    await db_session.execute(
        update(RestaurantTable)
        .where(RestaurantTable.id == menu.table)
        .values(cleaning_since=datetime.now(UTC) - timedelta(minutes=minutes))
    )
    await db_session.commit()


class TestMarkReady:
    async def test_a_waiter_frees_a_table_being_cleared_in_one_tap(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _settled_table(db_session, api_client)
        assert (await _floor_table(api_client, token, menu))["status"] == "cleaning"

        response = await api_client.post(f"{FLOOR}/tables/{menu.table}/ready", headers=_auth(token))

        assert response.status_code == 200, response.text
        assert (await _floor_table(api_client, token, menu))["status"] == "free"

    async def test_it_refuses_a_table_with_an_order_on_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        await _open(api_client, token, menu)

        response = await api_client.post(f"{FLOOR}/tables/{menu.table}/ready", headers=_auth(token))

        assert response.status_code == 409
        assert response.json()["code"] == "table.order_open"


class TestTheCleaningTime:
    async def test_a_table_being_cleared_says_when_it_will_be_ready(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _settled_table(db_session, api_client)

        cell = await _floor_table(api_client, token, menu)

        assert cell["status"] == "cleaning"
        ready_at = datetime.fromisoformat(cell["ready_at"])
        # Five minutes by default, counted from settlement.
        assert timedelta(minutes=4) < ready_at - datetime.now(UTC) <= timedelta(minutes=5)

    async def test_after_the_cleaning_time_it_counts_as_free_and_can_be_seated(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _settled_table(db_session, api_client)
        await _cleaning_for(db_session, menu, minutes=6)

        cell = await _floor_table(api_client, token, menu)
        assert cell["status"] == "free"
        assert cell["ready_at"] is None
        # And seating it works, which is what "free" has to mean.
        await _open(api_client, token, menu)

    async def test_with_no_cleaning_time_only_a_person_clears_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _settled_table(db_session, api_client, cleaning_minutes=None)
        await _cleaning_for(db_session, menu, minutes=120)

        cell = await _floor_table(api_client, token, menu)

        assert cell["status"] == "cleaning"
        assert cell["ready_at"] is None


def _window_around_now(timezone: str) -> dict[str, str]:
    now = datetime.now(ZoneInfo(timezone))
    # An hour either side; a window may cross midnight, so this holds at any time of day.
    return {
        "starts": (now - timedelta(hours=1)).strftime("%H:%M"),
        "ends": (now + timedelta(hours=1)).strftime("%H:%M"),
    }


class TestTheSettings:
    """The owner sets the cleaning time and the busy windows where the rest of the restaurant is
    configured, and gets told in words when a value will not do (B1)."""

    async def test_the_owner_saves_a_cleaning_time_and_busy_windows(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _setup(db_session, api_client)
        owner = await _token(api_client, "owner")
        tables = {
            "cleaning_minutes": 8,
            "busy_windows": [
                {"starts": "12:30", "ends": "15:00"},
                # Across midnight, for a place that is busiest after 11 pm.
                {"starts": "22:00", "ends": "01:00"},
            ],
        }

        response = await api_client.patch(RESTAURANT, json={"tables": tables}, headers=_auth(owner))

        assert response.status_code == 200, response.text
        saved = (await api_client.get(RESTAURANT, headers=_auth(owner))).json()["tables"]
        assert saved["cleaning_minutes"] == 8
        assert [(w["starts"], w["ends"]) for w in saved["busy_windows"]] == [
            ("12:30:00", "15:00:00"),
            ("22:00:00", "01:00:00"),
        ]

    async def test_a_restaurant_that_never_set_it_cleans_for_five_minutes(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _setup(db_session, api_client)
        owner = await _token(api_client, "owner")

        saved = (await api_client.get(RESTAURANT, headers=_auth(owner))).json()["tables"]

        assert saved == {"cleaning_minutes": 5, "busy_windows": []}

    async def test_an_unreasonable_cleaning_time_is_explained(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _setup(db_session, api_client)
        owner = await _token(api_client, "owner")

        response = await api_client.patch(
            RESTAURANT, json={"tables": {"cleaning_minutes": 0}}, headers=_auth(owner)
        )

        assert response.status_code == 422
        (problem,) = response.json()["details"]["fields"]
        assert problem["field"] == "tables.cleaning_minutes"
        assert problem["code"] == "field.out_of_range"


class TestBusyHours:
    async def test_inside_a_busy_window_a_settled_table_is_free_at_once(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        window = _window_around_now(world.restaurant.timezone)
        await _registered(db_session, world)
        await _set_tables(db_session, world, cleaning_minutes=5, busy_windows=[window])
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        assert (await _settle(api_client, token, order)).status_code == 201

        table = await db_session.scalar(
            select(RestaurantTable.status).where(RestaurantTable.id == menu.table)
        )
        assert table == "free"

    async def test_a_manager_switches_busy_mode_on_from_the_floor(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, waiter = await _setup(db_session, api_client)
        await _registered(db_session, world)
        manager = await _token(api_client, "manager")

        response = await api_client.post(f"{FLOOR}/busy", json={"on": True}, headers=_auth(manager))

        assert response.status_code == 200, response.text
        floor = await api_client.get(FLOOR, headers=_auth(waiter))
        assert floor.json()["busy"] is True
        order = await _added(api_client, waiter, await _open(api_client, waiter, menu), menu.dal)
        assert (await _settle(api_client, waiter, order)).status_code == 201
        assert (await _floor_table(api_client, waiter, menu))["status"] == "free"

    async def test_a_waiter_cannot_switch_busy_mode(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, waiter = await _setup(db_session, api_client)

        response = await api_client.post(f"{FLOOR}/busy", json={"on": True}, headers=_auth(waiter))

        assert response.status_code == 403

    async def test_busy_mode_left_on_switches_itself_off_the_next_business_day(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, _, waiter = await _setup(db_session, api_client)
        restaurant = world.restaurant
        today = business_date_of(
            datetime.now(UTC), restaurant.timezone, restaurant.business_day_start
        )
        await _set_tables(db_session, world, busy_mode_on=str(today - timedelta(days=1)))

        floor = await api_client.get(FLOOR, headers=_auth(waiter))

        assert floor.json()["busy"] is False
