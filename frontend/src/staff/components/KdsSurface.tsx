import { type ReactElement, type ReactNode, useEffect } from 'react';

/**
 * Switches the page to the kitchen surface while a KDS screen is mounted, and back when it leaves.
 *
 * `[data-surface='kds']` has existed in `tokens.css` since the design system was adopted and until
 * M08 nothing set it: 64 px targets and 1.5× density, for a screen read at two metres and tapped
 * with a glove (`docs/ui/conventions.md`).
 *
 * Deliberately a second component rather than a parameter on `WaiterSurface`. The engineering
 * standards forbid an abstraction before its third occurrence, and the two differ in more than a
 * string — a waiter's surface is the screen *in a hand* and lasts thirty seconds, while this one is
 * a wall tablet nobody holds and lasts a whole service. When the third arrives, generalise then.
 *
 * The previous value is restored rather than assumed, so a manager who opens the kitchen display on
 * their tablet and goes back to the cash-up gets their own spacing back.
 */
export function KdsSurface({ children }: { children: ReactNode }): ReactElement {
  useEffect(() => {
    const previous = document.body.dataset.surface;
    document.body.dataset.surface = 'kds';
    return () => {
      if (previous === undefined) {
        delete document.body.dataset.surface;
      } else {
        document.body.dataset.surface = previous;
      }
    };
  }, []);
  return <>{children}</>;
}
