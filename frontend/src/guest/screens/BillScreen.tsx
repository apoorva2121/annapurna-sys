import { type ReactElement, useEffect, useState } from 'react';

import { formatINR } from '@shared/money';

import { type GuestBill, fetchBill } from '../api';
import { strings } from '../strings';

/**
 * What this table is having, and what it comes to.
 *
 * **Every figure is the server's, rendered.** Nothing on this screen adds two rupee amounts
 * together (CLAUDE.md invariant 3) — a guest total that disagreed with the printed one by a paisa
 * is an argument at a table, and the guest is the one holding the phone.
 *
 * **No CGST/SGST split, and that is not an omission.** The split is a tax-invoice particular (CGST
 * Rules, Rule 46, per `docs/compliance-rules.md`) and this product produces an invoice at
 * settlement, not before. What a guest reads here is the provisional bill, with tax as one line —
 * which is what the staff bill shows too.
 *
 * **Lines are at menu price, before the discount and the tax**, which is what a person expects
 * beside a dish on an Indian bill and is what adds up to the subtotal beneath them.
 */
export function BillScreen(): ReactElement {
  const [bill, setBill] = useState<GuestBill | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetchBill()
      .then(setBill)
      .catch(() => {
        setFailed(true);
      });
  }, []);

  if (failed) {
    return <p className="text-base text-muted-foreground">{strings.scan.offlineBody}</p>;
  }
  if (bill === null) {
    return <p className="text-base text-muted-foreground">{strings.bill.loading}</p>;
  }

  return (
    <section className="flex flex-col gap-4">
      <ul className="flex flex-col gap-2">
        {bill.lines.map((line, index) => (
          <li key={`${line.name}-${String(index)}`} className="flex justify-between gap-3 text-base">
            <span>
              {line.name} <span className="text-muted-foreground">{strings.bill.quantity(line.quantity)}</span>
            </span>
            <span className="shrink-0 whitespace-nowrap tabular-nums">{formatINR(line.amount)}</span>
          </li>
        ))}
      </ul>

      <dl className="flex flex-col gap-1 border-t border-border pt-3 text-base">
        <Line label={strings.bill.subtotal} amount={bill.subtotal} />
        {bill.discount_total === '0.00' ? null : (
          <Line label={strings.bill.discount} amount={bill.discount_total} />
        )}
        {bill.charge_total === '0.00' ? null : (
          <Line label={strings.bill.charges} amount={bill.charge_total} />
        )}
        <Line label={strings.bill.tax} amount={bill.tax_total} />
        {bill.round_off === '0.00' ? null : (
          <Line label={strings.bill.roundOff} amount={bill.round_off} />
        )}
      </dl>

      <div className="flex justify-between border-t border-border pt-3 text-lg font-semibold">
        <span>{strings.bill.total}</span>
        <span className="shrink-0 whitespace-nowrap tabular-nums">
          {formatINR(bill.grand_total)}
        </span>
      </div>

      <p className="text-sm text-muted-foreground">
        {bill.is_settled ? strings.bill.settled : strings.bill.unsettled}
      </p>
      <p className="text-sm text-muted-foreground">{strings.bill.hint}</p>
    </section>
  );
}

function Line({ label, amount }: { label: string; amount: string }): ReactElement {
  return (
    <div className="flex justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="shrink-0 whitespace-nowrap tabular-nums">{formatINR(amount)}</dd>
    </div>
  );
}
