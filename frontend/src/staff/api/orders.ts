import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { ApiClientError, apiGet, apiPatch, apiPost } from '@shared/api';
import type {
  ChargeType,
  DiscountType,
  DocumentType,
  InvoiceStatus,
  OrderChannel,
  OrderLineStatus,
  OrderStatus,
  OrderType,
  PaymentMethod,
  PaymentStatus,
} from '@shared/enums';
import type { FoodType } from '@shared/ui/foodTypeMark';
import type { MenuVariant, ModifierGroup } from '@staff/api/menu';
import type { RestaurantTable } from '@staff/api/setup';

/**
 * Orders, from the table map to the settled invoice.
 *
 * **The client sends what was ordered, never what it costs.** No mutation here carries a price, a
 * tax or a total; the server prices every line from the menu and returns the whole order, and the
 * screen shows exactly that (`docs/security.md` A04). Every amount is a string, and nothing is
 * added up on this side (CLAUDE.md invariant 3).
 *
 * **Every change carries the version it read** (ADR 0010). A stale version is a 409 whose
 * `details.current_version` says what the server holds; the screen reloads the order rather than
 * overwriting it.
 *
 * **Each write puts the server's answer straight into the cache.** The server returns the whole
 * repriced order with its new version, so the screen updates the moment the response lands and the
 * next tap is made against the right version — without waiting on a refetch. That is short of the
 * fully optimistic UI `docs/ui/conventions.md` asks of the waiter surface, and the build log says so.
 */

const ORDERS_KEY = ['staff', 'orders'] as const;
const FLOOR_KEY = ['staff', 'orders', 'floor'] as const;

export type OrderLineModifier = { id: string; modifier_id: string; price_delta: string };

export type OrderLine = {
  id: string;
  menu_item_variant_id: string;
  quantity: number;
  unit_price: string;
  line_subtotal: string;
  line_discount: string;
  tax_regime: string;
  tax_rate: string;
  tax_inclusive: boolean;
  taxable_value: string;
  cgst_amount: string;
  sgst_amount: string;
  tax_amount: string;
  line_total: string;
  status: OrderLineStatus;
  sent_at: string | null;
  special_instructions: string | null;
  cancel_reason: string | null;
  seq: number;
  modifiers: OrderLineModifier[];
};

export type OrderDiscount = {
  id: string;
  order_line_id: string | null;
  type: DiscountType;
  rate: string | null;
  flat_amount: string | null;
  amount: string;
  reason: string;
  authorised_by: string;
};

export type OrderCharge = {
  id: string;
  type: ChargeType;
  amount: string;
  tax_rate: string | null;
  cgst_amount: string;
  sgst_amount: string;
  tax_amount: string;
  is_optional: boolean;
};

export type Order = {
  id: string;
  order_number: string;
  type: OrderType;
  channel: OrderChannel;
  external_order_id: string | null;
  status: OrderStatus;
  waiter_employee_id: string | null;
  /** Who is serving the table, by name. Null for a counter order or one nobody has claimed. */
  waiter: { id: string; full_name: string } | null;
  covers: number | null;
  parent_order_id: string | null;
  table_ids: string[];
  placed_at: string;
  first_sent_at: string | null;
  served_at: string | null;
  bill_requested_at: string | null;
  settled_at: string | null;
  cancelled_at: string | null;
  business_date: string;
  subtotal: string;
  discount_total: string;
  charge_total: string;
  tax_total: string;
  round_off: string;
  grand_total: string;
  cancel_reason: string | null;
  version: number;
  lines: OrderLine[];
  discounts: OrderDiscount[];
  charges: OrderCharge[];
  /** Set once the order is settled or voided, so a manager can reach its invoice. */
  invoice_id: string | null;
};

export type FloorOrder = {
  id: string;
  order_number: string;
  status: OrderStatus;
  grand_total: string;
  first_sent_at: string | null;
  bill_requested_at: string | null;
  version: number;
  waiter_name: string | null;
};

export type FloorTable = {
  id: string;
  code: string;
  seats: number;
  /** What the floor shows: `free` once a table's cleaning time has passed (backlog-issues B2). */
  status: RestaurantTable['status'];
  /** While a table is being cleared, when it counts as free by itself; null otherwise. */
  ready_at: string | null;
  orders: FloorOrder[];
};

export type FloorArea = { id: string; name: string; tables: FloorTable[] };

/** `busy`: a settled table skips cleaning right now — a busy window, or busy mode switched on. */
export type Floor = { areas: FloorArea[]; busy: boolean };

