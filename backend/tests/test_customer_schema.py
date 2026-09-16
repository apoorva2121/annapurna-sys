"""Migration 0036 against a real Postgres, and the constraints that are the module's real rules.

A check constraint here is not decoration. Several of M10's decisions are *only* true because the
database refuses the alternative, and each of those gets a test that proves the refusal rather than
the happy path — a constraint nobody has seen fire is a constraint that might be spelled wrong.

The two that matter most:

**One feedback per order** is a partial unique index, not a screen rule. "Never ask twice in one
visit" (`docs/customer-experience.md`) survives a guest tapping Send twice on a slow network only
because the second insert cannot land.

**A resolved complaint has a resolution.** `docs/customer-experience.md`: "A logged complaint that
nobody resolves is worse than no system." A dropdown that can be set to Resolved with an empty box
is how a complaint system becomes paperwork, so the database refuses it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customers import (
    Complaint,
    Customer,
    CustomerConsent,
    CustomerPreference,
    Feedback,
)
from app.models.tenancy import Organization, Restaurant


async def _org(session: AsyncSession) -> tuple[Organization, Restaurant]:
    organization = Organization(name="Spice Garden Group", slug=f"sg-{uuid.uuid4().hex[:8]}")
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id, name="Koregaon Park", code=f"KP{uuid.uuid4().hex[:6]}"
    )
    session.add(restaurant)
    await session.flush()
    return organization, restaurant


async def _order(
    session: AsyncSession, restaurant: Restaurant, number: str, **extra: object
) -> uuid.UUID:
    """A minimal open order. Written in SQL rather than through the model because this file tests
    the *schema*, and going through M07's service would test M07."""
    order_id = uuid.uuid4()
    columns = {
        "id": order_id,
        "restaurant_id": restaurant.id,
        "order_number": number,
        "type": "dine_in",
        "channel": "pos",
        "status": "open",
        "business_date": date(2026, 9, 16),
        **extra,
    }
    names = ", ".join(f'"{name}"' for name in columns)
    values = ", ".join(f":{name}" for name in columns)
    # Column names come from this function's own literal dict, never from a caller's string, so the
    # interpolation is a shape rather than an injection point. `extra`'s *values* are still bound.
    statement = (
        f'INSERT INTO "order" ({names}, placed_at, subtotal, discount_total, charge_total, '  # noqa: S608
        f"tax_total, round_off, grand_total) "
        f"VALUES ({values}, now(), 0, 0, 0, 0, 0, 0)"
    )
    await session.execute(text(statement), columns)
    return order_id


async def _customer(session: AsyncSession, organization: Organization, phone: str) -> Customer:
    customer = Customer(organization_id=organization.id, phone=phone)
    session.add(customer)
    await session.flush()
    return customer


# --------------------------------------------------------------------------- the tables exist


async def test_the_six_tables_arrive(db_session: AsyncSession) -> None:
    """`docs/schema.md` §9 lists five and this module ships six: `customer_consent` is M10's
    addition, because §B2's standard — one row per purpose, never a single boolean — cannot be met
    by any of the five."""
    rows = await db_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ANY(:names)"
        ),
        {
            "names": [
                "customer",
                "customer_preference",
                "customer_consent",
                "feedback",
                "feedback_line",
                "complaint",
            ]
        },
    )

    assert len(rows.all()) == 6


async def test_the_order_finally_points_at_a_customer(db_session: AsyncSession) -> None:
    """M07 left `order.customer_id` a bare column with a comment saying the table was M10's. It is
    a real foreign key from here, which is the difference between a convention and a guarantee."""
    found = await db_session.scalar(
        text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_name = 'fk_order_customer' AND constraint_type = 'FOREIGN KEY'"
        )
    )

    assert found == 1


async def test_every_table_gets_a_distinct_guest_slug(db_session: AsyncSession) -> None:
    """The migration backfills row by row rather than trusting a volatile column default.

    A slug is a public credential and "probably distinct" is the wrong phrase for one, so the
    migration runs an explicit UPDATE. This proves the backfill did what the comment claims.
    """
    slugs = (await db_session.execute(text("SELECT guest_slug FROM restaurant_table"))).scalars()
    values = list(slugs)

    assert all(value for value in values)
    assert len(set(values)) == len(values)


# --------------------------------------------------------------------------- tenancy


async def test_a_preference_cannot_belong_to_another_organizations_customer(
    db_session: AsyncSession,
) -> None:
    """The composite tenant key doing its job. A customer is the organization's, so a preference
    carries the organization too and the pair must resolve — nothing in the database permits a
    preference pointing across the boundary."""
    spice, _ = await _org(db_session)
    tandoor, _ = await _org(db_session)
    theirs = await _customer(db_session, tandoor, "9876500001")

    db_session.add(
        CustomerPreference(
            organization_id=spice.id, customer_id=theirs.id, type="allergy", value="Peanuts"
        )
    )

    with pytest.raises(IntegrityError, match="fk_customer_preference_customer_tenant"):
        await db_session.flush()


