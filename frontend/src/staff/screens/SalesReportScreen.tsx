import type { ReactElement } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { formatINR } from '@shared/money';
import { Permission } from '@shared/permissions';
import { useAuth } from '@staff/auth/AuthContext';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { ExportButton } from '@staff/components/ExportButton';
import { QueryState } from '@staff/components/QueryState';
import { StatTile } from '@staff/components/StatTile';
import { strings } from '@staff/strings';
import { type SalesReport, useSalesReport } from '@staff/api/reports';

/**
 * What the restaurant took, by business day.
 *
 * **Owner and accountant only.** The P1 design withholds `report.financial.view` from the manager,
 * so this screen is one a manager does not have rather than one with blanks in it — the route
 * refuses too, because a redacted figure invites somebody to go looking for the endpoint.
 *
 * **A table, not a chart** (`dataviz`: more than a handful of classes that all carry meaning is a
 * table). Every figure is right-aligned and tabular, and money goes through `formatINR` without
 * ever being parsed into a number (invariant 3).
 */
export default function SalesReportScreen(): ReactElement {
  // M19 criterion 6: a figure on the trends screen opens the rows it came from, **already
  // filtered**, which closes the M13 row that left this at "the right screen". The window arrives
  // in the URL rather than in memory so the link is shareable, survives a reload, and survives the
  // document load that a branch switch performs.
  //
  // `undefined` rather than `null` when absent: `useSalesReport` treats undefined as "the server's
  // own default window", which is what an unfiltered visit should still get.
  const [params] = useSearchParams();
  const since = params.get('since') ?? undefined;
  const until = params.get('until') ?? undefined;
  const report = useSalesReport(since, until);
  // Decision 4: a day's revenue reaches the bills that made it. Gated, because the bills screen is
  // a manager's and an accountant reads the books without holding it.
  const { can } = useAuth();

  return (
    <div className="flex flex-col gap-page">
      <h1 className="text-2xl font-semibold">{strings.reports.salesTitle}</h1>
      <QueryState
        isPending={report.isPending}
        error={report.error}
        pendingLabel={strings.reports.loading}
      >
        {report.data === undefined ? null : (
          <Sales report={report.data} toBills={can(Permission.ORDER_VOID)} />
        )}
      </QueryState>
    </div>
  );
}

function Sales({ report, toBills }: { report: SalesReport; toBills: boolean }): ReactElement {
  return (
    <>
      <p className="text-sm text-muted-foreground tabular-nums">
        {strings.reports.period(report.since, report.until)}
      </p>

      <div className="flex flex-wrap gap-4">
        <StatTile
          label={strings.reports.revenue}
          value={formatINR(report.revenue.value)}
          comparison={report.revenue}
        />
        <StatTile
          label={strings.reports.covers}
          value={report.covers.value}
          comparison={report.covers}
        />
        <StatTile
          label={strings.reports.averageBill}
          value={formatINR(report.average_bill.value)}
          comparison={report.average_bill}
        />
      </div>

      <ExportButton report="sales" />

      {report.days.length === 0 ? (
        <p className="text-muted-foreground">{strings.reports.empty}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{strings.reports.day}</TableHead>
              <TableHead className="text-right">{strings.reports.bills}</TableHead>
              <TableHead className="text-right">{strings.reports.covers}</TableHead>
              <TableHead className="text-right">{strings.reports.revenue}</TableHead>
              <TableHead className="text-right">{strings.reports.tax}</TableHead>
              <TableHead className="text-right">{strings.reports.discounts}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {report.days.map((day) => (
              <TableRow key={day.business_date}>
                <TableCell className="tabular-nums">
                  {toBills ? (
                    <Link className="underline" to="/bills">
                      {day.business_date}
                    </Link>
                  ) : (
                    day.business_date
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">{day.orders}</TableCell>
                <TableCell className="text-right tabular-nums">{day.covers}</TableCell>
                <TableCell className="text-right tabular-nums">{formatINR(day.revenue)}</TableCell>
                <TableCell className="text-right tabular-nums">{formatINR(day.tax)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatINR(day.discounts)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Payments report={report} />
    </>
  );
}

/** How the money arrived. Its own component so the screen stays inside the complexity budget. */
function Payments({ report }: { report: SalesReport }): ReactElement {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">{strings.reports.paymentsTitle}</h2>
      {report.payments.length === 0 ? (
        <p className="text-muted-foreground">{strings.reports.empty}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{strings.reports.paymentsTitle}</TableHead>
              <TableHead className="text-right">{strings.reports.bills}</TableHead>
              <TableHead className="text-right">{strings.reports.value}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {report.payments.map((split) => (
              <TableRow key={split.method}>
                <TableCell>{strings.reports.method[split.method] ?? split.method}</TableCell>
                <TableCell className="text-right tabular-nums">{split.count}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatINR(split.amount)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  );
}
