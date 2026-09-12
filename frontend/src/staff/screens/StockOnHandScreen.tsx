import { type ReactElement, useState } from 'react';

import { formatINR } from '@shared/money';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import {
  type Movement,
  type OnHandRow,
  useExpiring,
  useMovements,
  useOnHand,
} from '@staff/api/inventory';

/**
 * What the ledger says is on the shelf. The read surface of M05.
 *
 * **Negatives lead, and they are not an error state.** A negative position means stock was consumed
 * that nobody recorded receiving — which for a restaurant that has never kept records is not an
 * edge case, it is week one. `docs/onboarding-cold-start.md` is explicit that the first weeks of any
 * real deployment will show them. So the banner sits above the table, says what happened in a
 * sentence a manager can act on, and never uses the word "error": the ledger is not broken, the
 * paperwork is behind, and those need different responses.
 *
 * **Nothing on this screen is stored.** Every quantity is `SUM(quantity_delta)` computed at read
 * time (invariant 2). That is worth knowing when reading the code: there is no cache to invalidate
 * and no balance that can drift, which is why the table can be trusted to the paisa.
 *
 * **`is_negative` comes from the server rather than from `Number(quantity) < 0` here.** Parsing a
 * quantity to a number on the client to make a rendering decision is one small step from doing
 * arithmetic on it, which is CLAUDE.md invariant 3. The server already knows; it says so.
 *
 * **Colour is never the only signal** (`docs/ui/conventions.md` rule 5). A negative row carries the
 * word "No delivery recorded" beside the figure, so it reads the same on a steamed-up screen and to
 * the colour-blind.
 */
export default function StockOnHandScreen(): ReactElement {
  const [includeZero, setIncludeZero] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const onHand = useOnHand(includeZero);

  const rows = onHand.data?.items ?? [];
  const negatives = onHand.data?.negative_count ?? 0;

  return (
    <div className="space-y-page">
      <h1 className="text-2xl font-semibold">{strings.stockLedger.title}</h1>
      <p className="text-sm text-muted-foreground">{strings.stockLedger.intro}</p>

      <QueryState
        isPending={onHand.isPending}
        error={onHand.error}
        pendingLabel={strings.stockLedger.title}
      >
        {negatives > 0 && <NegativeBanner count={negatives} />}

        <label className="flex items-center gap-2 text-sm">
          <input
            id="stock-include-zero"
            type="checkbox"
            checked={includeZero}
            onChange={(event) => {
              setIncludeZero(event.target.checked);
            }}
            className="h-4 w-4"
          />
          {strings.stockLedger.showZero}
        </label>

        {rows.length === 0 ? (
          <p className="text-muted-foreground">{strings.stockLedger.empty}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{strings.stockLedger.item}</TableHead>
                <TableHead className="text-right">{strings.stockLedger.quantity}</TableHead>
                <TableHead className="text-right">{strings.stockLedger.value}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <StockRow
                  key={row.stock_item_id}
                  row={row}
                  isOpen={open === row.stock_item_id}
                  onToggle={() => {
                    setOpen(open === row.stock_item_id ? null : row.stock_item_id);
                  }}
                />
              ))}
            </TableBody>
          </Table>
        )}
      </QueryState>

      <ExpiringSection />
    </div>
  );
}

/** Split out of the screen because it pushed the parent past the complexity limit — and a
 *  separate component is the better shape anyway: the expiry list has its own query, its own
 *  pending state and its own empty state, none of which the on-hand table needs to know about. */
function ExpiringSection(): ReactElement {
  const expiring = useExpiring(7);
  const batches = expiring.data?.batches ?? [];

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">{strings.stockLedger.expiringTitle}</h2>
      <QueryState
        isPending={expiring.isPending}
        error={expiring.error}
        pendingLabel={strings.stockLedger.expiringTitle}
      >
        {batches.length === 0 ? (
          <p className="text-muted-foreground">{strings.stockLedger.expiringEmpty}</p>
        ) : (
          <ul className="space-y-2">
            {batches.map((batch) => (
              <li
                key={batch.batch_id}
                className="flex flex-wrap items-baseline justify-between gap-2 rounded border border-caution/40 bg-caution-soft px-3 py-2 text-sm"
              >
                <span>
                  {strings.stockLedger.expiringOn}{' '}
                  {batch.expiry_date ?? strings.stockLedger.noExpiry}
                </span>
                <span className="tabular-nums">
                  {strings.stockLedger.remaining} {batch.remaining}
                </span>
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </section>
  );
}

function NegativeBanner({ count }: { count: number }): ReactElement {
  return (
    <div
      role="status"
      className="rounded border border-critical/40 bg-critical-soft px-4 py-3 text-sm"
    >
      <p className="font-semibold">{strings.stockLedger.negativeBanner(count)}</p>
      <p className="mt-1 text-muted-foreground">{strings.stockLedger.negativeHelp}</p>
    </div>
  );
}

function StockRow({
  row,
  isOpen,
  onToggle,
}: {
  row: OnHandRow;
  isOpen: boolean;
  onToggle: () => void;
}): ReactElement {
  return (
    <>
      <TableRow>
        <TableCell>
          <span className="font-medium">{row.name}</span>
          {row.is_negative && (
            // The word, not only the colour. This is the row somebody needs to act on.
            <span className="ml-2 rounded bg-critical-soft px-1.5 py-0.5 text-xs text-critical">
              {strings.stockLedger.negativeTag}
            </span>
          )}
        </TableCell>
        <TableCell className="text-right tabular-nums">
          {row.quantity} {row.base_unit}
        </TableCell>
        <TableCell className="text-right tabular-nums">{formatINR(row.value)}</TableCell>
        <TableCell className="text-right">
          <button
            type="button"
            onClick={onToggle}
            className="text-sm underline underline-offset-4"
            aria-expanded={isOpen}
          >
            {strings.stockLedger.history}
          </button>
        </TableCell>
      </TableRow>
      {isOpen && (
        <TableRow>
          <TableCell colSpan={4} className="bg-muted/40">
            <MovementHistory stockItemId={row.stock_item_id} />
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

/** Every metric must drill through to the rows behind it (`docs/modules.md` M13). This is that. */
function MovementHistory({ stockItemId }: { stockItemId: string }): ReactElement {
  const movements = useMovements(stockItemId);

  return (
    <QueryState
      isPending={movements.isPending}
      error={movements.error}
      pendingLabel={strings.stockLedger.history}
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{strings.stockLedger.movementOn}</TableHead>
            <TableHead>{strings.stockLedger.movementType}</TableHead>
            <TableHead className="text-right">{strings.stockLedger.movementQuantity}</TableHead>
            <TableHead>{strings.stockLedger.movementNote}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {(movements.data ?? []).map((movement) => (
            <MovementRow key={movement.id} movement={movement} />
          ))}
        </TableBody>
      </Table>
    </QueryState>
  );
}

function MovementRow({ movement }: { movement: Movement }): ReactElement {
  return (
    <TableRow>
      <TableCell className="tabular-nums">{movement.business_date}</TableCell>
      <TableCell>
        {strings.stockLedger.types[movement.type]}
        <span className="ml-2 text-xs text-muted-foreground">
          {movement.basis === 'theoretical'
            ? strings.stockLedger.basisTheoretical
            : strings.stockLedger.basisActual}
        </span>
      </TableCell>
      <TableCell className="text-right tabular-nums">{movement.quantity_delta}</TableCell>
      <TableCell className="text-sm text-muted-foreground">{movement.note ?? ''}</TableCell>
    </TableRow>
  );
}
