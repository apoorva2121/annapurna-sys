"""When a table being cleared is ready, and when the floor is too busy to clear tables at all.

Pure functions over the restaurant's `settings["tables"]` block and a moment in time, so the rules
the owner decided on 2026-09-13 can be tested without a database, and so settlement and the floor
read them the same way:

1. **A cleaning time**, five minutes unless the restaurant says otherwise. `None` means only a
   person clears a table. It is derived when the floor is read; nothing runs in the background.
2. **Busy windows** in restaurant local time. A window may cross midnight — `22:00` to `01:00` is
   the late rush of a place that closes at two — and the end is exclusive.
3. **Busy mode from the floor** counts only on the business day it was switched on (ADR 0004's
   business day, not midnight), so a switch left on turns itself off rather than skipping cleaning
   for ever.

**Tolerant on the way out.** A restaurant seeded before this existed has no `tables` key, and a
malformed value written by hand must not take the floor down mid-service: anything unreadable falls
back to the default rather than raising. The API validates strictly on the way in.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.business_day import business_date_of
from app.core.enums import TableStatus

DEFAULT_CLEANING_MINUTES = 5


@dataclass(frozen=True, slots=True)
class BusyWindow:
    starts: time
    ends: time

    def covers(self, moment: time) -> bool:
        if self.starts <= self.ends:
            return self.starts <= moment < self.ends
        # Across midnight: from `starts` to the end of the day, and from midnight to `ends`.
        return moment >= self.starts or moment < self.ends


@dataclass(frozen=True, slots=True)
class TableSettings:
    cleaning_minutes: int | None = DEFAULT_CLEANING_MINUTES
    busy_windows: tuple[BusyWindow, ...] = ()
    busy_mode_on: date | None = None


def _minutes(stored: Mapping[str, Any]) -> int | None:
    if "cleaning_minutes" not in stored:
        return DEFAULT_CLEANING_MINUTES
    value = stored["cleaning_minutes"]
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return DEFAULT_CLEANING_MINUTES


def _window(entry: object) -> BusyWindow | None:
    if not isinstance(entry, Mapping):
        return None
    try:
        return BusyWindow(
            starts=time.fromisoformat(str(entry["starts"])),
            ends=time.fromisoformat(str(entry["ends"])),
        )
    except (KeyError, ValueError):
        return None


def _day(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value is not None else None
    except ValueError:
        return None


def read_table_settings(settings: Mapping[str, Any]) -> TableSettings:
    stored = settings.get("tables")
    if not isinstance(stored, Mapping):
        return TableSettings()
    windows = stored.get("busy_windows")
    parsed = [_window(entry) for entry in windows] if isinstance(windows, list) else []
    return TableSettings(
        cleaning_minutes=_minutes(stored),
        busy_windows=tuple(window for window in parsed if window is not None),
        busy_mode_on=_day(stored.get("busy_mode_on")),
    )


def is_busy(
    settings: TableSettings, *, now: datetime, timezone: str, business_day_start: time
) -> bool:
    """Whether a table settled at `now` skips cleaning."""
    if settings.busy_mode_on == business_date_of(now, timezone, business_day_start):
        return True
    local = now.astimezone(ZoneInfo(timezone)).time()
    return any(window.covers(local) for window in settings.busy_windows)


def ready_at(settings: TableSettings, cleaning_since: datetime | None) -> datetime | None:
    """When a table being cleared counts as free, or `None` if only a person can say so."""
    if cleaning_since is None or settings.cleaning_minutes is None:
        return None
    return cleaning_since + timedelta(minutes=settings.cleaning_minutes)


def floor_status(status: str, ready: datetime | None, now: datetime) -> str:
    """What the floor shows: a table whose cleaning time has passed is free."""
    if status == TableStatus.CLEANING and ready is not None and ready <= now:
        return TableStatus.FREE
    return status
