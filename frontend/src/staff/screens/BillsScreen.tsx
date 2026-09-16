import { type ReactElement, useState } from 'react';
import { Link } from 'react-router-dom';

import { businessToday } from '@shared/businessDay';
import { formatINR } from '@shared/money';
import { Button } from '@shared/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { useAuth } from '@staff/auth/AuthContext';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { useBills } from '@staff/api/orders';

/**
 * Today's settled and cancelled bills: where a manager starts when a dish has to come off a bill.
 *
 * **Today is the restaurant's business day, not the browser's.** A bill settled at 01:30 belongs to
 * the evening before, and a manager crediting it the next morning looks for it there
 * (CLAUDE.md invariant 4).
 *
 * **A full page offers the next one.** The list never stops silently at the page size; that is how
 * M01's staff list once hid everyone after the fiftieth.
 */
export default function BillsScreen(): ReactElement {
  const { session } = useAuth();
  // `session` is never null behind RequireAuth; the fallback keeps the screen usable if that changes.
  const today =
    session === null || session === undefined
      ? new Date().toISOString().slice(0, 10)
      : businessToday(session.restaurant.timezone, session.restaurant.business_day_start);
  const [cursor, setCursor] = useState<string | null>(null);
  const bills = useBills(today, cursor);
  const items = bills.data?.items ?? [];
  const next = bills.data?.next_cursor ?? null;

  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <h1 className="text-2xl font-semibold">{strings.bills.title}</h1>
      <p className="text-sm text-muted-foreground">{strings.bills.intro}</p>
      <QueryState
        isPending={bills.isPending}
        error={bills.error}
        pendingLabel={strings.bills.loading}
      >
        {items.length === 0 ? (
          <p className="text-muted-foreground">{strings.bills.empty}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{strings.bills.orderColumn}</TableHead>
                <TableHead>{strings.bills.statusColumn}</TableHead>
                <TableHead>{strings.bills.waiterColumn}</TableHead>
                <TableHead className="text-right">{strings.bills.totalColumn}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((bill) => (
                <TableRow key={bill.id} className="min-h-target">
                  <TableCell>
                    <Link to={`/bills/${bill.id}`} className="underline">
                      {strings.orders.orderLabel(bill.order_number)}
                    </Link>
                  </TableCell>
                  <TableCell>{strings.bills.statuses[bill.status] ?? bill.status}</TableCell>
                  <TableCell>
                    {bill.type !== 'dine_in'
                      ? strings.orders.counterOrder
                      : (bill.waiter?.full_name ?? strings.orders.noWaiter)}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {formatINR(bill.grand_total)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        <div className="flex justify-between gap-2">
          {cursor !== null && (
            <Button
              variant="secondary"
              onClick={() => {
                setCursor(null);
              }}
            >
              {strings.bills.firstPage}
            </Button>
          )}
          {next !== null && (
            <Button
              variant="secondary"
              onClick={() => {
                setCursor(next);
              }}
            >
              {strings.bills.nextPage}
            </Button>
          )}
        </div>
      </QueryState>
    </div>
  );
}
