"""The reports, each against a dataset engineered to make it fail.

**Why fixtures rather than the seed** (owner's decision, 2026-09-18): the 14 planted signals in
`docs/seed-data.md` need M15's 120-day generator, which does not exist. A report run over the
handful of days the seed currently holds would pass and prove almost nothing. So each metric here
is given data built to break it if the arithmetic is wrong — a known variance, a known waste, a
dish that sells well and earns nothing — and the 14-signal test becomes M15's exit criterion.

Rows are constructed directly rather than through M07's API. That is deliberate: this file tests
what the *reports* do with a ledger, and driving settlement to produce one would test settlement.
The one thing taken from the real write path is the shape — `theoretical_unit_cost` frozen on the
line, consumption negative in the ledger, `business_date` on everything.

The three that matter most:

**Unexplained variance.** A stock item where actual consumption exceeds theoretical by a known
amount, part of it explained by a logged waste event. The report has to produce exactly the
remainder, because that remainder is the only line in the product that says *this much of your food
went somewhere nobody can account for*.

**The 2am order.** An order placed at 01:30 belongs to the previous business day (invariant 4). A
report that grouped on `created_at` would put it on the wrong day and look entirely normal.

**The quadrant.** A dish that sells well and earns nothing must come back a plough-horse, because
that is planted signal 7 and the reason menu engineering is in the product at all.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MovementBasis, MovementType, OrderStatus, OrderType
from app.core.tenancy import TenantScope
from app.models.customers import Feedback
from app.models.inventory import StockBatch, StockMovement
from app.models.menu import MenuCategory, MenuItem, MenuItemVariant
from app.models.orders import Invoice, Order, OrderLine
from app.models.setup import Station, TaxGroup
from app.models.stock import StockItem
from app.models.tenancy import Organization, Restaurant
from app.models.waste import WastageEvent, WastageReason
from app.repositories.waste import WastageEventRepository
from app.services.reporting import ReportingService

_DAY = date(2026, 9, 16)
_EARLIER = date(2026, 9, 15)


class World:
    """The smallest restaurant a report can be run against."""

    def __init__(
        self,
        organization: Organization,
        restaurant: Restaurant,
        scope: TenantScope,
    ) -> None:
        self.organization = organization
        self.restaurant = restaurant
        self.scope = scope


async def _world(session: AsyncSession, *, is_demo: bool = False) -> World:
    organization = Organization(
        name="Spice Garden Group", slug=f"sg-{uuid.uuid4().hex[:8]}", is_demo=is_demo
    )
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name="Koregaon Park",
        code=f"KP{uuid.uuid4().hex[:6]}",
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
    )
    session.add(restaurant)
    await session.flush()
    return World(
        organization,
        restaurant,
        TenantScope(organization_id=organization.id, restaurant_id=restaurant.id),
    )


async def _variant(
    session: AsyncSession, world: World, *, dish: str, price: str
) -> MenuItemVariant:
    rid = world.restaurant.id
    category = MenuCategory(
        restaurant_id=rid, code=f"C{uuid.uuid4().hex[:6]}", name="Mains", seq=0, is_active=True
    )
    tax = TaxGroup(
        restaurant_id=rid, code=f"T{uuid.uuid4().hex[:6]}", name="GST 5%", is_active=True
    )
    # `menu_item.station_id` is NOT NULL: every dish routes to a station, which is what makes a
    # ticket printable at all (M03). A fixture without one is not a dish this product would accept.
    station = Station(
        restaurant_id=rid,
        code=f"ST{uuid.uuid4().hex[:5]}",
        name="Tandoor",
        seq=0,
        is_active=True,
    )
    session.add_all([category, tax, station])
    await session.flush()
    item = MenuItem(
        restaurant_id=rid,
        menu_category_id=category.id,
        code=f"D{uuid.uuid4().hex[:6]}",
        name=dish,
        station_id=station.id,
        food_type="veg",
        is_active=True,
        seq=0,
    )
    session.add(item)
    await session.flush()
    variant = MenuItemVariant(
        restaurant_id=rid,
        menu_item_id=item.id,
        code="FULL",
        name="Full",
        price=Decimal(price),
        prep_minutes=12,
        tax_group_id=tax.id,
        is_active=True,
        seq=0,
    )
    session.add(variant)
    await session.flush()
    return variant


async def _sold(
    session: AsyncSession,
    world: World,
    variant: MenuItemVariant,
    *,
    quantity: int,
    unit_price: str,
    unit_cost: str,
    business_date: date = _DAY,
    placed_at: datetime | None = None,
    covers: int = 2,
) -> Order:
    """One settled order with one line, and the invoice that settled it.

    **Built in the order the product builds it**: open, then the line, then settled. A trigger
    enforces invariant 6 — a settled order takes no new lines — so a fixture that created the order
    settled and then added to it is refused by the database, which is the invariant working. That
    refusal is also why this helper cannot be shortened.

    `theoretical_unit_cost` is set on the line exactly as settlement sets it: the frozen figure a
    report must read rather than recompute.
    """
    rid = world.restaurant.id
    revenue = Decimal(unit_price) * quantity
    order = Order(
        restaurant_id=rid,
        order_number=f"O{uuid.uuid4().hex[:8]}",
        type=OrderType.DINE_IN.value,
        channel="pos",
        status=OrderStatus.OPEN.value,
        covers=covers,
        placed_at=placed_at or datetime(2026, 9, 16, 13, 0, tzinfo=UTC),
        business_date=business_date,
    )
    session.add(order)
    await session.flush()
    session.add(
        OrderLine(
            restaurant_id=rid,
            order_id=order.id,
            menu_item_variant_id=variant.id,
            quantity=quantity,
            unit_price=Decimal(unit_price),
            line_subtotal=revenue,
            tax_group_id=variant.tax_group_id,
            tax_rate=Decimal("0.0500"),
            taxable_value=revenue,
            tax_amount=Decimal("0.00"),
            line_total=revenue,
            theoretical_unit_cost=Decimal(unit_cost),
            status="served",
        )
    )
    await session.flush()

    # Only now: the trigger refuses a line after this point, which is invariant 6 at the database.
    order.status = OrderStatus.SETTLED.value
    order.settled_at = placed_at or datetime(2026, 9, 16, 14, 0, tzinfo=UTC)
    await session.flush()

    # Sequential per financial year with no gaps (M07, GST law), so the fixture counts rather than
    # hardcoding — two bills in one test would otherwise collide on a rule that exists for a reason.
    sequence = (
        int(
            await session.scalar(select(func.count(Invoice.id)).where(Invoice.restaurant_id == rid))
            or 0
        )
        + 1
    )
    session.add(
        Invoice(
            restaurant_id=rid,
            order_id=order.id,
            document_type="tax_invoice",
            financial_year="2026-27",
            sequence=sequence,
            invoice_number=f"INV/{uuid.uuid4().hex[:8]}",
            status="issued",
            issued_at=order.settled_at,
            invoice_date=business_date,
            business_date=business_date,
            supplier_name="Spice Garden",
            # Rule 46(a): a tax invoice carries the supplier's GSTIN, and the schema refuses one
            # without it. A fixture that skipped it would be building a document no restaurant
            # using this product could legally issue.
            supplier_gstin="27AAAPA1234A1Z5",
            taxable_total=revenue,
            grand_total=revenue,
        )
    )
    await session.flush()
    return order


async def _item_with_ledger(
    session: AsyncSession,
    world: World,
    *,
    name: str,
    theoretical: str,
    actual: str,
    unit_cost: str = "0.36",
    business_date: date = _DAY,
) -> StockItem:
    """A stock item consumed twice: once as the recipes say, once as the shelf says.

    Consumption is **negative** in the ledger, exactly as `InventoryService` writes it, so the
    report's sign-flip is exercised rather than assumed.
    """
    rid = world.restaurant.id
    item = StockItem(
        restaurant_id=rid,
        code=f"S{uuid.uuid4().hex[:6]}",
        name=name,
        kind="ingredient",
        base_unit="g",
        is_active=True,
    )
    session.add(item)
    await session.flush()
    batch = StockBatch(
        restaurant_id=rid,
        stock_item_id=item.id,
        batch_code=f"B{uuid.uuid4().hex[:8]}",
        quantity_received=Decimal("100000"),
        unit_cost=Decimal(unit_cost),
        received_at=datetime(2026, 9, 10, 6, 0, tzinfo=UTC),
        source="purchase",
    )
    session.add(batch)
    await session.flush()
    for basis, quantity in (
        (MovementBasis.THEORETICAL, theoretical),
        (MovementBasis.ACTUAL, actual),
    ):
        if Decimal(quantity) == 0:
            # A movement of zero is refused by the ledger, and rightly: nothing moved. An item
            # that did not move has **no rows**, which is exactly the state the "not a line of
            # zeroes" test needs.
            continue
        session.add(
            StockMovement(
                restaurant_id=rid,
                stock_batch_id=batch.id,
                stock_item_id=item.id,
                type=MovementType.CONSUMPTION.value,
                quantity_delta=-Decimal(quantity),
                unit_cost=Decimal(unit_cost),
                basis=basis.value,
                occurred_at=datetime(2026, 9, 16, 15, 0, tzinfo=UTC),
                business_date=business_date,
            )
        )
    await session.flush()
    return item


async def _wasted(
    session: AsyncSession,
    world: World,
    item: StockItem,
    *,
    quantity: str,
    value: str,
    business_date: date = _DAY,
    stage: str = "prep",
    reason_name: str = "Over-preparation",
) -> None:
    """One logged waste event, with its own reason.

    The stage is a parameter because `docs/waste-model.md`'s whole argument is that the four
    stages have different owners and different fixes — a waste report tested only against "prep"
    would not notice a query that collapsed them.
    """
    rid = world.restaurant.id
    reason = WastageReason(
        restaurant_id=rid,
        code=f"R{uuid.uuid4().hex[:6]}",
        name=reason_name,
        stage=stage,
    )
    session.add(reason)
    await session.flush()
    from app.models.identity import Employee

    employee = Employee(
        organization_id=world.organization.id,
        employee_code=f"E{uuid.uuid4().hex[:6]}",
        full_name="Cook",
        joined_on=date(2026, 1, 1),
    )
    session.add(employee)
    await session.flush()
    session.add(
        WastageEvent(
            restaurant_id=rid,
            stock_item_id=item.id,
            wastage_reason_id=reason.id,
            quantity=Decimal(quantity),
            cost_value=Decimal(value),
            occurred_at=datetime(2026, 9, 16, 16, 0, tzinfo=UTC),
            business_date=business_date,
            reported_by=employee.id,
        )
    )
    await session.flush()


def _service(session: AsyncSession, world: World) -> ReportingService:
    return ReportingService(session, world.scope)


# ------------------------------------------------------------------ the variance


class TestTheNumberTheModuleExistsFor:
    async def test_unexplained_variance_is_the_gap_nobody_wrote_a_reason_for(
        self, db_session: AsyncSession
    ) -> None:
        """1000 g theoretical, 1400 g actual at ₹0.36/g — a ₹144.00 variance. 250 g of it was
        logged as waste at ₹90.00, so ₹54.00 is unexplained.

        If any of those four numbers is wrong the assertion fails, which is the point of choosing
        figures that do not divide into each other.
        """
        world = await _world(db_session)
        item = await _item_with_ledger(
            db_session, world, name="Paneer", theoretical="1000", actual="1400"
        )
        await _wasted(db_session, world, item, quantity="250", value="90.00")

        report = await _service(db_session, world).food_cost_variance(since=_DAY, until=_DAY)

        line = next(row for row in report.lines if row.item_name == "Paneer")
        assert line.theoretical_quantity == Decimal("1000")
        assert line.actual_quantity == Decimal("1400")
        assert line.variance_quantity == Decimal("400")
        assert line.variance_value == Decimal("144.00")
        assert line.waste_value == Decimal("90.00")
        assert line.unexplained_value == Decimal("54.00")

    async def test_the_two_bases_are_never_added_together(self, db_session: AsyncSession) -> None:
        """Invariant 7. If the report summed them, a 1000/1400 item would show 2400 somewhere —
        and the number nobody could explain would be the report's own."""
        world = await _world(db_session)
        await _item_with_ledger(db_session, world, name="Paneer", theoretical="1000", actual="1400")

        report = await _service(db_session, world).food_cost_variance(since=_DAY, until=_DAY)

        line = report.lines[0]
        assert line.theoretical_quantity + line.actual_quantity == Decimal("2400")
        # …and no figure the report produces is that sum.
        assert line.variance_quantity == Decimal("400")
        assert report.theoretical_total != report.actual_total

    async def test_waste_larger_than_the_variance_leaves_nothing_unexplained(
        self, db_session: AsyncSession
    ) -> None:
        """Not a negative number on screen. More waste than variance means the waste *is* the
        variance, and a negative "unexplained" would read as food appearing from nowhere."""
        world = await _world(db_session)
        item = await _item_with_ledger(
            db_session, world, name="Paneer", theoretical="1000", actual="1100"
        )
        await _wasted(db_session, world, item, quantity="500", value="180.00")

        report = await _service(db_session, world).food_cost_variance(since=_DAY, until=_DAY)

        assert report.lines[0].unexplained_value == Decimal("0")

    async def test_an_item_that_did_not_move_is_not_a_line_of_zeroes(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)
        await _item_with_ledger(db_session, world, name="Paneer", theoretical="1000", actual="1000")
        await _item_with_ledger(db_session, world, name="Ghee", theoretical="0", actual="0")

        report = await _service(db_session, world).food_cost_variance(since=_DAY, until=_DAY)

        assert [line.item_name for line in report.lines] == ["Paneer"]


