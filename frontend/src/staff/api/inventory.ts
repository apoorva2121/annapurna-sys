import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { apiGet, apiPatch, apiPost } from '@shared/api';

/**
 * The stock ledger.
 *
 * **Every quantity is a string**, for the same reason recipe quantities are (`stock.ts`): a
 * movement can be 0.05 g of saffron, and `number` is how that becomes 0.05000000000000000277 on a
 * table whose entire purpose is that it adds up exactly. Nothing here is ever added on the client.
 *
 * **There is no update or delete hook, for anything.** The ledger is append-only — the database
 * physically refuses both — so a hook implying otherwise would advertise a capability the server
 * rejects. A correction is `useAdjustStock`.
 *
 * **`is_negative` comes from the server.** The screen does not compute `quantity < 0`, because a
 * negative position is not a rendering detail: it means stock was consumed that nobody recorded
 * receiving, which is the single most useful thing this product can tell a restaurant that keeps
 * no records. It is a first-class field so it cannot be forgotten.
 */

const LEDGER_KEY = ['staff', 'stock-ledger'] as const;

export type OnHandRow = {
  stock_item_id: string;
  code: string;
  name: string;
  base_unit: 'g' | 'ml' | 'unit';
  quantity: string;
  value: string;
  is_negative: boolean;
};

export type OnHandList = {
  items: OnHandRow[];
  /** So a screen can lead with the problem rather than making somebody scan a list for it. */
  negative_count: number;
};

export type ExpiringBatch = {
  batch_id: string;
  unit_cost: string;
  remaining: string;
  expiry_date: string | null;
};

export type MovementType =
  | 'receipt'
  | 'production'
  | 'consumption'
  | 'wastage'
  | 'staff_meal'
  | 'complimentary'
  | 'transfer'
  | 'adjustment'
  | 'count';

export type Movement = {
  id: string;
  stock_item_id: string;
  stock_batch_id: string;
  type: MovementType;
  quantity_delta: string;
  unit_cost: string;
  basis: 'theoretical' | 'actual';
  occurred_at: string;
  business_date: string;
  ref_type: string | null;
  ref_id: string | null;
  note: string | null;
};

export type StockBatch = {
  id: string;
  stock_item_id: string;
  batch_code: string;
  quantity_received: string;
  unit_cost: string;
  received_at: string;
  expiry_date: string | null;
  storage_location: string | null;
  source: 'purchase' | 'production' | 'opening' | 'transfer';
};

export type CountLine = {
  stock_item_id: string;
  system_quantity: string;
  counted_quantity: string;
  variance_value: string;
  reason: string | null;
};

export type StockCount = {
  id: string;
  counted_at: string;
  business_date: string;
  scope: 'full' | 'partial' | 'spot';
  status: 'draft' | 'submitted' | 'approved';
  counted_by: string | null;
  approved_by: string | null;
  lines: CountLine[];
};

export type Consumption = {
  lines: { batch_id: string; quantity: string; unit_cost: string }[];
  /** What the batches could not cover. Reported, never refused — see the service. */
  shortfall: string;
  total_value: string;
};

// ---------------------------------------------------------------- reads

export function useOnHand(includeZero = false): UseQueryResult<OnHandList> {
  return useQuery({
    queryKey: [...LEDGER_KEY, 'on-hand', includeZero],
    queryFn: () => apiGet<OnHandList>(`/staff/stock/on-hand?include_zero=${String(includeZero)}`),
  });
}

export function useExpiring(withinDays = 7): UseQueryResult<{ batches: ExpiringBatch[] }> {
  return useQuery({
    queryKey: [...LEDGER_KEY, 'expiring', withinDays],
    queryFn: () =>
      apiGet<{ batches: ExpiringBatch[] }>(
        `/staff/stock/expiring?within_days=${String(withinDays)}`,
      ),
  });
}

export function useMovements(stockItemId: string | null): UseQueryResult<Movement[]> {
  return useQuery({
    queryKey: [...LEDGER_KEY, 'movements', stockItemId],
    // `?? ''` rather than a non-null assertion: `enabled` already stops the fetch, and an
    // assertion here would be a lie the type system stops checking.
    queryFn: () => apiGet<Movement[]>(`/staff/stock/items/${stockItemId ?? ''}/movements?limit=50`),
    enabled: stockItemId !== null,
  });
}

export function useStockCounts(): UseQueryResult<{ counts: StockCount[] }> {
  return useQuery({
    queryKey: [...LEDGER_KEY, 'counts'],
    queryFn: () => apiGet<{ counts: StockCount[] }>('/staff/stock/counts'),
  });
}

// ---------------------------------------------------------------- writes

/** Everything the ledger writes invalidates the same root key.
 *
 * Deliberately coarse. A receipt changes on-hand, the expiry list, the movement history and any
 * open count's system quantities, and a screen showing a stale position after a delivery was just
 * booked in is worse than one extra fetch. */
function useLedgerMutation<TVariables, TData>(
  fn: (variables: TVariables) => Promise<TData>,
): UseMutationResult<TData, Error, TVariables> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: LEDGER_KEY });
    },
  });
}

export type ReceiptInput = {
  stock_item_id: string;
  quantity: string;
  unit_cost: string;
  expiry_date?: string | null;
  storage_location?: string | null;
};

export function useReceiveStock(): UseMutationResult<StockBatch, Error, ReceiptInput> {
  return useLedgerMutation((input) => apiPost<StockBatch>('/staff/stock/receipts', input));
}

export function useProduceBatch(): UseMutationResult<
  StockBatch,
  Error,
  { stock_item_id: string; quantity: string }
> {
  return useLedgerMutation((input) => apiPost<StockBatch>('/staff/stock/production', input));
}

export function useAdjustStock(): UseMutationResult<
  Movement,
  Error,
  { stock_item_id: string; quantity_delta: string; reason: string }
> {
  return useLedgerMutation((input) => apiPost<Movement>('/staff/stock/adjustments', input));
}

export function useConsumeStock(): UseMutationResult<
  Consumption,
  Error,
  { stock_item_id: string; quantity: string }
> {
  return useLedgerMutation((input) => apiPost<Consumption>('/staff/stock/consumption', input));
}

// ---------------------------------------------------------------- counts

export function useOpenCount(): UseMutationResult<
  StockCount,
  Error,
  { stock_item_ids: string[]; scope: 'full' | 'partial' | 'spot' }
> {
  return useLedgerMutation((input) => apiPost<StockCount>('/staff/stock/counts', input));
}

export function useRecordCount(): UseMutationResult<
  StockCount,
  Error,
  { countId: string; lines: { stock_item_id: string; counted_quantity: string }[] }
> {
  return useLedgerMutation(({ countId, lines }) =>
    apiPatch<StockCount>(`/staff/stock/counts/${countId}`, { lines }),
  );
}

export function useSubmitCount(): UseMutationResult<StockCount, Error, string> {
  return useLedgerMutation((countId) =>
    apiPost<StockCount>(`/staff/stock/counts/${countId}/submit`),
  );
}

export function useApproveCount(): UseMutationResult<StockCount, Error, string> {
  return useLedgerMutation((countId) =>
    apiPost<StockCount>(`/staff/stock/counts/${countId}/approve`),
  );
}
