import type { ReactElement } from 'react';

import { formatINR } from '@shared/money';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { type WastageSummary, type WastageSummaryLine, useWastageSummary } from '@staff/api/waste';

/**
 * What was lost, by stage and then by reason.
 *
 * **Never one number.** `docs/waste-model.md` is explicit: "This week you lost ₹31,200" is a
 * number nobody can act on until it is split, because each stage has a different owner and a
 * different fix — receiving is the store manager weighing at the gate, prep is the chef and the
 * batch size, service is the manager and portion control. The total is shown, but it is the
 * *heading*, not the answer.
 *
 * **Manager surface, and dense on purpose** (`docs/ui/conventions.md`): a table rather than cards,
 * numbers right-aligned with tabular figures, and every row carrying its share so the eye finds
 * the biggest line without arithmetic.
 *
 * **Every figure here is the server's.** The rupee values arrive as strings and are formatted, not
 * summed; the shares are computed on the server from `Decimal` precisely so they add to a hundred
 * (CLAUDE.md invariant 3). Nothing on this screen adds two numbers together.
 */
export default function WasteSummaryScreen(): ReactElement {
  const summary = useWastageSummary();

  return (
    <div className="flex flex-col gap-page p-page">
      <h1 className="text-2xl font-semibold">{strings.waste.summary.title}</h1>
      <QueryState
        isPending={summary.isPending}
        error={summary.error}
        pendingLabel={strings.waste.summary.loading}
      >
        {summary.data === undefined ? null : <Report summary={summary.data} />}
      </QueryState>
    </div>
  );
}

function Report({ summary }: { summary: WastageSummary }): ReactElement {
  if (summary.lines.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-muted-foreground">
          {strings.waste.summary.range(summary.since, summary.until)}
        </p>
        {/* An empty state that says what will appear and how, never a bare "No data". */}
        <p>{strings.waste.summary.empty}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-page">
      <header className="flex flex-col gap-1">
        <p className="text-sm text-muted-foreground">
          {strings.waste.summary.range(summary.since, summary.until)}
        </p>
        <p className="text-sm text-muted-foreground">{strings.waste.summary.total}</p>
        <p className="text-3xl font-semibold tabular-nums">{formatINR(summary.total_cost)}</p>
        <p className="text-sm text-muted-foreground">{strings.waste.summary.hint}</p>
      </header>

      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-border text-sm text-muted-foreground">
            <th className="py-2 font-medium">{strings.waste.summary.stageHeading}</th>
            <th className="py-2 font-medium">{strings.waste.summary.reasonHeading}</th>
            <th className="py-2 text-right font-medium">{strings.waste.summary.timesHeading}</th>
            <th className="py-2 text-right font-medium">{strings.waste.summary.costHeading}</th>
            <th className="py-2 text-right font-medium">{strings.waste.summary.shareHeading}</th>
          </tr>
        </thead>
        <tbody>
          {summary.lines.map((line) => (
            <Row key={`${line.stage}-${line.reason_code}`} line={line} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Row({ line }: { line: WastageSummaryLine }): ReactElement {
  return (
    <tr className="border-b border-border">
      <td className="py-2">{strings.waste.stage[line.stage]}</td>
      <td className="py-2">{line.reason_name}</td>
      <td className="py-2 text-right tabular-nums">{line.events}</td>
      <td className="py-2 text-right tabular-nums">{formatINR(line.cost_value)}</td>
      {/* A string from the server, rendered. Not recomputed here — that is how four stages stop
          adding to a hundred. */}
      <td className="py-2 text-right tabular-nums">{line.share_percent}%</td>
    </tr>
  );
}
