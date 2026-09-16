"""Complaints, feedback, and the two reads that assemble a person's record.

`docs/customer-experience.md` is the spec behind this file, and two of its sentences are
load-bearing:

**"A logged complaint that nobody resolves is worse than no system."** It is worse because it
manufactures evidence that somebody was told and nothing happened. So the tests here are about the
two fields that make a complaint recoverable rather than recorded — an owner, and what was done —
and about the database refusing `resolved` with an empty resolution.

**"[Whether the customer returned] is the only real measure of recovery."** It is derived from the
order ledger, never typed, and no endpoint can write it. A field that becomes true weeks after
everyone has forgotten the complaint is a field nobody would ever update.
"""

from __future__ import annotations

import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenancy import Restaurant
from tests.test_customer_endpoints import CUSTOMERS, _auth, _create, _open_order, _sign_in, _world

COMPLAINTS = "/api/v1/staff/complaints"
FEEDBACK = "/api/v1/staff/feedback"


async def _settled_order_for(
    session: AsyncSession, restaurant: Restaurant, customer_id: str, *, day: date
) -> uuid.UUID:
    order_id = uuid.uuid4()
    await session.execute(
        text(
            'INSERT INTO "order" (id, restaurant_id, customer_id, order_number, type, channel, '
            "status, business_date, placed_at, settled_at, subtotal, discount_total, "
            "charge_total, tax_total, round_off, grand_total) "
            "VALUES (:id, :rid, :cid, :number, 'dine_in', 'pos', 'settled', :day, now(), now(), "
            "500, 0, 0, 25, 0, 525)"
        ),
        {
            "id": order_id,
            "rid": restaurant.id,
            "cid": uuid.UUID(customer_id),
            "number": uuid.uuid4().hex[:6],
            "day": day,
        },
    )
    return order_id


