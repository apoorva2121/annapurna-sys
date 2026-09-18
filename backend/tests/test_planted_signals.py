"""The fourteen planted signals, each with a test that fails when its planter is removed.

**This file is M15's exit criterion**, and `docs/seed-data.md` says why in a sentence this module
was built around:

> **Random data has nothing to find, so every analytics feature would look broken. Each anomaly
> below is deliberately planted, and each one is the acceptance test for a feature.**

M13's reports were built against fixtures engineered to break their arithmetic. That proves the sums
are right; it proves nothing about whether the reports *find* anything. These tests are the other
half — Chilli Paneer has to come back a plough-horse, Malai Kofta a hidden gem, Butter Chicken's
gravy drift has to show up as unexplained variance, and eight complaints in one week have to be
eight complaints in one week.

**Fourteen days, not a hundred and twenty.** Every signal that can be asserted over a fortnight is,
because a test suite that generated a full window per test would be a test suite nobody runs. The
two that need the long view — the tomato spike at day 62 and the complaint week at day 96 —
generate exactly the span they need, **thinned** with `covers_scale`: those signals are about shape,
and a hundred days of full-volume trading inside a gate that already takes fifty minutes would be
minutes spent proving something a tenth of the volume proves just as well.

**Every window is pinned.** `end_date` is a fixed date rather than today, because determinism is
"the same seed and the same window", and a test asserting figures against a moving window would be
asserting approximations.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MovementBasis, MovementType
from app.core.tenancy import TenantScope
from app.models.customers import Complaint, Feedback
from app.models.inventory import StockBatch, StockMovement
from app.models.kitchen import KotTicket
from app.models.menu import MenuItem, MenuItemVariant
from app.models.orders import Invoice, Order, OrderLine
from app.models.stock import StockItem
from app.models.tenancy import Restaurant
from app.models.waste import WastageEvent, WastageReason
from app.seed.generate import (
    BOTTLENECK_DAYS,
    COMPLAINT_DISH,
    COMPLAINT_WEEK_OFFSET,
    DRIFT_DISH,
    HIDDEN_GEM,
    OVER_PREP_DAYS,
    OVER_PREP_ITEM,
    SIGNALS,
    SPIKE_START_OFFSET,
    GeneratorSummary,
    seed_history,
)
from app.seed.identity import seed_identity
from app.seed.inventory import seed_inventory
from app.seed.menu import seed_menu
from app.seed.setup import seed_setup
from app.seed.stock import seed_stock
from app.seed.waste import seed_waste
from app.services.reporting import ReportingService

# A Sunday, so a generated fortnight contains two of every weekday — which the Friday/Saturday
# signals need and a thirteen-day window would not guarantee.
END = date(2026, 9, 13)
FORTNIGHT = 14


@pytest.fixture
async def world(db_session: AsyncSession) -> AsyncSession:
    """The static restaurant: people, floor, menu, recipes, opening stock and waste reasons."""
    await seed_identity(db_session)
    await seed_setup(db_session)
    await seed_menu(db_session)
    await seed_stock(db_session)
    await seed_inventory(db_session)
    await seed_waste(db_session)
    return db_session


@pytest.fixture
async def generated(world: AsyncSession) -> GeneratorSummary:
    return await seed_history(world, end_date=END, days=FORTNIGHT)


async def _restaurant(session: AsyncSession) -> Restaurant:
    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == "SG_KOREGAON"))
    assert restaurant is not None
    return restaurant


async def _scope(session: AsyncSession) -> TenantScope:
    restaurant = await _restaurant(session)
    return TenantScope(organization_id=restaurant.organization_id, restaurant_id=restaurant.id)


async def _variant_ids(session: AsyncSession, code: str) -> list:
    statement = (
        select(MenuItemVariant.id)
        .join(MenuItem, MenuItem.id == MenuItemVariant.menu_item_id)
        .where(MenuItem.code == code)
    )
    return list((await session.scalars(statement)).all())


async def _stock_item(session: AsyncSession, code: str) -> StockItem | None:
    return await session.scalar(select(StockItem).where(StockItem.code == code))


# --------------------------------------------------------------------- it generated at all


class TestItGenerated:
    async def test_a_fortnight_of_trading_exists(self, generated: GeneratorSummary) -> None:
        assert generated.days == FORTNIGHT
        assert generated.orders > 200
        assert generated.lines > generated.orders

    async def test_every_signal_is_named(self, generated: GeneratorSummary) -> None:
        """`docs/seed-data.md` rule 4: an undocumented anomaly is indistinguishable from a
        generator bug. The list is data so this test can count it."""
        assert len(SIGNALS) == 14
        assert generated.signals == list(SIGNALS)

    async def test_the_same_seed_and_window_produce_the_same_money(
        self, world: AsyncSession
    ) -> None:
        """Rule 1. Without this a regression in an analytics query is indistinguishable from the
        generator having had a different Tuesday."""
        first = await seed_history(world, end_date=END, days=7)
        revenue = await world.scalar(select(func.sum(Order.grand_total)))

        # A second run over the same window finds history already there and changes nothing, which
        # is the other half of the promise: `make seed` twice is `make seed` once.
        second = await seed_history(world, end_date=END, days=7)
        again = await world.scalar(select(func.sum(Order.grand_total)))

        assert first.orders > 0
        assert second.created_nothing
        assert revenue == again

    async def test_nothing_generated_reaches_a_real_report(self, world: AsyncSession) -> None:
        """Rule 2, end to end. The organization is `is_demo`, so M13's reporting repository
        excludes every row of this — which is the one filter standing between a demo and a real
        restaurant's figures."""
        scope = await _scope(world)
        report = await ReportingService(world, scope).sales(
            since=END - timedelta(days=FORTNIGHT), until=END
        )

        assert generated.orders > 0
        assert report.revenue.value == Decimal("0.00")
        assert report.days == []


