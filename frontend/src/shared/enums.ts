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

/** The veg / non-veg / egg declaration (compliance-rules §A1). Statutory; no default anywhere. */
export const FoodType = {
  VEG: 'veg',
  NON_VEG: 'non_veg',
  EGG: 'egg',
} as const;
export type FoodType = (typeof FoodType)[keyof typeof FoodType];

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

/**
 * Where a purchase order is in its life. Forward-only, with two terminal states.
 *
 * ```
 * draft ──send──▶ sent ──receive──▶ partial ──receive──▶ received
 *   │               │                  │
 *   └───cancel──────┴──────cancel──────┘
 * ```
 *
 * `partial` is the value that earns the enum: a supplier delivering 30 of 50 sacks is the ordinary
 * case, and an order going straight from `sent` to `received` would lose the 20 still owed — which
 * is the number a store manager chases. `cancelled` and `received` are terminal, and a cancelled
 * order always carries a reason. A purchase order is never deleted.
 */
export const PurchaseOrderStatus = {
  DRAFT: 'draft',
  SENT: 'sent',
  PARTIAL: 'partial',
  RECEIVED: 'received',
  CANCELLED: 'cancelled',
} as const;
export type PurchaseOrderStatus = (typeof PurchaseOrderStatus)[keyof typeof PurchaseOrderStatus];

export const OrderType = {
  DINE_IN: 'dine_in',
  TAKEAWAY: 'takeaway',
  DELIVERY: 'delivery',
} as const;
export type OrderType = (typeof OrderType)[keyof typeof OrderType];

/** Where an order came from. `aggregator` is recorded, not integrated. */
export const OrderChannel = {
  POS: 'pos',
  QR: 'qr',
  AGGREGATOR: 'aggregator',
} as const;
export type OrderChannel = (typeof OrderChannel)[keyof typeof OrderChannel];

/**
 * An order's life. `settled`, `cancelled` and `voided` are final. A cancelled order never
 * settled, so it never consumed an invoice number; a voided one had its invoice cancelled on its day
 * of issue.
 */
export const OrderStatus = {
  OPEN: 'open',
  SENT: 'sent',
  SERVED: 'served',
  SETTLED: 'settled',
  CANCELLED: 'cancelled',
  VOIDED: 'voided',
} as const;
export type OrderStatus = (typeof OrderStatus)[keyof typeof OrderStatus];

/** `preparing` and `ready` belong to M08's kitchen display; `sent` is M07's own. */
export const OrderLineStatus = {
  PENDING: 'pending',
  SENT: 'sent',
  PREPARING: 'preparing',
  READY: 'ready',
  SERVED: 'served',
  CANCELLED: 'cancelled',
  RETURNED: 'returned',
} as const;
export type OrderLineStatus = (typeof OrderLineStatus)[keyof typeof OrderLineStatus];

/**
 * Where in the restaurant the money leaked (M09). Four stages, never lumped: each has a different
 * owner, a different fix and a different size, and lumping them produces a number nobody can act
 * on. Prep is the biggest and the least measured, and the only one with a same-day fix.
 *
 * Staff meals and comps are deliberately absent — they are separate movement types and are not
 * waste. Counted as waste they look like theft and poison every variance number.
 */
export const WastageStage = {
  RECEIVING: 'receiving',
  STORAGE: 'storage',
  PREP: 'prep',
  SERVICE: 'service',
} as const;
export type WastageStage = (typeof WastageStage)[keyof typeof WastageStage];

/**
 * One round of dishes at one station (M08). The path is one-way — `new → acknowledged → preparing
 * → ready` — and `served` is not the kitchen's to set: a dish is served when it reaches a table,
 * which the kitchen cannot see. The KDS renders it and never sends it.
 */
export const KotTicketStatus = {
  NEW: 'new',
  ACKNOWLEDGED: 'acknowledged',
  PREPARING: 'preparing',
  READY: 'ready',
  SERVED: 'served',
  CANCELLED: 'cancelled',
} as const;
export type KotTicketStatus = (typeof KotTicketStatus)[keyof typeof KotTicketStatus];

