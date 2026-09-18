"""Migration 0041 against a real Postgres, and the constraints that are M11's real rules.

A check constraint here is not decoration. Four of this module's decisions are true *only* because
the database refuses the alternative, and each gets a test that proves the refusal rather than the
happy path — a constraint nobody has seen fire is a constraint that might be spelled wrong.

The two that matter most:

**A direct thread between two people is one row, forever.** The pair lives in
`conversation_participant`, where no expression index on `conversation` could see it, so the
canonical pair is denormalised into `direct_key` and a partial unique index is what makes two
simultaneous taps resolve to one thread instead of two inboxes full of duplicates.

**A deleted message has no body.** ADR 0008's single soft-delete exception, with the half that is
easy to forget enforced here rather than trusted to the one service method that deletes. "Deleted"
that a database administrator can still read is a lie told to the person who deleted it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.communication import (
    Attachment,
    Conversation,
    ConversationParticipant,
    Message,
    Task,
)
from app.models.identity import Employee
from app.models.tenancy import Organization, Restaurant

_TABLES = (
    "conversation",
    "conversation_participant",
    "message",
    "task",
    "task_event",
    "attachment",
    "comm_stream_cursor",
)


async def _world(session: AsyncSession) -> tuple[Restaurant, Employee]:
    organization = Organization(name="Spice Garden Group", slug=f"sg-{uuid.uuid4().hex[:8]}")
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id, name="Koregaon Park", code=f"KP{uuid.uuid4().hex[:6]}"
    )
    session.add(restaurant)
    await session.flush()
    employee = Employee(
        organization_id=organization.id,
        employee_code=f"E{uuid.uuid4().hex[:8]}",
        full_name="Priya Nair",
        employment_type="full_time",
        joined_on=date(2026, 1, 1),
    )
    session.add(employee)
    await session.flush()
    return restaurant, employee


def _conversation(restaurant: Restaurant, employee: Employee, **extra: object) -> Conversation:
    fields: dict[str, object] = {
        "restaurant_id": restaurant.id,
        "type": "group",
        "title": "Evening shift",
        "created_by": employee.id,
    }
    fields.update(extra)
    return Conversation(**fields)


def _message(
    restaurant: Restaurant, conversation: Conversation, employee: Employee, **extra: object
) -> Message:
    fields: dict[str, object] = {
        "restaurant_id": restaurant.id,
        "conversation_id": conversation.id,
        "sender_employee_id": employee.id,
        "body": "86 the paneer",
        "priority": "normal",
        "revision": 1,
    }
    fields.update(extra)
    return Message(**fields)


async def test_the_seven_tables_arrive(db_session: AsyncSession) -> None:
    """`docs/schema.md` §10 lists six and this module ships seven: `comm_stream_cursor` is M11's
    addition, for the reason `kot_stream_cursor` exists — a Postgres sequence is global, and a
    global cursor handed to a client leaks how busy every other tenant is."""
    rows = await db_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ANY(:names)"
        ),
        {"names": list(_TABLES)},
    )
    assert set(rows.scalars().all()) == set(_TABLES)


async def test_the_watermark_is_a_real_foreign_key_and_needs_no_follow_up_migration(
    db_session: AsyncSession,
) -> None:
    """`docs/schema.md` §"Migration order" calls `last_read_message_id` circular and says to add it
    in a follow-up. It is circular only if the participant table is created before `message`;
    created in the other order, the constraint resolves the first time and there is no follow-up to
    forget."""
    found = await db_session.scalar(
        text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_name = 'fk_conversation_participant_watermark' "
            "AND constraint_type = 'FOREIGN KEY'"
        )
    )
    assert found == 1


async def test_two_direct_threads_between_the_same_pair_cannot_both_exist(
    db_session: AsyncSession,
) -> None:
    """Decision 3, enforced where two simultaneous taps cannot both win."""
    restaurant, employee = await _world(db_session)
    other = uuid.uuid4()
    key = f"{min(employee.id, other)}:{max(employee.id, other)}"
    db_session.add(_conversation(restaurant, employee, type="direct", title=None, direct_key=key))
    await db_session.flush()

    db_session.add(_conversation(restaurant, employee, type="direct", title=None, direct_key=key))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_group_thread_may_not_carry_a_direct_key_and_a_direct_thread_must(
    db_session: AsyncSession,
) -> None:
    """Both directions, because a `direct_key` on a group would make an unrelated pair collide and
    a direct thread without one would escape the uniqueness altogether."""
    restaurant, employee = await _world(db_session)
    db_session.add(_conversation(restaurant, employee, direct_key="a:b"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    restaurant, employee = await _world(db_session)
    db_session.add(_conversation(restaurant, employee, type="direct", title=None))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_half_a_reference_is_refused(db_session: AsyncSession) -> None:
    """A thread attached to something carries both halves or neither. Half a reference is a row
    nothing can resolve and nothing will ever notice."""
    restaurant, employee = await _world(db_session)
    db_session.add(_conversation(restaurant, employee, ref_type="task"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_deleted_message_cannot_keep_its_body(db_session: AsyncSession) -> None:
    """The tombstone's other half. The row stays, the sender stays, the words do not."""
    restaurant, employee = await _world(db_session)
    conversation = _conversation(restaurant, employee)
    db_session.add(conversation)
    await db_session.flush()

    message = _message(restaurant, conversation, employee)
    db_session.add(message)
    await db_session.flush()

    message.deleted_at = datetime.now(UTC)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_message_cannot_be_parented_across_a_tenant_boundary(
    db_session: AsyncSession,
) -> None:
    """The composite foreign key, which is the structural half of invariant 1 — the half that does
    not depend on a repository remembering its scope."""
    first_restaurant, employee = await _world(db_session)
    second_restaurant, _ = await _world(db_session)
    conversation = _conversation(first_restaurant, employee)
    db_session.add(conversation)
    await db_session.flush()

    db_session.add(_message(second_restaurant, conversation, employee))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_completed_task_carries_the_moment_it_was_completed(
    db_session: AsyncSession,
) -> None:
    """A status that moves without its timestamp is how a history stops being one."""
    restaurant, _employee = await _world(db_session)
    db_session.add(
        Task(
            restaurant_id=restaurant.id,
            title="Deep-clean the fryer",
            priority="normal",
            status="completed",
            revision=1,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_verified_task_names_who_verified_it(db_session: AsyncSession) -> None:
    restaurant, _employee = await _world(db_session)
    db_session.add(
        Task(
            restaurant_id=restaurant.id,
            title="Deep-clean the fryer",
            priority="normal",
            status="verified",
            completed_at=datetime.now(UTC),
            verified_at=datetime.now(UTC),
            revision=1,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_an_attachment_of_no_size_is_refused(db_session: AsyncSession) -> None:
    """Zero bytes is not a photograph. It is an upload that failed and a row that would be served
    as though it had not."""
    restaurant, employee = await _world(db_session)
    db_session.add(
        Attachment(
            restaurant_id=restaurant.id,
            owner_type="message",
            owner_id=uuid.uuid4(),
            file_key=f"{restaurant.id}/2026/09/{uuid.uuid4().hex}.jpg",
            file_name="fridge.jpg",
            mime_type="image/jpeg",
            size_bytes=0,
            uploaded_by=employee.id,
            status="pending",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_one_person_is_one_participant_row(db_session: AsyncSession) -> None:
    """Rejoining clears `left_at` rather than inserting a second row, and this is what makes that
    the only option — which is also the right one, because two rows would make "when did you join"
    unanswerable."""
    restaurant, employee = await _world(db_session)
    conversation = _conversation(restaurant, employee)
    db_session.add(conversation)
    await db_session.flush()

    for _ in range(2):
        db_session.add(
            ConversationParticipant(
                restaurant_id=restaurant.id,
                conversation_id=conversation.id,
                employee_id=employee.id,
                joined_at=datetime.now(UTC),
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_the_pending_sweep_has_an_index_to_read(db_session: AsyncSession) -> None:
    """Partial, because a healthy store has almost no pending rows and a full index on a column
    that is 'ready' everywhere earns nothing."""
    found = await db_session.scalar(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_attachment_pending'")
    )
    assert found is not None
    assert "status = 'pending'" in found
