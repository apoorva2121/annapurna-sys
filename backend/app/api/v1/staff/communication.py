"""Conversations, messages, the stream, and tasks. Authorise, call, shape — nothing else.

Two permissions carry the whole file, and the P1 design drew both lines:

- `message.send` — every role, cleaner included. It means "may take part in conversations at all".
  It does **not** open every thread: you read one because a participant row says so, which is the
  control a permission catalogue cannot express and a repository scope can.
- `task.view` / `task.complete` — every role, so anybody can write down their own work and finish
  what they were given. `task.assign` — owner and manager, for giving work to somebody else.

**`POST /conversations` can answer 200.** A direct thread that already exists is not a conflict, it
is the answer: an inbox with seven threads to the same person looks broken.

**`POST /messages` carries an `Idempotency-Key`** for the reason `POST /wastage` does — a phone on
a bad connection in a kitchen, and a thumb that taps send twice.

**Every write route commits; the service only flushes.** This codebase's convention.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import EventSourceResponse, JSONResponse
from fastapi.sse import ServerSentEvent

from app.api.deps import SessionDep, require_permission
from app.api.idempotency import begin_idempotent
from app.api.v1.staff.attachments import attachment_response
from app.core.actor import Actor
from app.core.db import SessionFactoryDep
from app.core.enums import (
    AttachmentOwnerType,
    ConversationType,
    MessagePriority,
    TaskPriority,
    TaskStatus,
)
from app.core.permissions import PermissionCode
from app.models.communication import (
    Attachment,
    Conversation,
    ConversationParticipant,
    Message,
    Task,
    TaskEvent,
)
from app.schemas.communication import (
    AddParticipantsRequest,
    ConversationCreateRequest,
    ConversationResponse,
    ConversationUpdateRequest,
    InboxEntryResponse,
    InboxResponse,
    MessageCreateRequest,
    MessageListResponse,
    MessageResponse,
    ParticipantResponse,
    ReadRequest,
    TaskAssignRequest,
    TaskCreateRequest,
    TaskDetailResponse,
    TaskEventResponse,
    TaskListResponse,
    TaskPromoteRequest,
    TaskResponse,
    TaskStatusRequest,
    TaskUpdateRequest,
)
from app.services.attachments import attachments_for
from app.services.conversations import ConversationService
from app.services.message_stream import RETRY_MS, communication_events
from app.services.people import Person, people
from app.services.tasks import TaskService, is_overdue

router = APIRouter(tags=["communication"])

_TALK = Annotated[Actor, Depends(require_permission(PermissionCode.MESSAGE_SEND))]
_TASKS = Annotated[Actor, Depends(require_permission(PermissionCode.TASK_VIEW))]
_ASSIGN = Annotated[Actor, Depends(require_permission(PermissionCode.TASK_ASSIGN))]
_COMPLETE = Annotated[Actor, Depends(require_permission(PermissionCode.TASK_COMPLETE))]


def _conversations(session: SessionDep, actor: Actor) -> ConversationService:
    """The scope comes from the *actor*, never from the request (`docs/security.md` A04)."""
    return ConversationService(session, actor.scope)


def _tasks(session: SessionDep, actor: Actor) -> TaskService:
    return TaskService(session, actor.scope)


# ------------------------------------------------------------------- conversations


@router.get("/conversations", response_model=InboxResponse)
async def inbox(
    session: SessionDep,
    actor: _TALK,
    unread_only: Annotated[bool, Query()] = False,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    before: Annotated[datetime | None, Query()] = None,
) -> InboxResponse:
    """Every thread this person is in, newest first, with its unread count.

    One statement for any number of conversations — the inbox is the first screen anybody opens,
    and a per-row unread count would be an N+1 on the module's most-used query.
    """
    rows = await _conversations(session, actor).inbox(
        actor, unread_only=unread_only, limit=limit, before=before
    )
    items = [
        InboxEntryResponse(
            id=row.conversation.id,
            type=ConversationType(row.conversation.type),
            title=row.conversation.title,
            last_message_at=row.conversation.last_message_at,
            unread=row.unread,
            has_urgent_unread=row.has_urgent_unread,
            is_muted=row.is_muted,
        )
        for row in rows
    ]
    return InboxResponse(items=items, next_before=items[-1].last_message_at if items else None)


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    payload: ConversationCreateRequest, session: SessionDep, actor: _TALK
) -> Response:
    """201 for a new thread, **200 for a direct one that already existed** — which is not a
    conflict, it is the answer."""
    service = _conversations(session, actor)
    conversation, existed = await service.create(
        actor,
        type_=payload.type,
        title=payload.title,
        participant_ids=payload.participant_ids,
    )
    body = await _conversation_body(session, actor, service, conversation)
    await session.commit()
    return JSONResponse(
        content=body.model_dump(mode="json"),
        status_code=status.HTTP_200_OK if existed else status.HTTP_201_CREATED,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def read_conversation(
    conversation_id: uuid.UUID, session: SessionDep, actor: _TALK
) -> ConversationResponse:
    service = _conversations(session, actor)
    conversation = await service.get(actor, conversation_id)
    return await _conversation_body(session, actor, service, conversation)


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdateRequest,
    session: SessionDep,
    actor: _TALK,
) -> ConversationResponse:
    """A title belongs to the group; muting belongs to the person, which is why it lives on the
    participant row."""
    service = _conversations(session, actor)
    if payload.title is not None:
        await service.rename(actor, conversation_id, payload.title)
    if payload.is_muted is not None:
        await service.mute(actor, conversation_id, payload.is_muted)
    conversation = await service.get(actor, conversation_id)
    body = await _conversation_body(session, actor, service, conversation)
    await session.commit()
    return body


@router.post("/conversations/{conversation_id}/participants", response_model=ConversationResponse)
async def add_participants(
    conversation_id: uuid.UUID,
    payload: AddParticipantsRequest,
    session: SessionDep,
    actor: _TALK,
) -> ConversationResponse:
    service = _conversations(session, actor)
    await service.add_participants(actor, conversation_id, payload.employee_ids)
    conversation = await service.get(actor, conversation_id)
    body = await _conversation_body(session, actor, service, conversation)
    await session.commit()
    return body


@router.delete(
    "/conversations/{conversation_id}/participants/{employee_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_participant(
    conversation_id: uuid.UUID, employee_id: uuid.UUID, session: SessionDep, actor: _TALK
) -> Response:
    """Leaving is a fact with a date. Their messages stay, attributed to them."""
    await _conversations(session, actor).remove_participant(actor, conversation_id, employee_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/conversations/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    conversation_id: uuid.UUID, payload: ReadRequest, session: SessionDep, actor: _TALK
) -> Response:
    """Forward only. An older id is accepted and changes nothing."""
    await _conversations(session, actor).mark_read(
        actor, conversation_id, payload.last_read_message_id
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
async def read_thread(
    conversation_id: uuid.UUID,
    session: SessionDep,
    actor: _TALK,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    before: Annotated[uuid.UUID | None, Query()] = None,
) -> MessageListResponse:
    page = await _conversations(session, actor).thread(
        actor, conversation_id, limit=limit, before=before
    )
    return MessageListResponse(
        items=await _messages(session, actor, page.messages),
        next_before=page.next_before,
    )


# ----------------------------------------------------------------------- messages


@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    payload: MessageCreateRequest, request: Request, session: SessionDep, actor: _TALK
) -> MessageResponse | JSONResponse:
    """Idempotent (ADR 0010): a second tap on a stalled connection replays the first message
    rather than posting it twice."""
    call = await begin_idempotent(request, session, actor)
    if call.replay is not None:
        return call.replay
    message = await _conversations(session, actor).send(
        actor,
        conversation_id=payload.conversation_id,
        body=payload.body,
        priority=payload.priority,
        reply_to_message_id=payload.reply_to_message_id,
    )
    response = (await _messages(session, actor, [message]))[0]
    await call.complete(status.HTTP_201_CREATED, response)
    await session.commit()
    return response


@router.delete("/messages/{message_id}", response_model=MessageResponse)
async def delete_message(
    message_id: uuid.UUID, session: SessionDep, actor: _TALK
) -> MessageResponse:
    """A tombstone: the row stays, the sender stays, the words do not."""
    message = await _conversations(session, actor).delete_message(actor, message_id)
    response = (await _messages(session, actor, [message]))[0]
    await session.commit()
    return response


@router.get("/messages/stream", response_class=EventSourceResponse)
async def stream(
    request: Request,
    sessions: SessionFactoryDep,
    actor: _TALK,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> AsyncIterator[ServerSentEvent]:
    """Messages and tasks this person may see, as they happen.

    `retry` is sent first and once: the browser's backoff is the server's to choose. A heartbeat is
    a *comment* rather than an event — the difference between "the connection is alive" and
    "something happened".
    """
    yield ServerSentEvent(comment="stream open", retry=RETRY_MS)

    async for event in communication_events(
        sessions, actor, cursor=_cursor(last_event_id), is_disconnected=request.is_disconnected
    ):
        if event is None:
            yield ServerSentEvent(comment="heartbeat")
        elif event.message is not None:
            yield ServerSentEvent(
                id=str(event.revision),
                event="message",
                # `raw_data`, not `data`: the latter JSON-encodes whatever it is given, so a
                # pre-serialised model would arrive as a quoted string the browser parses twice.
                raw_data=_message_row(event.message, {}, {}).model_dump_json(),
            )
        elif event.task is not None:
            yield ServerSentEvent(
                id=str(event.revision),
                event="task",
                raw_data=_task_row(event.task, {}, {}).model_dump_json(),
            )


def _cursor(last_event_id: str | None) -> int | None:
    """Client-supplied and therefore not trusted: anything that is not a non-negative integer is
    treated as "no cursor" rather than refused, because a browser reconnecting with a corrupted
    header should get today's messages rather than an error it cannot act on."""
    if last_event_id is None or not last_event_id.isdigit():
        return None
    return int(last_event_id)


