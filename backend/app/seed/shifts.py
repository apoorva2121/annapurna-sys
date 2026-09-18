"""The demo restaurant's roster: two shifts, a fortnight of people, and sections that mean
something.

**A roster is what makes three other things visible without anybody configuring anything.** A
demonstration of auto-assignment needs a section with exactly one waiter on it; a demonstration of
`on-now` needs somebody actually covering the moment the screen is opened; and M17's normalisation
needs hours that differ between people. All three come free from a seeded fortnight and none of
them can be shown without one.

**Two shifts, and the evening one crosses midnight.** `docs/seed-data.md`'s rule that seeded data
is plausible rather than perfect applies to time as much as to money: a Pune restaurant closing at
half past midnight is the ordinary case, and a seed with two tidy daytime shifts would never
exercise the arithmetic that is most likely to be wrong.

**Only yesterday and today are clocked in.** Future days are `scheduled`, which is what a roster
looks like — and one person yesterday is deliberately left `scheduled` with no clock-in, so the
"did not clock in" state exists on screen without a demonstrator having to construct it. That is
M05's negative stock and M07's fifty-rupee-short till, applied here.

**Nobody is marked absent.** `absent` is a disciplinary fact with an author, and the seeder is not
an author. Leaving it out is the same decision the service makes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import shift_window
from app.core.enums import ShiftAssignmentStatus
from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee
from app.models.setup import DiningArea
from app.models.shifts import Shift, ShiftAssignment
from app.models.tenancy import Restaurant

logger = logging.getLogger(__name__)

_FOR_RESTAURANT = "SG_KOREGAON"

# Name, start, end. The evening one crosses midnight on purpose — see the module docstring.
_SHIFTS: tuple[tuple[str, time, time], ...] = (
    ("Morning", time(8, 0), time(16, 0)),
    ("Evening", time(16, 0), time(0, 30)),
)

# How many days either side of today the roster covers: three back and a week forward. Enough that
# the week grid has something in it in both directions and that yesterday's clocked-in shifts
# exist, small enough that `make seed` stays fast.
_DAYS_BACK = 3
_DAYS_FORWARD = 7


@dataclass(frozen=True, slots=True)
class ShiftSeed:
    shifts_created: int = 0
    assignments_created: int = 0

    @property
    def created_nothing(self) -> bool:
        return self.shifts_created == 0 and self.assignments_created == 0


async def seed_shifts(session: AsyncSession) -> ShiftSeed:
    """Two shifts and a fortnight of assignments. Safe to run repeatedly.

    Does not commit — the caller owns the transaction, which is what lets the suite seed inside one
    it rolls back. Idempotent: a restaurant that already has assignments is left alone, because a
    roster in it is a roster somebody made.
    """
    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == _FOR_RESTAURANT))
    if restaurant is None:
        return ShiftSeed()

    created = await _shifts(session, restaurant)

    existing = await session.scalar(
        select(func.count(ShiftAssignment.id)).where(ShiftAssignment.restaurant_id == restaurant.id)
    )
    if existing:
        return ShiftSeed(shifts_created=created)

    assignments = await _assignments(session, restaurant)
    summary = ShiftSeed(shifts_created=created, assignments_created=assignments)
    logger.info("seed.shifts.complete", extra={"summary": summary})
    return summary


async def _shifts(session: AsyncSession, restaurant: Restaurant) -> int:
    present = set(
        (
            await session.scalars(select(Shift.name).where(Shift.restaurant_id == restaurant.id))
        ).all()
    )
    created = 0
    for name, start, end in _SHIFTS:
        if name in present:
            continue
        session.add(
            Shift(
                restaurant_id=restaurant.id,
                name=name,
                start_time=start,
                end_time=end,
                is_active=True,
            )
        )
        created += 1
    await session.flush()
    return created


async def _assignments(session: AsyncSession, restaurant: Restaurant) -> int:
    shifts = {
        shift.name: shift
        for shift in (
            await session.scalars(select(Shift).where(Shift.restaurant_id == restaurant.id))
        ).all()
    }
    areas = (
        await session.scalars(
            select(DiningArea)
            .where(DiningArea.restaurant_id == restaurant.id)
            .order_by(DiningArea.seq)
        )
    ).all()
    if not areas or not shifts:
        return 0

    waiters = await _by_role(session, restaurant, "waiter")
    kitchen = await _by_role(session, restaurant, "chef") + await _by_role(
        session, restaurant, "kitchen_staff"
    )
    if not waiters:
        return 0

    today = shift_window.business_day_for(
        datetime.now(UTC), restaurant.timezone, restaurant.business_day_start
    )
    created = 0
    for offset in range(-_DAYS_BACK, _DAYS_FORWARD + 1):
        business_date = today + timedelta(days=offset)
        for index, (name, _start, _end) in enumerate(_SHIFTS):
            shift = shifts.get(name)
            if shift is None:  # pragma: no cover - both names were just created
                continue
            # **Exactly one waiter per section.** Auto-assignment answers nobody when two people
            # cover one section, so a demonstration of it needs the unambiguous case to exist.
            for position, waiter in enumerate(waiters):
                area = areas[(position + index) % len(areas)]
                created += _assign(
                    session,
                    restaurant,
                    shift,
                    waiter,
                    business_date,
                    area.id,
                    offset=offset,
                    skip_clock_in=offset == -1 and position == 0,
                )
            # The kitchen has no section: a chef covers a stove, not a room.
            for cook in kitchen[:1]:
                created += _assign(
                    session,
                    restaurant,
                    shift,
                    cook,
                    business_date,
                    None,
                    offset=offset,
                    skip_clock_in=False,
                )
    await session.flush()
    return created


def _assign(
    session: AsyncSession,
    restaurant: Restaurant,
    shift: Shift,
    employee: Employee,
    business_date: date,
    dining_area_id: Any,
    *,
    offset: int,
    skip_clock_in: bool,
) -> int:
    """One row, clocked in only if the day has happened.

    `skip_clock_in` is the planted state: one person yesterday who was rostered and never clocked
    in, so "did not clock in" is on the screen without a demonstrator constructing it.
    """
    status = ShiftAssignmentStatus.SCHEDULED
    clock_in: datetime | None = None
    clock_out: datetime | None = None

    if offset < 0 and not skip_clock_in:
        span = shift_window.span_of(
            business_day=business_date,
            start=shift.start_time,
            end=shift.end_time,
            timezone=restaurant.timezone,
            business_day_start=restaurant.business_day_start,
        )
        # Four minutes late: inside the ten-minute grace, so `present` rather than `late`. A seed
        # that made everybody exactly punctual would be the perfectly clean data rule 3 warns about.
        clock_in = span.starts_at + timedelta(minutes=4)
        clock_out = span.ends_at
        status = ShiftAssignmentStatus.PRESENT

    session.add(
        ShiftAssignment(
            restaurant_id=restaurant.id,
            shift_id=shift.id,
            employee_id=employee.id,
            dining_area_id=dining_area_id,
            business_date=business_date,
            status=status.value,
            clock_in_at=clock_in,
            clock_out_at=clock_out,
        )
    )
    return 1


async def _by_role(session: AsyncSession, restaurant: Restaurant, role_code: str) -> list[Employee]:
    statement = (
        select(Employee)
        .join(EmployeeRoleAssignment, EmployeeRoleAssignment.employee_id == Employee.id)
        .join(Role, Role.id == EmployeeRoleAssignment.role_id)
        .where(
            EmployeeRoleAssignment.restaurant_id == restaurant.id,
            Role.code == role_code,
            Employee.is_active.is_(True),
        )
        .order_by(Employee.employee_code)
    )
    return list((await session.scalars(statement)).all())
