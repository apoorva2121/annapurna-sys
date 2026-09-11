/**
 * The theme catalogue. **Add a theme by adding an entry here — nothing else.**
 *
 * A theme is a small set of *overrides* on the light baseline in `tokens.css`, not a full palette.
 * That is the whole design: you say what makes this theme feel different — the background, the
 * accent, how round things are — and everything you do not mention stays exactly as it was. A
 * theme file is six lines, not sixty, and a value you forget cannot be wrong because you never
 * gave one.
 *
 * ## What a theme may change
 *
 * Surfaces, text, the brand colour, borders, corner radius, and page rhythm. Enough to change how
 * the product feels; not enough to change what it means.
 *
 * ## What a theme may never change  (docs/ui/design-system.md §2.5)
 *
 * The six alert colours, the per-surface touch targets, the z-index ladder. Red means "act now" in
 * a kitchen in November too, and a festive theme that repaints it decorative breaks the only
 * promise the kitchen display makes. Those live outside the themeable block in `tokens.css` and
 * this file cannot reach them — not by convention, by construction: `applyTheme` only ever writes
 * the keys in `THEMEABLE`.
 *
 * ## Colour format
 *
 * Bare HSL triples — `"36 45% 97%"` — because Tailwind wraps them in `hsl(… / <alpha-value>)`,
 * which is what keeps `bg-card/80` working. Hue 0–360, then saturation and lightness as
 * percentages. Lightness is the one to reach for first: it is what separates a "light" theme from
 * a "dark" one.
 */

export type ThemeColors = {
  background: string;
  foreground: string;
  card: string;
  cardForeground: string;
  popover: string;
  popoverForeground: string;
  muted: string;
  mutedForeground: string;
  primary: string;
  primaryForeground: string;
  secondary: string;
  secondaryForeground: string;
  /** The brand fill — active navigation, links, selected state. */
  brand: string;
  brandForeground: string;
  /** The soft tint behind a hovered or selected row. */
  accent: string;
  accentForeground: string;
  /** The focus ring. Keep it lighter than `brand`, or focus disappears on a dim screen. */
  ring: string;
  border: string;
  input: string;
};

export type ThemeConfig = {
  id: string;
  /** Shown to the person choosing it. */
  name: string;
  /** One line, in the picker, saying what it is for. */
  description: string;
  /**
   * Picks the browser's own light/dark behaviour — scrollbars, form controls, `color-scheme`.
   * Set `dark` for any theme whose background is darker than its text.
   */
  appearance: 'light' | 'dark';
  /** Everything omitted keeps the light baseline's value. */
  colors?: Partial<ThemeColors>;
  /** Corner roundness. The most visible single lever a theme has. Default `0.5rem`. */
  radius?: string;
  /** Page rhythm — multiplies the shell's padding and gaps. 1 is the baseline; 1.25 feels
   *  noticeably airier, 0.9 denser. Touch targets are **not** affected: those are physical. */
  density?: number;
};

/**
 * `light` carries no overrides on purpose. Choosing it *clears* everything this module wrote,
 * which means the CSS baseline is the single definition of the default look — there is no second
 * copy of it here to drift out of step.
 */
