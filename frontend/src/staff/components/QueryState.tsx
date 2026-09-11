import type { ReactElement, ReactNode } from 'react';

import { errorProps } from './errorProps';
import { Notice } from './Notice';

/**
 * The pending and error halves of every query, in one place.
 *
 * docs/engineering-standards.md section 5 requires every one of pending, error and success to be
 * rendered explicitly — no state may fail silently. Writing that three times per screen is how one
 * of them eventually gets forgotten, so screens render `<QueryState>` and describe only success.
 *
 * The pending state is a skeleton rather than a spinner, per docs/ui/conventions.md: a block the
 * shape of the answer does not make the page jump when the answer arrives.
 */
export function QueryState({
  isPending,
  error,
  pendingLabel,
  children,
}: {
  isPending: boolean;
  error: unknown;
  pendingLabel: string;
  children: ReactNode;
}): ReactElement {
  if (isPending) {
    return (
      <div className="space-y-2" aria-busy="true" aria-live="polite">
        <span className="sr-only">{pendingLabel}</span>
        <div className="h-12 animate-pulse rounded bg-muted" />
        <div className="h-12 animate-pulse rounded bg-muted" />
        <div className="h-12 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  if (error !== null && error !== undefined) {
    return <Notice tone="critical" {...errorProps(error)} />;
  }

  return <>{children}</>;
}
