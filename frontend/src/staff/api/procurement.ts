import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { apiGet, apiPatch, apiPost } from '@shared/api';

/**
 * Suppliers, purchase orders and the delivery door.
 *
 * **Every quantity and every amount is a string**, for the reason `inventory.ts` gives: a line can
 * be 0.05 g of saffron, and `number` is how that becomes 0.05000000000000000277 on a table whose
 * whole purpose is that it adds up exactly. Nothing here is ever added on the client.
 *
 * **Three quantities per receipt line, and none of them is called `quantity`.** `quantity_invoiced`
 * is what the bill says, `quantity_received` is what the scale says, `quantity_rejected` is what
 * arrived and was refused. A single field named `quantity` would eventually be filled in with
 * whichever number the person had to hand, and `docs/waste-model.md` §1's report — *"Supplier A
 * short-delivered 4.2% this quarter — ₹18,400"* — would be unanswerable for ever.
 *
 * **Every derived figure comes off the server.** `accepted`, `short_delivery`, `order_shortfall`
 * and all four rupee values are response fields, computed once in
 * `app/services/procurement.py`. The receipt screen shows them *after* posting and never while
 * somebody is still typing a weight — `docs/waste-model.md` is explicit that showing the value of
 * a loss before it is recorded suppresses honest reporting.
 *
 * **There is no update or delete hook for a goods receipt.** It is append-only and the database
 * refuses both, so a hook implying otherwise would advertise something the server rejects. A
 * correction is a stock adjustment (`inventory.ts`'s `useAdjustStock`) referencing the receipt.
 */

const PROCUREMENT_KEY = ['staff', 'procurement'] as const;

export type Supplier = {
  id: string;
  name: string;
  contact_person: string | null;
  phone: string | null;
  email: string | null;
  gstin: string | null;
  payment_terms_days: number | null;
  is_active: boolean;
  deactivated_at: string | null;
};

export type OrderStatus = 'draft' | 'sent' | 'partial' | 'received' | 'cancelled';

export type OrderLine = {
  stock_item_id: string;
  quantity_ordered: string;
  unit_price: string;
};

export type PurchaseOrder = {
  id: string;
  po_number: string;
  supplier_id: string;
  status: OrderStatus;
  expected_at: string | null;
  total_amount: string;
  created_by: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  lines: OrderLine[];
};

export type ReceiptLine = {
  stock_item_id: string;
  quantity_invoiced: string;
  quantity_received: string;
  quantity_rejected: string;
  unit_price: string;
  rejection_reason: string | null;
};

export type GoodsReceipt = {
  id: string;
  purchase_order_id: string | null;
  supplier_id: string;
  received_at: string;
  business_date: string;
  invoice_number: string | null;
  invoice_amount: string | null;
  tax_amount: string | null;
  received_by: string | null;
  lines: ReceiptLine[];
};

/** One line as the server reported it back, with every derivation it computed. */
export type PostedLine = {
  stock_item_id: string;
  /** `null` for a market purchase: nothing was ordered, which is not the same as zero. */
  ordered: string | null;
  invoiced: string;
  received: string;
  rejected: string;
  /** `received − rejected`. The only quantity that reached a shelf. */
  accepted: string;
  /** `invoiced − received`. Billed and not delivered — the money leak. */
  short_delivery: string;
  order_shortfall: string | null;
  unit_price: string;
  /** Including the invoice's apportioned tax, which a 5%-scheme restaurant bears. */
  landed_unit_cost: string;
  short_delivery_value: string;
  accepted_value: string;
};

export type PostedReceipt = {
  receipt: GoodsReceipt;
  lines: PostedLine[];
  /** What the invoice's own lines add up to, before tax. When this and `invoice_amount` disagree
   *  by more than the tax, the supplier's arithmetic does not match their own line items. */
  invoice_line_total: string;
  short_delivery_value: string;
  accepted_value: string;
};

export type VarianceRow = {
  stock_item_id: string;
  code: string;
  name: string;
  base_unit: string;
  deliveries: number;
  invoiced: string;
  received: string;
  rejected: string;
  short_delivery: string;
  short_delivery_value: string;
};

export type SupplierVariance = {
  supplier_id: string;
  supplier_name: string;
  start: string;
  end: string;
  deliveries: number;
  invoiced: string;
  received: string;
  short_delivery_value: string;
  rows: VarianceRow[];
};

export type ReceiptLineInput = {
  stock_item_id: string;
  quantity_invoiced: string;
  quantity_received: string;
  quantity_rejected?: string;
  unit_price?: string;
  rejection_reason?: string | null;
};

// ---------------------------------------------------------------- reads

export function useSuppliers(includeInactive = true): UseQueryResult<{ suppliers: Supplier[] }> {
  return useQuery({
    queryKey: [...PROCUREMENT_KEY, 'suppliers', includeInactive],
    queryFn: () =>
      apiGet<{ suppliers: Supplier[] }>(
        `/staff/suppliers?include_inactive=${String(includeInactive)}`,
      ),
  });
}

