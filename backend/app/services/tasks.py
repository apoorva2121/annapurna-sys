"""Work with an owner, a due time, and a record nobody can quietly erase.

This is the half of M11 that WhatsApp cannot have, so it is the half worth getting exactly right.

**The transitions are a table, not scattered `if`s.** One place to read what may follow what, one
place to change it, and a refusal that names both states in words a person can act on. Scattered
conditions are how a lifecycle acquires a path nobody intended and nobody can find.

**Only the assignee completes.** Not the manager who asked for it, not a colleague being helpful —
because "the fryer was cleaned" asserted by the person who asked for it to be cleaned is not a
record of anything. The mirror rule: a `task.assign` holder may not verify work they completed
themselves unless they are the owner, which is M09's approver rule pointed at a different act.

**Reassignment writes an event.** A task that changed hands twice reads as a history rather than as
a current assignee, and "I never asked you to do that" has an answer a month later.

**Overdue is derived.** `due_at < now` and an unfinished status. Nothing flips a flag at midnight,
so there is no background job to fail quietly and no row whose meaning depends on one having run.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import TaskPriority, TaskStatus
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.permissions import OWNER_RANK, PermissionCode
from app.core.tenancy import TenantScope
from app.models.communication import Task, TaskEvent
from app.repositories.communication import (
    ConversationRepository,
    MessageRepository,
    TaskRepository,
)
from app.repositories.customers import ComplaintRepository
from app.repositories.employee import EmployeeRepository

logger = logging.getLogger(__name__)

# What may follow what. `cancelled` is reachable from everything unfinished; `verified` and
# `cancelled` are terminal.
TRANSITIONS: Mapping[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.CREATED: frozenset({TaskStatus.ASSIGNED, TaskStatus.CANCELLED}),
    TaskStatus.ASSIGNED: frozenset(
        {TaskStatus.ACCEPTED, TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}
    ),
    TaskStatus.ACCEPTED: frozenset(
        {TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED, TaskStatus.CANCELLED}
    ),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.COMPLETED, TaskStatus.CANCELLED}),
    # Completed work can be sent back. A verification that can only ever say yes is a rubber
    # stamp, and the one thing this module is for is the difference between the two.
    TaskStatus.COMPLETED: frozenset(
        {TaskStatus.VERIFIED, TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}
    ),
    TaskStatus.VERIFIED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

# The moves the assignee makes, and nobody else.
_ASSIGNEE_ONLY = frozenset({TaskStatus.ACCEPTED, TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED})

_WORDS: Mapping[TaskStatus, str] = {
    TaskStatus.CREATED: "waiting for somebody",
    TaskStatus.ASSIGNED: "assigned",
    TaskStatus.ACCEPTED: "accepted",
    TaskStatus.IN_PROGRESS: "in progress",
    TaskStatus.COMPLETED: "finished and waiting to be checked",
    TaskStatus.VERIFIED: "checked and closed",
    TaskStatus.CANCELLED: "cancelled",
}

_UNFINISHED = frozenset(
    {
        TaskStatus.CREATED,
        TaskStatus.ASSIGNED,
        TaskStatus.ACCEPTED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.COMPLETED,
    }
)


@dataclass(frozen=True, slots=True)
class TaskPage:
    items: Sequence[Task]
    next_after: uuid.UUID | None


def is_overdue(task: Task, *, now: datetime | None = None) -> bool:
    """Derived, never stored — which is why a due time passing changes no row."""
    if task.due_at is None or TaskStatus(task.status) not in _UNFINISHED:
        return False
    return task.due_at < (now or datetime.now(UTC))


class TaskService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._tasks = TaskRepository(session, scope)
        self._messages = MessageRepository(session, scope)
        self._conversations = ConversationRepository(session, scope)
        self._complaints = ComplaintRepository(session, scope)
        self._employees = EmployeeRepository(session, scope)

    # ------------------------------------------------------------------ writing

    async def create(
        self,
        actor: Actor,
        *,
        title: str,
        description: str | None = None,
        assigned_to: uuid.UUID | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        due_at: datetime | None = None,
        complaint_id: uuid.UUID | None = None,
        source_message_id: uuid.UUID | None = None,
    ) -> Task:
        """Writing down your own work needs `task.view`; giving it to somebody else needs
        `task.assign`. The P1 design's split, read literally, and the right line: a chef noting
        "deep-clean the fryer" is not the same act as a manager handing out work."""
        me = actor.employee_id
        if assigned_to is not None and assigned_to != me:
            self._require_assign(actor)
            await self._must_work_here(assigned_to)

        if complaint_id is not None and await self._complaints.get(complaint_id) is None:
            raise NotFoundError("task.complaint_not_found", "That complaint could not be found.")

        task = Task(
            restaurant_id=self.scope.restaurant_id,
            title=title,
            description=description,
            source_message_id=source_message_id,
            complaint_id=complaint_id,
            assigned_to=assigned_to,
            assigned_by=me,
            priority=priority.value,
            status=(
                TaskStatus.ASSIGNED.value if assigned_to is not None else TaskStatus.CREATED.value
            ),
            due_at=due_at,
            revision=await self._conversations.bump_revision(),
        )
        self.session.add(task)
        await self.session.flush()
        await self._record(
            task,
            actor,
            from_status=None,
            to_status=TaskStatus(task.status),
            note=None,
        )
        logger.info(
            "task.created",
            extra={
                "restaurant_id": str(self.scope.restaurant_id),
                "task_id": str(task.id),
                "assigned": assigned_to is not None,
                "priority": priority.value,
            },
        )
        return task

    async def promote(
        self,
        actor: Actor,
        message_id: uuid.UUID,
        *,
        title: str | None,
        assigned_to: uuid.UUID | None,
        priority: TaskPriority,
        due_at: datetime | None,
    ) -> Task:
        """A message becomes a task and keeps its parentage.

        Promotion is not a flag on the message — it is a task that points back, which is why
        promoting the same message twice is allowed: two people may genuinely owe two different
        pieces of work from one instruction.
        """
        message = await self._messages.get(message_id)
        if message is None or message.deleted_at is not None:
            raise NotFoundError("message.not_found", "That message could not be found.")
        # You must be able to see the thread to turn something in it into work.
        if await self._conversations.get_for(message.conversation_id, actor.employee_id) is None:
            raise PermissionDeniedError(
                "message.not_in_conversation",
                "That message is in a conversation you are not part of.",
            )
        body = (message.body or "").strip()
        return await self.create(
            actor,
            title=title or _first_line(body),
            description=body,
            assigned_to=assigned_to,
            priority=priority,
            due_at=due_at,
            source_message_id=message_id,
        )

    async def edit(
        self,
        actor: Actor,
        task_id: uuid.UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: TaskPriority | None = None,
        due_at: datetime | None = None,
    ) -> Task:
        task = await self._get(task_id)
        self._require_assign(actor)
        self._refuse_if_finished(task)
        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if priority is not None:
            task.priority = priority.value
        if due_at is not None:
            task.due_at = due_at
        task.revision = await self._conversations.bump_revision()
        await self.session.flush()
        return task

    async def assign(
        self, actor: Actor, task_id: uuid.UUID, *, employee_id: uuid.UUID | None, note: str | None
    ) -> Task:
        """Move a task to somebody else, or to nobody. Always an event, never an overwrite."""
        task = await self._get(task_id)
        self._require_assign(actor)
        self._refuse_if_finished(task)
        if task.assigned_to == employee_id:
            raise ConflictError("task.assignee_unchanged", "That person already has this task.")
        if employee_id is not None:
            await self._must_work_here(employee_id)

        previous = task.assigned_to
        task.assigned_to = employee_id
        task.status = (
            TaskStatus.ASSIGNED.value if employee_id is not None else TaskStatus.CREATED.value
        )
        task.revision = await self._conversations.bump_revision()
        await self.session.flush()
        await self._record(
            task,
            actor,
            from_status=None,
            to_status=None,
            note=_handover(previous, employee_id, note),
        )
        return task

    async def move(
        self, actor: Actor, task_id: uuid.UUID, *, to: TaskStatus, note: str | None
    ) -> Task:
        task = await self._get(task_id)
        current = TaskStatus(task.status)
        if to not in TRANSITIONS[current]:
            raise ConflictError(
                "task.transition_not_allowed",
                f"This task is {_WORDS[current]}, so it cannot be marked {_WORDS[to]}.",
                details={"from": current.value, "to": to.value},
            )
        self._may_move(actor, task, current, to)

        moment = datetime.now(UTC)
        task.status = to.value
        if to in (TaskStatus.COMPLETED, TaskStatus.VERIFIED):
            task.completed_at = task.completed_at or moment
        else:
            # Sending work back clears the completion, or the check constraint — and the history —
            # would say it was finished while it is being done again.
            task.completed_at = None
        if to is TaskStatus.VERIFIED:
            task.verified_at = moment
            task.verified_by = actor.employee_id
        else:
            task.verified_at = None
            task.verified_by = None
        task.revision = await self._conversations.bump_revision()
        await self.session.flush()
        await self._record(task, actor, from_status=current, to_status=to, note=note)
        logger.info(
            "task.moved",
            extra={
                "restaurant_id": str(self.scope.restaurant_id),
                "task_id": str(task.id),
                "from": current.value,
                "to": to.value,
            },
        )
        return task

    # ------------------------------------------------------------------ reading

    async def get(self, actor: Actor, task_id: uuid.UUID) -> Task:
        task = await self._get(task_id)
        self._may_read(actor, task)
        return task

    async def events(self, actor: Actor, task_id: uuid.UUID) -> Sequence[TaskEvent]:
        await self.get(actor, task_id)
        return await self._tasks.events(task_id)

    async def listing(
        self,
        actor: Actor,
        *,
        mine_only: bool = False,
        statuses: Sequence[str] | None = None,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> TaskPage:
        """Without `task.assign` you see your own work, whatever you asked for. The scope is not a
        filter a client can widen."""
        employee_id = (
            actor.employee_id if mine_only or not actor.holds(PermissionCode.TASK_ASSIGN) else None
        )
        items = list(
            await self._tasks.page(
                employee_id=employee_id, statuses=statuses, limit=limit, after=after
            )
        )
        return TaskPage(items=items, next_after=items[-1].id if items else None)

    # ---------------------------------------------------------------- internals

    async def _get(self, task_id: uuid.UUID) -> Task:
        task = await self._tasks.get(task_id)
        if task is None:
            raise NotFoundError("task.not_found", "That task could not be found.")
        return task

    def _may_read(self, actor: Actor, task: Task) -> None:
        if actor.holds(PermissionCode.TASK_ASSIGN):
            return
        if actor.employee_id in (task.assigned_to, task.assigned_by):
            return
        raise NotFoundError("task.not_found", "That task could not be found.")

    def _may_move(self, actor: Actor, task: Task, current: TaskStatus, to: TaskStatus) -> None:
        me = actor.employee_id
        # Sending completed work back to be done again is not the assignee restarting it — it is
        # somebody refusing to sign it off, which is the act `task.assign` exists for. Without the
        # `current` check this branch reads as "the assignee may resume", and the one person who
        # must not decide whether work passed would be the only person able to say it did not.
        if current is TaskStatus.COMPLETED and to is TaskStatus.IN_PROGRESS:
            self._require_assign(actor)
            return
        if to in _ASSIGNEE_ONLY:
            if task.assigned_to != me:
                raise PermissionDeniedError(
                    "task.not_yours",
                    "Only the person this task is assigned to can move it along.",
                )
            return
        if to is TaskStatus.VERIFIED:
            self._require_assign(actor)
            # M09's approver rule, pointed at a different act: the person who did the work is not
            # the person who says it was done. The owner is the exception, because a one-person
            # restaurant otherwise has no way to close anything.
            if task.assigned_to == me and actor.rank != OWNER_RANK:
                raise PermissionDeniedError(
                    "task.cannot_verify_own_work",
                    "Somebody else has to check work you finished yourself.",
                )
            return
        if to is TaskStatus.CANCELLED:
            if task.assigned_by == me or actor.holds(PermissionCode.TASK_ASSIGN):
                return
            raise PermissionDeniedError(
                "task.cannot_cancel", "Only whoever asked for this can cancel it."
            )
        # Sending completed work back to be done again.
        self._require_assign(actor)

    def _require_assign(self, actor: Actor) -> None:
        if not actor.holds(PermissionCode.TASK_ASSIGN):
            raise PermissionDeniedError(
                "task.not_permitted", "Only a manager can give work to somebody else."
            )

    def _refuse_if_finished(self, task: Task) -> None:
        status = TaskStatus(task.status)
        if status not in _UNFINISHED:
            raise ConflictError(
                "task.finished",
                f"This task is {_WORDS[status]} and cannot be changed.",
            )

    async def _must_work_here(self, employee_id: uuid.UUID) -> None:
        employee = await self._employees.get_assigned_here(employee_id)
        if employee is None or not employee.is_active:
            raise NotFoundError("task.person_not_found", "That person does not work here.")

    async def _record(
        self,
        task: Task,
        actor: Actor,
        *,
        from_status: TaskStatus | None,
        to_status: TaskStatus | None,
        note: str | None,
    ) -> None:
        self.session.add(
            TaskEvent(
                restaurant_id=self.scope.restaurant_id,
                task_id=task.id,
                actor_employee_id=actor.employee_id,
                from_status=None if from_status is None else from_status.value,
                to_status=None if to_status is None else to_status.value,
                note=note,
                occurred_at=datetime.now(UTC),
            )
        )
        await self.session.flush()


def _first_line(body: str) -> str:
    """A promoted message's first line becomes the title; the whole body stays as the description,
    so nothing said is lost to a truncation."""
    line = body.splitlines()[0].strip() if body else ""
    if not line:
        raise AppError(
            "task.title_required", "That message has no words to make a task from.", status_code=422
        )
    return line[:200]


def _handover(previous: uuid.UUID | None, current: uuid.UUID | None, note: str | None) -> str:
    """From and to, in the event's own note, so a task that changed hands twice reads as a
    history rather than as a current assignee."""
    parts = [f"from {previous or 'nobody'} to {current or 'nobody'}"]
    if note:
        parts.append(note)
    return " — ".join(parts)
