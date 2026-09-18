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
/** The design gallery, linked only in a development build (backlog-issues B11b).
 *
 * Its own component rather than a conditional in the nav: the gallery is for developers and
 * reviewers, and the shell is already at the complexity the lint rule allows. */
function DesignGalleryLink(): ReactElement | null {
  if (!import.meta.env.DEV) {
    return null;
  }
  return <Link to="/design">{strings.nav.design}</Link>;
}

/**
 * The links every role in the catalogue holds, with no permission check on any of them.
 *
 * Its own component because the nav went over the complexity budget, and because the grouping is
 * the honest one: M11 and M12 granted `message.send`, `task.view` and `shift.view` to everybody —
 * the design being right rather than generous. The person who finds the broken freezer at 6am is
 * exactly the person with no other permissions, and the same person needs to clock in.
 */
function EveryonesLinks(): ReactElement {
  return (
    <>
      <Link to="/alerts">{strings.nav.notifications}</Link>
      {/* M17. Every role, always — ADR 0011 makes it a structural guarantee, so this link has no
          permission check on it and is not supposed to. */}
      <Link to="/my-performance">{strings.nav.myPerformance}</Link>
      <Link to="/shifts">{strings.nav.myShifts}</Link>
      <Link to="/messages">{strings.nav.messages}</Link>
      <Link to="/tasks">{strings.nav.tasks}</Link>
    </>
  );
}

/**
 * The three screens somebody opens to find something out rather than to do something.
 *
 * Its own component because `Nav` went over eslint's complexity limit when M17 added the workload
 * link — the third time the budget has forced this grouping and the third time the grouping has
 * been the honest one. These are the modules that read the day rather than run it, and each is
 * behind a different permission because the P1 design draws the lines differently: a manager reads
 * the operations, an accountant reads the trail, and workload is about the roster.
 */
function InsightLinks(): ReactElement {
  const { can } = useAuth();
  return (
    <>
      {/* M13. One link, because `Today` is the way into the other four — a header with five
          report links would push the ones somebody uses every shift off the row. */}
      {can(Permission.REPORT_OPERATIONAL_VIEW) && <Link to="/reports">{strings.nav.reports}</Link>}
      {/* M14. Withheld from the manager by the P1 design, so the link is absent rather than
          disabled — a greyed-out door is an invitation to find out what is behind it. */}
      {can(Permission.AUDIT_VIEW) && <Link to="/audit">{strings.nav.audit}</Link>}
      {/* M17. About the rota rather than about pay, which is why it sits with the reading
          screens and not with the settings. */}
      {can(Permission.PERFORMANCE_VIEW_TEAM) && <Link to="/workload">{strings.nav.workload}</Link>}
      {/* M18. Sits with the reading screens: it is a thing somebody checks, not a thing they
          configure. The link is absent rather than disabled for the floor, for the same
          reason as the audit trail. */}
      {can(Permission.COMPLIANCE_VIEW) && <Link to="/compliance">{strings.nav.compliance}</Link>}
    </>
  );
}

/**
 * Everything in the header that depends on a permission.
 *
 * Extracted because `AppShell` went over the complexity budget when M12 added its links — which
 * is the budget doing its job rather than an inconvenience: the shell's own work is the theme, the
 * tenant name and signing out, and the navigation is a list that grows with every module.
 *
 * The navigation is built from permissions, never from a role name (ADR 0007).
 */
function Nav(): ReactElement {
  const { can } = useAuth();
  return (
    <>
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
      <InsightLinks />
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
      <EveryonesLinks />
      {can(Permission.SHIFT_MANAGE) && <Link to="/shifts/roster">{strings.nav.roster}</Link>}
      <Link to="/profile">{strings.nav.profile}</Link>
    </>
  );
}

export function AppShell(): ReactElement {
  const { session, signOut } = useAuth();
  const [signingOut, setSigningOut] = useState(false);

  return (
    <div className="min-h-screen">
      {/* Applies the restaurant-wide and festive themes once the session is known. Renders nothing. */}
      <RestaurantTheme />
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-border p-page print:hidden">
        {/* The restaurant name is the tenant, on every screen. If tenant scoping ever broke, this
            is where it would be visible first. */}
        <Link to="/" className="font-semibold">
          {session?.restaurant.name ?? strings.appName}
        </Link>
        <nav className="flex flex-wrap items-center gap-x-4">
          <Nav />
          <DesignGalleryLink />
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
