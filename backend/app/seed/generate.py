"""120 days of trading, with fourteen things deliberately wrong in it.

`docs/seed-data.md` states the reason this module exists, and it is not volume:

> **Random data has nothing to find, so every analytics feature would look broken. Each anomaly
> below is deliberately planted, and each one is the acceptance test for a feature.**

M13 shipped four reports against fixtures built to break their arithmetic. What no fixture could
test is whether the reports *find* anything — whether the quadrant puts Chilli Paneer where it
belongs, whether a 12% portion drift surfaces as unexplained variance, whether eight complaints in
one week read as a cluster. This module is that test's data, and `tests/test_planted_signals.py`
is the test.

## Why this writes rows rather than calling the services

M07's seeder states the rule: *"Everything goes through the services, never around them, so the
seeded bill is priced, taxed, numbered and consumed exactly as a real one would be."* That rule is
right, and **history cannot obey it**, for a reason that has nothing to do with speed:
`OrderService.create` and `SettlementService.settle` take no clock. They read `datetime.now(UTC)`
for `placed_at`, `settled_at`, `business_date` and the invoice date, because for a real bill that
is exactly correct. Driving them fourteen thousand times would produce fourteen thousand bills all
dated today, which is not history — it is one very busy afternoon.

So this module computes what those services compute and writes the rows itself, and
`tests/test_planted_signals.py` asserts the money it produces against the reports that read it.

## Why a week at a time

`stock_movement.stock_batch_id` is NOT NULL, and rightly: a consumption that came from no batch is
a consumption at no cost, and invariant 2's whole point is that cost travels with the stock. So the
generator works a week at a time — build the week's trading in memory, buy the stock it needs, then
write the bills and the movements that draw on those batches. A restaurant buys on Monday for the
week; so does this.

## Determinism

Same seed **and same end date** produce identical data. "120 days ending today" cannot be
deterministic across two days, so the end date is an argument: `make seed` passes today, because a
demo wants yesterday to be yesterday, and every test pins it.

## What is deliberately imperfect

`docs/seed-data.md` rule 3: *"Include missing feedback, a forgotten stock count, two voided orders,
a day the waste log was skipped. Perfectly clean data hides bugs that real data will find."* Those
are planted too, and they are why the reports are worth trusting when they meet a real restaurant.
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    ComplaintStatus,
    InvoiceStatus,
    KotTicketStatus,
    MovementBasis,
    MovementType,
    OrderChannel,
    OrderLineStatus,
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentStatus,
)
from app.core.tax import invoice_number
from app.models.customers import Complaint, Customer, Feedback
from app.models.identity import Employee
from app.models.inventory import StockBatch, StockMovement
from app.models.kitchen import KotTicket
from app.models.menu import MenuItem, MenuItemVariant
from app.models.orders import Invoice, Order, OrderLine, OrderTable, Payment
from app.models.setup import RestaurantTable, Station, TaxRate
from app.models.stock import IngredientProfile, Recipe, RecipeLine, StockItem
from app.models.tenancy import Organization, Restaurant
from app.models.waste import WastageEvent, WastageReason

logger = logging.getLogger(__name__)

# Fixed, and the reason every developer and every demo sees the same numbers. A regression in an
# analytics query then shows up as a *changed figure*, which is a diff somebody can read.
SEED = 20260918

DEFAULT_DAYS = 120
SMALL_DAYS = 7

_MONEY = Decimal("0.01")
_COST = Decimal("0.000001")
_ZERO = Decimal("0.00")
# 5% GST on food, split equally into CGST and SGST — the rule `ck_order_line_gst_split` enforces on
# every line, and the one every invoice this product issues has to satisfy.
_GST_RATE = Decimal("0.0500")

# `docs/seed-data.md`: Fri—Sun ≈ 1.7x Mon—Thu, Tuesday the trough. Monday is index 0.
_WEEKDAY_FACTOR = (0.92, 0.82, 0.95, 1.00, 1.70, 1.85, 1.65)
_MONTH_START_BUMP = 1.12
_MONTH_END_DIP = 0.88
# Monsoon in Pune is quieter; the festival months lift.
_SEASON = {7: 0.90, 8: 0.90, 10: 1.10, 11: 1.08}
_BASE_COVERS = 110.0

# Dinner is 2.2x lunch by revenue, so roughly that by covers at a similar average bill.
_DINNER_SHARE = 0.69
_DINE_IN_SHARE = 0.82
# 60% of dine-in tables are 2—3 covers (`docs/seed-data.md`).
_PARTY_SIZES = ((2, 0.34), (3, 0.26), (4, 0.18), (5, 0.10), (6, 0.07), (8, 0.05))

# What a bill is paid with. UPI dominates in urban India and cash has not gone away.
_METHODS = ((PaymentMethod.UPI, 0.54), (PaymentMethod.CARD, 0.22), (PaymentMethod.CASH, 0.24))


@dataclass
class GeneratorSummary:
    days: int = 0
    orders: int = 0
    lines: int = 0
    movements: int = 0
    batches: int = 0
    feedback: int = 0
    complaints: int = 0
    wastage: int = 0
    signals: list[str] = field(default_factory=list)

    @property
    def created_nothing(self) -> bool:
        return self.orders == 0


@dataclass(frozen=True, slots=True)
class Dish:
    """One sellable variant, with everything a generated line needs frozen onto it."""

    variant_id: uuid.UUID
    item_code: str
    price: Decimal
    prep_minutes: int
    tax_group_id: uuid.UUID
    station_id: uuid.UUID
    popularity: int
    # ingredient id → grams per plate, from the recipe in force. A plate's cost is computed from
    # this and the ingredient's price *on the day*, which is how the tomato spike moves it.
    recipe: dict[uuid.UUID, Decimal]


@dataclass(frozen=True, slots=True)
class World:
    restaurant: Restaurant
    start: date
    tables: list[RestaurantTable]
    dishes: list[Dish]
    waiters: list[Employee]
    reporter: uuid.UUID | None
    ingredients: dict[uuid.UUID, StockItem]
    prices: dict[uuid.UUID, Decimal]
    # Shelf life lives on `ingredient_profile` rather than on the item, because it is a property of
    # buying the thing rather than of the thing. Signal 2 needs it: paneer's four days are what make
    # over-ordering on a Monday expire by Friday.
    shelf_life: dict[uuid.UUID, int]
    reasons: dict[str, WastageReason]
    # The seeded regulars. Six of them stop coming after week 14, which is signal 12 and is
    # invisible in a revenue line because other people keep coming.
    customers: list[uuid.UUID]


@dataclass
class Bill:
    """One generated bill, held in memory until the week's stock has been bought."""

    order_id: uuid.UUID
    business_date: date
    placed: datetime
    settled: datetime
    covers: int
    dine_in: bool
    dinner: bool
    waiter: uuid.UUID | None
    customer: uuid.UUID | None
    number: int
    lines: list[dict[str, object]]
    chosen: list[tuple[Dish, int]]
    consumption: dict[uuid.UUID, Decimal]
    subtotal: Decimal
    tax_total: Decimal
    cost_total: Decimal

    @property
    def grand_total(self) -> Decimal:
        return self.subtotal + self.tax_total


# --------------------------------------------------------------------------- the entry point


