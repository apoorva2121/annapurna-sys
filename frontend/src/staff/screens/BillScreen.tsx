import { Fragment, type ReactElement, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import type { PaymentMethod } from '@shared/enums';
import { formatDelta, formatINR, parseAmount, percentToFraction } from '@shared/money';
import { Permission } from '@shared/permissions';
import { Button } from '@shared/ui/button';
import { useIdempotencyKey } from '@shared/useIdempotencyKey';
import { useAuth } from '@staff/auth/AuthContext';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { WaiterSurface } from '@staff/components/WaiterSurface';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type DiscountInput,
  type Invoice,
  type Order,
  type PaymentInput,
  dishNames,
  useAddDiscount,
  useAddServiceCharge,
  useOrder,
  useOrderingMenu,
  useRemoveCharge,
  useRemoveDiscount,
  useSettle,
  useSplit,
} from '@staff/api/orders';

/**
 * The provisional bill, splitting it, and settling it.
 *
 * **Provisional until settled, and it says so.** The pre-settlement printout carries the order number
 * and never an invoice number, because the invoice number is allocated at settlement and not before
 * (spec decision 1) — an order cancelled after its bill was shown then leaves no gap in the series.
 *
 * **Every figure is the server's.** Subtotal, discounts, charges, tax and the total arrive as strings
 * and are shown, never added up here (CLAUDE.md invariant 3). One payment sends the bill's own
 * `grand_total`, untyped.
 *
 * **"We'll pay separately" is several payments on one bill** (spec decision 9) — overwhelmingly
 * several UPI payments. Each amount is typed, and **the screen does not add them up**: the server
 * checks that they cover the bill exactly and says by how much they do not. **"Put the corporate lunch
 * on its own invoice" is a split by dishes**, which moves the ticked dishes to a separate order on the
 * same table before anything is settled; each then settles to its own invoice.
 *
 * **One idempotency key per bill** (ADR 0010). A Settle tapped twice on a stalled connection is the
 * same settlement, and replays rather than charging the table twice. A refused attempt stores
 * nothing, so correcting an amount and settling again under the same key is a fresh attempt.
 */
export default function BillScreen(): ReactElement {
  const { orderId } = useParams<{ orderId: string }>();
  const order = useOrder(orderId);
  return (
    <WaiterSurface>
      <QueryState
        isPending={order.isPending}
        error={order.error}
        pendingLabel={strings.orders.loadingOrder}
      >
        {order.data !== undefined && <Bill order={order.data} />}
      </QueryState>
    </WaiterSurface>
  );
}

const METHODS: PaymentMethod[] = ['upi', 'cash', 'card'];

const OFF_THE_BILL: ReadonlySet<string> = new Set(['cancelled', 'returned']);

type PaymentRow = { id: number; method: PaymentMethod; amount: string };

/** The payments to send, or the problem to show instead. */
function paymentsFor(order: Order, rows: PaymentRow[]): PaymentInput[] | string {
  const only = rows[0];
  if (rows.length === 1 && only !== undefined) {
    return [{ method: only.method, amount: order.grand_total }];
  }
  const payments: PaymentInput[] = [];
  for (const row of rows) {
    const amount = parseAmount(row.amount);
    if (amount === null) {
      return strings.orders.amountProblem;
    }
    payments.push({ method: row.method, amount });
  }
  return payments;
}

