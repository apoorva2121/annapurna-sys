import { type ReactElement, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { formatINR } from '@shared/money';
import { Permission } from '@shared/permissions';
import { Button } from '@shared/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@shared/ui/sheet';
import { useAuth } from '@staff/auth/AuthContext';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { WaiterSurface } from '@staff/components/WaiterSurface';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type FloorArea,
  type FloorTable,
  useFloor,
  useMarkReady,
  useOpenOrder,
  useSetBusy,
  useWaiters,
} from '@staff/api/orders';

/**
 * The table map: the waiter's first screen, and the one they come back to after every table.
 *
 * **One tap into a table.** A free table opens an order and goes straight to order taking; a table
 * with an order on it goes to that order. With Send on the order screen's bottom-right, the table map
 * to the kitchen is the tap into the table, the dishes, and Send (`docs/ui/conventions.md`).
 *
 * **A table being cleared is not a free table** (backlog-issues B2). Found in the M07 manual pass:
 * tapping a settled table to clear it opened an empty order on it, which held it Occupied, and
 * nothing on this screen could clear it. Now it says so, counts down to its cleaning time, and offers
 * Mark ready — and tapping it opens nothing.
 *
 * **Status is a word, never only a colour.** "Occupied", "Bill asked for" — a dim room and a
 * colour-blind waiter are both ordinary, and a border tint alone would fail both.
 */
export default function TableMapScreen(): ReactElement {
  const floor = useFloor();
  const open = useOpenOrder();
  const ready = useMarkReady();
  const navigate = useNavigate();
  const { can } = useAuth();
  // Someone holding order.assign is asked who serves a table first: the person seating a party is
  // often not the person who will serve it, and used to be credited with it (2026-09-14). A waiter
  // opening a table serves it, still in one tap.
  const [choosing, setChoosing] = useState<FloorTable | null>(null);

  function tapTable(table: FloorTable): void {
    if (can(Permission.ORDER_ASSIGN)) {
      setChoosing(table);
      return;
    }
    openTable(table);
  }

  function openTable(table: FloorTable, waiterId?: string): void {
    open.mutate(
      waiterId === undefined
        ? { type: 'dine_in', table_ids: [table.id] }
        : { type: 'dine_in', table_ids: [table.id], waiter_employee_id: waiterId },
      {
        onSuccess: (order) => {
          void navigate(`/orders/${order.id}`);
        },
      },
    );
  }

  function markReady(table: FloorTable): void {
    ready.mutate({ tableId: table.id });
  }

  const areas = floor.data?.areas ?? [];
  const failure = open.error ?? ready.error;
  return (
    <WaiterSurface>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold">{strings.orders.floorTitle}</h1>
          {floor.data !== undefined && <BusyMode busy={floor.data.busy} />}
        </div>
        {failure !== null && <Notice tone="critical" {...errorProps(failure)} />}
        <QueryState
          isPending={floor.isPending}
          error={floor.error}
          pendingLabel={strings.orders.loadingFloor}
        >
          {areas.length === 0 ? (
            <p className="text-muted-foreground">{strings.orders.floorEmpty}</p>
          ) : (
            areas.map((area) => (
              <Area
                key={area.id}
                area={area}
                busy={open.isPending || ready.isPending}
                onOpen={tapTable}
                onReady={markReady}
              />
            ))
          )}
        </QueryState>
        <WhoIsServing
          table={choosing}
          onClose={() => {
            setChoosing(null);
          }}
          onPick={(waiterId) => {
            if (choosing !== null) openTable(choosing, waiterId);
            setChoosing(null);
          }}
        />
      </div>
    </WaiterSurface>
  );
}

/** Who is serving a table, asked of whoever holds order.assign before the table is opened. Leaving
 *  it unassigned lets a waiter claim it from the order screen. */
function WhoIsServing({
  table,
  onPick,
  onClose,
}: {
  table: FloorTable | null;
  onPick: (waiterId?: string) => void;
  onClose: () => void;
}): ReactElement {
  const waiters = useWaiters(table !== null);
  return (
    <Sheet
      open={table !== null}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <SheetContent side="bottom">
        <SheetHeader>
          <SheetTitle>{table === null ? '' : strings.orders.whoIsServing(table.code)}</SheetTitle>
        </SheetHeader>
        <div className="flex flex-col gap-2 py-3">
          <QueryState
            isPending={waiters.isPending}
            error={waiters.error}
            pendingLabel={strings.orders.loadingWaiters}
          >
            {(waiters.data?.items ?? []).map((person) => (
              <Button
                key={person.id}
                variant="secondary"
                size="lg"
                onClick={() => {
                  onPick(person.id);
                }}
              >
                {person.full_name}
              </Button>
            ))}
          </QueryState>
          <Button
            variant="ghost"
            size="lg"
            onClick={() => {
              onPick();
            }}
          >
            {strings.orders.leaveUnassigned}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

/** The switch for whoever holds `floor.manage`; a plain word for everyone else while it is on. */
function BusyMode({ busy }: { busy: boolean }): ReactElement | null {
  const { can } = useAuth();
  const setBusy = useSetBusy();
  if (!can(Permission.FLOOR_MANAGE)) {
    return busy ? (
      <span className="rounded border border-border px-3 py-1 text-sm font-semibold">
        {strings.orders.busyOn}
      </span>
    ) : null;
  }
  return (
    <Button
      variant={busy ? 'primary' : 'secondary'}
      aria-pressed={busy}
      disabled={setBusy.isPending}
      onClick={() => {
        setBusy.mutate({ on: !busy });
      }}
    >
      {busy ? strings.orders.busyOn : strings.orders.busyOff}
    </Button>
  );
}

type CellProps = {
  busy: boolean;
  onOpen: (table: FloorTable) => void;
  onReady: (table: FloorTable) => void;
};

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

/** Whole minutes, never less than one: "Ready in 0 min" reads as a broken clock. */
function minutesUntil(moment: string): number {
  return Math.max(1, Math.ceil((Date.parse(moment) - Date.now()) / 60_000));
}

function TableCell({
  table,
  busy,
  onOpen,
  onReady,
}: CellProps & { table: FloorTable }): ReactElement {
  const live = table.orders[0];
  const status = strings.orders.tableStatuses[table.status] ?? table.status;

  if (live !== undefined) {
    return (
      <Link to={`/orders/${live.id}`} className={`${CELL} border-primary`}>
        <span className="text-lg font-semibold">{table.code}</span>
        <span>{status}</span>
        <span className="text-sm">{strings.orders.orderLabel(live.order_number)}</span>
        {typeof live.waiter_name === 'string' && (
          <span className="text-sm">{live.waiter_name}</span>
        )}
        <span className="font-mono tabular-nums">{formatINR(live.grand_total)}</span>
        {live.bill_requested_at !== null && (
          <span className="font-semibold">{strings.orders.billAsked}</span>
        )}
      </Link>
    );
  }

  if (table.status === 'cleaning') {
    return (
      <div className={`${CELL} border-border`}>
        <span className="text-lg font-semibold">{table.code}</span>
        <span>{status}</span>
        {typeof table.ready_at === 'string' && (
          <span className="text-sm text-muted-foreground">
            {strings.orders.readyIn(minutesUntil(table.ready_at))}
          </span>
        )}
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => {
            onReady(table);
          }}
        >
          {strings.orders.markReady(table.code)}
        </Button>
      </div>
    );
  }

  return (
    <button
      type="button"
      className={`${CELL} border-border disabled:opacity-60`}
      disabled={busy || table.status === 'out_of_service'}
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
