import type { ReactElement } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { formatINR } from '@shared/money';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { WaiterSurface } from '@staff/components/WaiterSurface';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import { type FloorArea, type FloorTable, useFloor, useOpenOrder } from '@staff/api/orders';

/**
 * The table map: the waiter's first screen, and the one they come back to after every table.
 *
 * **One tap into a table.** A free table opens an order and goes straight to order taking; a table
 * with an order on it goes to that order. With Send on the order screen's bottom-right, the table map
 * to the kitchen is the tap into the table, the dishes, and Send (`docs/ui/conventions.md`).
 *
 * **Status is a word, never only a colour.** "Occupied", "Bill asked for" — a dim room and a
 * colour-blind waiter are both ordinary, and a border tint alone would fail both.
 */
export default function TableMapScreen(): ReactElement {
  const floor = useFloor();
  const open = useOpenOrder();
  const navigate = useNavigate();

  function openTable(table: FloorTable): void {
    open.mutate(
      { type: 'dine_in', table_ids: [table.id] },
      {
        onSuccess: (order) => {
          void navigate(`/orders/${order.id}`);
        },
      },
    );
  }

  const areas = floor.data?.areas ?? [];
  return (
    <WaiterSurface>
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold">{strings.orders.floorTitle}</h1>
        {open.isError && <Notice tone="critical" {...errorProps(open.error)} />}
        <QueryState
          isPending={floor.isPending}
          error={floor.error}
          pendingLabel={strings.orders.loadingFloor}
        >
          {areas.length === 0 ? (
            <p className="text-muted-foreground">{strings.orders.floorEmpty}</p>
          ) : (
            areas.map((area) => (
              <Area key={area.id} area={area} opening={open.isPending} onOpen={openTable} />
            ))
          )}
        </QueryState>
      </div>
    </WaiterSurface>
  );
}

type CellProps = { opening: boolean; onOpen: (table: FloorTable) => void };

function Area({ area, ...cell }: CellProps & { area: FloorArea }): ReactElement {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-lg font-semibold">{area.name}</h2>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {area.tables.map((table) => (
          <li key={table.id}>
            <TableCell table={table} {...cell} />
          </li>
        ))}
      </ul>
    </section>
  );
}

const CELL =
  'flex min-h-target w-full flex-col items-start gap-1 rounded-lg border bg-card p-3 text-left';

function TableCell({ table, opening, onOpen }: CellProps & { table: FloorTable }): ReactElement {
  const live = table.orders[0];
  const status = strings.orders.tableStatuses[table.status] ?? table.status;

  if (live !== undefined) {
    return (
      <Link to={`/orders/${live.id}`} className={`${CELL} border-primary`}>
        <span className="text-lg font-semibold">{table.code}</span>
        <span>{status}</span>
        <span className="text-sm">{strings.orders.orderLabel(live.order_number)}</span>
        <span className="font-mono tabular-nums">{formatINR(live.grand_total)}</span>
        {live.bill_requested_at !== null && (
          <span className="font-semibold">{strings.orders.billAsked}</span>
        )}
      </Link>
    );
  }

  return (
    <button
      type="button"
      className={`${CELL} border-border disabled:opacity-60`}
      disabled={opening || table.status === 'out_of_service'}
      onClick={() => {
        onOpen(table);
      }}
    >
      <span className="text-lg font-semibold">{table.code}</span>
      <span>{status}</span>
      <span className="text-sm text-muted-foreground">{strings.orders.seats(table.seats)}</span>
    </button>
  );
}
