import { type ReactElement, type ReactNode, useEffect } from 'react';

/**
 * Switches the page to the waiter surface while a waiter screen is mounted, and back when it leaves.
 *
 * `main.tsx` sets `manager` for the whole staff app, which gives 44 px targets and a desk-sized
 * density. The table map, order taking and the bill are used one-handed on a phone in a dim room, so
 * they need the waiter's 48 px targets (`docs/ui/conventions.md`). The surface is a property of the
 * screen in the hand, not of the person signed in: a manager seating a table is doing a waiter's job
 * for those thirty seconds.
 *
 * The previous value is restored rather than assumed, so leaving a waiter screen for the manager's
 * cash-up puts back exactly what was there.
 */
export function WaiterSurface({ children }: { children: ReactNode }): ReactElement {
  useEffect(() => {
    const previous = document.body.dataset.surface;
    document.body.dataset.surface = 'waiter';
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
