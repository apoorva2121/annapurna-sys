"""What a *day* means — the arithmetic every later number in this product rests on.

A restaurant closing at 2am must count that 2am against the day it was still serving.
`business_date` is denormalised onto every order at insert, reporting groups on it, and M13's
dashboards, M17's shift figures and M15's 120-day generator all inherit what this function decides.

**Why this file is longer than the function it tests.** A wrong answer here is *plausible* rather
than obviously broken. A 01:30 order booked to the wrong day looks completely normal on screen; it
surfaces months later as a month-end total that is out by one night's takings, in data that is by
then too deep to recompute. Nothing downstream can detect it, because everything downstream trusts
it. So the tests are written to rule out families of inputs rather than to confirm three examples:

- hand-written cases for the boundaries a human can reason about,
- property-based cases for the ones nobody thinks of,
- and a deliberate contrast with `date_trunc('day', created_at)`, which is what someone reaches for
  having forgotten this module exists.

**Asia/Kolkata is not enough on its own.** India has no daylight saving, so an implementation that
assumed a fixed UTC offset would pass every Indian test while being wrong everywhere else — and
`restaurant.timezone` is an IANA zone precisely because the column outlives that assumption. The
DST cases below exist to fail that implementation.
"""

from __future__ import annotations

import zoneinfo
from datetime import UTC, date, datetime, time, timedelta
from importlib.metadata import version
from zoneinfo import ZoneInfo

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.core.business_day import (
    business_date_of,
    calendar_date_of,
    day_bounds_utc,
    financial_year_of,
)

KOLKATA = "Asia/Kolkata"
# A zone that actually observes daylight saving, so a fixed-offset implementation fails here.
LONDON = "Europe/London"
FIVE_AM = time(5, 0)
MIDNIGHT = time(0, 0)


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class TestTheBoundary:
    """The rule, at the only place it is interesting."""

    def test_just_before_the_start_belongs_to_the_previous_day(self) -> None:
        # IST is UTC+5:30, so the UTC date is a day *behind* the local one all evening: 20:00 UTC
        # on Monday the 9th is 01:30 IST on Tuesday the 10th. The kitchen is still serving Monday,
        # so the answer is the 9th.
        moment = _utc(2026, 3, 9, 20, 0)

        assert business_date_of(moment, KOLKATA, FIVE_AM) == date(2026, 3, 9)

    def test_just_after_the_start_belongs_to_the_new_day(self) -> None:
        # 23:31 UTC on the 9th is 05:01 IST on the 10th — one minute the other side of the same
        # boundary the test above sits below.
        moment = _utc(2026, 3, 9, 23, 31)

        assert business_date_of(moment, KOLKATA, FIVE_AM) == date(2026, 3, 10)

    def test_exactly_at_the_start_belongs_to_the_new_day(self) -> None:
        """Inclusive lower bound. A day has to start *somewhere*, and an order at exactly 05:00
        landing on yesterday would be indefensible to explain to an owner."""
        # 05:00:00 IST on 10 March = 23:30 UTC on 9 March.
        moment = _utc(2026, 3, 9, 23, 30)

        assert business_date_of(moment, KOLKATA, FIVE_AM) == date(2026, 3, 10)

    def test_midday_is_never_interesting(self) -> None:
        assert business_date_of(_utc(2026, 3, 10, 7, 0), KOLKATA, FIVE_AM) == date(2026, 3, 10)

    def test_a_midnight_start_makes_business_date_the_local_date(self) -> None:
        """The degenerate case, and the one that proves the function is not simply subtracting a
        day: with `business_day_start = 00:00` it must agree with the local calendar date."""
        moment = _utc(2026, 3, 9, 20, 0)  # 01:30 IST on the 10th

        assert business_date_of(moment, KOLKATA, MIDNIGHT) == date(2026, 3, 10)


