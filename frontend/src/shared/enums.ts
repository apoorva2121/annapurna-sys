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

/**
 * Live state of one table on the floor.
 *
 * `reserved` is set by hand by a manager taking a walk-in booking — there is no reservation system
 * behind it. `cleaning` clears in five minutes; `out_of_service` means a broken table nobody should
 * be offered.
 */
export const TableStatus = {
  FREE: 'free',
  OCCUPIED: 'occupied',
  RESERVED: 'reserved',
  CLEANING: 'cleaning',
  OUT_OF_SERVICE: 'out_of_service',
} as const;
export type TableStatus = (typeof TableStatus)[keyof typeof TableStatus];

/**
 * Where a stock item's `currentUnitCost` came from, and therefore how much to trust it.
 *
 * A restaurant that has recorded no purchases still sees a food cost on the day-1 screen — that is
 * the pitch — so the screen must not state a researched national average as confidently as a number
 * off the restaurant's own supplier bill. `market_rate` is the one the UI has to mark as estimated.
 *
 * The order is a confidence order: `purchase` beats `manual` beats `market_rate`.
 */
export const CostSource = {
  MARKET_RATE: 'market_rate',
  MANUAL: 'manual',
  PURCHASE: 'purchase',
} as const;
export type CostSource = (typeof CostSource)[keyof typeof CostSource];

/**
 * What caused a line in the stock ledger.
 *
 * The type is how a variance report tells shrinkage from service. `consumption` is a dish being
 * made, `wastage` is something thrown away, `adjustment` is a human correcting the book — and an
 * adjustment is never rendered invisibly, because a report that hid them would let someone erase a
 * shortfall by declaring it.
 */
export const MovementType = {
  RECEIPT: 'receipt',
  PRODUCTION: 'production',
  CONSUMPTION: 'consumption',
  WASTAGE: 'wastage',
  STAFF_MEAL: 'staff_meal',
  COMPLIMENTARY: 'complimentary',
  TRANSFER: 'transfer',
  ADJUSTMENT: 'adjustment',
  COUNT: 'count',
} as const;
export type MovementType = (typeof MovementType)[keyof typeof MovementType];

/**
 * How a movement's quantity was arrived at. Invariant 7 lives on this field.
 *
 * On-hand sums both — both genuinely move the book. What must never be summed across the two is a
 * single *consumption* figure, because the difference between recipe-derived and physically
 * observed consumption is the leakage number this product exists to surface.
 */
export const MovementBasis = {
  THEORETICAL: 'theoretical',
  ACTUAL: 'actual',
} as const;
export type MovementBasis = (typeof MovementBasis)[keyof typeof MovementBasis];

/**
 * How much of the storeroom a count covered, which decides what its variance means. A `full` count
 * reconciles everything, so anything unexplained is real; a `spot` count of four items says nothing
 * about the rest and must not be extrapolated from.
 */
export const StockCountScope = {
  FULL: 'full',
  PARTIAL: 'partial',
  SPOT: 'spot',
} as const;
export type StockCountScope = (typeof StockCountScope)[keyof typeof StockCountScope];

/**
 * Forward-only. Nothing reaches the ledger until `approved` — a submitted count is a worksheet, and
 * approval is what writes the adjustment movements. There is no `cancelled` and no delete, because
 * the count somebody wants to lose is exactly the count that matters.
 */
export const StockCountStatus = {
  DRAFT: 'draft',
  SUBMITTED: 'submitted',
  APPROVED: 'approved',
} as const;
export type StockCountStatus = (typeof StockCountStatus)[keyof typeof StockCountStatus];