function Bill({ order }: { order: Order }): ReactElement {
  const settle = useSettle();
  const submission = useIdempotencyKey();
  const nextRow = useRef(1);
  const [rows, setRows] = useState<PaymentRow[]>([{ id: 0, method: 'upi', amount: '' }]);
  const [problem, setProblem] = useState<string | null>(null);
  const [invoice, setInvoice] = useState<Invoice | null>(null);

  if (invoice !== null) {
    return <Settled invoice={invoice} />;
  }

  function onSettle(): void {
    const payments = paymentsFor(order, rows);
    if (typeof payments === 'string') {
      setProblem(payments);
      return;
    }
    setProblem(null);
    settle.mutate(
      { order, payments, idempotencyKey: submission.key },
      {
        onSuccess: (result) => {
          submission.renew();
          setInvoice(result);
        },
      },
    );
  }

  function addRow(): void {
    const id = nextRow.current;
    nextRow.current += 1;
    setRows((current) => [...current, { id, method: 'upi', amount: '' }]);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <Link to={`/orders/${order.id}`} className="min-h-target underline">
          {strings.orders.orderLabel(order.order_number)}
        </Link>
        <h1 className="text-2xl font-semibold">{strings.orders.billTitle}</h1>
      </div>
      <p className="text-sm text-muted-foreground">{strings.orders.provisional}</p>
      {problem !== null && <Notice tone="critical" title={problem} />}
      {settle.isError && <Notice tone="critical" {...errorProps(settle.error)} />}
      <Totals order={order} />
      <ServiceCharge order={order} />
      <Discounts order={order} />
      <PaymentRows
        rows={rows}
        onChange={(id, patch) => {
          setRows((current) => current.map((row) => (row.id === id ? { ...row, ...patch } : row)));
        }}
        onRemove={(id) => {
          setRows((current) => current.filter((row) => row.id !== id));
        }}
      />
      <Button variant="secondary" onClick={addRow}>
        {rows.length === 1 ? strings.orders.splitPayment : strings.orders.addPayment}
      </Button>
      <SplitByDishes order={order} />
      <div className="sticky bottom-0 flex justify-end border-t border-border bg-background py-3">
        <Button size="lg" disabled={settle.isPending} onClick={onSettle}>
          {settle.isPending
            ? strings.orders.settling
            : strings.orders.settle(formatINR(order.grand_total))}
        </Button>
      </div>
    </div>
  );
}

function Totals({ order }: { order: Order }): ReactElement {
  // String comparisons against "0.00", never arithmetic: whether to show a row is not a sum.
  const rows = [
    { label: strings.orders.subtotal, value: formatINR(order.subtotal) },
    ...(order.discount_total === '0.00'
      ? []
      : [{ label: strings.orders.discounts, value: formatDelta(`-${order.discount_total}`) }]),
    ...(order.charge_total === '0.00'
      ? []
      : [{ label: strings.orders.charges, value: formatINR(order.charge_total) }]),
    { label: strings.orders.tax, value: formatINR(order.tax_total) },
  ];
  return (
    <dl className="grid grid-cols-2 gap-y-2">
      {rows.map((row) => (
        <Fragment key={row.label}>
          <dt>{row.label}</dt>
          <dd className="text-right font-mono tabular-nums">{row.value}</dd>
        </Fragment>
      ))}
      <dt className="text-lg font-semibold">{strings.orders.total}</dt>
      <dd className="text-right font-mono text-lg font-semibold tabular-nums">
        {formatINR(order.grand_total)}
      </dd>
    </dl>
  );
}

function PaymentRows({
  rows,
  onChange,
  onRemove,
}: {
  rows: PaymentRow[];
  onChange: (id: number, patch: Partial<PaymentRow>) => void;
  onRemove: (id: number) => void;
}): ReactElement {
  const split = rows.length > 1;
  return (
    <div className="flex flex-col gap-4">
      {rows.map((row, index) => (
        <fieldset key={row.id} className="flex flex-col gap-2">
          <legend className="font-semibold">
            {split ? strings.orders.paymentLabel(index + 1) : strings.orders.paidBy}
          </legend>
          <MethodChoice
            value={row.method}
            onChange={(method) => {
              onChange(row.id, { method });
            }}
          />
          {split && (
            <div className="flex items-end gap-2">
              <Field
                label={strings.orders.amountFor(index + 1)}
                inputMode="decimal"
                value={row.amount}
                onChange={(event) => {
                  onChange(row.id, { amount: event.target.value });
                }}
              />
              <Button
                variant="ghost"
                onClick={() => {
                  onRemove(row.id);
                }}
              >
                {strings.orders.removePayment}
              </Button>
            </div>
          )}
        </fieldset>
      ))}
    </div>
  );
}

