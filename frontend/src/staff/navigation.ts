import { Permission } from '@shared/permissions';
import { strings } from '@staff/strings';

/**
 * Every screen this app can reach, once, with what a person must hold to be offered it.
 *
 * **One list, because there used to be two and they disagreed.** The header and the home page each
 * kept their own hand-written set. Eight screens appeared in both — the owner's report on
 * 2026-09-19: *"the options that are present at the top they should not be repeated below … that
 * is redundant"* — while ten more appeared on the home page and nowhere else. Neither list was
 * complete, and four separate comments across the two files record somebody noticing a gap and
 * patching one side of it. Two lists that must not overlap will overlap again within two modules
 * if they are kept by hand.
 *
 * **`where` is the partition.** A screen is in the header or on the home page, never both.
 * `navigationDiscipline.test.ts` refuses a duplicate and refuses a route that appears in neither.
 *
 * **Groups are the honest ones.** `AppShell` had already split its nav three times, and its own
 * comments say each split happened because eslint's complexity budget forced it —
 * *"the third time the budget has forced this grouping"*. The grouping existed in the code and was
 * never shown on the screen. It is shown now, and it is what makes a drawer readable rather than a
 * list of twenty-five.
 *
 * **Built from permissions, never from a role name** (ADR 0007). `permission: null` means everyone:
 * a waiter with nothing else still has a profile, and M11 and M12 granted messages, tasks and
 * shifts to every role deliberately — the person who finds the broken freezer at 6am is exactly
 * the person with no other permissions.
 */
export type NavEntry = {
  to: string;
  label: string;
  permission: Permission | null;
};

export type NavGroup = {
  /** Shown as a heading in the drawer and as a separator on a wide screen. */
  heading: string;
  entries: NavEntry[];
};

/**
 * The screens of a shift, and the only ones that stay visible on a phone.
 *
 * `AppShell` used to call this `ServiceLinks` and described it as "the screens of the shift, first
 * in the header because for everyone who holds them they are the screens of the shift". That is
 * the reason they survive the drawer: its own comment argues that *"a chef standing at the pass is
 * already inside the app, and going back to a landing page to reach the next screen is not how
 * anybody works a shift"* — and a hamburger is a landing page with fewer steps.
 *
 * Which of them a person sees is still a permission question, so a cleaner sees none of these and
 * gets only the drawer button.
 */
export const SERVICE: NavGroup = {
  heading: strings.nav.groups.service,
  entries: [
    { to: '/floor', label: strings.orders.navTables, permission: Permission.ORDER_VIEW },
    { to: '/bills', label: strings.bills.nav, permission: Permission.ORDER_VOID },
    { to: '/cash', label: strings.cash.nav, permission: Permission.CASH_MANAGE },
  ],
};