async def test_one_phone_is_one_customer_within_an_organization(db_session: AsyncSession) -> None:
    organization, _ = await _org(db_session)
    await _customer(db_session, organization, "9876500002")

    db_session.add(Customer(organization_id=organization.id, phone="9876500002"))

    with pytest.raises(IntegrityError, match="uq_customer_organization_phone"):
        await db_session.flush()


async def test_the_same_phone_in_two_organizations_is_two_people(db_session: AsyncSession) -> None:
    """Deliberate, and the other half of the rule above. Two unrelated restaurants may both know
    the same number, and neither can see the other's row."""
    spice, _ = await _org(db_session)
    tandoor, _ = await _org(db_session)

    await _customer(db_session, spice, "9876500003")
    await _customer(db_session, tandoor, "9876500003")

    count = await db_session.scalar(
        select(Customer.id).where(Customer.phone == "9876500003").limit(2)
    )
    assert count is not None


# --------------------------------------------------------------------------- the rules that bite


async def test_only_one_feedback_can_exist_for_an_order(db_session: AsyncSession) -> None:
    """ "Never ask twice in one visit", as an index rather than a screen rule.

    The service answers a second submission with the first row; this is what guarantees there is
    only ever one to answer with.
    """
    _, restaurant = await _org(db_session)
    order_id = await _order(db_session, restaurant, "1")
    for _ in range(2):
        db_session.add(
            Feedback(
                restaurant_id=restaurant.id,
                order_id=order_id,
                food_rating=5,
                source="qr",
                submitted_at=datetime.now(UTC),
                business_date=date(2026, 9, 16),
            )
        )

    with pytest.raises(IntegrityError, match="uq_feedback_order"):
        await db_session.flush()


async def test_feedback_that_says_nothing_is_refused(db_session: AsyncSession) -> None:
    """A row with no answer in it cost somebody three taps and told the restaurant nothing."""
    _, restaurant = await _org(db_session)

    db_session.add(
        Feedback(
            restaurant_id=restaurant.id,
            source="qr",
            submitted_at=datetime.now(UTC),
            business_date=date(2026, 9, 16),
        )
    )

    with pytest.raises(IntegrityError, match="ck_feedback_says_something"):
        await db_session.flush()


async def test_a_complaint_cannot_be_resolved_with_an_empty_resolution(
    db_session: AsyncSession,
) -> None:
    """`docs/customer-experience.md`: a logged complaint nobody resolves is worse than no system.
    The database is where that stops being an aspiration."""
    _, restaurant = await _org(db_session)

    db_session.add(
        Complaint(
            restaurant_id=restaurant.id,
            reference="1",
            category="food_quality",
            severity="high",
            description="The biryani was cold.",
            status="resolved",
            resolved_at=datetime.now(UTC),
            business_date=date(2026, 9, 16),
            financial_year="2026-27",
        )
    )

    with pytest.raises(IntegrityError, match="ck_complaint_resolution_pair"):
        await db_session.flush()


async def test_a_complaint_reference_is_unique_within_a_year_and_reused_across_years(
    db_session: AsyncSession,
) -> None:
    """The number a manager reads out on the phone. Short, per restaurant, per financial year — the
    same shape as the invoice series, so it restarts small rather than reaching six digits."""
    _, restaurant = await _org(db_session)

    def complaint(reference: str, year: str) -> Complaint:
        return Complaint(
            restaurant_id=restaurant.id,
            reference=reference,
            category="service",
            severity="low",
            description="Nobody came to the table.",
            status="open",
            business_date=date(2026, 9, 16),
            financial_year=year,
        )

    db_session.add(complaint("47", "2026-27"))
    db_session.add(complaint("47", "2027-28"))
    await db_session.flush()

    db_session.add(complaint("47", "2026-27"))
    with pytest.raises(IntegrityError, match="uq_complaint_reference_per_year"):
        await db_session.flush()


async def test_a_consent_purpose_outside_the_four_is_refused(db_session: AsyncSession) -> None:
    """`docs/compliance-rules.md` §B2's purpose limitation, as a constraint. A purpose nobody
    designed is a purpose nobody wrote a notice for."""
    organization, _ = await _org(db_session)
    customer = await _customer(db_session, organization, "9876500004")

    db_session.add(
        CustomerConsent(
            organization_id=organization.id,
            customer_id=customer.id,
            purpose="resell_to_anybody",
            granted=True,
            notice_version="2026-09-16.1",
            notice_language="en",
            source="qr",
            occurred_at=datetime.now(UTC),
        )
    )

    with pytest.raises(IntegrityError, match="ck_customer_consent_purpose"):
        await db_session.flush()


async def test_an_order_cannot_carry_half_a_guest_token(db_session: AsyncSession) -> None:
    """A hash with no expiry is a credential that never dies, and an expiry with no hash is a row
    that means nothing. Both or neither."""
    _, restaurant = await _org(db_session)

    with pytest.raises(IntegrityError, match="ck_order_guest_token_pair"):
        await _order(db_session, restaurant, "2", guest_token_hash="abc")  # noqa: S106