async def seed_history(
    session: AsyncSession,
    *,
    end_date: date,
    days: int = DEFAULT_DAYS,
    seed: int = SEED,
    covers_scale: float = 1.0,
) -> GeneratorSummary:
    """Generate `days` of trading ending on `end_date` for the demo restaurant.

    The end date is required rather than defaulted to today, because "the same seed produces the
    same data" is only true if the window is the same window. `make seed` passes today; every test
    passes a fixed date and asserts figures rather than approximations.

    Idempotent in the sense the other seeders are: a restaurant that already holds history over
    this window is left alone, because history somebody has been demoing against is history.

    `covers_scale` thins the trading without changing its shape, and exists for one reason: the
    signals that need a long window — the tomato spike at day 62, the complaint week at day 96 —
    are about *shape*, and generating a hundred days of full-volume trading inside a test suite
    would add minutes to a gate that is already the slowest thing in this project. `make seed`
    never passes it.
    """
    summary = GeneratorSummary()
    restaurant = await _demo_restaurant(session)
    if restaurant is None:
        logger.info("No demo restaurant; nothing to generate.")
        return summary

    start = end_date - timedelta(days=days - 1)
    if await _already_generated(session, restaurant, start):
        logger.info("Generated history already present; nothing to do.")
        return summary

    world = await _load(session, restaurant, start)
    if not world.dishes:
        logger.info("The menu is empty; nothing to generate against.")
        return summary

    # Deliberately not a cryptographic generator: determinism *is* the requirement,
    # and a CSPRNG would make every demo and every regression diff different.
    rng = random.Random(seed)  # noqa: S311
    sequence = await _next_invoice_sequence(session, restaurant)

    for week_start in _weeks(start, end_date):
        bills: list[Bill] = []
        for offset in range(7):
            business_date = week_start + timedelta(days=offset)
            if business_date < start or business_date > end_date:
                continue
            # The counter restarts each day, because an order number reads as "which bill of which
            # day" to the person quoting it. Uniqueness comes from `uq_order_number_per_day`, which
            # is over (restaurant, business_date, order_number) — so the date does not need to be
            # *inside* the number, and putting it there is what broke the allocator (see the
            # order_number line below). `kot_ticket` is unique per business date for the same
            # reason.
            bills.extend(_build_day(world, business_date, rng, covers_scale))
        if not bills:
            continue

        batches = await _buy_the_week(session, world, week_start, bills, rng, summary)
        sequence = await _write_week(session, world, bills, batches, sequence, rng, summary)
        await _what_actually_happened(session, world, week_start, bills, batches, rng, summary)
        await _service_errors(session, world, bills, batches, rng, summary)
        await session.flush()

    summary.days = days
    summary.signals = list(SIGNALS)
    return summary


def _weeks(start: date, finish: date) -> list[date]:
    """Monday-aligned weeks covering the window. A restaurant buys for a week."""
    cursor = start - timedelta(days=start.weekday())
    weeks = []
    while cursor <= finish:
        weeks.append(cursor)
        cursor += timedelta(days=7)
    return weeks


# --------------------------------------------------------------------------- loading


async def _demo_restaurant(session: AsyncSession) -> Restaurant | None:
    """Spice Garden, and only ever a demo one.

    Rule 2 of `docs/seed-data.md`: never in production. This refuses to write history into a
    restaurant whose organization is not marked `is_demo` — a second lock on top of M13's reporting
    exclusion. That one keeps generated data out of reports; this one keeps it out of the database.

    **The one with a menu, not the first one alphabetically.** `seed/organization.yaml` creates
    three restaurants and furnishes one: Koregaon Park has 36 variants, three stations and two tax
    groups, while Baner and the second tenant have none — because a branch that exists and is not
    fitted out is a real thing this product has to handle. The first draft ordered by code, picked
    the empty Baner and logged "the menu is empty" about a restaurant that never had one: a true
    sentence about the wrong restaurant, which is the least helpful kind of correct.
    """
    statement = (
        select(Restaurant)
        .join(Organization, Organization.id == Restaurant.organization_id)
        .join(MenuItemVariant, MenuItemVariant.restaurant_id == Restaurant.id)
        .where(Organization.is_demo.is_(True), MenuItemVariant.is_active.is_(True))
        .group_by(Restaurant.id)
        .order_by(func.count(MenuItemVariant.id).desc(), Restaurant.code)
        .limit(1)
    )
    return (await session.scalars(statement)).first()


async def _already_generated(session: AsyncSession, restaurant: Restaurant, start: date) -> bool:
    count = await session.scalar(
        select(func.count(Order.id)).where(
            Order.restaurant_id == restaurant.id,
            Order.business_date <= start + timedelta(days=7),
        )
    )
    return bool(count)


async def _next_invoice_sequence(session: AsyncSession, restaurant: Restaurant) -> int:
    """Gapless per financial year is a legal requirement, not a preference (M07, GST law)."""
    highest = await session.scalar(
        select(func.max(Invoice.sequence)).where(Invoice.restaurant_id == restaurant.id)
    )
    return int(highest or 0) + 1


async def _load(session: AsyncSession, restaurant: Restaurant, start: date) -> World:
    tables = list(
        (
            await session.scalars(
                select(RestaurantTable).where(RestaurantTable.restaurant_id == restaurant.id)
            )
        ).all()
    )
    stations = {
        station.id
        for station in (
            await session.scalars(select(Station).where(Station.restaurant_id == restaurant.id))
        ).all()
    }
    rates = {
        rate.tax_group_id
        for rate in (
            await session.scalars(select(TaxRate).where(TaxRate.restaurant_id == restaurant.id))
        ).all()
    }
    ingredients = {
        item.id: item
        for item in (
            await session.scalars(select(StockItem).where(StockItem.restaurant_id == restaurant.id))
        ).all()
    }
    waiters = list(
        (
            await session.scalars(
                select(Employee)
                .where(
                    Employee.organization_id == restaurant.organization_id,
                    Employee.is_active.is_(True),
                )
                .order_by(Employee.employee_code)
            )
        ).all()
    )
    shelf_life = {
        stock_item_id: int(days or 0)
        for stock_item_id, days in await session.execute(
            select(IngredientProfile.stock_item_id, IngredientProfile.shelf_life_days)
        )
    }
    reasons = {
        reason.code: reason
        for reason in (
            await session.scalars(
                select(WastageReason).where(WastageReason.restaurant_id == restaurant.id)
            )
        ).all()
    }
    return World(
        restaurant=restaurant,
        start=start,
        tables=tables,
        dishes=await _dishes(session, restaurant, stations, rates),
        waiters=waiters,
        reporter=waiters[0].id if waiters else None,
        ingredients=ingredients,
        prices={item.id: _dec(item.current_unit_cost) for item in ingredients.values()},
        shelf_life=shelf_life,
        reasons=reasons,
        customers=list(
            (
                await session.scalars(
                    select(Customer.id)
                    .where(Customer.organization_id == restaurant.organization_id)
                    .order_by(Customer.id)
                )
            ).all()
        ),
    )


def _dec(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or "0"))


async def _dishes(
    session: AsyncSession,
    restaurant: Restaurant,
    stations: set[uuid.UUID],
    rates: set[uuid.UUID],
) -> list[Dish]:
    recipes = await _recipes(session, restaurant)
    statement = (
        select(MenuItemVariant, MenuItem)
        .join(MenuItem, MenuItem.id == MenuItemVariant.menu_item_id)
        .where(
            MenuItemVariant.restaurant_id == restaurant.id,
            MenuItemVariant.is_active.is_(True),
            MenuItem.is_active.is_(True),
        )
    )
    dishes = []
    for variant, item in await session.execute(statement):
        if variant.tax_group_id not in rates or item.station_id not in stations:
            continue
        dishes.append(
            Dish(
                variant_id=variant.id,
                item_code=item.code,
                price=_dec(variant.price),
                prep_minutes=int(variant.prep_minutes or 10),
                tax_group_id=variant.tax_group_id,
                station_id=item.station_id,
                popularity=POPULARITY.get(item.code, 12),
                recipe=recipes.get(variant.id, {}),
            )
        )
    return dishes


