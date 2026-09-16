// The rules the guest app lives or dies by, checked by a machine.
//
// Same shape as `brandChecklist.test.ts`, `kdsReadability.test.ts` and `wasteDiscipline.test.ts`:
// a rule that lives only in prose is a rule the next screen written in a hurry quietly skips. This
// surface is the one where that costs the most — it is on a stranger's phone, over a network nobody
// controls, and nobody from the restaurant is standing beside them to explain it.
//
// Three rules, and each is a sentence from a document rather than a preference:
//
// 1. **No consent box is ever pre-ticked.** `docs/compliance-rules.md` §B2. A box somebody did not
//    tick is not consent, and a `defaultChecked` on this screen would silently make every guest
//    appear to have agreed to everything.
// 2. **No staff code reaches this bundle.** ADR 0009. eslint enforces the import boundary; this
//    checks the rule from the other side, over the source, so a change to the eslint config cannot
//    quietly turn it off.
// 3. **Three questions, and never a fourth.** `docs/customer-experience.md`: "every extra question
//    halves completion." A fourth rating here is the difference between a module that collects
//    something and one that collects nothing.
import { describe, expect, it } from 'vitest';

import { CONSENT_CHOICES } from './consentNotice';

const sources = import.meta.glob<string>('./**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
});

function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

function file(name: string): string {
  const found = Object.entries(sources).find(([path]) => path.endsWith(name));
  expect(found, `${name} was not found — this test would otherwise pass vacuously`).toBeDefined();
  return withoutComments(found?.[1] ?? '');
}

describe('the guest bundle keeps its promises', () => {
  it('reads the files it checks, so an empty parse cannot pass', () => {
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(6);
  });

  // Rule 1.
  it('pre-ticks no consent box anywhere in the bundle', () => {
    for (const [path, source] of Object.entries(sources)) {
      const code = withoutComments(source);
      expect(code, `${path} pre-ticks a control`).not.toMatch(/defaultChecked/);
      expect(code, `${path} forces a control checked`).not.toMatch(/checked=\{true\}/);
    }
  });

  it('offers each purpose separately rather than one blanket tick', () => {
    // §B2's purpose limitation: a phone number collected for a bill is not marketing consent, so
    // there is no single control that grants more than one thing.
    expect(CONSENT_CHOICES.length).toBeGreaterThanOrEqual(2);
    expect(new Set(CONSENT_CHOICES.map((choice) => choice.purpose)).size).toBe(
      CONSENT_CHOICES.length,
    );
  });

  // Rule 2. ADR 0009, checked over the source as well as by the eslint boundary.
  it('imports no staff code, anywhere', () => {
    for (const [path, source] of Object.entries(sources)) {
      const code = withoutComments(source);
      expect(code, `${path} imports staff code`).not.toMatch(/@staff\//);
      expect(code, `${path} reaches into the staff tree`).not.toMatch(/\.\.\/staff\//);
    }
  });

  it('ships none of the staff session machinery', () => {
    // `shared/api.ts` carries a refresh cookie, a cross-tab lock and a session-expiry handler. A
    // guest has none of those, and importing the staff client to get three GETs would drag all of
    // it into a bundle that opens on a stranger's phone.
    const client = file('/api.ts');

    expect(client).not.toMatch(/@shared\/api/);
    expect(client).toContain('/api/v1/guest');
  });

  // Rule 3.
  it('asks three questions and no more', () => {
    const screen = file('screens/FeedbackScreen.tsx');
    const ratings = [...screen.matchAll(/<Rating\b/g)];

    // Food and service are ratings; would-you-return is a yes/no. A third `<Rating` would be the
    // fourth question.
    expect(ratings).toHaveLength(2);
    expect(screen).toContain('wouldReturn');
    expect(screen).not.toMatch(/cleanliness/);
  });

  it('can be sent with no phone number at all', () => {
    // Anonymous is the normal path, not a degraded one. The button is disabled only when nothing
    // was rated — never because a number is missing.
    const screen = file('screens/FeedbackScreen.tsx');

    expect(screen).toContain('disabled={nothingChosen || sending}');
    expect(screen).not.toMatch(/phone === ''\s*\|\|\s*sending/);
  });

  // The menu's one control, from `docs/ui/brand.md` §7.1.
  it('offers exactly one filter on the menu, and it is veg-only', () => {
    const screen = file('screens/MenuScreen.tsx');
    const checkboxes = [...screen.matchAll(/type="checkbox"/g)];

    expect(checkboxes).toHaveLength(1);
    expect(screen).toContain('vegOnly');
  });

  it('marks every dish with its food type, in a word as well as a shape', () => {
    const screen = file('screens/MenuScreen.tsx');

    expect(screen).toContain('FoodTypeMark');
    // The word, for a screen-reader and for anybody who does not read the shape.
    expect(screen).toContain('aria-label={strings.menu.foodType[type]}');
  });

  // Invariant 3, on the surface where a wrong total starts an argument at a table.
  it('does no arithmetic on a rupee amount', () => {
    for (const name of ['screens/BillScreen.tsx', 'screens/MenuScreen.tsx']) {
      const code = file(name);
      expect(code, `${name} sums amounts`).not.toMatch(/reduce\(/);
      expect(code, `${name} parses an amount`).not.toMatch(/parseFloat\(/);
      expect(code, `${name} coerces an amount`).not.toMatch(/Number\(/);
    }
  });

  it('keeps every guest-facing word in the strings file', () => {
    // English only in month 1, in one place, so Hindi and Marathi are a data change rather than a
    // sweep through every screen. The consent notice is the exception and is versioned separately.
    const screen = file('screens/BillScreen.tsx');

    expect(screen).toContain('strings.bill');
    expect(screen).not.toMatch(/>[A-Z][a-z]+ [a-z]+</);
  });
});
