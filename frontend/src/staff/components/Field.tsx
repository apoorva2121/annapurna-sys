import { type InputHTMLAttributes, type ReactElement, useId } from 'react';

import { cn } from '@shared/cn';

/**
 * A labelled input with its error attached.
 *
 * The label is a real `<label htmlFor>` and the error is wired through `aria-describedby`, so a
 * screen reader announces the problem with the field rather than leaving a red border to carry the
 * meaning on its own. `min-h-target` keeps it thumb-sized on whichever surface it renders on.
 */
export function Field({
  label,
  error,
  hint,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string | undefined;
  hint?: string | undefined;
}): ReactElement {
  const id = useId();
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const describedBy = [hint === undefined ? null : hintId, error === undefined ? null : errorId]
    .filter((value): value is string => value !== null)
    .join(' ');

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {hint !== undefined && (
        <p id={hintId} className="text-sm text-muted-foreground">
          {hint}
        </p>
      )}
      <input
        id={id}
        aria-invalid={error !== undefined}
        aria-describedby={describedBy === '' ? undefined : describedBy}
        className={cn(
          'min-h-target rounded-md border bg-card px-3',
          'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2',
          error === undefined ? 'border-input' : 'border-critical',
          className,
        )}
        {...rest}
      />
      {error !== undefined && (
        <p id={errorId} className="text-sm text-critical">
          {error}
        </p>
      )}
    </div>
  );
}
