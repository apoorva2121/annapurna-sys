import { type ReactElement, useState } from 'react';

import { Button } from '@shared/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@shared/ui/select';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type Metric,
  type MyScore,
  useMyPeriods,
  useMyScore,
  useRaiseDispute,
} from '@staff/api/performance';

/**
 * A person's own figures — **the one screen every role in this product can open** (ADR 0011).
 *
 * *"A score an employee cannot see is surveillance and lowers morale; the same score, visible with
 * its inputs shown, is feedback and raises it."* Which of those two this feature becomes is decided
 * here, so three things are deliberate:
 *
 * **Sentences, not formulas.** *"You served 214 covers."* A points breakdown is not an explanation,
 * and `docs/workload-fairness.md`'s ethics review names that explicitly — visible is not the same
 * as understandable. The sentences come from the server so a future translation changes one place.
 *
 * **Every figure carries the count behind it.** Attribution is the weakest link in the whole
 * design, and a wrong attribution shows up here as a wrong *number of things* — which a person can
 * point at and dispute — rather than as an unexplained score, which they cannot.
 *
 * **There is a way to disagree.** Visibility without recourse is the shape of surveillance, so the
 * screen that shows somebody their score is also the screen where they can challenge it, and a
 * period cannot be published while that challenge is unanswered.
 *
 * **What is shown with zero weight is shown anyway.** The kitchen running late is on this screen
 * and counts for nothing, because that is what makes a low score explainable rather than an
 * accusation.
 *
 * **And the period is chosen from a list.** It used to be a text box reading *"paste the period id
 * your manager gave you"* — thirty-six hex characters spoken between two people, on the one screen
 * ADR 0011 promises to everybody. A guarantee reachable only by dictation is not a guarantee.
 */
export default function MyPerformanceScreen(): ReactElement {
  const [periodId, setPeriodId] = useState('');
  const periods = useMyPeriods();
  const score = useMyScore(periodId);

  return (
    <div className="flex flex-col gap-page">
      <h1 className="text-2xl font-semibold">{strings.performance.mineTitle}</h1>

      <QueryState
        isPending={periods.isPending}
        error={periods.error}
        pendingLabel={strings.performance.loading}
      >
        {periods.data === undefined ? null : periods.data.length === 0 ? (
          <p className="text-muted-foreground">{strings.performance.noPeriods}</p>
        ) : (
          <div className="flex max-w-sm flex-col gap-1">
            <span className="text-sm font-medium">{strings.performance.periodLabel}</span>
            <Select value={periodId} onValueChange={setPeriodId}>
              <SelectTrigger aria-label={strings.performance.periodLabel}>
                <SelectValue placeholder={strings.performance.pickAPeriod} />
              </SelectTrigger>
              <SelectContent>
                {periods.data.map((period) => (
                  <SelectItem key={period.id} value={period.id}>
                    {/* The label and the status come from the server: one phrasing, so a screen,
                        an export and a future translation cannot disagree. */}
                    {period.label}
                    {period.status === 'draft' ? ` · ${strings.performance.stillOpen}` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </QueryState>

      {periodId === '' ? (
        <p className="text-muted-foreground">{strings.performance.pickAPeriod}</p>
      ) : (
        <QueryState
          isPending={score.isPending}
          error={score.error}
          pendingLabel={strings.performance.loading}
        >
          {score.data === undefined || score.data === null ? (
            <p className="text-muted-foreground">{strings.performance.nothingYet}</p>
          ) : (
            <Score score={score.data} periodId={periodId} />
          )}
        </QueryState>
      )}
    </div>
  );
}

function Score({ score, periodId }: { score: MyScore; periodId: string }): ReactElement {
  return (
    <>
      <section className="flex flex-col gap-1 rounded border border-border p-4">
        <p className="text-sm text-muted-foreground">{strings.performance.points}</p>
        <p className="text-3xl font-semibold tabular-nums">{score.points}</p>
        <p className="text-sm text-muted-foreground">
          {strings.performance.hoursWorked(score.hours)}
        </p>
        {/* Somebody's own position is a thing to tell them about themselves. It appears nowhere
            in a list of other people — the API has no shape that could carry one. */}
        {score.rank !== null && (
          <p className="text-sm">{strings.performance.yourPlace(score.rank, score.of)}</p>
        )}
      </section>

      <ul className="flex flex-col gap-3">
        {score.metrics.map((metric) => (
          <MetricRow key={metric.key} metric={metric} />
        ))}
      </ul>

      {/* The promise, in the product. If it stops being true the sentence is a lie somebody will
          notice — which is the point of putting it on the screen rather than in a document. */}
      <p className="rounded border border-border bg-muted/40 p-4 text-sm">{score.purpose}</p>

      <Dispute periodId={periodId} employeeId={score.employee_id} />
    </>
  );
}

function MetricRow({ metric }: { metric: Metric }): ReactElement {
  return (
    <li className="flex flex-col gap-1 border-b border-border pb-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-medium">{strings.performance.metric[metric.key] ?? metric.key}</span>
        <span className="tabular-nums">{metric.value}</span>
      </div>
      {/* The sentence the server built. This is the half a person actually reads. */}
      <p className="text-sm text-muted-foreground">{metric.sentence}</p>
      {!metric.weighted && (
        // Said plainly rather than implied by a greyed-out row: a person looking at a bad number
        // needs to know it did not count against them.
        <p className="text-sm">{strings.performance.contextOnly}</p>
      )}
    </li>
  );
}

/**
 * The half of the screen the ethics review asked for.
 *
 * A challenge is raised by the person whose figures they are — the server enforces that — and it
 * blocks publication until somebody answers it in writing. Nothing here is a complaint form: it is
 * a specific statement about a specific period, attached to it.
 */
function Dispute({ periodId, employeeId }: { periodId: string; employeeId: string }): ReactElement {
  const [note, setNote] = useState('');
  const raise = useRaiseDispute();

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-lg font-semibold">{strings.performance.disputeTitle}</h2>
      <p className="text-sm text-muted-foreground">{strings.performance.disputeHint}</p>
      <Field
        label={strings.performance.disputeLabel}
        value={note}
        onChange={(event) => {
          setNote(event.target.value);
        }}
      />
      <Button
        variant="secondary"
        disabled={note.trim() === '' || raise.isPending}
        onClick={() => {
          raise.mutate(
            { periodId, employeeId, note },
            {
              onSuccess: () => {
                setNote('');
              },
            },
          );
        }}
      >
        {strings.performance.disputeSubmit}
      </Button>
      {raise.isSuccess && <Notice tone="success" title={strings.performance.disputeSent} />}
      {raise.error !== null && <Notice tone="critical" {...errorProps(raise.error)} />}
    </section>
  );
}
