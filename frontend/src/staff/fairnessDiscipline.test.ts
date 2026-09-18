// The rules that decide whether M17 raises morale or destroys it, checked by a machine.
//
// `docs/workload-fairness.md` opens with the sentence this file exists for: **a measurement system
// aimed at morale can destroy morale if built carelessly.** The backend holds most of the
// guardrails — the freeze, the weight rule, the dispute that blocks a publish — because they are
// properties of the data. Four of them are properties of the *screens*, and a screen can be
// rewritten by somebody who has not read the document:
//
// 1. **No screen computes a score.** Every figure, share and sentence arrives finished. A browser
//    recomputing somebody's points would be a second implementation of the thing that decides what
//    people are paid, free to disagree with the one that paid them.
// 2. **`performance.view.own` is never checked.** ADR 0011 makes it a structural guarantee held by
//    every role; a guard on it would imply it could be absent, which is the opposite of the
//    decision.
// 3. **The workload screen carries no points and no rank.** It exists so a conversation about
//    workload does not have to start with a score.
// 4. **The finding is never carried by colour alone.** `docs/ui/conventions.md` rule 5, and here
//    it matters more than usual: the reader is deciding about a colleague, not reacting to an
//    alarm.
import { describe, expect, it } from 'vitest';

const screens = import.meta.glob<string>('./screens/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const api = import.meta.glob<string>('./api/performance.ts', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

function screen(name: string): string {
  const found = Object.entries(screens).find(([path]) => path.endsWith(`/${name}.tsx`));
  expect(found, `${name} was not found — this test would otherwise pass vacuously`).toBeDefined();
  return withoutComments(found?.[1] ?? '');
}

describe('the fairness screens keep their four promises', () => {
  it('reads the screens it checks, so an empty parse cannot pass', () => {
    expect(screen('WorkloadScreen').length).toBeGreaterThan(500);
    expect(screen('MyPerformanceScreen').length).toBeGreaterThan(500);
  });

  // Rule 1. The one arithmetic allowed is turning a share into a percentage for display, which is
  // presentation rather than a figure — the share itself is computed on the server from Decimal.
  it('computes no score of its own', () => {
    for (const name of ['WorkloadScreen', 'MyPerformanceScreen']) {
      const code = screen(name);
      expect(code, `${name} multiplies weights`).not.toMatch(/weight\s*\*/);
      expect(code, `${name} sums points`).not.toMatch(/points\s*[+*]/);
      expect(code, `${name} parses points`).not.toMatch(/Number\(\s*\w*[Pp]oints/);
    }
  });

  // Rule 2. Named explicitly: the string is what a guard would have to contain.
  it('never checks whether somebody may see their own figures', () => {
    const offenders = Object.entries(screens)
      .filter(([, source]) => withoutComments(source).includes('PERFORMANCE_VIEW_OWN'))
      .map(([path]) => path);

    expect(offenders).toEqual([]);
  });

  // Rule 3. The workload screen is the module's primary screen precisely because it is not a
  // leaderboard; a points column would make it one.
  it('shows no points and no rank on the workload screen', () => {
    const code = screen('WorkloadScreen');

    expect(code).not.toContain('points');
    expect(code).not.toContain('rank');
  });

  // Rule 4. The row that matters says so in words.
  it('never carries the finding in colour alone', () => {
    const code = screen('WorkloadScreen');

    expect(code).toContain('carryingMore');
    expect(code).not.toMatch(/text-(critical|success|caution|serious)\b/);
  });

  // And the shape that makes rule 3 impossible to undo by accident: the client type for a team
  // row has no rank, because the server's schema has none.
  it('has no client type that can hold a ranked list of other people', () => {
    const source = withoutComments(Object.values(api)[0] ?? '');
    const teamLine = source.slice(source.indexOf('export type TeamLine'), source.indexOf('export type Team ='));

    expect(teamLine.length).toBeGreaterThan(0);
    expect(teamLine).not.toContain('rank');
  });
});
