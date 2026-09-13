// Every query and mutation for the setup surface. Components never call the API client directly
// (docs/engineering-standards.md §5) — they use these hooks.
//
// Keys are the API's JSON keys verbatim, as everywhere else in this app: no camelCase mapping
// layer until a real feature needs one, because a mapper is a second place for the contract to be
// wrong.
//
// **A rate is a string, both ways.** `"0.0500"` is five percent. It arrives as a string because the
// server sends `Decimal` that way, and it is sent back as a string because parsing it to a
// JavaScript number and re-serialising is exactly how 0.0500 becomes 0.05000000000000001 on some
// bill, some day (CLAUDE.md invariant 3).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { UseMutationResult, UseQueryResult } from '@tanstack/react-query';

import { apiGet, apiPatch, apiPost } from '@shared/api';
import type { RestaurantTheme } from '@shared/theme/theme';

/** A stretch of the day, restaurant local time, when a paid table skips cleaning. `ends` may be
 *  earlier than `starts`: a window can run past midnight (backlog-issues B2). */
export type BusyWindow = { starts: string; ends: string };

/** `cleaning_minutes: null` means only a person clears a table, with Mark ready. */
export type TableSettings = { cleaning_minutes: number | null; busy_windows: BusyWindow[] };

export type Restaurant = {
  id: string;
  name: string;
  code: string;
  timezone: string;
  currency: string;
  business_day_start: string;
  gstin: string | null;
  fssai_licence: string | null;
  address: string | null;
  /** Lives in the server's `settings` JSONB rather than in columns — it is genuinely configuration,
   *  unlike the FSSAI licence that finding S13 moved *out* of settings because it prints on bills.
   *
   *  Optional on the wire: a restaurant saved before this setting existed has no theme block. */
  theme?: RestaurantTheme;
  /** Also `settings` JSONB; the server fills in the five-minute default when none was saved. */
  tables?: TableSettings;
};

export type RestaurantChanges = {
  timezone?: string;
  currency?: string;
  business_day_start?: string;
  gstin?: string | null;
  fssai_licence?: string | null;
  address?: string | null;
  /** Sent whole, never merged: the client owns the complete theme settings, so a removed festive
   *  window is expressible. A merge on the server would make deletion impossible. */
  theme?: RestaurantTheme;
  /** Sent whole, like the theme. Busy mode switched on from the floor is kept by the server. */
  tables?: TableSettings;
};

export type DiningArea = {
  id: string;
  name: string;
  seq: number;
  is_active: boolean;
};

export type RestaurantTable = {
  id: string;
  dining_area_id: string;
  code: string;
  seats: number;
  status: 'free' | 'occupied' | 'reserved' | 'cleaning' | 'out_of_service';
  is_active: boolean;
};

export type Station = {
  id: string;
  code: string;
  name: string;
  seq: number;
  is_active: boolean;
};

export type TaxRate = {
  id: string;
  rate: string;
  is_inclusive: boolean;
  effective_from: string;
  effective_to: string | null;
};

/**
 * A tax class and every rate it has ever charged, newest first.
 *
 * The group is the identity a menu item points at (`menu_item_variant.tax_group_id`); the rates are
 * effective-dated rows beneath it. A rate change adds a row and leaves `id` alone, so nothing on the
 * menu is repointed — M03 spec decision 1.
 */
export type TaxGroup = {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
  rates: TaxRate[];
};

type Page<T> = { items: T[]; next_cursor: string | null };

// One key prefix for the whole surface, so any mutation can invalidate everything setup-related
// without knowing which screens are mounted. Cheap: these lists are small and rarely change.
const SETUP_KEY = ['staff', 'setup'] as const;

function useInvalidateSetup(): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: SETUP_KEY });
  };
}

// --------------------------------------------------------------------------- the restaurant

export function useRestaurant(): UseQueryResult<Restaurant> {
  return useQuery({
    queryKey: [...SETUP_KEY, 'restaurant'],
    queryFn: () => apiGet<Restaurant>('/staff/restaurant'),
  });
}

