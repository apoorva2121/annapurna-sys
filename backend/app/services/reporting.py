"""The reports themselves: the baselines, the quadrant, and the number the module exists for.

Four rules, and each of them is here rather than in a query or in a browser for a reason.

**The baseline comes from the server, over the same bounded query.** `docs/ui/conventions.md`:
*"Every metric shows a comparison (vs yesterday, vs last week) — a number with no baseline is not
information."* A browser subtracting two separately-fetched numbers is one rounding rule away from
disagreeing with the figure printed beside it.

**Unexplained variance is computed once, here.** Total variance minus the waste somebody wrote a
reason for. It is the line an owner acts on, and the only line in the product that says *this much
of your food went somewhere nobody can account for*.

**A percentage is computed once, at the end, from unrounded inputs.** Rounding twice is how a
column stops adding up to its own total, and a report is where that looks most harmless.

**Nothing here decides anything about a person.** Variance belongs to a dish and a period, never to
an employee: M17 is where people are measured and it has guardrails this module does not.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantScope
from app.repositories.reporting import (
    ConsumptionRow,
    DishRow,
    PaymentSplit,
    ReportingRepository,
    SalesDay,
)

# Two decimal places for money, four for a percentage before it is presented. Quantising once, at
# the boundary, is the rule invariant 3 exists for.
_MONEY = Decimal("0.01")
_PERCENT = Decimal("0.01")

# Where a dish sits in the quadrant. Both thresholds are *relative to this restaurant's own
# period* — an absolute food-cost percentage would be wrong for a bakery and wrong again for a bar,
# and a fixed "popular" number would be wrong for every restaurant on a Tuesday.
QUADRANT_POPULARITY_SHARE = Decimal("1.0")
"""A dish is popular if it sold more than its equal share of the period's units."""


@dataclass(frozen=True, slots=True)
class Compared:
    """A figure and what it is being compared with. Both, or the comparison is decoration."""

    value: Decimal
    previous: Decimal

    @property
    def change(self) -> Decimal:
        return self.value - self.previous

    @property
    def change_percent(self) -> Decimal | None:
        """`None` when there is nothing to compare against — not zero.

        Zero would read as "unchanged", which is a different and false statement: a restaurant's
        first Tuesday is not a Tuesday that did not move.
        """
        if self.previous == 0:
            return None
        return ((self.value - self.previous) / self.previous * 100).quantize(_PERCENT)


@dataclass(frozen=True, slots=True)
class SalesReport:
    since: date
    until: date
    days: Sequence[SalesDay]
    payments: Sequence[PaymentSplit]
    revenue: Compared
    covers: Compared
    average_bill: Compared


@dataclass(frozen=True, slots=True)
class VarianceLine:
    """One stock item's theoretical, actual, and the part of the gap nobody explained."""

    stock_item_id: uuid.UUID
    item_name: str
    base_unit: str
    theoretical_quantity: Decimal
    actual_quantity: Decimal
    variance_quantity: Decimal
    theoretical_value: Decimal
    actual_value: Decimal
    variance_value: Decimal
    waste_value: Decimal
    unexplained_value: Decimal


@dataclass(frozen=True, slots=True)
class VarianceReport:
    since: date
    until: date
    lines: Sequence[VarianceLine]
    theoretical_total: Decimal
    actual_total: Decimal
    variance_total: Decimal
    waste_total: Decimal
    unexplained_total: Decimal


@dataclass(frozen=True, slots=True)
class DishLine:
    variant_id: uuid.UUID
    item_name: str
    variant_name: str
    units: int
    revenue: Decimal
    theoretical_cost: Decimal
    margin: Decimal
    food_cost_percent: Decimal | None
    average_rating: Decimal | None
    average_prep_seconds: int | None
    quadrant: str
    advice: str


@dataclass(frozen=True, slots=True)
class DishReport:
    since: date
    until: date
    lines: Sequence[DishLine]


@dataclass(frozen=True, slots=True)
class TodayReport:
    business_date: date
    revenue: Compared
    covers: Compared
    open_orders: int
    average_rating: Decimal | None
    ratings_counted: int


