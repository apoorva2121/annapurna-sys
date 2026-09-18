import type { ReactElement } from 'react';

import { formatINR } from '@shared/money';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { ExportButton } from '@staff/components/ExportButton';
import { QueryState } from '@staff/components/QueryState';
import { StatTile } from '@staff/components/StatTile';
import { strings } from '@staff/strings';
import { type WasteReport, useWasteReport } from '@staff/api/reports';

/**
 * What was thrown away, split by where it happened.
 *
 * **Never one number.** `docs/waste-model.md` is explicit that "this week you lost ₹31,200" is a
 * figure nobody can act on, because receiving is the store manager weighing at the gate, prep is
 * the chef and the batch size, and service is portion control. The total is the *heading*; the
 * table is the answer. The stage labels are M09's own (`strings.waste.stage`) — four stages
 * spelled twice would eventually be four stages spelled two different ways.
 *
 * **The second waste screen in the product, and deliberately so.** M09's `/waste/summary` sits
 * behind `stock.view` so the chef who logs waste can read it back; this one sits behind
 * `report.operational.view`, which an accountant holds and a chef does not. Neither role can reach
 * the other's, so collapsing them would take the report away from somebody. What this one adds is
 * the period before it and the export.
 *
 * **The share is the server's string, rendered.** Recomputing it here from the costs is how four
 * stages stop adding to a hundred (invariant 3, and criterion 14).
 */
export default function WasteReportScreen(): ReactElement {
  const report = useWasteReport();

  return (
    <div className="flex flex-col gap-page">
      <h1 className="text-2xl font-semibold">{strings.reports.wasteTitle}</h1>
      <p className="text-sm text-muted-foreground">{strings.reports.wasteIntro}</p>
      <QueryState
        isPending={report.isPending}
        error={report.error}
        pendingLabel={strings.reports.loading}
      >
        {report.data === undefined ? null : <Waste report={report.data} />}
      </QueryState>
    </div>
  );
}

function Waste({ report }: { report: WasteReport }): ReactElement {
  return (
    <>
      <p className="text-sm text-muted-foreground tabular-nums">
        {strings.reports.period(report.since, report.until)}
      </p>

      <div className="flex flex-wrap gap-4">
        <StatTile
          label={strings.reports.wasteTotal}
          value={formatINR(report.total.value)}
          comparison={report.total}
        />
      </div>

      <ExportButton report="waste" />

      {report.lines.length === 0 ? (
        <p className="text-muted-foreground">{strings.waste.summary.empty}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{strings.reports.stageHeading}</TableHead>
              <TableHead>{strings.reports.reasonHeading}</TableHead>
              <TableHead className="text-right">{strings.reports.timesHeading}</TableHead>
              <TableHead className="text-right">{strings.reports.costHeading}</TableHead>
              <TableHead className="text-right">{strings.reports.shareHeading}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {report.lines.map((line) => (
              <TableRow key={`${line.stage}-${line.reason_code}`}>
                <TableCell>{strings.waste.stage[line.stage]}</TableCell>
                <TableCell>{line.reason_name}</TableCell>
                <TableCell className="text-right tabular-nums">{line.events}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatINR(line.cost_value)}
                </TableCell>
                <TableCell className="text-right tabular-nums">{line.share_percent}%</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </>
  );
}
