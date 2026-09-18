import type { ReactElement } from 'react';
import { Link } from 'react-router-dom';

import { formatINR } from '@shared/money';
import { Permission } from '@shared/permissions';
import { useAuth } from '@staff/auth/AuthContext';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { ExportButton } from '@staff/components/ExportButton';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { type DishLine, type DishReport, useDishReport } from '@staff/api/reports';

/**
 * Every dish, what it sold, what it earned, and where that puts it.
 *
 * **This is `docs/domain-model.md`'s acceptance query, rendered.** Units, revenue, theoretical
 * cost, rating and kitchen time per dish for a period — the question the whole product was
 * specified around.
 *
 * **The quadrant advises; it never acts.** There is no "remove this dish" button and there will
 * not be one: a product that removed a dish because a quadrant said so would be wrong about one
 * restaurant in five, and the one it was wrong about would be somebody's signature dish. So every
 * row carries a sentence with the numbers beside it, and the sentence is the server's — the same
 * words in the CSV as on the screen.
 *
 * **The quadrant name is a word, never a colour.** Four categorical hues for four names that
 * already fit in a column would spend colour on something text does better, and `docs/ui/
 * conventions.md` reserves the alert colours for things somebody must act on now.
 */
export default function DishPerformanceScreen(): ReactElement {
  const report = useDishReport();
  // Decision 4. Gated, because an accountant holds the report and not the costing screen, and a
  // link that answers 403 reads as a broken product.
  const { can } = useAuth();

  return (
    <div className="flex flex-col gap-page">
      <h1 className="text-2xl font-semibold">{strings.reports.dishesTitle}</h1>
      <p className="text-sm text-muted-foreground">{strings.reports.quadrantHint}</p>
      <QueryState
        isPending={report.isPending}
        error={report.error}
        pendingLabel={strings.reports.loading}
      >
        {report.data === undefined ? null : (
          <Dishes report={report.data} toCosts={can(Permission.COST_VIEW)} />
        )}
      </QueryState>
    </div>
  );
}

function Dishes({ report, toCosts }: { report: DishReport; toCosts: boolean }): ReactElement {
  if (report.lines.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-sm text-muted-foreground tabular-nums">
          {strings.reports.period(report.since, report.until)}
        </p>
        <p>{strings.reports.empty}</p>
      </div>
    );
  }

  return (
    <>
      <p className="text-sm text-muted-foreground tabular-nums">
        {strings.reports.period(report.since, report.until)}
      </p>
      <ExportButton report="dish-performance" />
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{strings.reports.dish}</TableHead>
              <TableHead className="text-right">{strings.reports.units}</TableHead>
              <TableHead className="text-right">{strings.reports.revenue}</TableHead>
              <TableHead className="text-right">{strings.reports.margin}</TableHead>
              <TableHead className="text-right">{strings.reports.foodCostPercent}</TableHead>
              <TableHead className="text-right">{strings.reports.rating}</TableHead>
              <TableHead className="text-right">{strings.reports.prepTime}</TableHead>
              <TableHead>{strings.reports.adviceHeading}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {report.lines.map((line) => (
              <Line key={line.variant_id} line={line} toCosts={toCosts} />
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}

function Line({ line, toCosts }: { line: DishLine; toCosts: boolean }): ReactElement {
  return (
    <TableRow>
      <TableCell>
        {toCosts ? (
          <Link className="font-medium underline" to="/costs">
            {line.item_name}
          </Link>
        ) : (
          <span className="font-medium">{line.item_name}</span>
        )}
        <span className="ml-2 text-xs text-muted-foreground">{line.variant_name}</span>
        {/* The quadrant, in words, beside the dish it describes. */}
        <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs">
          {strings.reports.quadrant[line.quadrant] ?? line.quadrant}
        </span>
      </TableCell>
      <TableCell className="text-right tabular-nums">{line.units}</TableCell>
      <TableCell className="text-right tabular-nums">{formatINR(line.revenue)}</TableCell>
      <TableCell className="text-right tabular-nums">{formatINR(line.margin)}</TableCell>
      {/* A dish given away free has no food-cost percentage, which is not the same as 0%. */}
      <TableCell className="text-right tabular-nums">
        {line.food_cost_percent === null ? '—' : `${line.food_cost_percent}%`}
      </TableCell>
      <TableCell className="text-right tabular-nums">{line.average_rating ?? '—'}</TableCell>
      <TableCell className="text-right tabular-nums">
        {line.average_prep_seconds === null
          ? '—'
          : strings.reports.minutes(line.average_prep_seconds)}
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">{line.advice}</TableCell>
    </TableRow>
  );
}
