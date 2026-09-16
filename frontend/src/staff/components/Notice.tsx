import type { ReactElement, ReactNode } from 'react';

import { cn } from '@shared/cn';
import { strings } from '@staff/strings';

export type Tone = 'critical' | 'success' | 'info';

// Colour never carries meaning alone (docs/ui/conventions.md): every tone pairs its colour with a
// word in the title and with role="alert" for anyone not looking at colour at all.
const TONES: Record<Tone, string> = {
  critical: 'border-critical text-critical',
  success: 'border-success text-success',
  info: 'border-info text-info',
};

export function Notice({
  tone,
  title,
  issue,
  lines,
  children,
}: {
  tone: Tone;
  title: string;
  /** The issue number a person reads out on the phone (backlog-issues B12, D11, D12). The error's
   *  code is never shown: it is for the frontend to switch on, not for a person to read. */
  issue?: number | undefined;
  /** One sentence per thing to fix — "GSTIN: Use the 15-character GSTIN…" — from `errorProps`. */
  lines?: readonly string[] | undefined;
  children?: ReactNode;
}): ReactElement {
  return (
    <div
      className={cn('rounded border p-4', TONES[tone])}
      role={tone === 'critical' ? 'alert' : 'status'}
    >
      <p className="font-semibold">{title}</p>
      {lines !== undefined && lines.length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-foreground">
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      {children !== undefined && <p className="mt-1 text-foreground">{children}</p>}
      {issue !== undefined && (
        <p className="mt-1 text-xs text-muted-foreground">{strings.errors.issue(issue)}</p>
      )}
    </div>
  );
}