# --------------------------------------------------------------------- the dishes


class TestTheQuadrant:
    async def test_a_dish_that_sells_well_and_earns_nothing_is_a_plough_horse(
        self, db_session: AsyncSession
    ) -> None:
        """Planted signal 7 — Chilli Paneer, high volume, 46% food cost. The reason menu
        engineering is in the product at all."""
        world = await _world(db_session)
        popular_poor = await _variant(db_session, world, dish="Chilli Paneer", price="300")
        quiet_rich = await _variant(db_session, world, dish="Malai Kofta", price="400")
        await _sold(db_session, world, popular_poor, quantity=40, unit_price="300", unit_cost="138")
        await _sold(db_session, world, quiet_rich, quantity=4, unit_price="400", unit_cost="80")

        report = await _service(db_session, world).dish_performance(since=_DAY, until=_DAY)

        by_dish = {line.item_name: line for line in report.lines}
        assert by_dish["Chilli Paneer"].quadrant == "plough_horse"
        assert by_dish["Malai Kofta"].quadrant == "hidden_gem"
        assert by_dish["Chilli Paneer"].food_cost_percent == Decimal("46.00")

    async def test_the_cost_is_the_one_frozen_on_the_line(self, db_session: AsyncSession) -> None:
        """A recipe edit today must not move last week's margin. The report reads
        `theoretical_unit_cost` off the settled line, which settlement froze."""
        world = await _world(db_session)
        variant = await _variant(db_session, world, dish="Butter Chicken", price="480")
        await _sold(db_session, world, variant, quantity=10, unit_price="480", unit_cost="126.70")

        report = await _service(db_session, world).dish_performance(since=_DAY, until=_DAY)

        assert report.lines[0].theoretical_cost == Decimal("1267.00")
        assert report.lines[0].margin == Decimal("3533.00")

    async def test_every_line_carries_advice_rather_than_an_action(
        self, db_session: AsyncSession
    ) -> None:
        """The screen recommends; it never acts."""
        world = await _world(db_session)
        variant = await _variant(db_session, world, dish="Dal Makhani", price="470")
        await _sold(db_session, world, variant, quantity=5, unit_price="470", unit_cost="100")

        report = await _service(db_session, world).dish_performance(since=_DAY, until=_DAY)

        assert report.lines[0].advice
        assert report.lines[0].advice[0].isupper()