export function useUpdateRestaurant(): UseMutationResult<Restaurant, Error, RestaurantChanges> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RestaurantChanges) => apiPatch<Restaurant>('/staff/restaurant', body),
    onSuccess: async () => {
      // Not just the setup surface: `timezone` and `business_day_start` are carried in the session
      // and every business date the browser computes reads them. A stale session after this write
      // would have the app disagreeing with the server about what day it is.
      await queryClient.invalidateQueries({ queryKey: SETUP_KEY });
      await queryClient.invalidateQueries({ queryKey: ['session'] });
    },
  });
}

// --------------------------------------------------------------------------- dining areas

export function useDiningAreas(includeInactive = false): UseQueryResult<Page<DiningArea>> {
  return useQuery({
    queryKey: [...SETUP_KEY, 'dining-areas', { includeInactive }],
    queryFn: () =>
      apiGet<Page<DiningArea>>(
        `/staff/setup/dining-areas${includeInactive ? '?include_inactive=true' : ''}`,
      ),
  });
}

export function useCreateDiningArea(): UseMutationResult<DiningArea, Error, { name: string }> {
  const invalidate = useInvalidateSetup();
  return useMutation({
    mutationFn: (body) => apiPost<DiningArea>('/staff/setup/dining-areas', body),
    onSuccess: invalidate,
  });
}

export type DiningAreaChanges = { name?: string; seq?: number; is_active?: boolean };

/**
 * Swap two areas' `seq`. **One mutation, not two.**
 *
 * The screen used to call `update.mutate()` twice on a single observer. `mutate()` detaches the
 * observer from its current mutation and attaches it to the new one, so the first PATCH still
 * executed but stopped being reported: if it failed and the second succeeded, the screen rendered
 * nothing and the two rows were left holding the *same* `seq`. The arrows then became permanently
 * dead — swapping equal values is a no-op — with no error and no explanation. That is the "reported
 * success while wiping the data" shape the restaurant-ui rules cite. Found by external review.
 *
 * Sequential, because the second write must not land before the first is acknowledged: a refetch
 * in between renders an order neither row asked for.
 *
 * `onSettled`, not `onSuccess`: a swap that failed halfway leaves the two rows inconsistent, and
 * the honest response is to refetch and show what actually happened. Real atomicity needs a server
 * `reorder` endpoint taking the whole ordering — that is in docs/backlog.md; this is as close as a
 * client can get, and at least the failure is visible.
 */
export function useSwapDiningAreaSeq(): UseMutationResult<
  void,
  Error,
  { area: DiningArea; other: DiningArea }
> {
  const invalidate = useInvalidateSetup();
  return useMutation({
    mutationFn: async ({ area, other }) => {
      await apiPatch<DiningArea>(`/staff/setup/dining-areas/${area.id}`, { seq: other.seq });
      await apiPatch<DiningArea>(`/staff/setup/dining-areas/${other.id}`, { seq: area.seq });
    },
    onSettled: invalidate,
  });
}

export function useUpdateDiningArea(): UseMutationResult<
  DiningArea,
  Error,
  { id: string; changes: DiningAreaChanges }
> {
  const invalidate = useInvalidateSetup();
  return useMutation({
    mutationFn: ({ id, changes }) =>
      apiPatch<DiningArea>(`/staff/setup/dining-areas/${id}`, changes),
    onSuccess: invalidate,
  });
}

// --------------------------------------------------------------------------- tables

export function useTables(diningAreaId?: string): UseQueryResult<Page<RestaurantTable>> {
  return useQuery({
    queryKey: [...SETUP_KEY, 'tables', { diningAreaId: diningAreaId ?? null }],
    queryFn: () =>
      apiGet<Page<RestaurantTable>>(
        `/staff/setup/tables${diningAreaId === undefined ? '' : `?dining_area_id=${diningAreaId}`}`,
      ),
  });
}

export type NewTable = { dining_area_id: string; code: string; seats: number };

export function useCreateTable(): UseMutationResult<RestaurantTable, Error, NewTable> {
  const invalidate = useInvalidateSetup();
  return useMutation({
    mutationFn: (body) => apiPost<RestaurantTable>('/staff/setup/tables', body),
    onSuccess: invalidate,
  });
}

