"""The opening stock, and the two signals it plants on purpose.

`docs/seed-data.md`'s principle is that a demo requiring the demonstrator to first create the
problem is a demo of an empty product. So the seed arrives with a near-expiry batch and a negative
position already in it, and these tests are what stop either quietly disappearing.

The negative is the one that matters. It is planted by *consuming* rather than by writing a negative
movement, because that is how it happens in a kitchen — the onions went into the pot and the
delivery note never reached the system — and because a directly-written negative would not prove the
shortfall path works.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MovementType
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.inventory import StockMovement
from app.models.stock import StockItem
from app.models.tenancy import Organization, Restaurant
from app.repositories.inventory import StockBatchRepository, StockMovementRepository
from app.seed.inventory import seed_inventory


async def _restaurant_with_items(session: AsyncSession, slug: str) -> Restaurant:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name=slug.title(),
        code=slug[:3].upper(),
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
    )
    session.add(restaurant)
    await session.flush()
    session.add(
        Employee(
            organization_id=organization.id,
            employee_code=f"{slug[:3].upper()}-1",
            full_name="Store Manager",
            joined_on=date(2026, 1, 1),
            employment_type="full_time",
            is_active=True,
        )
    )
    for code, cost in (("PANEER", "0.360000"), ("ONION", "0.040000"), ("OIL", "0.120000")):
        session.add(
            StockItem(
                restaurant_id=restaurant.id,
                kind="ingredient",
                code=code,
                name=code.title(),
                base_unit="g",
                current_unit_cost=Decimal(cost),
                is_active=True,
            )
        )
    await session.flush()
    return restaurant


async def test_it_plants_a_negative_position(db_session: AsyncSession) -> None:
    """The banner must be on screen the first time anybody opens the app.

    Not a path somebody has to discover: a restaurant that has never kept records will see this in
    week one, and the demo is worth nothing if it cannot show what the product does about it.
    """
    restaurant = await _restaurant_with_items(db_session, "seed-negative")

    summary = await seed_inventory(db_session)

    assert summary.negatives_planted == 1
    scope = TenantScope(organization_id=restaurant.organization_id, restaurant_id=restaurant.id)
    rows = await StockMovementRepository(db_session, scope).on_hand()
    negatives = [row for row in rows if row.quantity < 0]
    assert [row.code for row in negatives] == ["ONION"]


async def test_the_negative_is_reached_by_consuming_not_by_writing_one(
    db_session: AsyncSession,
) -> None:
    """A directly-written negative movement would look identical on the screen and prove nothing.

    Consuming means the shortfall path actually ran — the placeholder batch, the note, and the
    arithmetic that leaves the position short.
    """
    await _restaurant_with_items(db_session, "seed-how")

    await seed_inventory(db_session)

    notes = (
        await db_session.scalars(
            select(StockMovement.note).where(StockMovement.type == MovementType.CONSUMPTION)
        )
    ).all()
    assert any("without a recorded receipt" in (note or "") for note in notes)


async def test_it_plants_something_near_expiry(db_session: AsyncSession) -> None:
    restaurant = await _restaurant_with_items(db_session, "seed-expiry")

    await seed_inventory(db_session)

    scope = TenantScope(organization_id=restaurant.organization_id, restaurant_id=restaurant.id)
    # A far-future cutoff, so this asserts "exactly one batch carries an expiry date at all"
    # rather than depending on today's date — which is what the seed actually promises.
    dated = await StockBatchRepository(db_session, scope).expiring_before(date(2099, 1, 1))

    assert [batch.remaining for batch in dated] == [Decimal("8400.0000")]


async def test_running_it_twice_does_not_stack_a_second_week_of_stock(
    db_session: AsyncSession,
) -> None:
    """`make seed` is run repeatedly during development.

    The guard is "any movement exists", not a marker row, because a ledger with rows in it has
    already been used — and re-seeding somebody's real storeroom would corrupt their position
    rather than merely duplicating a fixture.
    """
    await _restaurant_with_items(db_session, "seed-twice")

    first = await seed_inventory(db_session)
    before = await db_session.scalar(select(func.count()).select_from(StockMovement))

    second = await seed_inventory(db_session)
    after = await db_session.scalar(select(func.count()).select_from(StockMovement))

    assert first.batches_created > 0
    assert second.created_nothing
    assert before == after


async def test_a_restaurant_with_no_stock_items_is_skipped_rather_than_failing(
    db_session: AsyncSession,
) -> None:
    organization = Organization(name="Empty", slug="empty-seed")
    db_session.add(organization)
    await db_session.flush()
    db_session.add(Restaurant(organization_id=organization.id, name="Empty", code="EMP"))
    await db_session.flush()

    summary = await seed_inventory(db_session)

    assert summary.created_nothing
