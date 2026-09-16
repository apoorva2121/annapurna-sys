"""The regulars, ratings and complaints the seed plants, so M10's screens open on something.

`docs/seed-data.md`'s principle, once more: a demo that opens on an empty customer list and a
complaint board with nothing on it is a demo of an empty product. These tests stop the planted state
quietly disappearing.

Each one is about a *state that cannot be demonstrated without it* rather than about a row count. A
consent that was granted and withdrawn is the only way to see that the ledger keeps history; a
resolved complaint whose customer never came back is the only way to see that `customer_returned`
can be false rather than merely null.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customers import Complaint, Customer, CustomerConsent, CustomerPreference, Feedback
from app.models.orders import Order
from app.models.tenancy import Restaurant
from app.seed.customers import seed_customer_feedback, seed_customers
from app.seed.identity import seed_identity
from app.seed.inventory import seed_inventory
from app.seed.menu import seed_menu
from app.seed.orders import seed_orders
from app.seed.setup import seed_setup
from app.seed.stock import seed_stock


@pytest.fixture
async def seeded(db_session: AsyncSession) -> AsyncSession:
    """The world up to the orders seeder — but **not** including it.

    The people come before the orders and their feedback comes after, because a customer goes on a
    bill while it is open: a settled order is immutable and a trigger enforces it. Each test runs
    the pass it is about.
    """
    await seed_identity(db_session)
    await seed_setup(db_session)
    await seed_menu(db_session)
    await seed_stock(db_session)
    await seed_inventory(db_session)
    return db_session


async def _with_orders(session: AsyncSession) -> None:
    """The orders seeder, run after the people exist so the settled bill can carry one."""
    await seed_orders(session)


async def _koregaon(session: AsyncSession) -> Restaurant:
    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == "SG_KOREGAON"))
    assert restaurant is not None
    return restaurant


async def test_the_customer_list_opens_on_regulars_rather_than_nothing(
    seeded: AsyncSession,
) -> None:
    summary = await seed_customers(seeded)
    restaurant = await _koregaon(seeded)

    assert summary.customers_created > 0
    customers = (
        await seeded.scalars(
            select(Customer).where(Customer.organization_id == restaurant.organization_id)
        )
    ).all()
    assert len(customers) >= 3, "too few people to show a list that looks like a real one"
    assert any(customer.name is None for customer in customers), (
        "everybody in the seed has a name, and plenty of real customers do not"
    )


async def test_somebody_has_an_allergy_the_kitchen_would_be_told_about(
    seeded: AsyncSession,
) -> None:
    """`customer_preference.is_critical` exists to reach the kitchen, and a seed with no critical
    preference cannot show that without somebody constructing one."""
    await seed_customers(seeded)
    restaurant = await _koregaon(seeded)

    critical = (
        await seeded.scalars(
            select(CustomerPreference).where(
                CustomerPreference.organization_id == restaurant.organization_id,
                CustomerPreference.is_critical.is_(True),
            )
        )
    ).all()

    assert critical


async def test_a_non_critical_preference_sits_beside_it(seeded: AsyncSession) -> None:
    """The pair is the point. A chef who reads a spice level beside an allergy learns to skim both,
    which is exactly what decision 9 is about — so the demo has to show the two being treated
    differently."""
    await seed_customers(seeded)
    restaurant = await _koregaon(seeded)

    ordinary = (
        await seeded.scalars(
            select(CustomerPreference).where(
                CustomerPreference.organization_id == restaurant.organization_id,
                CustomerPreference.is_critical.is_(False),
            )
        )
    ).all()

    assert ordinary


async def test_one_consent_was_granted_and_then_withdrawn(seeded: AsyncSession) -> None:
    """The ledger's whole shape — append-only, current state being the latest row — is invisible
    until one purpose has two rows."""
    await seed_customers(seeded)
    restaurant = await _koregaon(seeded)

    rows = (
        await seeded.scalars(
            select(CustomerConsent)
            .where(
                CustomerConsent.organization_id == restaurant.organization_id,
                CustomerConsent.purpose == "marketing",
            )
            .order_by(CustomerConsent.occurred_at)
        )
    ).all()

    assert [row.granted for row in rows] == [True, False]


async def test_every_seeded_consent_names_a_notice_somebody_could_read(
    seeded: AsyncSession,
) -> None:
    """A seeded consent with a made-up version would be a demo of a record that proves nothing."""
    from app.core.consent import CURRENT_NOTICE_VERSION

    await seed_customers(seeded)
    restaurant = await _koregaon(seeded)

    rows = (
        await seeded.scalars(
            select(CustomerConsent).where(
                CustomerConsent.organization_id == restaurant.organization_id
            )
        )
    ).all()

    assert rows
    assert all(row.notice_version == CURRENT_NOTICE_VERSION for row in rows)


async def test_most_bills_have_no_feedback(seeded: AsyncSession) -> None:
    """`docs/seed-data.md` rule 3: plausible, not perfect. The honest response rate for a QR on a
    bill is low, and a seed where every bill was rated would teach the opposite."""
    seeded_people = await seed_customers(seeded)
    await _with_orders(seeded)
    await seed_customer_feedback(seeded, seeded_people)
    restaurant = await _koregaon(seeded)

    orders = (
        await seeded.scalars(select(Order.id).where(Order.restaurant_id == restaurant.id))
    ).all()
    rated = (
        await seeded.scalars(select(Feedback.id).where(Feedback.restaurant_id == restaurant.id))
    ).all()

    assert rated, "no feedback at all, so the day view cannot be demonstrated"
    assert len(rated) < len(orders), "every order was rated, which is not what happens"


async def test_one_complaint_is_open_and_one_is_resolved_without_a_return(
    seeded: AsyncSession,
) -> None:
    """`customer_returned` is derived, and a seed where it is always null or always true says
    nothing about whether the derivation works."""
    seeded_people = await seed_customers(seeded)
    await _with_orders(seeded)
    await seed_customer_feedback(seeded, seeded_people)
    restaurant = await _koregaon(seeded)

    complaints = (
        await seeded.scalars(select(Complaint).where(Complaint.restaurant_id == restaurant.id))
    ).all()
    by_status = {complaint.status for complaint in complaints}

    assert "open" in by_status
    assert "resolved" in by_status

    resolved = next(complaint for complaint in complaints if complaint.status == "resolved")
    assert resolved.resolution is not None
    assert resolved.resolved_at is not None
    later = await seeded.scalar(
        select(Order.id).where(
            Order.customer_id == resolved.customer_id,
            Order.placed_at > resolved.resolved_at,
        )
    )
    assert later is None, (
        "the resolved complaint's customer came back, so 'not recovered' cannot be demonstrated"
    )


async def test_seeding_again_creates_no_second_set_of_people(seeded: AsyncSession) -> None:
    """A customer in a restaurant is somebody a real person typed in. Re-running the seed must not
    double them — and must not double the complaints hanging off them either."""
    first = await seed_customers(seeded)
    second = await seed_customers(seeded)

    assert first.customers_created > 0
    assert second.customers_created == 0
    assert second.feedback_created == 0


async def test_the_regulars_are_on_real_bills_rather_than_carrying_a_typed_number(
    seeded: AsyncSession,
) -> None:
    """The M10 review's finding, in the seed.

    `customer.visit_count` is a column nothing maintains, so the screens count settled bills. A
    seeder writing 7 into that column would have written a number nobody reads — so it attaches the
    regulars to the bills the orders seeder already settled instead. "Seventh visit" becomes
    something that happened rather than something typed.
    """
    await seed_customers(seeded)
    await _with_orders(seeded)
    restaurant = await _koregaon(seeded)

    attached = (
        await seeded.scalars(
            select(Order.customer_id).where(
                Order.restaurant_id == restaurant.id,
                Order.settled_at.is_not(None),
                Order.customer_id.is_not(None),
            )
        )
    ).all()

    assert attached, "no settled bill names a customer, so nobody has a visit history"


async def test_the_seed_writes_no_visit_count_of_its_own(seeded: AsyncSession) -> None:
    """A number in a column nothing reads is worse than no number: it looks maintained."""
    await seed_customers(seeded)
    restaurant = await _koregaon(seeded)

    customers = (
        await seeded.scalars(
            select(Customer).where(Customer.organization_id == restaurant.organization_id)
        )
    ).all()

    assert customers
    assert all(customer.visit_count == 0 for customer in customers)
