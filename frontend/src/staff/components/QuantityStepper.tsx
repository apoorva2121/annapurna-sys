import type { ReactElement } from 'react';

import { Button } from '@shared/ui/button';
import { strings } from '@staff/strings';

/**
 * A count of whole things, changed one at a time: dishes on an order, portions on a credit note.
 *
 * **Two buttons and the number between them, never a text box.** A waiter holding a phone in one hand
 * can hit a 48 px "+" without looking; a numeric keyboard covers half the screen and invites "11" for
 * "1". Each button names what it changes ("One more Dal Makhani"), because "+" alone tells a screen
 * reader nothing about which of twelve rows it belongs to.
 *
 * **The limits are the caller's, and a button at its limit is disabled rather than hidden**, so the
 * row does not shift under a thumb. Quantities are counts, not money, so stepping them here is
 * ordinary integer arithmetic; the price of the new quantity still comes back from the server.
 *
 * The number is `aria-live="polite"` so a change is announced without stealing focus.
 */
export function QuantityStepper({
  value,
  min,
  max,
  label,
  disabled = false,
  onChange,
}: {
  value: number;
  min: number;
  max: number;
  /** What is being counted, for the buttons' accessible names. */
  label: string;
  disabled?: boolean;
  onChange: (next: number) => void;
}): ReactElement {
  return (
    <div className="flex items-center gap-2">
      <Button
        variant="secondary"
        size="icon"
        aria-label={strings.orders.fewer(label)}
        disabled={disabled || value <= min}
        onClick={() => {
          onChange(value - 1);
        }}
      >
        −
      </Button>
      <span className="min-w-8 text-center font-mono text-lg tabular-nums" aria-live="polite">
        {value}
      </span>
      <Button
        variant="secondary"
        size="icon"
        aria-label={strings.orders.more(label)}
        disabled={disabled || value >= max}
        onClick={() => {
          onChange(value + 1);
        }}
      >
        +
      </Button>
    </div>
  );
}