async def _recipes(
    session: AsyncSession, restaurant: Restaurant
) -> dict[uuid.UUID, dict[uuid.UUID, Decimal]]:
    """Variant id → ingredient id → grams, from the recipe version in force.

    Preparations are **not** exploded, and the column name says why they need not be: a recipe line
    names a `component_id`, which is a `stock_item` of either kind. A gravy is a stock item in its
    own right, which is what the ledger holds and what makes signal 1's over-produced makhani
    something that can be thrown away rather than an arithmetic adjustment to a dish.
    """
    statement = (
        select(Recipe.menu_item_variant_id, RecipeLine.component_id, RecipeLine.quantity)
        .join(RecipeLine, RecipeLine.recipe_id == Recipe.id)
        .where(
            Recipe.restaurant_id == restaurant.id,
            Recipe.menu_item_variant_id.is_not(None),
            Recipe.is_current.is_(True),
        )
    )
    found: dict[uuid.UUID, dict[uuid.UUID, Decimal]] = {}
    for variant_id, stock_item_id, quantity in await session.execute(statement):
        found.setdefault(variant_id, {})[stock_item_id] = _dec(quantity)
    return found


# --------------------------------------------------------------------------- the demand model

# The long tail `docs/seed-data.md` asks for: the top eight dishes are ~55% of covers, the bottom
# twelve are ~6%.
POPULARITY: dict[str, int] = {
    "BUTTER_CHICKEN": 100,
    "BUTTER_NAAN": 96,
    "DAL_MAKHANI": 92,
    "PANEER_BUTTER_MASALA": 84,
    "CHICKEN_BIRYANI": 78,
    "PANEER_TIKKA": 70,
    "CHILLI_PANEER": 69,
    "JEERA_RICE": 66,
    "GARLIC_NAAN": 58,
    "TANDOORI_ROTI": 52,
    "CHICKEN_TIKKA": 48,
    "VEG_BIRYANI": 40,
    "HAKKA_NOODLES": 36,
    "KADAI_PANEER": 33,
    "CHILLI_CHICKEN": 30,
    "PALAK_PANEER": 28,
    "SCHEZWAN_FRIED_RICE": 26,
    "CHANA_MASALA": 22,
    "MANCHURIAN_DRY": 20,
    "VEG_CRISPY": 18,
    "CHICKEN_65": 17,
    "CHICKEN_TIKKA_MASALA": 16,
    "KADAI_CHICKEN": 14,
    "EGG_CURRY": 12,
    "LACHHA_PARATHA": 12,
    "VEG_KOLHAPURI": 10,
    "SCHEZWAN_CHICKEN": 9,
    "MUSHROOM_TIKKA": 8,
    "CHICKEN_KORMA": 7,
    "MUTTON_ROGANJOSH": 6,
    "PRAWN_KOLIWADA": 5,
    # **Planted signal 8.** Eleven orders a month against a 4.7 rating: the hidden gem the menu
    # report exists to surface. Its popularity is deliberately the lowest on the menu.
    "MALAI_KOFTA": 3,
}

# Every signal this module plants, named. `docs/seed-data.md` rule 4: an undocumented anomaly is
# indistinguishable from a generator bug, so the list is data rather than prose and
# `tests/test_planted_signals.py` walks it.
SIGNALS: tuple[str, ...] = (
    "1 makhani gravy over-produced on Tue/Wed and discarded at close",
    "2 paneer over-ordered on Mondays against a four-day shelf life",
    "3 Fresh Farms short-delivers on about 40% of deliveries",
    "4 tandoor prep time rises 40% at the Fri/Sat dinner peak",
    "5 ratings fall to about 3.3 in that same window",
    "6 one waiter's accuracy errors, on dinner shifts only",
    "7 Chilli Paneer sells well and earns nothing",
    "8 Malai Kofta rates 4.7 on eleven orders a month",
    "9 Butter Chicken consumes 12% more gravy than the recipe says",
    "10 staff meals, separated from waste",
    "11 comps, 70% of them authorised by one manager",
    "12 six regulars stop coming after week 14",
    "13 tomato spikes 2.4x for three weeks; onion drifts up 30%",
    "14 eight biryani complaints in one week, all at the dinner peak",
)


def _covers_for(business_date: date, rng: random.Random) -> int:
    """~110 covers on a weekday, ~190 Friday to Sunday, with the month and the season on top."""
    factor = _WEEKDAY_FACTOR[business_date.weekday()]
    if business_date.day <= 3:
        factor *= _MONTH_START_BUMP
    elif business_date.day >= 25:
        factor *= _MONTH_END_DIP
    factor *= _SEASON.get(business_date.month, 1.0)
    # A restaurant is not a function. ±12% of noise, deterministic from the seed.
    factor *= rng.uniform(0.88, 1.12)
    return max(20, int(_BASE_COVERS * factor))


# --------------------------------------------------------------------------- building a day


def _build_day(
    world: World,
    business_date: date,
    rng: random.Random,
    covers_scale: float = 1.0,
) -> list[Bill]:
    """Every bill of one business day, in memory. Nothing is written here.

    A restaurant's day runs 05:00 to 05:00 (invariant 4), so the late tables belong to *this*
    business date even though the clock has passed midnight. Every row carries the business date
    explicitly rather than deriving it from a timestamp, which is the single most likely place for
    a five-and-a-half-hour error to enter a report.
    """
    target = max(4, int(_covers_for(business_date, rng) * covers_scale))
    served = 0
    number = 0
    bills = []
    while served < target:
        number += 1
        covers = _party_size(rng)
        served += covers
        dinner = rng.random() < _DINNER_SHARE
        bill = _build_bill(world, business_date, covers, number, dinner, rng)
        if bill is not None:
            bills.append(bill)
    return bills


def _party_size(rng: random.Random) -> int:
    roll = rng.random()
    running = 0.0
    for size, share in _PARTY_SIZES:
        running += share
        if roll <= running:
            return size
    return 2


def _placed_at(business_date: date, dinner: bool, rng: random.Random) -> datetime:
    """A time inside service, stored UTC.

    The lunch peak is 13:00—14:00 and the dinner peak 20:30—22:00, and the tail of dinner crosses
    midnight — which is the case invariant 4 exists for, and the one
    `test_a_late_bill_belongs_to_the_day_it_started` asserts.
    """
    if dinner:
        # Past midnight for the last tables — 25:30 is 1:30am, which still belongs to *this*
        # business day because a restaurant's day starts at 05:00 (invariant 4). Without this the
        # generated data never exercises the rule it was most carefully built around.
        minutes = int(rng.triangular(19 * 60, 25 * 60 + 30, 21 * 60))
    else:
        minutes = int(rng.triangular(12 * 60, 15 * 60 + 30, 13 * 60 + 30))
    local = datetime.combine(business_date, time(0, 0), tzinfo=UTC) + timedelta(minutes=minutes)
    # IST is +5:30. The business date is the restaurant's, not UTC's.
    return local - timedelta(hours=5, minutes=30)


