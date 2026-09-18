"""Threads and the messages in them.

Four rules carry the module, and each is here rather than in a handler because each is the sort of
thing a second handler would get slightly differently.

**Participation is the access control.** A permission catalogue cannot say "this thread, not that
one". Every read goes through `ConversationRepository.get_for`, which is tenant scope and a
participant row in one query — a `get()` followed by a membership check is two places to forget the
second one.

**A direct thread between two people is one row, forever.** The canonical pair is computed here,
the database enforces it, and a race resolves to the winner rather than to an error: two people
tapping each other's name at the same moment must not end up with two threads and half the
conversation in each.

**A participant who has left keeps their messages.** Leaving writes a date; it does not delete a
row and it does not rewrite what was said. Rejoining clears the date on the same row, which the
unique constraint makes the only option and which is the right one — two rows would make "when did
you join" unanswerable.

**The revision is bumped once per transaction.** A message and anything else written beside it
share one, so the stream replays inclusively and applying an event twice changes nothing.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import ConversationType, MessagePriority
from app.core.errors import AppError, NotFoundError, PermissionDeniedError
from app.core.permissions import PermissionCode
from app.core.tenancy import TenantScope
from app.models.communication import Conversation, ConversationParticipant, Message
from app.repositories.communication import (
    ConversationRepository,
    InboxRow,
    MessageRepository,
    ParticipantRepository,
)
from app.repositories.employee import EmployeeRepository

logger = logging.getLogger(__name__)

# The types a client may create. `task` and `complaint` threads are made by the flows that own
# them; `announcement` is made by nothing in M11 (spec, Not in scope).
CREATABLE = (ConversationType.DIRECT, ConversationType.GROUP)


@dataclass(frozen=True, slots=True)
class ThreadPage:
    messages: Sequence[Message]
    next_before: uuid.UUID | None


class ConversationService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._conversations = ConversationRepository(session, scope)
        self._participants = ParticipantRepository(session, scope)
        self._messages = MessageRepository(session, scope)
        self._employees = EmployeeRepository(session, scope)

    # ------------------------------------------------------------------ threads

    async def create(
        self,
        actor: Actor,
        *,
        type_: ConversationType,
        title: str | None,
        participant_ids: Sequence[uuid.UUID],
    ) -> tuple[Conversation, bool]:
        """Returns the thread and whether it already existed.

        The second half of that tuple is why `POST /conversations` can answer 200: a direct thread
        that already exists is not a conflict, it is the answer.
        """
        me = self._me(actor)
        if type_ not in CREATABLE:
            raise AppError(
                "conversation.type_not_creatable",
                "That kind of conversation is created by the thing it belongs to.",
                status_code=422,
            )

        members = await self._verified_members(participant_ids, me)

        if type_ is ConversationType.DIRECT:
            return await self._direct(me, members)

        conversation = Conversation(
            restaurant_id=self.scope.restaurant_id,
            type=ConversationType.GROUP.value,
            title=title,
            created_by=me,
        )
        self.session.add(conversation)
        await self.session.flush()
        await self._join(conversation.id, members)
        logger.info(
            "conversation.created",
            extra={
                "restaurant_id": str(self.scope.restaurant_id),
                "conversation_id": str(conversation.id),
                "participants": len(members),
            },
        )
        return conversation, False

    async def _direct(self, me: uuid.UUID, members: set[uuid.UUID]) -> tuple[Conversation, bool]:
        others = members - {me}
        if len(others) != 1:
            raise AppError(
                "conversation.direct_needs_one_person",
                "A direct conversation is between two people.",
                status_code=422,
            )
        key = direct_key(me, next(iter(others)))

        existing = await self._conversations.by_direct_key(key)
        if existing is not None:
            # Somebody may have left this thread and be coming back to it. Rejoining is the same
            # row with its date cleared, which keeps every message they can already see.
            await self._join(existing.id, members)
            return existing, True

        conversation = Conversation(
            restaurant_id=self.scope.restaurant_id,
            type=ConversationType.DIRECT.value,
            title=None,
            created_by=me,
            direct_key=key,
        )
        # A savepoint, not the request's transaction. The loser of a race must undo its own insert
        # and nothing else — `session.rollback()` here would discard whatever the request had
        # already done, which is a far worse bug than the one it is handling.
        try:
            async with self.session.begin_nested():
                self.session.add(conversation)
                await self.session.flush()
        except IntegrityError:
            # Two taps at the same moment. The loser reads the winner's row rather than erroring,
            # because an inbox with two threads to the same person looks broken and an error here
            # would be about our plumbing rather than about anything the person did.
            winner = await self._conversations.by_direct_key(key)
            if winner is None:  # pragma: no cover - the constraint fired, so a row exists
                raise
            await self._join(winner.id, members)
            return winner, True

        await self._join(conversation.id, members)
        return conversation, False

    async def get(self, actor: Actor, conversation_id: uuid.UUID) -> Conversation:
        conversation = await self._conversations.get_for(conversation_id, self._me(actor))
        if conversation is None:
            raise self._not_found()
        return conversation

    async def participants(self, conversation_id: uuid.UUID) -> Sequence[ConversationParticipant]:
        return await self._participants.listing(conversation_id)

    async def inbox(
        self,
        actor: Actor,
        *,
        unread_only: bool = False,
        limit: int | None = None,
        before: datetime | None = None,
    ) -> list[InboxRow]:
        return await self._conversations.inbox(
            self._me(actor), unread_only=unread_only, limit=limit, before=before
        )

    async def rename(self, actor: Actor, conversation_id: uuid.UUID, title: str | None) -> None:
        conversation = await self.get(actor, conversation_id)
        if conversation.type == ConversationType.DIRECT.value:
            raise AppError(
                "conversation.direct_has_no_title",
                "A conversation between two people is named after them.",
                status_code=422,
            )
        me = self._me(actor)
        if conversation.created_by != me and not actor.holds(PermissionCode.TASK_ASSIGN):
            raise PermissionDeniedError(
                "conversation.not_yours", "Only whoever started this group can rename it."
            )
        conversation.title = title
        await self.session.flush()

    async def mute(self, actor: Actor, conversation_id: uuid.UUID, muted: bool) -> None:
        """Muting is per person, which is why it lives on the participant row and not the thread."""
        await self.get(actor, conversation_id)
        participant = await self._participants.of(conversation_id, self._me(actor))
        if participant is None:  # pragma: no cover - `get` already proved membership
            raise self._not_found()
        participant.is_muted = muted
        await self.session.flush()

    async def add_participants(
        self, actor: Actor, conversation_id: uuid.UUID, employee_ids: Sequence[uuid.UUID]
    ) -> None:
        conversation = await self.get(actor, conversation_id)
        if conversation.type == ConversationType.DIRECT.value:
            raise AppError(
                "conversation.direct_is_closed",
                "A conversation between two people cannot take a third. Start a group.",
                status_code=422,
            )
        members = await self._verified_members(employee_ids, self._me(actor))
        await self._join(conversation_id, members - {self._me(actor)})

    async def remove_participant(
        self, actor: Actor, conversation_id: uuid.UUID, employee_id: uuid.UUID
    ) -> None:
        """Leaving is a fact with a date. Their messages stay, attributed to them, and the thread
        still says they were here — a thread whose membership changed mid-argument has to be
        readable afterwards."""
        conversation = await self.get(actor, conversation_id)
        me = self._me(actor)
        if employee_id != me and conversation.created_by != me:
            raise PermissionDeniedError(
                "conversation.cannot_remove",
                "Only whoever started this group can remove somebody from it.",
            )
        if conversation.type == ConversationType.DIRECT.value:
            raise AppError(
                "conversation.direct_cannot_be_left",
                "A conversation between two people cannot be left. Mute it instead.",
                status_code=422,
            )
        participant = await self._participants.of(conversation_id, employee_id)
        if participant is None or participant.left_at is not None:
            raise NotFoundError(
                "conversation.not_a_participant", "That person is not in this conversation."
            )
        participant.left_at = datetime.now(UTC)
        await self.session.flush()

    # ----------------------------------------------------------------- messages

    async def thread(
        self,
        actor: Actor,
        conversation_id: uuid.UUID,
        *,
        limit: int | None = None,
        before: uuid.UUID | None = None,
    ) -> ThreadPage:
        await self.get(actor, conversation_id)
        messages = list(await self._messages.page(conversation_id, limit=limit, before=before))
        next_before = messages[-1].id if messages else None
        return ThreadPage(messages=messages, next_before=next_before)

    async def send(
        self,
        actor: Actor,
        *,
        conversation_id: uuid.UUID,
        body: str | None,
        priority: MessagePriority,
        reply_to_message_id: uuid.UUID | None,
    ) -> Message:
        conversation = await self.get(actor, conversation_id)
        text = (body or "").strip() or None
        if text is None:
            # An attachment on its own is a message, but the attachment is created *against* a
            # message, so the first thing sent cannot be empty. A client with a file and no words
            # sends a single space; that is the frontend's problem and not a schema's.
            raise AppError("message.empty", "A message needs something in it.", status_code=422)
        if reply_to_message_id is not None:
            replied_to = await self._messages.get(reply_to_message_id)
            if replied_to is None or replied_to.conversation_id != conversation_id:
                raise NotFoundError(
                    "message.reply_not_found", "The message you are replying to is not here."
                )

        moment = datetime.now(UTC)
        message = Message(
            restaurant_id=self.scope.restaurant_id,
            conversation_id=conversation_id,
            sender_employee_id=self._me(actor),
            body=text,
            priority=priority.value,
            reply_to_message_id=reply_to_message_id,
            revision=await self._conversations.bump_revision(),
        )
        self.session.add(message)
        await self.session.flush()
        await self._conversations.touch(conversation.id, moment)
        # **No body, at any level, ever.** A message is unstructured and therefore unclassifiable,
        # so the only safe assumption is that it contains everything — a guest's phone number, a
        # supplier's price, somebody's medical reason for being off.
        logger.info(
            "message.sent",
            extra={
                "restaurant_id": str(self.scope.restaurant_id),
                "conversation_id": str(conversation_id),
                "message_id": str(message.id),
                "priority": priority.value,
            },
        )
        return message

    async def delete_message(self, actor: Actor, message_id: uuid.UUID) -> Message:
        """A tombstone: the row stays, the sender stays, the words do not.

        Nulling the body rather than keeping it is the point — "deleted" that a database
        administrator can still read is a lie told to the person who deleted it.
        """
        message = await self._messages.get(message_id)
        if message is None:
            raise NotFoundError("message.not_found", "That message could not be found.")
        me = self._me(actor)
        if message.sender_employee_id != me and not actor.holds(PermissionCode.TASK_ASSIGN):
            raise PermissionDeniedError(
                "message.not_yours", "You can only delete a message you sent."
            )
        if message.deleted_at is None:
            message.deleted_at = datetime.now(UTC)
            message.body = None
            message.revision = await self._conversations.bump_revision()
            await self.session.flush()
        return message

    async def mark_read(
        self, actor: Actor, conversation_id: uuid.UUID, last_read_message_id: uuid.UUID
    ) -> None:
        """Forward only. An older id is accepted and changes nothing — because two devices, and
        because "mark unread" is not a feature and a rewind would be its accidental
        implementation."""
        await self.get(actor, conversation_id)
        message = await self._messages.get(last_read_message_id)
        if message is None or message.conversation_id != conversation_id:
            raise NotFoundError(
                "message.not_in_conversation", "That message is not in this conversation."
            )
        participant = await self._participants.of(conversation_id, self._me(actor))
        if participant is None:  # pragma: no cover - `get` already proved membership
            raise self._not_found()
        current = participant.last_read_message_id
        if current is None or last_read_message_id > current:
            participant.last_read_message_id = last_read_message_id
            await self.session.flush()

    # ---------------------------------------------------------------- internals

    async def _verified_members(
        self, employee_ids: Sequence[uuid.UUID], me: uuid.UUID
    ) -> set[uuid.UUID]:
        """Everybody named, plus the actor, each confirmed to work at this restaurant.

        `get_assigned_here` rather than `get`: an employee with no role at this branch must not be
        addable to its conversations, and the wider lookup exists so a manager can see somebody
        they have just created.
        """
        members = {me}
        for employee_id in employee_ids:
            if employee_id == me:
                continue
            employee = await self._employees.get_assigned_here(employee_id)
            if employee is None or not employee.is_active:
                raise NotFoundError(
                    "conversation.person_not_found",
                    "One of those people does not work here.",
                )
            members.add(employee_id)
        return members

    async def _join(self, conversation_id: uuid.UUID, employee_ids: set[uuid.UUID]) -> None:
        moment = datetime.now(UTC)
        for employee_id in sorted(employee_ids, key=str):
            existing = await self._participants.of(conversation_id, employee_id)
            if existing is None:
                self.session.add(
                    ConversationParticipant(
                        restaurant_id=self.scope.restaurant_id,
                        conversation_id=conversation_id,
                        employee_id=employee_id,
                        joined_at=moment,
                    )
                )
            elif existing.left_at is not None:
                existing.left_at = None
        await self.session.flush()

    def _me(self, actor: Actor) -> uuid.UUID:
        """Named rather than inlined: `actor.employee_id` reads as "some employee", and every use
        of it here means *the person asking*."""
        return actor.employee_id

    def _not_found(self) -> NotFoundError:
        """One message for "no such thread" and "a thread you are not in". Telling them apart is
        how somebody maps what exists without being able to read it."""
        return NotFoundError("conversation.not_found", "That conversation could not be found.")


def direct_key(first: uuid.UUID, second: uuid.UUID) -> str:
    """The canonical pair, smaller id first, so the two people produce one key in either order."""
    low, high = sorted((str(first), str(second)))
    return f"{low}:{high}"


__all__ = ["CREATABLE", "ConversationService", "ThreadPage", "direct_key"]
