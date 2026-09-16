"""A delivery is typed in the unit the invoice uses (backlog-issues B12e, owner defect sheet L127).

The receiving form asked for a "Cost per unit" while the ledger holds grams, so ₹28 a kilo was
stored as ₹28 a gram and a plate of cabbage came to more than a car. Two halves to the fix, and
both are tested here rather than in the pure helpers: the server does the conversion, and a price
far from what the item has been costing is put back to the person instead of being taken quietly.
"""

from __future__ import annotations

from decimal import Decimal

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_procurement_endpoints import STAFF, _ingredient
from tests.test_setup_endpoints import _auth, _token, _world


async def _receive(client: AsyncClient, token: str, **body: object) -> Response:
    return await client.post(f"{STAFF}/stock/receipts", json=body, headers=_auth(token))


class TestADeliveryIsTypedInThePurchaseUnit:
    async def test_kilos_are_stored_as_grams_and_the_price_comes_down_with_them(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item = await _ingredient(api_client, token, "PANEER")

        # 12 kg at ₹400 a kilo, on an item that holds grams and has been costing ₹0.36 a gram.
        response = await _receive(
            api_client,
            token,
            stock_item_id=item,
            quantity="12",
            unit_cost="400",
            per_purchase_unit=True,
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert Decimal(body["quantity_received"]) == Decimal("12000.0000")
        assert Decimal(body["unit_cost"]) == Decimal("0.400000")

    async def test_base_units_are_untouched_when_the_form_does_not_convert(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The old shape still means what it meant: no silent conversion for existing callers."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item = await _ingredient(api_client, token, "PANEER")

        response = await _receive(
            api_client,
            token,
            stock_item_id=item,
            quantity="12000",
            unit_cost="0.400000",
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert Decimal(body["quantity_received"]) == Decimal("12000.0000")
        assert Decimal(body["unit_cost"]) == Decimal("0.400000")


class TestAPriceFarFromTheItemsOwnCost:
    async def test_is_put_back_to_the_person_in_words(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """₹28 a kilo against an item costing ₹360 a kilo is the unit mix-up, not a bargain."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item = await _ingredient(api_client, token, "PANEER")

        response = await _receive(
            api_client,
            token,
            stock_item_id=item,
            quantity="12",
            unit_cost="28",
            per_purchase_unit=True,
        )

        assert response.status_code == 422, response.text
        message = response.json()["message"]
        assert "per kg" in message
        assert "Check the price and the unit." in message

    async def test_is_accepted_once_the_person_confirms_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A price really can move that far, so it is a question, not a refusal."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item = await _ingredient(api_client, token, "PANEER")

        response = await _receive(
            api_client,
            token,
            stock_item_id=item,
            quantity="12",
            unit_cost="28",
            per_purchase_unit=True,
            confirm_unusual_price=True,
        )

        assert response.status_code == 201, response.text
        assert Decimal(response.json()["unit_cost"]) == Decimal("0.028000")