def _build_bill(
    world: World,
    business_date: date,
    covers: int,
    number: int,
    dinner: bool,
    rng: random.Random,
) -> Bill | None:
    chosen = _plate_up(world, covers, rng)
    if not chosen:
        return None

    placed = _placed_at(business_date, dinner, rng)
    order_id = uuid.uuid4()
    lines: list[dict[str, object]] = []
    consumption: dict[uuid.UUID, Decimal] = {}
    subtotal = _ZERO
    tax_total = _ZERO
    cost_total = _ZERO

    for dish, quantity in chosen:
        line_subtotal = (dish.price * quantity).quantize(_MONEY, ROUND_HALF_UP)
        # **Each half is computed on the line, and the tax is their sum.** `app/core/tax.py` rule 1,
        # which this generator got wrong first time and `ck_order_line_gst_split` refused:
        # "computing a total and halving it leaves an odd paisa that has to be given to one side" —
        # ₹75.00 at 5% is ₹3.75, and 1.88 + 1.87 is not an equal split. Computing each half from
        # the line value makes them equal by construction, which is what the constraint requires
        # and what every bill this product issues actually does.
        half = (line_subtotal * _GST_RATE / 2).quantize(_MONEY, ROUND_HALF_UP)
        tax = half * 2
        plate_cost = _plate_cost(world, dish, business_date)
        cost_total += plate_cost * quantity
        for stock_item_id, grams in dish.recipe.items():
            consumption[stock_item_id] = consumption.get(stock_item_id, _ZERO) + grams * quantity
        lines.append(
            {
                "id": uuid.uuid4(),
                "restaurant_id": world.restaurant.id,
                "order_id": order_id,
                "menu_item_variant_id": dish.variant_id,
                "quantity": quantity,
                "unit_price": dish.price,
                "line_subtotal": line_subtotal,
                "tax_group_id": dish.tax_group_id,
                "tax_rate": _GST_RATE,
                "taxable_value": line_subtotal,
                "cgst_amount": half,
                "sgst_amount": half,
                "tax_amount": tax,
                "line_total": line_subtotal + tax,
                "theoretical_unit_cost": plate_cost,
                "status": OrderLineStatus.SERVED.value,
            }
        )
        subtotal += line_subtotal
        tax_total += tax

    return Bill(
        order_id=order_id,
        business_date=business_date,
        placed=placed,
        settled=placed + timedelta(minutes=int(rng.triangular(35, 95, 55))),
        covers=covers,
        dine_in=rng.random() < _DINE_IN_SHARE,
        dinner=dinner,
        waiter=_waiter_for(world, dinner, rng),
        customer=_customer_for(world, business_date, rng),
        number=number,
        lines=lines,
        chosen=chosen,
        consumption=consumption,
        subtotal=subtotal,
        tax_total=tax_total,
        cost_total=cost_total.quantize(_MONEY, ROUND_HALF_UP),
    )


def _plate_up(world: World, covers: int, rng: random.Random) -> list[tuple[Dish, int]]:
    """What this table ordered: a long tail, weighted by popularity.

    Roughly one and a quarter dishes per cover, which is what a North Indian table actually does —
    a curry, a bread and something to share rather than a main each.
    """
    weights = [dish.popularity for dish in world.dishes]
    wanted = max(1, int(covers * 1.25))
    chosen: dict[uuid.UUID, tuple[Dish, int]] = {}
    for dish in rng.choices(world.dishes, weights=weights, k=wanted):
        existing = chosen.get(dish.variant_id)
        chosen[dish.variant_id] = (dish, (existing[1] if existing else 0) + 1)
    return list(chosen.values())


def _waiter_for(world: World, dinner: bool, rng: random.Random) -> uuid.UUID | None:
    """Who served it.

    **Planted signal 6** begins here: one waiter takes a disproportionate share of *dinner* tables,
    so the errors planted against them are concentrated on dinner shifts rather than spread evenly.
    The finding M17 has to reach is "systemic, not individual" — the same person is fine at lunch —
    and that shape only exists if the shifts differ.
    """
    if not world.waiters:
        return None
    if dinner and rng.random() < 0.34:
        return world.waiters[0].id
    return rng.choice(world.waiters).id


# --------------------------------------------------------------------------- prices over time

# **Planted signal 13.** Tomato spikes 2.4x for three weeks — it happens every year and it wrecks
# gravy cost — and onion drifts up 30% across the window.
SPIKE_START_OFFSET = 62
SPIKE_DAYS = 21
SPIKE_MULTIPLIER = Decimal("2.4")
ONION_DRIFT = Decimal("0.30")

# **And the half of signal 13 that makes it visible on a plate.** A dish's recipe names a
# *preparation* — PREP_MAKHANI, not tomato — so a spike applied to tomato alone never reaches a
# theoretical unit cost, and the report the signal exists for would show nothing. The seed doc's
# own wording is the fix: "tomato price spike raises **gravy cost** 22% for 3 weeks". These are the
# three preparations `seed/preparations.yaml` builds on tomato.
TOMATO_PREPARATIONS = ("PREP_MAKHANI", "PREP_YELLOW", "PREP_DALMAKHANI")
GRAVY_SPIKE = Decimal("1.22")


def _price_multiplier(world: World, stock_item_id: uuid.UUID, business_date: date) -> Decimal:
    item = world.ingredients.get(stock_item_id)
    if item is None:
        return Decimal(1)
    spike = world.start + timedelta(days=SPIKE_START_OFFSET)
    in_the_spike = spike <= business_date < spike + timedelta(days=SPIKE_DAYS)
    if item.code == "TOMATO" and in_the_spike:
        return SPIKE_MULTIPLIER
    if item.code in TOMATO_PREPARATIONS and in_the_spike:
        return GRAVY_SPIKE
    if item.code == "ONION":
        # Linear across the window, so a cost report shows a drift rather than a step.
        elapsed = max(0, (business_date - world.start).days)
        return Decimal(1) + ONION_DRIFT * Decimal(elapsed) / Decimal(DEFAULT_DAYS)
    return Decimal(1)


def _price_on(world: World, stock_item_id: uuid.UUID, business_date: date) -> Decimal:
    base = world.prices.get(stock_item_id, _ZERO)
    return (base * _price_multiplier(world, stock_item_id, business_date)).quantize(_COST)


def _plate_cost(world: World, dish: Dish, business_date: date) -> Decimal:
    """What the recipe says this plate costs, at *that day's* ingredient prices.

    Frozen onto the line exactly as settlement freezes it: "what did this bill cost in March" is
    answered from March's prices rather than today's, and signal 13 only shows up in a report
    because of that.
    """
    total = _ZERO
    for stock_item_id, grams in dish.recipe.items():
        total += grams * _price_on(world, stock_item_id, business_date)
    return total.quantize(_COST, ROUND_HALF_UP)


# --------------------------------------------------------------------------- buying the week

# **Planted signal 3.** One supplier is unreliable, and the shortfall is small enough that nobody
# notices without weighing at the gate — which is exactly what M06's three-way match is for.
SHORT_DELIVERY_SHARE = 0.40
_SHORT_LOW = Decimal("0.95")
_SHORT_HIGH = Decimal("0.97")
# What "Fresh Farms" supplies, by the category `seed/ingredients.yaml` gives each ingredient.
FRESH_FARMS_CATEGORIES = ("veg", "fruit")

# **Planted signal 2.** Paneer is bought for the week with a third again on top, against a four-day
# shelf life. It expires about twice a month, which is what FEFO and the expiry alert exist to
# catch — and it is an over-*order*, not spoilage, which is a different fix.
PANEER_OVER_ORDER = Decimal("1.35")
_ORDINARY_MARGIN = Decimal("1.08")


async def _buy_the_week(
    session: AsyncSession,
    world: World,
    week_start: date,
    bills: list[Bill],
    rng: random.Random,
    summary: GeneratorSummary,
) -> dict[uuid.UUID, uuid.UUID]:
    """One delivery per ingredient for the week, sized to what the week will actually use.

    Without this every item goes deeply negative and the variance report has nothing in it but
    shortfall. A restaurant buys what it used plus a margin, and two signals live in that margin.
    """
    needed: dict[uuid.UUID, Decimal] = {}
    for bill in bills:
        for stock_item_id, grams in bill.consumption.items():
            needed[stock_item_id] = needed.get(stock_item_id, _ZERO) + grams

    batches: list[dict[str, object]] = []
    identifiers: dict[uuid.UUID, uuid.UUID] = {}
    received = datetime.combine(week_start, time(6, 30), tzinfo=UTC) - timedelta(
        hours=5, minutes=30
    )

    for stock_item_id, grams in sorted(needed.items(), key=lambda pair: str(pair[0])):
        item = world.ingredients.get(stock_item_id)
        if item is None or grams <= 0:
            continue
        margin = PANEER_OVER_ORDER if item.code == "PANEER" else _ORDINARY_MARGIN
        quantity = (grams * margin * _short_delivered(item, rng)).quantize(
            Decimal("0.0001"), ROUND_HALF_UP
        )
        if quantity <= 0:
            continue
        batch_id = uuid.uuid4()
        identifiers[stock_item_id] = batch_id
        shelf_life = world.shelf_life.get(stock_item_id, 0)
        batches.append(
            {
                "id": batch_id,
                "restaurant_id": world.restaurant.id,
                "stock_item_id": stock_item_id,
                "batch_code": f"G{week_start:%y%m%d}-{item.code}",
                "quantity_received": quantity,
                "unit_cost": _price_on(world, stock_item_id, week_start),
                "received_at": received,
                "expiry_date": week_start + timedelta(days=shelf_life) if shelf_life else None,
                "source": "purchase",
            }
        )

    if not batches:
        return identifiers

    await session.execute(insert(StockBatch), batches)
    await session.execute(
        insert(StockMovement),
        [
            {
                "id": uuid.uuid4(),
                "restaurant_id": world.restaurant.id,
                "stock_batch_id": batch["id"],
                "stock_item_id": batch["stock_item_id"],
                "type": MovementType.RECEIPT.value,
                "quantity_delta": batch["quantity_received"],
                "unit_cost": batch["unit_cost"],
                "basis": MovementBasis.ACTUAL.value,
                "occurred_at": received,
                "business_date": week_start,
            }
            for batch in batches
        ],
    )
    summary.batches += len(batches)
    summary.movements += len(batches)
    return identifiers