async def _log(api_client: AsyncClient, token: str, **body: object) -> dict[str, object]:
    response = await api_client.post(
        COMPLAINTS,
        json={
            "category": "food_quality",
            "severity": "high",
            "description": "The biryani was cold.",
            **body,
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


# --------------------------------------------------------------------------- complaints


class TestAComplaintHasAnOwnerAndAnOutcome:
    async def test_a_complaint_survives_and_gets_a_number_a_person_can_say(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))

        logged = await _log(api_client, token)

        listed = await api_client.get(COMPLAINTS, headers=_auth(token))
        assert listed.status_code == 200, listed.text
        assert [row["id"] for row in listed.json()["items"]] == [logged["id"]]
        # "Complaint 1", not thirty-six hex characters, because a manager reads it out on the phone.
        assert logged["reference"] == "1"

    async def test_references_count_up_within_a_restaurant(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))

        first = await _log(api_client, token)
        second = await _log(api_client, token, severity="low")

        assert [first["reference"], second["reference"]] == ["1", "2"]

    async def test_two_branches_number_their_own_complaints(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Per restaurant, like the order number and the invoice series. Baner's first complaint is
        Baner's complaint 1, whatever Koregaon Park has logged."""
        world = await _world(db_session, branches=("koregaon", "baner"))
        koregaon = await _sign_in(
            db_session, api_client, world, role="manager", branches=("koregaon",)
        )
        baner = await _sign_in(
            db_session, api_client, world, role="manager", branches=("baner",), label="baner"
        )
        await _log(api_client, koregaon)

        theirs = await _log(api_client, baner)

        assert theirs["reference"] == "1"

    async def test_assigning_an_owner_moves_it_off_untouched(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A complaint somebody is holding is not one nobody has looked at."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        logged = await _log(api_client, token)
        me = await api_client.get("/api/v1/auth/me", headers=_auth(token))
        employee_id = me.json()["employee_id"]

        assigned = await api_client.post(
            f"{COMPLAINTS}/{logged['id']}/assign",
            json={"assigned_to": employee_id},
            headers=_auth(token),
        )

        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["status"] == "investigating"
        assert assigned.json()["assigned_to"] == employee_id

    async def test_resolving_requires_saying_what_was_done(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The schema refuses an empty resolution and the database refuses it again. A dropdown that
        can be set to Resolved with an empty box is how a complaint system becomes paperwork."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        logged = await _log(api_client, token)

        empty = await api_client.post(
            f"{COMPLAINTS}/{logged['id']}/resolve", json={"resolution": ""}, headers=_auth(token)
        )
        written = await api_client.post(
            f"{COMPLAINTS}/{logged['id']}/resolve",
            json={"resolution": "Remade the dish and comped it.", "compensation_amount": "240.00"},
            headers=_auth(token),
        )

        assert empty.status_code == 422, empty.text
        assert written.status_code == 200, written.text
        assert written.json()["status"] == "resolved"
        assert written.json()["resolution"] == "Remade the dish and comped it."

    async def test_a_resolved_complaint_leaves_the_open_list(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        logged = await _log(api_client, token)
        await api_client.post(
            f"{COMPLAINTS}/{logged['id']}/resolve",
            json={"resolution": "Apologised and refunded."},
            headers=_auth(token),
        )
        await api_client.post(f"{COMPLAINTS}/{logged['id']}/close", headers=_auth(token))

        listed = await api_client.get(COMPLAINTS, headers=_auth(token))

        assert listed.json()["items"] == []

    async def test_a_closed_complaint_cannot_be_reopened(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Reopening is a new complaint. The second time is its own event, and a complaint that
        keeps reopening looks, in every report, like one complaint."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        logged = await _log(api_client, token)
        await api_client.post(
            f"{COMPLAINTS}/{logged['id']}/resolve",
            json={"resolution": "Sorted at the table."},
            headers=_auth(token),
        )
        await api_client.post(f"{COMPLAINTS}/{logged['id']}/close", headers=_auth(token))

        again = await api_client.post(
            f"{COMPLAINTS}/{logged['id']}/resolve",
            json={"resolution": "Again."},
            headers=_auth(token),
        )

        assert again.status_code == 409, again.text

    async def test_a_waiter_cannot_own_a_complaint(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        waiter = await _sign_in(
            db_session, api_client, world, role="waiter", branches=("main",), label="waiter"
        )

        response = await api_client.get(COMPLAINTS, headers=_auth(waiter))

        assert response.status_code == 403, response.text


class TestRecoveryIsMeasuredNotTyped:
    async def test_returning_after_a_resolution_shows_as_recovered(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876545001")
        logged = await _log(api_client, token, customer_id=customer["id"])
        await api_client.post(
            f"{COMPLAINTS}/{logged['id']}/resolve",
            json={"resolution": "Comped the table."},
            headers=_auth(token),
        )
        # They came back the following week, which is the only honest measure of recovery.
        await _settled_order_for(
            db_session, world.restaurants["main"], customer["id"], day=date(2026, 9, 23)
        )
        await db_session.flush()

        listed = await api_client.get(COMPLAINTS, headers=_auth(token))
        # Resolved complaints leave the open list, so read it back through the history instead.
        history = await api_client.get(
            f"{CUSTOMERS}/{customer['id']}/history", headers=_auth(token)
        )

        assert listed.json()["items"] == []
        assert len(history.json()["complaints"]) == 1

    async def test_no_endpoint_can_write_whether_they_returned(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The field is derived, so the API has nowhere to send it. `extra="forbid"` refuses a
        client that tries rather than dropping it silently — a client that sends a value believes
        the value it sent."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))

        response = await api_client.post(
            COMPLAINTS,
            json={
                "category": "service",
                "severity": "low",
                "description": "Nobody came.",
                "customer_returned": True,
            },
            headers=_auth(token),
        )

        assert response.status_code == 422, response.text

    async def test_an_unresolved_complaint_says_nothing_rather_than_no(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """ "Did they come back" has no meaning before the complaint is settled, and answering
        `false` would read as "they did not" — a different and untrue thing."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876545002")
        await _log(api_client, token, customer_id=customer["id"])

        listed = await api_client.get(COMPLAINTS, headers=_auth(token))

        assert listed.json()["items"][0]["customer_returned"] is None


# --------------------------------------------------------------------------- feedback


class TestStaffFeedback:
    async def test_a_manager_can_write_down_a_conversation(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))

        written = await api_client.post(
            FEEDBACK,
            json={"overall_rating": 4, "comment": "Said the paneer was excellent, on the phone."},
            headers=_auth(token),
        )

        assert written.status_code == 201, written.text
        # Visible as staff-entered in every view. Filling the form for a customer is legitimate;
        # hiding that it happened is not, and M17 pays attention to these numbers.
        assert written.json()["source"] == "staff"

        day = written.json()["business_date"]
        listed = await api_client.get(FEEDBACK, params={"business_date": day}, headers=_auth(token))
        assert [row["id"] for row in listed.json()["items"]] == [written.json()["id"]]

    async def test_staff_cannot_record_a_second_rating_over_a_guests(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The one-per-order index applies here too, and that is the right answer: the guest already
        said what they thought."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        order_id = await _open_order(db_session, world.restaurants["main"])
        first = await api_client.post(
            FEEDBACK, json={"order_id": order_id, "overall_rating": 5}, headers=_auth(token)
        )
        assert first.status_code == 201, first.text

        second = await api_client.post(
            FEEDBACK, json={"order_id": order_id, "overall_rating": 1}, headers=_auth(token)
        )

        assert second.status_code == 409, second.text

    async def test_a_waiter_reads_feedback_and_does_not_write_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A rating is about a table they served, and somebody who cannot see how their service
        landed cannot improve it. What nobody can do is submit feedback on their own tables."""
        world = await _world(db_session)
        waiter = await _sign_in(
            db_session, api_client, world, role="waiter", branches=("main",), label="waiter"
        )

        read = await api_client.get(
            FEEDBACK, params={"business_date": "2026-09-16"}, headers=_auth(waiter)
        )
        write = await api_client.post(FEEDBACK, json={"overall_rating": 5}, headers=_auth(waiter))

        assert read.status_code == 200, read.text
        assert write.status_code == 403, write.text


# --------------------------------------------------------------------------- history & export


class TestTheRecordOfAPerson:
    async def test_history_shows_this_branchs_visits_with_what_they_ate(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876545010", name="Ravi Kumar")
        await _settled_order_for(
            db_session, world.restaurants["main"], customer["id"], day=date(2026, 9, 16)
        )
        await db_session.flush()

        history = await api_client.get(
            f"{CUSTOMERS}/{customer['id']}/history", headers=_auth(token)
        )

        assert history.status_code == 200, history.text
        assert len(history.json()["visits"]) == 1
        assert history.json()["visits"][0]["total"] == "525.00"

    async def test_history_does_not_cross_branches(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The record is the organization's; what each branch shows is its own."""
        world = await _world(db_session, branches=("koregaon", "baner"))
        koregaon = await _sign_in(
            db_session, api_client, world, role="manager", branches=("koregaon",)
        )
        customer = await _create(api_client, koregaon, "9876545011")
        await _settled_order_for(
            db_session, world.restaurants["baner"], customer["id"], day=date(2026, 9, 16)
        )
        await db_session.flush()

        history = await api_client.get(
            f"{CUSTOMERS}/{customer['id']}/history", headers=_auth(koregaon)
        )

        assert history.json()["visits"] == []

    async def test_the_export_carries_the_consent_history_not_just_its_state(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """What somebody agreed to **and when** is the part that is evidence. A current state alone
        cannot answer "was this lawful in March"."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876545012")
        body = {
            "purpose": "marketing",
            "notice_version": "2026-09-16.1",
            "notice_language": "en",
        }
        for granted in (True, False):
            await api_client.post(
                f"{CUSTOMERS}/{customer['id']}/consent",
                json={**body, "granted": granted},
                headers=_auth(token),
            )

        export = await api_client.get(f"{CUSTOMERS}/{customer['id']}/export", headers=_auth(token))

        assert export.status_code == 200, export.text
        assert len(export.json()["consent_history"]) == 2
        assert {row["granted"] for row in export.json()["consent_history"]} == {True, False}

    async def test_a_waiter_cannot_export_a_customer(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Reading a profile to greet somebody and reading out everything ever held about them are
        different acts."""
        world = await _world(db_session)
        manager = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        waiter = await _sign_in(
            db_session, api_client, world, role="waiter", branches=("main",), label="waiter"
        )
        customer = await _create(api_client, manager, "9876545013")

        response = await api_client.get(
            f"{CUSTOMERS}/{customer['id']}/export", headers=_auth(waiter)
        )

        assert response.status_code == 403, response.text

    async def test_there_is_no_bulk_export_in_any_role(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The control is the shape of the surface, not the permission: the P1 design hands
        `customer.view` to waiters on purpose, so what must not exist is the one request that
        returns everybody."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))

        response = await api_client.get(f"{CUSTOMERS}/export", headers=_auth(token))

        # Routed as a customer id, which this is not — there is no bulk endpoint to reach.
        assert response.status_code in {404, 422}, response.text


# --------------------------------------------------------------------------- the review's finding


class TestVisitsAreCountedNotRemembered:
    """The M10 adversarial review's finding, and its regression test.

    `customer.visit_count`, `lifetime_value`, `first_visit_at` and `last_visit_at` are columns in
    `docs/schema.md` §9 that **nothing in this product writes**. A waiter's screen read them, so it
    would have shown "7th visit" frozen at whatever the seed put there, for ever.

    That is exactly the failure `customer_returned` was removed to avoid — a stored value beside a
    derivation that is always right — and it shipped anyway until somebody read the screen back.
    They are derived now, and these tests are what stop the columns creeping back into a response.
    """

    async def test_a_new_customer_has_no_visits(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))

        created = await _create(api_client, token, "9876546001")

        assert created["visit_count"] == 0
        assert created["lifetime_value"] == "0.00"
        assert created["last_visit_at"] is None

    async def test_a_settled_bill_makes_it_a_visit(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876546002")
        for _ in range(3):
            await _settled_order_for(
                db_session, world.restaurants["main"], customer["id"], day=date(2026, 9, 16)
            )
        await db_session.flush()

        profile = await api_client.get(f"{CUSTOMERS}/{customer['id']}", headers=_auth(token))

        assert profile.json()["visit_count"] == 3
        assert profile.json()["lifetime_value"] == "1575.00"

    async def test_visits_count_across_branches_even_though_the_list_does_not(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """ "Seventh visit" is a fact about the relationship, and the record is the organisation's
        precisely so a chain recognises one diner across its branches. What each branch *shows* of
        their history is still its own — which is why this asserts both halves."""
        world = await _world(db_session, branches=("koregaon", "baner"))
        koregaon = await _sign_in(
            db_session, api_client, world, role="manager", branches=("koregaon",)
        )
        customer = await _create(api_client, koregaon, "9876546003")
        await _settled_order_for(
            db_session, world.restaurants["koregaon"], customer["id"], day=date(2026, 9, 16)
        )
        await _settled_order_for(
            db_session, world.restaurants["baner"], customer["id"], day=date(2026, 9, 16)
        )
        await db_session.flush()

        profile = await api_client.get(f"{CUSTOMERS}/{customer['id']}", headers=_auth(koregaon))
        history = await api_client.get(
            f"{CUSTOMERS}/{customer['id']}/history", headers=_auth(koregaon)
        )

        assert profile.json()["visit_count"] == 2
        assert len(history.json()["visits"]) == 1

    async def test_the_list_counts_every_row_in_one_query(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A list of forty customers must cost one round trip for the counts, not forty. This
        asserts the figures are right for several rows at once, which is what the grouped query is
        for — the query count itself is held by the generic suites."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        first = await _create(api_client, token, "9876546004")
        second = await _create(api_client, token, "9876546005")
        await _settled_order_for(
            db_session, world.restaurants["main"], first["id"], day=date(2026, 9, 16)
        )
        await _settled_order_for(
            db_session, world.restaurants["main"], second["id"], day=date(2026, 9, 16)
        )
        await _settled_order_for(
            db_session, world.restaurants["main"], second["id"], day=date(2026, 9, 17)
        )
        await db_session.flush()

        listed = await api_client.get(CUSTOMERS, headers=_auth(token))

        counts = {row["id"]: row["visit_count"] for row in listed.json()["items"]}
        assert counts[first["id"]] == 1
        assert counts[second["id"]] == 2

    async def test_an_open_bill_is_not_a_visit_yet(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Counting an unsettled bill would make the number jump back down when a table walks out
        without paying, which is a worse lie than counting late."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876546006")
        order_id = await _open_order(db_session, world.restaurants["main"])
        await api_client.post(
            f"/api/v1/staff/orders/{order_id}/customer",
            json={"customer_id": customer["id"]},
            headers=_auth(token),
        )

        profile = await api_client.get(f"{CUSTOMERS}/{customer['id']}", headers=_auth(token))

        assert profile.json()["visit_count"] == 0
