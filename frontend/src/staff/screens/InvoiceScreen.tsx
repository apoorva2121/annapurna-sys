import { Fragment, type ReactElement, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import type { PaymentMethod } from '@shared/enums';
import { formatDelta, formatINR, parseAmount } from '@shared/money';
import { Button } from '@shared/ui/button';
import { FoodTypeMark } from '@shared/ui/foodTypeMark';
import { useIdempotencyKey } from '@shared/useIdempotencyKey';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QuantityStepper } from '@staff/components/QuantityStepper';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type CreditLineInput,
  type CreditNote,
  type CreditNoteSummary,
  type DishNames,
  type Invoice,
  type Order,
  type RefundInput,
  dishNames,
  useCancelInvoice,
  useCreditNote,
  useInvoice,
  useOrder,
  useOrderingMenu,
} from '@staff/api/orders';

/**
 * One settled bill, and the only two things that may happen to it afterwards.
 *
 * **Nothing here edits the bill** (CLAUDE.md invariant 6). Both actions issue a new document:
 *
 * - **A credit note** reduces the invoice by whole dishes, with any money given back recorded as a
 *   refund against it (spec decision 2). It is the primary action because it is the ordinary one: a
 *   dish sent back, a dish that never came.
 * - **Cancelling the invoice** is for one issued in error — billed to the wrong table — on its own
 *   business day and while nothing has been credited. It sits behind a second tap and asks what the
 *   error was, because it withdraws a legal document. The server holds each condition and says which
 *   one failed; this screen does not guess at business days.
 *
 * **Portions are chosen with a stepper, from none up to what was billed**, never typed. What a
 * portion is worth, its tax and the note's total are the server's: this screen sends dishes and counts
 * and shows the note that comes back. The refund is typed by whoever hands the money over, and the
 * server refuses one larger than the note.
 */
export default function InvoiceScreen(): ReactElement {
  const { orderId } = useParams<{ orderId: string }>();
  const order = useOrder(orderId);
  const invoiceId = order.data?.invoice_id ?? undefined;
  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <Link data-back to="/bills" className="min-h-target underline">
        {strings.bills.backToBills}
      </Link>
      <QueryState
        isPending={order.isPending}
        error={order.error}
        pendingLabel={strings.bills.loadingInvoice}
      >
        {order.data !== undefined &&
          (invoiceId === undefined ? (
            <p className="text-muted-foreground">{strings.bills.notSettled}</p>
          ) : (
            <LoadedInvoice order={order.data} invoiceId={invoiceId} />
          ))}
      </QueryState>
    </div>
  );
}

function LoadedInvoice({ order, invoiceId }: { order: Order; invoiceId: string }): ReactElement {
  const invoice = useInvoice(invoiceId);
  const menu = useOrderingMenu();
  const names = useMemo(() => dishNames(menu.data), [menu.data]);
  return (
    <QueryState
      isPending={invoice.isPending}
      error={invoice.error}
      pendingLabel={strings.bills.loadingInvoice}
    >
      {invoice.data !== undefined && (
        <InvoiceDetail order={order} invoice={invoice.data} names={names} />
      )}
    </QueryState>
  );
}

const OFF_THE_BILL: ReadonlySet<string> = new Set(['cancelled', 'returned']);

function InvoiceDetail({
  order,
  invoice,
  names,
}: {
  order: Order;
  invoice: Invoice;
  names: DishNames;
}): ReactElement {
  const [note, setNote] = useState<CreditNote | null>(null);
  const cancelled = invoice.status === 'cancelled';
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">
          {strings.bills.invoiceTitle(invoice.invoice_number)}
        </h1>
        <p>
          {`${strings.bills.statuses[invoice.status] ?? invoice.status} · ${strings.orders.orderLabel(order.order_number)}`}
        </p>
      </div>
      {cancelled && (
        <Notice tone="info" title={strings.bills.cancelledTitle}>
          {invoice.cancel_reason ?? undefined}
        </Notice>
      )}
      <InvoiceTotals invoice={invoice} />
      <Payments invoice={invoice} />
      <CreditNotes order={order} invoice={invoice} names={names} />
      {note !== null && (
        <IssuedNote
          note={note}
          onAnother={() => {
            setNote(null);
          }}
        />
      )}
      {!cancelled && note === null && (
        <CreditNoteForm order={order} invoice={invoice} names={names} onIssued={setNote} />
      )}
      {!cancelled && note === null && <CancelInvoice invoice={invoice} />}
    </div>
  );
}