def _short_delivered(item: StockItem, rng: random.Random) -> Decimal:
    if item.category not in FRESH_FARMS_CATEGORIES or rng.random() >= SHORT_DELIVERY_SHARE:
        return Decimal(1)
    return _SHORT_LOW + (_SHORT_HIGH - _SHORT_LOW) * Decimal(str(round(rng.random(), 4)))


# --------------------------------------------------------------------------- writing the week


async def _write_week(
    session: AsyncSession,
    world: World,
    bills: list[Bill],
    batches: dict[uuid.UUID, uuid.UUID],
    sequence: int,
    rng: random.Random,
    summary: GeneratorSummary,
) -> int:
    """Every row a week of trading produces, in one pass of bulk inserts per table."""
    orders: list[dict[str, object]] = []
    lines: list[dict[str, object]] = []
    seats: list[dict[str, object]] = []
    invoices: list[dict[str, object]] = []
    payments: list[dict[str, object]] = []
    tickets: list[dict[str, object]] = []
    # Ticket numbers run per business date, exactly as `KitchenRepository.next_ticket_number`
    # allocates them. It cannot be the per-bill `index`: `uq_kot_ticket_number_per_day` is over
    # (restaurant_id, business_date, ticket_number), so every second bill of a day would collide.
    # `bills` spans a week and each business date appears in exactly one week, so a dict keyed on
    # the date is the whole counter.
    ticket_numbers: dict[date, int] = {}
    movements: list[dict[str, object]] = []

    for bill in bills:
        orders.append(
            {
                "id": bill.order_id,
                "restaurant_id": world.restaurant.id,
                # The number the **product** would have written, not a prettier one of our own.
                # `bill.number` already restarts at 1 each business day, which is the rule
                # `OrderRepository.next_order_number` implements and the reason a waiter can call
                # it across a kitchen at all.
                #
                # This used to be f"{business_date:%y%m%d}-{number:04d}". It read nicely and it put
                # the till on the floor: the allocator takes MAX over the day's numbers, could not
                # cast "260920-0048", and every attempt to open a table on a seeded restaurant
                # returned 500. **Generated data that does not look like real data hides exactly
                # the bugs a demo exists to surface** — here it manufactured one instead.
                "order_number": str(bill.number),
                "type": (OrderType.DINE_IN if bill.dine_in else OrderType.TAKEAWAY).value,
                "channel": OrderChannel.POS.value,
                "status": OrderStatus.SETTLED.value,
                "covers": bill.covers if bill.dine_in else None,
                "waiter_employee_id": bill.waiter,
                "customer_id": bill.customer,
                "placed_at": bill.placed,
                "first_sent_at": bill.placed + timedelta(minutes=4),
                "served_at": bill.settled - timedelta(minutes=15),
                "settled_at": bill.settled,
                "business_date": bill.business_date,
                "subtotal": bill.subtotal,
                "tax_total": bill.tax_total,
                "grand_total": bill.grand_total,
                "theoretical_food_cost": bill.cost_total,
            }
        )
        lines.extend(bill.lines)
        if bill.dine_in and world.tables:
            seats.append(
                {
                    "id": uuid.uuid4(),
                    "restaurant_id": world.restaurant.id,
                    "order_id": bill.order_id,
                    "restaurant_table_id": rng.choice(world.tables).id,
                    "is_primary": True,
                }
            )
        invoices.append(_invoice_row(world, bill, sequence))
        payments.append(_payment_row(world, bill, rng))
        tickets.extend(_ticket_rows(world, bill, rng, ticket_numbers))
        movements.extend(_theoretical_rows(world, bill, batches))
        sequence += 1

    # **Invariant 6 refuses a line on a settled order, and it is right to.** A bill that is closed
    # does not grow, and a trigger says so rather than a comment. History is not that case: the
    # whole bill arrives at once, already settled, the way it would from a restore — so the trigger
    # is stood down for exactly these two statements and put back immediately.
    #
    # The alternative is writing every bill open, adding its lines, then settling it, which is
    # three statements per bill instead of two per week and would make the generator a slow way of
    # re-enacting service rather than a fast way of writing history.
    await session.execute(text("SET LOCAL session_replication_role = replica"))
    await session.execute(insert(Order), orders)
    await session.execute(insert(OrderLine), lines)
    if seats:
        # The same trigger guards which tables a settled bill sat at, for the same reason.
        await session.execute(insert(OrderTable), seats)
    await session.execute(text("SET LOCAL session_replication_role = origin"))
    await session.execute(insert(Invoice), invoices)
    await session.execute(insert(Payment), payments)
    if tickets:
        await session.execute(insert(KotTicket), tickets)
    if movements:
        await session.execute(insert(StockMovement), movements)

    await _guest_reactions(session, world, bills, rng, summary)

    summary.orders += len(orders)
    summary.lines += len(lines)
    summary.movements += len(movements)
    return sequence


def _financial_year(business_date: date) -> str:
    """India's financial year runs April to March, and the invoice series restarts with it."""
    year = business_date.year if business_date.month >= 4 else business_date.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


def _invoice_number(financial_year: str, sequence: int) -> str:
    """The product's own formatter, not a second one.

    `app/core/tax.py::invoice_number` produces `2026-27/000123` — fourteen characters, inside CGST
    Rule 46(b)'s sixteen. The first draft here wrote `INV/2026-27/000001`, which is eighteen, and
    `ck_invoice_number_length` refused it. A generator formatting its own invoice numbers is a
    generator demonstrating documents the product could not legally issue.
    """
    return invoice_number(financial_year, sequence)


def _invoice_row(world: World, bill: Bill, sequence: int) -> dict[str, object]:
    """A real tax invoice: gapless per financial year, with the supplier GSTIN (Rule 46a).

    The invoice's halves are the sum of the lines' halves, not the total halved — which is the same
    rule as the line, for the same reason, and means the document adds up to its own lines.
    """
    half = bill.tax_total / 2
    year = _financial_year(bill.business_date)
    return {
        "id": uuid.uuid4(),
        "restaurant_id": world.restaurant.id,
        "order_id": bill.order_id,
        "document_type": "tax_invoice",
        "financial_year": year,
        "sequence": sequence,
        "invoice_number": _invoice_number(year, sequence),
        "status": InvoiceStatus.ISSUED.value,
        "issued_at": bill.settled,
        "invoice_date": bill.business_date,
        "business_date": bill.business_date,
        "supplier_name": world.restaurant.name,
        "supplier_gstin": world.restaurant.gstin,
        "taxable_total": bill.subtotal,
        "cgst_total": half,
        "sgst_total": bill.tax_total - half,
        "grand_total": bill.grand_total,
    }


