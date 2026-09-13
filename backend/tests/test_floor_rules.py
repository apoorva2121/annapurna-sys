"""The table rules on their own, without a database.

The HTTP tests in `test_table_after_the_bill.py` prove the floor and settlement use these rules. The
edges live here, where they are cheap to state: a busy window across midnight, the end of a window,
a busy-mode switch from yesterday, and settings nobody ever saved.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.core.enums import TableStatus
from app.services.floor_rules import (
    DEFAULT_CLEANING_MINUTES,
    BusyWindow,
    TableSettings,
    floor_status,
    is_busy,
    read_table_settings,
    ready_at,
)

KOLKATA = "Asia/Kolkata"
FIVE_AM = time(5, 0)


def _ist(hour: int, minute: int = 0, day: int = 13) -> datetime:
    """A moment given in Kolkata time, expressed in UTC as the database stores it."""
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC) - timedelta(hours=5, minutes=30)


class TestReadingTheSettings:
    def test_a_restaurant_that_never_saved_them_cleans_for_five_minutes(self) -> None:
        assert read_table_settings({}) == TableSettings(DEFAULT_CLEANING_MINUTES, (), None)
        assert DEFAULT_CLEANING_MINUTES == 5

    def test_an_explicit_none_means_only_a_person_clears_a_table(self) -> None:
        assert read_table_settings({"tables": {"cleaning_minutes": None}}).cleaning_minutes is None

    @pytest.mark.parametrize("bad", [0, -3, "five", True, 2.5])
    def test_a_value_written_by_hand_that_makes_no_sense_falls_back(self, bad: object) -> None:
        settings = read_table_settings({"tables": {"cleaning_minutes": bad}})
        assert settings.cleaning_minutes == DEFAULT_CLEANING_MINUTES

    def test_windows_are_read_and_a_malformed_one_is_skipped_not_fatal(self) -> None:
        settings = read_table_settings(
            {
                "tables": {
                    "busy_windows": [
                        {"starts": "12:30", "ends": "15:00"},
                        {"starts": "noon"},
                        "22:00-01:00",
                    ]
                }
            }
        )
        assert settings.busy_windows == (BusyWindow(time(12, 30), time(15, 0)),)


class TestBusyWindows:
    @pytest.mark.parametrize(
        ("moment", "covered"),
        [(time(12, 29), False), (time(12, 30), True), (time(14, 59), True), (time(15, 0), False)],
    )
    def test_a_daytime_window_includes_its_start_and_excludes_its_end(
        self, moment: time, covered: bool
    ) -> None:
        assert BusyWindow(time(12, 30), time(15, 0)).covers(moment) is covered

    @pytest.mark.parametrize(
        ("moment", "covered"),
        [
            (time(21, 59), False),
            (time(22, 0), True),
            (time(23, 45), True),
            (time(0, 30), True),
            (time(1, 0), False),
            (time(12, 0), False),
        ],
    )
    def test_a_window_across_midnight_covers_both_sides_of_it(
        self, moment: time, covered: bool
    ) -> None:
        assert BusyWindow(time(22, 0), time(1, 0)).covers(moment) is covered

    def test_busy_is_judged_in_the_restaurants_own_time(self) -> None:
        late_rush = TableSettings(busy_windows=(BusyWindow(time(22, 0), time(1, 0)),))
        # 23:30 in Kolkata is 18:00 UTC — busy there, whatever the server's clock says.
        assert is_busy(late_rush, now=_ist(23, 30), timezone=KOLKATA, business_day_start=FIVE_AM)
        assert not is_busy(late_rush, now=_ist(19, 0), timezone=KOLKATA, business_day_start=FIVE_AM)


class TestBusyModeFromTheFloor:
    def test_it_counts_on_the_business_day_it_was_switched_on(self) -> None:
        settings = TableSettings(busy_mode_on=date(2026, 9, 13))
        assert is_busy(settings, now=_ist(20, 0), timezone=KOLKATA, business_day_start=FIVE_AM)

    def test_it_still_counts_at_1am_which_belongs_to_the_same_business_day(self) -> None:
        settings = TableSettings(busy_mode_on=date(2026, 9, 13))
        one_am_next_calendar_day = _ist(1, 0, day=14)
        assert is_busy(
            settings, now=one_am_next_calendar_day, timezone=KOLKATA, business_day_start=FIVE_AM
        )

    def test_left_on_it_switches_itself_off_the_next_business_day(self) -> None:
        settings = TableSettings(busy_mode_on=date(2026, 9, 12))
        assert not is_busy(settings, now=_ist(20, 0), timezone=KOLKATA, business_day_start=FIVE_AM)


class TestReadyAndTheFloor:
    def test_ready_after_the_cleaning_time(self) -> None:
        since = _ist(20, 0)
        assert ready_at(TableSettings(cleaning_minutes=8), since) == since + timedelta(minutes=8)

    def test_never_ready_by_itself_when_only_a_person_clears_it(self) -> None:
        assert ready_at(TableSettings(cleaning_minutes=None), _ist(20, 0)) is None

    def test_the_floor_shows_free_once_the_cleaning_time_has_passed(self) -> None:
        ready = _ist(20, 5)
        assert floor_status(TableStatus.CLEANING, ready, _ist(20, 4)) == TableStatus.CLEANING
        assert floor_status(TableStatus.CLEANING, ready, _ist(20, 5)) == TableStatus.FREE

    def test_no_other_status_is_ever_changed_by_the_clock(self) -> None:
        past = _ist(1, 0)
        for status in (TableStatus.OCCUPIED, TableStatus.RESERVED, TableStatus.OUT_OF_SERVICE):
            assert floor_status(status, past, _ist(20, 0)) == status
