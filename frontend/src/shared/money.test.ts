// Indian digit grouping, and the reason this file exists at all.
//
// `docs/ui/conventions.md` lists "₹ prefix, Indian digit grouping (₹1,23,456), two decimals" under
// Non-negotiables. The grouping is the part that gets written wrong, because the wrong version
// looks right to anyone who has only seen Western formatting: 1,23,456 groups three digits then
// two then two, while 123,456 groups by threes. A test that only checked small numbers would pass
// against both.

import { describe, expect, it } from 'vitest';

import { formatDelta, formatINR, formatINRAxis, parseAmount, percentToFraction } from './money';

describe('formatINR', () => {
  it('groups by the Indian system, not by thousands', () => {
    // The discriminating case. A `en-US` formatter returns "₹123,456.00" here and is wrong.
    expect(formatINR('123456')).toBe('₹1,23,456.00');
    expect(formatINR('12345678')).toBe('₹1,23,45,678.00');
  });

  it('always shows two decimals, because a menu price is a money amount', () => {
    expect(formatINR('470')).toBe('₹470.00');
    expect(formatINR('470.5')).toBe('₹470.50');
  });

  it('takes the string the server sent and never a float', () => {
    // The whole API returns money as a decimal string so no JavaScript number touches a rupee
    // (CLAUDE.md invariant 3). This asserts the formatter accepts that shape directly.
    expect(formatINR('1240.00')).toBe('₹1,240.00');
  });

  it('renders an em dash rather than ₹NaN when something upstream is wrong', () => {
    // `price` is NOT NULL, so this path means a bug elsewhere. A dash does not look like a real
    // amount; "₹NaN" on a bill preview looks like a product that cannot count.
    expect(formatINR(null)).toBe('—');
    expect(formatINR(undefined)).toBe('—');
    expect(formatINR('')).toBe('—');
    expect(formatINR('not a number')).toBe('—');
  });

  it('formats zero as a price, not as nothing', () => {
    // A complimentary side is a real menu line at ₹0.00 and must read as priced.
    expect(formatINR('0')).toBe('₹0.00');
  });
});

describe('formatDelta', () => {
  it('signs a price change so a waiter can see which way it goes', () => {
    expect(formatDelta('40')).toBe('+₹40.00');
  });

  it('uses a real minus sign, not a hyphen', () => {
    // U+2212. At the size a modifier list is read, a hyphen is easy to miss entirely — and
    // mistaking a discount for a surcharge is a number on a bill.
    expect(formatDelta('-20')).toBe('−₹20.00');
    expect(formatDelta('-20')).not.toContain('-');
  });

  it('renders nothing at zero, because a free choice is a choice and not a price', () => {
    expect(formatDelta('0')).toBe('');
    expect(formatDelta(null)).toBe('');
  });
});

describe('parseAmount', () => {
  // The write path. Everything above formats for a screen and throws the number away; this one
  // produces the string that gets stored, which is why it must never route through a float.
  it('pads what a person typed to two places, by string surgery', () => {
    expect(parseAmount('470')).toBe('470.00');
    expect(parseAmount('12.5')).toBe('12.50');
    expect(parseAmount('  99.99  ')).toBe('99.99');
  });

  it('refuses the inputs Number quietly accepts', () => {
    // Each of these becomes a real number under `Number()`, so the old `Number(x).toFixed(2)`
    // turned a typo into a price instead of refusing it. `""` is the dangerous one: it is 0.
    expect(parseAmount('')).toBeNull();
    expect(parseAmount('1e3')).toBeNull();
    expect(parseAmount('0x10')).toBeNull();
    expect(parseAmount('Infinity')).toBeNull();
    expect(parseAmount('12.345')).toBeNull();
    expect(parseAmount('rupees')).toBeNull();
  });

  it('refuses a negative price and allows a negative delta', () => {
    // "no rice" can legitimately be a discount; a dish cannot cost less than nothing.
    expect(parseAmount('-20')).toBeNull();
    expect(parseAmount('-20', { allowNegative: true })).toBe('-20.00');
  });

  it('does not invent a negative zero', () => {
    expect(parseAmount('-0', { allowNegative: true })).toBe('0.00');
  });

  it('survives the amount that motivates the whole rule', () => {
    // 0.1 + 0.2 is the reason this file forbids arithmetic. A parse that round-tripped through a
    // float would be free to return "1234567.89000001" here on some input; string surgery cannot.
    expect(parseAmount('1234567.89')).toBe('1234567.89');
  });
});

// Backlog-issues B6. The tax screen turned a typed percentage into the stored fraction through a
// float, and accepted anything `Number` does — "1e1" became a 10% tax rate. A rate is not money, but
// it is copied onto every order line and can never be edited, only superseded.
describe('percentToFraction', () => {
  it('moves the decimal point in the string, never through a float', () => {
    expect(percentToFraction('5')).toBe('0.0500');
    expect(percentToFraction('12.5')).toBe('0.1250');
    expect(percentToFraction('0.25')).toBe('0.0025');
    expect(percentToFraction('100')).toBe('1.0000');
    expect(percentToFraction(' 18 ')).toBe('0.1800');
  });

  it('refuses anything that is not a percentage from 0 to 100 with at most two decimals', () => {
    for (const typed of ['', '1e1', '101', '100.5', '-5', '5%', '12.345', '0x10']) {
      expect(percentToFraction(typed)).toBeNull();
    }
  });
});

// M19 chunk B. A chart axis is a scale, not a figure anybody reconciles, so its ticks drop the
// paise that would otherwise repeat on every gridline. The exact amount stays in the tooltip and
// the table, both of which go through `formatINR`.
describe('formatINRAxis', () => {
  it('drops the paise a gridline does not need', () => {
    expect(formatINRAxis('80000')).toBe('₹80,000');
    expect(formatINRAxis('0')).toBe('₹0');
    expect(formatINRAxis(20000)).toBe('₹20,000');
  });

  it('keeps Indian digit grouping, which is the whole reason Intl is used', () => {
    // Three, then two, then two — 1,23,456 and not 123,456.
    expect(formatINRAxis('123456')).toBe('₹1,23,456');
  });

  it('renders a dash rather than ₹NaN for something that is not a number', () => {
    for (const value of [null, undefined, '', 'abc']) {
      expect(formatINRAxis(value)).toBe('—');
    }
  });

  // The guard against somebody reaching for this on a bill: it rounds, and a rounded rupee figure
  // beside an exact one is how two numbers on one screen come to disagree.
  it('rounds, which is why it is for axes only', () => {
    expect(formatINRAxis('79999.50')).toBe('₹80,000');
    expect(formatINR('79999.50')).toBe('₹79,999.50');
  });
});
