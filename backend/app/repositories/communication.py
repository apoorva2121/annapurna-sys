"""Queries over conversations, messages, tasks and attachments. Business rules live in services.

Three of these carry weight.

**`inbox` answers unread for every conversation in one statement.** The inbox is the first screen
anybody opens, and an unread count computed per row would be an N+1 on the most-used query in the
module. The watermark makes it a `LEFT JOIN` and a `COUNT`, which is why
`conversation_participant.last_read_message_id` exists at all rather than a receipts table.

**Nothing here reads a conversation without a participant row.** Tenant scope is the outer
boundary and participation is the inner one, and the inner one is what a permission catalogue
cannot express. Every method that takes a conversation takes the employee too.

**`bump_revision` is `UPDATE ... RETURNING` on one row per restaurant**, called once per
transaction rather than once per row — `kitchen.py`'s shape, for the reason its docstring gives:
several rows can share a revision and the stream therefore replays *inclusively*.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, and_, func, or_, select, update

from app.models.communication import (
    Attachment,
    CommStreamCursor,
    Conversation,
    ConversationParticipant,
    Message,
    Task,
    TaskEvent,
)
from app.models.identity import Employee
from app.repositories.base import RestaurantScopedRepository, page_size


@dataclass(frozen=True, slots=True)
class InboxRow:
    """One line of the inbox: the thread, how many messages the viewer has not read, and whether
    any of them was urgent — because urgency sorts, and sorting cannot wait for the thread to be
    opened."""

    conversation: Conversation
    unread: int
    has_urgent_unread: bool
    is_muted: bool


class ConversationRepository(RestaurantScopedRepository[Conversation]):
    model = Conversation

    async def get_for(
        self, conversation_id: uuid.UUID, employee_id: uuid.UUID
    ) -> Conversation | None:
        """The thread, if this person is in it and has not left.

        Both halves in one query on purpose. A `get()` followed by a membership check is two places
        to forget the second one.
        """
        statement = (
            self.scoped()
            .join(
                ConversationParticipant,
                ConversationParticipant.conversation_id == Conversation.id,
            )
            .where(
                Conversation.id == conversation_id,
                ConversationParticipant.employee_id == employee_id,
                ConversationParticipant.left_at.is_(None),
            )
        )
        return (await self.session.scalars(statement)).first()

    async def by_direct_key(self, direct_key: str) -> Conversation | None:
        return (
            await self.session.scalars(self.scoped().where(Conversation.direct_key == direct_key))
        ).first()

    async def inbox(
        self,
        employee_id: uuid.UUID,
        *,
        unread_only: bool = False,
        limit: int | None = None,
        before: datetime | None = None,
    ) -> list[InboxRow]:
        """Every thread this person is in, newest first, with its unread count.

        One statement for any number of conversations. The correlated subqueries are bounded by
        `ix_message_conversation_id`, and the outer query by `ix_conversation_restaurant_recent`.
        """
        membership = ConversationParticipant
        watermark = membership.last_read_message_id

        # "Messages after my watermark, that I did not send, that are not deleted." A NULL
        # watermark means everything counts, which is what a new participant should see.
        unread_predicate = and_(
            Message.conversation_id == Conversation.id,
            Message.sender_employee_id != employee_id,
            Message.deleted_at.is_(None),
            or_(watermark.is_(None), Message.id > watermark),
        )
        unread = (
            select(func.count())
            .select_from(Message)
            .where(unread_predicate)
            .correlate(Conversation, membership)
            .scalar_subquery()
        )
        urgent = (
            select(func.count())
            .select_from(Message)
            .where(unread_predicate, Message.priority == "urgent")
            .correlate(Conversation, membership)
            .scalar_subquery()
        )

        statement: Select[tuple[Conversation, int, int, bool]] = (
            select(
                Conversation,
                unread.label("unread"),
                urgent.label("urgent"),
                membership.is_muted,
            )
            .join(membership, membership.conversation_id == Conversation.id)
            .where(
                Conversation.restaurant_id == self.scope.restaurant_id,
                membership.employee_id == employee_id,
                membership.left_at.is_(None),
            )
            .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.id.desc())
            .limit(page_size(limit))
        )
        if before is not None:
            statement = statement.where(Conversation.last_message_at < before)
        if unread_only:
            statement = statement.where(unread > 0)

        rows = (await self.session.execute(statement)).all()
        return [
            InboxRow(
                conversation=row[0],
                unread=int(row[1]),
                has_urgent_unread=int(row[2]) > 0,
                is_muted=bool(row[3]),
            )
            for row in rows
        ]

    async def touch(self, conversation_id: uuid.UUID, moment: datetime) -> None:
        """Move `last_message_at` forward. Never backwards — an out-of-order write would resort
        somebody's inbox behind their back."""
        await self.session.execute(
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.restaurant_id == self.scope.restaurant_id,
                or_(Conversation.last_message_at.is_(None), Conversation.last_message_at < moment),
            )
            .values(last_message_at=moment)
        )

    async def bump_revision(self) -> int:
        """The restaurant's next communication revision, allocated and returned in one statement.

        `KitchenRepository.bump_revision`'s twin. Called once per transaction, so a message and the
        task promoted from it share a revision and the stream replays inclusively.
        """
        revision = await self.session.scalar(
            update(CommStreamCursor)
            .where(CommStreamCursor.restaurant_id == self.scope.restaurant_id)
            .values(last_revision=CommStreamCursor.last_revision + 1)
            .returning(CommStreamCursor.last_revision)
        )
        if revision is not None:
            return int(revision)
        self.session.add(CommStreamCursor(restaurant_id=self.scope.restaurant_id, last_revision=1))
        await self.session.flush()
        return 1

    async def current_revision(self) -> int:
        revision = await self.session.scalar(
            select(CommStreamCursor.last_revision).where(
                CommStreamCursor.restaurant_id == self.scope.restaurant_id
            )
        )
        return int(revision or 0)


