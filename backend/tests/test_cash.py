"""The till over HTTP: spec decision 11 and acceptance criterion 16.

"Short the till and blame the float" is the threat. Every test below is one way of making the cash
disappear on paper — a payout nobody recorded, a count typed over afterwards, a variance quietly
corrected by the person who caused it, a refund that reaches back into a till already counted.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orders import CashMovement, Payment
from tests.test_orders_endpoints import _added, _menu, _open, _setup
from tests.test_reversals import _credit
from tests.test_settlement import _GSTIN, _count, _fresh_app, _registered, _settle
from tests.test_setup_endpoints import _auth, _token, _world

CASH = "/api/v1/staff/cash/sessions"


def _keyed(token: str, key: str | None = None) -> dict[str, str]:
    return _auth(token) | {"Idempotency-Key": key or str(uuid.uuid4())}


async def _open_till(client: AsyncClient, token: str, float_: str = "2000.00") -> dict[str, Any]:
    response = await client.post(CASH, json={"opening_float": float_}, headers=_auth(token))
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _payout(
    client: AsyncClient, token: str, till: dict[str, Any], amount: str, key: str | None = None
) -> Response:
    return await client.post(
        f"{CASH}/{till['id']}/payouts",
        json={"amount": amount, "reason": "vegetables from the market"},
        headers=_keyed(token, key),
    )


async def _close(
    client: AsyncClient, token: str, till: dict[str, Any], counts: list[tuple[str, int]]
) -> Response:
    return await client.post(
        f"{CASH}/{till['id']}/close",
        json={"counts": [{"denomination": d, "quantity": q} for d, q in counts]},
        headers=_auth(token),
    )


async def _adjust(client: AsyncClient, token: str, till: dict[str, Any], amount: str) -> Response:
    return await client.post(
        f"{CASH}/{till['id']}/adjustments",
        json={"amount": amount, "reason": "found in the second drawer"},
        headers=_keyed(token),
    )


class TestOpeningTheTill:
    async def test_a_manager_opens_the_till_with_a_float(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")

        till = await _open_till(api_client, manager)

        assert till["status"] == "open"
        assert (till["opening_float"], till["expected_cash"]) == ("2000.00", "2000.00")
        assert till["variance"] is None

    async def test_a_second_till_cannot_open_while_one_is(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        first = await _open_till(api_client, manager)

        response = await api_client.post(
            CASH, json={"opening_float": "1000.00"}, headers=_auth(manager)
        )

        assert response.status_code == 409
        assert response.json()["code"] == "cash.session_open"
        assert response.json()["details"]["session_id"] == first["id"]

    async def test_a_waiter_takes_cash_and_never_touches_the_till(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, waiter = await _setup(db_session, api_client)

        response = await api_client.post(
            CASH, json={"opening_float": "2000.00"}, headers=_auth(waiter)
        )

        assert response.status_code == 403


class TestPayouts:
    async def test_a_payout_comes_out_of_what_the_till_should_hold(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        till = await _open_till(api_client, manager)

        response = await _payout(api_client, manager, till, "300.00")

        assert response.status_code == 201, response.text
        assert (response.json()["payouts"], response.json()["expected_cash"]) == (
            "300.00",
            "1700.00",
        )
        (movement,) = response.json()["movements"]
        assert (movement["type"], movement["reason"]) == ("payout", "vegetables from the market")

    async def test_a_payout_larger_than_the_till_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        till = await _open_till(api_client, manager, "500.00")

        response = await _payout(api_client, manager, till, "500.01")

        assert response.status_code == 422
        assert response.json()["code"] == "cash.payout_exceeds_till"

    async def test_a_payout_tapped_twice_leaves_the_till_once(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        till = await _open_till(api_client, manager)
        key = str(uuid.uuid4())

        first = await _payout(api_client, manager, till, "300.00", key=key)
        again = await _payout(api_client, manager, till, "300.00", key=key)

        assert (first.status_code, again.status_code) == (201, 201), again.text
        assert again.headers.get("Idempotent-Replayed") == "true"
        assert await _count(db_session, CashMovement) == 1


class TestCashingUp:
    async def test_cash_taken_at_the_table_is_what_the_till_expects(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, waiter = await _setup(db_session, api_client)
        await _registered(db_session, world)
        manager = await _token(api_client, "manager")
        till = await _open_till(api_client, manager)
        order = await _added(api_client, waiter, await _open(api_client, waiter, menu), menu.dal)
        paid = await _settle(
            api_client, waiter, order, payments=[{"method": "cash", "amount": "493.50"}]
        )
        assert paid.status_code == 201, paid.text

        now = (await api_client.get(f"{CASH}/{till['id']}", headers=_auth(manager))).json()

        assert (now["cash_taken"], now["expected_cash"]) == ("493.50", "2493.50")

    async def test_closing_records_the_count_and_a_variance_that_is_never_corrected_away(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """₹2,000 float, ₹300 paid out, so ₹1,700 expected; ₹1,300 counted is ₹400 short."""
        await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        till = await _open_till(api_client, manager)
        assert (await _payout(api_client, manager, till, "300.00")).status_code == 201

        response = await _close(api_client, manager, till, [("500.00", 2), ("100.00", 3)])

        assert response.status_code == 200, response.text
        closed = response.json()
        assert closed["status"] == "closed"
        assert (closed["expected_cash"], closed["counted_cash"], closed["variance"]) == (
            "1700.00",
            "1300.00",
            "-400.00",
        )
        assert {(c["denomination"], c["quantity"]) for c in closed["counts"]} == {
            ("500.00", 2),
            ("100.00", 3),
        }

    async def test_a_closed_till_cannot_be_counted_again(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Otherwise a ₹400 shortage is corrected by typing a different count."""
        await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        till = await _open_till(api_client, manager)
        assert (await _close(api_client, manager, till, [("500.00", 4)])).status_code == 200

        again = await _close(api_client, manager, till, [("500.00", 3)])

        assert again.status_code == 409
        assert again.json()["code"] == "cash.session_closed"

    async def test_a_note_counted_twice_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        till = await _open_till(api_client, manager)

        response = await _close(api_client, manager, till, [("500.00", 2), ("500.00", 2)])

        assert response.status_code == 422
        assert response.json()["code"] == "cash.count_duplicate"


