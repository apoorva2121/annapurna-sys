import { useState, type ReactElement } from 'react';
import { useNavigate } from 'react-router-dom';

import { formatINR, formatINRAxis } from '@shared/money';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@shared/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import {
  useBranchComparison,
  useTrend,
  type BranchComparison,
  type BranchRow,
  type Bucket,
  type Metric,
  type Series,
  type SeriesPoint,
} from '@staff/api/analytics';
import { useAuth } from '@staff/auth/AuthContext';
import { switchBranch } from '@staff/auth/switchBranch';
import { BarChart, type BarDatum } from '@staff/components/charts/BarChart';
import { TrendChart } from '@staff/components/charts/TrendChart';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';

/**
 * M19 chunk B · the owner's trends, and the branch comparison.
 *
 * **Owner surface** (`docs/ui/conventions.md`): a laptop, calm, someone who came here to think
 * rather than to get through a rush. Behind `report.financial.view` — the same permission M13's
 * money screens use — so it is a screen a manager does not have rather than one with blanks in it.
 *
 * **This route is code-split**, which is the point of M19 decision 2. The charts are a few hundred
 * lines of SVG rather than a library, so the cost is small either way, but "small" is how a waiter's
 * bundle grows: `bundleBudget.test.ts` asserts that neither the guest nor the service bundle
 * reaches this module, and that no charting library has entered `package.json` behind its back.
 *
 * **Nothing tax-shaped appears here and none of it sums.** The owner's decision of 2026-09-19: two
 * branches can hold different GSTINs and even different schemes, so a combined tax figure has no
 * legal referent. The API has no field for it, so this screen could not render one if it tried.
 *
 * **Every figure is formatted from the server's own string** (invariant 3). The numbers the charts
 * use to size a mark come from `plot.ts` and are never displayed — `analyticsDiscipline.test.ts`
 * is what keeps that true rather than merely intended.
 */

const METRICS: Metric[] = ['revenue', 'covers', 'orders', 'discounts', 'average_bill'];
const BUCKETS: Bucket[] = ['day', 'week'];

/** Which metrics are money, and so go through `formatINR` rather than rendering as a count. */
const MONEY: ReadonlySet<Metric> = new Set<Metric>(['revenue', 'discounts', 'average_bill']);

function shortDate(iso: string): string {
  // `Intl` over a date library: the browser already ships the data, and a business date is a plain
  // calendar date with no zone to get wrong — it was resolved to the restaurant's day on the
  // server (invariant 4), and re-deriving one here is how 2am ends up on the wrong day.
  const [year, month, day] = iso.split('-').map(Number);
  if (year === undefined || month === undefined || day === undefined) {
    return iso;
  }
  return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' }).format(
    new Date(Date.UTC(year, month - 1, day)),
  );
}

