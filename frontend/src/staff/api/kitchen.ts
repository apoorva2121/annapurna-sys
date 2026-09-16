import { useEffect, useRef, useState } from 'react';
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { apiGet, apiPatch, apiPost, openEventStream } from '@shared/api';
import type { KotLineStatus, KotTicketStatus } from '@shared/enums';

/**
 * The kitchen display.
 *
 * **The rail is read once and then streamed.** `useRail` fetches what a station has to cook and
 * hands back the revision it read at; `useKitchenStream` opens the stream from exactly that
 * revision, so there is no gap between the two and nothing arrives twice. Every event is a whole
 * ticket keyed by its id, so applying one is a replace rather than a merge — which is why a
 * reconnect that re-delivers the last revision costs nothing.
 *
 * **Nothing here polls.** A kitchen display that refetched every few seconds would redraw the rail
 * under a chef's hands mid-service; the stream sends a ticket only when a ticket has changed.
 *
 * **Elapsed time is computed here, not sent.** The server sends `printed_at` and `target_minutes`
 * and the screen counts, because a server-sent "seven minutes ago" is stale the instant it arrives
 * and would need re-fetching every second to stay true.
 */

const KITCHEN_KEY = ['staff', 'kitchen'] as const;

export type KotLine = {
  id: string;
  order_line_id: string;
  item_name: string;
  variant_name: string;
  quantity: number;
  status: KotLineStatus;
  modifier_summary: string | null;
  special_instructions: string | null;
  remake_reason: string | null;
  started_at: string | null;
  ready_at: string | null;
  served_at: string | null;
};

export type KotTicket = {
  id: string;
  ticket_number: string;
  order_id: string;
  order_number: string;
  table_codes: string[];
  station_id: string;
  sequence_in_order: number;
  status: KotTicketStatus;
  is_remake: boolean;
  target_minutes: number;
  business_date: string;
  revision: number;
  printed_at: string;
  acknowledged_at: string | null;
  started_at: string | null;
  ready_at: string | null;
  served_at: string | null;
  lines: KotLine[];
};

export type Rail = { tickets: KotTicket[]; revision: number };

export function useRail(stationId: string | null): UseQueryResult<Rail> {
  return useQuery({
    queryKey: [...KITCHEN_KEY, 'rail', stationId],
    queryFn: () =>
      apiGet<Rail>(`/staff/kot/tickets${stationId === null ? '' : `?station_id=${stationId}`}`),
    // The stream keeps this fresh. A refetch on window focus would redraw the rail every time
    // somebody walks past the tablet.
    refetchOnWindowFocus: false,
    staleTime: Infinity,
  });
}

export function useTicket(ticketId: string): UseQueryResult<KotTicket> {
  return useQuery({
    queryKey: [...KITCHEN_KEY, 'ticket', ticketId],
    queryFn: () => apiGet<KotTicket>(`/staff/kot/tickets/${ticketId}`),
  });
}

/**
 * Put the server's answer straight into the rail, rather than invalidating and refetching.
 *
 * The server returns the whole ticket, so the screen can show the new state immediately. The
 * stream will deliver the same ticket a moment later and replace it with an identical value —
 * harmless, and the reason every event is a whole state rather than a delta.
 */
function useTicketMutation<TVariables>(
  fn: (variables: TVariables) => Promise<KotTicket>,
): UseMutationResult<KotTicket, Error, TVariables> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (ticket) => {
      client.setQueryData([...KITCHEN_KEY, 'ticket', ticket.id], ticket);
      applyToRails(client, ticket);
    },
  });
}

export function useAdvanceTicket(): UseMutationResult<
  KotTicket,
  Error,
  { ticketId: string; status: KotTicketStatus }
> {
  return useTicketMutation(({ ticketId, status }) =>
    apiPatch<KotTicket>(`/staff/kot/tickets/${ticketId}/status`, { status }),
  );
}

export function useAdvanceLine(): UseMutationResult<
  KotTicket,
  Error,
  { ticketId: string; lineId: string; status: KotLineStatus }
> {
  return useTicketMutation(({ ticketId, lineId, status }) =>
    apiPatch<KotTicket>(`/staff/kot/tickets/${ticketId}/lines/${lineId}/status`, { status }),
  );
}