function InvoiceTotals({ invoice }: { invoice: Invoice }): ReactElement {
  // Whether to show a row is a string comparison against "0.00", never a sum.
  const rows = [
    ...(invoice.discount_total === '0.00'
      ? []
      : [{ label: strings.bills.discounts, value: formatDelta(`-${invoice.discount_total}`) }]),
    ...(invoice.charge_total === '0.00'
      ? []
      : [{ label: strings.bills.charges, value: formatINR(invoice.charge_total) }]),
    { label: strings.bills.taxable, value: formatINR(invoice.taxable_total) },
    { label: strings.bills.cgst, value: formatINR(invoice.cgst_total) },
    { label: strings.bills.sgst, value: formatINR(invoice.sgst_total) },
    ...(invoice.non_gst_tax_total === '0.00'
      ? []
      : [{ label: strings.bills.otherTax, value: formatINR(invoice.non_gst_tax_total) }]),
  ];
  return (
    <dl className="grid grid-cols-2 gap-y-2">
      {rows.map((row) => (
        <Fragment key={row.label}>
          <dt>{row.label}</dt>
          <dd className="text-right font-mono tabular-nums">{row.value}</dd>
        </Fragment>
      ))}
      <dt className="text-lg font-semibold">{strings.bills.total}</dt>
      <dd className="text-right font-mono text-lg font-semibold tabular-nums">
        {formatINR(invoice.grand_total)}
      </dd>
    </dl>
  );
}

