// The theme catalogue's contract.
//
// Two properties matter and neither is visible by reading a config:
//
//   1. A theme that omits a colour inherits the baseline's. In a dark theme that means dark text on
//      a dark background — and it type-checks, lints, builds and passes every other test.
//   2. A theme whose values are individually reasonable can still be unreadable in combination.
//
// So parity is checked against the light baseline parsed out of tokens.css, and contrast is
// computed for every shipped theme. The point is that adding a theme stays a six-line config while
// the two ways that config can be silently wrong are both caught.

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import process from 'node:process';

import { afterEach, describe, expect, it } from 'vitest';

import {
  applyTheme,
  contrastRatio,
  DEFAULT_THEME,
  isThemeId,
  resolveTheme,
  validateTheme,
} from './theme';
import { THEMEABLE, THEMES, type ThemeColors, themeById } from './themes';

// Read from the project root: under jsdom `import.meta.url` is an http:// URL, not a file one.
const TOKENS = readFileSync(resolve(process.cwd(), 'src/shared/theme/tokens.css'), 'utf8');

/** The `--token: value` pairs declared in the block that starts at `selector`. */
function declarationsUnder(selector: string): Map<string, string> {
  const start = TOKENS.indexOf(selector);
  if (start === -1) {
    throw new Error(`tokens.css declares no block for ${selector}`);
  }
  const open = TOKENS.indexOf('{', start);
  let depth = 0;
  let end = open;
  for (let index = open; index < TOKENS.length; index += 1) {
    if (TOKENS[index] === '{') depth += 1;
    if (TOKENS[index] === '}') {
      depth -= 1;
      if (depth === 0) {
        end = index;
        break;
      }
    }
  }
  return new Map(
    [...TOKENS.slice(open, end).matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)].map((match) => [
      match[1] as string,
      (match[2] as string).trim(),
    ]),
  );
}

const HSL_TRIPLE = /^-?[\d.]+\s+[\d.]+%\s+[\d.]+%$/;
const BASELINE = declarationsUnder(':root {');

/** The light baseline as a config-shaped object, so a theme can be validated against what it
 *  actually inherits rather than against nothing. */
const BASELINE_COLORS = Object.fromEntries(
  Object.entries(THEMEABLE)
    .map(([key, property]) => [key, BASELINE.get(property)])
    .filter(([, value]) => value !== undefined),
) as Partial<ThemeColors>;

afterEach(() => {
  document.documentElement.removeAttribute('style');
  delete document.documentElement.dataset.theme;
});

describe('the baseline', () => {
  it('declares every themeable colour, so a theme can safely omit any of them', () => {
    // Guards the guard: if this parsed nothing, every parity test below would vacuously pass.
    const missing = Object.entries(THEMEABLE)
      .filter(([, property]) => !BASELINE.has(property))
      .map(([key]) => key);

    expect(missing, `tokens.css :root is missing ${missing.join(', ')}`).toEqual([]);
  });

  it('keeps the locked layer out of the themeable set', () => {
    // If `--critical` were themeable, a festive theme could repaint "act now" as decoration.
    for (const locked of ['--critical', '--warning', '--success', '--z-offline', '--target-min']) {
      expect(Object.values(THEMEABLE)).not.toContain(locked);
    }
  });
});

describe.each(THEMES.filter((theme) => theme.id !== DEFAULT_THEME))('theme "$id"', (theme) => {
  it('declares every colour, or deliberately inherits a readable one', () => {
    // A theme need not set everything — but whatever it leaves out it inherits, and that
    // combination is what the contrast check below is run against.
    const problems = validateTheme(theme, BASELINE_COLORS);

    expect(problems, `${theme.id}: ${problems.join('; ')}`).toEqual([]);
  });

  it('uses HSL triples, not hex or a colour name', () => {
    for (const [key, value] of Object.entries(theme.colors ?? {})) {
      expect(HSL_TRIPLE.test(value), `${key} is "${value}", not "H S% L%"`).toBe(true);
    }
  });

  it('has a name and a description, because a picker shows both', () => {
    expect(theme.name.length).toBeGreaterThan(0);
    expect(theme.description.length).toBeGreaterThan(0);
  });
});

describe('contrast', () => {
  it('computes a known ratio correctly', () => {
    // Black on white is 21:1 — the anchor that proves the maths, not the themes.
    expect(contrastRatio('0 0% 0%', '0 0% 100%')).toBeCloseTo(21, 0);
  });

  it('refuses a theme nobody could read', () => {
    const problems = validateTheme({
      id: 'unreadable',
      name: 'Unreadable',
      description: 'pale text on a pale ground',
      appearance: 'light',
      colors: { foreground: '0 0% 88%', background: '0 0% 96%' },
    });

    expect(problems.join(' ')).toContain('below the 4.5:1');
  });
});

describe('applying a theme', () => {
  it('writes the overrides a theme declares', () => {
    applyTheme('deepavali');

    expect(document.documentElement.dataset.theme).toBe('deepavali');
    expect(document.documentElement.style.getPropertyValue('--background')).toBe('36 45% 97%');
    expect(document.documentElement.style.getPropertyValue('--radius')).toBe('0.875rem');
  });

  it('clears the previous theme, so no value survives a switch', () => {
    // The failure this prevents is a half-and-half screen: deepavali's radius left behind under
    // monsoon because monsoon happened not to set one.
    applyTheme('deepavali');
    applyTheme('light');

    expect(document.documentElement.style.getPropertyValue('--background')).toBe('');
    expect(document.documentElement.style.getPropertyValue('--radius')).toBe('');
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('never writes a token outside the themeable set', () => {
    applyTheme('deepavali');
    const written = document.documentElement.getAttribute('style') ?? '';

    for (const locked of ['--critical', '--warning', '--z-dialog', '--target-min', '--density:']) {
      expect(written).not.toContain(locked);
    }
  });

  it('falls back to the default for a theme that no longer exists', () => {
    // A stale localStorage value, or a festive theme dropped after the season.
    expect(applyTheme('deepavali-2019')).toBe(DEFAULT_THEME);
    expect(document.documentElement.dataset.theme).toBe(DEFAULT_THEME);
  });
});

describe('choosing a theme', () => {
  it('prefers an explicit choice on this device', () => {
    expect(resolveTheme('monsoon', true)).toBe('monsoon');
  });

  it('follows the operating system when nobody has chosen', () => {
    expect(resolveTheme(null, true)).toBe('dark');
    expect(resolveTheme(null, false)).toBe(DEFAULT_THEME);
  });

  it('ignores a stored value that is not a theme', () => {
    expect(resolveTheme('{}', false)).toBe(DEFAULT_THEME);
    expect(isThemeId('monsoon')).toBe(true);
    expect(isThemeId('nope')).toBe(false);
    expect(themeById('nope')).toBeUndefined();
  });
});
