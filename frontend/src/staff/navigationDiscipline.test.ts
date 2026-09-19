// The navigation is one list, partitioned. This is what keeps it that way.
//
// `reachability.test.ts` (backlog-issues B10) already refuses a route with **no** link anywhere.
// It has never had an opinion about a route with **two**, which is why eight screens sat in the
// header and on the home page at once for five modules until an owner read the screen and said so:
// *"the options that are present at the top they should not be repeated below … any option should
// not be duplicate on a screen, that is redundant."*
//
// So this file asserts what that one cannot: a screen offered in the navigation is offered in
// exactly one place, and the navigation offers nothing the router cannot serve. It replaces the
// hand maintenance that kept failing — four separate comments in the old two lists record somebody
// noticing a gap and patching one side of it.
import { describe, expect, it } from 'vitest';

import { HEADER_GROUPS, HOME_GROUPS, SERVICE, type NavEntry } from '@staff/navigation';

const routes = import.meta.glob<string>('./App.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function entries(groups: { entries: NavEntry[] }[]): NavEntry[] {
  return groups.flatMap((group) => group.entries);
}

const header = entries(HEADER_GROUPS);
const home = entries(HOME_GROUPS);

/** Every route with a fixed address, as `/path` — the same rule `reachability.test.ts` uses. */
function fixedRoutes(): string[] {
  const source = routes['./App.tsx'];
  expect(source, 'App.tsx was not found — this test would otherwise pass vacuously').toBeDefined();
  return [...(source ?? '').matchAll(/path="([^"]+)"/g)]
    .map((match) => match[1] ?? '')
    .filter((path) => path !== '*' && path !== '/login' && !path.includes(':'))
    .map((path) => (path.startsWith('/') ? path : `/${path}`))
    // The design gallery is a development-only screen and is linked conditionally.
    .filter((path) => path !== '/design');
}

describe('the navigation is one list, partitioned', () => {
  it('reads what it checks', () => {
    expect(header.length).toBeGreaterThan(15);
    expect(home.length).toBeGreaterThan(5);
    expect(fixedRoutes().length).toBeGreaterThan(20);
  });

  // The owner's finding.
  it('never puts a screen in both the header and the home page', () => {
    const inHeader = new Set(header.map((entry) => entry.to));
    const both = home.filter((entry) => inHeader.has(entry.to)).map((entry) => entry.to);

    expect(
      both.join(', '),
      'a screen is offered twice; the header and the home page are a partition',
    ).toBe('');
  });

  it('lists no screen twice within one side either', () => {
    for (const [name, side] of [
      ['header', header],
      ['home', home],
    ] as const) {
      const seen = new Set<string>();
      const repeated = side
        .map((entry) => entry.to)
        .filter((to) => {
          if (seen.has(to)) {
            return true;
          }
          seen.add(to);
          return false;
        });
      expect(repeated.join(', '), `${name} repeats a screen`).toBe('');
    }
  });

  // **There is deliberately no "every route is in the navigation" test here.** A first version had
  // one and it was wrong: `/reports/sales`, `/reports/waste`, `/reports/dishes` and
  // `/reports/variance` are reached *from* the Reports screen, and M13's comment says why — "one
  // link, because Today is the way into the other four; a header with five report links would push
  // the ones somebody uses every shift off the row". `/staff/new` and `/purchasing/orders/new` are
  // the same shape, reached from their lists.
  //
  // A screen reached from its parent is correctly absent from the navigation, and
  // `reachability.test.ts` already refuses one reached from nowhere at all. Asserting it twice,
  // with a rule that cannot see an in-screen link, would only make this file wrong.

  it('offers nothing the router cannot serve', () => {
    const known = new Set(fixedRoutes());
    const dangling = [...header, ...home]
      .map((entry) => entry.to)
      .filter((to) => !known.has(to));

    expect(dangling.join(', '), 'the navigation offers a route that does not exist').toBe('');
  });

  // The shift screens are what survive the drawer on a phone, so they have to be in the header.
  it('keeps the screens of a shift in the header', () => {
    const inHeader = new Set(header.map((entry) => entry.to));
    for (const entry of SERVICE.entries) {
      expect(inHeader.has(entry.to), `${entry.to} is not in the header`).toBe(true);
    }
  });
});
