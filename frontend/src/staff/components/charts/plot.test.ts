import { describe, expect, it } from 'vitest';

import { fraction, niceTicks, runs, toPlotValue } from './plot';

describe('toPlotValue', () => {
  it('reads the decimal strings the API actually sends', () => {
    expect(toPlotValue('1234.50')).toBe(1234.5);
    expect(toPlotValue('0.00')).toBe(0);
    expect(toPlotValue('-40.25')).toBe(-40.25);
  });

  // The distinction the whole module rests on. `null` is "the restaurant was shut", and a zero
  // would draw a catastrophic day that never happened.
  it('keeps null as null rather than turning it into zero', () => {
    expect(toPlotValue(null)).toBeNull();
    expect(toPlotValue(undefined)).toBeNull();
    expect(toPlotValue(0)).toBe(0);
  });

  // `Number` is permissive in ways that put a mark in an absurd place rather than refusing.
  it('refuses the inputs Number would happily misread', () => {
    for (const input of ['1e3', '0x10', 'Infinity', '', ' ', 'abc', '12.345', '1,234']) {
      expect(toPlotValue(input), input).toBeNull();
    }
  });
});

describe('niceTicks', () => {
  it('ends on a round number at or above the maximum', () => {
    expect(niceTicks(47318).at(-1)).toBeGreaterThanOrEqual(47318);
    expect(niceTicks(47318)).toEqual([0, 20000, 40000, 60000]);
  });

  it('does not leave the data squashed in the bottom of the plot', () => {
    // A round top is only worth having if it is *near* the data. Twice the maximum would be
    // round, and would also make every real movement invisible.
    for (const max of [3, 97, 1234, 47318, 88000]) {
      const top = niceTicks(max).at(-1) ?? 0;
      expect(top, `max ${String(max)}`).toBeLessThan(max * 1.5 + 2);
    }
  });

  it('always starts at zero, because a lifted baseline exaggerates every difference', () => {
    for (const max of [3, 97, 1234, 88000]) {
      expect(niceTicks(max)[0]).toBe(0);
    }
  });

  it('is ascending and free of floating-point dust', () => {
    for (const max of [3, 9, 47, 250, 1001, 47318, 999999]) {
      const ticks = niceTicks(max);
      expect(ticks, `max ${String(max)}`).toEqual([...ticks].sort((a, b) => a - b));
      for (const tick of ticks) {
        // Dust looks like 12500.000000001, so the test is about the *decimal tail*, not about
        // magnitude — 250000 is a perfectly good tick. Four decimals is far more than any
        // rupee or cover count needs and far less than error accumulates to.
        expect(Number(tick.toFixed(4)), `max ${String(max)} tick ${String(tick)}`).toBe(tick);
      }
    }
  });

  it('survives a day with no trading at all', () => {
    expect(niceTicks(0)).toEqual([0, 1]);
    expect(niceTicks(Number.NaN)).toEqual([0, 1]);
  });
});

describe('fraction', () => {
  it('places a value in 0..1 of the plot height', () => {
    expect(fraction(50, 100)).toBe(0.5);
    expect(fraction(0, 100)).toBe(0);
    expect(fraction(100, 100)).toBe(1);
  });

  it('clamps rather than drawing outside the plot', () => {
    expect(fraction(150, 100)).toBe(1);
    expect(fraction(-10, 100)).toBe(0);
    expect(fraction(5, 0)).toBe(0);
  });
});

describe('runs', () => {
  const value = (point: { v: number | null }): number | null => point.v;

  it('breaks the line where the restaurant was shut', () => {
    const points = [{ v: 1 }, { v: 2 }, { v: null }, { v: 3 }, { v: 4 }];
    expect(runs(points, value)).toEqual([[{ v: 1 }, { v: 2 }], [{ v: 3 }, { v: 4 }]]);
  });

  it('never emits an empty run, which would render as a stray path', () => {
    const points = [{ v: null }, { v: null }, { v: 1 }, { v: null }];
    expect(runs(points, value)).toEqual([[{ v: 1 }]]);
  });

  it('returns nothing at all when there is nothing to draw', () => {
    expect(runs([{ v: null }], value)).toEqual([]);
    expect(runs([], value)).toEqual([]);
  });
});