# -------------------------------------------------------------------------- tasks


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    session: SessionDep,
    actor: _TASKS,
    mine_only: Annotated[bool, Query()] = False,
    status_in: Annotated[list[TaskStatus] | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    after: Annotated[uuid.UUID | None, Query()] = None,
) -> TaskListResponse:
    """Without `task.assign` the scope is your own work, whatever the query says."""
    page = await _tasks(session, actor).listing(
        actor,
        mine_only=mine_only,
        statuses=[value.value for value in status_in] if status_in else None,
        limit=limit,
        after=after,
    )
    return TaskListResponse(
        items=await _task_rows(session, actor, page.items), next_after=page.next_after
    )


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreateRequest, session: SessionDep, actor: _TASKS
) -> TaskResponse:
    """`task.view` to write down your own work; the service asks for `task.assign` the moment it
    is somebody else's."""
    task = await _tasks(session, actor).create(
        actor,
        title=payload.title,
        description=payload.description,
        assigned_to=payload.assigned_to,
        priority=payload.priority,
        due_at=payload.due_at,
        complaint_id=payload.complaint_id,
    )
    response = (await _task_rows(session, actor, [task]))[0]
    await session.commit()
    return response


@router.post(
    "/messages/{message_id}/promote",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def promote_message(
    message_id: uuid.UUID, payload: TaskPromoteRequest, session: SessionDep, actor: _TASKS
) -> TaskResponse:
    """The thing WhatsApp cannot do: an instruction becomes work with an owner and a record."""
    task = await _tasks(session, actor).promote(
        actor,
        message_id,
        title=payload.title,
        assigned_to=payload.assigned_to,
        priority=payload.priority,
        due_at=payload.due_at,
    )
    response = (await _task_rows(session, actor, [task]))[0]
    await session.commit()
    return response


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
async def read_task(task_id: uuid.UUID, session: SessionDep, actor: _TASKS) -> TaskDetailResponse:
    service = _tasks(session, actor)
    task = await service.get(actor, task_id)
    events = await service.events(actor, task_id)
    names = await people(session, actor.scope, [event.actor_employee_id for event in events])
    return TaskDetailResponse(
        task=(await _task_rows(session, actor, [task]))[0],
        events=[_event_row(event, names) for event in events],
    )


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID, payload: TaskUpdateRequest, session: SessionDep, actor: _ASSIGN
) -> TaskResponse:
    task = await _tasks(session, actor).edit(
        actor,
        task_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_at=payload.due_at,
    )
    response = (await _task_rows(session, actor, [task]))[0]
    await session.commit()
    return response