export type TableChanges = {
  dining_area_id?: string;
  code?: string;
  seats?: number;
  is_active?: boolean;
};

export function useUpdateTable(): UseMutationResult<
  RestaurantTable,
  Error,
  { id: string; changes: TableChanges }
> {
  const invalidate = useInvalidateSetup();
  return useMutation({
    mutationFn: ({ id, changes }) =>
      apiPatch<RestaurantTable>(`/staff/setup/tables/${id}`, changes),
    onSuccess: invalidate,
  });
}

/**
 * Status is not a field of the general table edit. It is live state, and the server refuses
 * `free` or `out_of_service` while an order is still open on the table (M07), so it has its own
 * transition endpoint and its own refusal to show.
 */
export function useSetTableStatus(): UseMutationResult<
  RestaurantTable,
  Error,
  { id: string; status: RestaurantTable['status'] }
> {
  const invalidate = useInvalidateSetup();
  return useMutation({
    mutationFn: ({ id, status }) =>
      apiPost<RestaurantTable>(`/staff/setup/tables/${id}/status`, { status }),
    onSuccess: invalidate,
  });
}

// --------------------------------------------------------------------------- stations

export function useStations(includeInactive = false): UseQueryResult<Page<Station>> {
  return useQuery({
    queryKey: [...SETUP_KEY, 'stations', { includeInactive }],
    queryFn: () =>
      apiGet<Page<Station>>(
        `/staff/setup/stations${includeInactive ? '?include_inactive=true' : ''}`,
      ),
  });
}

export type NewStation = { code: string; name: string };

export function useCreateStation(): UseMutationResult<Station, Error, NewStation> {
  const invalidate = useInvalidateSetup();
  return useMutation({
    mutationFn: (body) => apiPost<Station>('/staff/setup/stations', body),
    onSuccess: invalidate,
  });
}

export type StationChanges = { name?: string; seq?: number; is_active?: boolean };

export function useUpdateStation(): UseMutationResult<
  Station,
  Error,
  { id: string; changes: StationChanges }
> {
  const invalidate = useInvalidateSetup();
  return useMutation({
    mutationFn: ({ id, changes }) => apiPatch<Station>(`/staff/setup/stations/${id}`, changes),
    onSuccess: invalidate,
  });
}

// --------------------------------------------------------------------------- tax

export function useTaxGroups(): UseQueryResult<Page<TaxGroup>> {
  return useQuery({
    queryKey: [...SETUP_KEY, 'tax-groups'],
    queryFn: () => apiGet<Page<TaxGroup>>('/staff/setup/tax-groups'),
  });
}

export type NewTaxGroup = {
  code: string;
  name: string;
  rate: string;
  is_inclusive: boolean;
  effective_from: string;
};

export type NewTaxRate = {
  rate: string;
  is_inclusive: boolean;
  effective_from: string;
};

export function useCreateTaxGroup(): UseMutationResult<TaxGroup, Error, NewTaxGroup> {
  const invalidate = useInvalidateSetup();
  return useMutation({
    mutationFn: (body) => apiPost<TaxGroup>('/staff/setup/tax-groups', body),
    onSuccess: invalidate,
  });
}

export function useRenameTaxGroup(): UseMutationResult<
  TaxGroup,
  Error,
  { id: string; name: string }
> {
  const invalidate = useInvalidateSetup();
  return useMutation({
    mutationFn: ({ id, name }) => apiPatch<TaxGroup>(`/staff/setup/tax-groups/${id}`, { name }),
    onSuccess: invalidate,
  });
}

/**
 * Charge a new rate from a future date. The rate in force until then is closed the day before.
 *
 * Returns the whole group rather than the new rate, because what the user needs to see is the new
 * period beside the one it replaced.
 */
export function useAddTaxRate(): UseMutationResult<
  TaxGroup,
  Error,
  { id: string; body: NewTaxRate }
> {
  const invalidate = useInvalidateSetup();
  return useMutation({
    mutationFn: ({ id, body }) => apiPost<TaxGroup>(`/staff/setup/tax-groups/${id}/rates`, body),
    onSuccess: invalidate,
  });
}
