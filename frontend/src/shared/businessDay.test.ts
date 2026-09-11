// The browser's half of the business-day rule.
//
// These cases deliberately mirror `backend/tests/test_business_day.py`. The rule is defined once in
// `docs/decisions/0004-money-time-units.md` and implemented twice because a date must be shown and
// defaulted before any request is made — and two implementations of one rule drift silently. The
// same instants appear on both sides so a change to one that is not made to the other fails here.
//
// What makes this worth testing rather than assuming: `new Date().toISOString().slice(0, 10)` — the
// obvious one-liner, and what this file's subject replaces — returns *yesterday* in India for the
// five and a half hours after local midnight. It is right for a developer in London and wrong for
// every restaurant this product has.

import { describe, expect, it } from 'vitest';

import { businessDateOf } from '@shared/businessDay';

const KOLKATA = 'Asia/Kolkata';
// A zone that actually observes daylight saving, so a fixed-offset implementation fails here.
const LONDON = 'Europe/London';
const FIVE_AM = '05:00';
const MIDNIGHT = '00:00';

/** A UTC instant, written the way the backend tests write them. */
function utc(year: number, month: number, day: number, hour: number, minute = 0): Date {
  return new Date(Date.UTC(year, month - 1, day, hour, minute));
}

describe('the boundary', () => {
  it('puts an instant before the start on the previous day', () => {
    // 20:00 UTC on Monday the 9th is 01:30 IST on Tuesday the 10th. Still serving Monday.
    expect(businessDateOf(utc(2026, 3, 9, 20, 0), KOLKATA, FIVE_AM)).toBe('2026-03-09');
  });

  it('puts an instant after the start on the new day', () => {
    // 23:31 UTC on the 9th is 05:01 IST on the 10th.
    expect(businessDateOf(utc(2026, 3, 9, 23, 31), KOLKATA, FIVE_AM)).toBe('2026-03-10');
  });

  it('puts an instant exactly at the start on the new day', () => {
    // Inclusive lower bound, matching the backend: 05:00:00 IST on the 10th is 23:30 UTC on the 9th.
    expect(businessDateOf(utc(2026, 3, 9, 23, 30), KOLKATA, FIVE_AM)).toBe('2026-03-10');
  });

  it('is uninteresting at midday', () => {
    expect(businessDateOf(utc(2026, 3, 10, 7, 0), KOLKATA, FIVE_AM)).toBe('2026-03-10');
  });

  it('agrees with the local calendar date when the day starts at midnight', () => {
    // The degenerate case, and proof the function is not simply subtracting a day.
    expect(businessDateOf(utc(2026, 3, 9, 20, 0), KOLKATA, MIDNIGHT)).toBe('2026-03-10');
  });
});

describe('it is not toISOString().slice(0, 10)', () => {
  it('disagrees with the UTC date', () => {
    // 05:15 IST on the 11th: squarely inside the 11th's trading, past the 05:00 start.
    const moment = utc(2026, 3, 10, 23, 45);

    expect(moment.toISOString().slice(0, 10)).toBe('2026-03-10');
    expect(businessDateOf(moment, KOLKATA, FIVE_AM)).toBe('2026-03-11');
  });

  it('disagrees with the local calendar date too', () => {
    // The 00:30 order from a kitchen that closes at 2am. The local calendar has rolled over to the
    // 11th; the restaurant has not. Note UTC is accidentally right here and wrong above — the two
    // mistakes fail on different inputs, so neither can be caught by testing against the other.
    const moment = utc(2026, 3, 10, 19, 0);

    expect(moment.toLocaleDateString('en-CA', { timeZone: KOLKATA })).toBe('2026-03-11');
    expect(businessDateOf(moment, KOLKATA, FIVE_AM)).toBe('2026-03-10');
  });

  it('is wrong for five and a half hours a day, which is the bug it exists to fix', () => {
    // NewEmployeeScreen defaulted "joined on" with the UTC date. Every minute between local
    // midnight and 05:30 IST it offered yesterday, and a human accepting the default recorded the
    // wrong joining date without ever seeing anything odd.
    const justAfterLocalMidnight = utc(2026, 3, 10, 18, 45); // 00:15 IST on the 11th

    expect(justAfterLocalMidnight.toISOString().slice(0, 10)).toBe('2026-03-10');
    expect(businessDateOf(justAfterLocalMidnight, KOLKATA, MIDNIGHT)).toBe('2026-03-11');
  });
});

describe('daylight saving', () => {
  it('handles the night the clocks go forward', () => {
    // UK clocks go forward at 01:00 on 29 March 2026. 00:30 local belongs to the 28th.
    expect(businessDateOf(utc(2026, 3, 29, 0, 30), LONDON, FIVE_AM)).toBe('2026-03-28');
  });

  it('uses the new offset after the clocks go forward', () => {
    // 06:00 BST on the 29th is 05:00 UTC — only the 29th if the conversion used the new offset.
    expect(businessDateOf(utc(2026, 3, 29, 5, 0), LONDON, FIVE_AM)).toBe('2026-03-29');
  });

  it('answers rather than raising inside the repeated autumn hour', () => {
    const first = businessDateOf(utc(2026, 10, 25, 0, 30), LONDON, FIVE_AM);
    const second = businessDateOf(utc(2026, 10, 25, 1, 30), LONDON, FIVE_AM);

    expect(first).toBe('2026-10-24');
    expect(second).toBe('2026-10-24');
  });
});

describe('month and year ends', () => {
  it('rolls back into the previous month', () => {
    // 01:30 IST on 1 March 2026 is 20:00 UTC on 28 February.
    expect(businessDateOf(utc(2026, 2, 28, 20, 0), KOLKATA, FIVE_AM)).toBe('2026-02-28');
  });

  it('rolls back into the previous year', () => {
    // 02:00 IST on 1 January 2026 is 20:30 UTC on 31 December 2025.
    expect(businessDateOf(utc(2025, 12, 31, 20, 30), KOLKATA, FIVE_AM)).toBe('2025-12-31');
  });

  it('rolls back across a leap day', () => {
    // 01:00 IST on 1 March 2024 is 19:30 UTC on 29 February 2024.
    expect(businessDateOf(utc(2024, 2, 29, 19, 30), KOLKATA, FIVE_AM)).toBe('2024-02-29');
  });
});

describe('bad input', () => {
  it('refuses an unknown timezone rather than guessing', () => {
    // Falling back to the browser's zone would silently produce wrong dates for every restaurant
    // whose zone was mistyped — worse than refusing, because nobody would look.
    expect(() => businessDateOf(utc(2026, 3, 10, 12, 0), 'Mars/Olympus_Mons', FIVE_AM)).toThrow(
      /timezone/i,
    );
  });

  it('refuses a malformed start time', () => {
    expect(() => businessDateOf(utc(2026, 3, 10, 12, 0), KOLKATA, '5am')).toThrow(/start/i);
  });

  it('refuses an invalid date', () => {
    expect(() => businessDateOf(new Date('nonsense'), KOLKATA, FIVE_AM)).toThrow(/date/i);
  });
});
