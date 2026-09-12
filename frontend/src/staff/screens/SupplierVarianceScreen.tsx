import type { ReactElement } from 'react';
import { useParams } from 'react-router-dom';

import { formatINR } from '@shared/money';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { type VarianceRow, useSupplierVariance } from '@staff/api/procurement';

/**
 * *"Supplier A short-delivered 4.2% across 31 deliveries this quarter — ₹18,400."*
 *
 * That sentence is the whole reason M06 exists (`docs/waste-model.md` §1), and it is unanswerable
 * unless invoiced and received are two separate stored columns. They are, so it is answerable, and
 * this screen is where it gets said — **as a sentence, at the top, before the table.** A manager
 * who reads one line of this screen should still learn the thing worth knowing; the rows underneath
 * are for the person who then wants to know which item.
 *
 * **Biggest loss first.** The server orders by `short_delivery_value` descending, because the top
 * row is the one worth a phone call and a table sorted by item code buries it.
 *
 * **A clean supplier gets a sentence too, not an empty table.** "They delivered everything they
 * billed for" is information; a blank screen is ambiguous between that and a broken report
 * (`docs/ui/conventions.md`: empty states explain).
 */
export default function SupplierVarianceScreen(): ReactElement {
  const { supplierId } = useParams<{ supplierId: string }>();
  const report = useSupplierVariance(supplierId);

  // One place the optional chain is resolved, rather than six `??` scattered through the JSX.
  // Each of those is a branch, and a screen that renders one table should not read as a decision
  // tree.
  const summary = report.data ?? {
    supplier_name: '',
    deliveries: 0,
    short_delivery_value: '0.00',
    start: '',
    end: '',
    rows: [],
  };
  const rows = summary.rows;

  return (
    <div className="space-y-page">
      <h1 className="text-2xl font-semibold">{strings.procurement.varianceTitle}</h1>
      <p className="text-sm text-muted-foreground">{strings.procurement.varianceIntro}</p>

      <QueryState
        isPending={report.isPending}
        error={report.error}
        pendingLabel={strings.procurement.varianceTitle}
      >
        <Headline
          name={summary.supplier_name}
          deliveries={summary.deliveries}
          value={summary.short_delivery_value}
          hasRows={rows.length > 0}
        />

        {rows.length === 0 ? (
          <p className="text-muted-foreground">{strings.procurement.varianceEmpty}</p>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              {`${strings.procurement.period}: ${summary.start} — ${summary.end}`}
            </p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{strings.procurement.item}</TableHead>
                  <TableHead className="text-right">{strings.procurement.deliveries}</TableHead>
                  <TableHead className="text-right">{strings.procurement.invoiced}</TableHead>
                  <TableHead className="text-right">{strings.procurement.received}</TableHead>
                  <TableHead className="text-right">{strings.procurement.rejected}</TableHead>
                  <TableHead className="text-right">
                    {strings.procurement.shortDeliveryValue}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <Row key={row.stock_item_id} row={row} />
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </QueryState>
    </div>
  );
}

/** The sentence, before the table. Rendered as a status rather than an alert: a short delivery is
 *  something to act on this week, not an emergency, and `critical` in this product means somebody
 *  must act *now* (`docs/ui/conventions.md`). */
function Headline({
  name,
  deliveries,
  value,
  hasRows,
}: {
  name: string;
  deliveries: number;
  value: string;
  hasRows: boolean;
}): ReactElement | null {
  if (!hasRows) {
    return null;
  }
  // `value` is compared as a string against the server's own zero, not parsed: the only question
  // being asked is whether the server reported nothing owed, and `Number(value) > 0` would be
  // arithmetic on a rupee figure to decide a sentence.
  const owed = value !== '0.00' && value !== '0';

  return (
    <p
      role="status"
      className={
        owed
          ? 'rounded border border-warning/40 bg-warning-soft px-4 py-3 font-semibold'
          : 'rounded border border-success/40 bg-success-soft px-4 py-3 font-semibold'
      }
    >
      {owed
        ? strings.procurement.varianceHeadline(name, deliveries, formatINR(value))
        : strings.procurement.varianceClean(name)}
    </p>
  );
}

function Row({ row }: { row: VarianceRow }): ReactElement {
  return (
    <TableRow>
      <TableCell>
        <span className="font-medium">{row.name}</span>
        <span className="ml-2 font-mono text-xs text-muted-foreground">{row.code}</span>
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums">{row.deliveries}</TableCell>
      <TableCell className="text-right font-mono tabular-nums">
        {row.invoiced} {row.base_unit}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums">
        {row.received} {row.base_unit}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums">
        {row.rejected} {row.base_unit}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums">
        {formatINR(row.short_delivery_value)}
      </TableCell>
    </TableRow>
  );
}
