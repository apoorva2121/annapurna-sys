"""Two cooks, one batch of paneer, at the same instant. Acceptance criterion 2.

This is the hardest thing in M05 and the one place a green test would be most misleading. The
ordinary `db_session` fixture wraps everything in a single transaction, so two "concurrent"
consumptions inside it are not concurrent at all — they are sequential statements that cannot
contend, and a test written on it would pass against code with no locking whatsoever.

So these run on `fresh_database`: a real database, two real connections, two real transactions,
committing for real. That is the only arrangement in which `FOR UPDATE` means anything, and
guardrail G-2 exists because this project has already shipped a green test that did not work.
"""

from __future__ import annotations

import asyncio
from datetime import date, time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.actor import Actor
from app.core.enums import MovementBasis
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.inventory import StockMovement
from app.models.stock import StockItem
from app.models.tenancy import Organization, Restaurant
from app.services.inventory import InventoryService


async def _seed(session: AsyncSession) -> tuple[TenantScope, Actor, StockItem]:
    organization = Organization(name="Concurrency", slug="concurrency")
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name="Concurrency",
        code="CON",
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
    )
    session.add(restaurant)
    await session.flush()
    employee = Employee(
        organization_id=organization.id,
        employee_code="CON-1",
        full_name="Cook",
        joined_on=date(2026, 1, 1),
        employment_type="full_time",
        is_active=True,
    )
    session.add(employee)
    await session.flush()
    item = StockItem(
        restaurant_id=restaurant.id,
        kind="ingredient",
        code="PANEER",
        name="Paneer",
        base_unit="g",
        current_unit_cost=Decimal("0.360000"),
        is_active=True,
    )
    session.add(item)
    await session.flush()

    scope = TenantScope(organization_id=organization.id, restaurant_id=restaurant.id)
    actor = Actor(
        employee_id=employee.id,
        organization_id=organization.id,
        restaurant_id=restaurant.id,
        full_name="Cook",
        permissions=frozenset(),
        rank=10,
    )
    return scope, actor, item


async def test_two_concurrent_consumptions_do_not_oversell(fresh_database: str) -> None:
    """Both take 600 g from a batch holding 1000 g. Exactly one must be told it came up short.

    **The timing here is deliberate, and an earlier version of this test was worthless without
    it.** Written as a plain `asyncio.gather` of two consumptions, the two coroutines did not in
    fact interleave at the moment that matters — the first finished and committed before the second
    read — so the test passed identically with the row lock removed. A concurrency test that passes
    against unlocked code is not a test.

    So the contention is forced: the first transaction reads, then *holds its transaction open*
    while the second starts and tries to read the same batch.

      with the lock     the second SELECT blocks until the first commits, then sees 400 g left
                        and reports a 200 g shortfall
      without the lock  the second SELECT returns the stale 1000 g immediately, believes itself
                        fully covered, and reports no shortfall at all

    The total is -200 either way, which is why asserting the total alone proves nothing. The
    discriminating assertion is the pair of shortfalls, and the dangerous failure is the silent
    one: a position that is wrong with nothing saying so.
    """
    engine = create_async_engine(fresh_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as setup:
            scope, actor, item = await _seed(setup)
            service = InventoryService(setup, scope)
            await service.receive_stock(
                actor,
                stock_item_id=item.id,
                quantity=Decimal("1000"),
                unit_cost=Decimal("0.36"),
            )
            await setup.commit()
            item_id = item.id

        async def take(quantity: str, *, start_after: float, hold_for: float) -> Decimal:
            await asyncio.sleep(start_after)
            async with factory() as session:
                result = await InventoryService(session, scope).consume(
                    actor,
                    stock_item_id=item_id,
                    quantity=Decimal(quantity),
                    basis=MovementBasis.THEORETICAL,
                )
                # Hold the transaction open so the other caller is still inside its own read when
                # this one has taken the lock but not yet released it.
                await asyncio.sleep(hold_for)
                await session.commit()
                return result.shortfall

        first, second = await asyncio.gather(
            take("600", start_after=0.0, hold_for=0.6),
            take("600", start_after=0.15, hold_for=0.0),
        )

        async with factory() as check:
            total = await check.scalar(
                select(func.coalesce(func.sum(StockMovement.quantity_delta), 0))
            )

        # 1000 received, 1200 consumed. True with or without locking, hence not the real assertion.
        assert Decimal(str(total)) == Decimal("-200.0000")
        # This is the one that fails when the lock is removed.
        assert sorted([first, second]) == [Decimal("0"), Decimal("200")]
    finally:
        await engine.dispose()


async def test_concurrent_receipts_do_not_collide_on_batch_code(fresh_database: str) -> None:
    """Generated batch codes carry a random tail precisely so two deliveries of the same item on
    the same day do not violate `uq_stock_batch_restaurant_code`."""
    engine = create_async_engine(fresh_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as setup:
            scope, actor, item = await _seed(setup)
            await setup.commit()
            item_id = item.id

        async def receive() -> None:
            async with factory() as session:
                await InventoryService(session, scope).receive_stock(
                    actor,
                    stock_item_id=item_id,
                    quantity=Decimal("100"),
                    unit_cost=Decimal("0.36"),
                )
                await session.commit()

        await asyncio.gather(*(receive() for _ in range(5)))

        async with factory() as check:
            total = await check.scalar(
                select(func.coalesce(func.sum(StockMovement.quantity_delta), 0))
            )
        assert Decimal(str(total)) == Decimal("500.0000")
    finally:
        await engine.dispose()