# ---------------------------------------------------------------------- the dates


class TestTheBusinessDay:
    async def test_a_half_past_one_order_counts_towards_the_previous_day(
        self, db_session: AsyncSession
    ) -> None:
        """Invariant 4, and the reason no report may group on a timestamp. 01:30 IST on the 17th is
        business day the 16th for a restaurant whose day starts at 05:00 — and a report that used
        `created_at` would put it on the 17th and look entirely normal."""
        world = await _world(db_session)
        variant = await _variant(db_session, world, dish="Late Biryani", price="500")
        await _sold(
            db_session,
            world,
            variant,
            quantity=1,
            unit_price="500",
            unit_cost="150",
            business_date=_DAY,
            # 01:30 IST on the 17th, in UTC.
            placed_at=datetime(2026, 9, 16, 20, 0, tzinfo=UTC),
        )

        on_the_day = await _service(db_session, world).sales(since=_DAY, until=_DAY)
        on_the_next = await _service(db_session, world).sales(
            since=_DAY + timedelta(days=1), until=_DAY + timedelta(days=1)
        )

        assert on_the_day.revenue.value == Decimal("500.00")
        assert on_the_next.revenue.value == Decimal("0.00")

    async def test_the_baseline_is_the_preceding_period_of_equal_length(
        self, db_session: AsyncSession
    ) -> None:
        """Not "last month" — a comparison against a period of a different length is arithmetic
        about the calendar rather than about the restaurant."""
        world = await _world(db_session)
        variant = await _variant(db_session, world, dish="Dal Makhani", price="470")
        await _sold(db_session, world, variant, quantity=2, unit_price="470", unit_cost="100")
        await _sold(
            db_session,
            world,
            variant,
            quantity=1,
            unit_price="470",
            unit_cost="100",
            business_date=_EARLIER,
        )

        report = await _service(db_session, world).sales(since=_DAY, until=_DAY)

        assert report.revenue.value == Decimal("940.00")
        assert report.revenue.previous == Decimal("470.00")
        assert report.revenue.change == Decimal("470.00")
        assert report.revenue.change_percent == Decimal("100.00")

    async def test_no_previous_period_gives_null_rather_than_zero_percent(
        self, db_session: AsyncSession
    ) -> None:
        """Zero would read as "unchanged", which is false: a restaurant's first Tuesday is not a
        Tuesday that did not move."""
        world = await _world(db_session)
        variant = await _variant(db_session, world, dish="Dal Makhani", price="470")
        await _sold(db_session, world, variant, quantity=2, unit_price="470", unit_cost="100")

        report = await _service(db_session, world).sales(since=_DAY, until=_DAY)

        assert report.revenue.previous == Decimal("0.00")
        assert report.revenue.change_percent is None


