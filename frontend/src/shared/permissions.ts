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
} as const;

export type Permission = (typeof Permission)[keyof typeof Permission];
