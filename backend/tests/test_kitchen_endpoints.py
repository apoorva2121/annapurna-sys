"""The kitchen display over HTTP: the state machine, the two permissions, and the stream.

`test_generic_suites.py` already proves every route here is tenant-isolated and declares a
permission. `test_kitchen_send.py` proves a send raises the right paper. What is left, and what this
file is, is the part a person actually does during a service:

- **the clock only runs forwards** — `new → acknowledged → preparing → ready`, each stamping its own
  time and its own person, and nothing ever going back;
- **the kitchen owns `ready` and the floor owns `served`** — the module's main internal control,
  because a cook who clears a rail of food that never left the pass settles nothing and only widens
  a gap a manager can see;
- **a remake is new work** — the original line keeps its history and the remade dish gets its own
  ticket with its own clock;
- **a dropped stream loses nothing** — the acceptance criterion the whole design of the cursor
  exists to satisfy.

These go over HTTP rather than through the service, because G-3 says every security assertion needs
an HTTP-level test and because a waiter's token being accepted on the reads and refused on the
writes is a property of the routes, not of `KitchenService`.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import KotLineStatus, KotTicketStatus
from tests.test_orders_endpoints import ORDERS, Menu, _added, _menu, _open, _stepped
from tests.test_setup_endpoints import World, _auth, _token, _world

KOT = "/api/v1/staff/kot"


async def _sent_order(
    client: AsyncClient, token: str, menu: Menu, **open_options: Any
) -> dict[str, Any]:
    """An order with one dish on it, sent to the kitchen."""
    order = await _open(client, token, menu, **open_options)
    order = await _added(client, token, order, menu.dal)
    return await _stepped(client, token, order, "send")


async def _rail(client: AsyncClient, token: str, **params: Any) -> dict[str, Any]:
    response = await client.get(f"{KOT}/tickets", params=params, headers=_auth(token))
    assert response.status_code == 200, response.text
    return dict(response.json())


async def _one_ticket(client: AsyncClient, token: str) -> dict[str, Any]:
    tickets = (await _rail(client, token))["tickets"]
    assert len(tickets) == 1, tickets
    return dict(tickets[0])


async def _advance(client: AsyncClient, token: str, ticket_id: str, status: str) -> dict[str, Any]:
    response = await client.patch(
        f"{KOT}/tickets/{ticket_id}/status", json={"status": status}, headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


async def _chef(session: AsyncSession, client: AsyncClient) -> tuple[World, Menu, str, str]:
    """A waiter to take the order and a chef to cook it — the two sides of this module.

    Not `test_orders_endpoints._setup`, which builds no chef: that world was written when nobody
    in this product could cook anything.
    """
    world = await _world(session, "owner", "waiter", "manager", "chef")
    menu = await _menu(session, world)
    return world, menu, await _token(client, "waiter"), await _token(client, "chef")


# --------------------------------------------------------------------------- the rail


class TestTheRail:
    async def test_a_sent_order_appears_on_the_rail(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, waiter, chef = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)

        ticket = await _one_ticket(api_client, chef)

        assert ticket["status"] == KotTicketStatus.NEW
        assert ticket["lines"][0]["item_name"] == "Dal Makhani"

    async def test_the_rail_says_where_the_food_goes(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A runner needs the table, and a kitchen display has no floor plan to look it up in."""
        _, menu, waiter, chef = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)

        ticket = await _one_ticket(api_client, chef)

        assert ticket["table_codes"] == ["T6"]

    async def test_the_rail_hands_back_the_revision_to_start_the_stream_from(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """So a screen opens the stream exactly where its read finished — no gap, no double
        delivery."""
        _, menu, waiter, chef = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)

        rail = await _rail(api_client, chef)

        assert rail["revision"] == rail["tickets"][0]["revision"]

    async def test_a_served_ticket_has_left_the_rail(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, waiter, chef = await _chef(db_session, api_client)
        order = await _sent_order(api_client, waiter, menu)
        ticket = await _one_ticket(api_client, chef)
        for status in (
            KotTicketStatus.ACKNOWLEDGED,
            KotTicketStatus.PREPARING,
            KotTicketStatus.READY,
        ):
            await _advance(api_client, chef, ticket["id"], status)
        await _stepped(api_client, waiter, order, "served")

        assert (await _rail(api_client, chef))["tickets"] == []


# --------------------------------------------------------------------------- the state machine


class TestTheClockOnlyRunsForwards:
    async def test_each_arrival_stamps_its_own_time(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, waiter, chef = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)
        ticket = await _one_ticket(api_client, chef)

        acknowledged = await _advance(api_client, chef, ticket["id"], KotTicketStatus.ACKNOWLEDGED)
        preparing = await _advance(api_client, chef, ticket["id"], KotTicketStatus.PREPARING)
        ready = await _advance(api_client, chef, ticket["id"], KotTicketStatus.READY)

        assert acknowledged["acknowledged_at"] is not None
        assert preparing["started_at"] is not None
        assert ready["ready_at"] is not None

    async def test_a_step_out_of_order_names_the_step_that_was_expected(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A chef reading this at two metres needs to know what to press, not that they were
        wrong."""
        _, menu, waiter, chef = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)
        ticket = await _one_ticket(api_client, chef)

        response = await api_client.patch(
            f"{KOT}/tickets/{ticket['id']}/status",
            json={"status": KotTicketStatus.READY},
            headers=_auth(chef),
        )

        assert response.status_code == 409, response.text
        assert "acknowledged" in response.json()["message"]

    async def test_ready_does_not_go_back_to_preparing(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The one that protects the measurement. A `ready_at` overwritten by a second pass is a
        prep time that never happened, and M13 would average it into the standard for ever."""
        _, menu, waiter, chef = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)
        ticket = await _one_ticket(api_client, chef)
        for status in (
            KotTicketStatus.ACKNOWLEDGED,
            KotTicketStatus.PREPARING,
            KotTicketStatus.READY,
        ):
            await _advance(api_client, chef, ticket["id"], status)

        response = await api_client.patch(
            f"{KOT}/tickets/{ticket['id']}/status",
            json={"status": KotTicketStatus.PREPARING},
            headers=_auth(chef),
        )

        assert response.status_code == 409, response.text


class TestServedBelongsToTheFloor:
    async def test_the_kitchen_cannot_mark_a_ticket_served(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Refused with a message naming the order screen. The person is not unauthorised — they
        are on the wrong screen, and "denied" would teach them nothing.

        This is the module's main internal control: `ready` is cheap to press, and it settles
        nothing because the money and the service completion both hang off an action somebody else
        takes somewhere else.
        """
        _, menu, waiter, chef = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)
        ticket = await _one_ticket(api_client, chef)

        response = await api_client.patch(
            f"{KOT}/tickets/{ticket['id']}/status",
            json={"status": KotTicketStatus.SERVED},
            headers=_auth(chef),
        )

        assert response.status_code == 409, response.text
        assert "order screen" in response.json()["message"]
        # And a number to quote (D11, D12). The envelope carries `code` too — the frontend
        # switches on it — but a person never sees it; `brandChecklist.test.ts` holds that end.
        assert response.json()["issue"] > 0

    async def test_the_orders_serve_stamps_the_ticket_and_its_lines(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, waiter, chef = await _chef(db_session, api_client)
        order = await _sent_order(api_client, waiter, menu)
        ticket = await _one_ticket(api_client, chef)
        for status in (
            KotTicketStatus.ACKNOWLEDGED,
            KotTicketStatus.PREPARING,
            KotTicketStatus.READY,
        ):
            await _advance(api_client, chef, ticket["id"], status)

        await _stepped(api_client, waiter, order, "served")

        detail = await api_client.get(f"{KOT}/tickets/{ticket['id']}", headers=_auth(chef))
        body = detail.json()
        assert body["status"] == KotTicketStatus.SERVED
        assert body["served_at"] is not None
        assert body["lines"][0]["served_at"] is not None

    async def test_a_counter_order_served_off_the_pass_still_records_a_ready_time(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A counter-service restaurant takes the money before it cooks, so a dish can be handed
        over without anybody pressing `ready`. The database refuses a `served_at` with no
        `ready_at`, so the pass is recorded at the same instant rather than the write failing."""
        _, menu, waiter, chef = await _chef(db_session, api_client)
        order = await _sent_order(api_client, waiter, menu)
        ticket = await _one_ticket(api_client, chef)

        await _stepped(api_client, waiter, order, "served")

        detail = await api_client.get(f"{KOT}/tickets/{ticket['id']}", headers=_auth(chef))
        body = detail.json()
        assert body["status"] == KotTicketStatus.SERVED
        assert body["ready_at"] is not None
        assert body["served_at"] is not None


class TestOneDishAtATime:
    async def test_the_ticket_arrives_when_its_last_open_line_does_and_not_before(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The difference between "the table's food is ready" and "some of it is" — which is the
        difference between a runner walking to the table once and walking twice."""
        _, menu, waiter, chef = await _chef(db_session, api_client)
        order = await _open(api_client, waiter, menu)
        order = await _added(api_client, waiter, order, menu.dal)
        order = await _added(api_client, waiter, order, menu.dal)
        await _stepped(api_client, waiter, order, "send")
        ticket = await _one_ticket(api_client, chef)
        assert len(ticket["lines"]) == 2

        first = await api_client.patch(
            f"{KOT}/tickets/{ticket['id']}/lines/{ticket['lines'][0]['id']}/status",
            json={"status": KotLineStatus.READY},
            headers=_auth(chef),
        )
        assert first.status_code == 200, first.text
        assert first.json()["status"] != KotTicketStatus.READY

        second = await api_client.patch(
            f"{KOT}/tickets/{ticket['id']}/lines/{ticket['lines'][1]['id']}/status",
            json={"status": KotLineStatus.READY},
            headers=_auth(chef),
        )
        assert second.json()["status"] == KotTicketStatus.READY


class TestARemakeIsNewWork:
    async def test_the_remade_dish_arrives_as_a_new_ticket_and_the_original_keeps_its_history(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, waiter, chef = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)
        ticket = await _one_ticket(api_client, chef)

        response = await api_client.post(
            f"{KOT}/tickets/{ticket['id']}/lines/{ticket['lines'][0]['id']}/remake",
            json={"reason": "came back cold"},
            headers=_auth(chef),
        )

        assert response.status_code == 200, response.text
        remade = response.json()
        assert remade["id"] != ticket["id"]
        assert remade["is_remake"] is True
        assert remade["status"] == KotTicketStatus.NEW
        assert remade["station_id"] == ticket["station_id"]

        original = (
            await api_client.get(f"{KOT}/tickets/{ticket['id']}", headers=_auth(chef))
        ).json()
        assert original["lines"][0]["status"] == KotLineStatus.REMAKE
        assert original["lines"][0]["remake_reason"] == "came back cold"

    async def test_a_remake_needs_a_reason(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """How a kitchen learns which dishes come back and why. A blank one teaches nobody."""
        _, menu, waiter, chef = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)
        ticket = await _one_ticket(api_client, chef)

        response = await api_client.post(
            f"{KOT}/tickets/{ticket['id']}/lines/{ticket['lines'][0]['id']}/remake",
            json={"reason": ""},
            headers=_auth(chef),
        )

        assert response.status_code == 422, response.text


class TestCancellationTravelsOneWay:
    async def test_taking_a_sent_dish_off_the_bill_stops_the_kitchen_cooking_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A kitchen that keeps cooking a cancelled dish is the exact operational failure a KOT
        system exists to prevent."""
        _, menu, waiter, chef = await _chef(db_session, api_client)
        order = await _sent_order(api_client, waiter, menu)
        ticket = await _one_ticket(api_client, chef)

        response = await api_client.post(
            f"{ORDERS}/{order['id']}/lines/{order['lines'][0]['id']}/remove",
            json={"version": order["version"], "reason": "guest changed their mind"},
            headers=_auth(waiter),
        )
        assert response.status_code == 200, response.text

        detail = (await api_client.get(f"{KOT}/tickets/{ticket['id']}", headers=_auth(chef))).json()
        assert detail["lines"][0]["status"] == KotLineStatus.CANCELLED
        # Nothing left to cook, so the ticket leaves the rail with it.
        assert detail["status"] == KotTicketStatus.CANCELLED
        assert (await _rail(api_client, chef))["tickets"] == []


# --------------------------------------------------------------------------- permissions


class TestTheFloorWatchesAndDoesNotDrive:
    async def test_a_waiter_may_read_the_rail(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, waiter, _ = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)

        response = await api_client.get(f"{KOT}/tickets", headers=_auth(waiter))

        assert response.status_code == 200, response.text

    async def test_a_waiter_may_not_declare_a_dish_ready(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The design's own line, and the reason `kot.update` exists separately: seeing that table
        six's mains are still preparing is information; declaring them ready is a way to make the
        numbers look better."""
        _, menu, waiter, chef = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)
        ticket = await _one_ticket(api_client, chef)

        response = await api_client.patch(
            f"{KOT}/tickets/{ticket['id']}/status",
            json={"status": KotTicketStatus.ACKNOWLEDGED},
            headers=_auth(waiter),
        )

        assert response.status_code == 403, response.text

    async def test_a_waiter_may_not_ask_for_a_remake(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, waiter, chef = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)
        ticket = await _one_ticket(api_client, chef)

        response = await api_client.post(
            f"{KOT}/tickets/{ticket['id']}/lines/{ticket['lines'][0]['id']}/remake",
            json={"reason": "cold"},
            headers=_auth(waiter),
        )

        assert response.status_code == 403, response.text


class TestTheStreamOverHttp:
    async def test_the_stream_tells_proxies_not_to_buffer_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The failure this guards is the nastiest shape there is: works in development, works in
        staging behind nothing, and in production a buffering proxy holds `text/event-stream` until
        its buffer fills — so the kitchen display is silently a few minutes behind all service.

        FastAPI sets both headers itself for an SSE response. That is exactly why there is a test:
        the guarantee is depended upon and not owned, so a framework upgrade that dropped it would
        otherwise be discovered by a restaurant rather than by this suite.
        """
        _, menu, waiter, chef = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)

        async with api_client.stream("GET", f"{KOT}/stream", headers=_auth(chef)) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["x-accel-buffering"] == "no"
            assert "no-cache" in response.headers["cache-control"]

    async def test_the_stream_opens_by_naming_the_backoff(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`retry` is server-controlled so the reconnect interval can be changed without shipping a
        frontend, and it is a *comment* rather than an event so a screen does not redraw on
        connect."""
        _, menu, waiter, chef = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)

        async with api_client.stream("GET", f"{KOT}/stream", headers=_auth(chef)) as response:
            opening = b""
            async for chunk in response.aiter_bytes():
                opening += chunk
                if b"\n\n" in opening:
                    break

        assert b"retry: 3000" in opening

    async def test_a_waiter_may_watch_the_stream(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`kot.view`, which a waiter holds. Watching is the half of the kitchen the floor gets."""
        _, menu, waiter, _ = await _chef(db_session, api_client)
        await _sent_order(api_client, waiter, menu)

        async with api_client.stream("GET", f"{KOT}/stream", headers=_auth(waiter)) as response:
            assert response.status_code == 200

    async def test_the_stream_refuses_a_token_without_kot_view(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """An accountant holds `order.view` and no kitchen permission at all."""
        world = await _world(db_session, "owner", "waiter", "manager", "chef", "accountant")
        assert world is not None
        accountant = await _token(api_client, "accountant")

        async with api_client.stream("GET", f"{KOT}/stream", headers=_auth(accountant)) as response:
            assert response.status_code == 403
