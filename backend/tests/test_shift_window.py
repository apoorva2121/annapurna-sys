"""The crossing-midnight arithmetic, with no database in the way.

`app/core/shift_window.py` is pure, which is the point: this is the module every later question
about a shift resolves to — who was on the floor, how many hours M17 normalises against, whose
section a table is in — and none of those can detect it being wrong. A shift placed on the wrong
day looks entirely normal and surfaces months later as a fairness score that is out by a night.

CLAUDE.md invariant 4 is the rule under test: a restaurant's business day is not midnight to
midnight, and `business_day_start` (05:00 here, as it is for the seeded restaurant) is what makes
that expressible.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.core import shift_window

IST = "Asia/Kolkata"
OPENS_AT_FIVE = time(5, 0)

MORNING = (time(8, 0), time(16, 0))
EVENING = (time(18, 0), time(0, 30))
# A shift that begins before the business day does: the small hours at the *end* of a day.
NIGHT = (time(1, 0), time(4, 0))


def ist(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """A local wall-clock moment in Pune, as the instant it actually is."""
    from zoneinfo import ZoneInfo

    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(IST)).astimezone(UTC)


def span(business_day: date, times: tuple[time, time]) -> shift_window.ShiftSpan:
    return shift_window.span_of(
        business_day=business_day,
        start=times[0],
        end=times[1],
        timezone=IST,
        business_day_start=OPENS_AT_FIVE,
    )


class TestWhichShiftsCross:
    def test_an_evening_that_ends_after_midnight_crosses(self) -> None:
        assert shift_window.crosses_midnight(*EVENING)

    def test_a_morning_does_not(self) -> None:
        assert not shift_window.crosses_midnight(*MORNING)

    def test_equal_times_are_a_zero_length_shift_not_a_day_long_one(self) -> None:
        """Somebody typing the same value twice meant nothing by it, and reading it as twenty-four
        hours would put one person on the floor all day in every later query."""
        assert not shift_window.crosses_midnight(time(9, 0), time(9, 0))


class TestWhereAShiftSits:
    def test_a_morning_shift_is_where_it_says(self) -> None:
        found = span(date(2026, 9, 18), MORNING)
        assert found.starts_at == ist(2026, 9, 18, 8)
        assert found.ends_at == ist(2026, 9, 18, 16)

    def test_an_evening_shift_ends_on_the_next_calendar_day(self) -> None:
        """The M12 spec's first acceptance criterion. Business date 18 September, ending at 00:30
        on the 19th — one business day, two calendar days."""
        found = span(date(2026, 9, 18), EVENING)
        assert found.starts_at == ist(2026, 9, 18, 18)
        assert found.ends_at == ist(2026, 9, 19, 0, 30)

    def test_a_shift_starting_before_the_day_opens_lands_at_the_end_of_it(self) -> None:
        """01:00 is *after* business date D began at 05:00 on D — it is the small hours of D+1 in
        calendar terms. Getting this backwards would file a 1am stocktake against yesterday."""
        found = span(date(2026, 9, 18), NIGHT)
        assert found.starts_at == ist(2026, 9, 19, 1)
        assert found.ends_at == ist(2026, 9, 19, 4)


class TestWhatAShiftCovers:
    @pytest.mark.parametrize(
        ("moment", "expected"),
        [
            (ist(2026, 9, 18, 17, 59), False),
            (ist(2026, 9, 18, 18, 0), True),
            (ist(2026, 9, 18, 23, 59), True),
            (ist(2026, 9, 19, 0, 15), True),
            (ist(2026, 9, 19, 0, 30), False),
        ],
    )
    def test_the_evening_shift_across_midnight(self, moment: datetime, expected: bool) -> None:
        assert span(date(2026, 9, 18), EVENING).covers(moment) is expected

    def test_the_end_is_exclusive_so_two_shifts_never_both_claim_the_handover(self) -> None:
        """A Morning 08:00-16:00 and an Evening 16:00-23:00 meet at 16:00. If both covered it,
        "who is on the floor" would have two answers exactly when a handover makes the question
        worth asking."""
        handover = ist(2026, 9, 18, 16)
        assert not span(date(2026, 9, 18), MORNING).covers(handover)
        assert span(date(2026, 9, 18), (time(16, 0), time(23, 0))).covers(handover)

    def test_yesterdays_evening_shift_still_covers_this_morning(self) -> None:
        """00:15 on the 19th belongs to the 18th's Evening, not the 19th's. A roster that only
        looked at today's business date would leave the late rush with nobody on it."""
        late = ist(2026, 9, 19, 0, 15)
        assert span(date(2026, 9, 18), EVENING).covers(late)
        assert not span(date(2026, 9, 19), EVENING).covers(late)


class TestLateness:
    def test_inside_the_grace_is_present(self) -> None:
        found = span(date(2026, 9, 18), MORNING)
        assert not shift_window.is_late(ist(2026, 9, 18, 8, 9), found, grace_minutes=10)

    def test_eleven_minutes_after_a_ten_minute_grace_is_late(self) -> None:
        found = span(date(2026, 9, 18), MORNING)
        assert shift_window.is_late(ist(2026, 9, 18, 8, 11), found, grace_minutes=10)

    def test_arriving_early_is_never_late(self) -> None:
        found = span(date(2026, 9, 18), MORNING)
        assert not shift_window.is_late(ist(2026, 9, 18, 7, 30), found, grace_minutes=10)


class TestTheGraceIsReadTolerantly:
    """`floor_rules.py`'s pattern, 2026-09-13: a restaurant seeded before this existed has no
    `shifts` key, and a malformed value written by hand must not take the roster down at the start
    of a service. The API validates strictly on the way in; this is the way out."""

    @pytest.mark.parametrize(
        "settings",
        [
            None,
            {},
            {"shifts": None},
            {"shifts": {}},
            {"shifts": {"late_after_minutes": "ten"}},
            {"shifts": {"late_after_minutes": -1}},
            {"shifts": {"late_after_minutes": 1000}},
            {"shifts": {"late_after_minutes": True}},
        ],
    )
    def test_anything_unreadable_falls_back(self, settings: object) -> None:
        assert (
            shift_window.grace_minutes_from(settings)
            == shift_window.DEFAULT_LATE_AFTER_MINUTES
        )

    def test_a_real_value_is_used(self) -> None:
        assert shift_window.grace_minutes_from({"shifts": {"late_after_minutes": 25}}) == 25


def test_the_business_day_boundary_is_the_one_business_day_owns() -> None:
    """This module adds no second implementation of invariant 4 — it names the one that exists, so
    nobody reaches past it for the raw function and gets a different answer."""
    at_0430 = ist(2026, 9, 19, 4, 30)
    at_0500 = ist(2026, 9, 19, 5, 0)
    assert shift_window.business_day_for(at_0430, IST, OPENS_AT_FIVE) == date(2026, 9, 18)
    assert shift_window.business_day_for(at_0500, IST, OPENS_AT_FIVE) == date(2026, 9, 19)


def test_a_span_is_never_backwards() -> None:
    """Every combination of hours, checked rather than argued: an end before its start would be a
    negative duration M17 would later divide by."""
    for start_hour in range(24):
        for end_hour in range(24):
            found = span(date(2026, 9, 18), (time(start_hour), time(end_hour)))
            assert found.ends_at > found.starts_at
            assert found.ends_at - found.starts_at <= timedelta(hours=24)
