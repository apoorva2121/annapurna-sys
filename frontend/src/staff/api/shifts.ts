import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { apiDelete, apiGet, apiPatch, apiPost } from '@shared/api';
import type { ShiftAssignmentStatus } from '@shared/enums';

/**
 * The roster and the clock.
 *
 * **Clocking in sends no body.** There is no employee id to put in one: the server takes the
 * actor's own and refuses an assignment that is not theirs. A mutation here that accepted a person
 * would be a mutation somebody would eventually wire to a dropdown.
 *
 * **Nothing here computes a business date.** `today` comes back from the server with every roster
 * read, because a restaurant's day starts at 05:00 and a browser asked at 2am would answer
 * yesterday — CLAUDE.md invariant 4, and the reason M07's screens do the same.
 *
 * **Nothing here decides who is late, either.** The status arrives derived; a screen comparing a
 * clock-in to a start time would be a second implementation of a rule whose whole point is having
 * one.
 */

const SHIFTS_KEY = ['staff', 'shifts'] as const;

export type Shift = {
  id: string;
  name: string;
  start_time: string;
  end_time: string;
  /** Derived by the server, so a screen never compares two times to know how to render one. */
  crosses_midnight: boolean;
  is_active: boolean;
};

export type Assignment = {
  id: string;
  shift_id: string;
  shift_name: string;
  start_time: string;
  end_time: string;
  employee_id: string;
  employee_name: string | null;
  dining_area_id: string | null;
  business_date: string;
  status: ShiftAssignmentStatus;
  clock_in_at: string | null;
  clock_out_at: string | null;
  /** Clocked in and never out. Shown as open rather than closed at a guessed time. */
  is_open: boolean;
};

export type Roster = {
  since: string;
  until: string;
  items: Assignment[];
};

export type OnNowEntry = {
  assignment_id: string;
  employee_id: string;
  employee_name: string | null;
  shift_name: string;
  dining_area_id: string | null;
  status: ShiftAssignmentStatus;
};

export type OnNow = {
  business_date: string;
  items: OnNowEntry[];
};

export function useShifts(): UseQueryResult<{ items: Shift[] }> {
  return useQuery({
    queryKey: [...SHIFTS_KEY, 'list'],
    queryFn: () => apiGet<{ items: Shift[] }>('/staff/shifts'),
    // A shift template changes when an owner reorganises the day, which is rarely.
    staleTime: 5 * 60 * 1000,
  });
}

export function useRoster(since?: string, until?: string): UseQueryResult<Roster> {
  const params = new URLSearchParams();
  if (since !== undefined) {
    params.set('since', since);
  }
  if (until !== undefined) {
    params.set('until', until);
  }
  const query = params.size === 0 ? '' : `?${params.toString()}`;
  return useQuery({
    queryKey: [...SHIFTS_KEY, 'roster', since ?? '', until ?? ''],
    queryFn: () => apiGet<Roster>(`/staff/shifts/roster${query}`),
  });
}

export function useMyShifts(): UseQueryResult<Roster> {
  return useQuery({
    queryKey: [...SHIFTS_KEY, 'me'],
    queryFn: () => apiGet<Roster>('/staff/shifts/me'),
  });
}

export function useOnNow(): UseQueryResult<OnNow> {
  return useQuery({
    queryKey: [...SHIFTS_KEY, 'on-now'],
    queryFn: () => apiGet<OnNow>('/staff/shifts/on-now'),
  });
}

export function useCreateShift(): UseMutationResult<
  Shift,
  Error,
  { name: string; startTime: string; endTime: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ name, startTime, endTime }) =>
      apiPost<Shift>('/staff/shifts', {
        name,
        start_time: startTime,
        end_time: endTime,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: SHIFTS_KEY });
    },
  });
}

export function useAssign(): UseMutationResult<
  Assignment,
  Error,
  {
    shiftId: string;
    employeeId: string;
    businessDate: string;
    diningAreaId?: string | null;
  }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ shiftId, employeeId, businessDate, diningAreaId }) =>
      apiPost<Assignment>('/staff/shifts/assignments', {
        shift_id: shiftId,
        employee_id: employeeId,
        business_date: businessDate,
        ...(diningAreaId === undefined || diningAreaId === null
          ? {}
          : { dining_area_id: diningAreaId }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: SHIFTS_KEY });
    },
  });
}

export function useUnassign(): UseMutationResult<void, Error, { assignmentId: string }> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ assignmentId }) => {
      await apiDelete<undefined>(`/staff/shifts/assignments/${assignmentId}`);
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: SHIFTS_KEY });
    },
  });
}

export function useSetAssignmentStatus(): UseMutationResult<
  Assignment,
  Error,
  { assignmentId: string; status: ShiftAssignmentStatus }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ assignmentId, status }) =>
      apiPost<Assignment>(`/staff/shifts/assignments/${assignmentId}/status`, { status }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: SHIFTS_KEY });
    },
  });
}

/** A manager fixing a time. The reason is not optional here because it is not optional there. */
export function useCorrectAssignment(): UseMutationResult<
  Assignment,
  Error,
  {
    assignmentId: string;
    reason: string;
    clockInAt?: string;
    clockOutAt?: string;
    diningAreaId?: string;
  }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ assignmentId, reason, clockInAt, clockOutAt, diningAreaId }) =>
      apiPatch<Assignment>(`/staff/shifts/assignments/${assignmentId}`, {
        reason,
        ...(clockInAt === undefined ? {} : { clock_in_at: clockInAt }),
        ...(clockOutAt === undefined ? {} : { clock_out_at: clockOutAt }),
        ...(diningAreaId === undefined ? {} : { dining_area_id: diningAreaId }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: SHIFTS_KEY });
    },
  });
}

/**
 * Clock in, or out. **Neither takes a person** — see the module docstring.
 */
export function useClock(): UseMutationResult<
  Assignment,
  Error,
  { assignmentId: string; direction: 'in' | 'out' }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ assignmentId, direction }) =>
      apiPost<Assignment>(`/staff/shifts/assignments/${assignmentId}/clock-${direction}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: SHIFTS_KEY });
    },
  });
}
