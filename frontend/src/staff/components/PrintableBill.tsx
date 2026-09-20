import type { ReactElement } from 'react';

import { formatINR } from '@shared/money';
import type { Invoice, Order } from '@staff/api/orders';
import { strings } from '@staff/strings';

/**
 * The bill a restaurant hands a customer, on an 80mm thermal roll.
 *
 * **This did not exist until 2026-09-20, and its absence meant the product could not run a till.**
 * Every particular Rule 46 requires was already frozen onto `invoice` at settlement — supplier
 * name, address and GSTIN, a gapless serial, the date, the taxable value, the rate and the amount
 * of tax — and nothing laid them out for a person. `docs/compliance-rules.md` carried it as a known
 * gap for sixteen modules.
 *
 * **The gap survived on one misread word.** The row said *"Printing is out of scope for month 1
 * (CLAUDE.md)"*, and CLAUDE.md excludes **"printer/hardware drivers"** — which browser printing is
 * not. The product had been browser-printing credit notes since D27. It could print the document
 * that corrects a bill and not the bill.
 *
 * **Rule 5(1)(f) is why `document_type` matters here.** A composition restaurant does not issue a
 * tax invoice; it issues a *bill of supply*, and the words
 *
 *   > composition taxable person, not eligible to collect tax on supplies
 *
 * must appear **at the top**. That text is verbatim from CBIC's own PDF of the CGST Rules 2017,
 * read on 2026-09-20 — *"supplies"*, not *"supplier"*, which several secondary sources get wrong
 * and which is exactly why `docs/compliance-rules.md`'s first rule forbids filling these in from
 * memory. Getting it wrong is a licence risk for a real restaurant, not a typo.
 *
 * **Amounts are strings all the way to the ink.** `formatINR` takes the server's decimal string;
 * nothing here adds, subtracts or rounds a rupee (invariant 3). A bill that disagrees with the
 * screen is the worst defect a bill can have, and arithmetic in two places is how it happens.
 */