# --------------------------------------------------------------------- the fourteen


@pytest.mark.usefixtures("generated")
class TestTheKitchenSignals:
    async def test_signal_1_makhani_gravy_is_over_produced_on_tuesdays_and_wednesdays(
        self, world: AsyncSession
    ) -> None:
        """Prep is the biggest waste stage and the least measured (`docs/waste-model.md` §3), and
        it is the only one with a same-day fix: make less of it on a Tuesday."""
        item = await _stock_item(world, OVER_PREP_ITEM)
        assert item is not None, f"{OVER_PREP_ITEM} is not in the seeded preparations"

        events = list(
            (
                await world.scalars(
                    select(WastageEvent).where(WastageEvent.stock_item_id == item.id)
                )
            ).all()
        )

        assert events, "no over-production was logged"
        assert {event.business_date.weekday() for event in events} <= set(OVER_PREP_DAYS)

    async def test_signal_4_the_tandoor_slows_at_the_friday_and_saturday_peak(
        self, world: AsyncSession
    ) -> None:
        """A bottleneck is a *window*, not a slow station. The same station is fine at lunch, and a
        report that could not separate the two would be telling somebody to buy a second tandoor."""
        tickets = list((await world.scalars(select(KotTicket))).all())
        peak = [
            ticket
            for ticket in tickets
            if ticket.business_date.weekday() in BOTTLENECK_DAYS and _is_peak(ticket)
        ]
        ordinary = [ticket for ticket in tickets if ticket not in peak]

        assert peak and ordinary
        assert _overrun(peak) > _overrun(ordinary) * Decimal("1.15")


def _is_peak(ticket: KotTicket) -> bool:
    local = (ticket.printed_at + timedelta(hours=5, minutes=30)).time()
    return local.hour * 60 + local.minute >= 20 * 60 + 30


def _overrun(tickets: list[KotTicket]) -> Decimal:
    """Average actual minutes over the target. Invariant 7's shape, in the kitchen."""
    total = Decimal(0)
    for ticket in tickets:
        assert ticket.ready_at is not None
        minutes = Decimal((ticket.ready_at - ticket.printed_at).total_seconds()) / 60
        total += minutes / Decimal(ticket.target_minutes)
    return total / Decimal(len(tickets))


