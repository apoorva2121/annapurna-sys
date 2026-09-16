"""Consent and the two DPDP rights. These tests *are* the compliance evidence.

`docs/compliance-rules.md` §B2 sets the standard this module builds to: one consent row per purpose,
never a single boolean; withdrawal as easy as granting; the notice version and language retained;
erasure on purpose completion. Each of those is a sentence in a document until something proves it,
and this is that something.

**Said once, and said plainly: none of these obligations is currently in force.** The DPDP Act
2023's notice, consent and rights provisions are notified and commence **13 May 2027**. This product
builds to the standard now because consent architecture cannot be retrofitted — you cannot lawfully
re-derive consent that was never captured — and says nothing anywhere a person can read that calls
the obligation current.

The one that matters most operationally is **erasure keeps the money**. `docs/security.md`: erasure
"anonymises the customer row and keeps the order (financial records must be retained); it does not
cascade-delete revenue history". Get that wrong and exercising a data right silently destroys a
restaurant's books.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.consent import CURRENT_NOTICE_VERSION, DEFAULT_NOTICE_LANGUAGE
from app.models.customers import Customer, CustomerConsent
from app.models.orders import Order
from app.models.tenancy import Restaurant
from tests.test_customer_endpoints import CUSTOMERS, _auth, _create, _sign_in, _world


async def _settled_order(
    session: AsyncSession, restaurant: Restaurant, customer_id: str, total: str
) -> None:
    """A settled bill against this customer. Erasure must not move it by a paisa."""
    await session.execute(
        text(
            'INSERT INTO "order" (id, restaurant_id, customer_id, order_number, type, channel, '
            "status, business_date, placed_at, settled_at, subtotal, discount_total, charge_total, "
            "tax_total, round_off, grand_total) "
            "VALUES (:id, :rid, :cid, :number, 'dine_in', 'pos', 'settled', :day, now(), now(), "
            ":total, 0, 0, 0, 0, :total)"
        ),
        {
            "id": uuid.uuid4(),
            "rid": restaurant.id,
            "cid": uuid.UUID(customer_id),
            "number": uuid.uuid4().hex[:6],
            "day": date(2026, 9, 16),
            "total": Decimal(total),
        },
    )


# --------------------------------------------------------------------------- consent


class TestConsentIsALedger:
    async def test_granting_one_purpose_grants_nothing_else(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """§B2's purpose limitation, in its own words: "a phone number collected for a bill is not
        marketing consent"."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876544001")

        written = await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/consent",
            json={
                "purpose": "order_contact",
                "granted": True,
                "notice_version": CURRENT_NOTICE_VERSION,
                "notice_language": DEFAULT_NOTICE_LANGUAGE,
            },
            headers=_auth(token),
        )
        assert written.status_code == 200, written.text

        profile = await api_client.get(f"{CUSTOMERS}/{customer['id']}", headers=_auth(token))
        states = {row["purpose"]: row["granted"] for row in profile.json()["consents"]}
        assert states == {"order_contact": True}

    async def test_a_purpose_nobody_asked_about_is_absent_not_false(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """ "We never asked" and "they said no" are different facts, and a screen that showed them
        the same way would be showing something untrue."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876544002")

        profile = await api_client.get(f"{CUSTOMERS}/{customer['id']}", headers=_auth(token))

        assert profile.json()["consents"] == []

    async def test_withdrawing_is_a_new_row_and_the_grant_survives_in_the_ledger(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Append-only, and this is why: the history is the evidence. A consent record that can be
        rewritten proves nothing about what somebody agreed to, or when."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876544003")
        body = {
            "purpose": "marketing",
            "notice_version": CURRENT_NOTICE_VERSION,
            "notice_language": DEFAULT_NOTICE_LANGUAGE,
        }
        await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/consent",
            json={**body, "granted": True},
            headers=_auth(token),
        )

        await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/consent",
            json={**body, "granted": False},
            headers=_auth(token),
        )

        rows = (
            await db_session.scalars(
                select(CustomerConsent)
                .where(CustomerConsent.customer_id == uuid.UUID(customer["id"]))
                .order_by(CustomerConsent.occurred_at)
            )
        ).all()
        assert [row.granted for row in rows] == [True, False]

        profile = await api_client.get(f"{CUSTOMERS}/{customer['id']}", headers=_auth(token))
        states = {row["purpose"]: row["granted"] for row in profile.json()["consents"]}
        assert states == {"marketing": False}

    async def test_withdrawing_one_purpose_leaves_the_others_alone(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876544004")
        for purpose in ("order_contact", "marketing"):
            await api_client.post(
                f"{CUSTOMERS}/{customer['id']}/consent",
                json={
                    "purpose": purpose,
                    "granted": True,
                    "notice_version": CURRENT_NOTICE_VERSION,
                    "notice_language": DEFAULT_NOTICE_LANGUAGE,
                },
                headers=_auth(token),
            )

        await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/consent",
            json={
                "purpose": "marketing",
                "granted": False,
                "notice_version": CURRENT_NOTICE_VERSION,
                "notice_language": DEFAULT_NOTICE_LANGUAGE,
            },
            headers=_auth(token),
        )

        profile = await api_client.get(f"{CUSTOMERS}/{customer['id']}", headers=_auth(token))
        states = {row["purpose"]: row["granted"] for row in profile.json()["consents"]}
        assert states == {"order_contact": True, "marketing": False}

    async def test_the_notice_shown_is_recorded_with_the_consent(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """What somebody was shown is part of what they agreed to. §B2 asks for the version *and*
        the language, and a consent whose words are unrecoverable is not evidence of anything."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876544005")

        written = await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/consent",
            json={
                "purpose": "service_recognition",
                "granted": True,
                "notice_version": CURRENT_NOTICE_VERSION,
                "notice_language": DEFAULT_NOTICE_LANGUAGE,
            },
            headers=_auth(token),
        )

        assert written.json()["notice_version"] == CURRENT_NOTICE_VERSION
        assert written.json()["notice_language"] == DEFAULT_NOTICE_LANGUAGE
        # And who captured it: a staff-entered consent is legitimate and must stay visible as one.
        assert written.json()["source"] == "staff"

    async def test_a_waiter_cannot_record_a_consent(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        manager = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        waiter = await _sign_in(
            db_session, api_client, world, role="waiter", branches=("main",), label="waiter"
        )
        customer = await _create(api_client, manager, "9876544006")

        response = await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/consent",
            json={
                "purpose": "marketing",
                "granted": True,
                "notice_version": CURRENT_NOTICE_VERSION,
                "notice_language": DEFAULT_NOTICE_LANGUAGE,
            },
            headers=_auth(waiter),
        )

        assert response.status_code == 403, response.text


