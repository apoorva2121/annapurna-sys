"""The table map a waiter works from: who is sitting where, and for how much.

Behind `order.view` rather than `restaurant.configure`, which guards the setup table list — a waiter
holds the first and not the second, and before this endpoint existed the waiter's first screen had
nothing it was allowed to load.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.queries import count_queries
from tests.test_orders_endpoints import _added, _open, _setup, _stepped
from tests.test_setup_endpoints import _auth, _token, _world

FLOOR = "/api/v1/staff/floor"


class TestTheFloor:
    async def test_a_waiter_sees_every_table_and_the_order_sitting_at_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        response = await api_client.get(FLOOR, headers=_auth(token))

        assert response.status_code == 200, response.text
        (area,) = response.json()["areas"]
        tables = {table["code"]: table for table in area["tables"]}
        assert set(tables) == {"T6", "T7"}
        assert tables["T6"]["status"] == "occupied"
        (sitting,) = tables["T6"]["orders"]
        assert (sitting["id"], sitting["grand_total"], sitting["version"]) == (
            order["id"],
            "493.50",
            order["version"],
        )
        assert tables["T7"]["orders"] == []

    async def test_a_cancelled_order_leaves_the_map(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)
        await _stepped(api_client, token, order, "cancel", reason="opened by mistake")

        response = await api_client.get(FLOOR, headers=_auth(token))

        tables = {table["code"]: table for table in response.json()["areas"][0]["tables"]}
        assert tables["T6"]["orders"] == []
        assert tables["T6"]["status"] == "free"

    async def test_the_floor_costs_the_same_however_busy_the_evening(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The map is the screen a waiter reopens every few minutes, all evening. Its statements
        must not grow with the number of tables sat or orders open — the shape an N+1 cannot
        satisfy."""
        _, menu, token = await _setup(db_session, api_client)
        engine = db_session.get_bind().engine
        with count_queries(engine) as quiet:
            assert (await api_client.get(FLOOR, headers=_auth(token))).status_code == 200

        await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        second = await _open(api_client, token, menu, table_ids=[str(menu.second_table)])
        await _added(api_client, token, second, menu.paneer, modifiers=(menu.mild,))
        with count_queries(engine) as busy:
            assert (await api_client.get(FLOOR, headers=_auth(token))).status_code == 200

        assert busy.count == quiet.count

    async def test_the_kitchen_does_not_read_the_bills(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "chef")
        token = await _token(api_client, "chef")

        response = await api_client.get(FLOOR, headers=_auth(token))

        assert response.status_code == 403