@router.post("/tasks/{task_id}/assign", response_model=TaskResponse)
async def assign_task(
    task_id: uuid.UUID, payload: TaskAssignRequest, session: SessionDep, actor: _ASSIGN
) -> TaskResponse:
    """Writes an event, never an overwrite: a task that changed hands twice reads as a history."""
    task = await _tasks(session, actor).assign(
        actor, task_id, employee_id=payload.assigned_to, note=payload.note
    )
    response = (await _task_rows(session, actor, [task]))[0]
    await session.commit()
    return response


@router.post("/tasks/{task_id}/status", response_model=TaskResponse)
async def move_task(
    task_id: uuid.UUID, payload: TaskStatusRequest, session: SessionDep, actor: _COMPLETE
) -> TaskResponse:
    """The transition table decides what may follow what; the service decides who may say so."""
    task = await _tasks(session, actor).move(actor, task_id, to=payload.status, note=payload.note)
    response = (await _task_rows(session, actor, [task]))[0]
    await session.commit()
    return response


# ------------------------------------------------------------------------ shaping


async def _conversation_body(
    session: SessionDep,
    actor: Actor,
    service: ConversationService,
    conversation: Conversation,
) -> ConversationResponse:
    participants = await service.participants(conversation.id)
    names = await people(session, actor.scope, [row.employee_id for row in participants])
    return ConversationResponse(
        id=conversation.id,
        type=ConversationType(conversation.type),
        title=conversation.title,
        ref_type=conversation.ref_type,
        ref_id=conversation.ref_id,
        created_by=conversation.created_by,
        last_message_at=conversation.last_message_at,
        participants=[_participant_row(row, names) for row in participants],
    )


