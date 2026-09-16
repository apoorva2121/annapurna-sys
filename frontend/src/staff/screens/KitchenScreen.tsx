import { type ReactElement, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { Button } from '@shared/ui/button';
import { KdsSurface } from '@staff/components/KdsSurface';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type KotTicket,
  type StreamState,
  useAdvanceTicket,
  useKitchenStream,
  useRail,
} from '@staff/api/kitchen';
import { useStations } from '@staff/api/setup';
import { elapsedMinutes, nextStep } from '@staff/screens/kitchenRail';

/**
 * The rail: what this station has to cook, oldest first, read from two metres.
 *
 * **Every rule on this screen is physical** (`docs/ui/conventions.md`). Base type at 20px and order
 * numbers at 40px, because the person reading is two metres away. No modals, because a chef cannot
 * dismiss a dialog with wet hands — the ticket detail is a route. No scrolling: the rail shows what
 * fits. Colour never carries meaning alone; `late` is a word and a position as well as a red edge,
 * because commercial kitchens are full of colour-blind men and steamed-up screens.
 *
 * **One button per ticket, and it is the next step.** A chef should never have to decide which of
 * four controls applies — the ticket knows where it is, so the screen shows the one thing that
 * happens next and names it.
 *
 * **Elapsed time counts here.** The server sends `printed_at` and the standard; a server-sent
 * "seven minutes ago" would be stale on arrival and would need a refetch a second to stay true.
 *
 * **There is no Served button**, and that is the module's main control rather than an omission. A
 * dish is served when it reaches a table, which this screen cannot see — the waiter does it from
 * the order. Marking a rail ready settles nothing.
 */
export default function KitchenScreen(): ReactElement {
  const stations = useStations();
  const [stationId, setStationId] = useState<string | null>(() => remembered());
  const rail = useRail(stationId);
  const stream = useKitchenStream(stationId, rail.data?.revision);
  const now = useTicker();

  useEffect(() => {
    if (stationId !== null) {
      try {
        window.localStorage.setItem(STATION_KEY, stationId);
      } catch {
        // A wall tablet with storage disabled picks its station again after a reload. Annoying,
        // and not worth failing a kitchen display over.
      }
    }
  }, [stationId]);

  return (
    <KdsSurface>
      <div className="flex flex-col gap-page p-page">
        <header className="flex flex-wrap items-center justify-between gap-page">
          <h1 className="text-3xl font-semibold">{strings.kitchen.title}</h1>
          <StationPicker
            stations={stations.data?.items ?? []}
            stationId={stationId}
            onPick={setStationId}
          />
        </header>

        <ConnectionBanner state={stream} />

        <QueryState
          isPending={rail.isPending}
          error={rail.error}
          pendingLabel={strings.kitchen.loading}
        >
          <Rail tickets={rail.data?.tickets ?? []} now={now} />
        </QueryState>
      </div>
    </KdsSurface>
  );
}

const STATION_KEY = 'restaurant-os-kds-station';

function remembered(): string | null {
  try {
    return window.localStorage.getItem(STATION_KEY);
  } catch {
    return null;
  }
}

/**
 * One second, because the elapsed time on every ticket counts up and a chef watches it.
 *
 * Cheap: it re-renders a screen holding at most a page of tickets, and it is the only timer in the
 * application.
 */
function useTicker(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => { setNow(Date.now()); }, 1000);
    return () => { clearInterval(timer); };
  }, []);
  return now;
}

function StationPicker({
  stations,
  stationId,
  onPick,
}: {
  stations: { id: string; name: string }[];
  stationId: string | null;
  onPick: (id: string | null) => void;
}): ReactElement {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={strings.kitchen.stationLabel}>
      <Button
        variant={stationId === null ? 'primary' : 'secondary'}
        onClick={() => { onPick(null); }}
      >
        {strings.kitchen.allStations}
      </Button>
      {stations.map((station) => (
        <Button
          key={station.id}
          variant={stationId === station.id ? 'primary' : 'secondary'}
          onClick={() => { onPick(station.id); }}
        >
          {station.name}
        </Button>
      ))}
    </div>
  );
}

