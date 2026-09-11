"""What a *day* means for a restaurant.

A restaurant that closes at 2am is still serving Monday at 1:30am on Tuesday, and every figure it
reads must agree. `docs/decisions/0004-money-time-units.md` fixes the rule: every restaurant has an
IANA timezone and a `business_day_start` (05:00 by default), orders carry a denormalised
`business_date` computed at insert, and reporting groups on that column — **never** on
`date_trunc('day', created_at)`.

This module is the one implementation of that rule. M13's dashboards, M17's shift figures and M15's
120-day generator all inherit whatever it decides, and none of them can detect it being wrong: a
01:30 order booked to the wrong day looks entirely normal, and surfaces months later as a month-end
total that is out by one night's takings.

Two functions, deliberately paired:

- `business_date_of` — which day does this instant belong to? Used at insert.
- `day_bounds_utc` — which instants belong to this day? Used by every report.

They are inverses and are tested as inverses. If they ever disagreed, a report would count an order
that the order itself does not believe belongs to that day, and the discrepancy would be invisible
from either side alone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _zone(timezone: str) -> ZoneInfo:
    """Refuse an unknown zone rather than falling back to UTC.

    A fallback would silently shift every date for that restaurant by its offset — five and a half
    hours in India — and nobody would look, because the numbers would still be numbers.
    """
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(f"Unknown timezone {timezone!r}.") from error


def _require_aware(moment: datetime) -> datetime:
    """A datetime without a timezone is not an instant.

    Assuming UTC here is exactly how a `datetime.now()` written in a hurry becomes a five-and-a-half
    hour error that only shows up either side of midnight.
    """
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError("business_date_of needs a timezone-aware datetime.")
    return moment


def business_date_of(moment: datetime, timezone: str, day_starts_at: time) -> date:
    """The business date an instant belongs to.

    Convert to the restaurant's local time, then take the previous calendar day when the local
    clock has not yet reached `day_starts_at`. The boundary is **inclusive**: an order at exactly
    05:00 belongs to the new day, because a day has to begin somewhere and "your 05:00 order counted
    towards yesterday" is indefensible to explain to an owner.

    Conversion goes through `zoneinfo` rather than a stored offset, which is what makes this correct
    across a daylight-saving change. India has none — and `restaurant.timezone` is an IANA zone
    precisely because the column outlives that assumption.
    """
    local = _require_aware(moment).astimezone(_zone(timezone))
    if local.time() >= day_starts_at:
        return local.date()
    return local.date() - timedelta(days=1)


def day_bounds_utc(
    business_date: date, timezone: str, day_starts_at: time
) -> tuple[datetime, datetime]:
    """The half-open UTC range `[start, end)` covering one business date.

    Half-open, not inclusive, so consecutive days share a boundary without either counting an order
    twice or dropping one: the end of the 10th *is* the start of the 11th.

    `fold=0` on the local start resolves the ambiguous hour that occurs when clocks go back — the
    earlier of the two possible instants. The choice matters only for a start time inside that
    repeated hour, and being deterministic matters more than which one is picked: a report whose
    boundary moves between runs is worse than one whose boundary is arguable.
    """
    zone = _zone(timezone)
    start_local = datetime.combine(business_date, day_starts_at, tzinfo=zone).replace(fold=0)
    end_local = datetime.combine(business_date + timedelta(days=1), day_starts_at, tzinfo=zone)
    return start_local.astimezone(UTC), end_local.replace(fold=0).astimezone(UTC)
