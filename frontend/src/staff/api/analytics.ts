import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { apiGet } from '@shared/api';

/**
 * M19 · Owner analytics. Trends over time, and branches beside each other.
 *
 * **There is no tax field in this file, and that is deliberate.** The owner's decision of
 * 2026-09-19 is that nothing tax-shaped sums across branches — two restaurants under one
 * organization can hold different GSTINs and even different schemes, so a summed tax figure has no
 * legal referent. The backend schema omits it, which makes the forbidden total *unrepresentable*
 * rather than merely discouraged; this file keeps that property by not inventing a type for it.
 *
 * **Money is a string all the way to the formatter** (invariant 3). Nothing here parses one, and
 * nothing here adds two together — including the chart, which scales a series by comparing strings
 * through `Decimal`-safe helpers rather than by calling `Number()` on a rupee amount.
 */

const ANALYTICS_KEY = ['staff', 'analytics'] as const;

/** The metrics a series can be drawn of. Mirrors `app.services.analytics.Metric` — and `tax` is
 *  absent there for the reason above, so it is absent here. */
export type Metric = 'revenue' | 'covers' | 'orders' | 'discounts' | 'average_bill';

export type Bucket = 'day' | 'week';

export type SeriesPoint = {
  starts_on: string;
  ends_on: string;
  /** `null`, never `"0"`, when the bucket has nothing in it. A day the restaurant was shut has no
   *  average bill, and drawing a zero would put a line through the floor of the chart. */
  value: string | null;
  /** Business dates inside this bucket that issued an invoice. A week showing 2 of 7 is not a
   *  quiet week, it is a week the shop was shut — and the chart has to be able to say so. */
  days_traded: number;
};

export type Series = {
  metric: Metric;
  bucket: Bucket;
  since: string;
  until: string;
  restaurant_ids: string[];
  points: SeriesPoint[];
};

export type BranchRow = {
  restaurant_id: string;
  name: string;
  revenue: string;
  /** Dine-in only. `spend_per_cover` divides *this*, not `revenue`: `order.covers` is NULL for
   *  takeaway and delivery, so dividing total revenue by covers charges a branch's whole delivery
   *  trade to the guests who sat down. */
  dine_in_revenue: string;
  covers: number;
  orders: number;
  /** Distinct business dates this branch issued an invoice on. Not the length of the window. */
  business_days_traded: number;
  revenue_per_trading_day: string | null;
  /** The owner's chosen basis for comparing branches. `null` when nobody sat down, which is a
   *  different statement from zero. */
  spend_per_cover: string | null;
};

export type BranchComparison = {
  since: string;
  until: string;
  branches: BranchRow[];
  /** The figures that may be summed, and only those. */
  total_revenue: string;
  total_covers: number;
  total_orders: number;
  average_bill: string | null;
};

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      search.set(key, value);
    }
  }
  return search.size === 0 ? '' : `?${search.toString()}`;
}

export function useTrend(options: {
  metric: Metric;
  bucket: Bucket;
  since?: string;
  until?: string;
  acrossBranches?: boolean;
}): UseQueryResult<Series> {
  const { metric, bucket, since, until, acrossBranches = false } = options;
  return useQuery({
    queryKey: [...ANALYTICS_KEY, 'trend', metric, bucket, since ?? '', until ?? '', acrossBranches],
    queryFn: () =>
      apiGet<Series>(
        `/staff/analytics/trend${query({
          metric,
          bucket,
          since,
          until,
          across_branches: acrossBranches ? 'true' : undefined,
        })}`,
      ),
  });
}

export function useBranchComparison(
  since?: string,
  until?: string,
): UseQueryResult<BranchComparison> {
  return useQuery({
    queryKey: [...ANALYTICS_KEY, 'branches', since ?? '', until ?? ''],
    queryFn: () => apiGet<BranchComparison>(`/staff/analytics/branches${query({ since, until })}`),
  });
}