export default function AnalyticsScreen(): ReactElement {
  const [metric, setMetric] = useState<Metric>('revenue');
  const [bucket, setBucket] = useState<Bucket>('day');
  const [across, setAcross] = useState(false);

  const { session } = useAuth();
  const manyBranches = (session?.restaurants.length ?? 0) > 1;

  const trend = useTrend({ metric, bucket, acrossBranches: across && manyBranches });
  const comparison = useBranchComparison();

  return (
    <div className="flex flex-col gap-page">
      <div>
        <h1 className="text-2xl font-semibold">{strings.analytics.title}</h1>
        <p className="text-muted-foreground text-sm">{strings.analytics.intro}</p>
      </div>

      {/* Filters in one row above the charts (`dataviz`: never scattered among them). */}
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted-foreground">{strings.analytics.metricLabel}</span>
          <Select
            value={metric}
            onValueChange={(next) => {
              setMetric(next as Metric);
            }}
          >
            <SelectTrigger className="min-h-target w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {METRICS.map((option) => (
                <SelectItem key={option} value={option} className="min-h-target">
                  {strings.analytics.metric[option] ?? option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted-foreground">{strings.analytics.bucketLabel}</span>
          <Select
            value={bucket}
            onValueChange={(next) => {
              setBucket(next as Bucket);
            }}
          >
            <SelectTrigger className="min-h-target w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {BUCKETS.map((option) => (
                <SelectItem key={option} value={option} className="min-h-target">
                  {strings.analytics.bucket[option] ?? option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>

        {/* Offered only to somebody who actually holds more than one branch. A toggle with one
            possible outcome teaches people to ignore toggles. */}
        {manyBranches ? (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={across}
              onChange={(event) => {
                setAcross(event.target.checked);
              }}
              className="accent-brand size-4"
            />
            <span>{strings.analytics.acrossBranches}</span>
          </label>
        ) : null}
      </div>

      {across && manyBranches ? (
        <p className="text-muted-foreground max-w-prose text-xs">
          {strings.analytics.acrossBranchesHint}
        </p>
      ) : null}

      <QueryState
        isPending={trend.isPending}
        error={trend.error}
        pendingLabel={strings.analytics.loading}
      >
        {trend.data === undefined ? null : (
          <Trend series={trend.data} metric={metric} bucket={bucket} />
        )}
      </QueryState>

      {manyBranches ? (
        <QueryState
          isPending={comparison.isPending}
          error={comparison.error}
          pendingLabel={strings.analytics.loading}
        >
          {comparison.data === undefined ? null : <Branches comparison={comparison.data} />}
        </QueryState>
      ) : null}
    </div>
  );
}

function Trend({
  series,
  metric,
  bucket,
}: {
  series: Series;
  metric: Metric;
  bucket: Bucket;
}): ReactElement {
  const navigate = useNavigate();
  const money = MONEY.has(metric);
  const bucketDays = bucket === 'week' ? 7 : 1;

  // Money through `formatINR`, counts as themselves. Either way the argument is the server's own
  // string — never a number that came back out of the plot.
  const format = (value: string | null): string => (money ? formatINR(value) : (value ?? '—'));
  // An axis tick is a number this chart generated, not a figure the server sent, so it wears the
  // whole-rupee formatter: "₹80,000" on a gridline rather than "₹80,000.00" repeated five times.
  const formatTick = (value: string): string => (money ? formatINRAxis(value) : value);

  const span = (point: SeriesPoint): string =>
    point.starts_on === point.ends_on
      ? shortDate(point.starts_on)
      : `${shortDate(point.starts_on)}–${shortDate(point.ends_on)}`;

  const open = (point: SeriesPoint): void => {
    // `void`: react-router's navigate returns a promise in v6.4+ and there is nothing to await —
    // the drill-through is a navigation, not a transaction.
    void navigate(`/reports/sales?since=${point.starts_on}&until=${point.ends_on}`);
  };

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-medium">{strings.analytics.metric[metric] ?? metric}</h2>
      <p className="text-muted-foreground text-sm tabular-nums">
        {strings.reports.period(series.since, series.until)} ·{' '}
        {strings.analytics.branchCount(series.restaurant_ids.length)}
      </p>

      <TrendChart
        points={series.points}
        format={format}
        formatTick={formatTick}
        bucketDays={bucketDays}
        ariaLabel={strings.analytics.metric[metric] ?? metric}
        emptyLabel={strings.analytics.empty}
        formatSpan={span}
        formatTraded={strings.analytics.tradedDays}
        onSelect={open}
        selectLabel={(point) => strings.analytics.openDay(span(point), format(point.value))}
      />

      {/* The table view `dataviz` requires: identity and value never depend on reading a chart,
          and a screen reader gets the figures rather than a picture. */}
      <details>
        <summary className="text-muted-foreground min-h-target cursor-pointer text-sm">
          {strings.analytics.tableTitle}
        </summary>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{strings.analytics.colPeriod}</TableHead>
              <TableHead className="text-right">{strings.analytics.colValue}</TableHead>
              <TableHead className="text-right">{strings.analytics.colTraded}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {series.points.map((point) => (
              <TableRow key={point.starts_on}>
                <TableCell>{span(point)}</TableCell>
                <TableCell className="text-right tabular-nums">{format(point.value)}</TableCell>
                <TableCell className="text-right tabular-nums">{point.days_traded}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </details>
    </section>
  );
}

function Branches({ comparison }: { comparison: BranchComparison }): ReactElement {
  const { session } = useAuth();
  const navigate = useNavigate();

  // The drill-through that crosses a tenant boundary. Another branch's rows are not merely another
  // screen — they are outside this token's scope (invariant 1) — so reaching them means switching,
  // and `switchBranch` loads the destination so the window survives the switch. The branch already
  // in scope needs no switch and just navigates.
  const open = (row: BranchRow): void => {
    const destination = `/reports/sales?since=${comparison.since}&until=${comparison.until}`;
    if (row.restaurant_id === session?.restaurant.id) {
      // The branch already in scope needs no switch, and therefore no document load: a router
      // navigation keeps the cached queries, the scroll position and — the part that matters —
      // the access token, which lives in a module variable and does not survive a page load.
      void navigate(destination);
      return;
    }
    void switchBranch(row.restaurant_id, destination);
  };

  const spend: BarDatum[] = comparison.branches.map((row) => ({
    id: row.restaurant_id,
    name: row.name,
    value: row.spend_per_cover,
    label: formatINR(row.spend_per_cover),
    hint: strings.analytics.tradingDays(row.business_days_traded),
  }));

  // The recorded blind spot of the owner's decision 2, shown rather than left to be discovered: a
  // branch whose footfall collapsed but whose remaining guests spend well looks healthy on spend
  // alone. Two charts, never two y-axes on one — `dataviz`'s first non-negotiable.
  const footfall: BarDatum[] = comparison.branches.map((row) => ({
    id: row.restaurant_id,
    name: row.name,
    value:
      row.business_days_traded === 0
        ? null
        : // A count, not money: this division is arithmetic on guests, which invariant 3 does not
          // govern, and it is computed here rather than on the server only because both inputs are
          // already integers on the wire.
          String(Math.round(row.covers / row.business_days_traded)),
    label:
      row.business_days_traded === 0
        ? '—'
        : String(Math.round(row.covers / row.business_days_traded)),
  }));

  return (
    <section className="flex flex-col gap-6">
      <h2 className="text-lg font-medium">{strings.analytics.comparisonTitle}</h2>

      <div className="grid gap-8 lg:grid-cols-2">
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">{strings.analytics.comparisonBasis}</h3>
          <p className="text-muted-foreground max-w-prose text-xs">
            {strings.analytics.comparisonBasisHint}
          </p>
          <BarChart
            data={spend}
            series="series-1"
            ariaLabel={strings.analytics.comparisonBasis}
            emptyLabel={strings.analytics.noBranchData}
            noValueLabel={strings.analytics.noDineIn}
            onSelect={(datum) => {
              const row = comparison.branches.find((each) => each.restaurant_id === datum.id);
              if (row !== undefined) {
                open(row);
              }
            }}
            selectLabel={(datum) => strings.analytics.openBranch(datum.name, datum.label)}
          />
        </div>

        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">{strings.analytics.footfallTitle}</h3>
          <p className="text-muted-foreground max-w-prose text-xs">
            {strings.analytics.footfallHint}
          </p>
          <BarChart
            data={footfall}
            series="series-2"
            ariaLabel={strings.analytics.footfallTitle}
            emptyLabel={strings.analytics.noBranchData}
            noValueLabel={strings.analytics.noDineIn}
            selectLabel={(datum) => datum.name}
          />
        </div>
      </div>

      <details>
        <summary className="text-muted-foreground min-h-target cursor-pointer text-sm">
          {strings.analytics.tableTitle}
        </summary>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{strings.analytics.colBranch}</TableHead>
              <TableHead className="text-right">{strings.analytics.colRevenue}</TableHead>
              <TableHead className="text-right">{strings.analytics.colCovers}</TableHead>
              <TableHead className="text-right">{strings.analytics.colOrders}</TableHead>
              <TableHead className="text-right">{strings.analytics.colSpend}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {comparison.branches.map((row) => (
              <TableRow key={row.restaurant_id}>
                <TableCell>{row.name}</TableCell>
                <TableCell className="text-right tabular-nums">{formatINR(row.revenue)}</TableCell>
                <TableCell className="text-right tabular-nums">{row.covers}</TableCell>
                <TableCell className="text-right tabular-nums">{row.orders}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatINR(row.spend_per_cover)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </details>
    </section>
  );
}
