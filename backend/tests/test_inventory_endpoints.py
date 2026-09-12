"""The stock ledger over HTTP. Chunk E of M05.

`test_generic_suites.py` already proves every route here is tenant-isolated and declares a
permission — that is a loop over the route table, and it caught a real leak in this module the
moment these routes registered. What it cannot express is *which* role should hold *which* power,
so that is what this file is for.

The grants come from `seed/organization.yaml`'s P1 design, and the one worth reading is the chef:
`stock.produce` but not `stock.receive`. A kitchen turns ingredients into gravy; it does not sign
for the sack at the door.
"""

from __future__ import annotations

from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_setup_endpoints import _auth, _token, _world

STAFF = "/api/v1/staff"


async def _ingredient(client: AsyncClient, token: str, code: str = "PANEER") -> str:
    response = await client.post(
        f"{STAFF}/stock-items",
        json={
            "kind": "ingredient",
            "code": code,
            "name": code.title(),
            "base_unit": "g",
            "category": "dairy",
            "storage_type": "chilled",
            "current_unit_cost": "0.360000",
            "ingredient": {
                "purchase_unit": "kg",
                "purchase_to_base": "1000",
                "yield_factor": "0.98",
                "shelf_life_days": 4,
            },
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    created: str = response.json()["id"]
    return created


class TestTheJourney:
    async def test_receive_then_see_it_on_hand(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)

        receipt = await api_client.post(
            f"{STAFF}/stock/receipts",
            json={"stock_item_id": item_id, "quantity": "5000", "unit_cost": "0.36"},
            headers=_auth(token),
        )
        assert receipt.status_code == 201, receipt.text

        on_hand = await api_client.get(f"{STAFF}/stock/on-hand", headers=_auth(token))
        body = on_hand.json()
        assert body["items"][0]["quantity"] == "5000.0000"
        assert body["items"][0]["is_negative"] is False
        assert body["negative_count"] == 0

    async def test_a_negative_position_is_flagged_for_the_screen(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The screen should not have to know that `quantity < 0` is meaningful."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)

        await api_client.post(
            f"{STAFF}/stock/receipts",
            json={"stock_item_id": item_id, "quantity": "100", "unit_cost": "0.36"},
            headers=_auth(token),
        )
        consumed = await api_client.post(
            f"{STAFF}/stock/consumption",
            json={"stock_item_id": item_id, "quantity": "400"},
            headers=_auth(token),
        )
        assert consumed.status_code == 201, consumed.text
        assert consumed.json()["shortfall"] == "300.0000"

        body = (await api_client.get(f"{STAFF}/stock/on-hand", headers=_auth(token))).json()
        assert body["items"][0]["is_negative"] is True
        assert body["negative_count"] == 1

    async def test_the_full_count_cycle(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        await api_client.post(
            f"{STAFF}/stock/receipts",
            json={"stock_item_id": item_id, "quantity": "1000", "unit_cost": "0.36"},
            headers=_auth(token),
        )

        opened = await api_client.post(
            f"{STAFF}/stock/counts",
            json={"stock_item_ids": [item_id], "scope": "full"},
            headers=_auth(token),
        )
        assert opened.status_code == 201, opened.text
        count_id = opened.json()["id"]
        assert opened.json()["status"] == "draft"

        recorded = await api_client.patch(
            f"{STAFF}/stock/counts/{count_id}",
            json={"lines": [{"stock_item_id": item_id, "counted_quantity": "940"}]},
            headers=_auth(token),
        )
        assert recorded.status_code == 200, recorded.text
        assert recorded.json()["lines"][0]["variance_value"] == "-21.60"

        submitted = await api_client.post(
            f"{STAFF}/stock/counts/{count_id}/submit", headers=_auth(token)
        )
        assert submitted.json()["status"] == "submitted"

        # The owner opened this count, so the owner cannot approve it. Separation of duties is not
        # waived for the person at the top — that is the whole point of it.
        refused = await api_client.post(
            f"{STAFF}/stock/counts/{count_id}/approve", headers=_auth(token)
        )
        assert refused.status_code == 403, refused.text
        assert refused.json()["code"] == "self_approval"

    async def test_an_unknown_item_is_a_404_not_an_empty_list(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Suite 1 found this as a real leak: the route answered 200 for another tenant's id."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.get(
            f"{STAFF}/stock/items/01a09600-0000-7000-8000-000000000000/movements",
            headers=_auth(token),
        )

        assert response.status_code == 404
        assert response.json()["code"] == "stock_item_not_found"


class TestWhoMayDoWhat:
    async def test_a_chef_may_produce_but_not_receive(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The grant that carries the most meaning. A kitchen makes gravy; it does not sign for
        the delivery, so a cook cannot quietly book in stock that never arrived."""
        await _world(db_session, "owner", "chef")
        owner_token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, owner_token)
        chef_token = await _token(api_client, "chef")

        refused = await api_client.post(
            f"{STAFF}/stock/receipts",
            json={"stock_item_id": item_id, "quantity": "10", "unit_cost": "1"},
            headers=_auth(chef_token),
        )

        assert refused.status_code == 403

    async def test_a_chef_may_read_the_position(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "chef")
        chef_token = await _token(api_client, "chef")

        response = await api_client.get(f"{STAFF}/stock/on-hand", headers=_auth(chef_token))

        assert response.status_code == 200

    async def test_kitchen_staff_may_look_and_not_touch(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "kitchen_staff")
        owner_token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, owner_token)
        staff_token = await _token(api_client, "kitchen_staff")

        assert (
            await api_client.get(f"{STAFF}/stock/on-hand", headers=_auth(staff_token))
        ).status_code == 200
        assert (
            await api_client.post(
                f"{STAFF}/stock/adjustments",
                json={"stock_item_id": item_id, "quantity_delta": "-5", "reason": "shrinkage"},
                headers=_auth(staff_token),
            )
        ).status_code == 403

    async def test_a_waiter_reaches_none_of_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Default-deny: the storeroom is not a waiter's screen."""
        await _world(db_session, "owner", "waiter")
        waiter_token = await _token(api_client, "waiter")

        assert (
            await api_client.get(f"{STAFF}/stock/on-hand", headers=_auth(waiter_token))
        ).status_code == 403


class TestTheContractRefusesNonsense:
    async def test_a_receipt_of_zero_is_rejected_by_the_schema(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)

        response = await api_client.post(
            f"{STAFF}/stock/receipts",
            json={"stock_item_id": item_id, "quantity": "0", "unit_cost": "1"},
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_an_adjustment_without_a_reason_is_rejected(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)

        response = await api_client.post(
            f"{STAFF}/stock/adjustments",
            json={"stock_item_id": item_id, "quantity_delta": "-5", "reason": ""},
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_a_misspelled_field_is_refused_rather_than_ignored(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)

        response = await api_client.post(
            f"{STAFF}/stock/receipts",
            json={
                "stock_item_id": item_id,
                "quantity": "10",
                "unit_cost": "1",
                "expiry": "2026-10-01",
            },
            headers=_auth(token),
        )

        # `expiry` rather than `expiry_date`. Accepting it silently would mean a batch with no
        # expiry, which FEFO then sorts last and lets rot.
        assert response.status_code == 422

    async def test_quantities_come_back_as_strings(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A float round-trip through JavaScript is how 0.05 g of saffron becomes 0.0500000000003
        and a ledger stops adding up."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)
        await api_client.post(
            f"{STAFF}/stock/receipts",
            json={"stock_item_id": item_id, "quantity": "0.05", "unit_cost": "1"},
            headers=_auth(token),
        )

        body = (await api_client.get(f"{STAFF}/stock/on-hand", headers=_auth(token))).json()

        assert isinstance(body["items"][0]["quantity"], str)
        assert Decimal(body["items"][0]["quantity"]) == Decimal("0.05")
