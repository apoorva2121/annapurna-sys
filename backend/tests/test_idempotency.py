"""Idempotency over HTTP: ADR 0010, M07 spec decision 8, acceptance criterion 19.

Receiving is the first route behind it because M06's own adversarial review found the hole: a market
purchase has no invoice number, so the unique index that stops a double-booked *invoice* says
nothing, and two taps on "Book it in" over restaurant wifi booked the same vegetables twice.

Two kinds of test, for the reason `conftest.api` gives. The sequential ones run on the ordinary
fixture. The one that matters most — two requests racing with one key — needs real transactions,
because inside the shared test transaction the second insert never has to wait, and the test would
pass against code with no mechanism at all.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import get_session
from app.main import create_app
from app.models.procurement import GoodsReceipt
from tests.test_procurement_endpoints import STAFF, _ingredient, _order, _supplier
from tests.test_setup_endpoints import _auth, _token, _world

_UNKNOWN_SUPPLIER = "00000000-0000-0000-0000-0000000000ff"
_REPLAYED = "Idempotent-Replayed"


def _delivery(supplier_id: str, item_id: str, *, received: str = "1000.0000") -> dict[str, Any]:
    """A market purchase: no invoice number, so nothing but the key tells a retry from a second
    delivery of the same thing."""
    return {
        "supplier_id": supplier_id,
        "lines": [
            {
                "stock_item_id": item_id,
                "quantity_invoiced": "1000.0000",
                "quantity_received": received,
                "unit_price": "0.042000",
            }
        ],
    }


def _keyed(token: str, key: str) -> dict[str, str]:
    return _auth(token) | {"Idempotency-Key": key}


async def _receipts(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(GoodsReceipt)) or 0)


async def _stocked(
    session: AsyncSession, client: AsyncClient, slug: str = "spice-garden"
) -> tuple[str, str, str]:
    """An owner's token, a stock item and a supplier, in a restaurant of its own."""
    await _world(session, "owner", slug=slug)
    token = await _token(client, "owner", slug=slug)
    return token, await _ingredient(client, token), await _supplier(client, token)


