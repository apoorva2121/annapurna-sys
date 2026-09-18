"""The API contract for conversations, messages, tasks and attachments.

**Nothing here carries a storage key, a bucket name or a driver.** ADR 0005 says media URLs are
"pre-signed through a storage abstraction, never constructed from a provider-specific host"; a
client that learned the key would be constructing one. It gets an attachment id and asks.

**Nothing here carries a sender.** `sender_employee_id` comes from the actor on every write, so
posting as somebody else is not a permission check that could be forgotten — it is a field that
does not exist.

**`size_bytes` and `mime_type` on the way in are claims, and the contract says so.** They are what
a client believes about a file this process may never see. What decides the matter is
`POST /attachments/{id}/confirm`, which asks the store.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.core.enums import (
    AttachmentOwnerType,
    AttachmentStatus,
    ConversationType,
    MessagePriority,
    TaskPriority,
    TaskStatus,
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------- attachments


class AttachmentBeginRequest(_Schema):
    owner_type: AttachmentOwnerType
    owner_id: uuid.UUID
    file_name: str = Field(min_length=1, max_length=255)
    # Validated against the allow-list in `app/core/media.py`, not by a pattern here: the list is
    # a rule with reasons attached, and a regular expression in a schema is a rule with none.
    mime_type: str = Field(min_length=3, max_length=100)
    size_bytes: int = Field(gt=0)


class UploadInstructionResponse(_Schema):
    """Where to PUT the bytes. `headers` must be sent exactly — with the S3 driver the content
    type is part of what was signed, and a different one is a signature mismatch at the bucket."""

    method: str
    url: str
    headers: dict[str, str]
    expires_at: AwareDatetime


class AttachmentResponse(_Schema):
    id: uuid.UUID
    owner_type: AttachmentOwnerType
    owner_id: uuid.UUID
    file_name: str
    mime_type: str
    size_bytes: int
    status: AttachmentStatus
    uploaded_by: uuid.UUID
    uploaded_by_name: str | None = None
    created_at: datetime


class AttachmentBegunResponse(_Schema):
    attachment: AttachmentResponse
    upload: UploadInstructionResponse


# --------------------------------------------------------------------- conversations


class ConversationCreateRequest(_Schema):
    # `announcement` is absent on purpose: nothing in M11 creates one (spec, Not in scope).
    type: ConversationType = ConversationType.GROUP
    title: str | None = Field(default=None, max_length=120)
    participant_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class ConversationUpdateRequest(_Schema):
    title: str | None = Field(default=None, max_length=120)
    is_muted: bool | None = None


class ParticipantResponse(_Schema):
    employee_id: uuid.UUID
    full_name: str
    joined_at: datetime
    left_at: datetime | None


class ConversationResponse(_Schema):
    id: uuid.UUID
    type: ConversationType
    title: str | None
    ref_type: str | None
    ref_id: uuid.UUID | None
    created_by: uuid.UUID
    last_message_at: datetime | None
    participants: list[ParticipantResponse]


class InboxEntryResponse(_Schema):
    id: uuid.UUID
    type: ConversationType
    title: str | None
    last_message_at: datetime | None
    unread: int
    has_urgent_unread: bool
    is_muted: bool


class InboxResponse(_Schema):
    items: list[InboxEntryResponse]
    next_before: datetime | None


class AddParticipantsRequest(_Schema):
    employee_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class ReadRequest(_Schema):
    """Forward only. An older id is accepted and changes nothing, because two devices — and
    because "mark unread" is not a feature and a rewind would be its accidental implementation."""

    last_read_message_id: uuid.UUID


# ------------------------------------------------------------------------- messages


class MessageCreateRequest(_Schema):
    conversation_id: uuid.UUID
    # Nullable because an attachment on its own is a message. Both empty is refused in the service,
    # where the attachment is visible.
    body: str | None = Field(default=None, max_length=4000)
    priority: MessagePriority = MessagePriority.NORMAL
    reply_to_message_id: uuid.UUID | None = None


class MessageResponse(_Schema):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_employee_id: uuid.UUID
    sender_name: str | None
    body: str | None
    priority: MessagePriority
    reply_to_message_id: uuid.UUID | None
    # A tombstone renders as a tombstone: the row, the sender, the moment, and no words.
    is_deleted: bool
    attachments: list[AttachmentResponse]
    created_at: datetime


class MessageListResponse(_Schema):
    items: list[MessageResponse]
    next_before: uuid.UUID | None


# ---------------------------------------------------------------------------- tasks


class TaskCreateRequest(_Schema):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    assigned_to: uuid.UUID | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    due_at: AwareDatetime | None = None
    complaint_id: uuid.UUID | None = None


class TaskUpdateRequest(_Schema):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    priority: TaskPriority | None = None
    due_at: AwareDatetime | None = None


class TaskAssignRequest(_Schema):
    """`None` un-assigns. A reason is not required to give somebody work; it is required to take
    it away from them, which the service enforces."""

    assigned_to: uuid.UUID | None
    note: str | None = Field(default=None, max_length=500)


class TaskStatusRequest(_Schema):
    status: TaskStatus
    note: str | None = Field(default=None, max_length=500)


class TaskPromoteRequest(_Schema):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    assigned_to: uuid.UUID | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    due_at: AwareDatetime | None = None


class TaskEventResponse(_Schema):
    id: uuid.UUID
    actor_employee_id: uuid.UUID
    actor_name: str | None
    from_status: TaskStatus | None
    to_status: TaskStatus | None
    note: str | None
    occurred_at: datetime


class TaskResponse(_Schema):
    id: uuid.UUID
    title: str
    description: str | None
    source_message_id: uuid.UUID | None
    complaint_id: uuid.UUID | None
    assigned_to: uuid.UUID | None
    assigned_to_name: str | None
    assigned_by: uuid.UUID | None
    priority: TaskPriority
    status: TaskStatus
    due_at: datetime | None
    # Derived, never stored: no row changes when a due time passes.
    is_overdue: bool
    completed_at: datetime | None
    verified_at: datetime | None
    verified_by: uuid.UUID | None
    attachments: list[AttachmentResponse]
    created_at: datetime


class TaskDetailResponse(_Schema):
    task: TaskResponse
    events: list[TaskEventResponse]


class TaskListResponse(_Schema):
    items: list[TaskResponse]
    next_after: uuid.UUID | None
