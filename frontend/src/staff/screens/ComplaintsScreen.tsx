import { type ReactElement, useState } from 'react';

import { formatINR } from '@shared/money';
import { Button } from '@shared/ui/button';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type Complaint,
  useCloseComplaint,
  useOpenComplaints,
  useResolveComplaint,
} from '@staff/api/customers';

/**
 * What is still open, and what has to be written down before it can leave.
 *
 * **Manager surface.** The list is what nobody has finished with; a closed complaint is history and
 * belongs to a report.
 *
 * **`docs/customer-experience.md`: "A logged complaint that nobody resolves is worse than no
 * system."** It is worse because it manufactures evidence that somebody was told and nothing
 * happened. So this screen has exactly one primary action — *Mark it sorted* — and it cannot be
 * pressed without saying what was done. The field is required here, in the schema, and again by a
 * check constraint, because a dropdown that can be set to Resolved with an empty box is how a
 * complaint system becomes paperwork.
 *
 * **Severity is shown as a word in a soft badge**, never as colour alone.
 */
export default function ComplaintsScreen(): ReactElement {
  const complaints = useOpenComplaints();

  return (
    <div className="flex flex-col gap-page p-page">
      <h1 className="text-2xl font-semibold">{strings.complaints.title}</h1>
      <QueryState
        isPending={complaints.isPending}
        error={complaints.error}
        pendingLabel={strings.complaints.loading}
      >
        {complaints.data === undefined ? null : complaints.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">{strings.complaints.empty}</p>
        ) : (
          <ul className="flex flex-col gap-page">
            {complaints.data.map((complaint) => (
              <Row key={complaint.id} complaint={complaint} />
            ))}
          </ul>
        )}
      </QueryState>
    </div>
  );
}

const SEVERITY_TONE = {
  low: 'bg-info-soft text-info',
  medium: 'bg-caution-soft text-caution',
  high: 'bg-warning-soft text-warning',
  critical: 'bg-critical-soft text-critical',
} as const;

function Row({ complaint }: { complaint: Complaint }): ReactElement {
  const [resolution, setResolution] = useState('');
  const resolve = useResolveComplaint();
  const close = useCloseComplaint();

  return (
    <li className="flex flex-col gap-2 border-b border-border pb-4">
      <div className="flex items-center gap-2">
        <span className="font-medium tabular-nums">
          {strings.complaints.reference(complaint.reference)}
        </span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_TONE[complaint.severity]}`}
        >
          {strings.complaints.severity[complaint.severity]}
        </span>
        <span className="text-xs text-muted-foreground">
          {strings.complaints.status[complaint.status]}
        </span>
      </div>
      <p>{complaint.description}</p>

      {complaint.status === 'resolved' ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted-foreground">{complaint.resolution}</p>
          {complaint.compensation_amount === null ? null : (
            <p className="text-sm tabular-nums">{formatINR(complaint.compensation_amount)}</p>
          )}
          <p className="text-sm text-muted-foreground">
            {/* Derived from the order ledger, never typed — and null before it can mean anything. */}
            {complaint.customer_returned === null
              ? ''
              : complaint.customer_returned
                ? strings.complaints.cameBack
                : strings.complaints.notYet}
          </p>
          <Button
            variant="ghost"
            onClick={() => { close.mutate(complaint.id); }}
            disabled={close.isPending}
          >
            {strings.complaints.close}
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <label className="text-sm font-medium" htmlFor={`resolution-${complaint.id}`}>
            {strings.complaints.resolveTitle}
          </label>
          <input
            id={`resolution-${complaint.id}`}
            className="min-h-target rounded-md border border-border bg-background px-3 text-base"
            value={resolution}
            onChange={(event) => { setResolution(event.target.value); }}
            placeholder={strings.complaints.resolutionPlaceholder}
          />
          <p className="text-xs text-muted-foreground">{strings.complaints.resolutionHint}</p>
          <Button
            onClick={() => {
              resolve.mutate({ complaintId: complaint.id, resolution });
            }}
            disabled={resolution.trim() === '' || resolve.isPending}
          >
            {strings.complaints.resolve}
          </Button>
        </div>
      )}

      {resolve.error ? <Notice tone="critical" {...errorProps(resolve.error)} /> : null}
      {close.error ? <Notice tone="critical" {...errorProps(close.error)} /> : null}
    </li>
  );
}