class TestADeliveryTappedTwice:
    async def test_a_delivery_posted_without_a_key_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        token, item, supplier = await _stocked(db_session, api_client)

        response = await api_client.post(
            f"{STAFF}/goods-receipts", json=_delivery(supplier, item), headers=_auth(token)
        )

        assert response.status_code == 422
        assert response.json()["code"] == "idempotency.key_required"
        assert await _receipts(db_session) == 0

    async def test_a_second_tap_replays_the_first_receipt_and_books_nothing(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        token, item, supplier = await _stocked(db_session, api_client)
        key = str(uuid.uuid4())

        first = await api_client.post(
            f"{STAFF}/goods-receipts", json=_delivery(supplier, item), headers=_keyed(token, key)
        )
        again = await api_client.post(
            f"{STAFF}/goods-receipts", json=_delivery(supplier, item), headers=_keyed(token, key)
        )

        assert (first.status_code, again.status_code) == (201, 201), again.text
        assert again.json() == first.json()
        assert again.headers.get(_REPLAYED) == "true"
        assert _REPLAYED not in first.headers
        assert await _receipts(db_session) == 1

    async def test_the_same_key_on_a_different_delivery_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A client bug, not a retry. Replaying the first receipt would tell the store manager the
        second delivery was booked when it was not."""
        token, item, supplier = await _stocked(db_session, api_client)
        key = str(uuid.uuid4())
        first = await api_client.post(
            f"{STAFF}/goods-receipts", json=_delivery(supplier, item), headers=_keyed(token, key)
        )
        assert first.status_code == 201, first.text

        different = await api_client.post(
            f"{STAFF}/goods-receipts",
            json=_delivery(supplier, item, received="900.0000"),
            headers=_keyed(token, key),
        )

        assert different.status_code == 409
        assert different.json()["code"] == "idempotency.key_reused"
        assert await _receipts(db_session) == 1

    async def test_a_key_too_short_to_be_unguessable_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        token, item, supplier = await _stocked(db_session, api_client)

        response = await api_client.post(
            f"{STAFF}/goods-receipts", json=_delivery(supplier, item), headers=_keyed(token, "1")
        )

        assert response.status_code == 422
        assert response.json()["code"] == "idempotency.key_invalid"

    async def test_a_failed_attempt_leaves_its_key_free_for_the_retry(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """An error is never stored. The claim rolls back with the failed request, so the honest
        retry runs rather than replaying a failure."""
        token, item, supplier = await _stocked(db_session, api_client)
        key = str(uuid.uuid4())

        failed = await api_client.post(
            f"{STAFF}/goods-receipts",
            json=_delivery(_UNKNOWN_SUPPLIER, item),
            headers=_keyed(token, key),
        )
        retried = await api_client.post(
            f"{STAFF}/goods-receipts", json=_delivery(supplier, item), headers=_keyed(token, key)
        )

        assert failed.status_code == 404, failed.text
        assert retried.status_code == 201, retried.text
        assert _REPLAYED not in retried.headers
        assert await _receipts(db_session) == 1

    async def test_a_key_belongs_to_one_restaurant(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        key = str(uuid.uuid4())
        token, item, supplier = await _stocked(db_session, api_client)
        other_token, other_item, other_supplier = await _stocked(
            db_session, api_client, slug="other-kitchen"
        )

        mine = await api_client.post(
            f"{STAFF}/goods-receipts", json=_delivery(supplier, item), headers=_keyed(token, key)
        )
        theirs = await api_client.post(
            f"{STAFF}/goods-receipts",
            json=_delivery(other_supplier, other_item),
            headers=_keyed(other_token, key),
        )

        assert (mine.status_code, theirs.status_code) == (201, 201), theirs.text
        assert _REPLAYED not in theirs.headers
        assert await _receipts(db_session) == 2

    async def test_receiving_against_an_order_is_idempotent_too(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        token, item, supplier = await _stocked(db_session, api_client)
        order = await _order(api_client, token, supplier, item)
        body = {
            "lines": [
                {
                    "stock_item_id": item,
                    "quantity_invoiced": "50000.0000",
                    "quantity_received": "47000.0000",
                }
            ]
        }
        key = str(uuid.uuid4())
        path = f"{STAFF}/purchase-orders/{order['id']}/receive"

        first = await api_client.post(path, json=body, headers=_keyed(token, key))
        again = await api_client.post(path, json=body, headers=_keyed(token, key))

        assert (first.status_code, again.status_code) == (201, 201), again.text
        assert again.headers.get(_REPLAYED) == "true"
        assert await _receipts(db_session) == 1


async def test_two_taps_racing_with_one_key_book_one_delivery(fresh_database: str) -> None:
    """The case the whole mechanism exists for, on real transactions.

    Both requests carry one key and start together. The second's claim waits on the unique index
    until the first commits, then finds a finished request and replays it. Without the mechanism
    this books two receipts: a market purchase has no invoice number for the database to refuse.
    """
    engine = create_async_engine(fresh_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    application = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    application.dependency_overrides[get_session] = _session
    try:
        async with factory() as setup:
            await _world(setup, "owner")
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token = await _token(client, "owner")
            item = await _ingredient(client, token)
            supplier = await _supplier(client, token)
            body = _delivery(supplier, item)
            key = str(uuid.uuid4())

            first, second = await asyncio.gather(
                client.post(f"{STAFF}/goods-receipts", json=body, headers=_keyed(token, key)),
                client.post(f"{STAFF}/goods-receipts", json=body, headers=_keyed(token, key)),
            )

        assert (first.status_code, second.status_code) == (201, 201), second.text
        assert first.json() == second.json()
        assert [first.headers.get(_REPLAYED), second.headers.get(_REPLAYED)].count("true") == 1
        async with factory() as check:
            assert await _receipts(check) == 1
    finally:
        application.dependency_overrides.clear()
        await engine.dispose()
