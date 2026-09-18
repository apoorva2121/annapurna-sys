"""The dashboards and reports. Authorise, call, shape — and, for CSV, serialise differently.

**Two permissions, and the P1 design's split between them is sharper than it looks.**
`report.operational.view` is the owner's, the manager's, the store manager's and the accountant's.
`report.financial.view` is the owner's and the **accountant's** — *not* the manager's. So the money
screens are not manager screens with blanks in them; they are screens a manager does not have, and
the route refuses rather than redacting. A disabled figure invites somebody to find the endpoint.

**CSV is the same query, streamed.** It calls the same service method with the same bounds and
differs only in serialisation, because a CSV that disagrees with the screen is the worst defect a
report can have: both look authoritative and nobody can tell which is lying.

**Nothing here commits**, because nothing here writes. These are the only routes in the staff
surface with no `session.commit()` and that is the point — a report is a read.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.business_day import business_date_of
from app.core.permissions import PermissionCode
from app.repositories.setup import RestaurantRepository
from app.schemas.reporting import (
    ComparisonResponse,
    DishLineResponse,
    DishReportResponse,
    PaymentSplitResponse,
    SalesDayResponse,
    SalesReportResponse,
    TodayResponse,
    VarianceLineResponse,
    VarianceReportResponse,
    WasteLineResponse,
    WasteReportResponse,
)
from app.services.reporting import Compared, ReportingService

router = APIRouter(tags=["reports"])

_OPERATIONAL = Annotated[Actor, Depends(require_permission(PermissionCode.REPORT_OPERATIONAL_VIEW))]
_FINANCIAL = Annotated[Actor, Depends(require_permission(PermissionCode.REPORT_FINANCIAL_VIEW))]

# How far back a report looks when nobody says. A week, because that is the span an owner compares
# against the week before without having to think about which dates to type.
_DEFAULT_DAYS = 7

Format = Literal["json", "csv"]


def _service(session: SessionDep, actor: Actor) -> ReportingService:
    """The scope comes from the *actor*, never from the request (`docs/security.md` A04)."""
    return ReportingService(session, actor.scope)


async def _today(session: SessionDep, actor: Actor) -> date:
    """**The restaurant's** today, not the server's.

    A restaurant's day runs from `business_day_start` (invariant 4), so a report asked for at 2am
    is asking about the day that is still running — and `date.today()` would answer about the one
    that has not started.
    """
    restaurant = await RestaurantRepository(session, actor.scope).get()
    if restaurant is None:  # pragma: no cover - the actor's own restaurant always exists
        raise RuntimeError("the actor's restaurant does not exist")
    from datetime import UTC, datetime

    return business_date_of(datetime.now(UTC), restaurant.timezone, restaurant.business_day_start)


def _bounds(since: date | None, until: date | None, today: date) -> tuple[date, date]:
    finish = until or today
    start = since or finish - timedelta(days=_DEFAULT_DAYS - 1)
    return start, finish


def _money(value: Decimal) -> str:
    """Money crosses the wire as a string and never as a float (invariant 3)."""
    return str(value)


def _compared(compared: Compared) -> ComparisonResponse:
    percent = compared.change_percent
    return ComparisonResponse(
        value=_money(compared.value),
        previous=_money(compared.previous),
        change=_money(compared.change),
        change_percent=None if percent is None else str(percent),
    )


def _csv(rows: Sequence[Sequence[object]], header: Sequence[str], name: str) -> StreamingResponse:
    """Streamed rather than assembled: a year of order lines is not a string in memory.

    `newline=""` on the buffer, because csv writes its own line terminator and a Windows Python
    would otherwise emit `\\r\\r\\n` — which Excel reads as a blank row between every line.
    """

    def lines() -> Iterator[str]:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(header)
        yield _drain(buffer)
        for row in rows:
            writer.writerow(row)
            yield _drain(buffer)

    return StreamingResponse(
        lines(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )


def _drain(buffer: io.StringIO) -> str:
    written = buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    return written


# --------------------------------------------------------------------- the glance


@router.get("/dashboard/today", response_model=TodayResponse)
async def today(session: SessionDep, actor: _OPERATIONAL) -> TodayResponse:
    """What a manager wants in the ten seconds before service.

    Every figure carries yesterday beside it, computed on the server over the same query — a
    browser subtracting two separately-fetched numbers is one rounding rule from disagreeing with
    the figure printed next to it.
    """
    business_date = await _today(session, actor)
    report = await _service(session, actor).today(business_date=business_date)
    return TodayResponse(
        business_date=report.business_date,
        revenue=_compared(report.revenue),
        covers=_compared(report.covers),
        open_orders=report.open_orders,
        average_rating=None if report.average_rating is None else str(report.average_rating),
        ratings_counted=report.ratings_counted,
    )


# ---------------------------------------------------------------------- the money


@router.get("/reports/sales", response_model=SalesReportResponse | None)
async def sales(
    session: SessionDep,
    actor: _FINANCIAL,
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
    format: Annotated[Format, Query()] = "json",
) -> object:
    start, finish = _bounds(since, until, await _today(session, actor))
    report = await _service(session, actor).sales(since=start, until=finish)
    if format == "csv":
        return _csv(
            [
                (
                    day.business_date.isoformat(),
                    day.orders,
                    day.covers,
                    _money(day.revenue),
                    _money(day.tax),
                    _money(day.discounts),
                )
                for day in report.days
            ],
            ("business_date", "orders", "covers", "revenue", "tax", "discounts"),
            "sales",
        )
    return SalesReportResponse(
        since=report.since,
        until=report.until,
        revenue=_compared(report.revenue),
        covers=_compared(report.covers),
        average_bill=_compared(report.average_bill),
        days=[
            SalesDayResponse(
                business_date=day.business_date,
                orders=day.orders,
                covers=day.covers,
                revenue=_money(day.revenue),
                tax=_money(day.tax),
                discounts=_money(day.discounts),
            )
            for day in report.days
        ],
        payments=[
            PaymentSplitResponse(
                method=split.method, amount=_money(split.amount), count=split.count
            )
            for split in report.payments
        ],
    )


@router.get("/reports/food-cost-variance", response_model=VarianceReportResponse | None)
async def food_cost_variance(
    session: SessionDep,
    actor: _FINANCIAL,
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
    format: Annotated[Format, Query()] = "json",
) -> object:
    """**The report this product exists for.**

    Theoretical consumption against actual, with the waste that explains part of the gap — and the
    part nobody explained, which is the only line in the product that says *this much of your food
    went somewhere nobody can account for*.
    """
    start, finish = _bounds(since, until, await _today(session, actor))
    report = await _service(session, actor).food_cost_variance(since=start, until=finish)
    if format == "csv":
        return _csv(
            [
                (
                    line.item_name,
                    line.base_unit,
                    _money(line.theoretical_quantity),
                    _money(line.actual_quantity),
                    _money(line.variance_quantity),
                    _money(line.theoretical_value),
                    _money(line.actual_value),
                    _money(line.variance_value),
                    _money(line.waste_value),
                    _money(line.unexplained_value),
                )
                for line in report.lines
            ],
            (
                "item",
                "unit",
                "theoretical_quantity",
                "actual_quantity",
                "variance_quantity",
                "theoretical_value",
                "actual_value",
                "variance_value",
                "waste_value",
                "unexplained_value",
            ),
            "food-cost-variance",
        )
    return VarianceReportResponse(
        since=report.since,
        until=report.until,
        theoretical_total=_money(report.theoretical_total),
        actual_total=_money(report.actual_total),
        variance_total=_money(report.variance_total),
        waste_total=_money(report.waste_total),
        unexplained_total=_money(report.unexplained_total),
        lines=[
            VarianceLineResponse(
                stock_item_id=line.stock_item_id,
                item_name=line.item_name,
                base_unit=line.base_unit,
                theoretical_quantity=_money(line.theoretical_quantity),
                actual_quantity=_money(line.actual_quantity),
                variance_quantity=_money(line.variance_quantity),
                theoretical_value=_money(line.theoretical_value),
                actual_value=_money(line.actual_value),
                variance_value=_money(line.variance_value),
                waste_value=_money(line.waste_value),
                unexplained_value=_money(line.unexplained_value),
            )
            for line in report.lines
        ],
    )


# ------------------------------------------------------------------ the operations


@router.get("/reports/waste", response_model=WasteReportResponse | None)
async def waste(
    session: SessionDep,
    actor: _OPERATIONAL,
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
    format: Annotated[Format, Query()] = "json",
) -> object:
    """What was thrown away, by stage and then by reason — M09's summary, widened.

    **Two routes over the same rows, and the P1 design is why.** M09's `/wastage/summary` sits
    behind `stock.view`, which a chef and a kitchen hand hold and an accountant does not; this one
    sits behind `report.operational.view`, which an accountant holds and a chef does not. Neither
    role can reach the other's, so collapsing them would take the report away from somebody. What
    this one adds is the period before it, the export, and the demo exclusion every report carries.

    **Never one number.** The total is the heading; the stages are the answer
    (`docs/waste-model.md`).
    """
    start, finish = _bounds(since, until, await _today(session, actor))
    report = await _service(session, actor).waste(since=start, until=finish)
    if format == "csv":
        return _csv(
            [
                (
                    line.stage,
                    line.reason_code,
                    line.reason_name,
                    line.events,
                    _money(line.cost_value),
                    str(line.share_percent),
                )
                for line in report.lines
            ],
            ("stage", "reason_code", "reason", "events", "cost_value", "share_percent"),
            "waste",
        )
    return WasteReportResponse(
        since=report.since,
        until=report.until,
        total=_compared(report.total),
        lines=[
            WasteLineResponse(
                stage=line.stage,
                reason_code=line.reason_code,
                reason_name=line.reason_name,
                events=line.events,
                cost_value=_money(line.cost_value),
                share_percent=str(line.share_percent),
            )
            for line in report.lines
        ],
    )


@router.get("/reports/dish-performance", response_model=DishReportResponse | None)
async def dish_performance(
    session: SessionDep,
    actor: _OPERATIONAL,
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
    format: Annotated[Format, Query()] = "json",
) -> object:
    """Vision doc §12's quadrant, per dish, with the rating and the prep time beside it.

    Every `advice` string is advice with the numbers next to it. The screen recommends; it never
    acts — a product that removed a dish because a quadrant said so would be wrong about one
    restaurant in five, and the one it was wrong about would be somebody's signature dish.
    """
    start, finish = _bounds(since, until, await _today(session, actor))
    report = await _service(session, actor).dish_performance(since=start, until=finish)
    if format == "csv":
        return _csv(
            [
                (
                    line.item_name,
                    line.variant_name,
                    line.units,
                    _money(line.revenue),
                    _money(line.theoretical_cost),
                    _money(line.margin),
                    "" if line.food_cost_percent is None else str(line.food_cost_percent),
                    "" if line.average_rating is None else str(line.average_rating),
                    "" if line.average_prep_seconds is None else line.average_prep_seconds,
                    line.quadrant,
                )
                for line in report.lines
            ],
            (
                "dish",
                "variant",
                "units",
                "revenue",
                "theoretical_cost",
                "margin",
                "food_cost_percent",
                "average_rating",
                "average_prep_seconds",
                "quadrant",
            ),
            "dish-performance",
        )
    return DishReportResponse(
        since=report.since,
        until=report.until,
        lines=[
            DishLineResponse(
                variant_id=line.variant_id,
                item_name=line.item_name,
                variant_name=line.variant_name,
                units=line.units,
                revenue=_money(line.revenue),
                theoretical_cost=_money(line.theoretical_cost),
                margin=_money(line.margin),
                food_cost_percent=(
                    None if line.food_cost_percent is None else str(line.food_cost_percent)
                ),
                average_rating=(None if line.average_rating is None else str(line.average_rating)),
                average_prep_seconds=line.average_prep_seconds,
                quadrant=line.quadrant,
                advice=line.advice,
            )
            for line in report.lines
        ],
    )
