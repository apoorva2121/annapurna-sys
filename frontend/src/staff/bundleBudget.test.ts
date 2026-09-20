// M19 decision 2, as a machine check: **charts must not grow the bundle a waiter loads.**
//
// The failure this exists to prevent is invisible until somebody profiles a phone. A chart import
// added to a shared component, or a `lazy()` quietly turned into a static import during a refactor,
// costs nothing on a laptop and costs a waiter on a three-year-old Android several seconds of a
// rush. Nobody notices in review; the bundle notices immediately.
//
// Same shape as `reportDiscipline.test.ts`, `complianceDiscipline.test.ts` and
// `guestDiscipline.test.ts` — a rule that lives only in prose is a rule the next screen written in
// a hurry quietly skips.
//
// Four rules:
//
// 1. **No charting library, anywhere.** `reportDiscipline` rule 3 already says this; it is repeated
//    from the analytics side because M19 is precisely the module that would be tempted, and the
//    spec's own wording ("import a charting library only in a code-split route") is the temptation
//    written down. The charts here are hand-drawn SVG, so criterion 3 holds absolutely rather than
//    conditionally: a library that is not installed cannot reach any bundle.
// 2. **The chart components have exactly one importer**, the analytics screen. The moment a second
//    screen imports one, the charts are in the main chunk and the split is decorative.
// 3. **The analytics screen is reached only through `lazy()`.** A static import anywhere pulls it —
//    and its charts — back into the bundle every persona downloads.
// 4. **The guest bundle references none of it.** ADR 0009's boundary, checked from the source side
//    so that a change to the eslint config cannot quietly turn it off.
import { describe, expect, it } from 'vitest';

const staffSources = import.meta.glob<string>('./**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const guestSources = import.meta.glob<string>('../guest/**/*.{ts,tsx}', {
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

/** Source files that are not themselves tests — a test importing a chart is fine and proves
 *  nothing about the bundle, because tests are never bundled. */
function productionEntries(sources: Record<string, string>): [string, string][] {
  return Object.entries(sources)
    .filter(([path]) => !path.includes('.test.'))
    .map(([path, source]) => [path, withoutComments(source)]);
}

const CHART_LIBRARIES = [
  'recharts',
  'chart.js',
  'chartjs',
  'd3',
  'victory',
  'nivo',
  'echarts',
  'plotly',
  'visx',
  'apexcharts',
  'highcharts',
  'uplot',
  'lightweight-charts',
];

describe('the charts stay out of the bundle a waiter loads', () => {
  it('reads the files it checks, so an empty parse cannot pass', () => {
    expect(Object.keys(staffSources).length).toBeGreaterThanOrEqual(50);
    expect(Object.keys(guestSources).length).toBeGreaterThanOrEqual(5);
    // Guards the guard: if the chart module were renamed or deleted, rule 2 below would pass by
    // finding zero importers, which is the shape of green test that proves nothing.
    expect(
      Object.keys(staffSources).filter((path) => path.includes('/components/charts/')).length,
    ).toBeGreaterThanOrEqual(3);
  });

  // Rule 1. Named explicitly rather than by a pattern: a dependency added tomorrow with a new name
  // would slip past a regex, and these are the ones anybody would reach for.
  it('ships no charting library at all', () => {
    const manifest = Object.values(packageJson)[0] ?? '';
    expect(manifest.length).toBeGreaterThan(0);

    for (const library of CHART_LIBRARIES) {
      expect(manifest, `${library} was added to package.json`).not.toContain(`"${library}`);
    }
  });

  it('imports no charting library in any source file either', () => {
    for (const [path, code] of productionEntries(staffSources)) {
      for (const library of CHART_LIBRARIES) {
        expect(code, `${path} imports ${library}`).not.toMatch(
          new RegExp(`from\\s+['"]${library.replace('.', '\\.')}(/|['"])`),
        );
      }
    }
  });

  // Rule 2.
  it('is imported by the analytics screen and by nothing else', () => {
    const importers = productionEntries(staffSources)
      .filter(([path]) => !path.includes('/components/charts/'))
      .filter(([, code]) => /from\s+['"][^'"]*components\/charts\//.test(code))
      .map(([path]) => path);

    expect(importers).toEqual(['./screens/AnalyticsScreen.tsx']);
  });

  // Rule 3.
  it('reaches the analytics screen only through a dynamic import', () => {
    const app = withoutComments(staffSources['./App.tsx'] ?? '');
    expect(app.length, 'App.tsx was not found').toBeGreaterThan(0);

    expect(app).toMatch(/lazy\(\s*\(\)\s*=>\s*import\(['"][^'"]*AnalyticsScreen['"]\)\s*\)/);
    // A static `import AnalyticsScreen from …` would defeat the lazy one sitting beside it.
    expect(app).not.toMatch(/^import\s+[^\n]*AnalyticsScreen[^\n]*from/m);
  });

  it('is not statically imported by any other staff module', () => {
    const offenders = productionEntries(staffSources)
      .filter(([path]) => path !== './screens/AnalyticsScreen.tsx')
      .filter(([, code]) => /^import\s+[^\n]*AnalyticsScreen[^\n]*from/m.test(code))
      .map(([path]) => path);

    expect(offenders).toEqual([]);
  });

  // Rule 4.
  it('never reaches the guest bundle', () => {
    for (const [path, code] of productionEntries(guestSources)) {
      expect(code, `${path} reaches into staff code`).not.toMatch(/components\/charts|@staff\//);
      for (const library of CHART_LIBRARIES) {
        expect(code, `${path} imports ${library}`).not.toMatch(
          new RegExp(`from\\s+['"]${library.replace('.', '\\.')}(/|['"])`),
        );
      }
    }
  });
});