class ParticipantRepository(RestaurantScopedRepository[ConversationParticipant]):
    model = ConversationParticipant

    async def of(
        self, conversation_id: uuid.UUID, employee_id: uuid.UUID
    ) -> ConversationParticipant | None:
        """Including one who has left — callers that care check `left_at` themselves, because
        rejoining and "did they see it" both need the row."""
        statement = self.scoped().where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.employee_id == employee_id,
        )
        return (await self.session.scalars(statement)).first()

    async def listing(self, conversation_id: uuid.UUID) -> Sequence[ConversationParticipant]:
        statement = (
            self.scoped()
            .where(ConversationParticipant.conversation_id == conversation_id)
            .order_by(ConversationParticipant.joined_at)
        )
        return (await self.session.scalars(statement)).all()

    async def active_employee_ids(self, conversation_id: uuid.UUID) -> list[uuid.UUID]:
        statement = select(ConversationParticipant.employee_id).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.restaurant_id == self.scope.restaurant_id,
            ConversationParticipant.left_at.is_(None),
        )
        return list((await self.session.scalars(statement)).all())


class MessageRepository(RestaurantScopedRepository[Message]):
    model = Message

    async def page(
        self,
        conversation_id: uuid.UUID,
        *,
        limit: int | None = None,
        before: uuid.UUID | None = None,
    ) -> Sequence[Message]:
        """Newest first, keyed on the id — uuid7 is time-ordered, so this is both the sort and the
        cursor, on one index."""
        statement = (
            self.scoped()
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .limit(page_size(limit))
        )
        if before is not None:
            statement = statement.where(Message.id < before)
        return (await self.session.scalars(statement)).all()

    async def since_revision(self, revision: int, *, limit: int) -> Sequence[Message]:
        """At or after, not after: several rows can share a revision, and an exclusive cursor would
        permanently lose the rest of a batch whose first event arrived before a drop."""
        statement = (
            self.scoped()
            .where(Message.revision >= revision)
            .order_by(Message.revision, Message.id)
            .limit(limit)
        )
        return (await self.session.scalars(statement)).all()

    async def latest_id(self, conversation_id: uuid.UUID) -> uuid.UUID | None:
        found: uuid.UUID | None = await self.session.scalar(
            select(Message.id)
            .where(
                Message.conversation_id == conversation_id,
                Message.restaurant_id == self.scope.restaurant_id,
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        return found


class TaskRepository(RestaurantScopedRepository[Task]):
    model = Task

    async def page(
        self,
        *,
        employee_id: uuid.UUID | None = None,
        statuses: Sequence[str] | None = None,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[Task]:
        statement = self.scoped().order_by(Task.id.desc()).limit(page_size(limit))
        if employee_id is not None:
            # "Mine" is both directions: work I was given and work I wrote down for somebody.
            statement = statement.where(
                or_(Task.assigned_to == employee_id, Task.assigned_by == employee_id)
            )
        if statuses:
            statement = statement.where(Task.status.in_(list(statuses)))
        if after is not None:
            statement = statement.where(Task.id < after)
        return (await self.session.scalars(statement)).all()

    async def since_revision(self, revision: int, *, limit: int) -> Sequence[Task]:
        statement = (
            self.scoped()
            .where(Task.revision >= revision)
            .order_by(Task.revision, Task.id)
            .limit(limit)
        )
        return (await self.session.scalars(statement)).all()

    async def events(self, task_id: uuid.UUID) -> Sequence[TaskEvent]:
        statement = (
            select(TaskEvent)
            .where(
                TaskEvent.task_id == task_id,
                TaskEvent.restaurant_id == self.scope.restaurant_id,
            )
            .order_by(TaskEvent.occurred_at, TaskEvent.id)
        )
        return (await self.session.scalars(statement)).all()


class AttachmentRepository(RestaurantScopedRepository[Attachment]):
    model = Attachment

    async def for_owner(self, owner_type: str, owner_id: uuid.UUID) -> Sequence[Attachment]:
        statement = (
            self.scoped()
            .where(
                Attachment.owner_type == owner_type,
                Attachment.owner_id == owner_id,
                Attachment.status == "ready",
            )
            .order_by(Attachment.id)
        )
        return (await self.session.scalars(statement)).all()

    async def for_owners(
        self, owner_type: str, owner_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[Attachment]]:
        """Every attachment for a page of owners, in one query.

        The thread renders fifty messages; asking per message would be the module's second N+1
        after the inbox.
        """
        if not owner_ids:
            return {}
        statement = (
            self.scoped()
            .where(
                Attachment.owner_type == owner_type,
                Attachment.owner_id.in_(list(owner_ids)),
                Attachment.status == "ready",
            )
            .order_by(Attachment.id)
        )
        grouped: dict[uuid.UUID, list[Attachment]] = {}
        for attachment in (await self.session.scalars(statement)).all():
            grouped.setdefault(attachment.owner_id, []).append(attachment)
        return grouped

    async def stale_pending(
        self, *, older_than: datetime, limit: int = 200
    ) -> Sequence[Attachment]:
        """Rows that were begun and never confirmed. Deliberately **not** scoped to a restaurant:
        the sweep is a maintenance task run by the process, not by a person, and an orphan in
        another tenant is still an orphan paying for storage."""
        statement = (
            select(Attachment)
            .where(Attachment.status == "pending", Attachment.created_at < older_than)
            .order_by(Attachment.created_at)
            .limit(limit)
        )
        return (await self.session.scalars(statement)).all()


async def employee_names(
    repository: RestaurantScopedRepository[Attachment], ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Names for a page of people, in one query rather than one per row."""
    if not ids:
        return {}
    rows = await repository.session.execute(
        select(Employee.id, Employee.full_name).where(Employee.id.in_(list(ids)))
    )
    return {row[0]: row[1] for row in rows.all()}


def utcnow() -> datetime:
    return datetime.now(UTC)
