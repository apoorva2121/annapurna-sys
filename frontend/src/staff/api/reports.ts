import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import { apiGet, downloadCsv } from '@shared/api';
import type { WastageStage } from '@shared/enums';

/**
 * The dashboards and reports.
 *
 * **Every figure arrives with its comparison already computed.** `docs/ui/conventions.md`: a
 * number with no baseline is not information — and the baseline comes from the server over the
 * same bounded query, so a screen subtracting two separately-fetched numbers can never disagree
 * with the figure printed beside it.
 *
 * **Money is a string all the way to the formatter** (invariant 3). Nothing here parses one.
 *
 * **CSV is fetched, not linked.** A plain `<a href>` would reach the API without this session's
 * token — it lives in memory, not in a cookie — and putting the token in a query string would
 * write a live credential into every proxy log on the way. `downloadCsv` sends the header and
 * hands the browser a blob to save.
 */

const REPORTS_KEY = ['staff', 'reports'] as const;

export type Comparison = {
  value: string;
  previous: string;
  change: string;
  /** `null` means *nothing to compare against* — which is not the same as unchanged. */
  change_percent: string | null;
};

export type SalesDay = {
  business_date: string;
  orders: number;
  covers: number;
  revenue: string;
  tax: string;
  discounts: string;
};

export type PaymentSplit = {
  method: string;
  amount: string;
  count: number;
};

export type SalesReport = {
  since: string;
  until: string;
  revenue: Comparison;
  covers: Comparison;
  average_bill: Comparison;
  days: SalesDay[];
  payments: PaymentSplit[];
};

export type VarianceLine = {
  stock_item_id: string;
  item_name: string;
  base_unit: string;
  theoretical_quantity: string;
  actual_quantity: string;
  variance_quantity: string;
  theoretical_value: string;
  actual_value: string;
  variance_value: string;
  waste_value: string;
  /** The part nobody wrote a reason for. The line this module exists to produce. */
  unexplained_value: string;
};

export type VarianceReport = {
  since: string;
  until: string;
  theoretical_total: string;
  actual_total: string;
  variance_total: string;
  waste_total: string;
  unexplained_total: string;
  lines: VarianceLine[];
};

export type WasteLine = {
  /** M09's own four stages, never lumped (`docs/waste-model.md`). */
  stage: WastageStage;
  reason_code: string;
  reason_name: string;
  events: number;
  cost_value: string;
  /** Computed on the server from Decimal, so the stages add to a hundred within a paisa. */
  share_percent: string;
};

export type WasteReport = {
  since: string;
  until: string;
  total: Comparison;
  lines: WasteLine[];
};

export type Quadrant = 'star' | 'plough_horse' | 'hidden_gem' | 'dog';

export type DishLine = {
  variant_id: string;
  item_name: string;
  variant_name: string;
  units: number;
  revenue: string;
  theoretical_cost: string;
  margin: string;
  food_cost_percent: string | null;
  average_rating: string | null;
  average_prep_seconds: number | null;
  quadrant: Quadrant;
  /** A sentence, with the numbers beside it. The screen recommends; it never acts. */
  advice: string;
};

export type DishReport = {
  since: string;
  until: string;
  lines: DishLine[];
};

export type Today = {
  business_date: string;
  revenue: Comparison;
  covers: Comparison;
  open_orders: number;
  average_rating: string | null;
  /** How many ratings the average is of. A 4.8 from two people is not a 4.8. */
  ratings_counted: number;
};

function window(since?: string, until?: string): string {
  const params = new URLSearchParams();
  if (since !== undefined) {
    params.set('since', since);
  }
  if (until !== undefined) {
    params.set('until', until);
  }
  return params.size === 0 ? '' : `?${params.toString()}`;
}

export function useToday(): UseQueryResult<Today> {
  return useQuery({
    queryKey: [...REPORTS_KEY, 'today'],
    queryFn: () => apiGet<Today>('/staff/dashboard/today'),
  });
}

export function useSalesReport(since?: string, until?: string): UseQueryResult<SalesReport> {
  return useQuery({
    queryKey: [...REPORTS_KEY, 'sales', since ?? '', until ?? ''],
    queryFn: () => apiGet<SalesReport>(`/staff/reports/sales${window(since, until)}`),
  });
}

export function useVarianceReport(
  since?: string,
  until?: string,
): UseQueryResult<VarianceReport> {
  return useQuery({
    queryKey: [...REPORTS_KEY, 'variance', since ?? '', until ?? ''],
    queryFn: () =>
      apiGet<VarianceReport>(`/staff/reports/food-cost-variance${window(since, until)}`),
  });
}

export function useWasteReport(since?: string, until?: string): UseQueryResult<WasteReport> {
  return useQuery({
    queryKey: [...REPORTS_KEY, 'waste', since ?? '', until ?? ''],
    queryFn: () => apiGet<WasteReport>(`/staff/reports/waste${window(since, until)}`),
  });
}

export function useDishReport(since?: string, until?: string): UseQueryResult<DishReport> {
  return useQuery({
    queryKey: [...REPORTS_KEY, 'dishes', since ?? '', until ?? ''],
    queryFn: () => apiGet<DishReport>(`/staff/reports/dish-performance${window(since, until)}`),
  });
}

/** Fetch a report's CSV with this session's token and hand the browser a file to save. */
export async function exportCsv(report: string, since?: string, until?: string): Promise<void> {
  const params = new URLSearchParams(window(since, until).replace('?', ''));
  params.set('format', 'csv');
  await downloadCsv(`/staff/reports/${report}?${params.toString()}`, `${report}.csv`);
}
