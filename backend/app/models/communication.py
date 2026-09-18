"""Conversations, messages, tasks and attachments — `docs/schema.md` §10, migration 0041.

Argued in `docs/modules/M11-communication-spec.md`. Five things here are load-bearing:

**1 · Unread is a watermark, never a receipt.** `conversation_participant.last_read_message_id`
is one column against what `docs/schema.md` calls out as the alternative that "would be the largest
table in the schema — participants x messages". The unread count is one comparison, which is why
`ix_message_conversation_id` orders by `id` rather than by `created_at`: uuid7 is time-ordered, so
the same index serves paging *and* "how many since this one".

**2 · A direct conversation is one row, forever, and the database is what guarantees it.** The pair
lives in `conversation_participant`, where no expression index on `conversation` can see it — so
the canonical pair is denormalised into `conversation.direct_key` and a partial unique index makes
two simultaneous taps resolve to one thread instead of two.

**3 · Deletion leaves a tombstone.** `message.deleted_at` is ADR 0008's single soft-delete
exception, and the check constraint enforces the half that is easy to forget: a deleted message has
no body. "Deleted" that a database administrator can still read is a lie told to the person who
deleted it.

**4 · The stream has its own counter, for the reason M08's does.** `comm_stream_cursor` is
`kot_stream_cursor`'s shape, deliberately a second table rather than a shared one: a Postgres
sequence is global and a global cursor handed to a client leaks how busy every other tenant is.
What M11 *does* share with M08 is the polling loop, extracted to `app/services/event_stream.py` —
the machinery, not the counter.

**5 · A `pending` attachment is a claim and nothing more.** With the S3 driver the bytes never pass
through this application, so `size_bytes` and `mime_type` on a `pending` row are what a client
said. `READY` means the store itself was asked. The partial index on `pending` is what the sweep
reads.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    AttachmentOwnerType,
    AttachmentStatus,
    ConversationType,
    MessagePriority,
    TaskPriority,
    TaskStatus,
)
from app.models.base import Base, TimestampedUUIDMixin


def _uuid() -> Any:
    return postgresql.UUID(as_uuid=True)


def _values(members: Any) -> str:
    return ", ".join(f"'{member.value}'" for member in members)


class CommStreamCursor(Base):
    """One row per restaurant: the counter `GET /messages/stream` replays against.

    `kot_stream_cursor`'s twin, and the duplication is the point — see this module's docstring.
    Bumped once per transaction, so a message and the task it was promoted into share a revision
    and the stream replays *inclusively*.
    """

    __tablename__ = "comm_stream_cursor"
    __table_args__ = (CheckConstraint("last_revision >= 0", name="ck_comm_stream_cursor_revision"),)

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), primary_key=True
    )
    last_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Conversation(TimestampedUUIDMixin, Base):
    """A thread. `last_message_at` is denormalised because it is what the inbox sorts by."""

    __tablename__ = "conversation"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_conversation_id_restaurant"),
        CheckConstraint(
            f"type IN ({_values(ConversationType)})",
            name="ck_conversation_type",
        ),
        # A thread attached to something carries both halves or neither. Half a reference is a
        # row nothing can resolve and nothing will ever notice.
        CheckConstraint(
            "(ref_type IS NULL) = (ref_id IS NULL)",
            name="ck_conversation_ref_both_or_neither",
        ),
        CheckConstraint(
            "ref_type IS NULL OR ref_type IN ('task', 'complaint')",
            name="ck_conversation_ref_type",
        ),
        # Decision 3: the canonical pair, present exactly when the thread is a direct one.
        CheckConstraint(
            "(type = 'direct') = (direct_key IS NOT NULL)",
            name="ck_conversation_direct_key",
        ),
        Index(
            "uq_conversation_direct_pair",
            "restaurant_id",
            "direct_key",
            unique=True,
            postgresql_where=text("direct_key IS NOT NULL"),
        ),
        Index(
            "ix_conversation_restaurant_recent",
            "restaurant_id",
            text("last_message_at DESC"),
        ),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    # Attaches a thread to the thing it is about. No foreign key: two different targets in one
    # column cannot have one, and the resolution is a read-time lookup through the owning
    # repository, which is also where tenant scope is applied.
    ref_type: Mapped[str | None] = mapped_column(Text)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    created_by: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # '<smaller employee id>:<larger employee id>'. Written by the service, never by a client.
    direct_key: Mapped[str | None] = mapped_column(Text)


class Message(TimestampedUUIDMixin, Base):
    """One message. `body` is nullable because an attachment on its own is a message."""

    __tablename__ = "message"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_message_id_restaurant"),
        ForeignKeyConstraint(
            ["conversation_id", "restaurant_id"],
            ["conversation.id", "conversation.restaurant_id"],
            name="fk_message_conversation",
        ),
        CheckConstraint(
            f"priority IN ({_values(MessagePriority)})",
            name="ck_message_priority",
        ),
        # The tombstone's other half. Enforced here rather than trusted to the one service method
        # that deletes, because "deleted but still readable in the database" is the failure nobody
        # would ever see.
        CheckConstraint(
            "deleted_at IS NULL OR body IS NULL",
            name="ck_message_deleted_has_no_body",
        ),
        CheckConstraint("revision >= 1", name="ck_message_revision"),
        # By id, not by created_at: uuid7 is time-ordered, so this index pages the thread *and*
        # answers "how many since the watermark" without a second one.
        Index("ix_message_conversation_id", "conversation_id", text("id DESC")),
        Index("ix_message_restaurant_revision", "restaurant_id", "revision"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    sender_employee_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    body: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(
        Text, nullable=False, default=MessagePriority.NORMAL.value
    )
    reply_to_message_id: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("message.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ConversationParticipant(TimestampedUUIDMixin, Base):
    """Who is in a thread, since when, and how far they have read.

    Created after `message` so `last_read_message_id` needs no deferred constraint — the circular
    dependency `docs/schema.md` warns about only exists if the tables are created in the other
    order.
    """

    __tablename__ = "conversation_participant"
    __table_args__ = (
        UniqueConstraint("conversation_id", "employee_id", name="uq_conversation_participant_pair"),
        ForeignKeyConstraint(
            ["conversation_id", "restaurant_id"],
            ["conversation.id", "conversation.restaurant_id"],
            name="fk_conversation_participant_conversation",
        ),
        ForeignKeyConstraint(
            ["last_read_message_id", "restaurant_id"],
            ["message.id", "message.restaurant_id"],
            name="fk_conversation_participant_watermark",
        ),
        CheckConstraint(
            "left_at IS NULL OR left_at >= joined_at",
            name="ck_conversation_participant_left_after_joined",
        ),
        Index("ix_conversation_participant_employee", "employee_id", "conversation_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # A fact with a date, not a deletion (spec decision 4). Their messages stay attributed, the
    # thread still renders "Priya left, 14 Sep", and rejoining clears this rather than inserting
    # a second row — which the unique constraint makes the only option, and the right one.
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_read_message_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    is_muted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Task(TimestampedUUIDMixin, Base):
    """A piece of work with an owner and a lifecycle. Overdue is derived, never stored."""

    __tablename__ = "task"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_task_id_restaurant"),
        ForeignKeyConstraint(
            ["source_message_id", "restaurant_id"],
            ["message.id", "message.restaurant_id"],
            name="fk_task_source_message",
        ),
        ForeignKeyConstraint(
            ["complaint_id", "restaurant_id"],
            ["complaint.id", "complaint.restaurant_id"],
            name="fk_task_complaint",
        ),
        CheckConstraint(f"status IN ({_values(TaskStatus)})", name="ck_task_status"),
        CheckConstraint(f"priority IN ({_values(TaskPriority)})", name="ck_task_priority"),
        # A finished task knows when it finished. The pair of constraints below is what stops a
        # status moving without its timestamp, which is how a history stops being one.
        CheckConstraint(
            "(status IN ('completed', 'verified')) = (completed_at IS NOT NULL)",
            name="ck_task_completed_at",
        ),
        CheckConstraint(
            "(status = 'verified') = (verified_at IS NOT NULL AND verified_by IS NOT NULL)",
            name="ck_task_verified",
        ),
        CheckConstraint("revision >= 1", name="ck_task_revision"),
        Index("ix_task_restaurant_assignee", "restaurant_id", "assigned_to", "status"),
        Index(
            "ix_task_restaurant_due",
            "restaurant_id",
            "due_at",
            postgresql_where=text("status <> 'verified'"),
        ),
        Index("ix_task_restaurant_revision", "restaurant_id", "revision"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Where it came from. Promotion is not a flag on the message — it is a task that points back,
    # which is why promoting the same message twice is legal and produces two tasks.
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    priority: Mapped[str] = mapped_column(Text, nullable=False, default=TaskPriority.NORMAL.value)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=TaskStatus.CREATED.value)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)


class TaskEvent(TimestampedUUIDMixin, Base):
    """Append-only. One row per transition, reassignment included.

    A task that changed hands twice reads as a history rather than as a current assignee, and that
    is the whole reason a manager's "I never asked you to do that" has an answer.
    """

    __tablename__ = "task_event"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "restaurant_id"],
            ["task.id", "task.restaurant_id"],
            name="fk_task_event_task",
        ),
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_values(TaskStatus)})",
            name="ck_task_event_from_status",
        ),
        CheckConstraint(
            f"to_status IS NULL OR to_status IN ({_values(TaskStatus)})",
            name="ck_task_event_to_status",
        ),
        Index("ix_task_event_task", "task_id", "occurred_at"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    actor_employee_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    # Both nullable: a reassignment moves nobody between statuses, and its note carries from and to.
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Attachment(TimestampedUUIDMixin, Base):
    """One table, six owners. The owner decides who may attach (spec decision 6)."""

    __tablename__ = "attachment"
    __table_args__ = (
        CheckConstraint(
            f"owner_type IN ({_values(AttachmentOwnerType)})",
            name="ck_attachment_owner_type",
        ),
        CheckConstraint(
            f"status IN ({_values(AttachmentStatus)})",
            name="ck_attachment_status",
        ),
        CheckConstraint("size_bytes > 0", name="ck_attachment_size"),
        # The key is generated and the filename is decoration, so the key is what must be unique.
        UniqueConstraint("file_key", name="uq_attachment_file_key"),
        Index("ix_attachment_owner", "restaurant_id", "owner_type", "owner_id"),
        # What the sweep reads. Partial, because a healthy store has almost no pending rows and
        # a full index on a column that is 'ready' everywhere earns nothing.
        Index(
            "ix_attachment_pending",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    owner_type: Mapped[str] = mapped_column(Text, nullable=False)
    # No foreign key, for `conversation.ref_id`'s reason: six possible targets in one column. The
    # owner is resolved through its own repository, which is where tenant scope lives.
    owner_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    # `{restaurant_id}/{yyyy}/{mm}/{uuid7}{ext}` — generated, never derived from `file_name`, so an
    # uploaded '../../etc/passwd' is a display string and nothing else.
    file_key: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=AttachmentStatus.PENDING.value
    )