class ReportingService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._reports = ReportingRepository(session, scope)

    # ------------------------------------------------------------------ sales

    async def sales(self, *, since: date, until: date) -> SalesReport:
        days = await self._reports.sales_by_day(since=since, until=until)
        payments = await self._reports.payments_by_method(since=since, until=until)
        previous_since, previous_until = _previous_period(since, until)
        previous = await self._reports.sales_by_day(since=previous_since, until=previous_until)

        revenue = _sum(day.revenue for day in days)
        covers = Decimal(sum(day.covers for day in days))
        previous_revenue = _sum(day.revenue for day in previous)
        previous_covers = Decimal(sum(day.covers for day in previous))

        return SalesReport(
            since=since,
            until=until,
            days=days,
            payments=payments,
            revenue=Compared(revenue.quantize(_MONEY), previous_revenue.quantize(_MONEY)),
            covers=Compared(covers, previous_covers),
            average_bill=Compared(
                _per(revenue, Decimal(sum(day.orders for day in days))),
                _per(previous_revenue, Decimal(sum(day.orders for day in previous))),
            ),
        )

    # ------------------------------------------------------------- the variance

    async def food_cost_variance(self, *, since: date, until: date) -> VarianceReport:
        """The module's reason to exist.

        **Theoretical and actual are never added together** (invariant 7) — they are subtracted,
        and the remainder after the explained waste is taken out is the number an owner acts on.
        """
        rows = await self._reports.consumption(since=since, until=until)
        lines = [_variance_line(row) for row in rows if _is_material(row)]
        return VarianceReport(
            since=since,
            until=until,
            lines=lines,
            theoretical_total=_sum(line.theoretical_value for line in lines).quantize(_MONEY),
            actual_total=_sum(line.actual_value for line in lines).quantize(_MONEY),
            variance_total=_sum(line.variance_value for line in lines).quantize(_MONEY),
            waste_total=_sum(line.waste_value for line in lines).quantize(_MONEY),
            unexplained_total=_sum(line.unexplained_value for line in lines).quantize(_MONEY),
        )

    # -------------------------------------------------------------- the dishes

    async def dish_performance(self, *, since: date, until: date) -> DishReport:
        rows = await self._reports.dish_performance(since=since, until=until)
        total_units = sum(row.units for row in rows)
        total_revenue = _sum(row.revenue for row in rows)
        # The averages this restaurant's own period produced. A fixed threshold would be wrong for
        # a bakery and wrong again for a bar.
        average_units = Decimal(total_units) / len(rows) if rows else Decimal(0)
        average_margin_rate = (
            (total_revenue - _sum(row.theoretical_cost for row in rows)) / total_revenue
            if total_revenue
            else Decimal(0)
        )
        return DishReport(
            since=since,
            until=until,
            lines=[_dish_line(row, average_units, average_margin_rate) for row in rows],
        )

    # --------------------------------------------------------------- the glance

    async def today(self, *, business_date: date) -> TodayReport:
        days = await self._reports.sales_by_day(since=business_date, until=business_date)
        yesterday = business_date - timedelta(days=1)
        previous = await self._reports.sales_by_day(since=yesterday, until=yesterday)
        rating, counted = await self._reports.ratings(since=business_date, until=business_date)
        return TodayReport(
            business_date=business_date,
            revenue=Compared(
                _sum(day.revenue for day in days).quantize(_MONEY),
                _sum(day.revenue for day in previous).quantize(_MONEY),
            ),
            covers=Compared(
                Decimal(sum(day.covers for day in days)),
                Decimal(sum(day.covers for day in previous)),
            ),
            open_orders=await self._reports.open_orders(),
            average_rating=None if rating is None else rating.quantize(_PERCENT),
            ratings_counted=counted,
        )


# ---------------------------------------------------------------------- helpers


def _sum(values: Iterable[Decimal]) -> Decimal:
    """`sum()` starts at the integer 0 and returns one for an empty sequence, which then flows into
    a `Decimal` calculation as the wrong type. Starting at `Decimal(0)` keeps money money."""
    total = Decimal(0)
    for value in values:
        total += value
    return total


