import type { ReactElement, ReactNode } from 'react';

import { cn } from '@shared/cn';

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
  code,
  lines,
  children,
}: {
  tone: Tone;
  title: string;
  /** The backend's stable error code. Shown small, because it is what a user reads out on the
   *  phone when something is wrong and it is the only thing that makes a report actionable. */
  code?: string | undefined;
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
      {code !== undefined && <p className="mt-1 font-mono text-xs text-muted-foreground">{code}</p>}
    </div>
  );
}
