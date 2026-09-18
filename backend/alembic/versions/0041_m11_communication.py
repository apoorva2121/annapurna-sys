"""m11 - conversations, messages, tasks, attachments, and the stream's counter

Seven tables: the six from `docs/schema.md` §10 plus `comm_stream_cursor`. Argued in
`docs/modules/M11-communication-spec.md`.

Four things are deliberate.

**1. The circular foreign key `docs/schema.md` warns about does not exist here.** §"Migration
order" says `conversation_participant.last_read_message_id` "is circular against later steps - add
as a nullable FK in a follow-up migration". It is circular only if the participant table is created
before `message`. Created in the order conversation -> message -> participant, every constraint
resolves the first time and there is no follow-up to forget.

**2. `conversation.direct_key` is not in `docs/schema.md`, and it has to exist.** Decision 3 of the
spec: a direct thread between two people must be one row forever, and two simultaneous taps must
resolve to one thread rather than two. The pair lives in `conversation_participant`, which no
expression index on `conversation` can see, so the canonical pair - the two employee ids, smaller
first - is denormalised here and a partial unique index enforces it. §10 is updated in the same PR.

**3. `message.revision` and `task.revision` share one counter per restaurant.** M08's reasoning
(`kot_stream_cursor`) applies unchanged: a Postgres sequence is global, and a global cursor handed
to a client leaks how busy every other tenant is. A second table rather than a shared one, because
generalising the *counter* would mean rewriting an applied migration; what M11 and M08 share is the
polling loop, which moves to `app/services/event_stream.py`.

**4. Every child carries `restaurant_id` with a composite foreign key.** The house pattern since
M07: `(parent_id, restaurant_id)` referencing `(parent.id, parent.restaurant_id)`, so a row cannot
be parented across a tenant boundary even by a bug in a repository. `docs/schema.md` §10 lists
`conversation_participant` without the column; the table gets it, and §10 is updated to match,
because invariant 1 outranks a sketch.

Revision ID: 0041_m11_communication
Revises: 0040_m10_complaint_issues
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041_m11_communication"
down_revision: str | None = "0040_m10_complaint_issues"
branch_labels: str | None = None
depends_on: str | None = None

# `docs/schema.md` §10. `announcement` is in the constraint because the schema declares it; nothing
# in M11 creates one (spec, Not in scope).
_CONVERSATION_TYPES = ("direct", "group", "task", "complaint", "announcement")
_MESSAGE_PRIORITIES = ("normal", "high", "urgent")
_TASK_PRIORITIES = ("low", "normal", "high", "urgent")
_TASK_STATUSES = (
    "created",
    "assigned",
    "accepted",
    "in_progress",
    "completed",
    "verified",
    "cancelled",
)
_ATTACHMENT_OWNER_TYPES = (
    "message",
    "task",
    "complaint",
    "wastage_event",
    "feedback",
    "goods_receipt",
)
_ATTACHMENT_STATUSES = ("pending", "ready")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def upgrade() -> None:
    # ------------------------------------------------------- comm_stream_cursor
    op.create_table(
        "comm_stream_cursor",
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            primary_key=True,
        ),
        sa.Column("last_revision", sa.BigInteger(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.CheckConstraint("last_revision >= 0", name="ck_comm_stream_cursor_revision"),
    )

    # ------------------------------------------------------------- conversation
    op.create_table(
        "conversation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        # Attaches a thread to the thing it is about. No foreign key: two possible targets in one
        # column cannot have one, and the resolution is a read through the owning repository.
        sa.Column("ref_type", sa.Text(), nullable=True),
        sa.Column("ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=False,
        ),
        # Denormalised because it is what the inbox sorts by, and the inbox is the first screen
        # anybody opens.
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("direct_key", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_conversation_id_restaurant"),
        sa.CheckConstraint(_in("type", _CONVERSATION_TYPES), name="ck_conversation_type"),
        sa.CheckConstraint(
            "(ref_type IS NULL) = (ref_id IS NULL)", name="ck_conversation_ref_both_or_neither"
        ),
        sa.CheckConstraint(
            "ref_type IS NULL OR ref_type IN ('task', 'complaint')", name="ck_conversation_ref_type"
        ),
        sa.CheckConstraint(
            "(type = 'direct') = (direct_key IS NOT NULL)", name="ck_conversation_direct_key"
        ),
    )
    op.create_index(
        "uq_conversation_direct_pair",
        "conversation",
        ["restaurant_id", "direct_key"],
        unique=True,
        postgresql_where=sa.text("direct_key IS NOT NULL"),
    )
    op.create_index(
        "ix_conversation_restaurant_recent",
        "conversation",
        ["restaurant_id", sa.text("last_message_at DESC")],
    )

    # ------------------------------------------------------------------ message
    op.create_table(
        "message",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "sender_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=False,
        ),
        # Nullable: an attachment on its own is a message, and a deleted message has no body.
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("priority", sa.Text(), nullable=False, server_default="normal"),
        sa.Column(
            "reply_to_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("message.id"),
            nullable=True,
        ),
        # ADR 0008's single soft-delete exception in the whole schema.
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_message_id_restaurant"),
        sa.ForeignKeyConstraint(
            ["conversation_id", "restaurant_id"],
            ["conversation.id", "conversation.restaurant_id"],
            name="fk_message_conversation",
        ),
        sa.CheckConstraint(_in("priority", _MESSAGE_PRIORITIES), name="ck_message_priority"),
        sa.CheckConstraint(
            "deleted_at IS NULL OR body IS NULL", name="ck_message_deleted_has_no_body"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_message_revision"),
    )
    # By id rather than by created_at: uuid7 is time-ordered, so one index pages the thread and
    # answers "how many since the watermark".
    op.create_index(
        "ix_message_conversation_id", "message", ["conversation_id", sa.text("id DESC")]
    )
    op.create_index("ix_message_restaurant_revision", "message", ["restaurant_id", "revision"])

    # --------------------------------------------------- conversation_participant
    op.create_table(
        "conversation_participant",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=False,
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        # A fact with a date, not a deletion. Rejoining clears it rather than inserting a second
        # row, which the unique constraint makes the only option.
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        # The watermark. The alternative, `message_read_receipt`, would be participants x messages
        # and the largest table in the schema.
        sa.Column("last_read_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_muted", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.UniqueConstraint(
            "conversation_id", "employee_id", name="uq_conversation_participant_pair"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "restaurant_id"],
            ["conversation.id", "conversation.restaurant_id"],
            name="fk_conversation_participant_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["last_read_message_id", "restaurant_id"],
            ["message.id", "message.restaurant_id"],
            name="fk_conversation_participant_watermark",
        ),
        sa.CheckConstraint(
            "left_at IS NULL OR left_at >= joined_at",
            name="ck_conversation_participant_left_after_joined",
        ),
    )
    op.create_index(
        "ix_conversation_participant_employee",
        "conversation_participant",
        ["employee_id", "conversation_id"],
    )

    # --------------------------------------------------------------------- task
    op.create_table(
        "task",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("complaint_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "assigned_to",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=True,
        ),
        sa.Column(
            "assigned_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=True,
        ),
        sa.Column("priority", sa.Text(), nullable=False, server_default="normal"),
        sa.Column("status", sa.Text(), nullable=False, server_default="created"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "verified_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=True,
        ),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_task_id_restaurant"),
        sa.ForeignKeyConstraint(
            ["source_message_id", "restaurant_id"],
            ["message.id", "message.restaurant_id"],
            name="fk_task_source_message",
        ),
        sa.ForeignKeyConstraint(
            ["complaint_id", "restaurant_id"],
            ["complaint.id", "complaint.restaurant_id"],
            name="fk_task_complaint",
        ),
        sa.CheckConstraint(_in("status", _TASK_STATUSES), name="ck_task_status"),
        sa.CheckConstraint(_in("priority", _TASK_PRIORITIES), name="ck_task_priority"),
        sa.CheckConstraint(
            "(status IN ('completed', 'verified')) = (completed_at IS NOT NULL)",
            name="ck_task_completed_at",
        ),
        sa.CheckConstraint(
            "(status = 'verified') = (verified_at IS NOT NULL AND verified_by IS NOT NULL)",
            name="ck_task_verified",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_task_revision"),
    )
    op.create_index(
        "ix_task_restaurant_assignee", "task", ["restaurant_id", "assigned_to", "status"]
    )
    # Overdue is derived, never stored, and this is the index that makes deriving it cheap.
    op.create_index(
        "ix_task_restaurant_due",
        "task",
        ["restaurant_id", "due_at"],
        postgresql_where=sa.text("status <> 'verified'"),
    )
    op.create_index("ix_task_restaurant_revision", "task", ["restaurant_id", "revision"])

    # --------------------------------------------------------------- task_event
    op.create_table(
        "task_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "actor_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=False,
        ),
        # Both nullable: a reassignment moves nobody between statuses and its note carries from
        # and to.
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["task_id", "restaurant_id"],
            ["task.id", "task.restaurant_id"],
            name="fk_task_event_task",
        ),
        sa.CheckConstraint(
            "from_status IS NULL OR " + _in("from_status", _TASK_STATUSES),
            name="ck_task_event_from_status",
        ),
        sa.CheckConstraint(
            "to_status IS NULL OR " + _in("to_status", _TASK_STATUSES),
            name="ck_task_event_to_status",
        ),
    )
    op.create_index("ix_task_event_task", "task_event", ["task_id", "occurred_at"])

    # --------------------------------------------------------------- attachment
    op.create_table(
        "attachment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("owner_type", sa.Text(), nullable=False),
        # No foreign key, for `conversation.ref_id`'s reason: six possible targets in one column.
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Generated, never derived from `file_name`, so an uploaded '../../etc/passwd' is a display
        # string and nothing else.
        sa.Column("file_key", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        *_timestamps(),
        sa.UniqueConstraint("file_key", name="uq_attachment_file_key"),
        sa.CheckConstraint(
            _in("owner_type", _ATTACHMENT_OWNER_TYPES), name="ck_attachment_owner_type"
        ),
        sa.CheckConstraint(_in("status", _ATTACHMENT_STATUSES), name="ck_attachment_status"),
        sa.CheckConstraint("size_bytes > 0", name="ck_attachment_size"),
    )
    op.create_index(
        "ix_attachment_owner", "attachment", ["restaurant_id", "owner_type", "owner_id"]
    )
    # What the sweep reads. Partial, because a healthy store has almost no pending rows.
    op.create_index(
        "ix_attachment_pending",
        "attachment",
        ["created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table("attachment")
    op.drop_table("task_event")
    op.drop_table("task")
    op.drop_table("conversation_participant")
    op.drop_table("message")
    op.drop_table("conversation")
    op.drop_table("comm_stream_cursor")