function MethodChoice({
  value,
  onChange,
}: {
  value: PaymentMethod;
  onChange: (method: PaymentMethod) => void;
}): ReactElement {
  return (
    <div className="grid grid-cols-3 gap-2">
      {METHODS.map((method) => {
        const selected = method === value;
        return (
          <Button
            key={method}
            variant={selected ? 'primary' : 'secondary'}
            aria-pressed={selected}
            onClick={() => {
              onChange(method);
            }}
          >
            {`${selected ? '✓ ' : ''}${strings.orders.methods[method] ?? method}`}
          </Button>
        );
      })}
    </div>
  );
}

function SplitByDishes({ order }: { order: Order }): ReactElement | null {
  const split = useSplit();
  const menu = useOrderingMenu();
  const names = useMemo(() => dishNames(menu.data), [menu.data]);
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<string[]>([]);
  const [moved, setMoved] = useState<Order | null>(null);
  const billable = order.lines.filter((line) => !OFF_THE_BILL.has(line.status));

  if (moved !== null) {
    return (
      <Notice tone="success" title={strings.orders.movedTitle}>
        <Link to={`/orders/${moved.id}/bill`} className="underline">
          {strings.orders.openMoved(moved.order_number)}
        </Link>
      </Notice>
    );
  }
  // One dish cannot be split from itself, and moving every dish is just moving the bill.
  if (billable.length < 2) {
    return null;
  }
  if (!open) {
    return (
      <Button
        variant="secondary"
        onClick={() => {
          setOpen(true);
        }}
      >
        {strings.orders.splitDishes}
      </Button>
    );
  }

  function toggle(lineId: string): void {
    setChosen((current) =>
      current.includes(lineId) ? current.filter((id) => id !== lineId) : [...current, lineId],
    );
  }

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="font-semibold">{strings.orders.splitDishes}</legend>
      <p className="text-sm text-muted-foreground">{strings.orders.splitDishesHint}</p>
      {split.isError && <Notice tone="critical" {...errorProps(split.error)} />}
      {billable.map((line) => (
        <label key={line.id} className="flex min-h-target items-center gap-3">
          <input
            type="checkbox"
            checked={chosen.includes(line.id)}
            onChange={() => {
              toggle(line.id);
            }}
          />
          <span className="flex-1">
            {`${String(line.quantity)} × ${names.dishes.get(line.menu_item_variant_id) ?? ''}`}
          </span>
          <span className="font-mono tabular-nums">{formatINR(line.line_total)}</span>
        </label>
      ))}
      <Button
        variant="secondary"
        disabled={chosen.length === 0 || chosen.length === billable.length || split.isPending}
        onClick={() => {
          split.mutate(
            { order, lineIds: chosen },
            {
              onSuccess: (child) => {
                setChosen([]);
                setOpen(false);
                setMoved(child);
              },
            },
          );
        }}
      >
        {split.isPending ? strings.orders.moving : strings.orders.moveDishes}
      </Button>
    </fieldset>
  );
}

function Settled({ invoice }: { invoice: Invoice }): ReactElement {
  return (
    <div className="flex flex-col gap-4">
      <Notice tone="success" title={strings.orders.settledTitle}>
        {strings.orders.invoiceNumber(invoice.invoice_number)}
      </Notice>
      <Button asChild size="lg">
        <Link to="/floor">{strings.orders.nextTable}</Link>
      </Button>
    </div>
  );
}

/** The optional service charge (CCPA guidelines): added at the restaurant's own rate, never typed,
 *  and always removable when the guest asks. */
