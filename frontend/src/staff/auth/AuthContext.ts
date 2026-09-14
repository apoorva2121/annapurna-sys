// The context object and its hook, kept apart from the provider component.
//
// Not stylistic: eslint's react-refresh/only-export-components rule fires when a module exports
// both a component and a non-component, and the fix is to split rather than to silence it.

import { createContext, useContext } from 'react';

import type { Session } from './session';

export type AuthState = {
  /** null once we know nobody is signed in; undefined while we are still finding out. The
   *  difference matters — rendering the login screen during the check would flash it at every
   *  signed-in user on every page load. */
  session: Session | null | undefined;
  /** `choice` is the second step when one login belongs to more than one organization (B4). */
  signIn: (
    identifier: string,
    password: string,
    choice?: { ticket: string; organizationId: string },
  ) => Promise<void>;
  signOut: () => Promise<void>;
  /** Presentation only. The server authorises every request regardless (M01 spec). */
  can: (permission: string) => boolean;
};

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const state = useContext(AuthContext);
  if (state === null) {
    throw new Error('useAuth was called outside AuthProvider.');
  }
  return state;
}
