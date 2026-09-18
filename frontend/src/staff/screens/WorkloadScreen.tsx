import type { ReactElement } from 'react';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { type Share, useDistribution } from '@staff/api/performance';

/**
 * Who is actually carrying the load. **The primary screen of this module.**
 *
 * `docs/workload-fairness.md` frames the whole feature around a reframe, and this screen is it:
 * the owner's question is *"who is carrying the load and how do I reward them fairly?"*, and the
 * answer a restaurant usually needs is **the rota is unfair**, not *this person is bad*.
 *
 * So this is not a leaderboard and carries no points. It shows a share of the covers against a
 * share of the hours, and marks the rows where the first exceeds the second — which is a fact
 * about the roster and fixable by changing the roster.
 *
 * **No colour carries the finding.** The row that matters says so in words, because
 * `docs/ui/conventions.md` reserves the alert colours for things somebody must act on now, and
 * because a person reading this is deciding about a colleague rather than reacting to an alarm.
 *
 * **Nothing here is ranked and nothing is scored.** A person's points live on their own screen and
 * on their manager's; this screen exists precisely so that a conversation about workload does not
 * have to start with a score.
 */
export default function WorkloadScreen(): ReactElement {
  const distribution = useDistribution();

  return (
    <div className="flex flex-col gap-page">
      <h1 className="text-2xl font-semibold">{strings.performance.workloadTitle}</h1>
      <p className="text-sm text-muted-foreground">{strings.performance.workloadIntro}</p>

      <QueryState
        isPending={distribution.isPending}
        error={distribution.error}
        pendingLabel={strings.performance.loading}
      >
        {distribution.data === undefined ? null : distribution.data.lines.length === 0 ? (
          <p className="text-muted-foreground">{strings.performance.empty}</p>
        ) : (
          <>
            <p className="text-sm text-muted-foreground tabular-nums">
              {strings.performance.period(distribution.data.since, distribution.data.until)}
            </p>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{strings.performance.person}</TableHead>
                    <TableHead className="text-right">{strings.performance.hours}</TableHead>
                    <TableHead className="text-right">{strings.performance.covers}</TableHead>
                    <TableHead className="text-right">{strings.performance.assists}</TableHead>
                    <TableHead className="text-right">{strings.performance.shareOfWork}</TableHead>
                    <TableHead className="text-right">{strings.performance.shareOfHours}</TableHead>
                    <TableHead>{strings.performance.reading}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {distribution.data.lines.map((line) => (
                    <Row key={line.employee_id} line={line} />
                  ))}
                </TableBody>
              </Table>
            </div>
            <p className="text-sm text-muted-foreground">{strings.performance.workloadFooter}</p>
          </>
        )}
      </QueryState>
    </div>
  );
}

function Row({ line }: { line: Share }): ReactElement {
  return (
    <TableRow>
      {/* An id rather than a name: this screen is reached from the staff list, which has the
          names, and resolving them here would be a second lookup for a screen whose subject is
          the distribution rather than the people. */}
      <TableCell className="font-medium">{line.employee_id.slice(0, 8)}</TableCell>
      <TableCell className="text-right tabular-nums">{line.hours}</TableCell>
      <TableCell className="text-right tabular-nums">{line.covers}</TableCell>
      <TableCell className="text-right tabular-nums">{line.assists}</TableCell>
      <TableCell className="text-right tabular-nums">{percent(line.covers_share)}</TableCell>
      <TableCell className="text-right tabular-nums">{percent(line.hours_share)}</TableCell>
      {/* The finding, in words. Never a colour on its own. */}
      <TableCell className="text-sm">
        {line.carrying_more_than_their_hours ? strings.performance.carryingMore : ''}
      </TableCell>
    </TableRow>
  );
}

/**
 * `0.3125` → `31%`.
 *
 * The only arithmetic on this screen, and it is presentation rather than a figure: the share
 * itself is computed on the server from `Decimal`, so two screens cannot disagree about it.
 */
function percent(share: string): string {
  const value = Number(share);
  return Number.isFinite(value) ? `${String(Math.round(value * 100))}%` : '—';
}
