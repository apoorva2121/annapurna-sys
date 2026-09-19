// Backlog-issues B10. M02, M03 and M04 each shipped a screen with a route and no link to it, reachable
// only by typing its address. HomeScreen.test pins the links each role is offered, which catches one
// disappearing, not a route added tomorrow with none. This reads the route table and every link in
// the app, and fails when a fixed-address route has no link anywhere.
import { describe, expect, it } from 'vitest';

// `.ts` as well as `.tsx` since 2026-09-19: the navigation moved out of `AppShell.tsx` into
// `navigation.ts` as data, and a glob that saw only components stopped seeing twenty-one links —
// which this test then reported as twenty-one unreachable screens. It was right to complain.
const sources = import.meta.glob<string>('./**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function source(path: string): string {
  const found = sources[path];
  if (found === undefined) {
    throw new Error(`${path} was not found`);
  }
  return found;
}

/** Every route with a fixed address, as `/path`. A route with a parameter is reached from a list. */
function fixedRoutes(): string[] {
  return [...source('./App.tsx').matchAll(/path="([^"]+)"/g)]
    .map((match) => match[1] ?? '')
    .filter((path) => path !== '*' && path !== '/login' && !path.includes(':'))
    .map((path) => (path.startsWith('/') ? path : `/${path}`));
}

/** Every fixed link target in the app's own code, tests and the route table excluded. */
function linkTargets(): Set<string> {
  const targets = new Set<string>();
  for (const [path, text] of Object.entries(sources)) {
    if (path.endsWith('.test.tsx') || path === './App.tsx') {
      continue;
    }
    for (const match of text.matchAll(/\bto(?:=|:\s*)["'`]([^"'`$]+)["'`]/g)) {
      targets.add(match[1] ?? '');
    }
  }
  return targets;
}

describe('every screen is reachable', () => {
  it('finds the routes it checks, so an empty parse cannot pass', () => {
    expect(fixedRoutes().length).toBeGreaterThan(15);
  });

  it('links every fixed-address screen from somewhere in the app', () => {
    const targets = linkTargets();

    expect(fixedRoutes().filter((route) => !targets.has(route))).toEqual([]);
  });
});
