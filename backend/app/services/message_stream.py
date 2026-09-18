"""What `GET /messages/stream` yields.

The loop is `app/services/event_stream.py` — M08's, extracted when this module needed the same one.
What is here is the part that is communication-shaped, and three decisions worth reading:

**Two kinds of event, not three.** The spec sketched `message`, `task` and `unread`. `unread` is
gone, and its absence is the better design: a count pushed down a socket is a second source of
truth for something one indexed query already answers, and the two would drift the first time an
event was dropped or replayed. The client refetches the inbox when a message arrives, which is one
request against an index and always right.

**A tick is two seconds, not M08's half.** A kitchen display is a safety-critical two-metre read
and an inbox is not, and the database work is per open screen. Four times M08's interval, still
well inside "a message arrives while you are looking at the screen".

**Filtering happens in SQL, not afterwards.** The participant join is inside the query, so the page
limit is spent on rows the viewer is entitled to. Filtering in Python would let a busy thread the
viewer is not in starve them of their own messages — a correctness bug wearing a performance bug's
clothes.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.models.communication import Message, Task
from app.repositories.communication import (
    ConversationRepository,
    MessageRepository,
    TaskRepository,
)
from app.services.event_stream import RevisionBatch, revision_stream

logger = logging.getLogger(__name__)

# Two seconds. See the module docstring: an inbox is not a kitchen display.
TICK_SECONDS = 2.0
# Long enough that a quiet restaurant is quiet, short enough that a dead connection becomes obvious.
# Proxies also close idle connections, and this keeps them open.
HEARTBEAT_SECONDS = 20.0
# What the browser waits before reconnecting, in milliseconds. Server-controlled, so the backoff
# can be changed without shipping a frontend.
RETRY_MS = 5000
# How many rows one tick may carry, split between the two kinds. Bounded like every other query
# here; a backlog drains over the ticks that follow.
PAGE = 50
# Fifty-five minutes, just inside Cloud Run's sixty-minute request cap, so the server closes the
# response cleanly and the browser reconnects with its cursor rather than the platform killing a
# connection mid-event. It is also the backstop for `request.is_disconnected()`, which is not
# reliable on every transport — see `event_stream.py`.
MAX_SECONDS = 55 * 60


@dataclass(frozen=True, slots=True)
class CommEvent:
    """One whole object state, never a delta, so applying it twice changes nothing."""

    revision: int
    kind: str
    message: Message | None = None
    task: Task | None = None


async def communication_events(
    sessions: async_sessionmaker[AsyncSession],
    actor: Actor,
    *,
    cursor: int | None,
    is_disconnected: Callable[[], Awaitable[bool]],
    tick_seconds: float = TICK_SECONDS,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
    max_seconds: float | None = None,
) -> AsyncIterator[CommEvent | None]:
    """Yield an event per change this viewer may see, and `None` as a heartbeat otherwise."""
    employee_id = actor.employee_id
    # A `task.assign` holder watches the whole board; everybody else watches their own work.
    task_filter: uuid.UUID | None = None if actor.holds(PermissionCode.TASK_ASSIGN) else employee_id

    async def fetch(session: AsyncSession, position: int) -> list[RevisionBatch[CommEvent]]:
        messages = await MessageRepository(session, actor.scope).since_revision(
            position, employee_id=employee_id, limit=PAGE
        )
        tasks = await TaskRepository(session, actor.scope).since_revision(
            position, employee_id=task_filter, limit=PAGE
        )
        found = [
            RevisionBatch(
                revision=message.revision,
                payload=CommEvent(revision=message.revision, kind="message", message=message),
            )
            for message in messages
        ] + [
            RevisionBatch(
                revision=task.revision,
                payload=CommEvent(revision=task.revision, kind="task", task=task),
            )
            for task in tasks
        ]
        # One ordering across both kinds, so the cursor arithmetic in `event_stream` sees a single
        # monotonic sequence rather than two interleaved ones.
        found.sort(key=lambda batch: batch.revision)
        return found[:PAGE]

    async def latest(session: AsyncSession) -> int:
        return await ConversationRepository(session, actor.scope).current_revision()

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
        closed_log_event="messages.stream_closed",
    ):
        yield None if event is None else event.payload