export function usePurchaseOrders(status?: OrderStatus): UseQueryResult<{
  orders: PurchaseOrder[];
}> {
  return useQuery({
    queryKey: [...PROCUREMENT_KEY, 'orders', status ?? 'all'],
    queryFn: () =>
      apiGet<{ orders: PurchaseOrder[] }>(
        status === undefined ? '/staff/purchase-orders' : `/staff/purchase-orders?status=${status}`,
      ),
  });
}

export function usePurchaseOrder(orderId: string | undefined): UseQueryResult<PurchaseOrder> {
  return useQuery({
    queryKey: [...PROCUREMENT_KEY, 'order', orderId],
    // `?? ''` rather than a non-null assertion: `enabled` already stops the fetch, and an
    // assertion would be a lie the type system stops checking.
    queryFn: () => apiGet<PurchaseOrder>(`/staff/purchase-orders/${orderId ?? ''}`),
    enabled: orderId !== undefined,
  });
}

export function useGoodsReceipts(): UseQueryResult<{ receipts: GoodsReceipt[] }> {
  return useQuery({
    queryKey: [...PROCUREMENT_KEY, 'receipts'],
    queryFn: () => apiGet<{ receipts: GoodsReceipt[] }>('/staff/goods-receipts'),
  });
}

export function useSupplierVariance(
  supplierId: string | undefined,
): UseQueryResult<SupplierVariance> {
  return useQuery({
    queryKey: [...PROCUREMENT_KEY, 'variance', supplierId],
    queryFn: () => apiGet<SupplierVariance>(`/staff/suppliers/${supplierId ?? ''}/variance`),
    enabled: supplierId !== undefined,
  });
}

// ---------------------------------------------------------------- writes

/** Everything here invalidates the same root key.
 *
 * Deliberately coarse, as in `inventory.ts`. A delivery changes the order's status, the receipt
 * list, the supplier's variance report, the item's cost and the stock position — and a screen
 * showing a still-open order after its last crate was just booked in is worse than one extra
 * fetch. The stock ledger's own key is invalidated too, because receiving writes to it. */
function useProcurementMutation<TVariables, TData>(
  fn: (variables: TVariables) => Promise<TData>,
): UseMutationResult<TData, Error, TVariables> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: PROCUREMENT_KEY });
      void client.invalidateQueries({ queryKey: ['staff', 'stock-ledger'] });
    },
  });
}

export type SupplierInput = {
  name: string;
  contact_person?: string | null;
  phone?: string | null;
  email?: string | null;
  gstin?: string | null;
  payment_terms_days?: number | null;
};

export function useCreateSupplier(): UseMutationResult<Supplier, Error, SupplierInput> {
  return useProcurementMutation((input) => apiPost<Supplier>('/staff/suppliers', input));
}

export function useUpdateSupplier(): UseMutationResult<
  Supplier,
  Error,
  { supplierId: string; changes: Partial<SupplierInput> & { is_active?: boolean } }
> {
  return useProcurementMutation(({ supplierId, changes }) =>
    apiPatch<Supplier>(`/staff/suppliers/${supplierId}`, changes),
  );
}

export function useCreateOrder(): UseMutationResult<
  PurchaseOrder,
  Error,
  {
    supplier_id: string;
    lines: { stock_item_id: string; quantity_ordered: string; unit_price: string }[];
    expected_at?: string | null;
  }
> {
  // No `total_amount`. The server computes it from the lines; a client that could send a total
  // would be choosing what its own order cost (`docs/security.md` A04).
  return useProcurementMutation((input) => apiPost<PurchaseOrder>('/staff/purchase-orders', input));
}

export function useSendOrder(): UseMutationResult<PurchaseOrder, Error, string> {
  return useProcurementMutation((orderId) =>
    apiPost<PurchaseOrder>(`/staff/purchase-orders/${orderId}/send`),
  );
}

export function useCancelOrder(): UseMutationResult<
  PurchaseOrder,
  Error,
  { orderId: string; reason: string }
> {
  return useProcurementMutation(({ orderId, reason }) =>
    apiPost<PurchaseOrder>(`/staff/purchase-orders/${orderId}/cancel`, { reason }),
  );
}

export type ReceiveInput = {
  lines: ReceiptLineInput[];
  invoice_number?: string | null;
  invoice_amount?: string | null;
  tax_amount?: string | null;
};

export function useReceiveAgainstOrder(): UseMutationResult<
  PostedReceipt,
  Error,
  { orderId: string; body: ReceiveInput }
> {
  return useProcurementMutation(({ orderId, body }) =>
    apiPost<PostedReceipt>(`/staff/purchase-orders/${orderId}/receive`, body),
  );
}

export function useReceiveAdHoc(): UseMutationResult<
  PostedReceipt,
  Error,
  ReceiveInput & { supplier_id: string }
> {
  return useProcurementMutation((input) => apiPost<PostedReceipt>('/staff/goods-receipts', input));
}