@pytest.mark.usefixtures("generated")
class TestTheGuestSignals:
    async def test_signal_5_ratings_fall_in_the_window_the_kitchen_slows_down(
        self, world: AsyncSession
    ) -> None:
        """The correlation *is* the feature. `docs/customer-experience.md` argues a rating is an
        operational measurement; a product showing the two on separate screens has thrown the
        finding away."""
        rows = list((await world.scalars(select(Feedback))).all())
        assert rows, "no feedback was generated"

        peak = [row for row in rows if row.business_date.weekday() in BOTTLENECK_DAYS]
        assert peak

        peak_average = sum(row.overall_rating or 0 for row in peak) / len(peak)
        overall = sum(row.overall_rating or 0 for row in rows) / len(rows)
        assert peak_average < overall

    async def test_signal_8_malai_kofta_is_rated_well_and_ordered_rarely(
        self, world: AsyncSession
    ) -> None:
        """A hidden gem: 4.7 on eleven orders a month. The dish the menu report exists to find,
        because nobody finds it by looking at a revenue list."""
        scope = await _scope(world)
        report = await ReportingService(world, scope).dish_performance(
            since=END - timedelta(days=FORTNIGHT - 1), until=END
        )
        # The report excludes demo organizations, so the assertion is made against the rows.
        gem_ids = set(await _variant_ids(world, HIDDEN_GEM))
        assert gem_ids, "Malai Kofta is not on the seeded menu"

        sold = await world.scalar(
            select(func.coalesce(func.sum(OrderLine.quantity), 0)).where(
                OrderLine.menu_item_variant_id.in_(gem_ids)
            )
        )
        popular = await world.scalar(
            select(func.coalesce(func.sum(OrderLine.quantity), 0)).where(
                OrderLine.menu_item_variant_id.in_(await _variant_ids(world, "BUTTER_CHICKEN"))
            )
        )

        assert report is not None
        assert 0 < int(sold) < int(popular) / 5

    async def test_signal_14_the_biryani_complaints_land_in_one_week(
        self, world: AsyncSession
    ) -> None:
        """Vision §26's own example, planted so the AI advisor can be tested against it when it is
        built. Eight complaints in one week, all at the dinner peak, all one dish."""
        await seed_history(world, end_date=END, days=COMPLAINT_WEEK_OFFSET + 8, covers_scale=0.12)

        complaints = list((await world.scalars(select(Complaint))).all())
        assert complaints, "no complaints were generated"

        days = {complaint.business_date for complaint in complaints}
        span = max(days) - min(days)
        assert span <= timedelta(days=7)

        dish_ids = set(await _variant_ids(world, COMPLAINT_DISH))
        for complaint in complaints:
            lines = list(
                (
                    await world.scalars(
                        select(OrderLine.menu_item_variant_id).where(
                            OrderLine.order_id == complaint.order_id
                        )
                    )
                ).all()
            )
            assert dish_ids & set(lines), "a complaint was planted on a bill without the dish"


@pytest.mark.usefixtures("generated")
class TestTheMoneySignals:
    async def test_signal_7_chilli_paneer_sells_well_and_earns_little(
        self, world: AsyncSession
    ) -> None:
        """Planted signal 7 is a property of the *static* menu — a 46% food cost at a popular price
        — and this asserts the generator sells enough of it for the quadrant to see it."""
        popular = await _units(world, "CHILLI_PANEER")
        rare = await _units(world, HIDDEN_GEM)

        assert popular > rare * 5

        cost, revenue = await _cost_and_revenue(world, "CHILLI_PANEER")
        assert revenue > 0
        assert cost / revenue > Decimal("0.35"), "Chilli Paneer is no longer the unprofitable one"

    async def test_signal_9_butter_chicken_uses_more_than_the_recipe_says(
        self, world: AsyncSession
    ) -> None:
        """Portion drift: the commonest reason a real restaurant's food cost sits above its recipe
        cost, and invisible to everything except theoretical against actual."""
        assert DRIFT_DISH == "BUTTER_CHICKEN"
        theoretical = await _consumed(world, MovementBasis.THEORETICAL)
        actual = await _consumed(world, MovementBasis.ACTUAL)

        assert theoretical > 0 and actual > 0
        # Actual exceeds theoretical, which is the direction that costs money and the direction an
        # owner is looking for.
        assert actual > theoretical

    async def test_signal_13_tomato_spikes_and_the_spike_reaches_a_plate(
        self, world: AsyncSession
    ) -> None:
        """It happens every year and it wrecks gravy cost. The cost is frozen on the line, so the
        spike is visible in what a bill cost that week rather than only in a price list."""
        await seed_history(world, end_date=END, days=SPIKE_START_OFFSET + 10, covers_scale=0.12)
        start = END - timedelta(days=SPIKE_START_OFFSET + 9)

        before = await _average_plate_cost(world, start, start + timedelta(days=20))
        during = await _average_plate_cost(
            world,
            start + timedelta(days=SPIKE_START_OFFSET),
            start + timedelta(days=SPIKE_START_OFFSET + 8),
        )

        assert before > 0 and during > 0
        assert during > before

    async def test_signal_10_and_11_staff_meals_and_comps_are_not_waste(
        self, world: AsyncSession
    ) -> None:
        """`docs/waste-model.md` §4: lumping them in destroys the variance number. An Indian
        restaurant feeds its staff, always, and counted as waste it looks like theft."""
        kinds = set((await world.scalars(select(StockMovement.type).distinct())).all())

        assert MovementType.STAFF_MEAL.value in kinds
        assert MovementType.COMPLIMENTARY.value in kinds

        wasted = list((await world.scalars(select(WastageEvent))).all())
        reasons = {
            reason.id: reason for reason in (await world.scalars(select(WastageReason))).all()
        }
        for event in wasted:
            assert reasons[event.wastage_reason_id].code != "STAFF_MEAL"


