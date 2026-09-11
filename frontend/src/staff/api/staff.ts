// Every staff-surface query and mutation. Components never call the API client directly
// (docs/engineering-standards.md section 5) — they use these hooks.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { UseMutationResult, UseQueryResult } from '@tanstack/react-query';

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

export function useEmployees(includeInactive: boolean): UseQueryResult<EmployeeList> {
  return useQuery({
    queryKey: [...STAFF_KEY, { includeInactive }],
    queryFn: () =>
      apiGet<EmployeeList>(`/staff/employees${includeInactive ? '?include_inactive=true' : ''}`),
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