def _per(total: Decimal, count: Decimal) -> Decimal:
    """Zero rather than a division error when nothing happened. A day with no bills has an average
    bill of nothing, which is a true statement."""
    if count == 0:
        return Decimal(0).quantize(_MONEY)
    return (total / count).quantize(_MONEY)


def _previous_period(since: date, until: date) -> tuple[date, date]:
    """The same number of days, immediately before.

    Not "last month" or "the same week last year": a comparison has to be against a period of the
    same length, or the change is arithmetic about the calendar rather than about the restaurant.
    """
    length = (until - since).days + 1
    return since - timedelta(days=length), since - timedelta(days=1)


def _is_material(row: ConsumptionRow) -> bool:
    """Items that moved at all. An item with no consumption on either basis is not a line with
    zeroes in it — it is an item this period has nothing to say about, and a report full of those
    is a report nobody scrolls to the bottom of."""
    return bool(row.theoretical_quantity or row.actual_quantity or row.waste_quantity)


def _variance_line(row: ConsumptionRow) -> VarianceLine:
    """**Actual minus theoretical**, so a positive variance means more was used than the recipes
    say — which is the direction that costs money and the direction an owner is looking for."""
    variance_quantity = row.actual_quantity - row.theoretical_quantity
    variance_value = row.actual_value - row.theoretical_value
    return VarianceLine(
        stock_item_id=row.stock_item_id,
        item_name=row.item_name,
        base_unit=row.base_unit,
        theoretical_quantity=row.theoretical_quantity,
        actual_quantity=row.actual_quantity,
        variance_quantity=variance_quantity,
        theoretical_value=row.theoretical_value,
        actual_value=row.actual_value,
        variance_value=variance_value,
        waste_value=row.waste_value,
        # The part nobody wrote a reason for. Never negative on screen: waste larger than the
        # variance means the waste *is* the variance and there is nothing left unexplained.
        unexplained_value=max(variance_value - row.waste_value, Decimal(0)),
    )


def _dish_line(row: DishRow, average_units: Decimal, average_margin_rate: Decimal) -> DishLine:
    """Vision doc §12, with the one rule that matters: **this advises, it never acts.**"""
    margin = row.revenue - row.theoretical_cost
    margin_rate = (margin / row.revenue) if row.revenue else Decimal(0)
    popular = Decimal(row.units) >= average_units
    profitable = margin_rate >= average_margin_rate
    quadrant, advice = _QUADRANT[(popular, profitable)]
    return DishLine(
        variant_id=row.variant_id,
        item_name=row.item_name,
        variant_name=row.variant_name,
        units=row.units,
        revenue=row.revenue.quantize(_MONEY),
        theoretical_cost=row.theoretical_cost.quantize(_MONEY),
        margin=margin.quantize(_MONEY),
        food_cost_percent=(
            (row.theoretical_cost / row.revenue * 100).quantize(_PERCENT) if row.revenue else None
        ),
        average_rating=(
            None if row.average_rating is None else row.average_rating.quantize(_PERCENT)
        ),
        average_prep_seconds=row.average_prep_seconds,
        quadrant=quadrant,
        advice=advice,
    )


# The four names and what each one suggests. **Every sentence is advice with the numbers beside
# it** — a product that removed a dish because a quadrant said so would be wrong about one
# restaurant in five, and the one it was wrong about would be somebody's signature dish.
_QUADRANT: dict[tuple[bool, bool], tuple[str, str]] = {
    (True, True): (
        "star",
        "Sells well and earns well. Protect it — keep it available and in stock.",
    ),
    (True, False): (
        "plough_horse",
        "Sells well and earns little. Check the portion against the recipe, then the price.",
    ),
    (False, True): (
        "hidden_gem",
        "Earns well and few people order it. Worth promoting before changing anything else.",
    ),
    (False, False): (
        "dog",
        "Neither sells nor earns. Worth asking whether it belongs on the menu at all.",
    ),
}
