import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { apiGet, apiPost } from '@shared/api';
import type { CashMovementType, CashSessionStatus } from '@shared/enums';
import type { Person } from '@staff/api/people';

/**
 * The till: open with a float, pay out, count at close, adjust afterwards.
 *
 * **Nothing the till "should" hold is sent from here.** Expected cash, the variance and the adjusted
 * variance are response fields only; the server derives them from payment and movement rows, and a
 * client that could send one could send the answer it wanted (`docs/security.md` A04). What this side
 * sends is what a person saw or did: a float counted into the drawer, notes counted out of it, ₹300
 * handed to the vegetable seller and why.
 *
 * Payouts and adjustments carry an Idempotency-Key (ADR 0010): a payout tapped twice on a stalled
 * connection must take the money out of the till once.
 */

export type CashCount = { denomination: string; quantity: number };

export type CashMovement = {
  id: string;
  type: CashMovementType;
  amount: string;
  reason: string;
  recorded_by: string;
  occurred_at: string;
  recorded_by_person?: Person | null;
  /** Recorded by the person who closed the till (D16). */
  by_closer?: boolean;
};

export type TillSummary = {
  id: string;
  status: CashSessionStatus;
  opened_at: string;
  opened_by: string;
  opening_float: string;
  business_date: string;
  closed_at: string | null;
  closed_by: string | null;
  counted_cash: string | null;
  variance: string | null;
  cash_taken: string;
  payouts: string;
  adjustments: string;
  expected_cash: string;
  adjusted_variance: string | null;
  /** Decision D13: who closed and who adjusted, by name. Absent from an older API. */
  closed_by_person?: Person | null;
  adjusted_by?: (Person & { by_closer: boolean })[];
};

export type Till = TillSummary & { counts: CashCount[]; movements: CashMovement[] };

export type TillPage = { items: TillSummary[]; next_cursor: string | null };

const CASH_KEY = ['staff', 'cash'] as const;

export function useTills(): UseQueryResult<TillPage> {
  return useQuery({
    queryKey: [...CASH_KEY, 'tills'],
    queryFn: () => apiGet<TillPage>('/staff/cash/sessions'),
  });
}

/** Put the returned till in the cache and re-read the list, whose figures that till is part of. */
function useCashMutation<TVariables>(
  fn: (variables: TVariables) => Promise<Till>,
): UseMutationResult<Till, Error, TVariables> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (till) => {
      client.setQueryData([...CASH_KEY, 'till', till.id], till);
      void client.invalidateQueries({ queryKey: [...CASH_KEY, 'tills'] });
    },
  });
}

export function useOpenTill(): UseMutationResult<Till, Error, { openingFloat: string }> {
  return useCashMutation(({ openingFloat }) =>
    apiPost<Till>('/staff/cash/sessions', { opening_float: openingFloat }),
  );
}

export type TillMovementInput = {
  tillId: string;
  amount: string;
  reason: string;
  idempotencyKey: string;
};

export function usePayout(): UseMutationResult<Till, Error, TillMovementInput> {
  return useCashMutation(({ tillId, amount, reason, idempotencyKey }) =>
    apiPost<Till>(`/staff/cash/sessions/${tillId}/payouts`, { amount, reason }, { idempotencyKey }),
  );
}

export function useAdjustment(): UseMutationResult<Till, Error, TillMovementInput> {
  return useCashMutation(({ tillId, amount, reason, idempotencyKey }) =>
    apiPost<Till>(
      `/staff/cash/sessions/${tillId}/adjustments`,
      { amount, reason },
      { idempotencyKey },
    ),
  );
}

export function useCloseTill(): UseMutationResult<
  Till,
  Error,
  { tillId: string; counts: CashCount[] }
> {
  return useCashMutation(({ tillId, counts }) =>
    apiPost<Till>(`/staff/cash/sessions/${tillId}/close`, { counts }),
  );
}

/** Cash taken today with no till open (decision D3). No count expects it, so the screen says so. */
export type OutsideTill = { business_date: string; cash_taken: string; payments: number };

export function useCashOutsideTill(): UseQueryResult<OutsideTill> {
  return useQuery({
    queryKey: [...CASH_KEY, 'outside-till'],
    queryFn: () => apiGet<OutsideTill>('/staff/cash/outside-till'),
  });
}