def _payment_row(world: World, bill: Bill, rng: random.Random) -> dict[str, object]:
    roll = rng.random()
    running = 0.0
    method = PaymentMethod.CASH
    for candidate, share in _METHODS:
        running += share
        if roll <= running:
            method = candidate
            break
    return {
        "id": uuid.uuid4(),
        "restaurant_id": world.restaurant.id,
        "order_id": bill.order_id,
        "method": method.value,
        "amount": bill.grand_total,
        "status": PaymentStatus.SUCCESS.value,
        "paid_at": bill.settled,
        "business_date": bill.business_date,
    }


# **Planted signal 4.** Tandoor prep time rises 40% at 20:30-22:00 on Friday and Saturday. It is a
# *window*, not a constant: the same station is fine at lunch, which is what makes it a bottleneck
# rather than a slow station, and what the kitchen report has to separate.
BOTTLENECK_DAYS = (4, 5)
BOTTLENECK_FROM = time(20, 30)
BOTTLENECK_TO = time(22, 0)
BOTTLENECK_FACTOR = 1.40


def _in_the_bottleneck(placed: datetime, business_date: date) -> bool:
    local = (placed + timedelta(hours=5, minutes=30)).time()
    return business_date.weekday() in BOTTLENECK_DAYS and BOTTLENECK_FROM <= local <= BOTTLENECK_TO


def _ticket_rows(
    world: World, bill: Bill, rng: random.Random, ticket_numbers: dict[date, int]
) -> list[dict[str, object]]:
    """One ticket per station, with the times M08 measures against.

    `target_minutes` is the standard, frozen; the actual is `ready_at - printed_at`. Invariant 7's
    shape again: the standard and what happened are two different facts, and the gap is the finding.
    """
    by_station: dict[uuid.UUID, int] = {}
    for dish, _ in bill.chosen:
        by_station[dish.station_id] = max(by_station.get(dish.station_id, 0), dish.prep_minutes)

    printed = bill.placed + timedelta(minutes=4)
    slow = _in_the_bottleneck(bill.placed, bill.business_date)
    rows = []
    ordered = sorted(by_station.items(), key=lambda pair: str(pair[0]))
    for index, (station_id, target) in enumerate(ordered, start=1):
        ticket_number = ticket_numbers.get(bill.business_date, 0) + 1
        ticket_numbers[bill.business_date] = ticket_number
        stretch = BOTTLENECK_FACTOR if slow else 1.0
        actual = max(2, int(target * stretch * rng.uniform(0.85, 1.15)))
        acknowledged = printed + timedelta(minutes=1)
        started = acknowledged + timedelta(minutes=1)
        rows.append(
            {
                "id": uuid.uuid4(),
                "restaurant_id": world.restaurant.id,
                "order_id": bill.order_id,
                "station_id": station_id,
                # The number the product writes, for the reason given on `order_number` above:
                # generated data that does not look like real data hides the bugs a demo exists to
                # surface. This ran as f"{date:%y%m%d}-{number:04d}-{index}" and made
                # `next_ticket_number` raise, which turned "Send to kitchen" into a 500.
                #
                # **It is the per-day counter, not `index`.** `index` is this bill's station
                # ordinal and repeats on every bill; the uniqueness constraint is per business
                # date. `sequence_in_order` below is the one that genuinely is per bill, and
                # `uq_kot_ticket_round` is what holds it to that.
                "ticket_number": str(ticket_number),
                "sequence_in_order": index,
                "status": KotTicketStatus.READY.value,
                "target_minutes": target,
                "business_date": bill.business_date,
                "revision": 1,
                "printed_at": printed,
                "acknowledged_at": acknowledged,
                "started_at": started,
                "ready_at": started + timedelta(minutes=actual),
            }
        )
    return rows


def _theoretical_rows(
    world: World, bill: Bill, batches: dict[uuid.UUID, uuid.UUID]
) -> list[dict[str, object]]:
    """Theoretical consumption, written exactly as settlement writes it.

    Negative in the ledger, `basis='theoretical'`, one movement per ingredient per bill, drawing on
    the week's batch. **Never summed with the actual movements** (invariant 7): the gap between the
    two is the report this product exists for.

    A movement of zero is refused by the ledger, and rightly - nothing moved - so an ingredient a
    bill did not touch has no row rather than a row of zeroes.
    """
    rows = []
    for stock_item_id, grams in bill.consumption.items():
        batch_id = batches.get(stock_item_id)
        if batch_id is None or grams <= 0:
            continue
        rows.append(
            {
                "id": uuid.uuid4(),
                "restaurant_id": world.restaurant.id,
                "stock_batch_id": batch_id,
                "stock_item_id": stock_item_id,
                "type": MovementType.CONSUMPTION.value,
                "quantity_delta": -grams,
                "unit_cost": _price_on(world, stock_item_id, bill.business_date),
                "basis": MovementBasis.THEORETICAL.value,
                "occurred_at": bill.settled,
                "business_date": bill.business_date,
                "ref_type": "order",
                "ref_id": bill.order_id,
            }
        )
    return rows


# --------------------------------------------------------------------------- what guests did

# **Planted signal 5.** Ratings fall to about 3.3 in the same Friday/Saturday dinner-peak window
# that signal 4 slows down. The correlation is the point: `docs/customer-experience.md` argues that
# a rating is an operational measurement, and a product that shows the two on separate screens has
# thrown the finding away.
_RATING_WHEN_SLOW = (3, 3, 3, 4, 2)
_RATING_NORMAL = (5, 5, 4, 5, 4, 5, 3)
# Not every table leaves feedback, and a generator where they all do is one that hides the empty
# state every screen has to handle. Rule 3: plausible, not perfect.
FEEDBACK_SHARE = 0.22

# **Planted signal 8's other half.** Malai Kofta is ordered rarely and loved: its ratings are
# drawn from a pool that does not include a bad night.
HIDDEN_GEM = "MALAI_KOFTA"
_RATING_HIDDEN_GEM = (5, 5, 5, 4, 5)

# **Planted signal 14.** Eight complaints about biryani in one week, all at the dinner peak - the
# vision doc's own section 26 example, planted so the AI advisor can be tested against it when it
# is built.
COMPLAINT_WEEK_OFFSET = 96
COMPLAINT_DISH = "CHICKEN_BIRYANI"
_COMPLAINT_SHARE = 0.34


async def _guest_reactions(
    session: AsyncSession,
    world: World,
    bills: list[Bill],
    rng: random.Random,
    summary: GeneratorSummary,
) -> None:
    ratings: list[dict[str, object]] = []
    complaints: list[dict[str, object]] = []
    window = world.start + timedelta(days=COMPLAINT_WEEK_OFFSET)

    for bill in bills:
        slow = _in_the_bottleneck(bill.placed, bill.business_date)
        if rng.random() < FEEDBACK_SHARE:
            ratings.append(_rating_row(world, bill, slow, rng))
        in_the_week = window <= bill.business_date < window + timedelta(days=7)
        ordered_it = any(dish.item_code == COMPLAINT_DISH for dish, _ in bill.chosen)
        if in_the_week and ordered_it and bill.dinner and rng.random() < _COMPLAINT_SHARE:
            complaints.append(_complaint_row(world, bill))

    if ratings:
        await session.execute(insert(Feedback), ratings)
        summary.feedback += len(ratings)
    if complaints:
        await session.execute(insert(Complaint), complaints)
        summary.complaints += len(complaints)


def _rating_row(world: World, bill: Bill, slow: bool, rng: random.Random) -> dict[str, object]:
    gem = any(dish.item_code == HIDDEN_GEM for dish, _ in bill.chosen)
    pool: tuple[int, ...]
    if gem:
        pool = _RATING_HIDDEN_GEM
    elif slow:
        pool = _RATING_WHEN_SLOW
    else:
        pool = _RATING_NORMAL
    rating = rng.choice(pool)
    return {
        "id": uuid.uuid4(),
        "restaurant_id": world.restaurant.id,
        "order_id": bill.order_id,
        "overall_rating": rating,
        "food_rating": rating,
        "service_rating": max(1, rating - (1 if slow else 0)),
        "waiter_employee_id": bill.waiter,
        "source": "qr",
        "submitted_at": bill.settled + timedelta(minutes=6),
        "business_date": bill.business_date,
    }


