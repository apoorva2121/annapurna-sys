/**
 * Choosing a theme, and applying one.
 *
 * Applying is writing a handful of CSS custom properties onto `<html>`. The browser repaints them
 * itself, so nothing re-renders and no component ever learns that a theme exists.
 *
 * The default theme writes nothing — it *clears* what a previous theme wrote and lets the CSS
 * baseline in `tokens.css` show through. That is what keeps the default look defined in exactly
 * one place.
 *
 * Deliberately still missing: scheduling a festive theme by business date, and the restaurant-wide
 * default. Both belong with M02's settings screen, and both are now an insertion into
 * `resolveTheme` rather than a redesign.
 */

import { type ThemeColors, type ThemeConfig, THEMEABLE, themeById, THEMES } from './themes';

export const DEFAULT_THEME = 'light';

/** Where a per-device choice lives. Per device on purpose: one person preferring dark on their own
 *  phone is not a decision about the restaurant, and it never reaches the server. */
const STORAGE_KEY = 'restaurant-os.theme';

/** WCAG AA for body text. A theme below this is not applied. */
const MIN_CONTRAST = 4.5;

export function isThemeId(value: unknown): value is string {
  return typeof value === 'string' && themeById(value) !== undefined;
}

// ---------------------------------------------------------------- contrast

