// What a *day* means, in the browser.
//
// The mirror of `backend/app/core/business_day.py`. The rule is fixed once in
// `docs/decisions/0004-money-time-units.md`: a restaurant's day starts at `business_day_start`
// (05:00 by default), not midnight, so the 01:30 order belongs to the day still being served.
//
// **Why this exists twice.** The backend owns the number that is stored — `business_date` is
// computed there and denormalised onto the row. This copy exists for the dates the UI must produce
// *before* any request is made: a default in a date field, a heading over today's figures. Those
// cannot wait for a round trip, and getting them from the browser's clock instead is how
// `NewEmployeeScreen` came to offer *yesterday* as the joining date for five and a half hours out
// of every day in India.
//
// The two implementations are held together by their tests, which use the same instants on both
// sides. If this file and the Python one ever disagree, the UI shows a date the database does not
// hold, and the person looking at it has no way to tell which is wrong.
//
// No date library: `Intl.DateTimeFormat` already carries the IANA database the browser ships, which
// is what makes this correct across a daylight-saving change rather than only in India.

/** `HH:MM` or `HH:MM:SS` — the shape `restaurant.business_day_start` arrives in. */
const START_TIME = /^(\d{2}):(\d{2})(?::(\d{2}))?$/;

/**
 * Constructing one of these is expensive and this runs on render. Keyed by zone; the set of zones
 * in a session is the restaurants the user can see, so this stays tiny.
 */
const formatters = new Map<string, Intl.DateTimeFormat>();

function formatterFor(timeZone: string): Intl.DateTimeFormat {
  const cached = formatters.get(timeZone);
  if (cached !== undefined) {
    return cached;
  }
  let formatter: Intl.DateTimeFormat;
  try {
    formatter = new Intl.DateTimeFormat('en-US', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      // Not `hour12: false`, which yields hour "24" at midnight on some engines and would put every
      // midnight instant a day late.
      hourCycle: 'h23',
    });
  } catch {
    // Refuse rather than fall back to the browser's own zone, which would silently produce wrong
    // dates for that restaurant — worse than refusing, because nobody would look.
    throw new RangeError(`Unknown timezone ${timeZone}.`);
  }
  formatters.set(timeZone, formatter);
  return formatter;
}

interface LocalClock {
  year: number;
  month: number;
  day: number;
  secondsOfDay: number;
}

function localClock(moment: Date, timeZone: string): LocalClock {
  const parts = new Map<string, string>();
  for (const part of formatterFor(timeZone).formatToParts(moment)) {
    parts.set(part.type, part.value);
  }
  const read = (type: string): number => Number(parts.get(type));
  return {
    year: read('year'),
    month: read('month'),
    day: read('day'),
    secondsOfDay: read('hour') * 3600 + read('minute') * 60 + read('second'),
  };
}

function startOfDaySeconds(dayStartsAt: string): number {
  const match = START_TIME.exec(dayStartsAt);
  if (match === null) {
    throw new RangeError(`business_day_start must look like "05:00", got ${dayStartsAt}.`);
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  const seconds = Number(match[3] ?? '00');
  if (hours > 23 || minutes > 59 || seconds > 59) {
    // The regex accepts "99:99"; a time of day does not.
    throw new RangeError(`business_day_start is not a time of day: ${dayStartsAt}.`);
  }
  return hours * 3600 + minutes * 60 + seconds;
}

function isoDate(year: number, month: number, day: number): string {
  // Through UTC rather than local: this is calendar arithmetic on a date that is already local, and
  // a local `Date` would re-apply the browser's offset and could move the day back across midnight.
  const at = new Date(Date.UTC(year, month - 1, day));
  return at.toISOString().slice(0, 10);
}

/**
 * The business date an instant belongs to, as `YYYY-MM-DD`.
 *
 * Converts to the restaurant's local time, then takes the previous calendar day when the local
 * clock has not yet reached `dayStartsAt`. The boundary is inclusive — an order at exactly 05:00
 * belongs to the new day — matching `business_date_of` in the backend exactly.
 *
 * @param moment      an instant; a `Date` is one regardless of the browser's timezone
 * @param timeZone    the restaurant's IANA zone, e.g. `Asia/Kolkata`
 * @param dayStartsAt `restaurant.business_day_start`, as `HH:MM` or `HH:MM:SS`
 */
export function businessDateOf(moment: Date, timeZone: string, dayStartsAt: string): string {
  if (Number.isNaN(moment.getTime())) {
    // `new Date('nonsense')` is an Invalid Date, and every operation on one yields NaN quietly.
    // Unguarded, that surfaces as the string "NaN-NaN-NaN" in a date field.
    throw new RangeError('businessDateOf needs a valid Date.');
  }
  const startSeconds = startOfDaySeconds(dayStartsAt);
  const local = localClock(moment, timeZone);

  if (local.secondsOfDay >= startSeconds) {
    return isoDate(local.year, local.month, local.day);
  }
  return isoDate(local.year, local.month, local.day - 1);
}

/**
 * Today's business date for a restaurant — what a date field should default to.
 *
 * Separate from `businessDateOf` so callers do not each reach for `new Date()`, which is the one
 * line that makes a component untestable.
 */
export function businessToday(timeZone: string, dayStartsAt: string, now = new Date()): string {
  return businessDateOf(now, timeZone, dayStartsAt);
}