/** Everything else in the header, grouped. */
export const HEADER_GROUPS: NavGroup[] = [
  SERVICE,
  {
    heading: strings.nav.groups.menu,
    entries: [
      { to: '/menu', label: strings.nav.menu, permission: Permission.MENU_VIEW },
      { to: '/menu/options', label: strings.nav.menuOptions, permission: Permission.MENU_VIEW },
      { to: '/menu/codes', label: strings.nav.menuCodes, permission: Permission.MENU_MANAGE },
      { to: '/stock', label: strings.nav.stock, permission: Permission.RECIPE_VIEW },
      { to: '/costs', label: strings.nav.costs, permission: Permission.COST_VIEW },
    ],
  },
  {
    heading: strings.nav.groups.buying,
    entries: [
      {
        to: '/purchasing/orders',
        label: strings.nav.purchaseOrders,
        permission: Permission.SUPPLIER_VIEW,
      },
      {
        to: '/purchasing/suppliers',
        label: strings.nav.suppliers,
        permission: Permission.SUPPLIER_VIEW,
      },
    ],
  },
  {
    heading: strings.nav.groups.insight,
    entries: [
      {
        to: '/reports',
        label: strings.nav.reports,
        permission: Permission.REPORT_OPERATIONAL_VIEW,
      },
      // M19. Behind the financial permission, like M13's money screens: the owner and the
      // accountant hold it and the manager does not, so this is a screen a manager is not offered
      // rather than one that opens onto blanks.
      {
        to: '/analytics',
        label: strings.nav.analytics,
        permission: Permission.REPORT_FINANCIAL_VIEW,
      },
      { to: '/audit', label: strings.nav.audit, permission: Permission.AUDIT_VIEW },
      {
        to: '/workload',
        label: strings.nav.workload,
        permission: Permission.PERFORMANCE_VIEW_TEAM,
      },
      { to: '/compliance', label: strings.nav.compliance, permission: Permission.COMPLIANCE_VIEW },
    ],
  },
  {
    heading: strings.nav.groups.people,
    entries: [
      { to: '/staff', label: strings.nav.staff, permission: Permission.EMPLOYEE_VIEW },
      { to: '/shifts/roster', label: strings.nav.roster, permission: Permission.SHIFT_MANAGE },
    ],
  },
  {
    heading: strings.nav.groups.setup,
    entries: [
      {
        to: '/settings',
        label: strings.setup.navSettings,
        permission: Permission.RESTAURANT_CONFIGURE,
      },
      {
        to: '/settings/floor',
        label: strings.setup.navFloor,
        permission: Permission.RESTAURANT_CONFIGURE,
      },
      {
        to: '/settings/stations',
        label: strings.setup.navStations,
        permission: Permission.RESTAURANT_CONFIGURE,
      },
      {
        to: '/settings/tax',
        label: strings.setup.navTax,
        permission: Permission.RESTAURANT_CONFIGURE,
      },
      // M12's missing screen, added 2026-09-19. Behind `shift.manage` rather than
      // `restaurant.configure`, because rostering and configuring are different jobs and the
      // person who runs the rota is not always the person who sets up the restaurant.
      { to: '/settings/shifts', label: strings.nav.shiftSetup, permission: Permission.SHIFT_MANAGE },
    ],
  },
  {
    heading: strings.nav.groups.yours,
    entries: [
      { to: '/alerts', label: strings.nav.notifications, permission: null },
      // M17. Every role, always — ADR 0011 makes it a structural guarantee, so this carries no
      // permission check and is not supposed to.
      { to: '/my-performance', label: strings.nav.myPerformance, permission: null },
      { to: '/shifts', label: strings.nav.myShifts, permission: null },
      { to: '/messages', label: strings.nav.messages, permission: null },
      { to: '/tasks', label: strings.nav.tasks, permission: null },
      { to: '/profile', label: strings.nav.profile, permission: null },
    ],
  },
];

/**
 * The screens the home page lists, and the header does not.
 *
 * These are the ten that were **only** ever on the home page. The owner looked at the split on
 * 2026-09-19 and chose to keep it — they can reach these screens and did not want the header
 * carrying them — so this is a deliberate partition rather than a backlog of things to promote.
 *
 * What changed is the other direction: the eight screens that were on the home page **and** in the
 * header are now in the header only. The header is on every screen; the home page is somewhere
 * you land once.
 */
export const HOME_GROUPS: NavGroup[] = [
  {
    heading: strings.nav.groups.kitchen,
    entries: [
      { to: '/kitchen', label: strings.nav.kitchen, permission: Permission.KOT_VIEW },
      { to: '/waste', label: strings.nav.logWaste, permission: Permission.WASTAGE_LOG },
      { to: '/waste/summary', label: strings.nav.wasteSummary, permission: Permission.STOCK_VIEW },
    ],
  },
  {
    heading: strings.nav.groups.store,
    entries: [
      { to: '/stock/on-hand', label: strings.nav.onHand, permission: Permission.STOCK_VIEW },
      { to: '/stock/receive', label: strings.nav.receive, permission: Permission.STOCK_RECEIVE },
      { to: '/stock/produce', label: strings.nav.produce, permission: Permission.STOCK_PRODUCE },
      { to: '/stock/count', label: strings.nav.count, permission: Permission.STOCK_COUNT },
    ],
  },
  {
    heading: strings.nav.groups.diners,
    entries: [
      { to: '/customers', label: strings.nav.customers, permission: Permission.CUSTOMER_VIEW },
      { to: '/feedback', label: strings.nav.feedback, permission: Permission.FEEDBACK_VIEW },
      {
        to: '/complaints',
        label: strings.nav.complaints,
        permission: Permission.COMPLAINT_MANAGE,
      },
    ],
  },
];

/** Keeps a group out of the drawer entirely when the person holds none of it. */
export function visibleGroups(
  groups: NavGroup[],
  can: (permission: string) => boolean,
): NavGroup[] {
  return groups
    .map((group) => ({
      heading: group.heading,
      entries: group.entries.filter(
        (entry) => entry.permission === null || can(entry.permission),
      ),
    }))
    .filter((group) => group.entries.length > 0);
}
