import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { apiDelete, apiGet, apiPatch, apiPost } from '@shared/api';
import type {
  ComplaintCategory,
  ComplaintSeverity,
  ComplaintStatus,
  ConsentPurpose,
  ContactSource,
  PreferenceType,
} from '@shared/enums';

/**
 * Customers, consent, feedback and complaints.
 *
 * **What a list returns is this branch's customers, not the organisation's.** The record belongs to
 * the business so a chain recognises one diner across its branches; the view belongs to the branch.
 * Handling a second branch is an assignment and a switch — M01's existing gesture — so this client
 * has no "which branch" parameter and could not have one.
 *
 * **No consent is ever granted by default.** `recordConsent` takes one purpose and one answer, and
 * the screen sends it only when somebody ticked something. `docs/compliance-rules.md` §B2: a phone
 * number collected for a bill is not marketing consent.
 *
 * **Erasure is irreversible and the response says what survived.** It returns the orders and the
 * lifetime value it kept, so the screen can show both rather than asking anybody to take the
 * second half on trust.
 */

const CUSTOMERS_KEY = ['staff', 'customers'] as const;
const COMPLAINTS_KEY = ['staff', 'complaints'] as const;
const FEEDBACK_KEY = ['staff', 'feedback'] as const;

export type CustomerPreference = {
  id: string;
  type: PreferenceType;
  value: string;
  is_critical: boolean;
};

export type ConsentState = {
  purpose: ConsentPurpose;
  granted: boolean;
  occurred_at: string;
  notice_version: string;
  notice_language: string;
  source: ContactSource;
};

export type Customer = {
  id: string;
  phone: string;
  name: string | null;
  email: string | null;
  first_visit_at: string | null;
  last_visit_at: string | null;
  visit_count: number;
  lifetime_value: string;
  birthday: string | null;
  anniversary: string | null;
  is_erased: boolean;
  is_active: boolean;
  preferences: CustomerPreference[];
  consents: ConsentState[];
};

export type CustomerListItem = {
  id: string;
  phone: string;
  name: string | null;
  visit_count: number;
  last_visit_at: string | null;
  is_erased: boolean;
};

export type Visit = {
  order_id: string;
  business_date: string;
  total: string;
  items: string[];
};

export type Feedback = {
  id: string;
  order_id: string | null;
  customer_id: string | null;
  overall_rating: number | null;
  food_rating: number | null;
  service_rating: number | null;
  cleanliness_rating: number | null;
  would_return: boolean | null;
  waiter_employee_id: string | null;
  comment: string | null;
  source: ContactSource;
  submitted_at: string;
  business_date: string;
};

export type Complaint = {
  id: string;
  reference: string;
  customer_id: string | null;
  order_id: string | null;
  category: ComplaintCategory;
  severity: ComplaintSeverity;
  description: string;
  assigned_to: string | null;
  status: ComplaintStatus;
  resolution: string | null;
  compensation_amount: string | null;
  resolved_at: string | null;
  business_date: string;
  /** Derived from the order ledger, never stored. `null` before the complaint is resolved, because
   *  "did they come back" has no meaning yet — and `false` would read as "they did not". */
  customer_returned: boolean | null;
};

export type CustomerHistory = {
  visits: Visit[];
  feedback: Feedback[];
  complaints: Complaint[];
};

export type Erasure = {
  customer_id: string;
  erased_at: string;
  preferences_deleted: number;
  orders_retained: number;
  lifetime_value_retained: string;
};

export function useCustomers(search: string): UseQueryResult<CustomerListItem[]> {
  return useQuery({
    queryKey: [...CUSTOMERS_KEY, 'list', search],
    queryFn: () =>
      apiGet<{ items: CustomerListItem[] }>(
        search ? `/staff/customers?search=${encodeURIComponent(search)}` : '/staff/customers',
      ).then((page) => page.items),
  });
}

export function useCustomer(customerId: string): UseQueryResult<Customer> {
  return useQuery({
    queryKey: [...CUSTOMERS_KEY, customerId],
    queryFn: () => apiGet<Customer>(`/staff/customers/${customerId}`),
  });
}

export function useCustomerHistory(customerId: string): UseQueryResult<CustomerHistory> {
  return useQuery({
    queryKey: [...CUSTOMERS_KEY, customerId, 'history'],
    queryFn: () => apiGet<CustomerHistory>(`/staff/customers/${customerId}/history`),
  });
}

export function useAddPreference(
  customerId: string,
): UseMutationResult<Customer, Error, { type: PreferenceType; value: string; is_critical: boolean }> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiPost<Customer>(`/staff/customers/${customerId}/preferences`, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: [...CUSTOMERS_KEY, customerId] });
    },
  });
}

export function useRemovePreference(customerId: string): UseMutationResult<void, Error, string> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (preferenceId) =>
      apiDelete(`/staff/customers/${customerId}/preferences/${preferenceId}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: [...CUSTOMERS_KEY, customerId] });
    },
  });
}

export function useRecordConsent(
  customerId: string,
): UseMutationResult<
  ConsentState,
  Error,
  { purpose: ConsentPurpose; granted: boolean; notice_version: string; notice_language: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiPost<ConsentState>(`/staff/customers/${customerId}/consent`, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: [...CUSTOMERS_KEY, customerId] });
    },
  });
}

export function useEraseCustomer(
  customerId: string,
): UseMutationResult<Erasure, Error, Record<string, never>> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<Erasure>(`/staff/customers/${customerId}/erase`, {}),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: CUSTOMERS_KEY });
    },
  });
}

export function useUpdateCustomer(
  customerId: string,
): UseMutationResult<Customer, Error, { name?: string | null; email?: string | null }> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiPatch<Customer>(`/staff/customers/${customerId}`, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: [...CUSTOMERS_KEY, customerId] });
    },
  });
}

export function useOpenComplaints(): UseQueryResult<Complaint[]> {
  return useQuery({
    queryKey: COMPLAINTS_KEY,
    queryFn: () =>
      apiGet<{ items: Complaint[] }>('/staff/complaints').then((page) => page.items),
  });
}

export function useResolveComplaint(): UseMutationResult<
  Complaint,
  Error,
  { complaintId: string; resolution: string; compensation_amount?: string | null }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ complaintId, ...body }) =>
      apiPost<Complaint>(`/staff/complaints/${complaintId}/resolve`, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: COMPLAINTS_KEY });
    },
  });
}

export function useCloseComplaint(): UseMutationResult<Complaint, Error, string> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (complaintId) =>
      apiPost<Complaint>(`/staff/complaints/${complaintId}/close`, {}),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: COMPLAINTS_KEY });
    },
  });
}

export function useFeedbackDay(businessDate: string): UseQueryResult<Feedback[]> {
  return useQuery({
    queryKey: [...FEEDBACK_KEY, businessDate],
    queryFn: () =>
      apiGet<{ items: Feedback[] }>(`/staff/feedback?business_date=${businessDate}`).then(
        (page) => page.items,
      ),
  });
}
