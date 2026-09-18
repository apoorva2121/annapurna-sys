"""Threads, messages, the watermark and the stream — over HTTP, the way a screen uses them.

`test_generic_suites.py` already proves every route here is tenant-isolated and declares a
permission. What is left, and what this file is:

- **everybody can take part, including the cleaner** — asserted over the role catalogue, so a role
  added later fails a test rather than silently losing its voice;
- **the unread count is right in a group thread**, which is the watermark's whole justification;
- **one direct thread per pair, forever**, including when two people tap at the same moment;
- **a left participant reads nothing new and their old messages still render**;
- **the stream carries only what the viewer may see**, replays inclusively, and closes when the
  session is revoked;
- **every write actually commits.** Each write is followed by a *second request* that reads it
  back, because this codebase has now written the same vanishing-write bug twice.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.actor import Actor
from app.core.enums import UserAccountStatus
from app.core.permissions import CATALOGUE
from app.models.communication import Message
from app.models.identity import Employee, UserAccount, UserSession
from app.models.tenancy import Restaurant
from app.services.conversations import direct_key
from app.services.message_stream import communication_events
from tests.test_setup_endpoints import _auth, _token, _world

STAFF = "/api/v1/staff"
CONVERSATIONS = f"{STAFF}/conversations"
MESSAGES = f"{STAFF}/messages"

# Every system role in the catalogue, so this file's "everybody" means the catalogue's everybody.
EVERY_ROLE = tuple(role.code for role in CATALOGUE.roles)

_TICK = 0.01


async def _people(client: AsyncClient, token: str) -> dict[str, str]:
    """Employee ids by role, read the way a screen reads them — through the staff list."""
    response = await client.get(f"{STAFF}/employees", headers=_auth(token))
    assert response.status_code == 200, response.text
    return {row["full_name"].split()[0].lower(): row["id"] for row in response.json()["items"]}


async def _group(
    client: AsyncClient, token: str, members: list[str], title: str = "Evening shift"
) -> dict[str, Any]:
    response = await client.post(
        CONVERSATIONS,
        json={"type": "group", "title": title, "participant_ids": members},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _send(
    client: AsyncClient,
    token: str,
    conversation_id: str,
    body: str,
    *,
    priority: str = "normal",
    key: str | None = None,
) -> Any:
    return await client.post(
        MESSAGES,
        json={"conversation_id": conversation_id, "body": body, "priority": priority},
        headers={**_auth(token), "Idempotency-Key": key or str(uuid.uuid4())},
    )


class TestEverybodyTakesPart:
    async def test_every_role_in_the_catalogue_can_open_the_inbox_and_post(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The module's first acceptance criterion, asserted over the catalogue rather than over a
        list somebody remembered to update. `cleaner` held zero permissions before M11."""
        await _world(db_session, *EVERY_ROLE)
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)

        for role in EVERY_ROLE:
            token = await _token(api_client, role)
            inbox = await api_client.get(CONVERSATIONS, headers=_auth(token))
            assert inbox.status_code == 200, f"{role} cannot open the inbox: {inbox.text}"

            thread = await _group(api_client, token, [people["owner"]], title=f"{role} says")
            posted = await _send(api_client, token, thread["id"], "Fridge is warm.")
            assert posted.status_code == 201, f"{role} cannot post: {posted.text}"

    async def test_a_message_survives_the_request_that_made_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Two requests, deliberately. Only the second can tell whether anything committed."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"]])

        await _send(api_client, owner, thread["id"], "86 the paneer.")

        read_back = await api_client.get(
            f"{CONVERSATIONS}/{thread['id']}/messages", headers=_auth(owner)
        )
        assert read_back.status_code == 200, read_back.text
        assert [row["body"] for row in read_back.json()["items"]] == ["86 the paneer."]