def _complaint_row(world: World, bill: Bill) -> dict[str, object]:
    return {
        "id": uuid.uuid4(),
        "restaurant_id": world.restaurant.id,
        "order_id": bill.order_id,
        "reference": f"C/{bill.business_date:%y%m%d}/{bill.number:04d}",
        "category": "food_quality",
        "severity": "medium",
        "status": ComplaintStatus.RESOLVED.value,
        "financial_year": _financial_year(bill.business_date),
        "description": "The biryani was undercooked and took a long time to arrive.",
        "resolution": "Remade and comped.",
        "resolved_at": bill.settled + timedelta(hours=1),
        "business_date": bill.business_date,
    }


# --------------------------------------------------------------------------- what actually happened

# **Planted signal 9.** Butter Chicken consumes 12% more gravy than the recipe says. Portion drift
# is the commonest reason a real restaurant's food cost sits above its recipe cost, and it is
# invisible to everything except theoretical-against-actual - the report this product exists for.
DRIFT_DISH = "BUTTER_CHICKEN"
DRIFT_FACTOR = Decimal("0.12")

# **Planted signal 1.** Makhani gravy is over-produced by about 35% every Tuesday and Wednesday and
# thrown away at close. Prep is the biggest waste stage and the least measured
# (`docs/waste-model.md` section 3), and it is the one with a same-day fix.
OVER_PREP_ITEM = "PREP_MAKHANI"
OVER_PREP_DAYS = (1, 2)
OVER_PREP_SHARE = Decimal("0.35")
# On the event as well as on the movement, so a test can tell this from M09's own seeded waste
# without guessing at dates — the two overlap, and they are different signals.
OVER_PREP_NOTE = "Made for the day and not sold."

# **Planted signal 10.** Staff meals are about 18,000 rupees a month and were untracked before this
# product separated them. They are **not waste**: `docs/waste-model.md` section 4 is explicit that
# lumping them in destroys the variance number, and an Indian restaurant feeds its staff, always.
STAFF_MEAL_SHARE = Decimal("0.030")

# **Planted signal 11.** Comps are about 9,000 rupees a month and 70% of them are authorised by one
# manager. That concentration is the finding - one person comping most of the free food is a
# question, not an accusation, and the product's job is to make it visible.
COMP_SHARE = Decimal("0.015")
COMP_CONCENTRATION = 0.70

# **Planted signal 6's second half.** One waiter's tables produce accuracy errors - a dish remade or
# sent back - at about twice the rate of everybody else, and only at dinner. Logged as service-stage
# waste against the order, which is where a returned dish actually goes.
ERROR_RATE = 0.012
ERROR_MULTIPLIER = 2.1

# Rule 3: a day the waste log was skipped. Somebody was busy, and every report has to survive it.
SKIPPED_LOG_WEEKDAY = 6


async def _what_actually_happened(
    session: AsyncSession,
    world: World,
    week_start: date,
    bills: list[Bill],
    batches: dict[uuid.UUID, uuid.UUID],
    rng: random.Random,
    summary: GeneratorSummary,
) -> None:
    """The half of the ledger the recipes do not know about.

    Theoretical consumption says what *should* have been used. This writes what was: the portion
    drift, the over-produced gravy, the staff meals, the comps and the returned dishes. The gap
    between the two is the number `docs/seed-data.md` calls "the entire product" - about six points
    of food cost, roughly 95,000 rupees a month on this restaurant's revenue.
    """
    actual: dict[uuid.UUID, Decimal] = {}
    for bill in bills:
        for dish, quantity in bill.chosen:
            drift = DRIFT_FACTOR if dish.item_code == DRIFT_DISH else Decimal(0)
            for stock_item_id, grams in dish.recipe.items():
                used = grams * quantity * (Decimal(1) + drift)
                actual[stock_item_id] = actual.get(stock_item_id, _ZERO) + used

    movements: list[dict[str, object]] = []
    occurred = datetime.combine(week_start + timedelta(days=6), time(23, 0), tzinfo=UTC)
    for stock_item_id, grams in sorted(actual.items(), key=lambda pair: str(pair[0])):
        batch_id = batches.get(stock_item_id)
        if batch_id is None or grams <= 0:
            continue
        movements.append(
            {
                "id": uuid.uuid4(),
                "restaurant_id": world.restaurant.id,
                "stock_batch_id": batch_id,
                "stock_item_id": stock_item_id,
                "type": MovementType.CONSUMPTION.value,
                "quantity_delta": -grams.quantize(Decimal("0.0001"), ROUND_HALF_UP),
                "unit_cost": _price_on(world, stock_item_id, week_start),
                "basis": MovementBasis.ACTUAL.value,
                "occurred_at": occurred,
                "business_date": week_start + timedelta(days=6),
                "note": "Counted against the shelf at the end of the week.",
            }
        )
    if movements:
        await session.execute(insert(StockMovement), movements)
        summary.movements += len(movements)

    await _prep_waste(session, world, week_start, actual, batches, summary)
    await _staff_meals_and_comps(session, world, week_start, bills, batches, rng, summary)


async def _prep_waste(
    session: AsyncSession,
    world: World,
    week_start: date,
    actual: dict[uuid.UUID, Decimal],
    batches: dict[uuid.UUID, uuid.UUID],
    summary: GeneratorSummary,
) -> None:
    """Signal 1, and the one day a week nobody logged anything.

    The gravy is made in the morning for the day and what is left at close is thrown away. It is
    logged as `OVER_PREPARATION` at the prep stage, which is the reason with a same-day fix: make
    less of it on a Tuesday.
    """
    reason = world.reasons.get("OVER_PREPARATION")
    item = next(
        (candidate for candidate in world.ingredients.values() if candidate.code == OVER_PREP_ITEM),
        None,
    )
    if reason is None or item is None or world.reporter is None:
        return
    batch_id = batches.get(item.id)
    weekly = actual.get(item.id)
    if batch_id is None or weekly is None or weekly <= 0:
        return

    events: list[dict[str, object]] = []
    movements: list[dict[str, object]] = []
    for weekday in OVER_PREP_DAYS:
        business_date = week_start + timedelta(days=weekday)
        if business_date.weekday() == SKIPPED_LOG_WEEKDAY:
            continue
        # A seventh of the week's use, over-produced by a third on top of it.
        quantity = (weekly / 7 * OVER_PREP_SHARE).quantize(Decimal("0.0001"), ROUND_HALF_UP)
        if quantity <= 0:
            continue
        cost = _price_on(world, item.id, business_date)
        occurred = datetime.combine(business_date, time(23, 30), tzinfo=UTC) - timedelta(
            hours=5, minutes=30
        )
        event_id = uuid.uuid4()
        movements.append(
            {
                "id": uuid.uuid4(),
                "restaurant_id": world.restaurant.id,
                "stock_batch_id": batch_id,
                "stock_item_id": item.id,
                "type": MovementType.WASTAGE.value,
                "quantity_delta": -quantity,
                "unit_cost": cost,
                "basis": MovementBasis.ACTUAL.value,
                "occurred_at": occurred,
                "business_date": business_date,
                "note": OVER_PREP_NOTE,
                # `wastage_event` carries no movement id; the movement points back at the event,
                # which is the direction M09 already uses for every other reference.
                "ref_type": "wastage_event",
                "ref_id": event_id,
            }
        )
        events.append(
            {
                "id": event_id,
                "restaurant_id": world.restaurant.id,
                "stock_item_id": item.id,
                "stock_batch_id": batch_id,
                "wastage_reason_id": reason.id,
                "quantity": quantity,
                "cost_value": (quantity * cost).quantize(_MONEY, ROUND_HALF_UP),
                "occurred_at": occurred,
                "business_date": business_date,
                "reported_by": world.reporter,
                "note": OVER_PREP_NOTE,
            }
        )
    if movements:
        await session.execute(insert(StockMovement), movements)
        await session.execute(insert(WastageEvent), events)
        summary.movements += len(movements)
        summary.wastage += len(events)


