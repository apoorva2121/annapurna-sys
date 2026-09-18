"""What the reports cost on a restaurant's worth of rows. Acceptance criterion 13.

**The budget is 800 ms at p95 and it is verified on staging, not here.** This file does what
`test_kitchen_latency.py` does for the rail, and for the same reason: a laptop running a test suite
in a container is not a production database, and a test that asserts a product budget on one is a
test that fails for reasons nobody can act on and gets deleted rather than investigated. So the
assertion here is a **catastrophe bound** — a query that has stopped being a query and become a
loop — and the measured figures go in `docs/plan/m13-build-log.md` with their plans.

**The shape assertion is the one that keeps the bound honest.** A budget met on an empty database
by an N+1 is a budget that fails on the first month-end in a real restaurant, on the screen where
it is most visible. `test_reporting.py` asserts the query *count* is the same for one day and for
ninety; this file asserts the *time* does not grow with the rows the way a per-day query would.

The fixture is bulk-inserted rather than built through the service helpers. Ninety days of trading
through `_sold()` would take minutes of flushes to produce rows whose only job here is to be
numerous — and a slow test is a test somebody stops running.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MovementBasis, MovementType, OrderStatus, OrderType
from app.models.inventory import StockBatch, StockMovement
from app.models.orders import Invoice, Order, OrderLine
from app.models.stock import StockItem
from app.services.reporting import ReportingService
from tests.test_reporting import World, _variant, _world

# Ninety business days — the longest range the reports offer, and the one an owner asks for at the
# end of a quarter.
_DAYS = 90
_BILLS_PER_DAY = 20
_LINES_PER_BILL = 3
_STOCK_ITEMS = 40

_UNTIL = date(2026, 9, 16)
_SINCE = _UNTIL - timedelta(days=_DAYS - 1)

# A query that has become a loop, not the product's budget. The budget is 800 ms at p95 on staging;
# anything past this is a report issuing a statement per day or per row, which is what this catches.
_CATASTROPHE_MS = 4000.0
_BUDGET_MS = 800.0


async def _trading_quarter(session: AsyncSession, world: World) -> None:
    """Ninety days of bills and a ledger, inserted in four statements rather than 1800."""
    rid = world.restaurant.id
    variants = [
        await _variant(session, world, dish=f"Dish {index}", price="380") for index in range(6)
    ]
    await session.flush()

    orders: list[dict[str, object]] = []
    lines: list[dict[str, object]] = []
    invoices: list[dict[str, object]] = []
    sequence = 0
    for day_index in range(_DAYS):
        business_date = _SINCE + timedelta(days=day_index)
        settled = datetime.combine(business_date, datetime.min.time(), tzinfo=UTC) + timedelta(
            hours=14
        )
        for bill in range(_BILLS_PER_DAY):
            order_id = uuid.uuid4()
            sequence += 1
            orders.append(
                {
                    "id": order_id,
                    "restaurant_id": rid,
                    "order_number": f"O{day_index:03d}{bill:03d}",
                    "type": OrderType.DINE_IN.value,
                    "channel": "pos",
                    "status": OrderStatus.SETTLED.value,
                    "covers": 2,
                    "placed_at": settled,
                    "settled_at": settled,
                    "business_date": business_date,
                }
            )
            for line_index in range(_LINES_PER_BILL):
                variant = variants[(bill + line_index) % len(variants)]
                lines.append(
                    {
                        "id": uuid.uuid4(),
                        "restaurant_id": rid,
                        "order_id": order_id,
                        "menu_item_variant_id": variant.id,
                        "quantity": 1,
                        "unit_price": Decimal("380.00"),
                        "line_subtotal": Decimal("380.00"),
                        "tax_group_id": variant.tax_group_id,
                        "tax_rate": Decimal("0.0500"),
                        "taxable_value": Decimal("380.00"),
                        # A GST line's two halves are equal and sum to its tax
                        # (`ck_order_line_gst_split`, M07 decision 4). The database refused a
                        # fixture that carried the tax without splitting it, which is the rule
                        # every Indian invoice this product issues has to satisfy.
                        "cgst_amount": Decimal("9.50"),
                        "sgst_amount": Decimal("9.50"),
                        "tax_amount": Decimal("19.00"),
                        "line_total": Decimal("399.00"),
                        "theoretical_unit_cost": Decimal("95.000000"),
                        "status": "served",
                    }
                )
            invoices.append(
                {
                    "id": uuid.uuid4(),
                    "restaurant_id": rid,
                    "order_id": order_id,
                    "document_type": "tax_invoice",
                    "financial_year": "2026-27",
                    "sequence": sequence,
                    "invoice_number": f"INV/{sequence:06d}",
                    "status": "issued",
                    "issued_at": settled,
                    "invoice_date": business_date,
                    "business_date": business_date,
                    "supplier_name": "Spice Garden",
                    "supplier_gstin": "27AAAPA1234A1Z5",
                    "taxable_total": Decimal("1140.00"),
                    "grand_total": Decimal("1197.00"),
                }
            )

    # The order rows go in settled. The trigger that refuses a line on a settled order is a
    # statement-level rule about *changing* one, which is invariant 6 doing its job in the product;
    # here the whole bill arrives at once, as it would from a restore.
    await session.execute(text("SET session_replication_role = replica"))
    await session.execute(insert(Order), orders)
    await session.execute(insert(OrderLine), lines)
    await session.execute(insert(Invoice), invoices)
    await session.execute(text("SET session_replication_role = origin"))

    await _ledger(session, world)
    await session.flush()


async def _ledger(session: AsyncSession, world: World) -> None:
    """Forty ingredients, consumed on both bases on every one of the ninety days."""
    rid = world.restaurant.id
    items = [
        StockItem(
            restaurant_id=rid,
            code=f"S{index:04d}",
            name=f"Ingredient {index}",
            kind="ingredient",
            base_unit="g",
            is_active=True,
        )
        for index in range(_STOCK_ITEMS)
    ]
    session.add_all(items)
    await session.flush()
    batches = [
        StockBatch(
            restaurant_id=rid,
            stock_item_id=item.id,
            batch_code=f"B{index:04d}",
            quantity_received=Decimal("1000000"),
            unit_cost=Decimal("0.36"),
            received_at=datetime(2026, 6, 1, 6, 0, tzinfo=UTC),
            source="purchase",
        )
        for index, item in enumerate(items)
    ]
    session.add_all(batches)
    await session.flush()

    movements: list[dict[str, object]] = []
    for day_index in range(_DAYS):
        business_date = _SINCE + timedelta(days=day_index)
        occurred = datetime.combine(business_date, datetime.min.time(), tzinfo=UTC) + timedelta(
            hours=22
        )
        for item, batch in zip(items, batches, strict=True):
            for basis, quantity in (
                (MovementBasis.THEORETICAL, "1000"),
                (MovementBasis.ACTUAL, "1080"),
            ):
                movements.append(
                    {
                        "id": uuid.uuid4(),
                        "restaurant_id": rid,
                        "stock_batch_id": batch.id,
                        "stock_item_id": item.id,
                        "type": MovementType.CONSUMPTION.value,
                        "quantity_delta": -Decimal(quantity),
                        "unit_cost": Decimal("0.36"),
                        "basis": basis.value,
                        "occurred_at": occurred,
                        "business_date": business_date,
                    }
                )
    await session.execute(insert(StockMovement), movements)


def _median_ms(runs: list[float]) -> float:
    runs.sort()
    return runs[len(runs) // 2]


@pytest.fixture
async def quarter(db_session: AsyncSession) -> tuple[ReportingService, World]:
    world = await _world(db_session)
    await _trading_quarter(db_session, world)
    # ANALYZE, because a planner with no statistics chooses a different plan from the one a real
    # database would — and a measurement of the wrong plan is not a measurement.
    await db_session.execute(text("ANALYZE"))
    return ReportingService(db_session, world.scope), world


@pytest.mark.parametrize(
    "report",
    ["sales", "food_cost_variance", "dish_performance", "waste"],
)
async def test_no_report_has_become_a_loop_over_a_quarter(
    quarter: tuple[ReportingService, World], report: str
) -> None:
    """1800 bills, 5400 lines, 7200 ledger movements, ninety days — and one query each.

    The median of five runs rather than one: a single sample on a machine running a test suite is
    a coin toss, and a flaky performance test gets deleted rather than investigated.
    """
    service, _ = quarter
    call = getattr(service, report)

    # Once to warm the connection and the plan, so what is measured is the query rather than the
    # first statement of the session.
    await call(since=_SINCE, until=_UNTIL)

    runs: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        await call(since=_SINCE, until=_UNTIL)
        runs.append((time.perf_counter() - started) * 1000)

    median = _median_ms(runs)
    assert median < _CATASTROPHE_MS, (
        f"{report} took a median {median:.1f} ms over {_DAYS} days. The product's budget is "
        f"{_BUDGET_MS:.0f} ms at p95 and is verified on staging; this bound only catches a report "
        f"that has stopped being a query, so a failure here is a real regression."
    )


async def test_ninety_days_does_not_cost_ninety_times_one_day(
    quarter: tuple[ReportingService, World],
) -> None:
    """The shape, which is what keeps the bound above meaningful.

    A report that issued a statement per day would pass a catastrophe bound on a small fixture and
    fail on a real quarter. Ninety days is allowed to cost more than one day — it reads more rows —
    but nothing like ninety times more.
    """
    service, _ = quarter
    await service.sales(since=_UNTIL, until=_UNTIL)

    one_day: list[float] = []
    ninety: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        await service.sales(since=_UNTIL, until=_UNTIL)
        one_day.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        await service.sales(since=_SINCE, until=_UNTIL)
        ninety.append((time.perf_counter() - started) * 1000)

    # Ten, not ninety: room for the extra rows and for the noise of a shared machine, and nowhere
    # near enough room for a per-day query to hide in.
    assert _median_ms(ninety) < _median_ms(one_day) * 10 + 50
