import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';

import { apiGet, apiPost } from '@shared/api';

/**
 * Performance, and the three things this client deliberately cannot do.
 *
 * **There is no type here that can hold a ranked list of other people.** `TeamLine` has no rank
 * field, because the server's schema has none — a bottom ranking is prevented by the shape of the
 * data rather than by how a screen chooses to sort it.
 *
 * **Nothing computes a score.** Every figure, every share and every sentence arrives finished. A
 * browser recomputing somebody's points from their metrics would be a second implementation of the
 * thing that decides what people are paid, free to disagree with the one that paid them.
 *
 * **There is no endpoint for somebody else's own view.** `useMyScore` takes no employee id because
 * the route takes none: it answers about the caller, and that is a property of the API rather than
 * a habit of this file.
 */

const KEY = ['staff', 'performance'] as const;

export type Metric = {
  key: string;
  value: string;
  /** controllable | context. A context metric is shown and counts for nothing. */
  kind: string;
  /** How many things the rate came from — what makes a wrong attribution visible. */
  count: number;
  weighted: boolean;
  /** Plain English, from the server. "You served 214 covers." */
  sentence: string;
};

export type MyScore = {
  period_id: string;
  employee_id: string;
  hours: string;
  points: string;
  rank: number | null;
  of: number;
  metrics: Metric[];
  /** What these figures are used for, said in the product rather than only in a document. */
  purpose: string;
};

/** Deliberately has no rank. See the module docstring. */
export type TeamLine = {
  employee_id: string;
  points: string;
  hours: string;
};

export type Team = {
  period_id: string;
  /** False when the team is too small for anybody to be shown anybody else. */
  shows_others: boolean;
  lines: TeamLine[];
};

export type Share = {
  employee_id: string;
  hours: string;
  covers: number;
  orders: number;
  assists: number;
  covers_share: string;
  hours_share: string;
  /** A share of the work above a share of the roster. A fact about the rota. */
  carrying_more_than_their_hours: boolean;
};

export type Distribution = {
  since: string;
  until: string;
  lines: Share[];
};

export type Scheme = {
  id: string;
  name: string;
  period_type: string;
  weights: Record<string, string>;
  is_active: boolean;
  effective_from: string;
};

export type Period = {
  id: string;
  incentive_scheme_id: string;
  period_start: string;
  period_end: string;
  status: string;
  published_at: string | null;
  /** A period cannot be published while this is above zero. */
  unanswered_disputes: number;
};

export function useMyScore(periodId: string): UseQueryResult<MyScore | null> {
  return useQuery({
    queryKey: [...KEY, 'me', periodId],
    queryFn: () => apiGet<MyScore | null>(`/staff/performance/me?period_id=${periodId}`),
  });
}

export function useTeam(periodId: string): UseQueryResult<Team> {
  return useQuery({
    queryKey: [...KEY, 'team', periodId],
    queryFn: () => apiGet<Team>(`/staff/performance/team?period_id=${periodId}`),
  });
}

export function useDistribution(since?: string, until?: string): UseQueryResult<Distribution> {
  const params = new URLSearchParams();
  if (since !== undefined && since !== '') {
    params.set('since', since);
  }
  if (until !== undefined && until !== '') {
    params.set('until', until);
  }
  const query = params.size === 0 ? '' : `?${params.toString()}`;
  return useQuery({
    queryKey: [...KEY, 'distribution', since ?? '', until ?? ''],
    queryFn: () => apiGet<Distribution>(`/staff/performance/distribution${query}`),
  });
}

export function useGrantAward(): ReturnType<
  typeof useMutation<
    unknown,
    unknown,
    { employee_id: string; type: string; citation: string; amount?: string }
  >
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiPost('/staff/recognition/awards', body),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  });
}

export function useRaiseDispute(): ReturnType<
  typeof useMutation<unknown, unknown, { periodId: string; employeeId: string; note: string }>
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ periodId, employeeId, note }) =>
      apiPost(`/staff/performance/periods/${periodId}/notes`, {
        employee_id: employeeId,
        note,
        kind: 'dispute',
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  });
}
