"""Tasks: the lifecycle, who may move it, and the record that outlives the argument.

This is the half of M11 that WhatsApp cannot have, so these are the tests that decide whether the
module was worth building. Three of them carry the design:

**Only the assignee completes.** "The fryer was cleaned", asserted by the person who asked for it
to be cleaned, is not a record of anything.

**A `task.assign` holder cannot verify their own completed work** unless they are the owner —
M09's approver rule pointed at a different act, and for the same reason.

**Reassignment appends.** A task that changed hands twice reads as a history, so "I never asked
you to do that" has an answer a month later.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TaskStatus
from app.models.communication import Task
from app.services.tasks import TRANSITIONS
from tests.test_conversations import _group, _people, _send
from tests.test_setup_endpoints import _auth, _token, _world

STAFF = "/api/v1/staff"
TASKS = f"{STAFF}/tasks"


async def _task(
    client: AsyncClient, token: str, *, title: str = "Deep-clean the fryer", **extra: Any
) -> Any:
    return await client.post(TASKS, json={"title": title, **extra}, headers=_auth(token))


async def _move(
    client: AsyncClient, token: str, task_id: str, to: str, note: str | None = None
) -> Any:
    return await client.post(
        f"{TASKS}/{task_id}/status", json={"status": to, "note": note}, headers=_auth(token)
    )


class TestWritingWorkDown:
    async def test_anybody_can_write_down_their_own_work(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`task.view` is enough for that — the P1 design's split, and the line that keeps a chef
        able to note "deep-clean the fryer" without a permission the design withheld."""
        await _world(db_session, "owner", "chef")
        chef = await _token(api_client, "chef")
        people = await _people(api_client, await _token(api_client, "owner"))

        mine = await _task(api_client, chef, assigned_to=people["chef"])
        assert mine.status_code == 201, mine.text
        assert mine.json()["status"] == "assigned"

    async def test_giving_work_to_somebody_else_needs_task_assign(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "chef", "waiter")
        chef = await _token(api_client, "chef")
        people = await _people(api_client, await _token(api_client, "owner"))

        refused = await _task(api_client, chef, assigned_to=people["waiter"])
        assert refused.status_code == 403, refused.text
        assert refused.json()["code"] == "task.not_permitted"

        manager = await _token(api_client, "owner")
        allowed = await _task(api_client, manager, assigned_to=people["waiter"])
        assert allowed.status_code == 201, allowed.text

    async def test_a_task_survives_the_request_that_made_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Two requests, deliberately."""
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        created = await _task(api_client, owner)
        assert created.status_code == 201, created.text

        listed = await api_client.get(TASKS, headers=_auth(owner))
        assert [row["title"] for row in listed.json()["items"]] == ["Deep-clean the fryer"]

    async def test_work_for_somebody_who_does_not_work_here_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        refused = await _task(api_client, owner, assigned_to=str(uuid.uuid4()))
        assert refused.status_code == 404, refused.text


class TestTheLifecycle:
    def test_the_table_has_no_way_out_of_a_terminal_state(self) -> None:
        """Read from the table itself rather than restated, so a change to it fails here."""
        assert TRANSITIONS[TaskStatus.VERIFIED] == frozenset()
        assert TRANSITIONS[TaskStatus.CANCELLED] == frozenset()

    def test_everything_unfinished_can_be_cancelled(self) -> None:
        for status, allowed in TRANSITIONS.items():
            if status in (TaskStatus.VERIFIED, TaskStatus.CANCELLED):
                continue
            assert TaskStatus.CANCELLED in allowed, f"{status} cannot be cancelled"

    async def test_an_illegal_move_is_a_409_that_names_both_states_in_words(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A person reads `message`, never `code` (D11, D12), so the message has to be a sentence
        about their task rather than about our state machine."""
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        task = (await _task(api_client, owner, assigned_to=people["owner"])).json()

        refused = await _move(api_client, owner, task["id"], "verified")
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "task.transition_not_allowed"
        assert "assigned" in refused.json()["message"]
        assert "checked and closed" in refused.json()["message"]

    async def test_the_whole_happy_path(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        chef = await _token(api_client, "chef")
        people = await _people(api_client, owner)
        task = (await _task(api_client, owner, assigned_to=people["chef"])).json()

        for to in ("accepted", "in_progress", "completed"):
            moved = await _move(api_client, chef, task["id"], to)
            assert moved.status_code == 200, moved.text

        verified = await _move(api_client, owner, task["id"], "verified")
        assert verified.status_code == 200, verified.text
        assert verified.json()["verified_by"] == people["owner"]
        assert verified.json()["completed_at"] is not None


class TestWhoMayMoveIt:
    async def test_only_the_assignee_completes(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Not the manager who asked for it, not a colleague being helpful. The whole value of the
        record is that somebody specific said they did the work."""
        await _world(db_session, "owner", "chef", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        task = (await _task(api_client, owner, assigned_to=people["chef"])).json()

        chef = await _token(api_client, "chef")
        await _move(api_client, chef, task["id"], "in_progress")

        refused = await _move(api_client, owner, task["id"], "completed")
        assert refused.status_code == 403, refused.text
        assert refused.json()["code"] == "task.not_yours"

        waiter = await _token(api_client, "waiter")
        also_refused = await _move(api_client, waiter, task["id"], "completed")
        assert also_refused.status_code in (403, 404), also_refused.text

    async def test_a_manager_cannot_verify_work_they_did_themselves(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """M09's approver rule, pointed at a different act."""
        await _world(db_session, "owner", "manager")
        owner = await _token(api_client, "owner")
        manager = await _token(api_client, "manager")
        people = await _people(api_client, owner)

        task = (await _task(api_client, manager, assigned_to=people["manager"])).json()
        await _move(api_client, manager, task["id"], "in_progress")
        await _move(api_client, manager, task["id"], "completed")

        refused = await _move(api_client, manager, task["id"], "verified")
        assert refused.status_code == 403, refused.text
        assert refused.json()["code"] == "task.cannot_verify_own_work"

    async def test_the_owner_may_verify_their_own_work(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A one-person restaurant otherwise has no way to close anything, which is the case this
        product has to work for on day one."""
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        task = (await _task(api_client, owner, assigned_to=people["owner"])).json()
        await _move(api_client, owner, task["id"], "in_progress")
        await _move(api_client, owner, task["id"], "completed")

        verified = await _move(api_client, owner, task["id"], "verified")
        assert verified.status_code == 200, verified.text

    async def test_completed_work_can_be_sent_back(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A verification that can only ever say yes is a rubber stamp. Sending it back clears the
        completion, so the history does not claim it was finished while it is being done again."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        chef = await _token(api_client, "chef")
        people = await _people(api_client, owner)
        task = (await _task(api_client, owner, assigned_to=people["chef"])).json()
        await _move(api_client, chef, task["id"], "in_progress")
        await _move(api_client, chef, task["id"], "completed")

        sent_back = await _move(api_client, owner, task["id"], "in_progress", "Grease left in it.")
        assert sent_back.status_code == 200, sent_back.text
        assert sent_back.json()["completed_at"] is None


class TestTheRecord:
    async def test_reassignment_appends_and_the_previous_person_stays_readable(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "chef", "kitchen_staff")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        task = (await _task(api_client, owner, assigned_to=people["chef"])).json()

        moved = await api_client.post(
            f"{TASKS}/{task['id']}/assign",
            json={"assigned_to": people["kitchen_staff"], "note": "Chef is off."},
            headers=_auth(owner),
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["assigned_to"] == people["kitchen_staff"]

        detail = await api_client.get(f"{TASKS}/{task['id']}", headers=_auth(owner))
        notes = " ".join(event["note"] or "" for event in detail.json()["events"])
        assert people["chef"] in notes
        assert "Chef is off." in notes

    async def test_assigning_to_the_same_person_is_a_conflict(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        task = (await _task(api_client, owner, assigned_to=people["chef"])).json()

        again = await api_client.post(
            f"{TASKS}/{task['id']}/assign",
            json={"assigned_to": people["chef"], "note": None},
            headers=_auth(owner),
        )
        assert again.status_code == 409, again.text

    async def test_every_move_leaves_an_event(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        chef = await _token(api_client, "chef")
        people = await _people(api_client, owner)
        task = (await _task(api_client, owner, assigned_to=people["chef"])).json()
        await _move(api_client, chef, task["id"], "accepted")
        await _move(api_client, chef, task["id"], "in_progress")

        detail = await api_client.get(f"{TASKS}/{task['id']}", headers=_auth(owner))
        transitions = [
            (event["from_status"], event["to_status"]) for event in detail.json()["events"]
        ]
        assert (None, "assigned") in transitions
        assert ("assigned", "accepted") in transitions
        assert ("accepted", "in_progress") in transitions


class TestOverdueIsDerived:
    async def test_a_due_time_passing_changes_no_row(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Nothing flips a flag at midnight, so there is no background job to fail quietly."""
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        overdue_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        created = await _task(api_client, owner, assigned_to=people["owner"], due_at=overdue_at)
        assert created.json()["is_overdue"] is True

        row = await db_session.scalar(
            select(Task).where(Task.id == uuid.UUID(created.json()["id"]))
        )
        assert row is not None
        assert row.status == "assigned"

    async def test_finished_work_is_never_overdue(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        overdue_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        task = (
            await _task(api_client, owner, assigned_to=people["owner"], due_at=overdue_at)
        ).json()
        await _move(api_client, owner, task["id"], "in_progress")
        await _move(api_client, owner, task["id"], "completed")
        verified = await _move(api_client, owner, task["id"], "verified")
        assert verified.json()["is_overdue"] is False


class TestPromotion:
    async def test_a_message_becomes_a_task_and_keeps_its_parentage(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The thing that makes this module worth building instead of using WhatsApp."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"]])
        message = (
            await _send(api_client, owner, thread["id"], "AC repair guy coming at 4.\nLet him in.")
        ).json()

        promoted = await api_client.post(
            f"{STAFF}/messages/{message['id']}/promote",
            json={"assigned_to": people["chef"], "priority": "high"},
            headers=_auth(owner),
        )
        assert promoted.status_code == 201, promoted.text
        assert promoted.json()["source_message_id"] == message["id"]
        assert promoted.json()["title"] == "AC repair guy coming at 4."
        assert "Let him in." in promoted.json()["description"]

    async def test_promoting_the_same_message_twice_is_allowed(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Two people may genuinely owe two different pieces of work from one instruction, which
        is why promotion is a task that points back rather than a flag on the message."""
        await _world(db_session, "owner", "chef", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"], people["waiter"]])
        message = (await _send(api_client, owner, thread["id"], "Deep clean tonight.")).json()

        for who in ("chef", "waiter"):
            promoted = await api_client.post(
                f"{STAFF}/messages/{message['id']}/promote",
                json={"assigned_to": people[who], "priority": "normal"},
                headers=_auth(owner),
            )
            assert promoted.status_code == 201, promoted.text

        listed = await api_client.get(TASKS, headers=_auth(owner))
        assert len(listed.json()["items"]) == 2

    async def test_you_cannot_promote_a_message_from_a_thread_you_are_not_in(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "manager", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"]])
        message = (await _send(api_client, owner, thread["id"], "Private.")).json()

        manager = await _token(api_client, "manager")
        refused = await api_client.post(
            f"{STAFF}/messages/{message['id']}/promote",
            json={"priority": "normal"},
            headers=_auth(manager),
        )
        assert refused.status_code == 403, refused.text


class TestWhatYouCanSee:
    async def test_without_task_assign_you_see_only_your_own(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The scope is not a filter a client can widen."""
        await _world(db_session, "owner", "chef", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        await _task(api_client, owner, title="Chef's", assigned_to=people["chef"])
        await _task(api_client, owner, title="Waiter's", assigned_to=people["waiter"])

        chef = await _token(api_client, "chef")
        listed = await api_client.get(TASKS, headers=_auth(chef))
        assert [row["title"] for row in listed.json()["items"]] == ["Chef's"]

    async def test_somebody_elses_task_is_a_404(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A 404 rather than a 403, because telling them apart maps what exists."""
        await _world(db_session, "owner", "chef", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        task = (await _task(api_client, owner, assigned_to=people["chef"])).json()

        waiter = await _token(api_client, "waiter")
        refused = await api_client.get(f"{TASKS}/{task['id']}", headers=_auth(waiter))
        assert refused.status_code == 404, refused.text

    @pytest.mark.parametrize("role", ["cleaner", "kitchen_staff", "accountant"])
    async def test_every_role_can_see_the_work_assigned_to_it(
        self, db_session: AsyncSession, api_client: AsyncClient, role: str
    ) -> None:
        await _world(db_session, "owner", role)
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        await _task(api_client, owner, title="Yours", assigned_to=people[role])

        token = await _token(api_client, role)
        listed = await api_client.get(TASKS, headers=_auth(token))
        assert [row["title"] for row in listed.json()["items"]] == ["Yours"]
