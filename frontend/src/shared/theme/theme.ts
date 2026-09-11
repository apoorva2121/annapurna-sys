/**
 * Choosing a theme. Applying one is just an attribute — the browser repaints custom properties,
 * so nothing re-renders and no component ever learns a theme exists.
 *
 * Deliberately small. Scheduling a festive theme by business date, validating contrast and hue
 * distance, and the settings picker are all real and all deferred
 * (`docs/audit/external-review.md` §4 records the same reasoning for the audit's chunks): a
 * festive theme is already a config change once the token layer exists, which is the expensive
 * part and the part that is done.
 */

export const THEMES = ['light', 'dark'] as const;
export type ThemeId = (typeof THEMES)[number];

/** Where a per-device choice lives. Per device on purpose — one person preferring dark on their
 *  own phone is not a decision about the restaurant, and it never reaches the server. */
const STORAGE_KEY = 'restaurant-os.theme';

export function isThemeId(value: unknown): value is ThemeId {
  return typeof value === 'string' && (THEMES as readonly string[]).includes(value);
}

/**
 * Apply a theme by setting `data-theme` on `<html>`.
 *
 * Unknown ids fall back to light rather than throwing: a bad value in localStorage, or a theme
 * removed in a later release, must not leave someone with an unstyled screen mid-shift.
 */
export function applyTheme(theme: ThemeId, root: HTMLElement = document.documentElement): void {
  root.dataset.theme = isThemeId(theme) ? theme : 'light';
}

/**
 * First match wins: an explicit choice on this device, then the operating system's preference.
 *
 * The restaurant's own default and any scheduled festive theme slot in between these two when
 * M02's settings screen exists; the order is written now so adding them is an insertion rather
 * than a redesign.
 */
export function resolveTheme(stored: string | null, prefersDark: boolean): ThemeId {
  if (isThemeId(stored)) {
    return stored;
  }
  return prefersDark ? 'dark' : 'light';
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

export function storeTheme(theme: ThemeId): void {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Same reasoning: the theme still applies for this session.
  }
}

/** Called once before React mounts, so the first paint is already the right theme — a light flash
 *  before a dark repaint is the thing people notice most about theming done late. */
export function initialiseTheme(): ThemeId {
  const prefersDark =
    typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches;
  const theme = resolveTheme(readStoredTheme(), prefersDark);
  applyTheme(theme);
  return theme;
}