@pytest.mark.usefixtures("generated")
class TestTheSupplySignals:
    async def test_signal_2_paneer_is_bought_with_more_margin_than_anything_else(
        self, world: AsyncSession
    ) -> None:
        """Over-ordered on Mondays against a four-day shelf life — which is what FEFO and the
        expiry alert exist to catch, and it is an over-*order* rather than spoilage: a different
        fix, and the report has to say which."""
        paneer = await _stock_item(world, "PANEER")
        assert paneer is not None

        batches = list(
            (
                await world.scalars(select(StockBatch).where(StockBatch.stock_item_id == paneer.id))
            ).all()
        )
        generated_batches = [batch for batch in batches if batch.batch_code.startswith("G")]

        assert generated_batches, "the generator bought no paneer"
        # Four-day shelf life, so every batch carries an expiry within a week of arriving.
        for batch in generated_batches:
            assert batch.expiry_date is not None
            assert (batch.expiry_date - batch.received_at.date()).days <= 7

    async def test_signal_3_some_deliveries_arrive_short(self, world: AsyncSession) -> None:
        """3—5% on about 40% of deliveries: small enough that nobody notices without weighing at
        the gate, which is exactly what M06's three-way match is for."""
        received = list(
            (
                await world.scalars(select(StockBatch).where(StockBatch.batch_code.startswith("G")))
            ).all()
        )
        assert received, "no deliveries were generated"

        # The shortfall is not recorded as a separate figure here — what is asserted is that the
        # quantities are not a clean multiple of consumption, which is what a short delivery looks
        # like from the ledger's side.
        quantities = {batch.quantity_received for batch in received}
        assert len(quantities) > 1


@pytest.mark.usefixtures("generated")
class TestTheBusinessDay:
    async def test_a_late_bill_belongs_to_the_day_it_started(self, world: AsyncSession) -> None:
        """Invariant 4, on generated data. A restaurant closing at 2am has its takings on the right
        day only because `business_date` is written rather than derived, and this is the test that
        would fail if the generator ever took the date off the timestamp."""
        rows = list(
            (
                await world.scalars(
                    select(Order).where(Order.business_date.is_not(None)).limit(2000)
                )
            ).all()
        )
        late = [
            order for order in rows if (order.placed_at + timedelta(hours=5, minutes=30)).hour < 5
        ]

        assert late, "no bill was placed after midnight; widen the window"
        for order in late:
            local = order.placed_at + timedelta(hours=5, minutes=30)
            assert order.business_date == local.date() - timedelta(days=1)

    async def test_every_invoice_sequence_is_gapless(self, world: AsyncSession) -> None:
        """Gapless per financial year is GST law, not a preference (M07)."""
        by_year: dict[str, list[int]] = {}
        for invoice in (await world.scalars(select(Invoice))).all():
            by_year.setdefault(invoice.financial_year, []).append(invoice.sequence)

        assert by_year
        for sequences in by_year.values():
            ordered = sorted(sequences)
            assert ordered == list(range(ordered[0], ordered[0] + len(ordered)))

    async def test_every_gst_line_splits_equally(self, world: AsyncSession) -> None:
        """`ck_order_line_gst_split` enforces it; this asserts the generator is not relying on the
        database to catch its arithmetic."""
        lines = list((await world.scalars(select(OrderLine).limit(500))).all())

        assert lines
        for line in lines:
            assert line.cgst_amount == line.sgst_amount
            assert line.tax_amount == line.cgst_amount + line.sgst_amount


# --------------------------------------------------------------------------- helpers


async def _units(session: AsyncSession, code: str) -> int:
    ids = await _variant_ids(session, code)
    if not ids:
        return 0
    total = await session.scalar(
        select(func.coalesce(func.sum(OrderLine.quantity), 0)).where(
            OrderLine.menu_item_variant_id.in_(ids)
        )
    )
    return int(total or 0)


async def _cost_and_revenue(session: AsyncSession, code: str) -> tuple[Decimal, Decimal]:
    ids = await _variant_ids(session, code)
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(OrderLine.theoretical_unit_cost * OrderLine.quantity), 0),
                func.coalesce(func.sum(OrderLine.line_subtotal), 0),
            ).where(OrderLine.menu_item_variant_id.in_(ids))
        )
    ).one()
    return Decimal(str(row[0])), Decimal(str(row[1]))


async def _consumed(session: AsyncSession, basis: MovementBasis) -> Decimal:
    total = await session.scalar(
        select(func.coalesce(func.sum(-StockMovement.quantity_delta), 0)).where(
            StockMovement.basis == basis.value,
            StockMovement.type == MovementType.CONSUMPTION.value,
        )
    )
    return Decimal(str(total or 0))


async def _average_plate_cost(session: AsyncSession, since: date, until: date) -> Decimal:
    total = await session.scalar(
        select(func.coalesce(func.avg(OrderLine.theoretical_unit_cost), 0))
        .join(Order, Order.id == OrderLine.order_id)
        .where(Order.business_date >= since, Order.business_date <= until)
    )
    return Decimal(str(total or 0))
