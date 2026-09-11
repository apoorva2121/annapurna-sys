import { useQueryClient } from '@tanstack/react-query';
import {
  type ReactElement,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { onSessionExpired } from '@shared/api';

import { AuthContext, type AuthState } from './AuthContext';
import { login, logout, restore, type Session } from './session';

/**
 * Holds the session for the whole staff app.
 *
 * Three things happen here and nowhere else: the cold-load restore, the sign-in/sign-out
 * transitions, and the handler the API client calls when a refresh finally fails. Centralising the
 * last one is what stops a dead session from being handled differently on each screen.
 */
export function AuthProvider({ children }: { children: ReactNode }): ReactElement {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const queryClient = useQueryClient();

  // Cold load: the access token died with the previous tab, but the httpOnly refresh cookie did
  // not. Runs exactly once.
  useEffect(() => {
    let cancelled = false;
    void restore().then((restored) => {
      if (!cancelled) {
        setSession(restored);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // The API client cannot import the router, so it reports upward instead. This is the single
  // place a expired session becomes a redirect — the guards below send an unauthenticated user to
  // /login, so clearing the session here is the whole redirect.
  useEffect(() => {
    onSessionExpired(() => {
      setSession(null);
      // Anything already fetched belonged to the session that just ended. Without this, signing in
      // as someone else would briefly show the previous person's staff list from cache — which is
      // the cached-data-after-logout hole manual test A9 probes for.
      queryClient.clear();
    });
    return () => {
      onSessionExpired(null);
    };
  }, [queryClient]);

  const signIn = useCallback(
    async (identifier: string, password: string): Promise<void> => {
      const next = await login(identifier, password);
      queryClient.clear();
      setSession(next);
    },
    [queryClient],
  );

  const signOut = useCallback(async (): Promise<void> => {
    await logout();
    setSession(null);
    queryClient.clear();
  }, [queryClient]);

  const can = useCallback(
    (permission: string): boolean => session?.permissions.has(permission) ?? false,
    [session],
  );

  const value = useMemo<AuthState>(
    () => ({ session, signIn, signOut, can }),
    [session, signIn, signOut, can],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
