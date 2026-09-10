// Mirror of the backend's `app/core/enums.py`. Enums live in exactly one place per side and are
// mirrored across the wire boundary (CLAUDE.md, Conventions), so a value added on the server is a
// visible one-line diff here rather than a string literal scattered through components.
//
// Kept honest by `backend/tests/test_enum_mirror.py`, which parses this file and fails the build if
// the two sides disagree on a single name or value. Edit both, or neither.
//
// Declared as `as const` objects rather than TypeScript `enum`, because a TS enum emits a runtime
// object with reverse mappings and does not narrow to the string literal union we actually want.

export const OrganizationPlan = {
  TRIAL: 'trial',
  ACTIVE: 'active',
  SUSPENDED: 'suspended',
  CANCELLED: 'cancelled',
} as const;
export type OrganizationPlan = (typeof OrganizationPlan)[keyof typeof OrganizationPlan];

/**
 * Authentication state. Distinct from `employee.isActive`, which is employment state — a person can
 * be employed with no login, and a login can be suspended while employment continues.
 */
export const UserAccountStatus = {
  INVITED: 'invited',
  ACTIVE: 'active',
  SUSPENDED: 'suspended',
  LOCKED: 'locked',
} as const;
export type UserAccountStatus = (typeof UserAccountStatus)[keyof typeof UserAccountStatus];

export const EmploymentType = {
  FULL_TIME: 'full_time',
  PART_TIME: 'part_time',
  CONTRACT: 'contract',
} as const;
export type EmploymentType = (typeof EmploymentType)[keyof typeof EmploymentType];

/**
 * The nine system roles fixed by docs/schema.md §1.
 *
 * Never branch on these to decide what a user may do — the server authorises by permission string
 * (ADR 0007), and the UI asks `can('employee.view')`. These exist for labels and for the
 * role-assignment screen.
 */
export const RoleCode = {
  OWNER: 'owner',
  ADMIN: 'admin',
  MANAGER: 'manager',
  CHEF: 'chef',
  KITCHEN_STAFF: 'kitchen_staff',
  WAITER: 'waiter',
  STORE_MANAGER: 'store_manager',
  CLEANER: 'cleaner',
  ACCOUNTANT: 'accountant',
} as const;
export type RoleCode = (typeof RoleCode)[keyof typeof RoleCode];