export const THEMES: readonly ThemeConfig[] = [
  {
    id: 'light',
    name: 'Steel',
    description: 'The default. Steel neutrals, ink actions, jamun for interaction.',
    appearance: 'light',
  },
  {
    id: 'dark',
    name: 'Dark',
    description: 'For a dim floor and for reconciling cash at 1am.',
    appearance: 'dark',
    colors: {
      background: '222 30% 9%',
      foreground: '210 20% 96%',
      card: '222 26% 13%',
      cardForeground: '210 20% 96%',
      popover: '222 26% 13%',
      popoverForeground: '210 20% 96%',
      muted: '222 20% 18%',
      mutedForeground: '215 18% 68%',
      // Inverted: on a dark ground the high-contrast "ink" action is the light one.
      primary: '210 20% 96%',
      primaryForeground: '222 47% 11%',
      secondary: '222 20% 18%',
      secondaryForeground: '210 20% 96%',
      // Jamun has to lift in the dark — a 32% fill on a 9% ground is barely a colour.
      brand: '322 45% 58%',
      brandForeground: '222 47% 11%',
      accent: '322 28% 20%',
      accentForeground: '322 60% 88%',
      ring: '322 55% 62%',
      border: '222 18% 24%',
      input: '222 16% 32%',
    },
  },
  {
    id: 'deepavali',
    name: 'Deepavali',
    description: 'Warm ivory and wine, with softer corners. For the festive weeks.',
    appearance: 'light',
    colors: {
      // Warm ivory rather than steel — the single change that carries most of the feeling.
      background: '36 45% 97%',
      foreground: '24 30% 12%',
      card: '0 0% 100%',
      cardForeground: '24 30% 12%',
      popover: '0 0% 100%',
      popoverForeground: '24 30% 12%',
      muted: '36 40% 94%',
      mutedForeground: '24 14% 38%',
      primary: '24 30% 12%',
      primaryForeground: '36 45% 97%',
      secondary: '36 40% 94%',
      secondaryForeground: '24 30% 12%',
      // Wine. Deliberately 35° of hue from `critical` red, so "act now" still reads as its own
      // thing rather than as decoration.
      brand: '335 58% 30%',
      brandForeground: '0 0% 100%',
      accent: '335 50% 95%',
      accentForeground: '335 58% 26%',
      ring: '335 60% 44%',
      border: '36 30% 88%',
      input: '36 24% 78%',
    },
    // Rounder and airier. Radius is the most visible lever a theme has after the background.
    radius: '0.875rem',
    density: 1.15,
  },
  {
    id: 'monsoon',
    name: 'Monsoon',
    description: 'Cool slate and deep teal, tighter and crisper.',
    appearance: 'light',
    colors: {
      background: '200 24% 97%',
      foreground: '200 40% 12%',
      card: '0 0% 100%',
      cardForeground: '200 40% 12%',
      popover: '0 0% 100%',
      popoverForeground: '200 40% 12%',
      muted: '200 26% 94%',
      mutedForeground: '200 14% 38%',
      primary: '200 40% 12%',
      primaryForeground: '200 24% 97%',
      secondary: '200 26% 94%',
      secondaryForeground: '200 40% 12%',
      // Deep teal. Far enough from `success` green (142) and `info` blue (217) that none of the
      // three starts to look like another.
      brand: '188 62% 26%',
      brandForeground: '0 0% 100%',
      accent: '188 45% 94%',
      accentForeground: '188 62% 22%',
      ring: '188 60% 38%',
      border: '200 22% 88%',
      input: '200 18% 78%',
    },
    radius: '0.25rem',
    density: 0.95,
  },
];

/** The CSS custom property each config key writes to. This map *is* the permission list: a key
 *  that is not here cannot be set by a theme, whatever a config contains. */
export const THEMEABLE: Readonly<Record<keyof ThemeColors, string>> = {
  background: '--background',
  foreground: '--foreground',
  card: '--card',
  cardForeground: '--card-foreground',
  popover: '--popover',
  popoverForeground: '--popover-foreground',
  muted: '--muted',
  mutedForeground: '--muted-foreground',
  primary: '--primary',
  primaryForeground: '--primary-foreground',
  secondary: '--secondary',
  secondaryForeground: '--secondary-foreground',
  brand: '--brand',
  brandForeground: '--brand-foreground',
  accent: '--accent',
  accentForeground: '--accent-foreground',
  ring: '--ring',
  border: '--border',
  input: '--input',
};

export function themeById(id: string): ThemeConfig | undefined {
  return THEMES.find((theme) => theme.id === id);
}