class TestTheWatermark:
    async def test_three_of_five_have_read_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The case `message_read_receipt` was rejected for: a group thread read by some of the
        people in it. The whole count is one comparison against one column."""
        roles = ("owner", "manager", "chef", "waiter", "cleaner")
        await _world(db_session, *roles)
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(
            api_client, owner, [people[role] for role in roles if role != "owner"]
        )

        first = (await _send(api_client, owner, thread["id"], "One.")).json()
        second = (await _send(api_client, owner, thread["id"], "Two.")).json()

        chef = await _token(api_client, "chef")
        await api_client.patch(
            f"{CONVERSATIONS}/{thread['id']}/read",
            json={"last_read_message_id": first["id"]},
            headers=_auth(chef),
        )

        chef_inbox = (await api_client.get(CONVERSATIONS, headers=_auth(chef))).json()["items"][0]
        assert chef_inbox["unread"] == 1

        waiter = await _token(api_client, "waiter")
        waiter_inbox = (await api_client.get(CONVERSATIONS, headers=_auth(waiter))).json()["items"][
            0
        ]
        assert waiter_inbox["unread"] == 2

        await api_client.patch(
            f"{CONVERSATIONS}/{thread['id']}/read",
            json={"last_read_message_id": second["id"]},
            headers=_auth(chef),
        )
        chef_inbox = (await api_client.get(CONVERSATIONS, headers=_auth(chef))).json()["items"][0]
        assert chef_inbox["unread"] == 0

    async def test_your_own_messages_are_never_unread(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A badge on a thread because you spoke in it is the fastest way to teach somebody to
        ignore badges."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"]])
        await _send(api_client, owner, thread["id"], "Mine.")

        inbox = (await api_client.get(CONVERSATIONS, headers=_auth(owner))).json()["items"][0]
        assert inbox["unread"] == 0

    async def test_the_watermark_never_moves_backwards(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Two devices, and the fact that "mark unread" is not a feature — a rewind would be its
        accidental implementation."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"]])
        first = (await _send(api_client, owner, thread["id"], "One.")).json()
        second = (await _send(api_client, owner, thread["id"], "Two.")).json()

        chef = await _token(api_client, "chef")
        for message_id in (second["id"], first["id"]):
            moved = await api_client.patch(
                f"{CONVERSATIONS}/{thread['id']}/read",
                json={"last_read_message_id": message_id},
                headers=_auth(chef),
            )
            assert moved.status_code == 204, moved.text

        inbox = (await api_client.get(CONVERSATIONS, headers=_auth(chef))).json()["items"][0]
        assert inbox["unread"] == 0

    async def test_an_urgent_message_is_visible_before_the_thread_is_opened(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Priority is sorting and colour and nothing else in M11 — but it has to reach the inbox,
        or it is nothing at all."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"]])
        await _send(api_client, owner, thread["id"], "Gas leak.", priority="urgent")

        chef = await _token(api_client, "chef")
        inbox = (await api_client.get(CONVERSATIONS, headers=_auth(chef))).json()["items"][0]
        assert inbox["has_urgent_unread"] is True


class TestOneThreadPerPair:
    async def test_asking_twice_returns_the_same_thread(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """An inbox with seven threads to the same person looks broken, so the second ask is a
        200 with the first thread rather than a 201 with a second one."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)

        first = await api_client.post(
            CONVERSATIONS,
            json={"type": "direct", "participant_ids": [people["chef"]]},
            headers=_auth(owner),
        )
        assert first.status_code == 201, first.text

        second = await api_client.post(
            CONVERSATIONS,
            json={"type": "direct", "participant_ids": [people["chef"]]},
            headers=_auth(owner),
        )
        assert second.status_code == 200, second.text
        assert second.json()["id"] == first.json()["id"]

    async def test_the_other_person_asking_gets_the_same_thread(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Which is what the canonical pair is for: two people produce one key in either order."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        mine = await api_client.post(
            CONVERSATIONS,
            json={"type": "direct", "participant_ids": [people["chef"]]},
            headers=_auth(owner),
        )

        chef = await _token(api_client, "chef")
        theirs = await api_client.post(
            CONVERSATIONS,
            json={"type": "direct", "participant_ids": [people["owner"]]},
            headers=_auth(chef),
        )
        assert theirs.status_code == 200, theirs.text
        assert theirs.json()["id"] == mine.json()["id"]

    def test_the_key_is_the_same_in_either_order(self) -> None:
        first, second = uuid.uuid4(), uuid.uuid4()
        assert direct_key(first, second) == direct_key(second, first)

    async def test_a_direct_thread_cannot_take_a_third_person(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "chef", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        direct = await api_client.post(
            CONVERSATIONS,
            json={"type": "direct", "participant_ids": [people["chef"]]},
            headers=_auth(owner),
        )
        refused = await api_client.post(
            f"{CONVERSATIONS}/{direct.json()['id']}/participants",
            json={"employee_ids": [people["waiter"]]},
            headers=_auth(owner),
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "conversation.direct_is_closed"


class TestWhoCanSeeAThread:
    async def test_somebody_who_is_not_in_it_cannot_read_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Participation is the control a permission catalogue cannot express. Note the 404, not a
        403: telling the two apart maps what exists to somebody who cannot read it."""
        await _world(db_session, "owner", "chef", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"]])

        waiter = await _token(api_client, "waiter")
        refused = await api_client.get(f"{CONVERSATIONS}/{thread['id']}", headers=_auth(waiter))
        assert refused.status_code == 404, refused.text

        posted = await _send(api_client, waiter, thread["id"], "Butting in.")
        assert posted.status_code == 404, posted.text

    async def test_somebody_who_has_left_keeps_their_messages_and_loses_the_thread(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Leaving is a fact with a date. A thread whose membership changed mid-argument has to be
        readable afterwards, and the person who left must not keep reading it."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"]])

        chef = await _token(api_client, "chef")
        await _send(api_client, chef, thread["id"], "Said before leaving.")

        removed = await api_client.delete(
            f"{CONVERSATIONS}/{thread['id']}/participants/{people['chef']}",
            headers=_auth(owner),
        )
        assert removed.status_code == 204, removed.text

        gone = await api_client.get(f"{CONVERSATIONS}/{thread['id']}/messages", headers=_auth(chef))
        assert gone.status_code == 404, gone.text

        still_there = await api_client.get(
            f"{CONVERSATIONS}/{thread['id']}/messages", headers=_auth(owner)
        )
        assert [row["body"] for row in still_there.json()["items"]] == ["Said before leaving."]

        remaining = await api_client.get(f"{CONVERSATIONS}/{thread['id']}", headers=_auth(owner))
        chef_row = next(
            row for row in remaining.json()["participants"] if row["employee_id"] == people["chef"]
        )
        assert chef_row["left_at"] is not None

    async def test_somebody_who_does_not_work_here_cannot_be_added(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        refused = await api_client.post(
            CONVERSATIONS,
            json={"type": "group", "title": "Ghosts", "participant_ids": [str(uuid.uuid4())]},
            headers=_auth(owner),
        )
        assert refused.status_code == 404, refused.text
        assert refused.json()["code"] == "conversation.person_not_found"


class TestSendingAndDeleting:
    async def test_a_double_tap_posts_once(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A phone on a bad connection in a kitchen — the situation the key exists for."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"]])

        key = str(uuid.uuid4())
        first = await _send(api_client, owner, thread["id"], "Once.", key=key)
        second = await _send(api_client, owner, thread["id"], "Once.", key=key)
        assert first.status_code == 201
        assert second.json()["id"] == first.json()["id"]

        listed = await api_client.get(
            f"{CONVERSATIONS}/{thread['id']}/messages", headers=_auth(owner)
        )
        assert len(listed.json()["items"]) == 1

    async def test_deleting_leaves_a_tombstone_and_no_words(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """ "Deleted" that a database administrator can still read is a lie told to the person who
        deleted it — so the assertion is against the row, not the response."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"]])
        message = (await _send(api_client, owner, thread["id"], "Regrettable.")).json()

        deleted = await api_client.delete(f"{MESSAGES}/{message['id']}", headers=_auth(owner))
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["is_deleted"] is True
        assert deleted.json()["body"] is None

        row = await db_session.scalar(select(Message).where(Message.id == uuid.UUID(message["id"])))
        assert row is not None
        assert row.body is None
        assert row.sender_employee_id is not None

    async def test_you_cannot_delete_somebody_elses_message(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "chef", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"], people["waiter"]])
        message = (await _send(api_client, owner, thread["id"], "Mine.")).json()

        waiter = await _token(api_client, "waiter")
        refused = await api_client.delete(f"{MESSAGES}/{message['id']}", headers=_auth(waiter))
        assert refused.status_code == 403, refused.text

    async def test_an_empty_message_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"]])
        refused = await _send(api_client, owner, thread["id"], "   ")
        assert refused.status_code == 422, refused.text


# --------------------------------------------------------------------------- the stream


async def _collect(
    sessions: async_sessionmaker[AsyncSession],
    actor: Actor,
    *,
    cursor: int | None,
    expected: int,
) -> list[Any]:
    """Drive the generator directly. The cursor arithmetic is what can be wrong, and an HTTP
    connection in the way would prove less about it — `test_kitchen_stream.py`'s argument."""
    found: list[Any] = []
    ticks = 0

    async def done() -> bool:
        nonlocal ticks
        ticks += 1
        return len(found) >= expected or ticks > 40

    async for event in communication_events(
        sessions,
        actor,
        cursor=cursor,
        is_disconnected=done,
        tick_seconds=_TICK,
        heartbeat_seconds=60.0,
        max_seconds=5.0,
    ):
        if event is not None:
            found.append(event)
            if len(found) >= expected:
                break
    return found


async def _actor_for(session: AsyncSession, email: str) -> Actor:
    account = await session.scalar(select(UserAccount).where(UserAccount.email == email))
    assert account is not None
    employee = await session.scalar(select(Employee).where(Employee.user_account_id == account.id))
    assert employee is not None
    restaurant = await session.scalar(
        select(Restaurant).where(Restaurant.organization_id == employee.organization_id)
    )
    assert restaurant is not None
    return Actor(
        employee_id=employee.id,
        organization_id=employee.organization_id,
        restaurant_id=restaurant.id,
        full_name=employee.full_name,
        permissions=frozenset({"message.send", "task.view", "task.complete"}),
        rank=40,
    )


class TestTheStream:
    async def test_it_carries_only_what_the_viewer_is_in(
        self, db_session: AsyncSession, api_client: AsyncClient, sessions: Any
    ) -> None:
        """The participant join is inside the query, so the page limit is spent on rows the viewer
        may have. Filtering afterwards would let a busy thread they are not in starve them."""
        await _world(db_session, "owner", "chef", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        mine = await _group(api_client, owner, [people["chef"]], title="Kitchen")
        theirs = await _group(api_client, owner, [people["waiter"]], title="Floor")

        await _send(api_client, owner, theirs["id"], "Not for the chef.")
        await _send(api_client, owner, mine["id"], "For the chef.")

        actor = await _actor_for(db_session, "chef@spice-garden.test")
        events = await _collect(sessions, actor, cursor=1, expected=1)
        bodies = [event.message.body for event in events if event.message is not None]
        assert bodies == ["For the chef."]

    async def test_a_reconnect_replays_inclusively_and_loses_nothing(
        self, db_session: AsyncSession, api_client: AsyncClient, sessions: Any
    ) -> None:
        """M08's property, asserted for this stream too: disconnect, let things happen, reconnect
        with `Last-Event-ID`, receive all of them."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        thread = await _group(api_client, owner, [people["chef"]])
        for body in ("One.", "Two.", "Three."):
            await _send(api_client, owner, thread["id"], body)

        actor = await _actor_for(db_session, "chef@spice-garden.test")
        events = await _collect(sessions, actor, cursor=1, expected=3)
        assert [event.message.body for event in events if event.message] == [
            "One.",
            "Two.",
            "Three.",
        ]

    async def test_a_revoked_session_closes_the_stream(
        self, db_session: AsyncSession, api_client: AsyncClient, sessions: Any
    ) -> None:
        """The one place in the product where revocation and a long-lived connection meet."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        await _group(api_client, owner, [people["chef"]])

        actor = await _actor_for(db_session, "chef@spice-garden.test")
        account_id = await db_session.scalar(
            select(UserAccount.id).where(UserAccount.email == "chef@spice-garden.test")
        )
        assert account_id is not None
        session_row = UserSession(
            user_account_id=account_id,
            refresh_token_hash=uuid.uuid4().hex,
            family_id=uuid.uuid4(),
            restaurant_id=actor.restaurant_id,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        db_session.add(session_row)
        await db_session.flush()
        revoked = replace(actor, session_id=session_row.id)

        # Both halves of what revocation means: the account and the session row.
        await db_session.execute(
            update(UserAccount)
            .where(UserAccount.id == account_id)
            .values(status=UserAccountStatus.SUSPENDED.value)
        )
        await db_session.execute(
            update(UserSession)
            .where(UserSession.id == session_row.id)
            .values(revoked_at=datetime.now(UTC))
        )
        await db_session.commit()

        events = await _collect(sessions, revoked, cursor=1, expected=1)
        assert events == []


@pytest.fixture
def sessions(db_connection: Any) -> Any:
    """The session *factory* the stream takes, bound to this test's connection.

    The stream opens a session per tick and closes it — a dependency-injected one would hold a
    pooled connection for the life of a screen.
    """
    from tests.conftest import _session_factory

    return _session_factory(db_connection)


async def test_the_inbox_costs_the_same_for_one_thread_and_for_many(
    db_session: AsyncSession, api_client: AsyncClient
) -> None:
    """The module's defining N+1 risk: the first screen anybody opens, with a count per row."""
    from tests.helpers.queries import count_queries

    await _world(db_session, "owner", "chef")
    owner = await _token(api_client, "owner")
    people = await _people(api_client, owner)
    engine = db_session.get_bind().engine
    thread = await _group(api_client, owner, [people["chef"]], title="First")
    await _send(api_client, owner, thread["id"], "One.")

    chef = await _token(api_client, "chef")
    with count_queries(engine) as one:
        await api_client.get(CONVERSATIONS, headers=_auth(chef))

    for index in range(9):
        extra = await _group(api_client, owner, [people["chef"]], title=f"Thread {index}")
        await _send(api_client, owner, extra["id"], "Hello.")

    with count_queries(engine) as ten:
        listed = await api_client.get(CONVERSATIONS, headers=_auth(chef))
    assert len(listed.json()["items"]) == 10

    assert ten.count == one.count, (
        f"the inbox costs {one.count} queries for one thread and {ten.count} for ten — "
        "an unread count per row is an N+1 on the most-used query in the module"
    )