function ServiceCharge({ order }: { order: Order }): ReactElement | null {
  const { can } = useAuth();
  const add = useAddServiceCharge();
  const remove = useRemoveCharge();
  if (!can(Permission.ORDER_MODIFY)) {
    return null;
  }
  const charge = order.charges.find((row) => row.type === 'service_charge');
  const pending = add.isPending || remove.isPending;
  return (
    <div className="flex flex-col gap-2">
      {add.isError && <Notice tone="critical" {...errorProps(add.error)} />}
      {remove.isError && <Notice tone="critical" {...errorProps(remove.error)} />}
      {charge === undefined ? (
        <Button
          variant="secondary"
          disabled={pending}
          onClick={() => {
            add.mutate({ order });
          }}
        >
          {strings.orders.addServiceCharge}
        </Button>
      ) : (
        <div className="flex items-center justify-between gap-3">
          <span>{strings.orders.serviceCharge}</span>
          <span className="whitespace-nowrap font-mono tabular-nums">
            {formatINR(charge.amount)}
          </span>
          <Button
            variant="ghost"
            disabled={pending}
            onClick={() => {
              remove.mutate({ order, chargeId: charge.id });
            }}
          >
            {strings.orders.removeServiceCharge}
          </Button>
        </div>
      )}
    </div>
  );
}

type DiscountKind = 'percentage' | 'flat' | 'comp';

type DiscountDraft = {
  kind: DiscountKind;
  value: string;
  lineId: string | null;
  reason: string | null;
  note: string;
};

const OTHER_REASON = 'Other';

/** The reason as it is recorded: the chosen one, then the note after a colon when there is one. */
function reasonOrProblem(draft: DiscountDraft): string | { problem: string } {
  const note = draft.note.trim();
  if (draft.reason === null) {
    return { problem: strings.orders.chooseReason };
  }
  if (draft.reason === OTHER_REASON && note === '') {
    return { problem: strings.orders.otherNeedsNote };
  }
  return note === '' ? draft.reason : `${draft.reason}: ${note}`;
}

/** What comes off, as the API takes it: a fraction, an amount, or a comp's whole. Never a float. */
function sizeOrProblem(draft: DiscountDraft): Pick<DiscountInput, 'rate' | 'flat_amount'> | string {
  if (draft.kind === 'comp') {
    return { rate: '1.0000' };
  }
  if (draft.kind === 'flat') {
    const amount = parseAmount(draft.value);
    return amount === null ? strings.orders.amountOffProblem : { flat_amount: amount };
  }
  const rate = percentToFraction(draft.value);
  return rate === null ? strings.orders.percentProblem : { rate };
}

function discountOrProblem(draft: DiscountDraft): DiscountInput | string {
  const size = sizeOrProblem(draft);
  if (typeof size === 'string') {
    return size;
  }
  const reason = reasonOrProblem(draft);
  if (typeof reason !== 'string') {
    return reason.problem;
  }
  return {
    type: draft.kind,
    ...size,
    ...(draft.lineId === null ? {} : { order_line_id: draft.lineId }),
    reason,
  };
}

const EMPTY_DRAFT: DiscountDraft = {
  kind: 'percentage',
  value: '',
  lineId: null,
  reason: null,
  note: '',
};

/** The discounts already on the bill, each with the one way to take it off again. */
function GivenDiscounts({ order }: { order: Order }): ReactElement | null {
  const remove = useRemoveDiscount();
  if (order.discounts.length === 0) {
    return null;
  }
  return (
    <>
      <ul className="flex flex-col">
        {order.discounts.map((row) => (
          <li key={row.id} className="flex items-center justify-between gap-3 py-1">
            <span className="flex-1">{row.reason}</span>
            <span className="whitespace-nowrap font-mono tabular-nums">
              {formatDelta(`-${row.amount}`)}
            </span>
            <Button
              variant="ghost"
              disabled={remove.isPending}
              onClick={() => {
                remove.mutate({ order, discountId: row.id });
              }}
            >
              {strings.orders.removeDiscount}
            </Button>
          </li>
        ))}
      </ul>
      {remove.isError && <Notice tone="critical" {...errorProps(remove.error)} />}
    </>
  );
}

