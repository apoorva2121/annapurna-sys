"""Allocating the next order number, when the day already holds a number it did not write.

**The bug this file exists for.** `next_order_number` took `MAX(CAST(order_number AS INTEGER))`,
which assumes every order number on a business date is a plain integer. `order_number` is a `Text`
column, and the M15 generator wrote `260920-0048` — a date and a sequence. Postgres cannot cast
that to an integer, so the statement raised and **opening a table returned 500** on any restaurant
whose data came from the generator. Reported from the floor as *"not able to assign any waiter to
any table"*, which is what a crash on `POST /orders` looks like to somebody standing at a table.

Two properties are worth pinning separately, because fixing only one leaves the other free to
break again:

1. **The allocator never raises on a number it cannot parse.** The column is text, and a restored
   row, an imported history or a hand-corrected number must not be able to stop the till. This is
   the property that keeps the product running.
2. **The generator writes what the product writes.** That is the root cause rather than the
   symptom: a demo whose data does not look like real data hides exactly this class of bug, which
   is the one thing a demo is for.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import OrderStatus, OrderType
from app.core.tenancy import TenantScope
from app.models.orders import Order
from app.models.tenancy import Organization, Restaurant
from app.repositories.orders import OrderRepository

BUSINESS_DATE = date(2026, 9, 20)


async def _scope(session: AsyncSession, slug: str) -> TenantScope:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id, name=slug.title(), code=slug[:3].upper()
    )
    session.add(restaurant)
    await session.flush()
    return TenantScope(organization_id=organization.id, restaurant_id=restaurant.id)


async def _order(session: AsyncSession, scope: TenantScope, number: str) -> Order:
    order = Order(
        id=uuid.uuid4(),
        restaurant_id=scope.restaurant_id,
        order_number=number,
        type=OrderType.DINE_IN,
        status=OrderStatus.OPEN,
        placed_at=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
        business_date=BUSINESS_DATE,
    )
    session.add(order)
    await session.flush()
    return order


async def test_allocates_past_a_generator_written_number(db_session: AsyncSession) -> None:
    """The regression. A date-prefixed number on the day must not stop the next order."""
    scope = await _scope(db_session, "koregaon")
    await _order(db_session, scope, "260920-0048")

    # Before the fix this raised asyncpg InvalidTextRepresentationError:
    #   invalid input syntax for type integer: "260920-0048"
    number = await OrderRepository(db_session, scope).next_order_number(BUSINESS_DATE)

    assert number.isdigit(), f"an allocated number must be plain digits, got {number!r}"


async def test_ignores_an_unparseable_number_rather_than_counting_it(
    db_session: AsyncSession,
) -> None:
    """A number it cannot read is skipped, not guessed at.

    Counting `260920-0048` as a sequence would allocate 260920-0049's worth of number — a six-digit
    order number that no waiter is going to call across a kitchen, which is the whole reason the
    counter resets daily.
    """
    scope = await _scope(db_session, "tandoor")
    await _order(db_session, scope, "260920-0048")
    await _order(db_session, scope, "7")

    number = await OrderRepository(db_session, scope).next_order_number(BUSINESS_DATE)

    assert number == "8"


async def test_starts_at_one_on_a_day_with_only_unparseable_numbers(
    db_session: AsyncSession,
) -> None:
    """A seeded day the product has never written to starts its own count at one.

    "1" cannot collide with "260920-0001" — `uq_order_number_per_day` is over the *text*, and the
    two are different strings.
    """
    scope = await _scope(db_session, "deccan")
    await _order(db_session, scope, "260920-0001")
    await _order(db_session, scope, "260920-0002")

    assert await OrderRepository(db_session, scope).next_order_number(BUSINESS_DATE) == "1"


async def test_still_counts_normally_when_every_number_is_plain(
    db_session: AsyncSession,
) -> None:
    """Guards the guard: the fix must not change the behaviour it was not about."""
    scope = await _scope(db_session, "camp")
    for number in ("1", "2", "3"):
        await _order(db_session, scope, number)

    assert await OrderRepository(db_session, scope).next_order_number(BUSINESS_DATE) == "4"


async def test_counts_only_this_business_day(db_session: AsyncSession) -> None:
    """The counter resets daily, which is why a waiter can call it out at all."""
    scope = await _scope(db_session, "aundh")
    yesterday = Order(
        id=uuid.uuid4(),
        restaurant_id=scope.restaurant_id,
        order_number="94",
        type=OrderType.DINE_IN,
        status=OrderStatus.OPEN,
        placed_at=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
        business_date=date(2026, 9, 19),
    )
    db_session.add(yesterday)
    await db_session.flush()

    assert await OrderRepository(db_session, scope).next_order_number(BUSINESS_DATE) == "1"


@pytest.mark.parametrize(
    "number",
    ["260920-0048", "", "  ", "12a", "-3", "1.5", "٤٢"],
)
async def test_survives_anything_the_text_column_can_hold(
    db_session: AsyncSession, number: str
) -> None:
    """The column is `Text`. Nothing a person or an import can put in it may stop the till.

    `٤٢` is Arabic-Indic for 42: Python's `str.isdigit()` says True for it and Postgres will not
    cast it, which is exactly the kind of disagreement that puts a crash back.
    """
    scope = await _scope(db_session, f"shop{abs(hash(number)) % 10_000}")
    await _order(db_session, scope, number)

    allocated = await OrderRepository(db_session, scope).next_order_number(BUSINESS_DATE)

    assert allocated.isascii() and allocated.isdigit()
