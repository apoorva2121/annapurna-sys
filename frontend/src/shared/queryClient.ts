import { QueryClient } from '@tanstack/react-query';

// One client for the staff app. The defaults are tuned for restaurant floor devices, not desktops:
//
// - refetchOnWindowFocus off: a waiter's phone blurs and focuses constantly as they move between
//   apps, and a refetch storm on a bad basement network is worse than slightly stale data.
// - retry 1: one retry absorbs a dropped packet; more than that just delays the error state a user
//   needs to see (docs/engineering-standards.md section 5 — no silent failures).
// - staleTime 30s: long enough to stop duplicate fetches when several components mount together,
//   short enough that nothing on screen is meaningfully out of date.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30_000,
    },
  },
});
