"""The polling cursor both server-sent streams are built on.

M08 wrote this once, for the kitchen display, and argued every part of it. M11 needs the same
thing for messages and tasks, so the machinery moved here rather than being written a second time.
**M08's behaviour did not change**: `tests/test_kitchen_stream.py` and
`tests/test_kitchen_latency.py` pass unedited, and they are the regression suite for this
extraction rather than something adjusted to fit it.

What moved, and why each part is the way it is (the reasoning is `kitchen_stream.py`'s, kept with
the code it describes):

**It polls a cursor.** Not an in-process broadcast, which is wrong the moment there are two workers
and then fails silently and only under load; not `LISTEN`/`NOTIFY`, which needs a connection held
outside the pool for the life of the process and which pgbouncer in transaction-pooling mode — the
likely production shape — drops without erroring. One indexed query per tick is the same code path
for live delivery and for reconnect replay, so the reconnect test exercises the production path
rather than a second implementation of it.

**It opens a session per tick and closes it.** A dependency-injected session would hold one pooled
connection for the whole of a service — six screens, six connections, never returned. These are the
only places in the application that take the session *factory*.

**It replays inclusively.** Several rows can share a revision, so a client resumes at
`>= Last-Event-ID`. Re-sending is free, because every event is a whole object state keyed by its
id and applying one twice changes nothing. An exclusive cursor would permanently lose the rest of
a batch whose first event arrived before the connection dropped.

**It re-checks the session every tick.** The one place in the product where revocation and a
long-lived connection meet. A stream opened at 9pm on a token revoked at 10pm must not still be
running at 3am, and a check made at the handshake cannot say that.

**It ends by itself.** `request.is_disconnected()` is the only signal that a client has gone, and
it is not reliable on every transport — under httpx's ASGI transport it never fires at all. A loop
whose only exit is a signal from somewhere else is a loop that hangs when that signal does not
arrive, and "for ever" on a route holding a database session per tick is not an acceptable failure
mode. So every stream carries a deadline, inside Cloud Run's sixty-minute request cap, and the
browser reconnects with its cursor.

What did **not** move is the counter. `kot_stream_cursor` and `comm_stream_cursor` stay two tables:
a Postgres sequence is global, and a global cursor handed to a client leaks how busy every other
tenant is. Sharing one row between the kitchen and the inbox would also make every message bump the
kitchen's revision, which would wake every display in the building.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.actor import Actor
from app.repositories.account import UserSessionRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RevisionBatch[T]:
    """What one tick found: the rows, and whether the page was full.

    "Full" is the part that is easy to drop. A full page may have cut a revision in half — several
    rows can share one — so the cursor stays on that revision and the remainder arrives next tick.
    """

    revision: int
    payload: T


async def revision_stream[T](
    sessions: async_sessionmaker[AsyncSession],
    actor: Actor,
    *,
    fetch: Callable[[AsyncSession, int], Awaitable[Sequence[RevisionBatch[T]]]],
    latest_revision: Callable[[AsyncSession], Awaitable[int]],
    cursor: int | None,
    is_disconnected: Callable[[], Awaitable[bool]],
    page: int,
    tick_seconds: float,
    heartbeat_seconds: float,
    max_seconds: float,
    closed_log_event: str,
) -> AsyncIterator[RevisionBatch[T] | None]:
    """Yield one event per change, and `None` as a heartbeat when nothing has happened.

    `is_disconnected` is injected rather than read off the request, so reconnect behaviour — the
    whole point of this module — is testable without an HTTP server standing in the way.

    `max_seconds` is passed in rather than read from a constant here, because each caller owns its
    own deadline and because a test that lowers one must be lowering the value the generator
    actually reads.
    """
    position = cursor
    last_sent = datetime.now(UTC)
    deadline = datetime.now(UTC) + timedelta(seconds=max_seconds)

    while datetime.now(UTC) < deadline and not await is_disconnected():
        async with sessions() as session:
            if not await still_signed_in(session, actor):
                logger.info(closed_log_event, extra={"reason": "session_revoked"})
                return
            if position is None:
                # A screen arriving without a cursor starts from *now*, not from the beginning of
                # time: it has just read the current state, and replaying everything since the
                # restaurant opened would redraw tonight from last March.
                position = await latest_revision(session) + 1
            found = list(await fetch(session, position))

        for event in found:
            last_sent = datetime.now(UTC)
            yield event

        if found:
            highest = max(event.revision for event in found)
            position = highest if len(found) == page else highest + 1

        if (datetime.now(UTC) - last_sent).total_seconds() >= heartbeat_seconds:
            last_sent = datetime.now(UTC)
            yield None

        await asyncio.sleep(tick_seconds)


async def still_signed_in(session: AsyncSession, actor: Actor) -> bool:
    """One indexed lookup per tick.

    A token minted before sessions carried an id (backlog-issues B4) has nothing to look up and
    falls back to the token's own expiry — which the handshake already checked, and which bounds
    such a stream at fifteen minutes rather than for ever.
    """
    if actor.session_id is None:
        return True
    return await UserSessionRepository(session).is_live(actor.session_id)