function Payments({ invoice }: { invoice: Invoice }): ReactElement {
  return (
    <section className="flex flex-col gap-1">
      <h2 className="text-lg font-semibold">{strings.bills.paymentsTitle}</h2>
      <ul>
        {invoice.payments.map((payment) => {
          const refund = payment.amount.startsWith('-');
          const method = strings.orders.methods[payment.method] ?? payment.method;
          return (
            <li key={payment.id} className="flex justify-between gap-3">
              <span>{refund ? `${strings.bills.refund} · ${method}` : method}</span>
              <span className="font-mono tabular-nums">
                {refund ? formatDelta(payment.amount) : formatINR(payment.amount)}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

type RefundChoice = PaymentMethod | 'none';

const REFUND_METHODS: RefundChoice[] = ['none', 'cash', 'upi', 'card'];

function CreditNoteForm({
  order,
  invoice,
  names,
  onIssued,
}: {
  order: Order;
  invoice: Invoice;
  names: DishNames;
  onIssued: (note: CreditNote) => void;
}): ReactElement {
  const credit = useCreditNote();
  const submission = useIdempotencyKey();
  const billed = order.lines.filter((line) => !OFF_THE_BILL.has(line.status));
  // What earlier credit notes took off each dish, so this one offers only what is left (B6).
  const credited = new Map((invoice.credited ?? []).map((row) => [row.order_line_id, row]));
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [reason, setReason] = useState('');
  const [refundMethod, setRefundMethod] = useState<RefundChoice>('none');
  const [refundAmount, setRefundAmount] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  function refundsOrProblem(): RefundInput[] | string {
    if (refundMethod === 'none') {
      return [];
    }
    const amount = parseAmount(refundAmount);
    return amount === null ? strings.bills.refundAmountNeeded : [{ method: refundMethod, amount }];
  }

  function onIssue(): void {
    const lines: CreditLineInput[] = billed
      .map((line) => ({ order_line_id: line.id, quantity: counts[line.id] ?? 0 }))
      .filter((line) => line.quantity > 0);
    const refunds = refundsOrProblem();
    const found =
      lines.length === 0
        ? strings.bills.noDishes
        : reason.trim().length < 3
          ? strings.bills.reasonNeeded
          : typeof refunds === 'string'
            ? refunds
            : null;
    setProblem(found);
    if (found !== null || typeof refunds === 'string') {
      return;
    }
    credit.mutate(
      {
        invoiceId: invoice.id,
        reason: reason.trim(),
        lines,
        refunds,
        idempotencyKey: submission.key,
      },
      {
        onSuccess: (note) => {
          submission.renew();
          onIssued(note);
        },
      },
    );
  }

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-border p-4">
      <h2 className="text-lg font-semibold">{strings.bills.creditTitle}</h2>
      <p className="text-sm text-muted-foreground">{strings.bills.creditIntro}</p>
      {problem !== null && <Notice tone="critical" title={problem} />}
      {credit.isError && <Notice tone="critical" {...errorProps(credit.error)} />}
      <ul className="flex flex-col">
        {billed.map((line) => {
          const dish = names.dishes.get(line.menu_item_variant_id) ?? '';
          return (
            <li
              key={line.id}
              className="flex items-center justify-between gap-3 border-b border-border py-2"
            >
              <span>
                <span className="flex items-center gap-2">
                  {/* brand.md §8.8 - named to a guest, so it carries the mark. */}
                  <FoodTypeMark
                    foodType={names.foodTypes.get(line.menu_item_variant_id) ?? 'veg'}
                  />
                  {dish}
                </span>
                <span className="text-sm text-muted-foreground">
                  {strings.bills.billedCount(line.quantity, formatINR(line.line_total))}
                </span>
                {credited.has(line.id) && (
                  <span className="block text-sm text-muted-foreground">
                    {strings.bills.alreadyCredited(
                      credited.get(line.id)?.quantity ?? 0,
                      formatINR(credited.get(line.id)?.amount),
                    )}
                  </span>
                )}
              </span>
              <QuantityStepper
                value={counts[line.id] ?? 0}
                min={0}
                max={line.quantity - (credited.get(line.id)?.quantity ?? 0)}
                label={dish}
                disabled={credit.isPending}
                onChange={(next) => {
                  setCounts((current) => ({ ...current, [line.id]: next }));
                }}
              />
            </li>
          );
        })}
      </ul>
      <Field
        label={strings.bills.reason}
        value={reason}
        onChange={(event) => {
          setReason(event.target.value);
        }}
      />
      <fieldset className="flex flex-col gap-2">
        <legend className="font-medium">{strings.bills.refundLegend}</legend>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {REFUND_METHODS.map((method) => {
            const selected = method === refundMethod;
            return (
              <Button
                key={method}
                variant={selected ? 'primary' : 'secondary'}
                aria-pressed={selected}
                onClick={() => {
                  setRefundMethod(method);
                }}
              >
                {`${selected ? '✓ ' : ''}${strings.bills.refundMethods[method] ?? method}`}
              </Button>
            );
          })}
        </div>
        {refundMethod !== 'none' && (
          <Field
            label={strings.bills.refundAmount}
            inputMode="decimal"
            value={refundAmount}
            onChange={(event) => {
              setRefundAmount(event.target.value);
            }}
          />
        )}
      </fieldset>
      <div className="flex justify-end">
        <Button size="lg" disabled={credit.isPending} onClick={onIssue}>
          {credit.isPending ? strings.bills.issuing : strings.bills.issueCredit}
        </Button>
      </div>
    </section>
  );
}

function IssuedNote({
  note,
  onAnother,
}: {
  note: CreditNote;
  onAnother: () => void;
}): ReactElement {
  return (
    <div className="flex flex-col gap-3">
      <Notice tone="success" title={strings.bills.creditIssued(note.credit_note_number)}>
        {strings.bills.creditTotal(formatINR(note.grand_total))}
      </Notice>
      {note.refunds.map((refund) => (
        <p key={refund.id} className="font-mono tabular-nums">
          {strings.bills.refunded(
            strings.orders.methods[refund.method] ?? refund.method,
            formatINR(refund.amount.replace(/^-/, '')),
          )}
        </p>
      ))}
      <Button variant="secondary" onClick={onAnother}>
        {strings.bills.anotherCredit}
      </Button>
    </div>
  );
}

function CancelInvoice({ invoice }: { invoice: Invoice }): ReactElement {
  const cancel = useCancelInvoice();
  const submission = useIdempotencyKey();
  // `null` until somebody asks to cancel; then the error being described.
  const [reason, setReason] = useState<string | null>(null);

  if (reason === null) {
    return (
      <div className="flex flex-col items-start gap-1">
        <Button
          variant="ghost"
          onClick={() => {
            setReason('');
          }}
        >
          {strings.bills.cancelInvoice}
        </Button>
        <p className="text-sm text-muted-foreground">{strings.bills.cancelHint}</p>
      </div>
    );
  }

  return (
    <section className="flex flex-col gap-2 rounded-lg border border-critical p-4">
      <h2 className="text-lg font-semibold">{strings.bills.cancelInvoice}</h2>
      <p className="text-sm">{strings.bills.cancelHint}</p>
      {cancel.isError && <Notice tone="critical" {...errorProps(cancel.error)} />}
      <Field
        label={strings.bills.cancelReason}
        value={reason}
        onChange={(event) => {
          setReason(event.target.value);
        }}
      />
      <div className="flex justify-end gap-2">
        <Button
          variant="secondary"
          onClick={() => {
            setReason(null);
          }}
        >
          {strings.bills.keepInvoice}
        </Button>
        <Button
          variant="destructive"
          disabled={cancel.isPending || reason.trim().length < 3}
          onClick={() => {
            cancel.mutate(
              { invoiceId: invoice.id, reason: reason.trim(), idempotencyKey: submission.key },
              {
                onSuccess: () => {
                  submission.renew();
                  setReason(null);
                },
              },
            );
          }}
        >
          {cancel.isPending ? strings.bills.cancelling : strings.bills.confirmCancel}
        </Button>
      </div>
    </section>
  );
}

/**
 * Every credit note against this invoice, readable and printable (decision D27). Printing uses the
 * browser's own print: the chosen note is the only thing on the page while it prints.
 */
function CreditNotes({
  order,
  invoice,
  names,
}: {
  order: Order;
  invoice: Invoice;
  names: DishNames;
}): ReactElement | null {
  const [printing, setPrinting] = useState<string | null>(null);
  useEffect(() => {
    if (printing === null) {
      return;
    }
    window.print();
    setPrinting(null);
  }, [printing]);
  const notes = invoice.credit_notes ?? [];
  if (notes.length === 0) {
    return null;
  }
  const dishOf = (orderLineId: string): string => {
    const line = order.lines.find((each) => each.id === orderLineId);
    return line === undefined ? '' : (names.dishes.get(line.menu_item_variant_id) ?? '');
  };
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold print:hidden">{strings.bills.creditNotesTitle}</h2>
      {notes.map((note) => (
        <PrintableNote
          key={note.id}
          note={note}
          invoice={invoice}
          dishOf={dishOf}
          hidden={printing !== null && printing !== note.id}
          onPrint={() => {
            setPrinting(note.id);
          }}
        />
      ))}
    </section>
  );
}

function PrintableNote({
  note,
  invoice,
  dishOf,
  hidden,
  onPrint,
}: {
  note: CreditNoteSummary;
  invoice: Invoice;
  dishOf: (orderLineId: string) => string;
  hidden: boolean;
  onPrint: () => void;
}): ReactElement {
  return (
    <article className={`rounded-lg border border-border p-4 ${hidden ? 'print:hidden' : ''}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{strings.bills.creditNoteTitle(note.credit_note_number)}</p>
          <p className="text-sm text-muted-foreground">
            {strings.bills.againstInvoice(invoice.invoice_number, note.note_date)}
          </p>
          <p className="text-sm">{invoice.supplier_name}</p>
          {invoice.supplier_gstin !== null && (
            <p className="text-sm">{strings.bills.gstin(invoice.supplier_gstin)}</p>
          )}
        </div>
        <Button
          variant="secondary"
          className="print:hidden"
          aria-label={strings.bills.printCreditNote(note.credit_note_number)}
          onClick={onPrint}
        >
          {strings.bills.print}
        </Button>
      </div>
      <p className="mt-2">{note.reason}</p>
      <ul className="mt-2">
        {note.lines.map((line) => (
          <li key={line.id} className="flex justify-between gap-3">
            <span>{`${String(line.quantity)} × ${dishOf(line.order_line_id)}`}</span>
            <span className="whitespace-nowrap font-mono tabular-nums">
              {formatINR(line.line_total)}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 flex justify-between gap-3 font-semibold">
        <span>{strings.bills.creditTotalLabel}</span>
        <span className="whitespace-nowrap font-mono tabular-nums">
          {formatINR(note.grand_total)}
        </span>
      </p>
    </article>
  );
}