# --------------------------------------------------------------------------- erasure


class TestErasureKeepsTheMoney:
    async def test_erasure_leaves_revenue_totals_unchanged(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """modules.md's own acceptance criterion, and the one that would be catastrophic to get
        wrong: exercising a data right must not destroy a restaurant's books."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876544010", name="Ravi Kumar")
        for total in ("1240.00", "860.50"):
            await _settled_order(db_session, world.restaurants["main"], customer["id"], total)
        await db_session.flush()
        before = await db_session.scalar(
            select(func.coalesce(func.sum(Order.grand_total), 0)).where(
                Order.restaurant_id == world.restaurants["main"].id
            )
        )

        erased = await api_client.post(f"{CUSTOMERS}/{customer['id']}/erase", headers=_auth(token))

        assert erased.status_code == 200, erased.text
        after = await db_session.scalar(
            select(func.coalesce(func.sum(Order.grand_total), 0)).where(
                Order.restaurant_id == world.restaurants["main"].id
            )
        )
        assert after == before == Decimal("2100.50")
        # And the response says so, so the screen can show it and nobody takes it on trust.
        assert erased.json()["orders_retained"] == 2

    async def test_everything_that_names_a_person_is_gone(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(
            api_client,
            token,
            "9876544011",
            name="Ravi Kumar",
            email="ravi@example.test",
            birthday="1990-03-14",
        )
        await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/preferences",
            json={"type": "allergy", "value": "Peanuts", "is_critical": True},
            headers=_auth(token),
        )

        await api_client.post(f"{CUSTOMERS}/{customer['id']}/erase", headers=_auth(token))

        row = await db_session.get(Customer, uuid.UUID(customer["id"]))
        assert row is not None
        await db_session.refresh(row)
        assert row.name is None
        assert row.email is None
        assert row.birthday is None
        assert row.erased_at is not None
        # The phone becomes a placeholder rather than a null: the column is the natural key, and two
        # erased customers must not collide on it. It is deliberately not a number — nothing should
        # ever be able to dial it.
        assert row.phone.startswith("erased:")

        profile = await api_client.get(f"{CUSTOMERS}/{customer['id']}", headers=_auth(token))
        assert profile.json()["preferences"] == []
        assert profile.json()["is_erased"] is True

    async def test_the_consent_history_survives_the_erasure(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """What remains is "marketing was granted on this date and withdrawn on that one" against an
        id that no longer names anybody — which is the record proving the erasure was lawful."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876544012")
        await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/consent",
            json={
                "purpose": "marketing",
                "granted": True,
                "notice_version": CURRENT_NOTICE_VERSION,
                "notice_language": DEFAULT_NOTICE_LANGUAGE,
            },
            headers=_auth(token),
        )

        await api_client.post(f"{CUSTOMERS}/{customer['id']}/erase", headers=_auth(token))

        rows = (
            await db_session.scalars(
                select(CustomerConsent).where(
                    CustomerConsent.customer_id == uuid.UUID(customer["id"])
                )
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].notice_version == CURRENT_NOTICE_VERSION

    async def test_nothing_more_can_be_recorded_about_an_erased_person(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The erasure holding. Accepting a consent or a preference afterwards would be the right
        quietly not having been exercised."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876544013")
        await api_client.post(f"{CUSTOMERS}/{customer['id']}/erase", headers=_auth(token))

        consent = await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/consent",
            json={
                "purpose": "marketing",
                "granted": True,
                "notice_version": CURRENT_NOTICE_VERSION,
                "notice_language": DEFAULT_NOTICE_LANGUAGE,
            },
            headers=_auth(token),
        )
        edit = await api_client.patch(
            f"{CUSTOMERS}/{customer['id']}", json={"name": "Somebody"}, headers=_auth(token)
        )

        assert consent.status_code == 409, consent.text
        assert consent.json()["code"] == "customer.erased"
        assert edit.status_code == 409, edit.text

    async def test_erasing_twice_is_refused_readably(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876544014")
        await api_client.post(f"{CUSTOMERS}/{customer['id']}/erase", headers=_auth(token))

        again = await api_client.post(f"{CUSTOMERS}/{customer['id']}/erase", headers=_auth(token))

        assert again.status_code == 409, again.text
        assert again.json()["code"] == "customer.already_erased"

    async def test_two_erased_customers_do_not_collide(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The placeholder carries the id for exactly this reason. A blank or a shared sentinel
        would make the second erasure fail on the unique constraint — a data right refused because
        somebody else exercised theirs first."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        first = await _create(api_client, token, "9876544015")
        second = await _create(api_client, token, "9876544016")

        await api_client.post(f"{CUSTOMERS}/{first['id']}/erase", headers=_auth(token))
        response = await api_client.post(f"{CUSTOMERS}/{second['id']}/erase", headers=_auth(token))

        assert response.status_code == 200, response.text

    async def test_the_same_person_returning_is_a_new_customer(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """What erasure means, stated as a test because it is the consequence an owner should hear
        before pressing the button — and the screen says it in those words."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876544017", name="Ravi Kumar")
        await api_client.post(f"{CUSTOMERS}/{customer['id']}/erase", headers=_auth(token))

        again = await _create(api_client, token, "9876544017", name="Ravi Kumar")

        assert again["id"] != customer["id"]
        assert again["visit_count"] == 0

    async def test_the_erasure_is_audited(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """It destroys data and cannot be undone, so the record of who did it is the only thing that
        can answer the question afterwards."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876544018")

        await api_client.post(f"{CUSTOMERS}/{customer['id']}/erase", headers=_auth(token))

        logged = await db_session.scalar(
            text(
                "SELECT count(*) FROM audit_log WHERE action = 'customer.erase' AND entity_id = :id"
            ),
            {"id": uuid.UUID(customer["id"])},
        )
        assert logged == 1


# --------------------------------------------------------------------------- no PII in logs


async def test_no_phone_number_reaches_a_log_record(
    db_session: AsyncSession, api_client: AsyncClient, caplog: object
) -> None:
    """The Definition of Done says "no PII in logs", and this is the first module with real PII.

    The log records this module emits carry ids, purposes and counts — never a number, a name or an
    email. A phone number in a log line is a phone number in whatever ships logs off the box.
    """
    import logging

    world = await _world(db_session)
    token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))

    with caplog.at_level(logging.DEBUG):  # type: ignore[attr-defined]
        customer = await _create(api_client, token, "9876544020", name="Ravi Kumar")
        await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/consent",
            json={
                "purpose": "marketing",
                "granted": True,
                "notice_version": CURRENT_NOTICE_VERSION,
                "notice_language": DEFAULT_NOTICE_LANGUAGE,
            },
            headers=_auth(token),
        )
        await api_client.post(f"{CUSTOMERS}/{customer['id']}/erase", headers=_auth(token))

    # This module's own records, not the whole log: SQLAlchemy's echo would defeat any assertion
    # about every record ever emitted, and it is the application's own lines we control and ship.
    application = [record for record in caplog.records if record.name.startswith("app.")]  # type: ignore[attr-defined]
    assert application, "no application log records at all — this test would pass vacuously"

    for record in application:
        rendered = record.getMessage() + repr(record.__dict__)
        assert "9876544020" not in rendered, f"a phone number reached {record.name}"
        assert "Ravi Kumar" not in rendered, f"a customer's name reached {record.name}"


def test_the_erasure_placeholder_is_not_dialable() -> None:
    """A small thing with a real consequence: if the placeholder looked like a number, something
    downstream would eventually try to send a message to it."""
    from app.services.customers import _ERASED_PHONE

    placeholder = _ERASED_PHONE.format(customer_id=uuid.uuid4())

    assert not placeholder.replace("-", "").isdigit()
    assert placeholder.startswith("erased:")
