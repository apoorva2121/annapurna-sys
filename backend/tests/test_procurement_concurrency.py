"""Two managers raising an order in the same second, and a delivery that fails half way through.

Acceptance criteria 8 and 11. Both need **real** transactions: the ordinary `db_session` fixture
wraps everything in one, so two "concurrent" allocations inside it are sequential statements that
cannot contend, and a test written on it would pass against code with no locking at all. Guardrail
G-2 exists because this project has already shipped exactly that green test.

**Why the numbering test matters beyond M06.** `docs/modules.md` M07 requires invoice numbers
"sequential per financial year with no gaps", where gaplessness is GST law rather than tidiness.
The advisory lock proved here is the mechanism M07 will need, on a document where a gap costs
nothing — which is much cheaper than debugging it on one where a gap is a compliance breach.
"""

from __future__ import annotations

import asyncio
from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.actor import Actor
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.inventory import StockMovement
from app.models.procurement import GoodsReceipt, GoodsReceiptLine, PurchaseOrder
from app.models.stock import StockItem
from app.models.tenancy import Organization, Restaurant
from app.services.procurement import (
    OrderLineInput,
    ProcurementService,
    ReceiptLineInput,
)

PER_GRAM = Decimal("0.042000")


async def _seed(session: AsyncSession) -> tuple[TenantScope, Actor, StockItem, StockItem]:
    organization = Organization(name="Procure", slug="procure")
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name="Procure",
        code="PRO",
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
    )
    session.add(restaurant)
    await session.flush()
    employee = Employee(
        organization_id=organization.id,
        employee_code="PRO-1",
        full_name="Store Manager",
        joined_on=date(2026, 1, 1),
        employment_type="full_time",
        is_active=True,
    )
    session.add(employee)
    await session.flush()
    items = []
    for code in ("PANEER", "GHEE"):
        item = StockItem(
            restaurant_id=restaurant.id,
            kind="ingredient",
            code=code,
            name=code.title(),
            base_unit="g",
            current_unit_cost=Decimal("0.360000"),
            is_active=True,
        )
        session.add(item)
        items.append(item)
    await session.flush()

    scope = TenantScope(organization_id=organization.id, restaurant_id=restaurant.id)
    actor = Actor(
        employee_id=employee.id,
        organization_id=organization.id,
        restaurant_id=restaurant.id,
        full_name="Store Manager",
        permissions=frozenset(),
        rank=30,
    )
    return scope, actor, items[0], items[1]


async def test_concurrent_orders_get_distinct_consecutive_numbers(fresh_database: str) -> None:
    """Acceptance criterion 8, and it is written to fail with the advisory lock removed.

    `SELECT max(po_number) + 1` on its own is a race: both callers read `PO-000001` and both try to
    write `PO-000002`. The unique constraint saves the data and hands one of them a 500 — which is
    a manager staring at "Something went wrong" while holding a supplier on the phone.

      with the lock     the second allocation waits for the first transaction, reads what it
                        committed, and takes the next number. Five orders, five numbers.
      without the lock  two or more callers read the same maximum, and one of them dies on
                        `uq_purchase_order_restaurant_num`.

    **To re-verify this test is not decorative:** delete the `pg_advisory_xact_lock` call from
    `PurchaseOrderRepository.next_number` and run it again. It must go red. Put it back.
    """
    engine = create_async_engine(fresh_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as setup:
            scope, actor, paneer, _ = await _seed(setup)
            supplier = await ProcurementService(setup, scope).create_supplier(
                actor, name="Sharma Traders"
            )
            await setup.commit()
            supplier_id, item_id = supplier.id, paneer.id

        async def raise_order() -> str:
            async with factory() as session:
                order = await ProcurementService(session, scope).create_order(
                    actor,
                    supplier_id=supplier_id,
                    lines=[
                        OrderLineInput(
                            stock_item_id=item_id,
                            quantity_ordered=Decimal("1000"),
                            unit_price=PER_GRAM,
                        )
                    ],
                )
                number = order.po_number
                await session.commit()
                return number

        numbers = await asyncio.gather(*(raise_order() for _ in range(5)))

        # Distinct, and a contiguous run from one. Both halves matter: distinctness is what the
        # unique constraint would have given us anyway (with a 500), and contiguity is what says
        # the allocation actually read the committed maximum each time.
        assert sorted(numbers) == [
            "PO-000001",
            "PO-000002",
            "PO-000003",
            "PO-000004",
            "PO-000005",
        ]

        async with factory() as check:
            stored = await check.scalars(select(PurchaseOrder.po_number))
            assert sorted(stored.all()) == sorted(numbers)
    finally:
        await engine.dispose()


async def test_a_failed_delivery_leaves_nothing_behind(fresh_database: str) -> None:
    """Acceptance criterion 11. A receipt is all of it or none of it.

    The failure is injected where it is most dangerous: **after** the first line has written its
    receipt line, its stock batch and its movement, and while the second is still to come. A
    partially posted delivery would put stock on the shelf that no receipt accounts for — which is
    indistinguishable, three weeks later, from theft.

    The second line names an item from another restaurant, so `_require_item` raises `NotFoundError`
    mid-loop. That is not a contrived failure: it is what a client sending a stale id does.
    """
    engine = create_async_engine(fresh_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as setup:
            scope, actor, paneer, _ = await _seed(setup)
            # A second restaurant, whose stock item the receipt will illegally name.
            other = Restaurant(
                organization_id=scope.organization_id,
                name="Other Branch",
                code="OTH",
                timezone="Asia/Kolkata",
                business_day_start=time(5, 0),
            )
            setup.add(other)
            await setup.flush()
            foreign = StockItem(
                restaurant_id=other.id,
                kind="ingredient",
                code="FOREIGN",
                name="Foreign",
                base_unit="g",
                current_unit_cost=Decimal("0.100000"),
                is_active=True,
            )
            setup.add(foreign)
            await setup.flush()
            supplier = await ProcurementService(setup, scope).create_supplier(
                actor, name="Sharma Traders"
            )
            await setup.commit()
            supplier_id, good_id, bad_id = supplier.id, paneer.id, foreign.id

        async with factory() as session:
            service = ProcurementService(session, scope)
            with pytest.raises(Exception, match="stock item"):
                await service.receive(
                    actor,
                    supplier_id=supplier_id,
                    lines=[
                        ReceiptLineInput(
                            stock_item_id=good_id,
                            quantity_invoiced=Decimal("1000"),
                            quantity_received=Decimal("1000"),
                            unit_price=PER_GRAM,
                        ),
                        ReceiptLineInput(
                            stock_item_id=bad_id,
                            quantity_invoiced=Decimal("1000"),
                            quantity_received=Decimal("1000"),
                            unit_price=PER_GRAM,
                        ),
                    ],
                )
            await session.rollback()

        async with factory() as check:
            # Nothing at all: not the receipt, not its first line, not the batch the first line
            # created, and not the movement that batch wrote.
            assert await check.scalar(select(func.count()).select_from(GoodsReceipt)) == 0
            assert await check.scalar(select(func.count()).select_from(GoodsReceiptLine)) == 0
            assert await check.scalar(
                select(func.coalesce(func.sum(StockMovement.quantity_delta), 0))
            ) == Decimal("0")
    finally:
        await engine.dispose()