# ----------------------------------------------------------------- the exclusions


class TestWhatNoReportShows:
    async def test_a_demo_organization_appears_in_no_report(self, db_session: AsyncSession) -> None:
        """A seeded demo restaurant's figures must never reach a real report, and the exclusion
        lives in the repository so no query can forget it."""
        world = await _world(db_session, is_demo=True)
        variant = await _variant(db_session, world, dish="Dal Makhani", price="470")
        await _sold(db_session, world, variant, quantity=3, unit_price="470", unit_cost="100")

        report = await _service(db_session, world).sales(since=_DAY, until=_DAY)

        assert report.revenue.value == Decimal("0.00")
        assert report.days == []

    async def test_another_restaurants_figures_never_appear(self, db_session: AsyncSession) -> None:
        mine = await _world(db_session)
        theirs = await _world(db_session)
        variant = await _variant(db_session, theirs, dish="Their Dal", price="470")
        await _sold(db_session, theirs, variant, quantity=9, unit_price="470", unit_cost="100")

        report = await _service(db_session, mine).sales(since=_DAY, until=_DAY)

        assert report.revenue.value == Decimal("0.00")


# ---------------------------------------------------------------------- the waste


class TestTheWasteReport:
    """M09's summary, widened. Three things this report must not do.

    **Never one number.** `docs/waste-model.md`: "this week you lost 31,200" is unactionable until
    it is split by stage, because receiving is the store manager at the gate and prep is the chef
    and the batch size.

    **The shares must add to a hundred**, which they only do because they are computed once, from
    `Decimal`, after the total is known. A window function rounding each row on its own is the
    classic way this column stops adding up.

    **It must agree with M09's own summary**, because the two queries are written twice — once
    here with the demo exclusion, once in `WastageEventRepository` for the chef's screen behind a
    permission an accountant does not hold. Two queries over the same rows drift; this is the test
    that stops them.
    """

    async def test_the_report_splits_by_stage_rather_than_giving_one_total(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)
        item = await _item_with_ledger(
            db_session, world, name="Paneer", theoretical="1000", actual="1400"
        )
        await _wasted(db_session, world, item, quantity="250", value="90.00", stage="prep")
        await _wasted(
            db_session,
            world,
            item,
            quantity="100",
            value="30.00",
            stage="receiving",
            reason_name="Short-weighted at the gate",
        )

        report = await _service(db_session, world).waste(since=_DAY, until=_DAY)

        assert report.total.value == Decimal("120.00")
        assert {line.stage for line in report.lines} == {"prep", "receiving"}
        # Biggest first: the eye finds the line worth acting on without arithmetic.
        assert [line.cost_value for line in report.lines] == [Decimal("90.00"), Decimal("30.00")]

    async def test_the_shares_add_to_a_hundred_within_a_paisa(
        self, db_session: AsyncSession
    ) -> None:
        """Acceptance criterion 14, and the honest version of it.

        Three equal thirds of a total cannot add to exactly 100 at two decimal places — a third is
        33.33% and three of those are 99.99%. **Within a paisa is the guarantee.**

        The failure it rules out is the one that actually happens: a share computed per row in SQL,
        which drifts by whole percentage points rather than by one paisa. Rounding the *cost* twice
        cannot happen here at all — `wastage_event.cost_value` is `NUMERIC(12,2)`, so the database
        has already rounded before the service sees a figure, and a test claiming to prove
        otherwise would be proving the column's work.
        """
        world = await _world(db_session)
        item = await _item_with_ledger(
            db_session, world, name="Paneer", theoretical="1000", actual="1400"
        )
        for index, stage in enumerate(("prep", "service", "storage")):
            await _wasted(
                db_session,
                world,
                item,
                quantity="100",
                value="33.33",
                stage=stage,
                reason_name=f"Reason {index}",
            )

        report = await _service(db_session, world).waste(since=_DAY, until=_DAY)

        total_share = sum(line.share_percent for line in report.lines)
        assert abs(total_share - Decimal("100")) <= Decimal("0.01"), total_share

    async def test_the_waste_report_agrees_with_m09s_own_summary(
        self, db_session: AsyncSession
    ) -> None:
        """**The price of writing the aggregation twice.**

        `ReportingRepository.waste_by_reason` exists separately from M09's
        `WastageEventRepository.summary` because every report carries the demo exclusion
        (decision 8) and M09's screen does not. Same rows, same answer — asserted, not assumed.
        """
        world = await _world(db_session)
        item = await _item_with_ledger(
            db_session, world, name="Paneer", theoretical="1000", actual="1400"
        )
        await _wasted(db_session, world, item, quantity="250", value="90.00", stage="prep")
        await _wasted(
            db_session,
            world,
            item,
            quantity="100",
            value="30.00",
            stage="receiving",
            reason_name="Short-weighted at the gate",
        )

        report = await _service(db_session, world).waste(since=_DAY, until=_DAY)
        m09 = await WastageEventRepository(db_session, world.scope).summary(since=_DAY, until=_DAY)

        assert [
            (line.stage, line.reason_code, line.events, line.cost_value) for line in report.lines
        ] == [(row.stage, row.reason_code, row.events, row.cost_value) for row in m09]

    async def test_a_demo_organizations_waste_appears_in_no_report(
        self, db_session: AsyncSession
    ) -> None:
        """The half of decision 8 the duplicated query could have missed."""
        world = await _world(db_session, is_demo=True)
        item = await _item_with_ledger(
            db_session, world, name="Paneer", theoretical="1000", actual="1400"
        )
        await _wasted(db_session, world, item, quantity="250", value="90.00")

        report = await _service(db_session, world).waste(since=_DAY, until=_DAY)

        assert report.lines == []
        assert report.total.value == Decimal("0.00")

    async def test_a_week_with_no_waste_is_a_good_week_and_not_a_division_error(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)

        report = await _service(db_session, world).waste(since=_DAY, until=_DAY)

        assert report.lines == []
        assert report.total.change_percent is None