class TestItIsNotDateTrunc:
    """The implementation someone reaches for when they have forgotten this module exists.

    `date_trunc('day', created_at)` is wrong twice over — it uses UTC rather than the restaurant's
    timezone, and it knows nothing about the day starting at 05:00. These assert that the two
    genuinely disagree, so a future refactor that quietly replaces one with the other fails here.
    """

    def test_truncating_in_utc_is_wrong(self) -> None:
        """The first mistake: `date_trunc('day', created_at)` with no timezone at all.

        An order placed at 05:15 on the morning of the 11th is squarely inside the 11th's trading —
        past the 05:00 start, nothing ambiguous about it. UTC still calls it the 10th, because in
        IST the UTC date lags by five and a half hours.
        """
        moment = _utc(2026, 3, 10, 23, 45)  # 05:15 IST on the 11th

        assert moment.date() == date(2026, 3, 10), "UTC truncation says the 10th"
        assert business_date_of(moment, KOLKATA, FIVE_AM) == date(2026, 3, 11), "it is the 11th"

    def test_truncating_in_local_time_is_also_wrong(self) -> None:
        """The second mistake, and the more dangerous one: converting to the restaurant's timezone
        first and *then* truncating. That fixes the offset and still ignores the 05:00 start.

        This is the 00:30 order from a kitchen that closes at 2am. The local calendar has rolled
        over to the 11th; the restaurant has not — it is still serving the 10th.

        Note that UTC happens to give the right answer for this instant. The two mistakes fail on
        different inputs, so neither one can be caught by testing against the other.
        """
        moment = _utc(2026, 3, 10, 19, 0)  # 00:30 IST on the 11th

        local_date = moment.astimezone(ZoneInfo(KOLKATA)).date()
        assert local_date == date(2026, 3, 11), "the local calendar date has already rolled over"
        assert business_date_of(moment, KOLKATA, FIVE_AM) == date(2026, 3, 10), (
            "the business day has not"
        )


class TestDaylightSaving:
    """India has none, so every Indian test passes on an implementation that assumes a fixed
    offset. These are the ones that do not."""

    def test_the_spring_forward_night(self) -> None:
        # UK clocks go forward at 01:00 on 29 March 2026. 00:30 local is 00:30 UTC; the business
        # day began at 05:00 on the 28th, so this belongs to the 28th.
        moment = _utc(2026, 3, 29, 0, 30)

        assert business_date_of(moment, LONDON, FIVE_AM) == date(2026, 3, 28)

    def test_after_the_spring_forward_the_offset_has_changed(self) -> None:
        # 06:00 BST on 29 March = 05:00 UTC. Past the start, so it is the 29th — and it is only
        # the 29th if the conversion used the *new* offset.
        moment = _utc(2026, 3, 29, 5, 0)

        assert business_date_of(moment, LONDON, FIVE_AM) == date(2026, 3, 29)

    def test_the_autumn_ambiguous_hour_resolves_without_raising(self) -> None:
        """01:30 happens twice on the night the clocks go back. Either resolution puts it before
        05:00, so the business date is the same both times — what matters is that it answers rather
        than raising on an ambiguous local time."""
        # 25 October 2026, 00:30 and 01:30 UTC both land inside the repeated local hour.
        first = business_date_of(_utc(2026, 10, 25, 0, 30), LONDON, FIVE_AM)
        second = business_date_of(_utc(2026, 10, 25, 1, 30), LONDON, FIVE_AM)

        assert first == second == date(2026, 10, 24)


