import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { apiGet, apiPost } from '@shared/api';
import type { WastageStage } from '@shared/enums';

/**
 * Waste.
 *
 * **No mutation here carries a cost, and none can.** The server computes it from the batches the
 * stock actually came out of; the API has no field to send one, so a client that tried would be
 * refused. The rupee value arrives in the *response* and the screen shows it afterwards — which
 * `docs/waste-model.md` says teaches, where showing it first suppresses honest reporting.
 *
 * **Logging carries an idempotency key made when the button was pressed** (ADR 0010). A kitchen
 * phone on a bad connection is exactly what it is for: double-booked waste is not a duplicate row,
 * it is a second consumption against the stock ledger and a food-cost figure wrong all month.
 */

const WASTE_KEY = ['staff', 'wastage'] as const;

export type WastageReason = {
  id: string;
  code: string;
  name: string;
  stage: WastageStage;
  /** Stored, and not enforced until M11 owns attachments. The screen may nudge; nothing refuses. */
  requires_photo: boolean;
  requires_approval: boolean;
  is_active: boolean;
};

export type WastageEvent = {
  id: string;
  stock_item_id: string;
  wastage_reason_id: string;
  reason_code: string;
  reason_name: string;
  stage: WastageStage;
  quantity: string;
  /** A string all the way to the formatter. Never parsed into a number (invariant 3). */
  cost_value: string;
  occurred_at: string;
  business_date: string;
  reported_by: string;
  approved_by: string | null;
  approved_at: string | null;
  awaiting_approval: boolean;
  note: string | null;
};

export type WastageSummaryLine = {
  stage: WastageStage;
  reason_code: string;
  reason_name: string;
  events: number;
  cost_value: string;
  share_percent: string;
};

export type WastageSummary = {
  since: string;
  until: string;
  total_cost: string;
  lines: WastageSummaryLine[];
};

export function useWastageReasons(): UseQueryResult<{ items: WastageReason[] }> {
  return useQuery({
    queryKey: [...WASTE_KEY, 'reasons'],
    queryFn: () => apiGet<{ items: WastageReason[] }>('/staff/wastage/reasons'),
    // Reasons change when an owner configures them, which is rarely. Refetching this on every
    // mount would cost a round trip on the screen whose whole promise is ten seconds.
    staleTime: 5 * 60 * 1000,
  });
}

export function useWastageLog(
  businessDate?: string,
): UseQueryResult<{ items: WastageEvent[]; next_cursor: string | null }> {
  const query = businessDate === undefined ? '' : `?business_date=${businessDate}`;
  return useQuery({
    queryKey: [...WASTE_KEY, 'log', businessDate ?? 'today'],
    queryFn: () =>
      apiGet<{ items: WastageEvent[]; next_cursor: string | null }>(`/staff/wastage${query}`),
  });
}

export function useWastageSummary(since?: string, until?: string): UseQueryResult<WastageSummary> {
  const params = new URLSearchParams();
  if (since !== undefined) {
    params.set('since', since);
  }
  if (until !== undefined) {
    params.set('until', until);
  }
  const query = params.size === 0 ? '' : `?${params.toString()}`;
  return useQuery({
    queryKey: [...WASTE_KEY, 'summary', since ?? '', until ?? ''],
    queryFn: () => apiGet<WastageSummary>(`/staff/wastage/summary${query}`),
  });
}

export type LogWastageInput = {
  stockItemId: string;
  wastageReasonId: string;
  /** What the person tapped — in the item's purchase unit when `perPurchaseUnit` is true. */
  quantity: string;
  /**
   * Whether the server must convert. The screen never does the arithmetic itself: a quantity
   * divided by a thousand in a browser is the float round-trip invariant 3 forbids, and that rule
   * exists because a delivery typed against the wrong unit once repriced cabbage to ₹40 a gram.
   */
  perPurchaseUnit: boolean;
  note?: string;
  idempotencyKey: string;
};

export function useLogWastage(): UseMutationResult<WastageEvent, Error, LogWastageInput> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      stockItemId,
      wastageReasonId,
      quantity,
      perPurchaseUnit,
      note,
      idempotencyKey,
    }) =>
      apiPost<WastageEvent>(
        '/staff/wastage',
        {
          stock_item_id: stockItemId,
          wastage_reason_id: wastageReasonId,
          quantity,
          per_purchase_unit: perPurchaseUnit,
          ...(note === undefined ? {} : { note }),
        },
        { idempotencyKey },
      ),
    onSuccess: () => {
      // The log and the summary both move, and so does what is on the shelf — logging waste is a
      // stock consumption, so the on-hand screen is stale the moment this returns.
      void client.invalidateQueries({ queryKey: WASTE_KEY });
      void client.invalidateQueries({ queryKey: ['staff', 'stock'] });
    },
  });
}

export function useApproveWastage(): UseMutationResult<WastageEvent, Error, { eventId: string }> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ eventId }) => apiPost<WastageEvent>(`/staff/wastage/${eventId}/approve`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: WASTE_KEY });
    },
  });
}
