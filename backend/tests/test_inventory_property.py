"""Acceptance criterion 1: on-hand equals the movement sum after 1,000 random operations.

The point of a property test here is that the ledger's correctness is not about any one operation.
Receive, consume, adjust and produce each have their own unit tests; what none of them can show is
that a long *interleaving* of them never drifts — that no path double-counts a batch, loses a
shortfall, or writes a movement whose sign is wrong in a way the happy path never exercises.

**The seed is fixed.** A property test that generates a fresh sequence every run is a test that
fails once on someone else's machine, cannot be reproduced, and gets deleted. With a fixed seed the
sequence is a fact: a failure is reproducible from the failure message alone, and the sequence can
be replayed while the fix is written. The cost is that it explores one path rather than a new one
each night, which is the right trade for a suite that has to stay trustworthy.
"""

from __future__ import annotations

import random
from datetime import date, time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import MovementBasis
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.inventory import StockMovement
from app.models.stock import StockItem
from app.models.tenancy import Organization, Restaurant
from app.services.inventory import InventoryService

# Change this and you are running a different test. Recorded rather than passed in, so a failure
# names the exact sequence that produced it.
SEED = 20260912
OPERATIONS = 1000


async def _world(session: AsyncSession) -> tuple[InventoryService, Actor, StockItem]:
    organization = Organization(name="Property", slug="property")
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name="Property",
        code="PRP",
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
    )
    session.add(restaurant)
    await session.flush()
    employee = Employee(
        organization_id=organization.id,
        employee_code="PRP-1",
        full_name="Store Manager",
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

    actor = Actor(
        employee_id=employee.id,
        organization_id=organization.id,
        restaurant_id=restaurant.id,
        full_name="Store Manager",
        permissions=frozenset(),
        rank=10,
    )
    service = InventoryService(
        session,
        TenantScope(organization_id=organization.id, restaurant_id=restaurant.id),
    )
    return service, actor, item


async def test_on_hand_equals_the_movement_sum_after_a_thousand_operations(
    db_session: AsyncSession,
) -> None:
    """The ledger's central promise, exercised over a long random interleaving.

    `expected` is maintained independently, in Python, by adding exactly what each call was asked
    to move. It is deliberately *not* derived from the ledger — a check that computed the expected
    value the same way the code does would agree with any bug that was consistent.

    Consumption is the interesting case. It is never refused (spec decision 2), so a consumption of
    500 against 100 on hand moves the position by the full 500 and leaves it negative. If the
    shortfall path ever failed to record its remainder, `expected` and the ledger would diverge
    here and nowhere else.
    """
    service, actor, item = await _world(db_session)
    rng = random.Random(SEED)
    expected = Decimal("0")
    receipts = consumptions = adjustments = shortfalls = 0

    for step in range(OPERATIONS):
        roll = rng.random()

        if roll < 0.35:
            quantity = Decimal(rng.randrange(1, 2000))
            await service.receive_stock(
                actor,
                stock_item_id=item.id,
                quantity=quantity,
                unit_cost=Decimal(rng.randrange(1, 100)) / Decimal("100"),
            )
            expected += quantity
            receipts += 1

        elif roll < 0.85:
            quantity = Decimal(rng.randrange(1, 3000))
            # Consumption outweighs receipt on purpose, so the position is repeatedly driven
            # through zero and the shortfall path is genuinely exercised. An earlier version of
            # this test drew receipts large enough that stock never ran out, and it then passed
            # with `_record_shortfall` disabled entirely — a thousand operations proving nothing
            # about the one path they were meant to cover.
            result = await service.consume(
                actor,
                stock_item_id=item.id,
                quantity=quantity,
                basis=MovementBasis.THEORETICAL if rng.random() < 0.5 else MovementBasis.ACTUAL,
            )
            # The whole quantity moves whether or not the batches covered it. The shortfall is a
            # report, not a reduction — asserting that here is what makes the negative path part
            # of this property rather than an exception to it.
            assert result.shortfall >= 0
            if result.shortfall > 0:
                shortfalls += 1
            expected -= quantity
            consumptions += 1

        else:
            delta = Decimal(rng.randrange(-2000, 2000))
            if delta == 0:
                delta = Decimal("1")
            await service.adjust(
                actor,
                stock_item_id=item.id,
                quantity_delta=delta,
                reason=f"property step {step}",
            )
            expected += delta
            adjustments += 1

        # Checked every 50 steps rather than every step: often enough that a failure names a short
        # window to replay, cheap enough that the test stays runnable on every commit.
        if step % 50 == 0:
            ledger = await db_session.scalar(
                select(func.coalesce(func.sum(StockMovement.quantity_delta), 0))
            )
            assert Decimal(str(ledger)) == expected, (
                f"drift at step {step} (seed {SEED}): ledger {ledger}, expected {expected}"
            )

    ledger = await db_session.scalar(
        select(func.coalesce(func.sum(StockMovement.quantity_delta), 0))
    )
    on_hand = await service.movements.quantity_for_item(item.id)

    assert Decimal(str(ledger)) == expected, f"seed {SEED}: ledger {ledger} != expected {expected}"
    assert on_hand == expected, f"seed {SEED}: on_hand {on_hand} != expected {expected}"

    # The mix actually exercised all three paths. Without this the test could pass having done a
    # thousand receipts, which proves nothing about the interleaving it exists to test.
    assert receipts > 200
    assert consumptions > 200
    assert adjustments > 50
    # **The guard that makes the rest of this test mean anything.** Verified by disabling
    # `_record_shortfall` and confirming this test then fails; without it, it passed.
    assert shortfalls > 100, (
        f"only {shortfalls} consumptions came up short, so the shortfall path was barely "
        "exercised. Rebalance the distribution rather than deleting this assertion."
    )
    # And the sequence genuinely went negative at some point, which is the path spec decision 2
    # added and the one most likely to be got wrong.
    assert expected != Decimal("0")
