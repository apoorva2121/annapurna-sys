// The four rules the report screens live or die by, checked by a machine.
//
// A report is the surface where a wrong habit is least visible and most expensive: every figure
// looks authoritative, and nobody re-derives one by hand to check. So the rules that keep these
// screens honest are stated here rather than only in prose — same shape as `wasteDiscipline`,
// `brandChecklist` and `kdsReadability`, and for the same reason: a rule that lives only in a
// docstring is a rule the next report written in a hurry quietly skips.
//
// 1. **No screen does arithmetic on money.** Invariant 3. Every rupee figure arrives as a string,
//    every percentage and every comparison is computed once on the server, and a browser that
//    subtracts two of them is one rounding rule from disagreeing with the figure beside it.
// 2. **The delta is never an alert colour.** `docs/ui/conventions.md` locks six alert colours and
//    `critical` means *somebody must act now*. Revenue down against yesterday is information, not
//    an alarm; spending red on a quiet Tuesday teaches people to ignore red.
// 3. **No chart library.** The `dataviz` skill's own heuristic put every one of these on tiles and
//    tables, and a charting bundle in a PWA a waiter loads on a three-year-old Android is half a
//    megabyte spent on four numbers somebody reads in two seconds.
// 4. **The unexplained figure never names anybody.** A missed waste log and theft produce exactly
//    the same number. Measuring people is M17, which has guardrails this module does not.
import { describe, expect, it } from 'vitest';

const screens = import.meta.glob<string>('./screens/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const components = import.meta.glob<string>('./components/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const packageJson = import.meta.glob<string>('../../package.json', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

/** The five report screens plus the tile they share. */
const REPORT_SCREENS = [
  'TodayScreen',
  'SalesReportScreen',
  'VarianceReportScreen',
  'DishPerformanceScreen',
  'WasteReportScreen',
];

function reportSources(): [string, string][] {
  const all = { ...screens, ...components };
  return REPORT_SCREENS.concat(['StatTile']).map((name) => {
    const found = Object.entries(all).find(([path]) => path.endsWith(`/${name}.tsx`));
    expect(found, `${name} was not found — this test would otherwise pass vacuously`).toBeDefined();
    return [name, withoutComments(found?.[1] ?? '')];
  });
}

describe('the report screens keep their four promises', () => {
  it('reads the screens it checks, so an empty parse cannot pass', () => {
    expect(reportSources()).toHaveLength(REPORT_SCREENS.length + 1);
  });

  // Rule 1. `Number(`, `parseFloat`, and any arithmetic operator applied to a figure are all the
  // same mistake wearing different clothes.
  it('never parses a figure into a number', () => {
    const offenders = reportSources()
      .filter(([, code]) => /\bNumber\(|\bparseFloat\(|\bparseInt\(/.test(code))
      .map(([name]) => name);

    expect(offenders).toEqual([]);
  });

  it('computes no percentage of its own', () => {
    // A share or a change rendered with a `*` or a `/` beside it is a figure the server already
    // sent — recomputed, and free to disagree with the CSV.
    const offenders = reportSources()
      .filter(([, code]) => /[\w.)]\s*[*/]\s*\d|\btoFixed\(/.test(code))
      .map(([name]) => name);

    expect(offenders).toEqual([]);
  });

  // Rule 2. The tile is the only place a comparison is rendered, and it says so in ink.
  it('renders no delta in an alert colour', () => {
    const offenders = reportSources()
      .filter(([, code]) => /text-(critical|success|caution|info|warning|serious)\b/.test(code))
      .map(([name]) => name);

    expect(offenders).toEqual([]);
  });

  // Rule 3. Named explicitly rather than by a pattern: a dependency added tomorrow with a new name
  // would slip past a regex, and these are the ones anybody would reach for.
  it('ships no charting library', () => {
    const manifest = Object.values(packageJson)[0] ?? '';
    expect(manifest.length).toBeGreaterThan(0);

    for (const library of ['recharts', 'chart.js', 'd3', 'victory', 'nivo', 'echarts', 'plotly']) {
      expect(manifest).not.toContain(`"${library}`);
    }
  });

  // Rule 4. The variance screen is the one that could accuse somebody, and the words it uses were
  // chosen so it does not.
  it('never puts a person beside the unexplained figure', () => {
    const variance = reportSources().find(([name]) => name === 'VarianceReportScreen')?.[1] ?? '';

    expect(variance.length).toBeGreaterThan(0);
    for (const word of ['employee', 'staff_id', 'reported_by', 'waiter', 'blame']) {
      expect(variance).not.toContain(word);
    }
  });
});
