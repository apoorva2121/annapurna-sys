// Every staff-surface query and mutation. Components never call the API client directly
// (docs/engineering-standards.md section 5) — they use these hooks.

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  InfiniteData,
  UseInfiniteQueryResult,
  UseMutationResult,
  UseQueryResult,
} from '@tanstack/react-query';

import { apiGet, apiPatch, apiPost } from '@shared/api';
import type { EmploymentType } from '@shared/enums';

export type Employee = {
  id: string;
  employee_code: string;
  full_name: string;
  phone: string | null;
  joined_on: string;
  employment_type: EmploymentType;
  is_active: boolean;
  deactivated_at: string | null;
  has_login: boolean;
  roles: string[];
};

export type EmployeeList = {
  items: Employee[];
  next_cursor: string | null;
};

export type Role = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  rank: number;
  is_system: boolean;
};

export type NewEmployee = {
  full_name: string;
  employee_code: string;
  joined_on: string;
  employment_type: EmploymentType;
  phone?: string | undefined;
  login_identifier?: string | undefined;
  initial_password?: string | undefined;
};

export type EmployeeChanges = {
  full_name?: string;
  phone?: string | null;
  employment_type?: EmploymentType;
};

// One key prefix, so every mutation below can invalidate the whole staff surface without knowing
// which screens are mounted.
const STAFF_KEY = ['staff', 'employees'] as const;

function employeesPath(includeInactive: boolean, cursor: string | null): string {
  const query = new URLSearchParams();
  if (includeInactive) {
    query.set('include_inactive', 'true');
  }
  if (cursor !== null) {
    query.set('cursor', cursor);
  }
  const suffix = query.toString();
  return `/staff/employees${suffix === '' ? '' : `?${suffix}`}`;
}

/**
 * The staff list, one page at a time.
 *
 * Infinite rather than a plain query because the endpoint pages at 50 and answers with a cursor.
 * A screen that fetched once and ignored the cursor would show a 60-person restaurant exactly 50
 * people with nothing to indicate the rest existed — and it would look perfect against the demo
 * data, which has 19.
 */
export function useEmployees(
  includeInactive: boolean,
): UseInfiniteQueryResult<InfiniteData<EmployeeList>> {
  return useInfiniteQuery({
    queryKey: [...STAFF_KEY, { includeInactive }],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => apiGet<EmployeeList>(employeesPath(includeInactive, pageParam)),
    // The server sends a cursor only when the page it just returned was full, so this is null on
    // the last page without the client having to count anything.
    getNextPageParam: (lastPage: EmployeeList) => lastPage.next_cursor,
  });
}

export function useEmployee(employeeId: string): UseQueryResult<Employee> {
  return useQuery({
    queryKey: [...STAFF_KEY, employeeId],
    queryFn: () => apiGet<Employee>(`/staff/employees/${employeeId}`),
  });
}

export function useRoles(): UseQueryResult<Role[]> {
  return useQuery({
    queryKey: ['staff', 'roles'],
    // The catalogue changes when a migration ships, not while someone is looking at it.
    staleTime: 60 * 60 * 1000,
    queryFn: () => apiGet<Role[]>('/staff/roles'),
  });
}

/** Shared by every mutation here: after a write, nothing cached about staff is known to be true. */
function useInvalidateStaff(): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: STAFF_KEY });
  };
}

export function useCreateEmployee(): UseMutationResult<Employee, Error, NewEmployee> {
  const invalidate = useInvalidateStaff();
  return useMutation({
    mutationFn: (body: NewEmployee) => apiPost<Employee>('/staff/employees', body),
    onSuccess: invalidate,
  });
}

export function useUpdateEmployee(
  employeeId: string,
): UseMutationResult<Employee, Error, EmployeeChanges> {
  const invalidate = useInvalidateStaff();
  return useMutation({
    mutationFn: (body: EmployeeChanges) =>
      apiPatch<Employee>(`/staff/employees/${employeeId}`, body),
    onSuccess: invalidate,
  });
}

/** Answers with the whole employee, not just the roles — the server re-reads the row after the
 *  change, so the screen never has to guess what the new state is. */
export function useSetRoles(employeeId: string): UseMutationResult<Employee, Error, string[]> {
  const invalidate = useInvalidateStaff();
  return useMutation({
    mutationFn: (roleIds: string[]) =>
      apiPost<Employee>(`/staff/employees/${employeeId}/roles`, { role_ids: roleIds }),
    onSuccess: invalidate,
  });
}

export function useSetActive(employeeId: string): UseMutationResult<Employee, Error, boolean> {
  const invalidate = useInvalidateStaff();
  return useMutation({
    mutationFn: (active: boolean) =>
      apiPost<Employee>(`/staff/employees/${employeeId}/${active ? 'reactivate' : 'deactivate'}`),
    onSuccess: invalidate,
  });
}

/**
 * Set a new password for someone else (`employee.password.reset`, backlog-issues B6). The server
 * refuses anyone more senior (G-4, G-5), signs them out everywhere, and asks them to choose their own
 * the next time they sign in.
 */
export function useResetPassword(employeeId: string): UseMutationResult<void, Error, string> {
  return useMutation({
    mutationFn: async (newPassword: string) => {
      await apiPost<undefined>(`/staff/employees/${employeeId}/password`, {
        new_password: newPassword,
      });
    },
  });
}

/** The next free employee code (decision D19): filled in on the add-employee form, and editable. */
export function useNextEmployeeCode(): UseQueryResult<{ employee_code: string }> {
  return useQuery({
    queryKey: ['staff', 'employees', 'next-code'],
    queryFn: () => apiGet<{ employee_code: string }>('/staff/employees/next-code'),
  });
}