/**
 * Says so when the screen is not live.
 *
 * `docs/ui/conventions.md`: never silent failure. A kitchen display that has quietly stopped
 * updating is worse than one that is obviously broken, because the chef keeps believing it.
 */
function ConnectionBanner({ state }: { state: StreamState }): ReactElement | null {
  if (state === 'live') {
    return null;
  }
  return (
    <Notice
      // `critical` while reconnecting rather than a softer tone: a rail that is not live is the
      // one thing on this screen a chef must not keep trusting.
      tone={state === 'reconnecting' ? 'critical' : 'info'}
      title={
        state === 'reconnecting' ? strings.kitchen.reconnecting : strings.kitchen.connecting
      }
    />
  );
}

function Rail({ tickets, now }: { tickets: KotTicket[]; now: number }): ReactElement {
  if (tickets.length === 0) {
    return (
      <p className="text-xl text-muted-foreground">{strings.kitchen.empty}</p>
    );
  }
  return (
    <ul className="grid grid-cols-1 gap-page md:grid-cols-2 xl:grid-cols-3">
      {tickets.map((ticket) => (
        <li key={ticket.id}>
          <Ticket ticket={ticket} now={now} />
        </li>
      ))}
    </ul>
  );
}

function Ticket({ ticket, now }: { ticket: KotTicket; now: number }): ReactElement {
  const advance = useAdvanceTicket();
  const minutes = elapsedMinutes(ticket.printed_at, now);
  const late = minutes > ticket.target_minutes;
  const next = nextStep(ticket.status);

  return (
    <article
      className={`flex flex-col gap-3 rounded-lg border-4 bg-card p-page ${
        late ? 'border-critical' : 'border-border'
      }`}
    >
      <header className="flex items-baseline justify-between gap-3">
        {/* 40px, per the conventions: the number is what a chef looks for from across a kitchen. */}
        <span className="text-[2.5rem] font-bold leading-none tabular-nums">
          {ticket.order_number}
        </span>
        <span className="text-xl">
          {ticket.table_codes.length === 0
            ? strings.kitchen.takeaway
            : ticket.table_codes.join(', ')}
        </span>
      </header>

      <p className="flex items-center gap-3 text-xl">
        {/* Colour is never the only signal: "LATE" is a word, and the border is a fourth cue. */}
        <span className={`font-bold tabular-nums ${late ? 'text-critical' : ''}`}>
          {minutes} {strings.kitchen.minutesShort}
        </span>
        {late ? <span className="font-bold text-critical">{strings.kitchen.late}</span> : null}
        {ticket.is_remake ? (
          <span className="font-bold text-warning">{strings.kitchen.remake}</span>
        ) : null}
        {ticket.sequence_in_order > 1 ? (
          <span>{strings.kitchen.round(ticket.sequence_in_order)}</span>
        ) : null}
      </p>

      <ul className="flex flex-col gap-2 text-xl">
        {ticket.lines.map((line) => (
          <li key={line.id} className="flex flex-col">
            <span className="font-semibold">
              {line.quantity} × {line.item_name} ({line.variant_name})
            </span>
            {line.modifier_summary === null ? null : (
              <span className="text-warning">{line.modifier_summary}</span>
            )}
            {line.special_instructions === null ? null : (
              <span className="font-bold text-warning">{line.special_instructions}</span>
            )}
          </li>
        ))}
      </ul>

      <footer className="flex flex-wrap gap-3">
        {next === null ? null : (
          <Button
            onClick={() => { advance.mutate({ ticketId: ticket.id, status: next }); }}
            disabled={advance.isPending}
          >
            {strings.kitchen.step[next]}
          </Button>
        )}
        <Button variant="secondary" asChild>
          <Link to={`/kitchen/${ticket.id}`}>{strings.kitchen.openTicket}</Link>
        </Button>
      </footer>

      {advance.error === null ? null : (
        <Notice tone="critical" {...errorProps(advance.error)} />
      )}
    </article>
  );
}
