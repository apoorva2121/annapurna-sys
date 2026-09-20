// The two rules the menu screens keep after the owner's pass of 2026-09-19, checked by a machine.
//
// Same shape as `communicationDiscipline.test.ts` and `wasteDiscipline.test.ts`: a rule that lives
// only in prose is a rule the next screen written in a hurry quietly skips.
//
// 1. **A code is never printed beside a name.** Every menu screen used to render one in small
//    monospace, so a browse list read "Veg Starters STARTER_VEG" — the same thing twice, once for
//    a person and once for the database. The owner's words: *"name is okay, but the other thing
//    should not be in ui."* `/menu/codes` is the one screen that shows them, and it is exempt.
// 2. **A code is derived once, at creation, and never on rename.** It is the join key
//    `library/dishes.yaml` and every M04 recipe use, so a code that followed the name would
//    silently detach a dish from its recipe the first time somebody fixed a spelling. This is the
//    rule `codeFromName.test.ts` says it cannot test from the inside.
import { describe, expect, it } from 'vitest';

// Scoped to the menu screens deliberately. A first version globbed every screen and flagged
// `FloorPlanScreen`, which prints `table.code` — but that is the table *number*, what staff call
// out across a room ("Table 6, order 42"), not a database key. The rule is about menu objects
// whose code is a join key nobody should have to read, so the glob says so rather than the
// exemption list growing to hold every screen that has a `.code` field meaning something else.
const screens = import.meta.glob<string>('./screens/{Menu,ModifierGroups,DishCost}*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

/** The screen whose whole job is showing codes. */
const CODES_SCREEN = './screens/MenuCodesScreen.tsx';

/**
 * Screens exempt from rule 1, and the list is deliberately one entry long.
 *
 * It briefly held `DishCostScreen` too, because that screen named each ingredient in a cost
 * breakdown by its code and the API sent no name for a costed line. The exemption carried that
 * reason in writing — and writing it down is what made it obvious it should be fixed instead.
 * `CostedLine` now carries a `name` (F24), so the screen shows "chicken tikka" and the exemption
 * is gone.
 */
const EXEMPT = new Set([CODES_SCREEN]);

describe('the menu screens keep their rules', () => {
  it('reads the files it checks, so an empty parse cannot pass', () => {
    expect(Object.keys(screens).length).toBeGreaterThanOrEqual(4);
    expect(screens[CODES_SCREEN], 'the codes screen was not found').toBeDefined();
  });

  // Rule 1.
  it('prints no code beside a name, except on the page that exists for codes', () => {
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(screens)) {
      if (EXEMPT.has(path)) {
        continue;
      }
      const code = withoutComments(source);
      // `{something.code}` rendered as JSX text. Passing a code as a *prop* or in a request body
      // is fine and necessary — this is only about putting one on the screen.
      for (const match of code.matchAll(/>\s*\{\s*([A-Za-z_][\w.]*)\.code\s*\}/g)) {
        offenders.push(`${path}: ${match[1] ?? ''}.code`);
      }
    }
    expect(
      offenders.join(' | '),
      'a database code is printed beside a name; only /menu/codes may do that',
    ).toBe('');
  });

  // Rule 1, the other half: the codes screen must actually still show them, or rule 1 is being
  // satisfied by having removed the one place a person can look a code up.
  it('still shows codes on the page that exists for them', () => {
    const code = withoutComments(screens[CODES_SCREEN] ?? '');
    expect(code).toContain('row.code');
  });

  // Rule 2.
  it('derives a code only when something is created, never when it is renamed', () => {
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(screens)) {
      const code = withoutComments(source);
      if (!code.includes('suffixedCode') && !code.includes('codeFromName')) {
        continue;
      }
      // An update path is anything calling a mutation named for changing an existing thing.
      for (const match of code.matchAll(/\b(useUpdate\w*|useRename\w*)\b/g)) {
        // The generator and an update hook in the same file is not proof, but it is the only
        // signal a static check has — and the files are small enough that it is worth the noise.
        offenders.push(`${path}: ${match[1] ?? ''} sits beside a code generator`);
      }
    }
    expect(
      offenders.join(' | '),
      'a screen both updates a record and derives a code — a rename must never regenerate one',
    ).toBe('');
  });
});