export function PrintableBill({
  invoice,
  order,
  dishOf,
}: {
  invoice: Invoice;
  order: Order;
  /** A dish's name for an order line, resolved by the screen that already has the menu. */
  dishOf: (orderLineId: string) => string;
}): ReactElement {
  const isBillOfSupply = invoice.document_type === 'bill_of_supply';

  return (
    <article
      id="printable-bill"
      // **Duplicate content, so it is hidden from assistive technology.** Every figure here is
      // already on the screen above in a layout built for reading; this one is built for a 72mm
      // roll. In a browser `hidden` keeps it out of the accessibility tree anyway — this is
      // explicit for jsdom, where no stylesheet applies and the whole bill would otherwise be
      // announced, and read, twice.
      aria-hidden="true"
      className="till-roll mx-auto hidden max-w-[72mm] font-mono text-sm print:block"
    >
      {/* Rule 5(1)(f): at the top, before anything else, and only on a bill of supply. */}
      {isBillOfSupply && (
        <p className="mb-2 border border-black p-1 text-center text-xs font-semibold uppercase">
          {strings.bills.compositionDeclaration}
        </p>
      )}

      <Masthead invoice={invoice} />

      <p className="mt-2 border-y border-dashed border-black py-1 text-center text-xs font-semibold">
        {isBillOfSupply ? strings.bills.billOfSupplyTitle : strings.bills.taxInvoiceTitle}
      </p>

      <dl className="mt-2 text-xs">
        <Row label={strings.bills.numberLabel} value={invoice.invoice_number} />
        <Row label={strings.bills.dateLabel} value={invoice.invoice_date} />
        <Row label={strings.bills.orderLabel} value={order.order_number} />
        {invoice.recipient_name !== null && (
          <Row label={strings.bills.recipientLabel} value={invoice.recipient_name} />
        )}
        {invoice.recipient_gstin !== null && (
          <Row label={strings.bills.recipientGstinLabel} value={invoice.recipient_gstin} />
        )}
      </dl>

      <table className="mt-2 w-full border-y border-dashed border-black text-xs">
        <thead>
          <tr>
            <th className="py-1 text-left font-semibold">{strings.bills.itemHeading}</th>
            <th className="py-1 text-right font-semibold">{strings.bills.qtyHeading}</th>
            <th className="py-1 text-right font-semibold">{strings.bills.amountHeading}</th>
          </tr>
        </thead>
        <tbody>
          {order.lines.map((line) => (
            <tr key={line.id}>
              <td className="py-0.5 pr-1 align-top">{dishOf(line.id)}</td>
              <td className="py-0.5 text-right align-top tabular-nums">{line.quantity}</td>
              <td className="py-0.5 text-right align-top tabular-nums">
                {formatINR(line.line_total)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <Totals invoice={invoice} isBillOfSupply={isBillOfSupply} />

      <p className="mt-1 flex justify-between border-t border-black pt-1 text-base font-semibold">
        <span>{strings.bills.totalLabel}</span>
        <span className="tabular-nums">{formatINR(invoice.grand_total)}</span>
      </p>

      {invoice.payments.length > 0 && (
        <dl className="mt-2 text-xs">
          {invoice.payments.map((payment) => (
            <Row
              key={payment.id}
              label={strings.orders.methods[payment.method] ?? payment.method}
              value={formatINR(payment.amount)}
              money
            />
          ))}
        </dl>
      )}

      <p className="mt-3 text-center text-xs">{strings.bills.thankYou}</p>
    </article>
  );
}

/** Who issued it: Rule 46(a) is name, address and GSTIN, and the FSSAI number rides along. */
function Masthead({ invoice }: { invoice: Invoice }): ReactElement {
  const address = invoice.supplier_address;
  const lines = [
    address?.line1,
    address?.line2,
    [address?.city, address?.state].filter(Boolean).join(', ') || null,
    address?.postcode,
  ].filter((line): line is string => typeof line === 'string' && line.trim() !== '');

  return (
    <header className="text-center">
      <p className="text-base font-semibold">{invoice.supplier_name}</p>
      {lines.map((line) => (
        <p key={line} className="text-xs">
          {line}
        </p>
      ))}
      {invoice.supplier_gstin !== null && (
        <p className="text-xs">{strings.bills.gstin(invoice.supplier_gstin)}</p>
      )}
      {/* §A5. On the bill because a diner is entitled to see it, not to satisfy Rule 46. */}
      {invoice.fssai_licence !== null && (
        <p className="text-xs">{strings.bills.fssai(invoice.fssai_licence)}</p>
      )}
    </header>
  );
}

/**
 * What it came to.
 *
 * **A bill of supply shows no tax at all**, and that is not a rendering shortcut: a composition
 * restaurant may not collect any (CGST Act s.10), so printing `CGST 0.00` would be a statement
 * about tax where the law requires silence.
 *
 * The optional rows compare against `'0.00'` as a **string**. Parsing them to compare numerically
 * would put a float in the path of a rupee amount, which invariant 3 forbids — and the server
 * always sends two decimal places, so the comparison is exact.
 */
function Totals({
  invoice,
  isBillOfSupply,
}: {
  invoice: Invoice;
  isBillOfSupply: boolean;
}): ReactElement {
  return (
    <dl className="mt-2 text-xs">
      <Row label={strings.bills.taxableLabel} value={formatINR(invoice.taxable_total)} money />
      {isBillOfSupply ? null : (
        <>
          <Row label={strings.bills.cgstLabel} value={formatINR(invoice.cgst_total)} money />
          <Row label={strings.bills.sgstLabel} value={formatINR(invoice.sgst_total)} money />
        </>
      )}
      {invoice.discount_total === '0.00' ? null : (
        <Row label={strings.bills.discountLabel} value={formatINR(invoice.discount_total)} money />
      )}
      {invoice.charge_total === '0.00' ? null : (
        <Row label={strings.bills.chargesLabel} value={formatINR(invoice.charge_total)} money />
      )}
      {invoice.round_off === '0.00' ? null : (
        <Row label={strings.bills.roundOffLabel} value={formatINR(invoice.round_off)} money />
      )}
    </dl>
  );
}

/** One label-and-value line. Amounts line up because the digits are tabular, not because of spaces. */
function Row({
  label,
  value,
  money = false,
}: {
  label: string;
  value: string;
  money?: boolean;
}): ReactElement {
  return (
    <div className="flex justify-between gap-2">
      <dt>{label}</dt>
      <dd className={money ? 'tabular-nums' : ''}>{value}</dd>
    </div>
  );
}