/** One channel of an `"H S% L%"` triple, converted to the 0–1 linear value WCAG needs. */
function relativeLuminance(hsl: string): number | null {
  const match = /^\s*(-?[\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*$/.exec(hsl);
  if (match === null) {
    return null;
  }
  const hue = Number(match[1]);
  const saturation = Number(match[2]) / 100;
  const lightness = Number(match[3]) / 100;

  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
  const secondary = chroma * (1 - Math.abs(((hue / 60) % 2) - 1));
  const offset = lightness - chroma / 2;
  const sector = Math.floor(((hue % 360) + 360) / 60) % 6;
  const rgb = [
    [chroma, secondary, 0],
    [secondary, chroma, 0],
    [0, chroma, secondary],
    [0, secondary, chroma],
    [secondary, 0, chroma],
    [chroma, 0, secondary],
  ][sector] as [number, number, number];

  const [red, green, blue] = rgb.map((channel) => {
    const value = channel + offset;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];

  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

export function contrastRatio(foreground: string, background: string): number | null {
  const first = relativeLuminance(foreground);
  const second = relativeLuminance(background);
  if (first === null || second === null) {
    return null;
  }
  const [lighter, darker] = first > second ? [first, second] : [second, first];
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * The pairs that decide whether a screen can be read at all.
 *
 * Checked because the failure is silent and total: a theme whose text and background are both pale
 * type-checks, lints, builds and renders an app nobody can use. Better to refuse it and say why
 * than to ship a beautiful config that blanks the staff list mid-service.
 */
const CONTRAST_PAIRS: readonly (readonly [keyof ThemeColors, keyof ThemeColors])[] = [
  ['foreground', 'background'],
  ['cardForeground', 'card'],
  ['mutedForeground', 'muted'],
  ['primaryForeground', 'primary'],
  ['brandForeground', 'brand'],
  ['accentForeground', 'accent'],
];

/** Every readability problem in a config, as sentences. Empty means it is safe to apply. */
export function validateTheme(theme: ThemeConfig, baseline: Partial<ThemeColors> = {}): string[] {
  const colors = { ...baseline, ...theme.colors };
  const problems: string[] = [];

  for (const [foregroundKey, backgroundKey] of CONTRAST_PAIRS) {
    const foreground = colors[foregroundKey];
    const background = colors[backgroundKey];
    // A pair the theme did not touch inherits the baseline, which is already known good.
    if (foreground === undefined || background === undefined) {
      continue;
    }
    const ratio = contrastRatio(foreground, background);
    if (ratio === null) {
      problems.push(`${foregroundKey} or ${backgroundKey} is not an "H S% L%" triple`);
    } else if (ratio < MIN_CONTRAST) {
      problems.push(
        `${foregroundKey} on ${backgroundKey} is ${ratio.toFixed(1)}:1, below the ${String(MIN_CONTRAST)}:1 needed to read it`,
      );
    }
  }
  return problems;
}

// ---------------------------------------------------------------- applying

/**
 * Apply a theme by id.
 *
 * Unknown ids and unreadable configs both fall back to the default rather than throwing: a stale
 * value in localStorage, or a theme removed in a later release, must never leave someone with an
 * unusable screen mid-shift.
 */
export function applyTheme(id: string, root: HTMLElement = document.documentElement): string {
  const theme = themeById(id);
  if (theme === undefined) {
    return applyTheme(DEFAULT_THEME, root);
  }

  const problems = validateTheme(theme);
  if (problems.length > 0) {
    console.warn(`Theme "${theme.id}" was not applied:\n  ${problems.join('\n  ')}`);
    return theme.id === DEFAULT_THEME ? DEFAULT_THEME : applyTheme(DEFAULT_THEME, root);
  }

  clearOverrides(root);
  writeOverrides(theme, root);
  root.dataset.theme = theme.id;
  root.style.colorScheme = theme.appearance;
  return theme.id;
}

/**
 * Remove everything a previous theme wrote.
 *
 * Always, before writing — including for the default theme, which writes nothing and is therefore
 * *defined* by this step. Without it, switching from a theme that sets a radius to one that does
 * not leaves the first theme's radius behind, and you get a half-and-half screen nobody can
 * reproduce because it depends on what was selected before.
 */
function clearOverrides(root: HTMLElement): void {
  for (const property of Object.values(THEMEABLE)) {
    root.style.removeProperty(property);
  }
  root.style.removeProperty('--radius');
  root.style.removeProperty('--theme-density');
}

/** Write only the keys in `THEMEABLE`, plus the two non-colour levers. This function is the reason
 *  a config cannot reach an alert colour or a touch target: there is no branch here that would. */
function writeOverrides(theme: ThemeConfig, root: HTMLElement): void {
  for (const [key, property] of Object.entries(THEMEABLE)) {
    const value = theme.colors?.[key as keyof ThemeColors];
    if (value !== undefined) {
      root.style.setProperty(property, value);
    }
  }
  if (theme.radius !== undefined) {
    root.style.setProperty('--radius', theme.radius);
  }
  if (theme.density !== undefined) {
    root.style.setProperty('--theme-density', String(theme.density));
  }
}

// ---------------------------------------------------------------- choosing

/** A festive theme, for a stretch of business dates. Mirrors the server's `ThemeSettings`. */
export interface ThemeWindow {
  theme: string;
  starts_on: string;
  ends_on: string;
}

export interface RestaurantTheme {
  default: string | null;
  schedule: ThemeWindow[];
}

/**
 * First match wins, and the order is the whole design:
 *
 *   1. an explicit choice on this device
 *   2. a festive window covering today's **business date**
 *   3. the restaurant's own default
 *   4. the operating system's preference
 *
 * **A person's own choice outranks the festival.** The alternative — a restaurant-wide theme that
 * overrides the device — means the manager who deliberately set dark mode for a dim back office
 * has it taken away for a week in November, by a setting someone else changed, with no way to keep
 * it. A festive theme is a nice touch; it is not worth overriding a decision a person made about
 * the screen in front of them.
 *
 * The date compared is the **business date**, not the calendar date (ADR 0004). A festival that
 * ends "on the 12th" ends when the restaurant's 12th ends, which is 5am on the 13th — otherwise the
 * theme changes under the staff mid-service, at midnight, while they are still serving the 12th.
 *
 * An id no longer in `THEMES` is skipped rather than honoured: a theme removed from the code should
 * degrade to the next rule, not leave a restaurant unable to render.
 */
export function resolveTheme(
  stored: string | null,
  prefersDark: boolean,
  restaurant?: RestaurantTheme | null,
  businessDate?: string,
): string {
  if (isThemeId(stored)) {
    return stored;
  }
  const festive = scheduledTheme(restaurant, businessDate);
  if (festive !== null) {
    return festive;
  }
  if (restaurant != null && isThemeId(restaurant.default)) {
    return restaurant.default;
  }
  return prefersDark ? 'dark' : DEFAULT_THEME;
}

/**
 * The festive theme covering a business date, if any.
 *
 * Inclusive at both ends, which is how a person reading "6 November to 12 November" understands it.
 * ISO dates compare correctly as strings, so no parsing is needed and no timezone can creep in
 * through a `Date` constructed from a date-only string.
 */
export function scheduledTheme(
  restaurant: RestaurantTheme | null | undefined,
  businessDate: string | undefined,
): string | null {
  if (restaurant == null || businessDate === undefined) {
    return null;
  }
  for (const window of restaurant.schedule) {
    if (window.starts_on <= businessDate && businessDate <= window.ends_on) {
      return isThemeId(window.theme) ? window.theme : null;
    }
  }
  return null;
}

export function readStoredTheme(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    // Private browsing, or storage disabled by policy. A preference is a convenience; losing it
    // must never stop the app rendering.
    return null;
  }
}

export function storeTheme(id: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // Same reasoning — the theme still applies for this session.
  }
}

/** Called once before React mounts, so the first paint is already correct. Applied later, a light
 *  flash followed by a dark repaint is the thing people notice most about theming. */
export function initialiseTheme(): string {
  const prefersDark =
    typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches;
  return applyTheme(resolveTheme(readStoredTheme(), prefersDark));
}

export { THEMES };