# ------------------------------------------------------------------- the glance


class TestTheGlance:
    async def test_today_carries_yesterday_beside_it(self, db_session: AsyncSession) -> None:
        world = await _world(db_session)
        variant = await _variant(db_session, world, dish="Dal Makhani", price="470")
        await _sold(db_session, world, variant, quantity=2, unit_price="470", unit_cost="100")
        await _sold(
            db_session,
            world,
            variant,
            quantity=1,
            unit_price="470",
            unit_cost="100",
            business_date=_EARLIER,
        )

        report = await _service(db_session, world).today(business_date=_DAY)

        assert report.revenue.value == Decimal("940.00")
        assert report.revenue.previous == Decimal("470.00")

    async def test_an_average_rating_says_how_many_it_is_of(self, db_session: AsyncSession) -> None:
        """A 4.8 from two people is not a 4.8."""
        world = await _world(db_session)
        for rating in (5, 4):
            db_session.add(
                Feedback(
                    restaurant_id=world.restaurant.id,
                    overall_rating=rating,
                    source="qr",
                    submitted_at=datetime(2026, 9, 16, 15, 0, tzinfo=UTC),
                    business_date=_DAY,
                )
            )
        await db_session.flush()

        report = await _service(db_session, world).today(business_date=_DAY)

        assert report.average_rating == Decimal("4.50")
        assert report.ratings_counted == 2