/** A dish as order taking needs it: every variant with its price, every question with its answers. */
export type OrderingItem = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  food_type: FoodType;
  station_id: string;
  image_url: string | null;
  is_active: boolean;
  variants: MenuVariant[];
  modifier_groups: ModifierGroup[];
};

export type OrderingCategory = {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
  items: OrderingItem[];
};

export type OrderingMenu = { version: number; categories: OrderingCategory[] };

export type Payment = {
  id: string;
  method: PaymentMethod;
  amount: string;
  tip_amount: string;
  reference: string | null;
  status: PaymentStatus;
  paid_at: string;
  credit_note_id: string | null;
};

export type Invoice = {
  id: string;
  order_id: string;
  document_type: DocumentType;
  invoice_number: string;
  financial_year: string;
  status: InvoiceStatus;
  issued_at: string;
  invoice_date: string;
  business_date: string;
  supplier_name: string;
  supplier_gstin: string | null;
  fssai_licence: string | null;
  recipient_name: string | null;
  recipient_gstin: string | null;
  sac_code: string;
  taxable_total: string;
  cgst_total: string;
  sgst_total: string;
  non_gst_tax_total: string;
  discount_total: string;
  charge_total: string;
  round_off: string;
  grand_total: string;
  cancelled_at: string | null;
  cancel_reason: string | null;
  payments: Payment[];
};

export type PaymentInput = { method: PaymentMethod; amount: string; reference?: string };

// ---------------------------------------------------------------- reads

/** The table map. Refetched when the waiter comes back to it, which is the moment it matters. */
export function useFloor(): UseQueryResult<Floor> {
  return useQuery({
    queryKey: FLOOR_KEY,
    queryFn: () => apiGet<Floor>('/staff/floor'),
    refetchOnWindowFocus: true,
  });
}

/** The whole menu in one request, under the menu key so a menu edit invalidates it. */
export function useOrderingMenu(): UseQueryResult<OrderingMenu> {
  return useQuery({
    queryKey: ['staff', 'menu', 'tree'],
    queryFn: () => apiGet<OrderingMenu>('/staff/menu'),
    staleTime: 60_000,
  });
}

export function useOrder(orderId: string | undefined): UseQueryResult<Order> {
  return useQuery({
    queryKey: [...ORDERS_KEY, 'order', orderId],
    queryFn: () => apiGet<Order>(`/staff/orders/${String(orderId)}`),
    enabled: orderId !== undefined,
  });
}

export function useInvoice(invoiceId: string | undefined): UseQueryResult<Invoice> {
  return useQuery({
    queryKey: [...ORDERS_KEY, 'invoice', invoiceId],
    queryFn: () => apiGet<Invoice>(`/staff/invoices/${String(invoiceId)}`),
    enabled: invoiceId !== undefined,
  });
}

// ---------------------------------------------------------------- writes

/**
 * Put the returned order in the cache and mark the floor stale. The floor is invalidated rather
 * than rewritten because a change to one order can change a table's status too.
 */
function useOrderMutation<TVariables>(
  fn: (variables: TVariables) => Promise<Order>,
): UseMutationResult<Order, Error, TVariables> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (order) => {
      client.setQueryData([...ORDERS_KEY, 'order', order.id], order);
      void client.invalidateQueries({ queryKey: FLOOR_KEY });
    },
    // A stale version means somebody else changed the order. Re-read it straight away, so the
    // screen shows what the server holds and the next tap is made against the right version.
    onError: (error, variables) => {
      const orderId = orderIdOf(variables);
      if (error instanceof ApiClientError && error.code === 'order.stale' && orderId !== null) {
        void client.invalidateQueries({ queryKey: [...ORDERS_KEY, 'order', orderId] });
      }
    },
  });
}

function orderIdOf(variables: unknown): string | null {
  if (typeof variables !== 'object' || variables === null || !('order' in variables)) {
    return null;
  }
  const { order } = variables as { order: { id?: unknown } };
  return typeof order.id === 'string' ? order.id : null;
}

/** What a line is called, from the menu the screen already loaded: a dish, its variant when the
 *  dish has more than one, and its options. Built once per menu, not per line. */
export type DishNames = { dishes: Map<string, string>; options: Map<string, string> };

