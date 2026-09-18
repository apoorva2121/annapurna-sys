import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';

import { apiGet, apiPost } from '@shared/api';

/**
 * The audit trail, and the notification centre.
 *
 * **The sentence comes from the server.** *"Priya repriced a dish — price 480.00 → 520.00."* One
 * phrasing, so a screen, an export and a future email cannot disagree about what a row means — the
 * same reason M13's comparisons are computed server-side.
 *
 * **Every condition in the centre is live.** Nothing here is a stored notification: the list is a
 * set of queries, so a warning about stock disappears the moment somebody records the delivery. A
 * refetch is therefore meaningful rather than cosmetic, which is why marking one read invalidates
 * the list instead of patching it in place.
 */

const AUDIT_KEY = ['staff', 'audit'] as const;
const NOTICES_KEY = ['staff', 'notifications'] as const;

export type AuditEntry = {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  actor_employee_id: string | null;
  actor_name: string | null;
  occurred_at: string;
  /** What happened, in words. The raw values sit beneath it for when words are not enough. */
  sentence: string;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  reason: string | null;
};

export type AuditPage = {
  items: AuditEntry[];
  next_cursor: string | null;
};

export type AuditFilters = {
  entityType?: string;
  actorEmployeeId?: string;
  since?: string;
  until?: string;
};

export type Notice = {
  /** The condition's own identity. Dismissing this one leaves the next of its kind alone. */
  key: string;
  kind: string;
  severity: string;
  subject: string;
  detail: string;
  ref_type: string;
  ref_id: string;
  occurred_at: string | null;
  read: boolean;
  dismissed: boolean;
};

export type NoticeList = {
  items: Notice[];
  unread: number;
};

function query(filters: AuditFilters): string {
  const params = new URLSearchParams();
  if (filters.entityType !== undefined && filters.entityType !== '') {
    params.set('entity_type', filters.entityType);
  }
  if (filters.actorEmployeeId !== undefined && filters.actorEmployeeId !== '') {
    params.set('actor_employee_id', filters.actorEmployeeId);
  }
  if (filters.since !== undefined && filters.since !== '') {
    params.set('since', `${filters.since}T00:00:00Z`);
  }
  if (filters.until !== undefined && filters.until !== '') {
    params.set('until', `${filters.until}T23:59:59Z`);
  }
  return params.size === 0 ? '' : `?${params.toString()}`;
}

export function useAuditTrail(filters: AuditFilters = {}): UseQueryResult<AuditPage> {
  return useQuery({
    queryKey: [...AUDIT_KEY, filters],
    queryFn: () => apiGet<AuditPage>(`/staff/audit${query(filters)}`),
  });
}

export function useNotifications(): UseQueryResult<NoticeList> {
  return useQuery({
    queryKey: NOTICES_KEY,
    queryFn: () => apiGet<NoticeList>('/staff/notifications'),
  });
}

export function useMarkNotice(): ReturnType<
  typeof useMutation<void, unknown, { key: string; dismissed?: boolean }>
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ key, dismissed = false }) =>
      apiPost('/staff/notifications/read', { key, dismissed }),
    // Invalidated rather than patched: the conditions are queries, so the answer after the write
    // may legitimately differ from the answer before it in more ways than the one field changed.
    onSuccess: () => client.invalidateQueries({ queryKey: NOTICES_KEY }),
  });
}
