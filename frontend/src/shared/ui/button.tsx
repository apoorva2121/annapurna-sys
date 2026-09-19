import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef } from 'react';
import type { ButtonHTMLAttributes } from 'react';

import { cn } from '@shared/cn';

/**
 * shadcn/ui's Button, adapted to this product's tokens and physical constraints.
 *
 * Three deliberate departures from the generated source:
 *
 * 1. **Sizes start at the touch target, not at 36px.** `min-h-target` reads `--target-min`, which
 *    `data-surface` sets — 44px on a laptop, 48px in a waiter's hand, 64px on a wall tablet
 *    tapped with a glove. One component, correct on all three, with no per-screen overrides.
 * 2. **No shadows.** Elevation is tonal (docs/ui/conventions.md); a shadow belongs to something
 *    that genuinely floats, which a button does not.
 * 3. **`destructive` names the action, never the container.** It is for money and deletion only.
 *
 * `asChild` renders a Link with a button's appearance. Use it whenever the thing navigates: a
 * `<Link>` nested inside a `<button>` is invalid HTML and cannot be opened in a new tab.
 *
 * **Wrapped in `forwardRef`, like every other component in this folder.** It was the only one that
 * was not, and the omission was invisible: Radix passes a ref to whatever a `DialogTrigger` or
 * `SheetTrigger` renders, and React answered with *"Function components cannot be given refs"* on
 * every page carrying one. The click still worked — that rides on event delegation — so the
 * warning printed for months and nothing looked broken. **What was broken is focus**: Radix uses
 * that ref to return focus to the trigger when the overlay closes, which is the whole keyboard
 * contract, and a busy till is exactly where people stop using a mouse.
 */
const buttonVariants = cva(
  cn(
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md',
    'min-h-target text-sm font-medium transition-colors',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
    'focus-visible:ring-offset-2 focus-visible:ring-offset-background',
    'disabled:pointer-events-none disabled:opacity-60',
    '[&_svg]:pointer-events-none [&_svg]:size-5 [&_svg]:shrink-0',
  ),
  {
    variants: {
      variant: {
        primary: 'bg-primary text-primary-foreground hover:bg-primary/90',
        secondary: 'border border-input bg-card text-foreground hover:bg-muted',
        // Jamun. For the action that *is* the brand moment on a screen, not for emphasis.
        brand: 'bg-brand text-brand-foreground hover:bg-brand/90',
        ghost: 'text-foreground hover:bg-accent hover:text-accent-foreground',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        link: 'text-brand underline-offset-4 hover:underline',
      },
      size: {
        // No `sm`. There is no touch surface on which a button smaller than the target is correct,
        // and a size that is wrong everywhere should not be offered.
        md: 'px-4 py-2',
        lg: 'px-6 py-3 text-base',
        icon: 'min-w-target px-0',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
);

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    /** Render as the child element — a router Link that should look like a button. */
    asChild?: boolean;
  };

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, asChild = false, type = 'button', ...props },
  ref,
) {
  const Component = asChild ? Slot : 'button';
  return (
    <Component
      ref={ref}
      // Defaulted rather than omitted: a <button> with no type inside a form submits it, which is
      // how a "Cancel" ends up saving.
      {...(asChild ? {} : { type })}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
});

export { buttonVariants };