export function dishNames(menu: OrderingMenu | undefined): DishNames {
  const dishes = new Map<string, string>();
  const options = new Map<string, string>();
  for (const item of (menu?.categories ?? []).flatMap((category) => category.items)) {
    for (const variant of item.variants) {
      dishes.set(
        variant.id,
        item.variants.length > 1 ? `${item.name} · ${variant.name}` : item.name,
      );
    }
    for (const modifier of item.modifier_groups.flatMap((group) => group.modifiers)) {
      options.set(modifier.id, modifier.name);
    }
  }
  return { dishes, options };
}

export type OpenOrderInput = {
  type: OrderType;
  table_ids: string[];
  covers?: number;
  /** Sent only by whoever holds order.assign, naming who serves the table. */
  waiter_employee_id?: string;
};

export function useOpenOrder(): UseMutationResult<Order, Error, OpenOrderInput> {
  return useOrderMutation((body) => apiPost<Order>('/staff/orders', body));
}

// ---------------------------------------------------------------- who is serving (2026-09-14)

export type WaiterOption = { id: string; full_name: string; employee_code: string };

/** Who can serve a table here, for choosing one. Only read by whoever holds order.assign. */
export function useWaiters(enabled: boolean): UseQueryResult<{ items: WaiterOption[] }> {
  return useQuery({
    queryKey: [...ORDERS_KEY, 'waiters'],
    queryFn: () => apiGet<{ items: WaiterOption[] }>('/staff/waiters'),
    enabled,
  });
}

/** Assign to me: a dine-in order nobody is serving. */
export function useClaimOrder(): UseMutationResult<Order, Error, { order: Order }> {
  return useOrderMutation(({ order }) =>
    apiPost<Order>(`/staff/orders/${order.id}/waiter/claim`, { version: order.version }),
  );
}

/** Move an order to another waiter, with a reason (order.assign). */
export function useMoveOrder(): UseMutationResult<
  Order,
  Error,
  { order: Order; employeeId: string | null; reason: string }
> {
  return useOrderMutation(({ order, employeeId, reason }) =>
    apiPost<Order>(`/staff/orders/${order.id}/waiter`, {
      version: order.version,
      employee_id: employeeId,
      reason,
    }),
  );
}

export type AddLineInput = {
  order: Order;
  variantId: string;
  quantity: number;
  modifierIds: string[];
  instructions?: string;
};

export function useAddLine(): UseMutationResult<Order, Error, AddLineInput> {
  return useOrderMutation(({ order, variantId, quantity, modifierIds, instructions }) =>
    apiPost<Order>(`/staff/orders/${order.id}/lines`, {
      version: order.version,
      menu_item_variant_id: variantId,
      quantity,
      modifier_ids: modifierIds,
      ...(instructions === undefined || instructions === ''
        ? {}
        : { special_instructions: instructions }),
    }),
  );
}

export function useChangeQuantity(): UseMutationResult<
  Order,
  Error,
  { order: Order; lineId: string; quantity: number }
> {
  return useOrderMutation(({ order, lineId, quantity }) =>
    apiPatch<Order>(`/staff/orders/${order.id}/lines/${lineId}`, {
      version: order.version,
      quantity,
    }),
  );
}

export function useRemoveLine(): UseMutationResult<
  Order,
  Error,
  { order: Order; lineId: string; reason?: string }
> {
  return useOrderMutation(({ order, lineId, reason }) =>
    apiPost<Order>(`/staff/orders/${order.id}/lines/${lineId}/remove`, {
      version: order.version,
      ...(reason === undefined ? {} : { reason }),
    }),
  );
}

/** Send, serve and ask for the bill carry nothing but the version. */
export function useOrderStep(
  step: 'send' | 'served' | 'bill',
): UseMutationResult<Order, Error, { order: Order }> {
  return useOrderMutation(({ order }) =>
    apiPost<Order>(`/staff/orders/${order.id}/${step}`, { version: order.version }),
  );
}

export function useCancelOrder(): UseMutationResult<
  Order,
  Error,
  { order: Order; reason: string }
> {
  return useOrderMutation(({ order, reason }) =>
    apiPost<Order>(`/staff/orders/${order.id}/cancel`, { version: order.version, reason }),
  );
}

/** Mark ready (backlog-issues B2): a table being cleared is free for the next party. */
export function useMarkReady(): UseMutationResult<FloorTable, Error, { tableId: string }> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ tableId }) => apiPost<FloorTable>(`/staff/floor/tables/${tableId}/ready`, {}),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: FLOOR_KEY });
    },
  });
}

