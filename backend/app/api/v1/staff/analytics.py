"""M19 · Owner Analytics. Trends over time, and branches beside each other.

**Behind `report.financial.view`, the same permission M13's money screens use.** Every figure here
is revenue, covers or a spend per guest, and the P1 design gives that permission to the owner and
the accountant and **not** to the manager — so these are screens a manager does not have, rather
than screens with blanks in them. `reports.py` makes the same call for the same reason: *"a
disabled figure invites somebody to find the endpoint."*

**Nothing here commits, because nothing here writes.** Like M13's reports, these are reads.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.schemas.analytics import (
    BranchComparisonResponse,
    BranchRowResponse,
    SeriesPointResponse,
    SeriesResponse,
)
from app.services.analytics import AnalyticsService, Bucket, Metric, comparison_basis
from app.services.reporting import ReportingService

router = APIRouter(tags=["analytics"])

_FINANCIAL = Annotated[Actor, Depends(require_permission(PermissionCode.REPORT_FINANCIAL_VIEW))]

# Eight weeks. Long enough that a weekly trend has a shape, short enough that the first load of the
# screen is not four months of arithmetic nobody asked for.
_DEFAULT_DAYS = 56


def _money(value: Decimal | None) -> str | None:
    """Money crosses the wire as a string and never as a float (invariant 3)."""
    return None if value is None else str(value)


async def _bounds(
    session: SessionDep, actor: Actor, since: date | None, until: date | None
) -> tuple[date, date]:
    """The window, defaulting to the last eight weeks of the **restaurant's** days.

    `business_date_now` and not `date.today()`: a restaurant's day starts at `business_day_start`
    (invariant 4), so a screen opened at 2am is asking about the day that is still running.
    """
    finish = until or await ReportingService(session, actor.scope).business_date_now()
    start = since or finish - timedelta(days=_DEFAULT_DAYS - 1)
    return start, finish


@router.get("/analytics/trend", response_model=SeriesResponse)
async def trend(
    session: SessionDep,
    actor: _FINANCIAL,
    metric: Annotated[Metric, Query()] = Metric.REVENUE,
    bucket: Annotated[Bucket, Query()] = Bucket.DAY,
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
    across_branches: Annotated[bool, Query()] = False,
) -> SeriesResponse:
    """One metric over time.

    `across_branches` widens it to every branch this person holds a role at — not a fixed list and
    not a role check: `AnalyticsService.branch_ids` reuses the set `POST /auth/switch` already
    admits, and the organization boundary is enforced inside the query rather than here.

    **`tax` is not a choice**, deliberately. It is absent from `Metric` because it does not sum.
    """
    start, finish = await _bounds(session, actor, since, until)
    series = await AnalyticsService(session, actor).series(
        metric=metric, since=start, until=finish, bucket=bucket, across_branches=across_branches
    )
    return SeriesResponse(
        metric=series.metric,
        bucket=series.bucket,
        since=series.since,
        until=series.until,
        restaurant_ids=list(series.restaurant_ids),
        points=[
            SeriesPointResponse(
                starts_on=point.starts_on,
                ends_on=point.ends_on,
                value=_money(point.value),
                days_traded=point.days_traded,
            )
            for point in series.points
        ],
    )


@router.get("/analytics/branches", response_model=BranchComparisonResponse)
async def branches(
    session: SessionDep,
    actor: _FINANCIAL,
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
) -> BranchComparisonResponse:
    """Every branch this person holds a role at, beside each other.

    **A comparison first and a sum second** — the owner's decision of 2026-09-19. A sum answers
    *"how are we doing"*; a comparison answers *"which branch has the problem"*, and only the
    second leads to an action. Revenue, covers and orders sum; nothing tax-shaped is here to sum.

    Ordered by spend per dine-in guest, the basis the owner chose: size-neutral, so a 22-seat branch
    can beat a 60-seat one. A branch with no dine-in guests sorts last rather than first — `None` is
    "no answer", and ranking it top would put an empty restaurant at the head of the table.
    """
    start, finish = await _bounds(session, actor, since, until)
    comparison = await AnalyticsService(session, actor).compare_branches(since=start, until=finish)
    rows = sorted(
        comparison.branches,
        key=lambda branch: (comparison_basis(branch) is not None, comparison_basis(branch) or 0),
        reverse=True,
    )
    return BranchComparisonResponse(
        since=comparison.since,
        until=comparison.until,
        branches=[
            BranchRowResponse(
                restaurant_id=row.restaurant_id,
                name=row.name,
                revenue=str(row.revenue),
                dine_in_revenue=str(row.dine_in_revenue),
                covers=row.covers,
                orders=row.orders,
                business_days_traded=row.business_days_traded,
                revenue_per_trading_day=_money(row.revenue_per_trading_day),
                spend_per_cover=_money(comparison_basis(row)),
            )
            for row in rows
        ],
        total_revenue=str(comparison.total_revenue),
        total_covers=comparison.total_covers,
        total_orders=comparison.total_orders,
        average_bill=_money(comparison.average_bill),
    )
