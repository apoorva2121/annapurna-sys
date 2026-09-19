"""M19 · Owner Analytics — trends over time, and branches beside each other.

**This module computes no metric of its own.** Every figure here is M13's, fetched through
`ReportingService`/`ReportingRepository` and then bucketed or grouped. That is the whole design:
`docs/plan/m19-build-log.md`'s metric table exists because M13 pinned the arithmetic in one place
and a second module restating any of it is how two screens end up disagreeing about food cost %.

**The org view is the owner's decision of 2026-09-19** (`docs/owner-actions.md` Q3): a comparison
first and a sum second. A sum answers *"how are we doing"*; a comparison answers *"which branch has
the problem"*, and only the second leads to an action. What follows from that answer is enforced
here rather than left to the screen:

- revenue, covers, orders and discounts sum across branches;
- **tax does not sum**, and `BranchComparison` carries no field that could hold a tax total. Two
  branches under one organization can hold different GSTINs and different schemes; a summed tax
  figure has no legal referent. It is refused structurally rather than by a comment asking nicely;
- a branch that traded nine days of thirty carries `business_days_traded`, and every per-day figure
  divides by *that*, never by the length of the window.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.repositories.access import AccessRepository
from app.repositories.reporting import ReportingRepository, SalesDay

_MONEY = Decimal("0.01")


class Metric(StrEnum):
    """What a series can be drawn of.

    Every member has a row in `docs/plan/m19-build-log.md`'s metric table naming its source tables
    and its formula. A member added here without that row is the thing the table exists to prevent.

    `TAX` is absent on purpose and not by oversight — see this module's docstring.
    """

    REVENUE = "revenue"
    COVERS = "covers"
    ORDERS = "orders"
    DISCOUNTS = "discounts"
    AVERAGE_BILL = "average_bill"


class Bucket(StrEnum):
    DAY = "day"
    WEEK = "week"


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    """One bucket. `starts_on`/`ends_on` are business dates, inclusive at both ends."""

    starts_on: date
    ends_on: date
    value: Decimal | None
    #: Business dates inside this bucket that actually issued an invoice. A bucket with 2 of 7
    #: is not a quiet week; it is a week the shop was shut, and the screen must be able to say so.
    days_traded: int


@dataclass(frozen=True, slots=True)
class Series:
    metric: Metric
    bucket: Bucket
    since: date
    until: date
    restaurant_ids: tuple[uuid.UUID, ...]
    points: tuple[SeriesPoint, ...]


@dataclass(frozen=True, slots=True)
class BranchRow:
    """One branch over the window.

    No tax field, and that is load-bearing rather than an omission — see the module docstring.
    """

    restaurant_id: uuid.UUID
    name: str
    revenue: Decimal
    #: Dine-in revenue only. `comparison_basis` divides by covers and `covers` is NULL for takeaway
    #: and delivery, so this is the only numerator that yields a real spend-per-guest.
    dine_in_revenue: Decimal
    covers: int
    orders: int
    business_days_traded: int
    #: `revenue / business_days_traded` — decision 1.3. `None` when the branch never traded, which
    #: is a different statement from zero and is rendered differently.
    revenue_per_trading_day: Decimal | None


@dataclass(frozen=True, slots=True)
class BranchComparison:
    since: date
    until: date
    branches: tuple[BranchRow, ...]
    #: The figures that may be summed, and only those.
    total_revenue: Decimal
    total_covers: int
    total_orders: int
    #: Recomputed from the summed revenue and the summed orders — never an average of the branch
    #: averages, which would weight a quiet branch equally with a busy one.
    average_bill: Decimal | None


def _weeks_back(since: date, until: date) -> list[tuple[date, date]]:
    """Seven-business-date buckets, anchored to `until` and counted backwards.

    Not `date_trunc('week', …)`. `invoice.business_date` is already the restaurant's own day
    (invariant 4, paid for once in M07); re-deriving a calendar week from a timestamp here would be
    paying for it a second time and getting a different answer at 2am.

    Anchored to the **end** so the most recent bucket is always whole and the ragged one is the
    oldest. An owner comparing this week against a partial week that happens to sit at the start of
    the window is being shown a fall that is not there.
    """
    buckets: list[tuple[date, date]] = []
    end = until
    while end >= since:
        start = max(since, end - timedelta(days=6))
        buckets.append((start, end))
        end = start - timedelta(days=1)
    return list(reversed(buckets))


def _days(since: date, until: date) -> list[tuple[date, date]]:
    span = (until - since).days
    return [(since + timedelta(days=n),) * 2 for n in range(span + 1)]


def _sum(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0"))


def _bucket_value(metric: Metric, rows: Sequence[SalesDay]) -> Decimal | None:
    """The metric table's formulas, and nothing invented here.

    `AVERAGE_BILL` is `revenue / orders` and is **undefined rather than zero** when nothing was
    sold: a bucket with no orders has no average bill, and rendering ₹0.00 would draw a line
    through the floor on a day the restaurant was closed.
    """
    if not rows:
        return None
    match metric:
        case Metric.REVENUE:
            return _sum([row.revenue for row in rows]).quantize(_MONEY)
        case Metric.DISCOUNTS:
            return _sum([row.discounts for row in rows]).quantize(_MONEY)
        case Metric.COVERS:
            return Decimal(sum(row.covers for row in rows))
        case Metric.ORDERS:
            return Decimal(sum(row.orders for row in rows))
        case Metric.AVERAGE_BILL:
            orders = sum(row.orders for row in rows)
            if orders == 0:
                return None
            return (_sum([row.revenue for row in rows]) / orders).quantize(_MONEY)


class AnalyticsService:
    """Chunk A: series and the branch comparison. Charts are chunk B and live entirely in the
    frontend — nothing here knows what a colour is."""

    def __init__(self, session: AsyncSession, actor: Actor) -> None:
        self.session = session
        self.actor = actor
        self._access = AccessRepository(session)

    async def branch_ids(self) -> tuple[uuid.UUID, ...]:
        """Every branch this analytics view covers.

        **Not a new rule.** The owner chose the shape of the view, not who can see which branch, and
        an access rule already exists: `AuthService.switch_restaurant` admits exactly the branches
        in `AccessRepository.restaurants_for_employee`. Reusing it means a two-branch manager sees
        their two and the owner's view is the general case rather than a second feature.

        The organization boundary is **not** enforced here. It is enforced inside
        `ReportingRepository._real_restaurants`, where it cannot be forgotten by a future caller
        that builds its own list.
        """
        held = await self._access.restaurants_for_employee(self.actor.employee_id)
        if not held:
            # Every actor is assigned somewhere to have logged in at all; belt and braces for the
            # case where the assignment is withdrawn mid-session.
            return (self.actor.restaurant_id,)
        return tuple(held)

    def _reports(self, restaurant_ids: Sequence[uuid.UUID]) -> ReportingRepository:
        return ReportingRepository(self.session, self.actor.scope, across=restaurant_ids)

    async def series(
        self,
        *,
        metric: Metric,
        since: date,
        until: date,
        bucket: Bucket,
        across_branches: bool,
    ) -> Series:
        """One metric over time, over one branch or over all of them.

        **One query, then arithmetic in Python.** `sales_by_day` already returns a row per business
        date, so a series is that result bucketed — not one query per bucket, which is how an
        eight-week weekly trend becomes fifty-six round trips and misses the 800 ms budget on the
        only screen that has one.
        """
        restaurant_ids = await self.branch_ids() if across_branches else (self.actor.restaurant_id,)
        rows = await self._reports(restaurant_ids).sales_by_day(since=since, until=until)
        by_date: dict[date, list[SalesDay]] = {}
        for row in rows:
            by_date.setdefault(row.business_date, []).append(row)

        spans = _weeks_back(since, until) if bucket is Bucket.WEEK else _days(since, until)
        points = []
        for starts_on, ends_on in spans:
            inside = [
                row
                for day, rows_for_day in by_date.items()
                if starts_on <= day <= ends_on
                for row in rows_for_day
            ]
            traded = len({row.business_date for row in inside})
            points.append(
                SeriesPoint(
                    starts_on=starts_on,
                    ends_on=ends_on,
                    value=_bucket_value(metric, inside),
                    days_traded=traded,
                )
            )
        return Series(
            metric=metric,
            bucket=bucket,
            since=since,
            until=until,
            restaurant_ids=tuple(restaurant_ids),
            points=tuple(points),
        )

    async def compare_branches(self, *, since: date, until: date) -> BranchComparison:
        """Every branch this person holds a role at, beside each other, over one window.

        The owner's decision made this a **comparison first and a sum second**, so the summing
        rules are not the interesting part of this method — they are fixed, and they are:

        - revenue, covers and orders sum, because they are counts of the same thing in the same
          unit;
        - `average_bill` is recomputed from the summed revenue over the summed orders, never
          averaged from the per-branch averages, which would weight a quiet branch equally with a
          busy one;
        - **nothing tax-shaped sums**, which is enforced by `BranchSales` not carrying tax at all.

        What is *not* fixed is the basis the branches are compared on — see `comparison_basis`.
        """
        restaurant_ids = await self.branch_ids()
        rows = await self._reports(restaurant_ids).sales_by_branch(since=since, until=until)

        branches = tuple(
            BranchRow(
                restaurant_id=row.restaurant_id,
                name=row.name,
                revenue=row.revenue.quantize(_MONEY),
                dine_in_revenue=row.dine_in_revenue.quantize(_MONEY),
                covers=row.covers,
                orders=row.orders,
                business_days_traded=row.business_days_traded,
                revenue_per_trading_day=(
                    None
                    if row.business_days_traded == 0
                    else (row.revenue / row.business_days_traded).quantize(_MONEY)
                ),
            )
            for row in rows
        )

        total_revenue = _sum([branch.revenue for branch in branches]).quantize(_MONEY)
        total_orders = sum(branch.orders for branch in branches)
        return BranchComparison(
            since=since,
            until=until,
            branches=branches,
            total_revenue=total_revenue,
            total_covers=sum(branch.covers for branch in branches),
            total_orders=total_orders,
            average_bill=(
                None if total_orders == 0 else (total_revenue / total_orders).quantize(_MONEY)
            ),
        )


def comparison_basis(branch: BranchRow) -> Decimal | None:
    """Average spend per dine-in guest — the figure branches are ranked and compared on.

    **The owner's decision, 2026-09-19.** The spec's rule for M19 is that *every screen either
    shows a shape a table cannot, or produces an action with a rupee figure on it*. Ranking
    branches on raw revenue fails that rule: it reports that the big branch is big, which an owner
    already knows and cannot act on. Spend per guest is **size-neutral** — a 22-seat branch can beat
    a 60-seat one — and it moves when something an owner controls moves: menu mix, upselling,
    pricing, whether starters get offered.

    **Dine-in revenue, not all revenue, and this is not a detail.** `order.covers` is NULL for
    takeaway and delivery (`ck_order_covers` permits NULL, and `SUM` skips NULLs), so dividing
    *total* revenue by covers charges a branch's entire takeaway trade to the guests who sat down.
    A delivery-heavy branch would post an impossible spend per head and be ranked healthiest. The
    repository carries `dine_in_revenue` for exactly this reason.

    **What this basis does not catch, stated rather than discovered later:** a branch whose footfall
    has collapsed while its remaining guests spend well looks fine here. Covers per trading day is
    the figure that would show it, and `BranchRow` carries both `covers` and
    `business_days_traded` so the screen can show it alongside without a second decision. Chunk B
    should put it beside this number rather than behind a toggle.

    `None` when the branch had no dine-in guests in the window — a takeaway-only branch, or one
    that never opened. That is a different statement from zero and the screen renders it
    differently; a zero here would rank a closed branch as the worst performer.
    """
    if branch.covers == 0:
        return None
    return (branch.dine_in_revenue / branch.covers).quantize(_MONEY)
