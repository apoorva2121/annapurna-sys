// The theme layer's contract, and the one test that makes "themes are easy later" a fact instead
// of a claim.
//
// The parity test is the important one. A theme that omits a token does not fail loudly — the token
// keeps its light value, so dark text lands on a dark background and the screen is unreadable in
// exactly the conditions the dark theme exists for. Nothing else catches that: it type-checks, it
// lints, it builds, and the tests pass.

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import process from 'node:process';

import { afterEach, describe, expect, it } from 'vitest';

import { applyTheme, isThemeId, resolveTheme, THEMES } from './theme';

// Read from the project root rather than `import.meta.url`: under jsdom that is an http:// URL,
// not a file one.
const TOKENS = readFileSync(resolve(process.cwd(), 'src/shared/theme/tokens.css'), 'utf8');

/** An HSL triple — `222 47% 11%`. Colour tokens hold these; shape, type and motion tokens do not. */
const HSL_TRIPLE = /^-?[\d.]+\s+[\d.]+%\s+[\d.]+%$/;

/** Every `--token: value` pair declared inside the block that starts at `selector`. */
function declarationsUnder(selector: string): Map<string, string> {
  const start = TOKENS.indexOf(selector);
  if (start === -1) {
    throw new Error(`tokens.css declares no block for ${selector}`);
  }
  const open = TOKENS.indexOf('{', start);
  let depth = 0;
  let end = open;
  for (let i = open; i < TOKENS.length; i += 1) {
    if (TOKENS[i] === '{') depth += 1;
    if (TOKENS[i] === '}') {
      depth -= 1;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  const body = TOKENS.slice(open, end);
  return new Map(
    [...body.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)].map((match) => [
      match[1] as string,
      (match[2] as string).trim(),
    ]),
  );
}

/** Every `--token:` declared inside the block that starts at `selector`. */
function tokensDeclaredUnder(selector: string): Set<string> {
  const start = TOKENS.indexOf(selector);
  if (start === -1) {
    throw new Error(`tokens.css declares no block for ${selector}`);
  }
  const open = TOKENS.indexOf('{', start);
  let depth = 0;
  let end = open;
  for (let i = open; i < TOKENS.length; i += 1) {
    if (TOKENS[i] === '{') depth += 1;
    if (TOKENS[i] === '}') {
      depth -= 1;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  const body = TOKENS.slice(open, end);
  return new Set([...body.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((match) => match[1] as string));
}

afterEach(() => {
  delete document.documentElement.dataset.theme;
});

describe('every theme declares every colour', () => {
  // The light theme in `:root` is the contract. Only *colours* have to be re-declared: a theme
  // inheriting `--radius` or `--font-sans` is correct and intended — a dark theme has no business
  // changing the corner radius. A theme inheriting a colour is the dangerous case, because the
  // light value is by definition wrong on a dark background.
  const light = declarationsUnder(':root {');
  const lightColours = [...light].filter(([, value]) => HSL_TRIPLE.test(value)).map(([key]) => key);

  it('light declares a non-trivial set of colours, so the comparison below means something', () => {
    // Guards the guard: a parser that returned nothing would make every parity test pass.
    expect(lightColours.length).toBeGreaterThan(12);
    expect(lightColours).toContain('--background');
    expect(lightColours).toContain('--brand');
  });

  it('dark re-declares every colour, so none silently keeps its light value', () => {
    const dark = tokensDeclaredUnder("[data-theme='dark']");
    const missing = lightColours.filter((token) => !dark.has(token));

    expect(
      missing,
      `dark is missing ${missing.join(', ')} — each keeps its light value, which on a dark ` +
        'background is somewhere between wrong and unreadable',
    ).toEqual([]);
  });

  it('does not re-declare shape, type or motion, which are deliberately shared', () => {
    const dark = tokensDeclaredUnder("[data-theme='dark']");

    for (const shared of ['--radius', '--font-sans', '--duration-base']) {
      expect(dark.has(shared)).toBe(false);
    }
  });
});

describe('the locked layer', () => {
  it('is declared for every theme, not only the default', () => {
    // `:root, [data-theme]` — the alert colours and the z-index ladder apply whatever is chosen.
    const locked = tokensDeclaredUnder(':root,\n  [data-theme] {');

    expect(locked.has('--critical')).toBe(true);
    expect(locked.has('--z-offline')).toBe(true);
  });

  it('keeps the six alert colours out of the themeable block', () => {
    // If `--critical` were themeable, a festive theme could make red decorative — and red is the
    // only promise the kitchen display makes.
    const themeable = tokensDeclaredUnder(':root {');

    for (const alert of ['--critical', '--warning', '--caution', '--info', '--success']) {
      expect(themeable.has(alert)).toBe(false);
    }
  });

  it('sets a touch target for every surface', () => {
    for (const surface of ["[data-surface='waiter']", "[data-surface='kds']"]) {
      expect(tokensDeclaredUnder(surface).has('--target-min')).toBe(true);
    }
  });
});

describe('applying a theme', () => {
  it('is one attribute, so nothing has to re-render', () => {
    applyTheme('dark');

    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('falls back to light for a value that is no longer a theme', () => {
    // A stale localStorage value, or a theme dropped in a later release. An unstyled screen
    // mid-shift is worse than the wrong colours.
    applyTheme('deepavali-2019' as never);

    expect(document.documentElement.dataset.theme).toBe('light');
  });
});

describe('resolving which theme to use', () => {
  it('prefers an explicit choice on this device', () => {
    expect(resolveTheme('light', true)).toBe('light');
  });

  it('follows the operating system when nobody has chosen', () => {
    expect(resolveTheme(null, true)).toBe('dark');
    expect(resolveTheme(null, false)).toBe('light');
  });

  it('ignores a stored value that is not a theme', () => {
    expect(resolveTheme('{}', false)).toBe('light');
    expect(THEMES.every(isThemeId)).toBe(true);
  });
});
