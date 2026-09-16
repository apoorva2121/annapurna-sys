import { type FormEvent, type ReactElement, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { formatINR, parseAmount } from '@shared/money';
import { Button } from '@shared/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { useIdempotencyKey } from '@shared/useIdempotencyKey';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type PostedLine,
  type PostedReceipt,
  type ReceiptLineInput,
  usePurchaseOrder,
  useReceiveAgainstOrder,
} from '@staff/api/procurement';
import { type Person, describePerson } from '@staff/api/people';
import { useStockItems } from '@staff/api/stock';

type Weighed = { invoiced: string; received: string; rejected: string; reason: string };

const BLANK: Weighed = { invoiced: '', received: '', rejected: '', reason: '' };

/** What the supplier's paperwork says, as three strings from three inputs. */
type Invoice = { number: string; amount: string; tax: string };

/** The invoice half of the request. Empty boxes become `null` rather than `"0"`: a market trader
 *  who charges no tax and a delivery where nobody wrote the tax down are different facts, and
 *  storing zero for the second would state a figure nobody reported. */
function invoiceBody(invoice: Invoice): {
  invoice_number: string | null;
  invoice_amount: string | null;
  tax_amount: string | null;
} {
  return {
    invoice_number: invoice.number === '' ? null : invoice.number,
    invoice_amount: invoice.amount === '' ? null : parseAmount(invoice.amount),
    tax_amount: invoice.tax === '' ? null : parseAmount(invoice.tax),
  };
}

/**
 * **The money screen.** `docs/waste-model.md` §1: ordered 50 kg, delivered 47 kg, invoiced 50 kg
 * happens constantly and nobody notices, because nobody weighs. This is the screen that makes
 * somebody weigh.
 *
 * **The two inputs are labelled "What the bill says" and "What the scale says", never "Quantity"
 * and "Actual".** That is the most important decision on this screen and it is a wording one: a
 * store manager who types the invoiced figure into both boxes destroys the entire value of the
 * module while every test in the project stays green. The only defence is two labels that cannot
 * be mistaken for each other, and an ordered column beside them for context.
 *
 * **No rupee variance is shown while a weight is still editable.** Three columns sit side by side
 * so the discrepancy is *visible* — no subtraction happens here, on money or on quantities — and
 * every derived figure appears in the confirmation panel afterwards, once the weights are recorded
 * and can no longer be changed. `docs/waste-model.md` is explicit about why: showing the value of a
 * loss before it is logged suppresses honest reporting, and a screen announcing *"this weight will
 * flag your supplier for ₹4,200"* while somebody holds the scale is asking them to choose between
 * an accurate number and an awkward conversation. Some of them will move the number.
 *
 * Every quantity is a string from the keyboard to the API. `parseAmount` validates without a
 * `Number` in between (CLAUDE.md invariant 3).
 */
