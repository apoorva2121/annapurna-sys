/**
 * The geometry a chart needs, and the one place in the staff app where a figure becomes a number.
 *
 * **Why this is allowed here and nowhere else.** CLAUDE.md invariant 3 and `reportDiscipline`
 * rule 1 forbid parsing a rupee amount into a JavaScript number, because `0.1 + 0.2` is how a
 * displayed total comes to disagree with the bill. That rule is about *figures a person reads*.
 * A y-coordinate is not a figure a person reads — nobody reconciles a pixel — so turning
 * `"1234.50"` into `1234.5` to decide how tall a bar is does not put a wrong rupee on a screen.
 *
 * The property that keeps it honest is enforced by `analyticsDiscipline.test.ts`:
 *
 *   **a number produced in this file is never rendered.** Every amount on every analytics screen
 *   is formatted from the original server string through `formatINR`. The plot value decides
 *   geometry and is then thrown away, exactly as `formatINR` throws its own parse away.
 *
 * So: import `toPlotValue` to size a mark. Never to label one.
 */

/** Same grammar the API emits and `parseAmount` accepts: an optional sign, up to ten whole
 *  digits, up to two decimals. Deliberately stricter than `Number`, which reads `"1e3"` as a
 *  thousand and `"Infinity"` as a value — a malformed figure must become a gap in the line, not a
 *  mark drawn somewhere absurd. */
const PLOTTABLE = /^[+-]?\d{1,10}(?:\.\d{1,2})?$/;

/**
 * A server figure as a number **for geometry only**, or `null` when there is nothing to draw.
 *
 * `null` in, `null` out: the API sends `null` rather than `"0"` for a bucket with nothing in it,
 * and the difference matters. A restaurant that was shut has no average bill; drawing it as zero
 * puts a line through the floor of the chart and invents a terrible day that never happened.
 */
export function toPlotValue(amount: string | number | null | undefined): number | null {
  if (amount === null || amount === undefined) {
    return null;
  }
  if (typeof amount === 'number') {
    return Number.isFinite(amount) ? amount : null;
  }
  if (!PLOTTABLE.test(amount.trim())) {
    return null;
  }
  const value = Number(amount);
  return Number.isFinite(value) ? value : null;
}

/**
 * A y-axis that ends on a round number.
 *
 * `dataviz`: *"Y-axis ticks: round to clean numbers (0 / 1,000 / 2,000)"* — they carry the values
 * that are not directly labelled. An axis topping out at 47,318 makes the reader do arithmetic to
 * place a mark; one topping out at 50,000 does not.
 *
 * Returns the ticks **including both ends**, ascending, always starting at zero. A bar or line
 * chart whose baseline is not zero exaggerates every difference on it, which is the oldest chart
 * lie there is, so the baseline is not a parameter.
 */
export function niceTicks(max: number, count = 4): number[] {
  if (!Number.isFinite(max) || max <= 0) {
    return [0, 1];
  }
  const rough = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  // 1, 2, 2.5, 5, 10 — the steps that produce ticks a person reads without pausing.
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? magnitude * 10;
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let tick = 0; tick <= top + step / 2; tick += step) {
    // Floating step arithmetic (2.5 * 10^n) accumulates error; round to the step's own precision.
    ticks.push(Number(tick.toFixed(10)));
  }
  return ticks;
}

/** Where a value sits in `0..1` of the plot height. Zero-based, so the baseline is the floor. */
export function fraction(value: number, top: number): number {
  return top <= 0 ? 0 : Math.max(0, Math.min(1, value / top));
}

/**
 * A series split into the runs that can actually be drawn as one stroke.
 *
 * A `null` bucket is a hole, and a line drawn straight across it asserts trading that did not
 * happen. SVG's own answer — `NaN` in the path data — silently drops the whole path in some
 * renderers, so the split is explicit and each run is its own `<path>`.
 */
export function runs<T>(points: T[], valueOf: (point: T) => number | null): T[][] {
  const out: T[][] = [];
  let current: T[] = [];
  for (const point of points) {
    if (valueOf(point) === null) {
      if (current.length > 0) {
        out.push(current);
        current = [];
      }
    } else {
      current.push(point);
    }
  }
  if (current.length > 0) {
    out.push(current);
  }
  return out;
}