/** One dish on a ticket. `remake` is terminal — the remade dish arrives as its own new ticket. */
export const KotLineStatus = {
  PENDING: 'pending',
  PREPARING: 'preparing',
  READY: 'ready',
  SERVED: 'served',
  CANCELLED: 'cancelled',
  REMAKE: 'remake',
} as const;
export type KotLineStatus = (typeof KotLineStatus)[keyof typeof KotLineStatus];

export const DiscountType = {
  PERCENTAGE: 'percentage',
  FLAT: 'flat',
  COMP: 'comp',
} as const;
export type DiscountType = (typeof DiscountType)[keyof typeof DiscountType];

/** A service charge is only ever optional (CCPA guidelines, upheld 28 Mar 2025). */
export const ChargeType = {
  PACKAGING: 'packaging',
  SERVICE_CHARGE: 'service_charge',
  DELIVERY: 'delivery',
} as const;
export type ChargeType = (typeof ChargeType)[keyof typeof ChargeType];

export const PaymentMethod = {
  CASH: 'cash',
  CARD: 'card',
  UPI: 'upi',
  WALLET: 'wallet',
  ONLINE: 'online',
  DUE: 'due',
} as const;
export type PaymentMethod = (typeof PaymentMethod)[keyof typeof PaymentMethod];

/** No `refunded`: a refund is a new negative payment, never a status on the original. */
export const PaymentStatus = {
  SUCCESS: 'success',
  FAILED: 'failed',
} as const;
export type PaymentStatus = (typeof PaymentStatus)[keyof typeof PaymentStatus];

/**
 * Which GST scheme a restaurant is under; it decides the document. `regular` collects CGST +
 * SGST on a tax invoice; `composition` may not collect tax and issues a bill of supply. Both are
 * called "5%", which is the trap.
 */
export const GstScheme = {
  REGULAR: 'regular',
  COMPOSITION: 'composition',
  UNREGISTERED: 'unregistered',
} as const;
export type GstScheme = (typeof GstScheme)[keyof typeof GstScheme];

/** `non_gst` is liquor: outside GST, taxed by the state, never split into CGST and SGST. */
export const TaxRegime = {
  GST: 'gst',
  NON_GST: 'non_gst',
} as const;
export type TaxRegime = (typeof TaxRegime)[keyof typeof TaxRegime];

export const DocumentType = {
  TAX_INVOICE: 'tax_invoice',
  BILL_OF_SUPPLY: 'bill_of_supply',
} as const;
export type DocumentType = (typeof DocumentType)[keyof typeof DocumentType];

/** A cancelled invoice keeps its number. */
export const InvoiceStatus = {
  ISSUED: 'issued',
  CANCELLED: 'cancelled',
} as const;
export type InvoiceStatus = (typeof InvoiceStatus)[keyof typeof InvoiceStatus];

export const IdempotencyState = {
  IN_PROGRESS: 'in_progress',
  COMPLETED: 'completed',
  FAILED: 'failed',
} as const;
export type IdempotencyState = (typeof IdempotencyState)[keyof typeof IdempotencyState];

export const CashSessionStatus = {
  OPEN: 'open',
  CLOSED: 'closed',
} as const;
export type CashSessionStatus = (typeof CashSessionStatus)[keyof typeof CashSessionStatus];

/** Cash out of the till that is not a refund: a payout, or a post-close correction. */
export const CashMovementType = {
  PAYOUT: 'payout',
  ADJUSTMENT: 'adjustment',
} as const;
export type CashMovementType = (typeof CashMovementType)[keyof typeof CashMovementType];

/** What a customer always wants. `ALLERGY` is the kind the kitchen is told about. */
export const PreferenceType = {
  DIETARY: 'dietary',
  ALLERGY: 'allergy',
  SPICE_LEVEL: 'spice_level',
  SEATING: 'seating',
  OTHER: 'other',
} as const;
export type PreferenceType = (typeof PreferenceType)[keyof typeof PreferenceType];

/**
 * One purpose per consent row. Granting one grants nothing else, and withdrawing one withdraws
 * nothing else — a phone number collected for a bill is not marketing consent.
 */
export const ConsentPurpose = {
  ORDER_CONTACT: 'order_contact',
  SERVICE_RECOGNITION: 'service_recognition',
  FEEDBACK_FOLLOWUP: 'feedback_followup',
  MARKETING: 'marketing',
} as const;
export type ConsentPurpose = (typeof ConsentPurpose)[keyof typeof ConsentPurpose];

