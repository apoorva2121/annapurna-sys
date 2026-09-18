"""The kitchen stream: what `GET /kot/stream` yields, and why it is shaped like this.

`docs/modules/M08-kitchen-spec.md` decisions 3 and 4 argue the design. The code below is the part
that is easy to get subtly wrong, so each hazard is named where it is handled.

**The loop moved to `app/services/event_stream.py` when M11 needed the same one**, and so did the
paragraphs below — they are kept here in short form because this is the file somebody opens when
the kitchen display misbehaves. The long form, with M08's full argument, is in that module.

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

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.actor import Actor
from app.models.kitchen import KotTicket
from app.repositories.kitchen import KitchenRepository
from app.services.event_stream import RevisionBatch, revision_stream

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

    The loop itself is `app/services/event_stream.py` since M11 needed the same one for messages.
    Everything this module still owns is kitchen-shaped: which rows a tick fetches, and what an
    event carries.
    """

    async def fetch(session: AsyncSession, position: int) -> list[RevisionBatch[KotTicket]]:
        kitchen = KitchenRepository(session, actor.scope)
        tickets = await kitchen.since(position, station_id=station_id, limit=PAGE)
        return [RevisionBatch(revision=ticket.revision, payload=ticket) for ticket in tickets]

    async def latest(session: AsyncSession) -> int:
        return await KitchenRepository(session, actor.scope).current_revision()

    # `MAX_SECONDS` is read here rather than used as a default argument, because a default is
    # evaluated once when the function is defined — so a test that lowers the constant would be
    # lowering something this generator had already stopped reading, and would hang for the full
    # fifty-five minutes proving it.
    deadline = MAX_SECONDS if max_seconds is None else max_seconds

    async for event in revision_stream(
        sessions,
        actor,
        fetch=fetch,
        latest_revision=latest,
        cursor=cursor,
        is_disconnected=is_disconnected,
        page=PAGE,
        tick_seconds=tick_seconds,
        heartbeat_seconds=heartbeat_seconds,
        max_seconds=deadline,
        closed_log_event="kot.stream_closed",
    ):
        yield None if event is None else TicketEvent(revision=event.revision, ticket=event.payload)
