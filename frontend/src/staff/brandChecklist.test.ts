// The parts of `docs/ui/brand.md` §8 a machine can hold, checked across every staff screen.
//
// §9 step 3 rolls the brand guide across the screens built before it existed. A sweep done once is
// a sweep that decays: this is the same move B10 made for the rules that lived only in prose —
// state the rule as a test, so the next screen cannot quietly skip it.
//
// Only the mechanical lines are here. "One primary action, named for its outcome" and "phone width
// checked" are judgements a person makes; §8 still owns those.
import { describe, expect, it } from 'vitest';

const screens = import.meta.glob<string>('./screens/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const app = import.meta.glob<string>('./App.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

/** Source of every screen, excluding its tests and the gallery's own specimen file. */
function pages(): [string, string][] {
  return Object.entries(screens).filter(
    ([path]) => !path.includes('.test.') && !path.includes('.visual.'),
  );
}

/** Comments carry prose about money and colour; the rules below are about rendered output. */
function withoutComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
}

describe('brand guide §8, the lines a test can hold', () => {
  it('reads the screens it checks, so an empty parse cannot pass', () => {
    expect(pages().length).toBeGreaterThan(25);
  });

  // §8.2 — tokens only. A hex colour is the one that matters: it survives a theme switch and a
  // contrast check, and looks right on the machine that typed it.
  it('uses tokens rather than hex colours or inline style', () => {
    const offenders = pages()
      .filter(([, source]) => {
        const code = withoutComments(source);
        return /#[0-9a-fA-F]{3,8}\b/.test(code) || /style=\{\{/.test(code);
      })
      .map(([path]) => path);

    expect(offenders).toEqual([]);
  });

  // §8.6 — errors in plain language with no code. A code on screen is what the owner's defect
  // sheet opened with (D11, D12); `Notice` takes an issue number and no code at all.
  it('never puts an error code on a screen', () => {
    const offenders = pages()
      .filter(([, source]) => /\bcode=\{?["'`]?(?:[a-z_]+\.[a-z_]+)/.test(withoutComments(source)))
      .map(([path]) => path);

    expect(offenders).toEqual([]);
  });

  // §8.7 — a Back link to where the person came from. A screen reached from the header does not
  // need one; a screen reached *into*, with an id in its address, always does — that is the shape
  // of the recipe screen the owner had to force-close a tab to leave (defect sheet row 24).
  //
  // Marked with `data-back` rather than sniffed out of the label: the label is named for where it
  // goes — "Tables", "Bills", an order's own number — so matching on spelling would make this test
  // a guess. Same idiom as `data-surface` and the gallery's `data-specimen`.
  it('gives every screen reached by an id a way back that is not Save', () => {
    const source = Object.values(app)[0] ?? '';
    const detail = [...source.matchAll(/path="[^"]*:[^"]*"[\s\S]{0,400}?<([A-Z][A-Za-z]*Screen)/g)]
      .map((match) => match[1] ?? '')
      .filter((name) => name !== '');
    expect(detail.length).toBeGreaterThan(5);

    const missing = [...new Set(detail)].filter((name) => {
      const found = pages().find(([path]) => path.endsWith(`/${name}.tsx`));
      if (found === undefined) {
        return false;
      }
      return !/data-back/.test(found[1]);
    });

    expect(missing).toEqual([]);
  });
});
