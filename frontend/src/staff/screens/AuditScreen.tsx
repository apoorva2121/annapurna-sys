import { type ReactElement, useState } from 'react';

import { Field } from '@staff/components/Field';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { type AuditEntry, type AuditFilters, useAuditTrail } from '@staff/api/audit';

/**
 * What happened, who did it, and what the value was before.
 *
 * **Every row is a sentence.** *"Priya repriced a dish — price 480.00 → 520.00."* A JSON blob on a
 * screen is a log, not a record, and the person who opens this is already suspicious about
 * something: making them read `{"price": "520.00"}` to find out is how a record stops being used.
 * The raw values are one tap away underneath, for the case where the sentence is not enough.
 *
 * **Three filters, and no search box.** Entity, actor and date range are the three ways somebody
 * actually arrives — *what happened to this order*, *what did this person do*, *what happened on
 * Tuesday*. A free-text search over old values would be a second copy of everything in the product,
 * sitting outside every retention story; M11 refused the same thing for messages.
 *
 * **A manager never reaches this screen**, and not because it is hidden: the route refuses and the
 * navigation does not draw the link. The P1 design gives `audit.view` to the owner, the
 * administrator and the accountant, because the person who runs the floor is frequently the subject
 * of the record.
 */
export default function AuditScreen(): ReactElement {
  const [filters, setFilters] = useState<AuditFilters>({});
  const trail = useAuditTrail(filters);

  return (
    <div className="flex flex-col gap-page">
      <h1 className="text-2xl font-semibold">{strings.audit.title}</h1>
      <p className="text-sm text-muted-foreground">{strings.audit.intro}</p>

      <Filters filters={filters} onChange={setFilters} />

      <QueryState
        isPending={trail.isPending}
        error={trail.error}
        pendingLabel={strings.audit.loading}
      >
        {trail.data === undefined ? null : trail.data.items.length === 0 ? (
          <p className="text-muted-foreground">{strings.audit.empty}</p>
        ) : (
          <ol className="flex flex-col">
            {trail.data.items.map((entry) => (
              <Row key={entry.id} entry={entry} />
            ))}
          </ol>
        )}
      </QueryState>
    </div>
  );
}

/** The three ways in. Its own component so the screen stays inside the complexity budget. */
function Filters({
  filters,
  onChange,
}: {
  filters: AuditFilters;
  onChange: (next: AuditFilters) => void;
}): ReactElement {
  return (
    <div className="flex flex-wrap gap-4">
      <Field
        label={strings.audit.entityLabel}
        hint={strings.audit.entityHint}
        value={filters.entityType ?? ''}
        onChange={(event) => {
          onChange({ ...filters, entityType: event.target.value });
        }}
      />
      <Field
        label={strings.audit.sinceLabel}
        type="date"
        value={filters.since ?? ''}
        onChange={(event) => {
          onChange({ ...filters, since: event.target.value });
        }}
      />
      <Field
        label={strings.audit.untilLabel}
        type="date"
        value={filters.until ?? ''}
        onChange={(event) => {
          onChange({ ...filters, until: event.target.value });
        }}
      />
    </div>
  );
}

function Row({ entry }: { entry: AuditEntry }): ReactElement {
  const [open, setOpen] = useState(false);

  return (
    <li className="flex flex-col gap-1 border-b border-border py-3">
      <p>{entry.sentence}</p>
      <p className="text-xs text-muted-foreground tabular-nums">
        {new Date(entry.occurred_at).toLocaleString()} · {entry.action}
      </p>
      {/* The why, when the act had one — a waiter handover, an attendance correction. It is the
          half a person actually reads, so it is not hidden behind the toggle. */}
      {entry.reason !== null && (
        <p className="text-sm">{strings.audit.reason(entry.reason)}</p>
      )}
      <button
        type="button"
        className="min-h-target self-start text-sm underline underline-offset-4"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
        }}
      >
        {open ? strings.audit.hideValues : strings.audit.showValues}
      </button>
      {open && <Values entry={entry} />}
    </li>
  );
}

/** The raw before and after. Deliberately plain: this is the fallback when words were not enough. */
function Values({ entry }: { entry: AuditEntry }): ReactElement {
  return (
    <dl className="grid grid-cols-[auto_1fr_1fr] gap-x-4 gap-y-1 rounded bg-muted/40 p-3 text-sm">
      <dt className="font-medium">{strings.audit.field}</dt>
      <dd className="font-medium">{strings.audit.before}</dd>
      <dd className="font-medium">{strings.audit.after}</dd>
      {[...new Set([...Object.keys(entry.old_value ?? {}), ...Object.keys(entry.new_value ?? {})])].map(
        (field) => (
          <FieldRow key={field} field={field} entry={entry} />
        ),
      )}
    </dl>
  );
}

function FieldRow({ field, entry }: { field: string; entry: AuditEntry }): ReactElement {
  return (
    <>
      <dt className="text-muted-foreground">{field.replaceAll('_', ' ')}</dt>
      <dd className="tabular-nums">{render(entry.old_value?.[field])}</dd>
      <dd className="tabular-nums">{render(entry.new_value?.[field])}</dd>
    </>
  );
}

/**
 * One stored value, readable.
 *
 * `old_value` and `new_value` are JSONB, so a field can legitimately hold a list or an object —
 * the roles somebody was given, the lines of a credit note. `String()` on one of those renders
 * "[object Object]", which is the least useful thing a record could say at the moment somebody
 * most needs it.
 */
function render(value: unknown): string {
  if (value === null || value === undefined) {
    return '—';
  }
  // Money arrives as a string and stays one all the way to the screen (invariant 3): nothing here
  // parses one, and nothing formats one either — an audit row shows the value that was stored.
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return JSON.stringify(value);
}
