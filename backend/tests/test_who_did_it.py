"""The people behind a delivery and a till, by name (owner defect sheet rows 4, 5, 22 and 26).

Decisions D13 and D16 (backlog-issues B12): who closed a till and who adjusted it are shown by
name, employee code and role, beside the original figure; the owner may adjust a till they closed,
and it is marked. Who received a delivery is shown the same way. And an expiring batch says what it
is."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_cash import CASH, _adjust, _close, _open_till
from tests.test_procurement_endpoints import STAFF, _ingredient, _keyed, _supplier
from tests.test_setup_endpoints import _auth, _token, _world

OWNER = {"full_name": "Owner Person", "employee_code": "E000", "roles": ["Owner"]}


class TestATill:
    async def test_the_owner_may_adjust_a_till_they_closed_and_it_is_marked(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "manager")
        owner = await _token(api_client, "owner")
        till = await _open_till(api_client, owner)
        assert (await _close(api_client, owner, till, [("500.00", 3)])).status_code == 200

        response = await _adjust(api_client, owner, till, "400.00")

        assert response.status_code == 201, response.text
        movement = response.json()["movements"][-1]
        assert movement["recorded_by_person"] == OWNER
        assert movement["by_closer"] is True

    async def test_the_list_names_who_closed_and_who_adjusted(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "manager")
        owner = await _token(api_client, "owner")
        manager = await _token(api_client, "manager")
        till = await _open_till(api_client, manager)
        assert (await _close(api_client, manager, till, [("500.00", 3)])).status_code == 200
        assert (await _adjust(api_client, owner, till, "400.00")).status_code == 201

        listed = (await api_client.get(CASH, headers=_auth(owner))).json()["items"][0]

        assert listed["closed_by_person"] == {
            "full_name": "Manager Person",
            "employee_code": "E001",
            "roles": ["Manager"],
        }
        assert listed["adjusted_by"] == [OWNER | {"by_closer": False}]


class TestADelivery:
    async def test_the_receipt_names_who_received_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item = await _ingredient(api_client, token)
        supplier = await _supplier(api_client, token)

        posted = await api_client.post(
            f"{STAFF}/goods-receipts",
            json={
                "supplier_id": supplier,
                "lines": [
                    {
                        "stock_item_id": item,
                        "quantity_invoiced": "1000.0000",
                        "quantity_received": "1000.0000",
                        "unit_price": "0.360000",
                    }
                ],
            },
            headers=_keyed(token),
        )
        listed = await api_client.get(f"{STAFF}/goods-receipts", headers=_auth(token))

        assert posted.status_code == 201, posted.text
        assert posted.json()["receipt"]["received_by_person"] == OWNER
        assert listed.json()["receipts"][0]["received_by_person"] == OWNER


class TestExpiringStock:
    async def test_an_expiring_batch_says_what_it_is(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item = await _ingredient(api_client, token)
        soon = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
        received = await api_client.post(
            f"{STAFF}/stock/receipts",
            json={
                "stock_item_id": item,
                "quantity": "500",
                "unit_cost": "0.36",
                "expiry_date": soon,
            },
            headers=_auth(token),
        )
        assert received.status_code == 201, received.text

        batch = (await api_client.get(f"{STAFF}/stock/expiring", headers=_auth(token))).json()[
            "batches"
        ][0]

        assert (batch["stock_item_id"], batch["code"], batch["name"], batch["base_unit"]) == (
            item,
            "PANEER",
            "Paneer",
            "g",
        )
