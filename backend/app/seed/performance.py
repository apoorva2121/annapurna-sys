"""M17's incentive scheme and the periods that make the workload screens show anything.

**The scheme was fully designed in `seed/operations.yaml` and nothing ever loaded it.** The weights,
the `context_only` metrics carried beside a score at weight zero, the award types — all written
down, and no `seed/performance.py` existed to read them. The chain broke at the first link: no
scheme means no period, no period means no score, and every user opening My performance saw
*"No periods have been set up yet. Ask your manager."* Including the owner, who has no manager.

So M17 shipped complete, tested, and unreachable for a person. The owner found it on 2026-09-19 by
opening the screen. Three of their findings that week were the same gap wearing different clothes —
a module is not finished when its tests pass, it is finished when somebody can look at it.

**Periods are seeded as drafts, deliberately, and none is published.** Publishing is the freeze
(ADR 0011): it writes every figure into `performance_score` and they are never recomputed, which is
what makes a score something a bonus can be paid against. A seeder that published would have to
invent who published it and freeze figures nobody reviewed — and it would rob the owner of the one
action on that screen worth experiencing. A draft period computes live from the generated trading
and the seeded roster, so the numbers on screen are real rather than fabricated.

**It calls the service rather than building rows.** `create_scheme` runs `validate_weights`, which
is where *"volume never stands alone"* stops being a principle in a document and becomes something
the product refuses to do; `open_period` owns the backwards-period refusal. A seeder that inserted
its own rows would be a second implementation of both, and would happily seed a scheme the
application would reject.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import shift_window
from app.core.actor import Actor
from app.core.tenancy import TenantScope
from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee
from app.models.performance import IncentiveScheme, PerformancePeriod
from app.models.tenancy import Restaurant
from app.seed.generate import DEFAULT_DAYS
from app.seed.loader import find_seed_directory
from app.services.performance import PerformanceService

logger = logging.getLogger(__name__)

_OPERATIONS_FILE = "operations.yaml"
_FOR_RESTAURANT = "SG_KOREGAON"


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    schemes_created: int = 0
    periods_created: int = 0

    @property
    def created_nothing(self) -> bool:
        return not (self.schemes_created or self.periods_created)


def _load_operations() -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load(
        (find_seed_directory() / _OPERATIONS_FILE).read_text(encoding="utf-8")
    )
    return parsed


def _months_back(today: date, days: int) -> list[tuple[date, date]]:
    """Calendar months covering the generated window, oldest first, ending with the month in
    progress.

    Monthly because `incentive_scheme.period_type` says so, and because a restaurant thinks in
    months — a weekly bonus is a different product. The last one runs to `today` rather than to the
    month's end: a period that claims to cover days that have not happened would show every person
    short on hours through no fault of theirs.
    """
    start = today - timedelta(days=days)
    periods: list[tuple[date, date]] = []
    cursor = start.replace(day=1)
    while cursor <= today:
        if cursor.month == 12:
            next_month = cursor.replace(year=cursor.year + 1, month=1)
        else:
            next_month = cursor.replace(month=cursor.month + 1)
        end = min(next_month - timedelta(days=1), today)
        periods.append((max(cursor, start), end))
        cursor = next_month
    return periods


async def _most_senior(session: AsyncSession, restaurant: Restaurant) -> Employee | None:
    """Whoever holds the most senior role here — rank 0 is the top of the ladder.

    Used only to attribute the seeded scheme. `min(Role.rank)` rather than a role *name*: ADR 0007
    forbids reading behaviour off a role's code, and the rule holds in a seeder too.
    """
    found: Employee | None = await session.scalar(
        select(Employee)
        .join(EmployeeRoleAssignment, EmployeeRoleAssignment.employee_id == Employee.id)
        .join(Role, Role.id == EmployeeRoleAssignment.role_id)
        .where(EmployeeRoleAssignment.restaurant_id == restaurant.id)
        .order_by(Role.rank, Employee.employee_code)
        .limit(1)
    )
    return found


async def seed_performance(session: AsyncSession) -> PerformanceSummary:
    """Create the scheme and its periods. Safe to run repeatedly."""
    operations = _load_operations()
    record = operations.get("incentive_scheme")
    if record is None:
        return PerformanceSummary()

    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == _FOR_RESTAURANT))
    if restaurant is None:
        return PerformanceSummary()

    scope = TenantScope(organization_id=restaurant.organization_id, restaurant_id=restaurant.id)

    # **The actor has to be a real employee.** `create_scheme` is `@audited`, and `audit_log`
    # carries a foreign key to `employee` — a scope-shaped actor with the restaurant's own id got
    # as far as a ForeignKeyViolationError, which is the audit trail refusing to name somebody who
    # does not exist. Correct of it.
    #
    # So the scheme is attributed to the restaurant's most senior employee. That is a small
    # fiction, and the honest one: setting the weights that decide a bonus is an owner's act, and
    # the seeded world is a fiction throughout. A seed that wrote an unattributable audit row would
    # be worse — the trail's whole value is that every row names somebody.
    owner = await _most_senior(session, restaurant)
    if owner is None:
        return PerformanceSummary()

    actor = Actor(
        employee_id=owner.id,
        organization_id=restaurant.organization_id,
        restaurant_id=restaurant.id,
        full_name=owner.full_name,
        permissions=frozenset(),
        rank=0,
    )
    service = PerformanceService(session, scope)

    existing = await session.scalar(
        select(IncentiveScheme).where(IncentiveScheme.restaurant_id == restaurant.id)
    )
    schemes_created = 0
    if existing is None:
        # Get-or-create by restaurant, like every other seeder here: `make seed` is run casually
        # and repeatedly, and the failure to design against is a second scheme, not a crash.
        existing = await service.create_scheme(
            actor,
            name=str(record["name"]),
            period_type=str(record["period_type"]),
            weights=dict(record["weights"]),
            effective_from=record["effective_from"],
        )
        schemes_created = 1

    today = shift_window.business_day_for(
        datetime.now(UTC), restaurant.timezone, restaurant.business_day_start
    )
    days = int(os.environ.get("SEED_DAYS", DEFAULT_DAYS))

    already = {
        (period.period_start, period.period_end)
        for period in (
            await session.scalars(
                select(PerformancePeriod).where(PerformancePeriod.restaurant_id == restaurant.id)
            )
        ).all()
    }
    periods_created = 0
    for period_start, period_end in _months_back(today, days):
        if (period_start, period_end) in already:
            continue
        await service.open_period(
            actor,
            scheme_id=existing.id,
            period_start=period_start,
            period_end=period_end,
        )
        periods_created += 1

    await session.flush()
    summary = PerformanceSummary(schemes_created=schemes_created, periods_created=periods_created)
    logger.info("seed.performance.complete", extra={"summary": summary})
    return summary
