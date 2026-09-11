import { type ReactElement, useState } from 'react';
import { Link, Outlet } from 'react-router-dom';

import { Permission } from '@shared/permissions';
import { useAuth } from '@staff/auth/AuthContext';
import { strings } from '@staff/strings';

/**
 * The frame every signed-in screen renders inside.
 *
 * The navigation is built from permissions, never from a role name (ADR 0007). A waiter therefore
 * sees no Staff link — not because the code checks for "waiter", but because they do not hold
 * `employee.view` (manual test C2). The server refuses the route regardless; this only avoids
 * showing a door that will not open.
 */
export function AppShell(): ReactElement {
  const { session, signOut, can } = useAuth();
  const [signingOut, setSigningOut] = useState(false);

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-border p-page">
        {/* The restaurant name is the tenant, on every screen. If tenant scoping ever broke, this
            is where it would be visible first. */}
        <Link to="/" className="font-semibold">
          {session?.restaurant.name ?? strings.appName}
        </Link>
        <nav className="flex flex-wrap items-center gap-x-4">
          {can(Permission.EMPLOYEE_VIEW) && <Link to="/staff">{strings.nav.staff}</Link>}
          {/* Four links rather than one, because they are four different jobs done at four
              different times — the floor changes when tables move, tax when a rate changes, and a
              manager should be able to reach the one they came for without reading a submenu. */}
          {can(Permission.RESTAURANT_CONFIGURE) && (
            <>
              <Link to="/settings">{strings.setup.navSettings}</Link>
              <Link to="/settings/floor">{strings.setup.navFloor}</Link>
              <Link to="/settings/stations">{strings.setup.navStations}</Link>
              <Link to="/settings/tax">{strings.setup.navTax}</Link>
            </>
          )}
          <Link to="/profile">{strings.nav.profile}</Link>
        </nav>
        <button
          type="button"
          className="ml-auto min-h-target underline disabled:opacity-60"
          disabled={signingOut}
          onClick={() => {
            setSigningOut(true);
            void signOut().finally(() => {
              setSigningOut(false);
            });
          }}
        >
          {signingOut ? strings.nav.signingOut : strings.nav.signOut}
        </button>
      </header>

      <main className="mx-auto max-w-3xl p-page">
        <Outlet />
      </main>
    </div>
  );
}
