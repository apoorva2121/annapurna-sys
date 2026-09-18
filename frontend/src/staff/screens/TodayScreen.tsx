import type { ReactElement } from 'react';
import { Link } from 'react-router-dom';

import { formatINR } from '@shared/money';
import { Permission } from '@shared/permissions';
import { useAuth } from '@staff/auth/AuthContext';
import { QueryState } from '@staff/components/QueryState';
import { StatTile } from '@staff/components/StatTile';
import { strings } from '@staff/strings';
import { useToday } from '@staff/api/reports';

/**
 * The ten seconds before service, and the way into every other report.
 *
 * **A KPI row, not a chart.** The `dataviz` skill's own heuristic: a handful of headline numbers
 * is a stat-tile row, and a chart of one value is a chart of nothing. It is also why this
 * application ships no charting library at all — half a megabyte in a PWA that a waiter loads on a
 * three-year-old Android, to draw four numbers somebody reads in two seconds.
 *
 * **The business day is printed, not assumed.** A restaurant's day starts at five in the morning
 * (invariant 4), so "today" on this screen and "today" on the phone in somebody's hand are
 * different dates at 2am. The screen says which one it means.
 *
 * **Every tile leads somewhere.** Decision 4: a figure that cannot be opened is a figure nobody
 * trusts the second time it surprises them.
 */
export default function TodayScreen(): ReactElement {
  const today = useToday();
  const { can } = useAuth();

  return (
    <div className="flex flex-col gap-page">
      <h1 className="text-2xl font-semibold">{strings.reports.todayTitle}</h1>
      <QueryState
        isPending={today.isPending}
        error={today.error}
        pendingLabel={strings.reports.loading}
      >
        {today.data === undefined ? null : (
          <>
            <div className="flex flex-col gap-1">
              <p className="text-sm text-muted-foreground tabular-nums">
                {strings.reports.businessDay(today.data.business_date)}
              </p>
              <p className="text-sm text-muted-foreground">{strings.reports.businessDayHint}</p>
            </div>

            <div className="flex flex-wrap gap-4">
              <StatTile
                label={strings.reports.revenue}
                value={formatINR(today.data.revenue.value)}
                comparison={today.data.revenue}
                against={strings.reports.versusYesterday}
              />
              <StatTile
                label={strings.reports.covers}
                value={today.data.covers.value}
                comparison={today.data.covers}
                against={strings.reports.versusYesterday}
              />
              <StatTile
                label={strings.reports.openOrders}
                value={String(today.data.open_orders)}
                hint={strings.reports.openOrdersHint}
              />
              <StatTile
                label={strings.reports.rating}
                value={today.data.average_rating ?? '—'}
                hint={strings.reports.ratingsCounted(today.data.ratings_counted)}
              />
            </div>

            <ReportLinks canSeeMoney={can(Permission.REPORT_FINANCIAL_VIEW)} />
          </>
        )}
      </QueryState>
    </div>
  );
}

/**
 * The other four reports.
 *
 * The two financial ones are **absent** rather than disabled for a manager. The P1 design withholds
 * `report.financial.view` from them on purpose, and a greyed-out link is an invitation to find out
 * what is behind it (ADR 0007, and the same reasoning the route uses when it returns 403 rather
 * than a screen full of blanks).
 */
function ReportLinks({ canSeeMoney }: { canSeeMoney: boolean }): ReactElement {
  return (
    <nav className="flex flex-col gap-2">
      <Link className="min-h-target underline" to="/reports/dishes">
        {strings.reports.dishesTitle}
      </Link>
      <Link className="min-h-target underline" to="/reports/waste">
        {strings.reports.wasteTitle}
      </Link>
      {canSeeMoney && (
        <>
          <Link className="min-h-target underline" to="/reports/sales">
            {strings.reports.salesTitle}
          </Link>
          <Link className="min-h-target underline" to="/reports/variance">
            {strings.reports.varianceTitle}
          </Link>
        </>
      )}
    </nav>
  );
}
