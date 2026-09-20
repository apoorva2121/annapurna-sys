// The rules M19's screens live or die by, checked by a machine.
//
// Analytics is the surface where a wrong habit is least visible and most expensive: a chart looks
// authoritative at a glance, and nobody re-derives a bar by hand. Five rules, each a sentence from
// a document rather than a preference.
//
// 1. **A plot number is never rendered.** `plot.ts` is the one place a figure becomes a number, and
//    it exists for geometry — a y-coordinate, a bar length. CLAUDE.md invariant 3 forbids a rupee
//    amount going through a JavaScript float on its way to a person. The quarantine is the whole
//    justification for that file existing, so it is checked rather than promised.
// 2. **Nothing tax-shaped appears.** The owner's decision of 2026-09-19: two branches can hold
//    different GSTINs and even different schemes, so a combined tax figure has no legal referent.
//    The API omits the field; this keeps the frontend from inventing one.
// 3. **No series wears an alert colour.** `docs/ui/conventions.md` locks six alert hues and
//    `critical` means *somebody must act now*. A revenue line painted red teaches people to ignore
//    red — M19 acceptance criterion 5.
// 4. **No chart has two y-axes.** `dataviz`'s first non-negotiable, and the single most common
//    chart mistake: two scales make unrelated measures look correlated.
// 5. **A second series would need a legend.** Today every chart here draws one series, so the
//    heading names it and a legend box would restate the heading. The moment that stops being true
//    the legend is not optional, so the rule is written down now rather than discovered later.
import { describe, expect, it } from 'vitest';

const sources = import.meta.glob<string>('./**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

/** Everything M19 chunk B added, minus its own tests. */
function analyticsEntries(): [string, string][] {
  return Object.entries(sources)
    .filter(
      ([path]) =>
        (path.includes('/components/charts/') ||
          path.includes('AnalyticsScreen') ||
          path.includes('api/analytics')) &&
        !path.includes('.test.'),
    )
    .map(([path, source]) => [path, withoutComments(source)]);
}

describe('the analytics screens keep their five promises', () => {
  it('reads the files it checks, so an empty parse cannot pass', () => {
    const paths = analyticsEntries().map(([path]) => path);
    expect(paths.length).toBeGreaterThanOrEqual(4);
    expect(paths.some((path) => path.includes('AnalyticsScreen'))).toBe(true);
    expect(paths.some((path) => path.endsWith('plot.ts'))).toBe(true);
  });

  // Rule 1. `plot.ts` is the single exemption, and it is exempt *because* it never renders.
  it('parses a figure into a number in plot.ts and nowhere else', () => {
    const offenders = analyticsEntries()
      .filter(([path]) => !path.endsWith('plot.ts'))
      .filter(([, code]) => /\bNumber\(|\bparseFloat\(|\bparseInt\(/.test(code))
      .map(([path]) => path);

    expect(offenders).toEqual([]);
  });

  it('never renders a value that came back out of the plot', () => {
    // The geometry helpers return numbers for marks. If one of them appears inside JSX braces it
    // is on its way to a person's eyes, which is exactly what the quarantine forbids.
    const offenders = analyticsEntries()
      .filter(([path]) => !path.endsWith('plot.ts'))
      .filter(([, code]) => /\{\s*(toPlotValue|fraction)\s*\(/.test(code))
      .map(([path]) => path);

    expect(offenders).toEqual([]);
  });

  // Rule 2.
  it('has no tax field anywhere', () => {
    for (const [path, code] of analyticsEntries()) {
      for (const word of ['tax', 'cgst', 'sgst', 'gst']) {
        expect(code.toLowerCase(), `${path} mentions ${word}`).not.toMatch(
          new RegExp(`\\b${word}\\b`),
        );
      }
    }
  });

  // Rule 3. The six locked alert hues, as the Tailwind classes a chart would reach for.
  it('paints no mark in an alert colour', () => {
    const offenders = analyticsEntries()
      .filter(([, code]) =>
        /(fill|stroke|bg|text)-(critical|warning|caution|info|success|neutral)\b/.test(code),
      )
      .map(([path]) => path);

    expect(offenders).toEqual([]);
  });

  it('paints marks only from the validated series slots', () => {
    const used = new Set<string>();
    for (const [, code] of analyticsEntries()) {
      for (const match of code.matchAll(/(?:fill|stroke)-(series-\d+)/g)) {
        used.add(match[1] ?? '');
      }
    }
    // Three slots exist because three hue bands survive the alert set and the brand; a fourth is
    // not a free choice, it is a validator run. See tokens.css.
    expect([...used].sort()).toEqual(['series-1', 'series-2']);
  });

  // Rule 4.
  it('builds no second y-axis', () => {
    const offenders = analyticsEntries()
      .filter(([, code]) => /\by2\s*\(|yRight|rightAxis|secondAxis|axisRight/.test(code))
      .map(([path]) => path);

    expect(offenders).toEqual([]);
  });

  // Rule 5. Each chart takes one series; the day that changes, a legend becomes mandatory.
  it('draws one series per chart, so the heading can do the legend’s job', () => {
    for (const [path, code] of analyticsEntries()) {
      if (!path.includes('/components/charts/') || path.endsWith('plot.ts')) {
        continue;
      }
      // A multi-series chart would take a list of series. If one ever appears, this test must be
      // replaced by one asserting a legend is rendered — not deleted.
      expect(code, `${path} appears to take more than one series`).not.toMatch(
        /series\s*:\s*[A-Za-z]+\[\]|seriesList|datasets/,
      );
    }
  });
});