/** Busy mode from the floor: settled tables skip cleaning until the next business day. */
export function useSetBusy(): UseMutationResult<{ busy: boolean }, Error, { on: boolean }> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiPost<{ busy: boolean }>('/staff/floor/busy', body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: FLOOR_KEY });
    },
  });
}

export function useSplit(): UseMutationResult<Order, Error, { order: Order; lineIds: string[] }> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ order, lineIds }) =>
      apiPost<Order>(`/staff/orders/${order.id}/split`, {
        version: order.version,
        line_ids: lineIds,
      }),
    // The original's version moved too, and the response is the *new* order, so both are re-read.
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ORDERS_KEY });
    },
  });
}

/**
 * Settle. `idempotencyKey` comes from `useIdempotencyKey` in the screen, made once per bill, so a
 * Settle tapped twice on a stalled connection charges the table once (ADR 0010).
 */
export function useSettle(): UseMutationResult<
  Invoice,
  Error,
  { order: Order; payments: PaymentInput[]; idempotencyKey: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ order, payments, idempotencyKey }) =>
      apiPost<Invoice>(
        `/staff/orders/${order.id}/settle`,
        { version: order.version, payments },
        { idempotencyKey },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ORDERS_KEY });
    },
  });
}

// ---------------------------------------------------------------- after settlement (chunk K)

export type OrderSummary = Omit<Order, 'lines' | 'discounts' | 'charges' | 'invoice_id'>;

export type OrderPage = { items: OrderSummary[]; next_cursor: string | null };

/**
 * One business day's settled and cancelled bills, a page at a time: where the manager who has to
 * credit a dish starts. A full page offers the next one rather than stopping without a word, which
 * is how M01's staff list once hid everyone after the fiftieth.
 */
export function useBills(businessDate: string, cursor: string | null): UseQueryResult<OrderPage> {
  return useQuery({
    queryKey: [...ORDERS_KEY, 'bills', businessDate, cursor],
    queryFn: () => {
      const query = new URLSearchParams([
        ['status', 'settled'],
        ['status', 'voided'],
        ['business_date', businessDate],
      ]);
      if (cursor !== null) {
        query.append('cursor', cursor);
      }
      return apiGet<OrderPage>(`/staff/orders?${query.toString()}`);
    },
  });
}

export type CreditNoteLine = {
  id: string;
  order_line_id: string;
  quantity: number;
  taxable_value: string;
  cgst_amount: string;
  sgst_amount: string;
  tax_amount: string;
  line_total: string;
};

export type CreditNote = {
  id: string;
  invoice_id: string;
  credit_note_number: string;
  financial_year: string;
  issued_at: string;
  note_date: string;
  business_date: string;
  reason: string;
  issued_by: string;
  taxable_total: string;
  cgst_total: string;
  sgst_total: string;
  non_gst_tax_total: string;
  grand_total: string;
  lines: CreditNoteLine[];
  refunds: Payment[];
};

export type CreditLineInput = { order_line_id: string; quantity: number };

/** Sent positive; the server stores it as a negative payment naming the credit note. */
export type RefundInput = { method: PaymentMethod; amount: string; reference?: string };

/** Withdraw an invoice issued in error. Idempotent (ADR 0010): a double tap withdraws it once. */
export function useCancelInvoice(): UseMutationResult<
  Invoice,
  Error,
  { invoiceId: string; reason: string; idempotencyKey: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ invoiceId, reason, idempotencyKey }) =>
      apiPost<Invoice>(`/staff/invoices/${invoiceId}/cancel`, { reason }, { idempotencyKey }),
    onSuccess: (invoice) => {
      client.setQueryData([...ORDERS_KEY, 'invoice', invoice.id], invoice);
      void client.invalidateQueries({ queryKey: ORDERS_KEY });
    },
  });
}

/**
 * Reduce a settled bill by whole dishes, with any money given back. A refund changes what the till
 * should hold, so the till is re-read as well as the bill.
 */
export function useCreditNote(): UseMutationResult<
  CreditNote,
  Error,
  {
    invoiceId: string;
    reason: string;
    lines: CreditLineInput[];
    refunds: RefundInput[];
    idempotencyKey: string;
  }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ invoiceId, reason, lines, refunds, idempotencyKey }) =>
      apiPost<CreditNote>(
        `/staff/invoices/${invoiceId}/credit-notes`,
        { reason, lines, refunds },
        { idempotencyKey },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ORDERS_KEY });
      void client.invalidateQueries({ queryKey: ['staff', 'cash'] });
    },
  });
}
