import { type ReactElement, useState } from 'react';

import { formatINR } from '@shared/money';
import { Button } from '@shared/ui/button';
import { Notice } from '@staff/components/Notice';
import { errorProps } from '@staff/components/errorProps';
import { QueryState } from '@staff/components/QueryState';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { strings } from '@staff/strings';
import {
  type StockCount,
  useApproveCount,
  useOpenCount,
  useRecordCount,
  useStockCounts,
  useSubmitCount,
} from '@staff/api/inventory';
import { useStockItems } from '@staff/api/stock';

/**
 * Physical counts: open a sheet, write what is on the shelf, submit, and have somebody else approve.
 *
 * **The screen never hides that approval is what moves the ledger.** A submitted count is a
 * worksheet — the book has not changed — and a manager who thought submitting was the end would
 * wonder later why the position never corrected. So the status is stated on every count and the
 * approve button says what it will do.
 *
 * **Self-approval is refused by the server, and the screen does not pretend otherwise.** It offers
 * the button and reports the refusal in the person's own words, rather than hiding the control
 * based on a guess about who counted. Hiding it would teach the wrong lesson: the rule is not "this
 * button is unavailable", it is "a count needs a second pair of eyes", and the sentence that comes
 * back says so.
 *
 * **Variance is shown in rupees, negative where the shelf holds less than the book.** That is the
 * leakage number — the thing this whole module exists to surface — and a count sheet that showed
 * only quantities would make somebody do the arithmetic that the product is for.
 */
export default function StockCountScreen(): ReactElement {
  const counts = useStockCounts();
  const items = useStockItems('ingredient');
  const open = useOpenCount();

  const draft = (counts.data?.counts ?? []).find((count) => count.status === 'draft');

  return (
    <div className="space-y-page">
      <h1 className="text-2xl font-semibold">{strings.stockLedger.countTitle}</h1>
      <p className="text-sm text-muted-foreground">{strings.stockLedger.countIntro}</p>

      {open.isError && <Notice tone="critical" {...errorProps(open.error)} />}

      <QueryState
        isPending={counts.isPending}
        error={counts.error}
        pendingLabel={strings.stockLedger.countTitle}
      >
        {draft === undefined && (
          <Button
            type="button"
            disabled={open.isPending || items.isPending}
            onClick={() => {
              open.mutate({
                stock_item_ids: (items.data?.items ?? []).map((item) => item.id),
                scope: 'full',
              });
            }}
          >
            {strings.stockLedger.startCount}
          </Button>
        )}

        {(counts.data?.counts ?? []).map((count) => (
          <CountSheet key={count.id} count={count} />
        ))}
      </QueryState>
    </div>
  );
}

function CountSheet({ count }: { count: StockCount }): ReactElement {
  const record = useRecordCount();
  const submit = useSubmitCount();
  const approve = useApproveCount();
  const [counted, setCounted] = useState<Record<string, string>>({});

  const isDraft = count.status === 'draft';
  const isSubmitted = count.status === 'submitted';

  return (
    <section className="space-y-3 rounded border border-border p-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">{count.business_date}</h2>
        <span className="text-sm text-muted-foreground">
          {strings.stockLedger.status[count.status]}
        </span>
      </header>

      {approve.isError && (
        // The server's sentence, not ours. A refused approval says *why* — "a count must be
        // approved by somebody other than the person who counted it" — and replacing that with a
        // generic title would throw away the only part worth reading.
        <Notice tone="critical" {...errorProps(approve.error)} />
      )}

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{strings.stockLedger.item}</TableHead>
              <TableHead className="text-right">{strings.stockLedger.book}</TableHead>
              <TableHead className="text-right">{strings.stockLedger.counted}</TableHead>
              <TableHead className="text-right">{strings.stockLedger.variance}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {count.lines.map((line) => (
              <TableRow key={line.stock_item_id}>
                <TableCell className="font-mono text-xs">
                  {line.stock_item_id.slice(0, 8)}
                </TableCell>
                <TableCell className="text-right tabular-nums">{line.system_quantity}</TableCell>
                <TableCell className="text-right">
                  {isDraft ? (
                    <input
                      id={`count-${line.stock_item_id}`}
                      inputMode="decimal"
                      value={counted[line.stock_item_id] ?? line.counted_quantity}
                      onChange={(event) => {
                        setCounted({ ...counted, [line.stock_item_id]: event.target.value });
                      }}
                      className="min-h-target w-28 rounded border border-input bg-background px-2 text-right"
                      aria-label={strings.stockLedger.counted}
                    />
                  ) : (
                    <span className="tabular-nums">{line.counted_quantity}</span>
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatINR(line.variance_value)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="flex flex-wrap gap-2">
        {isDraft && (
          <>
            <Button
              type="button"
              variant="secondary"
              disabled={record.isPending}
              onClick={() => {
                record.mutate({
                  countId: count.id,
                  lines: count.lines.map((line) => ({
                    stock_item_id: line.stock_item_id,
                    counted_quantity: counted[line.stock_item_id] ?? line.counted_quantity,
                  })),
                });
              }}
            >
              {strings.stockLedger.saveCount}
            </Button>
            <Button
              type="button"
              disabled={submit.isPending}
              onClick={() => {
                submit.mutate(count.id);
              }}
            >
              {strings.stockLedger.submitCount}
            </Button>
          </>
        )}
        {isSubmitted && (
          <Button
            type="button"
            disabled={approve.isPending}
            onClick={() => {
              approve.mutate(count.id);
            }}
          >
            {strings.stockLedger.approveCount}
          </Button>
        )}
      </div>

      {isSubmitted && (
        <p className="text-sm text-muted-foreground">{strings.stockLedger.approveExplains}</p>
      )}
    </section>
  );
}
