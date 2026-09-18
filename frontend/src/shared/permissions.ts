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
  // M09. A waiter holds neither: waste is a kitchen and storeroom event. The people who log most
  // of it — the chef and the kitchen staff — hold LOG and not APPROVE, which is the separation of
  // duties standing between an expensive reason code and somebody logging theft as waste.
  WASTAGE_LOG: 'wastage.log',
  // M10. A waiter holds `customer.view` and `feedback.view` — the P1 design being right rather than
  // generous: the regular's card belongs on the waiter's screen, and a rating is about a table they
  // served. Editing somebody's details and owning a complaint are a manager's.
  CUSTOMER_VIEW: 'customer.view',
  CUSTOMER_MANAGE: 'customer.manage',
  FEEDBACK_VIEW: 'feedback.view',
  COMPLAINT_MANAGE: 'complaint.manage',
  WASTAGE_APPROVE: 'wastage.approve',
  // M11. Every role holds the first three, cleaner included — the P1 design's own grant, and the
  // reason is that the person who finds the broken freezer at 6am is exactly the person with no
  // other permissions. MESSAGE_SEND does not open every thread: you read one because you are a
  // participant in it, which is the control a permission cannot express. TASK_VIEW is enough to
  // write down your own work; giving work to somebody else is TASK_ASSIGN, so the screens render
  // an assignee picker only for that one.
  MESSAGE_SEND: 'message.send',
  TASK_VIEW: 'task.view',
  TASK_COMPLETE: 'task.complete',
  TASK_ASSIGN: 'task.assign',
  // M12. Every role holds SHIFT_VIEW — one deliberate widening of the P1 grant, because a roster
  // nobody can read is a noticeboard in a locked room. The permission opens the screen; the scope
  // decides the content. There is no `shift.clock`: clocking in declares SHIFT_VIEW and the server
  // enforces that the row is yours.
  SHIFT_VIEW: 'shift.view',
  SHIFT_MANAGE: 'shift.manage',
  // M13. The manager holds the operational reports and **not** the financial ones —
  // the P1 design's line, and the reason the money screens are absent from a
  // manager's navigation rather than present and empty.
  REPORT_OPERATIONAL_VIEW: 'report.operational.view',
  REPORT_FINANCIAL_VIEW: 'report.financial.view',
  // M14. The owner's, the administrator's and the accountant's — and not the manager's.
  // The person who runs the floor is frequently the subject of the record, and a record
  // its subject curates is not a record. The notification centre has no permission at all:
  // what it shows is decided per condition by what each person can act on.
  AUDIT_VIEW: 'audit.view',
  // M17. `performance.view.own` is listed so the role screen can explain what it means —
  // and **nothing in this application checks it**, because ADR 0011 makes it a structural
  // guarantee rather than a setting: it is held by every role and is not removable. A guard
  // on it would imply it could be absent, which is the opposite of the decision.
  PERFORMANCE_VIEW_OWN: 'performance.view.own',
  PERFORMANCE_VIEW_TEAM: 'performance.view.team',
  PERFORMANCE_PUBLISH: 'performance.publish',
  INCENTIVE_CONFIGURE: 'incentive.configure',
  RECOGNITION_AWARD: 'recognition.award',
  // M18. Seeing and deciding are split. A manager holds the first — the floor is where an
  // expired licence is found by an inspector, and withholding the list from the person most
  // able to act on it would be the wrong kind of caution. Only the owner and the
  // administrator hold the second: a suppression is the row an inspection reads.
  COMPLIANCE_VIEW: 'compliance.view',
  COMPLIANCE_ACT: 'compliance.act',
} as const;

export type Permission = (typeof Permission)[keyof typeof Permission];