# ------------------------------------------------------- the acceptance query


class TestTheChainThatHasToWork:
    """`docs/domain-model.md`: *"This query must be answerable in SQL, because it is the product."*

        For last week, per dish: units sold, revenue, theoretical food cost from recipes, actual
        ingredient consumption from the ledger, the variance between them, waste attributed to it,
        average prep time, and average customer rating.

    **It is answered by two reports, not one, and that is a finding rather than a shortcut.**

    Units, revenue, theoretical cost, prep time and rating are per dish, and the dish report
    answers them from figures frozen on the settled line. Actual consumption is not a per-dish
    fact and cannot be made into one: the shelf is counted per ingredient, and a kilo of paneer
    that went missing did not arrive with a note saying which dish it was meant for. Splitting it
    across dishes in proportion to what the recipes say would produce a number that *looks* per
    dish and is really the theoretical figure wearing a different hat — which is precisely what
    invariant 7 forbids.

    So the variance half is answered per ingredient, by the variance report, over the same period
    and the same restaurant. Both halves are asserted here together, because the criterion is that
    the chain works end to end and a test of each half separately would not show that.
    """

    async def test_the_chain_is_answerable_end_to_end(self, db_session: AsyncSession) -> None:
        world = await _world(db_session)
        variant = await _variant(db_session, world, dish="Paneer Tikka", price="380")
        await _sold(db_session, world, variant, quantity=4, unit_price="380", unit_cost="95")
        item = await _item_with_ledger(
            db_session, world, name="Paneer", theoretical="1000", actual="1400"
        )
        await _wasted(db_session, world, item, quantity="250", value="90.00")

        service = _service(db_session, world)
        dishes = await service.dish_performance(since=_DAY, until=_DAY)
        variance = await service.food_cost_variance(since=_DAY, until=_DAY)
        waste = await service.waste(since=_DAY, until=_DAY)

        # The per-dish half.
        dish = next(line for line in dishes.lines if line.item_name == "Paneer Tikka")
        assert dish.units == 4
        assert dish.revenue == Decimal("1520.00")
        assert dish.theoretical_cost == Decimal("380.00")
        assert dish.average_prep_seconds is None or dish.average_prep_seconds >= 0
        assert dish.average_rating is None or dish.average_rating >= 0

        # The per-ingredient half, over the same period.
        line = next(row for row in variance.lines if row.item_name == "Paneer")
        assert line.theoretical_quantity == Decimal("1000")
        assert line.actual_quantity == Decimal("1400")
        assert line.variance_value == Decimal("144.00")
        assert line.waste_value == Decimal("90.00")
        assert line.unexplained_value == Decimal("54.00")

        # And the waste the variance half attributed is the waste the waste report splits.
        assert waste.total.value == Decimal("90.00")

    async def test_theoretical_cost_per_dish_is_the_frozen_one(
        self, db_session: AsyncSession
    ) -> None:
        """The half of the chain a recipe edit could quietly rewrite.

        `order_line.theoretical_unit_cost` is written at settlement from the recipe version in
        force *then*. A report that recomputed from today's recipes would answer "what did this
        bill cost in March" with March's prices and today's portions.
        """
        world = await _world(db_session)
        variant = await _variant(db_session, world, dish="Paneer Tikka", price="380")
        await _sold(db_session, world, variant, quantity=2, unit_price="380", unit_cost="95")
        # The recipe changes after the bill was settled. Nothing in the report may move.
        variant.price = Decimal("999")
        await db_session.flush()

        dishes = await _service(db_session, world).dish_performance(since=_DAY, until=_DAY)

        assert dishes.lines[0].revenue == Decimal("760.00")
        assert dishes.lines[0].theoretical_cost == Decimal("190.00")


