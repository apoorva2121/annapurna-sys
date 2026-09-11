import type { ButtonHTMLAttributes, ReactElement } from 'react';

import { cn } from '@shared/cn';

type Variant = 'primary' | 'secondary' | 'danger';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-foreground text-background hover:opacity-90',
  secondary: 'border border-border bg-background text-foreground hover:bg-muted',
  danger: 'border border-critical text-critical hover:bg-critical hover:text-background',
};

/**
 * `min-h-12` is 48px — the waiter surface's tap-target floor (docs/ui/conventions.md). It is set
 * here rather than per-screen so no button can quietly ship smaller than a thumb.
 */
export function Button({
  variant = 'primary',
  className,
  type = 'button',
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }): ReactElement {
  return (
    <button
      type={type}
      className={cn(
        'inline-flex min-h-12 items-center justify-center rounded px-4 font-medium',
        'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2',
        'disabled:cursor-not-allowed disabled:opacity-60',
        VARIANTS[variant],
        className,
      )}
      {...rest}
    />
  );
}
