// The kitchen display's physical contract, checked by a machine.
//
// `docs/ui/conventions.md` calls the KDS "the one people get wrong": base type ≥ 20px, order
// numbers ≥ 40px, high contrast only, colour never alone, no modals, no scrolling. Those are not
// style preferences — at two metres, through steam, with a glove on, they are the difference
// between a working screen and a decorative one.
//
// Stated as a test for the same reason `brandChecklist.test.ts` exists: a rule that lives only in
// prose is a rule the next screen written in a hurry quietly skips. These are the lines a machine
// can hold; "can a chef actually work from this" is the manual script's job and always will be.
import { describe, expect, it } from 'vitest';

const kds = import.meta.glob<string>('./screens/Kitchen*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

/** Source of every KDS screen, excluding tests. */
function screens(): [string, string][] {
  return Object.entries(kds).filter(([path]) => !path.includes('.test.'));
}

function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

/** Every Tailwind text size used in the file, as they appear in class names. */
function textSizes(source: string): string[] {
  // No trailing \b: it would never match `text-[2.5rem]`, because `]` is not a word character
  // and the next character is a quote. The first draft had one, which made both the 40px check and
  // the unmeasurable-size check pass while seeing nothing at all.
  return [...withoutComments(source).matchAll(/\btext-(\[[^\]]+\]|[a-z0-9]+\b)/g)]
    .map((match) => match[1] ?? '')
    .filter((size) => !COLOURS.has(size));
}

// `text-` is overloaded in Tailwind: it sets a size and also a colour. These are the colours this
// product uses, so the size check does not read `text-critical` as a font size.
const COLOURS = new Set([
  'critical',
  'warning',
  'caution',
  'info',
  'success',
  'neutral',
  'foreground',
  'background',
  'card',
  'muted',
  'primary',
  'secondary',
  'destructive',
  'accent',
  'popover',
  'ring',
  'border',
]);

// Tailwind's default scale, in pixels. Anything below 20px is too small for this surface.
const SCALE: Record<string, number> = {
  xs: 12,
  sm: 14,
  base: 16,
  lg: 18,
  xl: 20,
  '2xl': 24,
  '3xl': 30,
  '4xl': 36,
  '5xl': 48,
  '6xl': 60,
  '7xl': 72,
};

/** An arbitrary value such as `text-[2.5rem]`, in pixels; NaN if it is not one. */
function arbitraryPx(size: string): number {
  const match = /^\[(\d*\.?\d+)(rem|px)\]$/.exec(size);
  if (match === null) {
    return Number.NaN;
  }
  const value = Number(match[1]);
  return match[2] === 'rem' ? value * 16 : value;
}

function pixels(size: string): number {
  return size.startsWith('[') ? arbitraryPx(size) : (SCALE[size] ?? Number.NaN);
}

describe('the KDS is readable at two metres', () => {
  it('reads the screens it checks, so an empty parse cannot pass', () => {
    expect(screens().length).toBeGreaterThanOrEqual(2);
  });

  // §"Kitchen" — base font ≥ 20px. `text-xl` is exactly 20 and is the floor, not the aspiration.
  it('uses no type smaller than 20px', () => {
    const offenders = screens().flatMap(([path, source]) =>
      textSizes(source)
        .filter((size) => !Number.isNaN(pixels(size)) && pixels(size) < 20)
        .map((size) => `${path}: text-${size}`),
    );

    expect(offenders).toEqual([]);
  });

  // Every size used has to be one this test understands. A size it cannot measure is a size that
  // could be 11px, and a check that silently skips what it cannot parse is worse than no check.
  it('uses only type sizes this test can measure', () => {
    const unmeasurable = screens().flatMap(([path, source]) =>
      textSizes(source)
        .filter((size) => Number.isNaN(pixels(size)))
        .map((size) => `${path}: text-${size}`),
    );

    expect(unmeasurable).toEqual([]);
  });

  // §"Kitchen" — order numbers ≥ 40px. It is the thing a chef looks for from across a kitchen, and
  // the one number on the screen that has to be readable without walking over.
  it('renders the order number at 40px or more', () => {
    const tooSmall = screens().filter(([, source]) => {
      const code = withoutComments(source);
      const marked = /order_number/.test(code);
      if (!marked) {
        return false;
      }
      return !textSizes(source).some((size) => pixels(size) >= 40);
    });

    expect(tooSmall.map(([path]) => path)).toEqual([]);
  });

  // §"Kitchen" — no modals. A chef cannot dismiss a dialog with wet hands, so the ticket detail is
  // a route and the remake form is inline.
  it('opens no dialog', () => {
    const offenders = screens()
      .filter(([, source]) => /\bDialog\b|\bSheet\b|window\.confirm|window\.alert/.test(
        withoutComments(source),
      ))
      .map(([path]) => path);

    expect(offenders).toEqual([]);
  });

  // §"Kitchen" — colour never carries meaning alone, because commercial kitchens are full of
  // colour-blind men and steamed-up screens. Every state the rail colours is also a word.
  it('never says late, remake or not-live in colour alone', () => {
    const rail = screens().find(([path]) => path.endsWith('/KitchenScreen.tsx'));
    expect(rail).toBeDefined();
    const code = withoutComments(rail?.[1] ?? '');

    // The words come from `strings.kitchen`, so the screen is checked for the reference rather
    // than for the spelling — the spelling belongs in one place and this is not it.
    expect(code).toMatch(/strings\.kitchen\.late/);
    expect(code).toMatch(/strings\.kitchen\.remake/);
    expect(code).toMatch(/strings\.kitchen\.reconnecting/);
  });

  // The rail must not offer a control that cannot work. `served` is the floor's, and a button here
  // would be a 409 dressed up as an action (M08 spec decision 5).
  it('offers no way to mark a dish served', () => {
    const offenders = screens()
      .filter(([, source]) => /KotTicketStatus\.SERVED|KotLineStatus\.SERVED/.test(
        withoutComments(source),
      ))
      .map(([path]) => path);

    expect(offenders).toEqual([]);
  });

  // The surface itself: 64px targets and 1.5× density come from `[data-surface='kds']`, and a
  // screen that forgets to mount it renders at a laptop's spacing while looking fine on a laptop.
  it('mounts the kitchen surface', () => {
    const missing = screens()
      .filter(([, source]) => !/KdsSurface/.test(source))
      .map(([path]) => path);

    expect(missing).toEqual([]);
  });
});
