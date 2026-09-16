"""The kitchen stream: what `GET /kot/stream` yields, and why it is shaped like this.

`docs/modules/M08-kitchen-spec.md` decisions 3 and 4 argue the design. The code below is the part
that is easy to get subtly wrong, so each hazard is named where it is handled.

**It polls a cursor.** Not an in-process broadcast, which is wrong the moment there are two workers
and then fails silently and only under load; not `LISTEN`/`NOTIFY`, which needs a connection held
outside the pool for the life of the process and which pgbouncer in transaction-pooling mode — the
likely production shape — drops without erroring. One indexed query per tick is the same code path
for live delivery and for reconnect replay, so the reconnect test exercises the production path
rather than a second implementation of it.

**It opens a session per tick and closes it.** A dependency-injected session would hold one pooled
database connection for the whole of a service — six screens, six connections, never returned. This
is the only place in the application that takes the session *factory* instead.

**It replays inclusively.** Several tickets can share a revision, so a client resumes at
`>= Last-Event-ID`. Re-sending is free, because every event is a whole ticket state keyed by its id
and applying one twice changes nothing. An exclusive cursor would permanently lose the rest of a
batch whose first event arrived before the connection dropped.

**It re-checks the session every tick.** This is the one place in the product where revocation and
a long-lived connection meet. A stream opened at 9pm on a token revoked at 10pm must not still be
running at 3am, and a check made at the handshake cannot say that.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.actor import Actor
from app.models.kitchen import KotTicket
from app.repositories.account import UserSessionRepository
from app.repositories.kitchen import KitchenRepository

logger = logging.getLogger(__name__)

# 500 ms puts worst-case delivery at half the 1 s budget. Lower would buy nothing anybody can
# perceive on a wall-mounted screen and would double the database work for every open display.
TICK_SECONDS = 0.5
# Long enough that an idle kitchen is quiet, short enough that a dead connection becomes obvious
# before anybody starts wondering. Proxies also close idle connections, and this keeps them open.
HEARTBEAT_SECONDS = 15.0
# What the browser waits before reconnecting, in milliseconds. Server-controlled, so the backoff can
# be changed without shipping a frontend.
RETRY_MS = 3000
# How many tickets one tick may carry. Bounded like every other query in this codebase
# (engineering-standards §3); a backlog drains over the ticks that follow.
PAGE = 50
# **A stream ends by itself, and does not wait to be told to.**
#
# Fifty-five minutes, just inside Cloud Run's sixty-minute request cap, so the server closes the
# response cleanly and the browser reconnects with its cursor rather than the platform killing a
# connection mid-event.
#
# It is also the backstop for the thing that actually bit: `request.is_disconnected()` is the only
# signal that a client has gone, and it is not reliable on every transport — under httpx's ASGI
# transport it never fires at all, so the first version of this generator looped for ever against a
# client that had already hung up. A loop whose only exit is a signal from somewhere else is a loop
# that hangs when that signal does not arrive, and "for ever" on a route that holds a database
# session per tick is not an acceptable failure mode.
MAX_SECONDS = 55 * 60


@dataclass(frozen=True, slots=True)
class TicketEvent:
    """One ticket's whole state. Never a delta — see the module docstring."""

    revision: int
    ticket: KotTicket


async def kitchen_events(
    sessions: async_sessionmaker[AsyncSession],
    actor: Actor,
    *,
    station_id: uuid.UUID | None,
    cursor: int | None,
    is_disconnected: Callable[[], Awaitable[bool]],
    tick_seconds: float = TICK_SECONDS,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
    max_seconds: float | None = None,
) -> AsyncIterator[TicketEvent | None]:
    """Yield a ticket event per change, and `None` as a heartbeat when nothing has happened.

    `is_disconnected` is injected rather than read off the request, so the reconnect behaviour —
    the whole point of this module — is testable without an HTTP server standing in the way.
    """
    position = cursor
    last_sent = datetime.now(UTC)
    # `MAX_SECONDS` is read here rather than used as a default argument, because a default is
    # evaluated once when the function is defined — so a test that lowers the constant would be
    # lowering something this generator had already stopped reading, and would hang for the full
    # fifty-five minutes proving it.
    deadline = datetime.now(UTC) + timedelta(
        seconds=MAX_SECONDS if max_seconds is None else max_seconds
    )

    while datetime.now(UTC) < deadline and not await is_disconnected():
        async with sessions() as session:
            if not await _still_signed_in(session, actor):
                logger.info("kot.stream_closed", extra={"reason": "session_revoked"})
                return
            kitchen = KitchenRepository(session, actor.scope)
            if position is None:
                # A screen arriving without a cursor starts from *now*, not from the beginning of
                # time: it has just read the rail, and replaying every ticket since the restaurant
                # opened would redraw tonight from last March.
                position = await kitchen.current_revision() + 1
            tickets = list(await kitchen.since(position, station_id=station_id, limit=PAGE))

        for ticket in tickets:
            last_sent = datetime.now(UTC)
            yield TicketEvent(revision=ticket.revision, ticket=ticket)

        if tickets:
            highest = max(ticket.revision for ticket in tickets)
            # A full page may have cut a revision in half — several tickets can share one. Stay on
            # that revision so the remainder arrives next tick; re-delivering what was already sent
            # costs nothing, because every event is a whole ticket state keyed by its id.
            position = highest if len(tickets) == PAGE else highest + 1

        if (datetime.now(UTC) - last_sent).total_seconds() >= heartbeat_seconds:
            last_sent = datetime.now(UTC)
            yield None

        await asyncio.sleep(tick_seconds)


async def _still_signed_in(session: AsyncSession, actor: Actor) -> bool:
    """One indexed lookup per tick.

    A token minted before sessions carried an id (backlog-issues B4) has nothing to look up and
    falls back to the token's own expiry — which the handshake already checked, and which bounds
    such a stream at fifteen minutes rather than for ever.
    """
    if actor.session_id is None:
        return True
    return await UserSessionRepository(session).is_live(actor.session_id)
