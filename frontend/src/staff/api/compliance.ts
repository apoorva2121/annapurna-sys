import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';

import { apiGet, apiPost, downloadCsv } from '@shared/api';

/**
 * Compliance, and the three things this client deliberately does not do.
 *
 * **Nothing here decides whether something is wrong.** Every finding arrives finished — its title,
 * its risk, its action and its citation. A browser evaluating an Indian rule would be a second
 * implementation of the law, free to disagree with the one that wrote the record, and the record
 * is what an owner hands an inspector.
 *
 * **Nothing here hides a finding.** Suppression is a POST that records a decision; it is not a
 * filter the screen applies. A finding a person set aside stays on the list, marked, because
 * advice ignored is still advice given.
 *
 * **Nothing here reformats a citation into a claim.** `status` is carried through as it comes —
 * `in_force`, `notified_not_in_force`, `unsettled`, `unverified` — and the screen says which in
 * words. `docs/compliance-rules.md`: only the first is safe to build on, and only the first may
 * block a user.
 *
 * Note the query is not `staleTime: Infinity`. Asking the server re-runs the evaluation, which is
 * how this module works at all (there is no background job, ADR 0005) — so a refetch here writes
 * to the record, and that is deliberate rather than an accident of caching.
 */

const KEY = ['staff', 'compliance'] as const;

export type Citation = {
  instrument: string;
  commencement: string;
  /** When somebody last confirmed the citation against the instrument. */
  checked_on: string;
  /** in_force | notified_not_in_force | unsettled | unverified */
  status: string;
};

export type Finding = {
  id: string;
  rule_code: string;
  /** critical | warning | advisory. Only a rule in force can be critical. */
  severity: string;
  /** open | acknowledged | suppressed | resolved */
  state: string;
  title: string;
  risk: string;
  action: string;
  evidence: Record<string, unknown>;
  /** When this system first *detected* it — not when the condition began. */
  raised_at: string;
  resolved_at: string | null;
  citation: Citation | null;
};

export type Review = {
  as_of: string;
  business_date: string;
  /** Open findings only. Zero means the card says nothing at all. */
  outstanding: number;
  findings: Finding[];
};

export type Rule = {
  code: string;
  title: string;
  severity: string;
  citation: Citation;
};

export function useCompliance(): UseQueryResult<Review> {
  return useQuery({
    queryKey: KEY,
    queryFn: () => apiGet<Review>('/staff/compliance/findings'),
  });
}

export function useComplianceHistory(): UseQueryResult<Finding[]> {
  return useQuery({
    queryKey: [...KEY, 'history'],
    queryFn: () => apiGet<Finding[]>('/staff/compliance/history'),
  });
}

export function useRules(): UseQueryResult<{ rules: Rule[] }> {
  return useQuery({
    queryKey: [...KEY, 'rules'],
    queryFn: () => apiGet<{ rules: Rule[] }>('/staff/compliance/rules'),
  });
}

export function useAcknowledge(): ReturnType<typeof useMutation<unknown, unknown, { id: string }>> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id }) => apiPost(`/staff/compliance/findings/${id}/acknowledge`, {}),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  });
}

export function useSuppress(): ReturnType<
  typeof useMutation<unknown, unknown, { id: string; reason: string }>
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }) =>
      apiPost(`/staff/compliance/findings/${id}/suppress`, { reason }),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  });
}

/** Fetched with the session's token rather than linked — see `ExportButton`. */
export async function exportCompliance(): Promise<void> {
  await downloadCsv('/staff/compliance/export', 'compliance.csv');
}
