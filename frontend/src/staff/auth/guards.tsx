import type { ReactElement, ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { Notice } from '@staff/components/Notice';
import { strings } from '@staff/strings';

import { useAuth } from './AuthContext';

/**
 * Everything behind a login.
 *
 * Renders nothing at all while the cold-load restore is in flight. That blank moment is
 * deliberate: redirecting to /login before we know would bounce every signed-in user to the login
 * screen on every page refresh, and showing the app before we know would flash data at someone who
 * turns out to be signed out.
 */
export function RequireAuth({ children }: { children: ReactNode }): ReactElement | null {
  const { session } = useAuth();
  const location = useLocation();

  if (session === undefined) {
    return null;
  }
  if (session === null) {
    // `replace` so the browser Back button cannot return to a page that is no longer authorised —
    // manual test A9.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

/**
 * Hide a screen the actor cannot use. **Presentation only.**
 *
 * The server denies the request regardless (`require_permission`), so this is not a security
 * control — it exists so the UI does not show doors that do not open. It renders a clear refusal
 * rather than a blank page or a redirect, because a waiter who types the staff URL should be told
 * no, not silently bounced (manual test C3).
 */
export function RequirePermission({
  permission,
  children,
}: {
  permission: string;
  children: ReactNode;
}): ReactElement {
  const { can } = useAuth();

  if (!can(permission)) {
    return (
      <Notice tone="critical" title={strings.errors.forbidden}>
        {strings.errors.forbiddenHint}
      </Notice>
    );
  }
  return <>{children}</>;
}
