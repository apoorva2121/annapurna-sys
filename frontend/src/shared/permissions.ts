// The permission strings the staff app knows about, mirroring `app/core/permissions.json`.
//
// Deliberately NOT in enums.ts: that file is mirrored member-for-member against
// `app/core/enums.py` by `backend/tests/test_enum_mirror.py`, and permissions live in
// `app/core/permissions.py` instead. Adding them there would fail that test for being an enum the
// Python side does not have.
//
// These exist so a component writes `can(Permission.EMPLOYEE_VIEW)` rather than a loose string a
// typo can silently disable. They are *presentation only* — the server authorises every request
// regardless, and the UI merely avoids showing doors that will not open (M01 spec).

export const Permission = {
  EMPLOYEE_VIEW: 'employee.view',
  EMPLOYEE_CREATE: 'employee.create',
  EMPLOYEE_EDIT: 'employee.edit',
  EMPLOYEE_DEACTIVATE: 'employee.deactivate',
  EMPLOYEE_ROLE_ASSIGN: 'employee.role.assign',
  EMPLOYEE_PASSWORD_RESET: 'employee.password.reset',
  ROLE_VIEW: 'role.view',
  // M02. The whole setup surface sits behind this one: settings, floor, stations, tax.
  RESTAURANT_CONFIGURE: 'restaurant.configure',
  // M03. Three, because `seed/organization.yaml`'s P1 design draws a line a single permission
  // cannot: a manager may shape the menu and may not price it. The UI uses MENU_PRICE to decide
  // whether to render a price control at all — a disabled input that 403s reads as a bug in the
  // product rather than as a boundary in it.
  MENU_VIEW: 'menu.view',
  MENU_MANAGE: 'menu.manage',
  MENU_PRICE: 'menu.price',
  // M04. The separation is in both directions and it comes from the P1 design: a chef holds
  // RECIPE_MANAGE and not COST_VIEW ("a chef sees grams, not rupees"); a manager holds COST_VIEW
  // and not RECIPE_MANAGE. So the person who writes the recipe cannot see the margin, and the
  // person who sees the margin cannot change the recipe that produces it.
  RECIPE_VIEW: 'recipe.view',
  RECIPE_MANAGE: 'recipe.manage',
  COST_VIEW: 'cost.view',
  // M05. The one worth reading is the chef: STOCK_PRODUCE and not STOCK_RECEIVE. A kitchen turns
  // ingredients into gravy; it does not sign for the sack at the door, so a cook cannot book in
  // stock that never arrived.
  STOCK_VIEW: 'stock.view',
  STOCK_RECEIVE: 'stock.receive',
  STOCK_PRODUCE: 'stock.produce',
  STOCK_ADJUST: 'stock.adjust',
  STOCK_COUNT: 'stock.count',
  // M06. The line worth reading is the accountant: PURCHASE_MANAGE and not STOCK_RECEIVE. Raising
  // an order and signing for the delivery are different acts, and posting a receipt writes the
  // stock ledger — so it keeps the ledger's permission rather than gaining one of its own. The
  // screens follow that split: the receive button appears for STOCK_RECEIVE, and the order form
  // for PURCHASE_MANAGE.
  SUPPLIER_VIEW: 'supplier.view',
  SUPPLIER_MANAGE: 'supplier.manage',
  PURCHASE_MANAGE: 'purchase.manage',
  // M07. A waiter holds ORDER_SETTLE and not ORDER_VOID or ORDER_DISCOUNT, the P1 design's
  // classic leakage vectors, and the bill screen renders a void or discount control only for
  // the permission that makes it work. CASH_MANAGE is the M07 spec's amendment to that design:
  // a waiter takes cash and never closes the till it went into.
  ORDER_VIEW: 'order.view',
  ORDER_CREATE: 'order.create',
  ORDER_MODIFY: 'order.modify',
  ORDER_SETTLE: 'order.settle',
  ORDER_VOID: 'order.void',
  ORDER_DISCOUNT: 'order.discount',
  CASH_MANAGE: 'cash.manage',
  // Backlog-issues B2. Busy mode on the floor: settled tables skip cleaning. Owner and manager —
  // it changes every table, so the floor renders the switch only for this permission. Mark ready
  // needs none of its own: whoever holds ORDER_CREATE seats a table and clears it.
  FLOOR_MANAGE: 'floor.manage',
  // Waiter assignment (2026-09-14). Choosing who serves a table when opening it for someone else,
  // and moving an order between waiters. Owner and manager; a waiter claims only an unserved order.
  ORDER_ASSIGN: 'order.assign',
  // M08. The kitchen display. A waiter holds KOT_VIEW and not KOT_UPDATE, which is the P1 design's
  // own line — the floor watches the kitchen and does not drive it — so the rail renders its
  // buttons only for the second. Neither marks anything served: a dish is served when it reaches a
  // table, which the kitchen cannot see, so that stays on the order screen.
  KOT_VIEW: 'kot.view',
  KOT_UPDATE: 'kot.update',
} as const;

export type Permission = (typeof Permission)[keyof typeof Permission];
