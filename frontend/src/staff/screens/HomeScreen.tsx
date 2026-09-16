import type { ReactElement } from 'react';
import { Link } from 'react-router-dom';

import { Permission } from '@shared/permissions';
import { useAuth } from '@staff/auth/AuthContext';
import { LicenceNotice } from '@staff/components/LicenceNotice';
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
/**
 * Everywhere this app can go, and what a person must hold to be offered it.
 *
 * **In one list, in route order.** M03 and M04 each shipped screens with a route and no link of
 * any kind, reachable only by typing a URL — which is to say not reachable. `AppShell`'s header is
 * the primary fix, because it is on every screen; this list is the landing page saying the same
 * thing to somebody who has just signed in. A missing entry here is a visible omission.
 *
 * `null` means everyone: a waiter with no permissions still has a profile.
 */
const links: { to: string; label: string; permission: Permission | null }[] = [
  { to: '/staff', label: strings.nav.staff, permission: Permission.EMPLOYEE_VIEW },
  { to: '/settings', label: strings.nav.settings, permission: Permission.RESTAURANT_CONFIGURE },
  { to: '/menu', label: strings.nav.menu, permission: Permission.MENU_VIEW },
  { to: '/menu/options', label: strings.nav.menuOptions, permission: Permission.MENU_VIEW },
  { to: '/stock', label: strings.nav.stock, permission: Permission.RECIPE_VIEW },
  { to: '/costs', label: strings.nav.costs, permission: Permission.COST_VIEW },
  { to: '/stock/on-hand', label: strings.nav.onHand, permission: Permission.STOCK_VIEW },
  { to: '/stock/receive', label: strings.nav.receive, permission: Permission.STOCK_RECEIVE },
  { to: '/stock/produce', label: strings.nav.produce, permission: Permission.STOCK_PRODUCE },
  { to: '/stock/count', label: strings.nav.count, permission: Permission.STOCK_COUNT },
  // M08. The rail was reachable only from its own ticket detail, which links back to it — a
  // circular pair the reachability test cannot see through, so the kitchen display had no entry
  // point from anywhere a person starts. Found while wiring M09's links.
  { to: '/kitchen', label: strings.nav.kitchen, permission: Permission.KOT_VIEW },
  // M09. Logging is a kitchen and storeroom act; the summary is behind `stock.view`, because
  // seeing what was thrown away is not the same power as throwing it away.
  { to: '/waste', label: strings.nav.logWaste, permission: Permission.WASTAGE_LOG },
  { to: '/waste/summary', label: strings.nav.wasteSummary, permission: Permission.STOCK_VIEW },
  // M10. A waiter sees the first two: the regular's card belongs on their screen, and a rating is
  // about a table they served. Complaints are a manager's, because owning one is accountable.
  //
  // `reachability.test.ts` refused the build until these were here — the same test that found M09's
  // waste screen reachable only from its own detail page.
  { to: '/customers', label: strings.nav.customers, permission: Permission.CUSTOMER_VIEW },
  { to: '/feedback', label: strings.nav.feedback, permission: Permission.FEEDBACK_VIEW },
  { to: '/complaints', label: strings.nav.complaints, permission: Permission.COMPLAINT_MANAGE },
  { to: '/profile', label: strings.nav.profile, permission: null },
];

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
      <LicenceNotice />

      {session.permissions.size === 0 ? (
        // Empty states explain what will appear and how (docs/ui/conventions.md). A waiter seeing
        // a blank page would reasonably conclude the app is broken.
        <Notice tone="info" title={strings.home.noPermissions} />
      ) : (
        <ul className="space-y-2">
          {links
            .filter((link) => link.permission === null || can(link.permission))
            .map((link) => (
              <li key={link.to}>
                <Link className="text-info underline" to={link.to}>
                  {link.label}
                </Link>
              </li>
            ))}
        </ul>
      )}

      <p className="text-sm text-muted-foreground">{strings.home.m01Note}</p>
    </div>
  );
}