export function useRequestRemake(): UseMutationResult<
  KotTicket,
  Error,
  { ticketId: string; lineId: string; reason: string }
> {
  return useTicketMutation(({ ticketId, lineId, reason }) =>
    apiPost<KotTicket>(`/staff/kot/tickets/${ticketId}/lines/${lineId}/remake`, { reason }),
  );
}

/** Replace this ticket wherever a rail is holding it, and drop it once it has left the rail. */
function applyToRails(client: ReturnType<typeof useQueryClient>, ticket: KotTicket): void {
  client.setQueriesData<Rail>({ queryKey: [...KITCHEN_KEY, 'rail'] }, (rail) => {
    if (rail === undefined) {
      return rail;
    }
    return { ...rail, tickets: mergeTicket(rail.tickets, ticket) };
  });
}

/** A ticket that has left the rail disappears; anything else is replaced in place, or appended. */
export function mergeTicket(tickets: KotTicket[], incoming: KotTicket): KotTicket[] {
  const gone = incoming.status === 'served' || incoming.status === 'cancelled';
  const without = tickets.filter((ticket) => ticket.id !== incoming.id);
  if (gone) {
    return without;
  }
  if (without.length === tickets.length) {
    // New work. Oldest first, because a rail is worked from the top — sorting the newest to the
    // front would have the kitchen cook the last order first all night.
    return [...without, incoming].sort((a, b) => a.printed_at.localeCompare(b.printed_at));
  }
  return tickets.map((ticket) => (ticket.id === incoming.id ? incoming : ticket));
}

export type StreamState = 'connecting' | 'live' | 'reconnecting';

/**
 * Hold the stream open, and keep the rail current from it.
 *
 * **Reconnection lives here rather than in the client**, because only this layer knows what a gap
 * means: the last revision applied is remembered across reconnects, so the server replays what was
 * missed. The backoff is the server's (`retry:`), which is why it is stored rather than invented.
 *
 * The connection state is returned so the screen can say so. `docs/ui/conventions.md`: the kitchen
 * view shows a persistent banner when offline — never silent failure, because a kitchen display
 * that has quietly stopped updating is worse than one that is obviously broken.
 */
export function useKitchenStream(stationId: string | null, startAt: number | undefined): StreamState {
  const client = useQueryClient();
  const [state, setState] = useState<StreamState>('connecting');
  // Refs, not state: changing these must not re-render, and a reconnect must see the latest value
  // without re-running the effect and tearing down the connection it is about to use.
  const cursor = useRef<number | undefined>(startAt);
  const backoff = useRef(3000);

  useEffect(() => {
    if (startAt === undefined) {
      return;
    }
    cursor.current ??= startAt;
    const controller = new AbortController();
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const connect = async (): Promise<void> => {
      try {
        await openEventStream(
          `/staff/kot/stream${stationId === null ? '' : `?station_id=${stationId}`}`,
          {
            signal: controller.signal,
            lastEventId: cursor.current === undefined ? null : String(cursor.current),
            onRetryInterval: (milliseconds) => {
              backoff.current = milliseconds;
            },
            onEvent: (event) => {
              setState('live');
              if (event.event !== 'ticket') {
                return;
              }
              const ticket = JSON.parse(event.data) as KotTicket;
              // The cursor advances only after the ticket has been applied, so a drop between the
              // two replays it rather than skipping it.
              applyToRails(client, ticket);
              client.setQueryData([...KITCHEN_KEY, 'ticket', ticket.id], ticket);
              if (event.id !== null) {
                cursor.current = Number(event.id);
              }
            },
          },
        );
      } catch {
        // Every failure is the same failure to a chef: the screen is not live. The banner says so
        // and the connection is retried; there is nothing here for a person to act on.
      }
      if (!stopped) {
        setState('reconnecting');
        timer = setTimeout(() => void connect(), backoff.current);
      }
    };

    void connect();
    return () => {
      stopped = true;
      controller.abort();
      if (timer !== undefined) {
        clearTimeout(timer);
      }
    };
  }, [client, stationId, startAt]);

  return state;
}