class TestProperties:
    """The families of input nobody writes an example for."""

    @given(
        moment=st.datetimes(
            min_value=datetime(2024, 1, 1),
            max_value=datetime(2030, 12, 31),
            timezones=st.just(UTC),
        ),
        start_hour=st.integers(min_value=0, max_value=23),
        zone=st.sampled_from([KOLKATA, LONDON, "America/New_York", "Pacific/Kiritimati"]),
    )
    @settings(max_examples=300, deadline=None)
    def test_the_business_date_is_the_local_date_or_the_day_before(
        self, moment: datetime, start_hour: int, zone: str
    ) -> None:
        """The whole rule, as one property.

        Whatever the instant, whatever the zone, whatever the start hour: the answer is the local
        calendar date, or exactly one day earlier, and which one is decided solely by whether the
        local time has reached the start. Any implementation that is off by a day, uses UTC instead
        of local, or mishandles an offset change fails this.
        """
        start = time(start_hour, 0)
        local = moment.astimezone(ZoneInfo(zone))
        result = business_date_of(moment, zone, start)

        expected = local.date() if local.time() >= start else local.date() - timedelta(days=1)
        assert result == expected

    @given(
        moment=st.datetimes(
            min_value=datetime(2024, 1, 1),
            max_value=datetime(2030, 12, 31),
            timezones=st.just(UTC),
        ),
        zone=st.sampled_from([KOLKATA, LONDON, "America/New_York"]),
    )
    @settings(max_examples=200, deadline=None)
    def test_a_midnight_start_always_equals_the_local_date(
        self, moment: datetime, zone: str
    ) -> None:
        """With the day starting at midnight there is nothing to subtract, so the business date must
        be the local calendar date — always, in every zone. An implementation that subtracts a day
        unconditionally, or that works in UTC, fails this immediately."""
        local_date = moment.astimezone(ZoneInfo(zone)).date()

        assert business_date_of(moment, zone, MIDNIGHT) == local_date

    @given(
        moment=st.datetimes(
            min_value=datetime(2024, 1, 1),
            max_value=datetime(2030, 12, 31),
            timezones=st.just(UTC),
        ),
        start_hour=st.integers(min_value=0, max_value=23),
    )
    @settings(max_examples=200, deadline=None)
    def test_it_never_moves_by_more_than_one_day(self, moment: datetime, start_hour: int) -> None:
        """A guard against the arithmetic going wrong in a way the property above might mirror:
        the business date is always within a day of the UTC date for a zone whose offset is under
        24 hours, which is all of them."""
        result = business_date_of(moment, KOLKATA, time(start_hour, 0))

        assert abs((result - moment.date()).days) <= 1


class TestDayBounds:
    """The inverse: given a business date, which instants belong to it?

    Reporting needs this — "today's sales" is a range over `created_at`, and deriving the range from
    the same rule that assigned the date is what stops the two drifting apart.
    """

    def test_the_bounds_are_half_open(self) -> None:
        start, end = day_bounds_utc(date(2026, 3, 10), KOLKATA, FIVE_AM)

        # 05:00 IST on the 10th through 05:00 IST on the 11th, exclusive.
        assert start == _utc(2026, 3, 9, 23, 30)
        assert end == _utc(2026, 3, 10, 23, 30)

    @given(
        day=st.dates(min_value=date(2024, 1, 1), max_value=date(2030, 12, 31)),
        start_hour=st.integers(min_value=0, max_value=23),
        zone=st.sampled_from([KOLKATA, LONDON, "America/New_York"]),
    )
    @settings(max_examples=200, deadline=None)
    def test_every_instant_in_the_range_maps_back_to_that_business_date(
        self, day: date, start_hour: int, zone: str
    ) -> None:
        """The round trip, and the property that makes the pair trustworthy: if `day_bounds_utc`
        and `business_date_of` ever disagreed, a report would count an order the order itself does
        not think belongs to that day."""
        start_time = time(start_hour, 0)
        start, end = day_bounds_utc(day, zone, start_time)
        assume(start < end)

        for moment in (start, start + (end - start) / 2, end - timedelta(microseconds=1)):
            assert business_date_of(moment, zone, start_time) == day

    def test_the_end_of_one_day_is_the_start_of_the_next(self) -> None:
        """No gap and no overlap, or an order at exactly the boundary is counted twice or not at
        all."""
        _, first_end = day_bounds_utc(date(2026, 3, 10), KOLKATA, FIVE_AM)
        second_start, _ = day_bounds_utc(date(2026, 3, 11), KOLKATA, FIVE_AM)

        assert first_end == second_start


class TestBadInput:
    def test_an_unknown_timezone_is_refused_rather_than_guessed(self) -> None:
        """Falling back to UTC would silently produce wrong dates for every order in that
        restaurant — worse than refusing, because nobody would look."""
        with pytest.raises(ValueError, match="timezone"):
            business_date_of(_utc(2026, 3, 10, 12, 0), "Mars/Olympus_Mons", FIVE_AM)

    def test_a_naive_datetime_is_refused(self) -> None:
        """An instant without a timezone is not an instant. Assuming UTC here is how a local
        `datetime.now()` silently becomes a five-and-a-half-hour error."""
        with pytest.raises(ValueError, match="aware"):
            business_date_of(datetime(2026, 3, 10, 12, 0), KOLKATA, FIVE_AM)


