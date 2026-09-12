// Indian digit grouping, and the reason this file exists at all.
//
// `docs/ui/conventions.md` lists "₹ prefix, Indian digit grouping (₹1,23,456), two decimals" under
// Non-negotiables. The grouping is the part that gets written wrong, because the wrong version
// looks right to anyone who has only seen Western formatting: 1,23,456 groups three digits then
// two then two, while 123,456 groups by threes. A test that only checked small numbers would pass
// against both.

import { describe, expect, it } from 'vitest';

import { formatDelta, formatINR } from './money';

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