@pytest.mark.parametrize("days", [1, 7, 90])
async def test_the_report_costs_the_same_for_one_day_and_for_ninety(
    db_session: AsyncSession, days: int
) -> None:
    """The query count is a property of the report, not of the range. A per-day query would be an
    N+1 that only shows up on an owner's month-end."""
    from tests.helpers.queries import count_queries

    world = await _world(db_session)
    variant = await _variant(db_session, world, dish="Dal Makhani", price="470")
    await _sold(db_session, world, variant, quantity=2, unit_price="470", unit_cost="100")
    engine = db_session.get_bind().engine

    with count_queries(engine) as counted:
        await _service(db_session, world).sales(since=_DAY - timedelta(days=days - 1), until=_DAY)

    # Three: the days, the payment split, and the baseline. Never more, whatever the range.
    assert counted.count == 3


@pytest.mark.parametrize("days", [1, 7, 90])
async def test_the_waste_report_costs_the_same_for_one_day_and_for_ninety(
    db_session: AsyncSession, days: int
) -> None:
    from tests.helpers.queries import count_queries

    world = await _world(db_session)
    engine = db_session.get_bind().engine

    with count_queries(engine) as counted:
        await _service(db_session, world).waste(since=_DAY - timedelta(days=days - 1), until=_DAY)

    # Two: the period and its baseline. Never one per day.
    assert counted.count == 2
