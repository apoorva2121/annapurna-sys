import type { ReactElement } from 'react';
import { Link } from 'react-router-dom';

import { Permission } from '@shared/permissions';
import { useAuth } from '@staff/auth/AuthContext';
import { Notice } from '@staff/components/Notice';
import { strings } from '@staff/strings';

/**
 * Where everyone lands after signing in.
 *
 * Acceptance criterion 1 is satisfied here: the page names the restaurant, so the owner can see at
 * a glance which tenant they are in — which is also the first thing that would look wrong if
 * tenant scoping were broken.
 *
 * A waiter and a chef land here too. Their own screens are M07 and M08; until then this page tells
 * them they are signed in and shows them no staff navigation, which is the correct M01 behaviour
 * rather than a placeholder.
 */
export default function HomeScreen(): ReactElement {
  const { session, can } = useAuth();
  if (session === null || session === undefined) {
    return <></>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">{session.restaurant.name}</h1>
        <p className="text-muted-foreground">{strings.home.greeting(session.fullName)}</p>
      </div>

      {session.permissions.size === 0 ? (
        // Empty states explain what will appear and how (docs/ui/conventions.md). A waiter seeing
        // a blank page would reasonably conclude the app is broken.
        <Notice tone="info" title={strings.home.noPermissions} />
      ) : (
        <ul className="space-y-2">
          {can(Permission.EMPLOYEE_VIEW) && (
            <li>
              <Link className="text-info underline" to="/staff">
                {strings.nav.staff}
              </Link>
            </li>
          )}
          <li>
            <Link className="text-info underline" to="/profile">
              {strings.nav.profile}
            </Link>
          </li>
        </ul>
      )}

      <p className="text-sm text-muted-foreground">{strings.home.m01Note}</p>
    </div>
  );
}