/** How a piece of customer input reached us. Shared by feedback and consent. */
export const ContactSource = {
  QR: 'qr',
  APP: 'app',
  STAFF: 'staff',
  CALL: 'call',
} as const;
export type ContactSource = (typeof ContactSource)[keyof typeof ContactSource];

export const ComplaintCategory = {
  FOOD_QUALITY: 'food_quality',
  SERVICE: 'service',
  DELAY: 'delay',
  BILLING: 'billing',
  HYGIENE: 'hygiene',
  STAFF_CONDUCT: 'staff_conduct',
  OTHER: 'other',
} as const;
export type ComplaintCategory = (typeof ComplaintCategory)[keyof typeof ComplaintCategory];

export const ComplaintSeverity = {
  LOW: 'low',
  MEDIUM: 'medium',
  HIGH: 'high',
  CRITICAL: 'critical',
} as const;
export type ComplaintSeverity = (typeof ComplaintSeverity)[keyof typeof ComplaintSeverity];

/** `RESOLVED` means somebody wrote down what was done; `CLOSED` means it is finished with. */
export const ComplaintStatus = {
  OPEN: 'open',
  INVESTIGATING: 'investigating',
  RESOLVED: 'resolved',
  CLOSED: 'closed',
} as const;
export type ComplaintStatus = (typeof ComplaintStatus)[keyof typeof ComplaintStatus];

/** What a thread is for. Nothing in M11 creates an `ANNOUNCEMENT`. */
export const ConversationType = {
  DIRECT: 'direct',
  GROUP: 'group',
  TASK: 'task',
  COMPLAINT: 'complaint',
  ANNOUNCEMENT: 'announcement',
} as const;
export type ConversationType = (typeof ConversationType)[keyof typeof ConversationType];

/** Sorting and colour, and deliberately nothing else in M11 — notifications are M14. */
export const MessagePriority = {
  NORMAL: 'normal',
  HIGH: 'high',
  URGENT: 'urgent',
} as const;
export type MessagePriority = (typeof MessagePriority)[keyof typeof MessagePriority];

export const TaskPriority = {
  LOW: 'low',
  NORMAL: 'normal',
  HIGH: 'high',
  URGENT: 'urgent',
} as const;
export type TaskPriority = (typeof TaskPriority)[keyof typeof TaskPriority];

/** `VERIFIED` is separate from `COMPLETED`: somebody did the work, somebody else agrees. */
export const TaskStatus = {
  CREATED: 'created',
  ASSIGNED: 'assigned',
  ACCEPTED: 'accepted',
  IN_PROGRESS: 'in_progress',
  COMPLETED: 'completed',
  VERIFIED: 'verified',
  CANCELLED: 'cancelled',
} as const;
export type TaskStatus = (typeof TaskStatus)[keyof typeof TaskStatus];

/** One `attachment` table, six owners. M11 gives three of them a screen. */
export const AttachmentOwnerType = {
  MESSAGE: 'message',
  TASK: 'task',
  COMPLAINT: 'complaint',
  WASTAGE_EVENT: 'wastage_event',
  FEEDBACK: 'feedback',
  GOODS_RECEIPT: 'goods_receipt',
} as const;
export type AttachmentOwnerType = (typeof AttachmentOwnerType)[keyof typeof AttachmentOwnerType];

/** `READY` means the store was asked how big the object is and its first bytes matched. */
export const AttachmentStatus = {
  PENDING: 'pending',
  READY: 'ready',
} as const;
export type AttachmentStatus = (typeof AttachmentStatus)[keyof typeof AttachmentStatus];

/** `PRESENT`/`LATE` are derived at clock-in; `ABSENT`/`LEAVE` are set by a person. */
export const ShiftAssignmentStatus = {
  SCHEDULED: 'scheduled',
  PRESENT: 'present',
  ABSENT: 'absent',
  LATE: 'late',
  LEAVE: 'leave',
} as const;
export type ShiftAssignmentStatus =
  (typeof ShiftAssignmentStatus)[keyof typeof ShiftAssignmentStatus];
