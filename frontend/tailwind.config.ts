import type { Config } from 'tailwindcss';

/*
 * Tailwind reads tokens, never values. Every colour here resolves to a CSS custom property
 * declared in src/shared/theme/tokens.css, which is what lets a theme repaint the product without
 * a component re-rendering or a class changing.
 *
 * The `<alpha-value>` slot is what keeps `bg-primary/90` and `ring-ring/40` working against a
 * variable — without it, opacity utilities silently produce nothing.
 */
const withAlpha = (variable: string) => `hsl(var(${variable}) / <alpha-value>)`;

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: withAlpha('--background'),
        foreground: withAlpha('--foreground'),
        card: {
          DEFAULT: withAlpha('--card'),
          foreground: withAlpha('--card-foreground'),
        },
        popover: {
          DEFAULT: withAlpha('--popover'),
          foreground: withAlpha('--popover-foreground'),
        },
        primary: {
          DEFAULT: withAlpha('--primary'),
          foreground: withAlpha('--primary-foreground'),
        },
        secondary: {
          DEFAULT: withAlpha('--secondary'),
          foreground: withAlpha('--secondary-foreground'),
        },
        muted: {
          DEFAULT: withAlpha('--muted'),
          foreground: withAlpha('--muted-foreground'),
        },
        // shadcn's `accent` is the subtle tint used for hover and selection.
        accent: {
          DEFAULT: withAlpha('--accent'),
          foreground: withAlpha('--accent-foreground'),
        },
        // Jamun at full strength: active nav, links, selected state.
        brand: {
          DEFAULT: withAlpha('--brand'),
          foreground: withAlpha('--brand-foreground'),
        },
        destructive: {
          DEFAULT: withAlpha('--destructive'),
          foreground: withAlpha('--destructive-foreground'),
        },
        border: withAlpha('--border'),
        input: withAlpha('--input'),
        ring: withAlpha('--ring'),

        // The locked alert set. Fixed meanings on every surface (docs/ui/conventions.md); a theme
        // may not change them. `-soft` is the tinted background for a badge or a row.
        critical: { DEFAULT: withAlpha('--critical'), soft: withAlpha('--critical-soft') },
        warning: { DEFAULT: withAlpha('--warning'), soft: withAlpha('--warning-soft') },
        caution: { DEFAULT: withAlpha('--caution'), soft: withAlpha('--caution-soft') },
        info: { DEFAULT: withAlpha('--info'), soft: withAlpha('--info-soft') },
        success: { DEFAULT: withAlpha('--success'), soft: withAlpha('--success-soft') },
        neutral: { DEFAULT: withAlpha('--neutral'), soft: withAlpha('--neutral-soft') },

        // The scrim behind a modal. `bg-scrim/70` rather than shadcn's generated `bg-black/80`,
        // which is a palette colour no theme or ADR can reach.
        scrim: withAlpha('--scrim'),
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      fontFamily: {
        sans: 'var(--font-sans)',
        // Tabular figures: manager and owner surfaces right-align numbers and compare them down a
        // column, which only works if the digits are the same width.
        mono: 'var(--font-mono)',
      },
      // Page rhythm: surface density × theme density. `p-page` and `gap-page` rather than an
      // arbitrary value per screen, so nobody hand-tunes padding and the two levers compose.
      spacing: { page: 'var(--page-gap)' },
      // The minimum touch target for the current surface. `min-h-target` rather than a hard-coded
      // height means one component is correct on a phone, a laptop and a wall tablet.
      minHeight: { target: 'var(--target-min)' },
      minWidth: { target: 'var(--target-min)' },
      transitionDuration: {
        fast: 'var(--duration-fast)',
        DEFAULT: 'var(--duration-base)',
        slow: 'var(--duration-slow)',
      },
      transitionTimingFunction: { DEFAULT: 'var(--easing)' },
      // Named rungs only. A raw `z-50` in a component is a bug waiting for a second raw `z-50`.
      zIndex: {
        sticky: 'var(--z-sticky)',
        dropdown: 'var(--z-dropdown)',
        sheet: 'var(--z-sheet)',
        dialog: 'var(--z-dialog)',
        toast: 'var(--z-toast)',
        offline: 'var(--z-offline)',
      },
    },
  },
  plugins: [],
} satisfies Config;