def _participant_row(
    participant: ConversationParticipant, names: dict[uuid.UUID, Person]
) -> ParticipantResponse:
    person = names.get(participant.employee_id)
    return ParticipantResponse(
        employee_id=participant.employee_id,
        full_name=person.full_name if person else "",
        joined_at=participant.joined_at,
        left_at=participant.left_at,
    )


async def _messages(
    session: SessionDep, actor: Actor, messages: Sequence[Message]
) -> list[MessageResponse]:
    """Names and attachments for a whole page in two queries, not two per row."""
    names = await people(session, actor.scope, [row.sender_employee_id for row in messages])
    attachments = await attachments_for(
        session, actor.scope, AttachmentOwnerType.MESSAGE.value, [row.id for row in messages]
    )
    return [_message_row(row, names, attachments) for row in messages]


def _message_row(
    message: Message,
    names: dict[uuid.UUID, Person],
    attachments: dict[uuid.UUID, list[Attachment]],
) -> MessageResponse:
    person = names.get(message.sender_employee_id)
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_employee_id=message.sender_employee_id,
        sender_name=person.full_name if person else None,
        body=message.body,
        priority=MessagePriority(message.priority),
        reply_to_message_id=message.reply_to_message_id,
        is_deleted=message.deleted_at is not None,
        attachments=[attachment_response(row) for row in attachments.get(message.id, [])],
        created_at=message.created_at,
    )


async def _task_rows(
    session: SessionDep, actor: Actor, tasks: Sequence[Task]
) -> list[TaskResponse]:
    names = await people(session, actor.scope, [row.assigned_to for row in tasks])
    attachments = await attachments_for(
        session, actor.scope, AttachmentOwnerType.TASK.value, [row.id for row in tasks]
    )
    return [_task_row(row, names, attachments) for row in tasks]


def _task_row(
    task: Task,
    names: dict[uuid.UUID, Person],
    attachments: dict[uuid.UUID, list[Attachment]],
) -> TaskResponse:
    person = names.get(task.assigned_to) if task.assigned_to else None
    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        source_message_id=task.source_message_id,
        complaint_id=task.complaint_id,
        assigned_to=task.assigned_to,
        assigned_to_name=person.full_name if person else None,
        assigned_by=task.assigned_by,
        priority=TaskPriority(task.priority),
        status=TaskStatus(task.status),
        due_at=task.due_at,
        is_overdue=is_overdue(task),
        completed_at=task.completed_at,
        verified_at=task.verified_at,
        verified_by=task.verified_by,
        attachments=[attachment_response(row) for row in attachments.get(task.id, [])],
        created_at=task.created_at,
    )


def _event_row(event: TaskEvent, names: dict[uuid.UUID, Person]) -> TaskEventResponse:
    person = names.get(event.actor_employee_id)
    return TaskEventResponse(
        id=event.id,
        actor_employee_id=event.actor_employee_id,
        actor_name=person.full_name if person else None,
        from_status=TaskStatus(event.from_status) if event.from_status else None,
        to_status=TaskStatus(event.to_status) if event.to_status else None,
        note=event.note,
        occurred_at=event.occurred_at,
    )
