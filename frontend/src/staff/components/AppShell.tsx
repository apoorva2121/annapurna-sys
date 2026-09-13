import { type ReactElement, useState } from 'react';
import { Link, Outlet } from 'react-router-dom';

import { Permission } from '@shared/permissions';
import { useAuth } from '@staff/auth/AuthContext';
import { BranchSwitcher } from '@staff/components/BranchSwitcher';
import { RestaurantTheme } from '@staff/components/RestaurantTheme';
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
      {/* Applies the restaurant-wide and festive themes once the session is known. Renders nothing. */}
      <RestaurantTheme />
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-border p-page">
        {/* The restaurant name is the tenant, on every screen. If tenant scoping ever broke, this
            is where it would be visible first. */}
        <Link to="/" className="font-semibold">
          {session?.restaurant.name ?? strings.appName}
        </Link>
        <nav className="flex flex-wrap items-center gap-x-4">
          <ServiceLinks />
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
          {/* M03 and M04. These shipped as routes with nothing linking to them, so every one was
              reachable only by typing a URL — which is to say not reachable. The header is where
              they belong rather than only the home page: a chef standing at the pass is already
              inside the app, and going back to a landing page to reach the next screen is not how
              anybody works a shift. */}
          {can(Permission.MENU_VIEW) && (
            <>
              <Link to="/menu">{strings.nav.menu}</Link>
              <Link to="/menu/options">{strings.nav.menuOptions}</Link>
            </>
          )}
          {can(Permission.RECIPE_VIEW) && <Link to="/stock">{strings.nav.stock}</Link>}
          {can(Permission.COST_VIEW) && <Link to="/costs">{strings.nav.costs}</Link>}
          {/* M06. Two links rather than one: a store manager arrives either to raise an order or
              to look up what a supplier owes them, and those are different errands. */}
          {can(Permission.SUPPLIER_VIEW) && (
            <>
              <Link to="/purchasing/orders">{strings.nav.purchaseOrders}</Link>
              <Link to="/purchasing/suppliers">{strings.nav.suppliers}</Link>
            </>
          )}
          <Link to="/profile">{strings.nav.profile}</Link>
        </nav>
        {/* Renders nothing for the great majority of staff, who work at one restaurant. */}
        <BranchSwitcher />
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

/**
 * M07. The links for running service, first in the header because for everyone who holds them they
 * are the screens of the shift.
 *
 * A component of its own so `AppShell` stays under eslint's complexity limit as service screens
 * arrive: each permission check is a branch, and the header already carries eight of them. Raising
 * the limit would have hidden the next nine.
 */
function ServiceLinks(): ReactElement {
  const { can } = useAuth();
  return (
    <>
      {can(Permission.ORDER_VIEW) && <Link to="/floor">{strings.orders.navTables}</Link>}
      {can(Permission.ORDER_VOID) && <Link to="/bills">{strings.bills.nav}</Link>}
      {can(Permission.CASH_MANAGE) && <Link to="/cash">{strings.cash.nav}</Link>}
    </>
  );
}