/**
 * Discounts and comps (decision D2, backlog-issues B7). Only for whoever holds `order.discount`, who
 * the server records as the authoriser. The reason is chosen from a short list, so the monthly
 * comps-by-authoriser report can group them; a note adds the particulars. No second approval — the
 * report is the check, and a comp is audited when it is added and when it is removed.
 */
function Discounts({ order }: { order: Order }): ReactElement | null {
  const { can } = useAuth();
  const add = useAddDiscount();
  const menu = useOrderingMenu();
  const names = useMemo(() => dishNames(menu.data), [menu.data]);
  const [draft, setDraft] = useState<DiscountDraft>(EMPTY_DRAFT);
  const [problem, setProblem] = useState<string | null>(null);
  if (!can(Permission.ORDER_DISCOUNT)) {
    return null;
  }
  const billable = order.lines.filter((line) => !OFF_THE_BILL.has(line.status));
  const change = (patch: Partial<DiscountDraft>): void => {
    setDraft((current) => ({ ...current, ...patch }));
  };

  function onApply(): void {
    const discount = discountOrProblem(draft);
    if (typeof discount === 'string') {
      setProblem(discount);
      return;
    }
    setProblem(null);
    add.mutate(
      { order, discount },
      {
        onSuccess: () => {
          setDraft(EMPTY_DRAFT);
        },
      },
    );
  }

  return (
    <section className="flex flex-col gap-3 border-t border-border pt-4">
      <h2 className="text-lg font-semibold">{strings.orders.discountsTitle}</h2>
      <GivenDiscounts order={order} />
      {problem !== null && <Notice tone="critical" title={problem} />}
      {add.isError && <Notice tone="critical" {...errorProps(add.error)} />}
      <Choice
        legend={strings.orders.discountKind}
        name="discount-kind"
        options={(['percentage', 'flat', 'comp'] as const).map((kind) => ({
          value: kind,
          label: strings.orders.discountKinds[kind],
        }))}
        chosen={draft.kind}
        onChoose={(kind) => {
          change({ kind: kind as DiscountKind, value: '' });
        }}
      />
      {draft.kind !== 'comp' && (
        <Field
          label={draft.kind === 'flat' ? strings.orders.amountOff : strings.orders.percentOff}
          inputMode="decimal"
          value={draft.value}
          onChange={(event) => {
            change({ value: event.target.value });
          }}
        />
      )}
      <Choice
        legend={strings.orders.comesOff}
        name="discount-line"
        options={[
          { value: '', label: strings.orders.wholeBill },
          ...billable.map((line) => ({
            value: line.id,
            label: names.dishes.get(line.menu_item_variant_id) ?? '',
          })),
        ]}
        chosen={draft.lineId ?? ''}
        onChoose={(lineId) => {
          change({ lineId: lineId === '' ? null : lineId });
        }}
      />
      <Choice
        legend={strings.orders.discountReason}
        name="discount-reason"
        options={strings.orders.discountReasons.map((reason) => ({ value: reason, label: reason }))}
        chosen={draft.reason ?? ''}
        onChoose={(reason) => {
          change({ reason });
        }}
      />
      <Field
        label={strings.orders.discountNote}
        value={draft.note}
        maxLength={200}
        onChange={(event) => {
          change({ note: event.target.value });
        }}
      />
      <Button variant="secondary" disabled={add.isPending} onClick={onApply}>
        {add.isPending ? strings.orders.applying : strings.orders.apply}
      </Button>
    </section>
  );
}

/** A radio group with a thumb-sized row per option. */
function Choice({
  legend,
  name,
  options,
  chosen,
  onChoose,
}: {
  legend: string;
  name: string;
  options: { value: string; label: string }[];
  chosen: string;
  onChoose: (value: string) => void;
}): ReactElement {
  return (
    <fieldset className="flex flex-col">
      <legend className="font-semibold">{legend}</legend>
      {options.map((option) => (
        <label key={option.value} className="flex min-h-target items-center gap-3">
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={chosen === option.value}
            onChange={() => {
              onChoose(option.value);
            }}
          />
          {option.label}
        </label>
      ))}
    </fieldset>
  );
}
