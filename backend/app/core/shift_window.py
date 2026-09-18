"""What a shift's times mean on a given business date.

Pure functions over a shift's `start_time` and `end_time`, a restaurant's timezone and its
`business_day_start` — no database, no I/O — so the crossing-midnight arithmetic can be tested
exhaustively without a fixture, and so the roster, the clock and the order screen all read it the
same way.

**A shift may cross midnight; a business date may not.** An Evening shift of 18:00-00:30 on
business date 2026-09-18 runs from 18:00 on the 18th to 00:30 on the 19th, in the restaurant's
local time. Nothing stores those two instants: `business_day.py` plus the shift's times produce
them, which is the only arrangement in which a roster edited next week still describes last week
correctly.

**The end is exclusive.** A shift 08:00-16:00 does not cover 16:00, so a Morning and an Evening
that meet at 16:00 do not both claim it — otherwise "which shift covers this moment" would have
two answers exactly when a handover makes the question worth asking.

This is `floor_rules.BusyWindow.covers`'s shape, deliberately: that module already solved the
crossing-midnight comparison on 2026-09-13, and a second solution to a solved problem is a second
place for it to be wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.business_day import business_date_of

# The only limit a check constraint can usefully assert on a shift's length. It exists to catch a
# typo, not to regulate anything — see the M12 spec's research note: this module makes no statutory
# claim of any kind.
MAX_SHIFT_HOURS = 24

# How late is late, when a restaurant has not said. Ten minutes: long enough to absorb a bus, short
# enough that habitual lateness still shows up as lateness.
DEFAULT_LATE_AFTER_MINUTES = 10


@dataclass(frozen=True, slots=True)
class ShiftSpan:
    """The two instants a shift occupies on one business date, in UTC."""

    starts_at: datetime
    ends_at: datetime

    def covers(self, moment: datetime) -> bool:
        """End exclusive — see the module docstring."""
        return self.starts_at <= moment < self.ends_at


def crosses_midnight(start: time, end: time) -> bool:
    """`18:00-00:30` does; `08:00-16:00` does not. Equal times are a zero-length shift, not a
    twenty-four-hour one: somebody typing the same value twice meant nothing by it."""
    return start > end


def span_of(
    *,
    business_day: date,
    start: time,
    end: time,
    timezone: str,
    business_day_start: time,
) -> ShiftSpan:
    """Where a shift sits in real time, for one business date.

    The *business* date is the anchor, not the calendar date, which is the whole point: a shift
    beginning at 01:00 belongs to the previous calendar day's business date when the restaurant's
    day starts at 05:00, so its span has to be placed relative to that day rather than to midnight.
    """
    zone = ZoneInfo(timezone)
    # The calendar day the business date's own clock-start falls on. For a 05:00 start they are the
    # same day; the arithmetic below is what makes an 01:00 shift land on the day after.
    opening = datetime.combine(business_day, business_day_start, tzinfo=zone)

    starts_local = datetime.combine(business_day, start, tzinfo=zone)
    if starts_local < opening:
        # Before the day opened, so it belongs to the small hours at the *end* of this business day.
        starts_local += timedelta(days=1)

    ends_local = datetime.combine(starts_local.date(), end, tzinfo=zone)
    if crosses_midnight(start, end) or ends_local <= starts_local:
        ends_local += timedelta(days=1)

    return ShiftSpan(starts_at=starts_local.astimezone(UTC), ends_at=ends_local.astimezone(UTC))


def covers(
    moment: datetime,
    *,
    business_day: date,
    start: time,
    end: time,
    timezone: str,
    business_day_start: time,
) -> bool:
    """Does this shift, on this business date, contain this instant?"""
    return span_of(
        business_day=business_day,
        start=start,
        end=end,
        timezone=timezone,
        business_day_start=business_day_start,
    ).covers(moment)


def business_day_for(moment: datetime, timezone: str, business_day_start: time) -> date:
    """A thin name over `business_day.business_date_of`, so this module is the one import a
    roster needs and nobody reaches past it for the raw function."""
    return business_date_of(moment, timezone, business_day_start)


def is_late(
    clock_in_at: datetime,
    span: ShiftSpan,
    *,
    grace_minutes: int = DEFAULT_LATE_AFTER_MINUTES,
) -> bool:
    """Later than the shift's start plus the restaurant's grace.

    Derived at clock-in and stored as a status, rather than computed on every read: `late` is a
    fact about what happened that morning, and a grace period changed in settings next month must
    not silently rewrite who was late last month.
    """
    return clock_in_at > span.starts_at + timedelta(minutes=grace_minutes)


def grace_minutes_from(settings: object) -> int:
    """Read `settings["shifts"]["late_after_minutes"]` tolerantly.

    The pattern `floor_rules.py` established on 2026-09-13: a restaurant seeded before this existed
    has no `shifts` key, and a malformed value written by hand must not take the roster down at the
    start of a service. Anything unreadable falls back to the default; the API validates strictly
    on the way in.
    """
    if not isinstance(settings, dict):
        return DEFAULT_LATE_AFTER_MINUTES
    block = settings.get("shifts")
    if not isinstance(block, dict):
        return DEFAULT_LATE_AFTER_MINUTES
    value = block.get("late_after_minutes")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 240:
        return DEFAULT_LATE_AFTER_MINUTES
    return value