class TestTheDatabaseItself:
    """The IANA database has to be a dependency, not a thing the host happens to have.

    Every test above resolves zones through `zoneinfo`, which reads the operating system's copy and
    falls back to the `tzdata` package. Debian ships a system copy and Windows ships none, so this
    whole file passed in CI and raised `ZoneInfo("Asia/Kolkata")` on a developer's laptop until
    `tzdata` became a runtime dependency — which is the weaker half of the problem. The real one is
    that two hosts reading two copies can disagree about a timezone rule while both look healthy.
    """

    def test_the_tz_database_is_installed_as_a_package(self) -> None:
        """Fails if `tzdata` is dropped from pyproject.toml, even on a machine whose OS would hide
        the loss. Paired with `ENV PYTHONTZPATH=""` in the Dockerfile, which stops the container
        reading Debian's copy instead of this one.

        Asks the installed distributions rather than importing the module, so it is checking the
        declared dependency and not merely that some `tzdata` is importable from somewhere.
        """
        assert version("tzdata")

    def test_a_zone_still_resolves_with_the_system_path_removed(self) -> None:
        """The container's configuration, exercised here rather than trusted.

        `PYTHONTZPATH=""` is read once at interpreter start, so this resets the search path by hand
        to prove the package alone can answer. If it cannot, the image raises on the first order it
        ever timestamps — a failure worth finding in a test rather than on a deploy.

        **`no_cache` is the assertion, not an optimisation detail.** `ZoneInfo()` is memoised
        process-wide and `reset_tzpath()` does not invalidate that cache, so every test above this
        one has already warmed `Asia/Kolkata`. Constructing through the cache answered from memory
        with the search path empty — verified to succeed even with `tzdata` unimportable — so this
        passed without ever consulting the path it had just emptied. Found by external review.
        """
        original = zoneinfo.TZPATH
        try:
            zoneinfo.reset_tzpath(to=[])
            assert zoneinfo.ZoneInfo.no_cache("Asia/Kolkata").key == "Asia/Kolkata"
            assert zoneinfo.ZoneInfo.no_cache("Europe/London").key == "Europe/London"
        finally:
            zoneinfo.reset_tzpath(to=list(original))


class TestTheFinancialYear:
    """M07. An invoice series follows the calendar, and the calendar and the working day disagree
    for four and a half hours every night."""

    def test_a_bill_at_0130_on_1_april_splits_the_two_boundaries(self) -> None:
        """Acceptance criterion 4. 20:00 UTC on 31 March is 01:30 IST on 1 April: business day
        31 March, invoice dated 1 April, and the new year's series."""
        moment = _utc(2027, 3, 31, 20, 0)

        assert business_date_of(moment, KOLKATA, FIVE_AM) == date(2027, 3, 31)
        assert calendar_date_of(moment, KOLKATA) == date(2027, 4, 1)
        assert financial_year_of(calendar_date_of(moment, KOLKATA)) == "2027-28"

    def test_the_business_date_would_file_that_bill_in_the_closed_year(self) -> None:
        """The mistake this helper exists to prevent, shown rather than described."""
        moment = _utc(2027, 3, 31, 20, 0)

        assert financial_year_of(business_date_of(moment, KOLKATA, FIVE_AM)) == "2026-27"

    @pytest.mark.parametrize(
        ("day", "year"),
        [
            (date(2026, 3, 31), "2025-26"),
            (date(2026, 4, 1), "2026-27"),
            (date(2026, 12, 31), "2026-27"),
            (date(2027, 1, 1), "2026-27"),
            (date(1999, 4, 1), "1999-00"),
        ],
    )
    def test_the_year_begins_on_1_april(self, day: date, year: str) -> None:
        assert financial_year_of(day) == year

    @given(st.dates(min_value=date(2000, 1, 1), max_value=date(2098, 12, 31)))
    def test_every_date_belongs_to_the_year_its_label_names(self, day: date) -> None:
        label = financial_year_of(day)
        start = int(label[:4])

        assert date(start, 4, 1) <= day < date(start + 1, 4, 1)
        assert label[5:] == f"{(start + 1) % 100:02d}"

    def test_a_naive_datetime_is_refused(self) -> None:
        with pytest.raises(ValueError):
            calendar_date_of(datetime(2027, 3, 31, 20, 0), KOLKATA)