class TestAdjustments:
    """M05's count-approval rule, held the same way: whoever closed a till does not correct it."""

    async def test_the_person_who_closed_the_till_cannot_adjust_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        till = await _open_till(api_client, manager)
        assert (await _close(api_client, manager, till, [("500.00", 3)])).status_code == 200

        response = await _adjust(api_client, manager, till, "400.00")

        assert response.status_code == 409
        assert response.json()["code"] == "cash.adjustment_by_closer"

    async def test_another_manager_adjusts_and_the_original_variance_stays_beside_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        owner = await _token(api_client, "owner")
        till = await _open_till(api_client, manager)
        assert (await _close(api_client, manager, till, [("100.00", 16)])).status_code == 200

        response = await _adjust(api_client, owner, till, "400.00")

        assert response.status_code == 201, response.text
        adjusted = response.json()
        assert (adjusted["variance"], adjusted["adjusted_variance"]) == ("-400.00", "0.00")

    async def test_an_open_till_is_counted_not_adjusted(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        owner = await _token(api_client, "owner")
        till = await _open_till(api_client, manager)

        response = await _adjust(api_client, owner, till, "100.00")

        assert response.status_code == 409
        assert response.json()["code"] == "cash.session_still_open"


class TestARefundInALaterTill:
    async def test_a_refund_next_shift_leaves_the_counted_till_untouched(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 16. The bill was paid into till A, which was counted and closed; the
        refund is given from till B, open now. Till A's expected cash and variance do not move, and
        till B expects exactly the refund less."""
        world, menu, waiter = await _setup(db_session, api_client)
        await _registered(db_session, world)
        manager = await _token(api_client, "manager")
        owner = await _token(api_client, "owner")

        till_a = await _open_till(api_client, manager)
        order = await _added(
            api_client, waiter, await _open(api_client, waiter, menu), menu.dal, quantity=2
        )
        invoice = (
            await _settle(
                api_client, waiter, order, payments=[{"method": "cash", "amount": "987.00"}]
            )
        ).json()
        # ₹2,000 float and ₹987 of cash, counted in notes and coins that exist.
        counted = [
            ("500.00", 5),
            ("200.00", 2),
            ("50.00", 1),
            ("20.00", 1),
            ("10.00", 1),
            ("5.00", 1),
            ("2.00", 1),
        ]
        closed_a = (await _close(api_client, manager, till_a, counted)).json()
        assert closed_a["variance"] == "0.00"

        till_b = await _open_till(api_client, owner, "1000.00")
        refund = await _credit(
            api_client, manager, invoice, refunds=[{"method": "cash", "amount": "493.50"}]
        )
        assert refund.status_code == 201, refund.text

        after_a = (await api_client.get(f"{CASH}/{till_a['id']}", headers=_auth(manager))).json()
        after_b = (await api_client.get(f"{CASH}/{till_b['id']}", headers=_auth(manager))).json()
        assert (after_a["expected_cash"], after_a["variance"]) == (
            closed_a["expected_cash"],
            closed_a["variance"],
        )
        assert Decimal(after_b["expected_cash"]) == Decimal("1000.00") - Decimal("493.50")


# --------------------------------------------------------------------------- the second reader

INVOICES = "/api/v1/staff/invoices"


async def _cash_bill(
    session: AsyncSession, client: AsyncClient
) -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any], str]:
    """A till open with a ₹2,000 float and one dal settled into it in cash."""
    world, menu, waiter = await _setup(session, client)
    await _registered(session, world)
    manager = await _token(client, "manager")
    till = await _open_till(client, manager)
    order = await _added(client, waiter, await _open(client, waiter, menu), menu.dal)
    paid = await _settle(client, waiter, order, payments=[{"method": "cash", "amount": "493.50"}])
    assert paid.status_code == 201, paid.text
    return world, till, order, paid.json(), manager


class TestACancelledBillsCash:
    """Second reader, finding 3. Cancelling is for a bill raised against the wrong table, and the
    same notes are then settled again against the right one. Left in, they are expected twice."""

    async def test_a_cancelled_invoice_takes_its_cash_out_of_what_the_open_till_expects(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, till, _, invoice, manager = await _cash_bill(db_session, api_client)

        cancelled = await api_client.post(
            f"{INVOICES}/{invoice['id']}/cancel",
            json={"reason": "billed to table 7"},
            headers=_keyed(manager),
        )

        assert cancelled.status_code == 200, cancelled.text
        now = (await api_client.get(f"{CASH}/{till['id']}", headers=_auth(manager))).json()
        assert (now["cash_taken"], now["expected_cash"]) == ("0.00", "2000.00")

    async def test_an_invoice_whose_cash_is_already_counted_cannot_be_cancelled(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Cancelling it would change a till that was closed and counted, which nothing may do."""
        _, till, _, invoice, manager = await _cash_bill(db_session, api_client)
        closed = await _close(api_client, manager, till, [("500.00", 5)])
        assert closed.status_code == 200, closed.text

        refused = await api_client.post(
            f"{INVOICES}/{invoice['id']}/cancel",
            json={"reason": "billed to table 7"},
            headers=_keyed(manager),
        )

        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "invoice.till_closed"
        after = (await api_client.get(f"{CASH}/{till['id']}", headers=_auth(manager))).json()
        assert after["expected_cash"] == closed.json()["expected_cash"]


class TestCashIntoACountedTill:
    """Second reader, finding 1: cash must never be posted into a till that has been counted."""

    async def test_the_database_refuses_cash_posted_into_a_closed_till(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, till, order, invoice, manager = await _cash_bill(db_session, api_client)
        assert (await _close(api_client, manager, till, [("500.00", 5)])).status_code == 200

        db_session.add(
            Payment(
                restaurant_id=world.restaurant.id,
                order_id=uuid.UUID(order["id"]),
                invoice_id=uuid.UUID(invoice["id"]),
                cash_session_id=uuid.UUID(till["id"]),
                method="cash",
                amount=Decimal("100.00"),
                paid_at=datetime.now(UTC),
                business_date=datetime.now(UTC).date(),
            )
        )
        with pytest.raises(DBAPIError) as raised:
            await db_session.flush()
        assert "closed" in str(raised.value)


async def test_cash_settled_while_the_till_is_being_closed_never_lands_in_that_till(
    fresh_database: str,
) -> None:
    """The close holds the till row. A settle looking for the open till waits for it, and once the
    close commits there is no open till, so the cash is posted to none rather than to the till just
    counted.

    **To re-verify this test is not decorative:** remove `with_for_update(read=True)` from
    `CashSessionRepository.open_id`. The settle then fails on migration 0021's trigger instead of
    succeeding; drop the trigger as well, and it posts its cash into the closed till.
    """
    application, factory, engine = await _fresh_app(fresh_database)
    try:
        async with factory() as setup:
            world = await _world(setup, "owner")
            menu = await _menu(setup, world)
            world.restaurant.gstin = _GSTIN
            await setup.commit()
            restaurant_id = world.restaurant.id
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            owner = await _token(client, "owner")
            till = await _open_till(client, owner)
            opened = await _open(client, owner, menu, type="takeaway", table_ids=[])
            order = await _added(client, owner, opened, menu.dal)
            params = {"id": till["id"], "restaurant_id": str(restaurant_id)}
            async with factory() as closer:
                # What `CashService.close` does, held open: lock the till, then mark it counted.
                await closer.execute(
                    text(
                        "SELECT id FROM cash_session"
                        " WHERE id = :id AND restaurant_id = :restaurant_id FOR UPDATE"
                    ),
                    params,
                )
                await closer.execute(
                    text(
                        "UPDATE cash_session SET status = 'closed', closed_at = now(),"
                        " closed_by = opened_by, counted_cash = opening_float, variance = 0"
                        " WHERE id = :id AND restaurant_id = :restaurant_id"
                    ),
                    params,
                )
                settling = asyncio.create_task(
                    _settle(
                        client,
                        owner,
                        order,
                        payments=[{"method": "cash", "amount": order["grand_total"]}],
                    )
                )
                await asyncio.sleep(3)
                assert not settling.done(), "the settle should be waiting on the till being closed"
                await closer.commit()
            response = await settling

        assert response.status_code == 201, response.text
        async with factory() as check:
            posted_to = await check.scalar(
                select(Payment.cash_session_id).where(Payment.restaurant_id == restaurant_id)
            )
        assert posted_to is None
    finally:
        application.dependency_overrides.clear()
        await engine.dispose()
