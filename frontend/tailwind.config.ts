import type { Config } from 'tailwindcss';

// The six semantic colours are fixed across all four surfaces (docs/ui/conventions.md, vision §28).
// `critical` means someone must act now — it is never a decorative accent. Colour never carries
// meaning alone; pair it with text and position, because kitchens are steamy and colour-blindness
// is common.
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        critical: 'hsl(var(--critical))',
        warning: 'hsl(var(--warning))',
        caution: 'hsl(var(--caution))',
        info: 'hsl(var(--info))',
        success: 'hsl(var(--success))',
        neutral: 'hsl(var(--neutral))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        border: 'hsl(var(--border))',
        muted: 'hsl(var(--muted))',
        'muted-foreground': 'hsl(var(--muted-foreground))',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        // Tabular figures: manager and owner surfaces right-align numbers and compare them
        // down a column, which only works if the digits are the same width.
        mono: ['ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config;