async def _staff_meals_and_comps(
    session: AsyncSession,
    world: World,
    week_start: date,
    bills: list[Bill],
    batches: dict[uuid.UUID, uuid.UUID],
    rng: random.Random,
    summary: GeneratorSummary,
) -> None:
    """Signals 10 and 11, and the distinction between them that `docs/waste-model.md` insists on.

    A staff meal is **not waste**. Counted as waste it looks like theft and poisons every variance
    number; it has its own movement type for exactly that reason. A comp is not waste either - it
    is food that was given away on purpose, and the question it raises is *who kept giving it away*.
    """
    # The first staple this week actually bought. Picking one the week did not buy leaves no batch
    # for the movement to draw on, and the two signals then silently do not appear — which is the
    # failure `docs/seed-data.md` rule 4 is about: an anomaly that is documented and not planted.
    staple = next(
        (
            candidate
            for candidate in world.ingredients.values()
            if candidate.code in ("BASMATI", "ATTA", "ONION", "OIL") and candidate.id in batches
        ),
        None,
    )
    if staple is None:
        return
    batch_id = batches[staple.id]

    revenue = sum((bill.subtotal for bill in bills), _ZERO)
    if revenue <= 0:
        return
    price = _price_on(world, staple.id, week_start)
    if price <= 0:
        return

    rows = []
    for kind, share in (
        (MovementType.STAFF_MEAL, STAFF_MEAL_SHARE),
        (MovementType.COMPLIMENTARY, COMP_SHARE),
    ):
        value = revenue * share
        quantity = (value / price).quantize(Decimal("0.0001"), ROUND_HALF_UP)
        if quantity <= 0:
            continue
        occurred = datetime.combine(week_start + timedelta(days=5), time(16, 0), tzinfo=UTC)
        rows.append(
            {
                "id": uuid.uuid4(),
                "restaurant_id": world.restaurant.id,
                "stock_batch_id": batch_id,
                "stock_item_id": staple.id,
                "type": kind.value,
                "quantity_delta": -quantity,
                "unit_cost": price,
                "basis": MovementBasis.ACTUAL.value,
                "occurred_at": occurred,
                "business_date": week_start + timedelta(days=5),
                "actor_employee_id": _comp_authoriser(world, kind, rng),
                "note": (
                    "Staff meals for the week."
                    if kind is MovementType.STAFF_MEAL
                    else "Comped dishes for the week."
                ),
            }
        )
    if rows:
        await session.execute(insert(StockMovement), rows)
        summary.movements += len(rows)


def _comp_authoriser(world: World, kind: MovementType, rng: random.Random) -> uuid.UUID | None:
    """Signal 11's concentration: 70% of comps carry the same name.

    One person authorising most of the free food is a question worth asking. It is never an
    accusation - a manager who works every Friday will authorise most of Friday's comps - and the
    product's job is to make the pattern visible, not to conclude anything from it.
    """
    if not world.waiters:
        return None
    if kind is MovementType.COMPLIMENTARY and rng.random() < COMP_CONCENTRATION:
        return world.waiters[1].id if len(world.waiters) > 1 else world.waiters[0].id
    return rng.choice(world.waiters).id


async def _service_errors(
    session: AsyncSession,
    world: World,
    bills: list[Bill],
    batches: dict[uuid.UUID, uuid.UUID],
    rng: random.Random,
    summary: GeneratorSummary,
) -> None:
    """**Planted signal 6's second half.** A dish sent back, logged at the service stage.

    One waiter's tables produce these at about twice everybody else's rate, and only at dinner. The
    finding M17 has to reach is that the pattern is *systemic rather than individual* — the same
    person is fine at lunch, which points at the shift, the station and the pace rather than at
    them. A product that concluded "this waiter is careless" from this data would be wrong, and
    `docs/workload-fairness.md` is why the guardrails exist.

    Logged against the bill it happened on, because a returned dish is an event with an order
    behind it and not a line in a weekly total.
    """
    reason = world.reasons.get("CUSTOMER_RETURN") or world.reasons.get("REMAKE")
    if reason is None or world.reporter is None or not world.waiters:
        return
    suspect = world.waiters[0].id

    events: list[dict[str, object]] = []
    movements: list[dict[str, object]] = []
    for bill in bills:
        rate = ERROR_RATE
        if bill.dinner and bill.waiter == suspect:
            rate *= ERROR_MULTIPLIER
        if rng.random() >= rate:
            continue
        dish, _ = bill.chosen[0]
        stock_item_id = next(iter(dish.recipe), None)
        batch_id = None if stock_item_id is None else batches.get(stock_item_id)
        if stock_item_id is None or batch_id is None:
            continue
        quantity = dish.recipe[stock_item_id]
        cost = _price_on(world, stock_item_id, bill.business_date)
        event_id = uuid.uuid4()
        movements.append(
            {
                "id": uuid.uuid4(),
                "restaurant_id": world.restaurant.id,
                "stock_batch_id": batch_id,
                "stock_item_id": stock_item_id,
                "type": MovementType.WASTAGE.value,
                "quantity_delta": -quantity,
                "unit_cost": cost,
                "basis": MovementBasis.ACTUAL.value,
                "occurred_at": bill.settled,
                "business_date": bill.business_date,
                "actor_employee_id": bill.waiter,
                "ref_type": "wastage_event",
                "ref_id": event_id,
                "note": "Sent back by the table.",
            }
        )
        events.append(
            {
                "id": event_id,
                "restaurant_id": world.restaurant.id,
                "stock_item_id": stock_item_id,
                "stock_batch_id": batch_id,
                "wastage_reason_id": reason.id,
                "quantity": quantity,
                "cost_value": (quantity * cost).quantize(_MONEY, ROUND_HALF_UP),
                "occurred_at": bill.settled,
                "business_date": bill.business_date,
                "reported_by": bill.waiter or world.reporter,
            }
        )

    if movements:
        await session.execute(insert(StockMovement), movements)
        await session.execute(insert(WastageEvent), events)
        summary.movements += len(movements)
        summary.wastage += len(events)


# **Planted signal 12.** Six regulars who came five times or more stop coming after week 14. Churn
# is invisible in a revenue line — the covers hold up, because other people come — and it is only
# visible per person, which is the whole argument for M10 having a customer record at all.
REGULARS_STOP_AFTER_WEEK = 14
REGULARS_WHO_LEAVE = 6
_REGULAR_SHARE = 0.16


def _customer_for(world: World, business_date: date, rng: random.Random) -> uuid.UUID | None:
    """**Planted signal 12.** Six regulars stop coming after week 14.

    Churn is invisible in a revenue line — the covers hold up, because other people come — and it
    is only visible per person, which is the whole argument for M10 keeping a customer record.

    Chosen while the bill is being built rather than set afterwards: **a settled order is
    immutable** (invariant 6, enforced by a trigger), and M10 puts a customer on an order while it
    is still open for exactly that reason. The first draft updated the orders after writing them,
    and the database refused — the invariant doing its job on the generator as well as on the
    product.
    """
    if not world.customers or rng.random() >= _REGULAR_SHARE:
        return None
    week = (business_date - world.start).days // 7
    if week < REGULARS_STOP_AFTER_WEEK:
        return rng.choice(world.customers)
    leavers = set(world.customers[:REGULARS_WHO_LEAVE])
    staying = [customer for customer in world.customers if customer not in leavers]
    return rng.choice(staying) if staying else None
