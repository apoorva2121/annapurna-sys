# Build brief · `indian-demand-calendar`

**Status: brief, not scope.** Written 2026-09-11. Second in priority behind `indian-fnb-lexicon`,
which has a nearer consumer.

**Rationale:** `docs/product/candidate-flagship-features.md` §B. A forecaster is commodity; the
calendar is the differentiator, and it is knowledge work that needs no customer data.

---

## What it is

A date and a place in; the demand-relevant features of that day out.

```python
def features_for(day: date, *, city: str, state: str) -> CalendarFeatures: ...
def features_between(start: date, end: date, *, city: str, state: str) -> Sequence[CalendarFeatures]: ...
```

A generic forecaster trained on ninety days of history will be confidently wrong on exactly the days
that decide a restaurant's month. This package is what stops that.

## Features

| Feature | Why a restaurant cares |
|---|---|
| `festival` + `regional_weight` | Ganesh Chaturthi is the year's peak in Pune and unremarkable in Kolkata |
| `festival_phase` — eve / day / after | Three completely different days. The eve is often the peak; the day itself can be dead if people eat at home |
| `fasting_observance` | Navratri, Shravan, Karva Chauth. Demand does not fall — it **moves** to a different menu, which a volume-only model reads as a collapse |
| `cricket_fixture` | Format, day/night, India playing. A night India match is a dine-in event and a delivery event at once |
| `monsoon_phase` (by city) | Onset and withdrawal, not month. Dine-in falls, delivery rises |
| `dry_day` (by state) | Bar revenue goes to zero, food mix shifts |
| `exam_season`, `school_holiday` | Family dining pattern inverts |
| `payday` | The 1st and the last working day are real demand events in India |
| `long_weekend` | Outbound travel empties a city; inbound fills a tourist one |

`regional_weight` matters more than the festival list. A national list with no weighting is worse
than nothing, because it will predict a spike for a festival nobody in that city observes.

## The rule that decides whether this is worth building

**Dates are sourced and cited, never generated.**

A model asked for Diwali 2027 will answer plausibly and may be wrong, and the error is invisible
until the single day it matters most. Every dated row carries its source. A year with no citable
source is absent rather than guessed — a gap is honest and a wrong date is not.

Structure this as verified data with a refresh process, not as a model's recall. Lunar and regional
calendars are precisely where confident recall fails.

## Boundaries

Same as `indian-fnb-lexicon`: never imports `app.*`, no database, no network at runtime, pure
functions, own tests and version. Output is plain data keyed by date and place.

## Coverage

- **2024 → 2030**, so backtests have history and forecasts have a horizon
- **Maharashtra and Pune first** — the pilot city. Extensible by state, and honest about what is not
  yet covered: `features_for` on an uncovered state raises rather than silently returning a national
  default, because a silent default is a wrong answer wearing a right one's clothes

## Tests

- known-date assertions against the citation for each year (Diwali, Eid, Ganesh Chaturthi, Holi)
- **every dated row has a source** — asserted, not reviewed
- no gaps: every date in the covered range resolves
- an uncovered state raises; an uncovered *year* raises. Neither degrades quietly
- `festival_phase` is consistent — every festival day has an eve and an after
- regional weighting differs where it should: the same festival returns different weights for Pune
  and Kolkata, or the weighting is not doing anything

## Done means

1. installs and tests pass with no database, no network, no `app` package present
2. `SOURCES.md` cites, per year and per festival family, where the dates came from
3. asking for an uncovered place or year fails loudly
4. a worked example: the same week, Pune versus Kolkata, showing the features genuinely diverge
