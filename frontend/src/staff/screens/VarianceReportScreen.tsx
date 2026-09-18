import type { ReactElement } from 'react';

import { formatINR } from '@shared/money';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { ExportButton } from '@staff/components/ExportButton';
import { QueryState } from '@staff/components/QueryState';
import { StatTile } from '@staff/components/StatTile';
import { strings } from '@staff/strings';
import { type VarianceLine, type VarianceReport, useVarianceReport } from '@staff/api/reports';

/**
 * What the recipes say was used, against what the shelf says was used.
 *
 * **The screen this product exists for.** The last column is the only line in the whole
 * application that says *this much of your food went somewhere nobody can account for* — and the
 * wording of that column was chosen more carefully than anything else on the screen.
 *
 * **It never names a person, and it says what it is.** An unexplained figure is a question to ask,
 * not an accusation: a cook who forgot to log a dropped tray produces exactly the same number as
 * theft, and a report that implied otherwise would be wrong about most restaurants most weeks.
 * Measuring people is M17, which has guardrails this module does not.
 *
 * **The two bases sit in separate columns and are never added** (invariant 7). The gap between
 * them *is* the report; a single "consumption" figure would destroy the only insight here.
 */
export default function VarianceReportScreen(): ReactElement {
  const report = useVarianceReport();

  return (
    <div className="flex flex-col gap-page">
      <h1 className="text-2xl font-semibold">{strings.reports.varianceTitle}</h1>
      <p className="text-sm text-muted-foreground">{strings.reports.varianceIntro}</p>
      <QueryState
        isPending={report.isPending}
        error={report.error}
        pendingLabel={strings.reports.loading}
      >
        {report.data === undefined ? null : <Variance report={report.data} />}
      </QueryState>
    </div>
  );
}

function Variance({ report }: { report: VarianceReport }): ReactElement {
  return (
    <>
      <p className="text-sm text-muted-foreground tabular-nums">
        {strings.reports.period(report.since, report.until)}
      </p>

      <div className="flex flex-wrap gap-4">
        <StatTile label={strings.reports.variance} value={formatINR(report.variance_total)} />
        <StatTile
          label={strings.reports.wasteAttributed}
          value={formatINR(report.waste_total)}
        />
        <StatTile
          label={strings.reports.unexplained}
          value={formatINR(report.unexplained_total)}
          hint={strings.reports.unexplainedHint}
        />
      </div>

      <ExportButton report="food-cost-variance" />

      {report.lines.length === 0 ? (
        <p className="text-muted-foreground">{strings.reports.empty}</p>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{strings.reports.item}</TableHead>
                <TableHead className="text-right">{strings.reports.theoretical}</TableHead>
                <TableHead className="text-right">{strings.reports.actual}</TableHead>
                <TableHead className="text-right">{strings.reports.variance}</TableHead>
                <TableHead className="text-right">{strings.reports.wasteAttributed}</TableHead>
                <TableHead className="text-right">{strings.reports.unexplained}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {report.lines.map((line) => (
                <Line key={line.stock_item_id} line={line} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}

/**
 * One ingredient's row.
 *
 * Quantities carry their base unit because a bare "400" beside paneer means nothing — units are
 * canonical in the ledger (invariant 5) and the screen is where that becomes readable.
 */
function Line({ line }: { line: VarianceLine }): ReactElement {
  return (
    <TableRow>
      <TableCell className="font-medium">{line.item_name}</TableCell>
      <TableCell className="text-right tabular-nums">
        {line.theoretical_quantity} {line.base_unit}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {line.actual_quantity} {line.base_unit}
      </TableCell>
      <TableCell className="text-right tabular-nums">{formatINR(line.variance_value)}</TableCell>
      <TableCell className="text-right tabular-nums">{formatINR(line.waste_value)}</TableCell>
      {/* The number the module exists for, in the last column and in plain ink. It is a question,
          and a question does not need a colour to be read. */}
      <TableCell className="text-right font-semibold tabular-nums">
        {formatINR(line.unexplained_value)}
      </TableCell>
    </TableRow>
  );
}
