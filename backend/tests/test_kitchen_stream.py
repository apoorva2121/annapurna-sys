"""A dropped kitchen display loses nothing — M08's acceptance criteria 10 to 13.

This is the file the whole design of the cursor exists for, so it tests the *property* rather than
the mechanism: disconnect, let three things happen, reconnect with `Last-Event-ID`, and receive all
three. If a future change swaps polling for `LISTEN`/`NOTIFY` or an in-process broadcast, these
should still pass — and if they cannot be made to pass, that change is wrong.

They drive `kitchen_events` directly rather than over HTTP. Not to avoid the transport: the
generator is where the cursor arithmetic lives, and a test that opened a real SSE connection would
spend its time on `anyio` task groups and prove less about the thing that can actually be wrong —
*which revision does the client resume from, and is anything between the two lost?*

The tick interval is compressed. Real time is 500 ms against a 1 s budget; waiting that out
thirteen times would add a minute to every run for no extra confidence, and the hazard here is
arithmetic rather than duration.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.actor import Actor
from app.core.enums import UserAccountStatus
from app.models.identity import UserAccount, UserSession
from app.services.kitchen import KitchenService
from app.services.kitchen_stream import TicketEvent, kitchen_events
from tests.test_kitchen_send import _line, _order, _scope
from tests.test_orders_schema import _World
from tests.test_orders_schema import _world as _order_world

# Fast enough that thirteen tests do not add a minute to the run; the arithmetic under test does
# not care how long a tick is.
_TICK = 0.01


def _actor(world: _World, session_id: uuid.UUID | None = None) -> Actor:
    return Actor(
        employee_id=world.employee.id,
        organization_id=world.restaurant.organization_id,
        restaurant_id=world.restaurant.id,
        full_name=world.employee.full_name,
        permissions=frozenset({"kot.view"}),
        rank=0,
        session_id=session_id,
    )


class _Connection:
    """A client that can be hung up on, and counts its ticks so a test can bound the wait."""

    def __init__(self, hang_up_after: int) -> None:
        self.ticks = 0
        self._hang_up_after = hang_up_after

    async def is_disconnected(self) -> bool:
        self.ticks += 1
        return self.ticks > self._hang_up_after


async def _drain(
    sessions: async_sessionmaker[AsyncSession],
    actor: Actor,
    *,
    cursor: int | None,
    ticks: int,
    station_id: uuid.UUID | None = None,
) -> list[TicketEvent | None]:
    """Everything the stream yields over a bounded number of ticks."""
    seen: list[TicketEvent | None] = []
    connection = _Connection(ticks)
    async for event in kitchen_events(
        sessions,
        actor,
        station_id=station_id,
        cursor=cursor,
        is_disconnected=connection.is_disconnected,
        tick_seconds=_TICK,
        heartbeat_seconds=1000.0,
    ):
        seen.append(event)
    return seen


def _factory(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    """A factory handing back the test's own session.

    The stream opens and closes a session per tick in production, which it must: holding one for a
    whole service would take a pooled connection out of circulation for hours. Here every tick gets
    the test's transaction instead, so what a tick reads is what this test has written and not
    committed.
    """

    class _Same:
        def __call__(self) -> Any:
            return _Ctx()

    class _Ctx:
        async def __aenter__(self) -> AsyncSession:
            return session

        async def __aexit__(self, *_: object) -> None:
            return None

    return _Same()  # type: ignore[return-value]


async def _three_kitchen_events(session: AsyncSession, world: _World) -> list[int]:
    """Three separate sends, so three separate revisions — the "missed three" of criterion 11."""
    service = KitchenService(session, _scope(world))
    revisions = []
    order = await _order(session, world)
    for index in range(3):
        line = await _line(session, world, order, seq=index)
        [ticket] = await service.raise_tickets(order, [line])
        revisions.append(ticket.revision)
    return revisions


class TestNothingIsLostAcrossADrop:
    async def test_a_client_that_missed_three_events_receives_all_three_on_reconnect(
        self, db_session: AsyncSession
    ) -> None:
        """Acceptance criterion 11, and the reason this module has a cursor at all.

        The client is *not* connected while the three things happen — there is no queue holding
        them, and nothing in memory that would survive a worker restart. They are recovered because
        the stream is derived from the table.
        """
        world = await _order_world(db_session, "streamone")
        sessions = _factory(db_session)
        actor = _actor(world)

        opened = await _drain(sessions, actor, cursor=None, ticks=1)
        assert opened == []
        cursor_at_disconnect = await KitchenService(db_session, _scope(world)).current_revision()

        revisions = await _three_kitchen_events(db_session, world)

        resumed = await _drain(sessions, actor, cursor=cursor_at_disconnect + 1, ticks=1)

        assert [event.revision for event in resumed if event is not None] == revisions

    async def test_resuming_is_inclusive_of_the_revision_the_client_last_saw(
        self, db_session: AsyncSession
    ) -> None:
        """Several tickets can share one revision — a send that reaches three stations is one
        kitchen event. If the connection dies after the first of those three reaches the browser,
        an exclusive resume would lose the other two for ever.

        So a client resumes at `>= Last-Event-ID` and the last revision is re-delivered. That costs
        nothing, because every event is a whole ticket state keyed by its id: applying one twice
        changes nothing on the screen.
        """
        world = await _order_world(db_session, "streamtwo")
        sessions = _factory(db_session)
        revisions = await _three_kitchen_events(db_session, world)

        resumed = await _drain(sessions, _actor(world), cursor=revisions[-1], ticks=1)

        assert [event.revision for event in resumed if event is not None] == [revisions[-1]]

    async def test_a_screen_arriving_without_a_cursor_starts_from_now(
        self, db_session: AsyncSession
    ) -> None:
        """It has just read the rail. Replaying every ticket since the restaurant opened would
        redraw tonight from last March, and on a busy Saturday that is thousands of events for a
        screen that already has the answer."""
        world = await _order_world(db_session, "streamthree")
        sessions = _factory(db_session)
        await _three_kitchen_events(db_session, world)

        fresh = await _drain(sessions, _actor(world), cursor=None, ticks=1)

        assert fresh == []

    async def test_an_event_after_the_client_arrives_is_delivered(
        self, db_session: AsyncSession
    ) -> None:
        world = await _order_world(db_session, "streamfour")
        sessions = _factory(db_session)
        actor = _actor(world)
        start = await KitchenService(db_session, _scope(world)).current_revision()
        revisions = await _three_kitchen_events(db_session, world)

        live = await _drain(sessions, actor, cursor=start + 1, ticks=1)

        assert [event.revision for event in live if event is not None] == revisions


class TestTheStreamIsScoped:
    async def test_one_restaurants_cursor_selects_nothing_in_another(
        self, db_session: AsyncSession
    ) -> None:
        """The stream is the only place this product hands a cursor to a client, so it is the only
        place a cursor could be replayed against somebody else's kitchen. It selects nothing
        because the repository is scoped, not because the number is unguessable."""
        mine = await _order_world(db_session, "streamscopeone")
        theirs = await _order_world(db_session, "streamscopetwo")
        sessions = _factory(db_session)
        their_revisions = await _three_kitchen_events(db_session, theirs)

        # My screen, resuming from a cursor taken off their stream.
        leaked = await _drain(sessions, _actor(mine), cursor=their_revisions[0], ticks=1)

        assert [event for event in leaked if event is not None] == []

    async def test_a_station_sees_only_its_own_rail(self, db_session: AsyncSession) -> None:
        world = await _order_world(db_session, "streamstation")
        sessions = _factory(db_session)
        start = await KitchenService(db_session, _scope(world)).current_revision()
        await _three_kitchen_events(db_session, world)

        other_station = uuid.uuid4()
        filtered = await _drain(
            sessions, _actor(world), cursor=start + 1, ticks=1, station_id=other_station
        )

        assert [event for event in filtered if event is not None] == []


class TestARevokedSessionEndsTheStream:
    async def test_the_stream_closes_within_a_tick_of_the_session_being_revoked(
        self, db_session: AsyncSession
    ) -> None:
        """The one place in the product where revocation and a long-lived connection meet.

        Every other route re-checks authorisation by being called again. A stream opened at 9pm on
        a token revoked at 10pm would otherwise still be delivering a restaurant's tickets at 3am,
        because the handshake was the only check it ever got.
        """
        world = await _order_world(db_session, "streamrevoked")
        sessions = _factory(db_session)
        # That world's employee has no login — it was built for schema tests, where nobody signs
        # in. A session needs an account, so this one gets the smallest account there is.
        account = UserAccount(
            organization_id=world.restaurant.organization_id,
            email="chef@streamrevoked.test",
            password_hash=None,
            status=UserAccountStatus.INVITED,
        )
        db_session.add(account)
        await db_session.flush()
        session_row = UserSession(
            user_account_id=account.id,
            refresh_token_hash=uuid.uuid4().hex,
            family_id=uuid.uuid4(),
            expires_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
        db_session.add(session_row)
        await db_session.flush()

        await db_session.execute(
            update(UserSession)
            .where(UserSession.id == session_row.id)
            .values(revoked_at=datetime.now(UTC))
        )
        await db_session.flush()

        # Ten ticks' worth of patience: the stream must end on its own, not because the client
        # hung up.
        delivered = await _drain(sessions, _actor(world, session_row.id), cursor=None, ticks=10)

        assert delivered == []