export default function GoodsReceiptScreen(): ReactElement {
  const { poId } = useParams<{ poId: string }>();
  const order = usePurchaseOrder(poId);
  const items = useStockItems('ingredient');
  const receive = useReceiveAgainstOrder();
  // One key for this delivery: kept across a second tap, renewed once the delivery is booked.
  const submission = useIdempotencyKey();

  const [weights, setWeights] = useState<Record<string, Weighed>>({});
  const [invoice, setInvoice] = useState<Invoice>({ number: '', amount: '', tax: '' });
  const [problem, setProblem] = useState<string | null>(null);
  const [posted, setPosted] = useState<PostedReceipt | null>(null);

  const names = new Map((items.data?.items ?? []).map((item) => [item.id, item]));
  const lines = order.data?.lines ?? [];
  const poNumber = order.data?.po_number ?? '';

  if (posted !== null) {
    return <PostedPanel posted={posted} names={names} />;
  }

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const validated = validate(lines, weights);
    if (typeof validated === 'string') {
      setProblem(validated);
      return;
    }
    setProblem(null);
    receive.mutate(
      {
        orderId: poId ?? '',
        body: { lines: validated, ...invoiceBody(invoice) },
        idempotencyKey: submission.key,
      },
      {
        onSuccess: (result) => {
          submission.renew();
          setPosted(result);
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-3xl flex-col gap-4" noValidate>
      <h1 className="text-2xl font-semibold">{strings.procurement.receiveTitle}</h1>
      <p className="text-sm text-muted-foreground">{strings.procurement.receiveIntro}</p>

      <Problems problem={problem} failure={receive.isError ? receive.error : null} />

      <QueryState
        isPending={order.isPending}
        error={order.error}
        pendingLabel={strings.procurement.receiveTitle}
      >
        <p className="font-mono text-sm">{poNumber}</p>
        <div className="space-y-4">
          {lines.map((line) => (
            <WeighLine
              key={line.stock_item_id}
              item={names.get(line.stock_item_id)}
              ordered={line.quantity_ordered}
              value={weights[line.stock_item_id]}
              onChange={(patch) => {
                setWeights((current) => ({
                  ...current,
                  [line.stock_item_id]: { ...(current[line.stock_item_id] ?? BLANK), ...patch },
                }));
              }}
            />
          ))}
        </div>
      </QueryState>

      <InvoiceFields
        invoice={invoice}
        onChange={(patch) => {
          setInvoice((current) => ({ ...current, ...patch }));
        }}
      />

      <Button type="submit" disabled={receive.isPending}>
        {receive.isPending ? strings.procurement.posting : strings.procurement.postReceipt}
      </Button>
    </form>
  );
}

/**
 * One item, with what was ordered, what the bill claims, and what the scale said — in that order,
 * left to right, so the eye reads them as three separate facts.
 *
 * Ordered is rendered as text rather than as a disabled input: a greyed-out field invites somebody
 * to try to change it, and this one is a fact about a document that already exists.
 */
function WeighLine({
  item,
  ordered,
  value = BLANK,
  onChange,
}: {
  item: { name: string; base_unit: string } | undefined;
  ordered: string;
  value: Weighed | undefined;
  onChange: (patch: Partial<Weighed>) => void;
}): ReactElement {
  // Something has been refused, so the reason box earns its place. Compared as a string against
  // what an empty and a zeroed box actually contain — no parsing, because the only question is
  // whether a person typed something other than nothing.
  const refused = value.rejected !== '' && value.rejected !== '0';

  return (
    <div className="space-y-3 rounded border p-3">
      <p className="font-medium">
        {item?.name ?? ''}{' '}
        <span className="text-sm text-muted-foreground">({item?.base_unit ?? ''})</span>
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium">{strings.procurement.ordered}</span>
          <p className="min-h-target font-mono tabular-nums">{ordered}</p>
        </div>
        <Field
          label={strings.procurement.invoicedLabel}
          value={value.invoiced}
          inputMode="decimal"
          onChange={(event) => {
            onChange({ invoiced: event.target.value });
          }}
        />
        <Field
          label={strings.procurement.receivedLabel}
          value={value.received}
          inputMode="decimal"
          onChange={(event) => {
            onChange({ received: event.target.value });
          }}
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label={strings.procurement.rejectedLabel}
          value={value.rejected}
          inputMode="decimal"
          onChange={(event) => {
            onChange({ rejected: event.target.value });
          }}
        />
        {/* Appears only once something has been refused — an always-present reason box on every
            line is four empty inputs a person learns to scroll past. */}
        {refused && (
          <Field
            label={strings.procurement.rejectionReason}
            value={value.reason}
            onChange={(event) => {
              onChange({ reason: event.target.value });
            }}
          />
        )}
      </div>
    </div>
  );
}

/** Both ways this screen can refuse, in one place.
 *
 * Two of them, and they are different in kind: `problem` is this screen saying a weight is not a
 * number yet, and `failure` is the server saying the delivery could not be booked — a duplicate
 * invoice, a closed order. Neither may be silent (`docs/engineering-standards.md` §5), and keeping
 * them together is what stops the second being added without the first.
 */
function Problems({
  problem,
  failure,
}: {
  problem: string | null;
  failure: unknown;
}): ReactElement {
  return (
    <>
      {problem !== null && <Notice tone="critical" title={problem} />}
      {failure !== null && <Notice tone="critical" {...errorProps(failure)} />}
    </>
  );
}

/** The supplier's paperwork. Grouped below the weights on purpose: the weighing is the job, and
 *  the invoice number is what makes the same bill impossible to book twice. */
function InvoiceFields({
  invoice,
  onChange,
}: {
  invoice: Invoice;
  onChange: (patch: Partial<Invoice>) => void;
}): ReactElement {
  return (
    <>
      <Field
        label={strings.procurement.invoiceNumber}
        hint={strings.procurement.invoiceNumberHint}
        value={invoice.number}
        onChange={(event) => {
          onChange({ number: event.target.value });
        }}
      />
      <Field
        label={strings.procurement.invoiceAmount}
        value={invoice.amount}
        inputMode="decimal"
        onChange={(event) => {
          onChange({ amount: event.target.value });
        }}
      />
      <Field
        label={strings.procurement.taxAmount}
        hint={strings.procurement.taxAmountHint}
        value={invoice.tax}
        inputMode="decimal"
        onChange={(event) => {
          onChange({ tax: event.target.value });
        }}
      />
    </>
  );
}

/**
 * The confirmation panel: every figure the server computed, once the weights are fixed.
 *
 * Nothing here is calculated in the browser. `accepted`, `short_delivery`, `order_shortfall`, the
 * landed cost and all four rupee values are response fields from
 * `app/services/procurement.py`, so the screen and the ledger cannot disagree about a variance.
 */
function PostedPanel({
  posted,
  names,
}: {
  posted: PostedReceipt;
  names: Map<string, { name: string; base_unit: string }>;
}): ReactElement {
  return (
    <div className="space-y-page">
      <h1 className="text-2xl font-semibold">{strings.procurement.postedTitle}</h1>
      <p className="text-sm text-muted-foreground">{strings.procurement.postedIntro}</p>
      {(posted.receipt.received_by_person ?? null) !== null && (
        <p className="text-sm">
          {strings.procurement.receivedBy(
            describePerson(posted.receipt.received_by_person as Person),
          )}
        </p>
      )}

      <Notice
        tone="success"
        title={strings.procurement.postedHeadline(
          formatINR(posted.short_delivery_value),
          formatINR(posted.accepted_value),
        )}
      />

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{strings.procurement.item}</TableHead>
            <TableHead className="text-right">{strings.procurement.invoicedLabel}</TableHead>
            <TableHead className="text-right">{strings.procurement.receivedLabel}</TableHead>
            <TableHead className="text-right">{strings.procurement.accepted}</TableHead>
            <TableHead className="text-right">{strings.procurement.shortDelivery}</TableHead>
            <TableHead className="text-right">{strings.procurement.landedCost}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {posted.lines.map((line) => (
            <PostedRow
              key={line.stock_item_id}
              line={line}
              name={names.get(line.stock_item_id)?.name ?? ''}
            />
          ))}
        </TableBody>
      </Table>

      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <dt>{strings.procurement.invoiceLineTotal}</dt>
        <dd className="font-mono tabular-nums">{formatINR(posted.invoice_line_total)}</dd>
        <dt>{strings.procurement.taxAmount}</dt>
        <dd className="font-mono tabular-nums">{formatINR(posted.receipt.tax_amount)}</dd>
        <dt>{strings.procurement.invoiceAmount}</dt>
        <dd className="font-mono tabular-nums">{formatINR(posted.receipt.invoice_amount)}</dd>
      </dl>

      <Link to="/purchasing/orders" className="underline underline-offset-4">
        {strings.procurement.backToOrders}
      </Link>
    </div>
  );
}

function PostedRow({ line, name }: { line: PostedLine; name: string }): ReactElement {
  const short = line.short_delivery !== '0' && parseAmount(line.short_delivery) !== '0.00';

  return (
    <TableRow>
      <TableCell>
        {name}
        {short && (
          // The word beside the figure, not the colour alone: a short delivery is the row somebody
          // has to act on, and it has to read the same on a steamed-up screen.
          <span className="ml-2 rounded bg-warning-soft px-1.5 py-0.5 text-xs text-warning">
            {strings.procurement.shortDelivery}
          </span>
        )}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums">{line.invoiced}</TableCell>
      <TableCell className="text-right font-mono tabular-nums">{line.received}</TableCell>
      <TableCell className="text-right font-mono tabular-nums">{line.accepted}</TableCell>
      <TableCell className="text-right font-mono tabular-nums">
        {line.short_delivery} ({formatINR(line.short_delivery_value)})
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums">{line.landed_unit_cost}</TableCell>
    </TableRow>
  );
}

/** Returns the request lines, or the sentence explaining why it cannot be posted.
 *
 * A line left entirely blank is skipped rather than refused: a delivery against a five-line order
 * that brought two of them is ordinary, and the PO stays open for the rest. What is refused is a
 * half-filled line, because "the bill says 50 and I did not write down what arrived" is the exact
 * gap this screen exists to close. */
function validate(
  lines: { stock_item_id: string }[],
  weights: Record<string, Weighed>,
): ReceiptLineInput[] | string {
  const out: ReceiptLineInput[] = [];
  for (const line of lines) {
    const weighed = weights[line.stock_item_id];
    if (weighed === undefined || (weighed.invoiced === '' && weighed.received === '')) {
      continue;
    }
    const checked = oneLine(line.stock_item_id, weighed);
    if (typeof checked === 'string') {
      return checked;
    }
    out.push(checked);
  }
  return out.length === 0 ? strings.procurement.receiptNeedsLines : out;
}

/** One line's three quantities, or the sentence explaining why they are not usable.
 *
 * `parseAmount` rather than `Number(...)`: it refuses "1e3", "0x10" and " 12 " instead of turning
 * a typo into a weight, and it pads to two places without a float in the middle (invariant 3). */
function oneLine(stockItemId: string, weighed: Weighed): ReceiptLineInput | string {
  const invoiced = parseAmount(weighed.invoiced);
  const received = parseAmount(weighed.received);
  const rejected = weighed.rejected === '' ? '0.00' : parseAmount(weighed.rejected);
  if (invoiced === null || received === null || rejected === null) {
    return strings.procurement.receiptBadNumber;
  }
  if (rejected !== '0.00' && weighed.reason.trim() === '') {
    return strings.procurement.rejectedNeedsReason;
  }
  return {
    stock_item_id: stockItemId,
    quantity_invoiced: invoiced,
    quantity_received: received,
    quantity_rejected: rejected,
    rejection_reason: weighed.reason === '' ? null : weighed.reason,
  };
}
