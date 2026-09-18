"""Every enum in the domain lives here and is mirrored in frontend/src/shared/enums.ts.

One definition, two languages, kept in step by a test that compares the two files. Values are the
strings stored in the database, so renaming one is a migration, not a refactor (ADR 0008: text
columns with a CHECK constraint, never a Postgres native enum).
"""

from __future__ import annotations

from enum import StrEnum


class OrganizationPlan(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class FoodType(StrEnum):
    """The veg / non-veg / egg declaration (`docs/compliance-rules.md` §A1). The one enum here with
    a statutory basis. No default anywhere: a dish whose type nobody chose must not publish."""

    VEG = "veg"
    NON_VEG = "non_veg"
    EGG = "egg"


class UserAccountStatus(StrEnum):
    """Authentication state. Distinct from employee.is_active, which is employment state — a
    person can be employed with no login, and a login can be suspended while employment continues.
    """

    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    LOCKED = "locked"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"


class RoleCode(StrEnum):
    """The nine system roles fixed by docs/schema.md §1.

    These are template roles seeded with organization_id IS NULL. Code never branches on them —
    authorisation is always require_permission("resource.action") (ADR 0007). They exist so the
    catalogue in permissions.json has stable keys and the seeding migration has stable targets.
    """

    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    CHEF = "chef"
    KITCHEN_STAFF = "kitchen_staff"
    WAITER = "waiter"
    STORE_MANAGER = "store_manager"
    CLEANER = "cleaner"
    ACCOUNTANT = "accountant"


class TableStatus(StrEnum):
    """Live state of one table on the floor.

    `reserved` is set by hand by a manager taking a walk-in booking (M02 spec decision 3). There is
    no reservation system behind it and it does not pretend to be one — the alternative was dropping
    the value, and a manager blocking a table for 8pm is how small restaurants actually work.

    `cleaning` and `out_of_service` are distinct on purpose: one clears in five minutes, the other
    means a broken table that should not be offered until someone fixes it.
    """

    FREE = "free"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    CLEANING = "cleaning"
    OUT_OF_SERVICE = "out_of_service"


class CostSource(StrEnum):
    """Where a stock item's `current_unit_cost` came from, and therefore how much to trust it.

    This exists because `docs/onboarding-cold-start.md` promises bootstrapped prices will be
    "visibly marked estimated", and nothing on `stock_item` could express that. A restaurant that
    has not yet recorded a single purchase still sees a food cost on the day-1 screen — that is the
    whole commercial pitch — and the screen must not state a researched national average with the
    same confidence as a number off the restaurant's own supplier bill.

    The ordering is a confidence ordering: `purchase` beats `manual` beats `market_rate`. A price
    should only ever move *up* this scale on its own; anything moving it down is a correction
    somebody made deliberately.
    """

    # Bootstrapped from `library/market-rates.yaml` x the city multiplier. Nobody at this
    # restaurant has confirmed it. The UI must mark it.
    MARKET_RATE = "market_rate"
    # Typed by a human here — a chef or store manager who knows what they pay.
    MANUAL = "manual"
    # Derived from a real recorded purchase. The only one that is this restaurant's own truth.
    # M06 (procurement) is what will start writing this.
    PURCHASE = "purchase"


class MovementType(StrEnum):
    """What caused a line in the stock ledger.

    The type is how M13 tells shrinkage from service. `consumption` is a dish being made,
    `wastage` is something thrown away, `adjustment` is a human correcting the book — and an
    adjustment is never invisible, because a variance report that hid them would let an insider
    erase a shortfall by declaring it.
    """

    RECEIPT = "receipt"
    PRODUCTION = "production"
    CONSUMPTION = "consumption"
    WASTAGE = "wastage"
    STAFF_MEAL = "staff_meal"
    COMPLIMENTARY = "complimentary"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"
    COUNT = "count"


class MovementBasis(StrEnum):
    """How a movement's quantity was arrived at. Invariant 7 lives on this column.

    On-hand sums both — both genuinely move the book. What must never be summed across the two is
    a single *consumption* figure, because the difference between recipe-derived and physically
    observed consumption is the leakage number this product exists to surface.
    """

    # Derived from a recipe. What the dish says was used.
    THEORETICAL = "theoretical"
    # Physically observed. A receipt counted in, a weighed wastage, a shelf count.
    ACTUAL = "actual"


class StockCountScope(StrEnum):
    """How much of the storeroom a count covered, which decides what its variance means.

    A `full` count reconciles everything, so anything unexplained is real. A `spot` count of four
    items says nothing about the rest, and a variance report must not extrapolate from it.
    """

    FULL = "full"
    PARTIAL = "partial"
    SPOT = "spot"


class StockCountStatus(StrEnum):
    """Forward-only. Nothing reaches the ledger until `approved`.

    A `submitted` count is a worksheet; approval is what writes the adjustment movements. There is
    no `cancelled` and no delete, because the count somebody wants to lose is exactly the count
    that matters.
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"


class PurchaseOrderStatus(StrEnum):
    """Where an order is in its life. Forward-only, with two terminal states.

    ```
    draft ──send──▶ sent ──receive──▶ partial ──receive──▶ received
      │               │                  │
      └───cancel──────┴──────cancel──────┘
    ```

    `partial` is the value that earns the enum. A supplier delivering 30 of 50 sacks is the
    ordinary case, not an exception, and an order that went straight from `sent` to `received`
    would lose the fact that 20 are still owed — which is the number a store manager chases.

    `cancelled` and `received` are terminal, and a cancellation always carries a reason (a CHECK
    constraint pairs the two). A PO is never deleted: ADR 0008 puts it in the transactional tier,
    where state lives in `status` and the row stays.
    """

    DRAFT = "draft"
    SENT = "sent"
    PARTIAL = "partial"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class OrderType(StrEnum):
    DINE_IN = "dine_in"
    TAKEAWAY = "takeaway"
    DELIVERY = "delivery"


class OrderChannel(StrEnum):
    """Where an order came from (G-13 checklist item 2, finding S4).

    `aggregator` is recorded, not integrated: an order a waiter keys in from a Swiggy tablet is
    still an aggregator order, and M13 must split it from dine-in without an importer existing.
    """

    POS = "pos"
    QR = "qr"
    AGGREGATOR = "aggregator"


class OrderStatus(StrEnum):
    """An order's life. `settled`, `cancelled` and `voided` are final.

    `cancelled` is an order that never settled, so it never consumed an invoice number and cannot
    make a gap. `voided` is a settled order whose invoice was cancelled on its day of issue.
    Anything after that day is a credit note, and the order stays `settled`.
    """

    OPEN = "open"
    SENT = "sent"
    SERVED = "served"
    SETTLED = "settled"
    CANCELLED = "cancelled"
    VOIDED = "voided"


class OrderLineStatus(StrEnum):
    """`preparing` and `ready` belong to M08's kitchen display and are allowed now so M08 needs no
    migration. `sent` is M07's own: without it, a line the kitchen has seen and a line nobody has
    sent would both read `pending`."""

    PENDING = "pending"
    SENT = "sent"
    PREPARING = "preparing"
    READY = "ready"
    SERVED = "served"
    CANCELLED = "cancelled"
    RETURNED = "returned"


class WastageStage(StrEnum):
    """Where in the restaurant the money leaked (M09, `docs/waste-model.md`).

    Four stages, never lumped: each has a different owner, a different fix and a different size,
    and "lumping them produces a number nobody can act on" is the sentence this enum exists for.
    Prep is the biggest and the least measured — 4 to 8% of food cost — and the only one with a
    same-day fix.

    What is **not** here is as important: `staff_meal` and `complimentary` are separate movement
    types from M05 and are not waste. Indian restaurants feed staff, always; counted as waste it
    looks like theft and poisons every variance number.
    """

    RECEIVING = "receiving"
    STORAGE = "storage"
    PREP = "prep"
    SERVICE = "service"


class KotTicketStatus(StrEnum):
    """One round of dishes at one station, from the printer to the pass (M08).

    The path is one-way: `new → acknowledged → preparing → ready`, and nothing goes back. Correcting
    a mistake is a remake with a reason, which is a row, not an edit.

    **`served` is not the kitchen's**, even though it lives here. A dish is served when it reaches a
    table, which the kitchen cannot see — it is written by the order's serve path, behind the
    permissions a waiter holds, and refused on every KOT route. That separation is the control
    against a rail being cleared of food that never left the pass: marking everything `ready`
    settles nothing and hides nothing, it only makes the gap to `served_at` visible.

    `cancelled` is nobody's transition either. A ticket is cancelled by its order's lines being
    cancelled, never by a button on the rail.
    """

    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    PREPARING = "preparing"
    READY = "ready"
    SERVED = "served"
    CANCELLED = "cancelled"


class KotLineStatus(StrEnum):
    """One dish on a ticket. `remake` is terminal: the remade dish is new work on a new ticket, so
    the original line keeps its history instead of being reopened."""

    PENDING = "pending"
    PREPARING = "preparing"
    READY = "ready"
    SERVED = "served"
    CANCELLED = "cancelled"
    REMAKE = "remake"


class DiscountType(StrEnum):
    PERCENTAGE = "percentage"
    FLAT = "flat"
    COMP = "comp"


class ChargeType(StrEnum):
    """A service charge is only ever optional (CCPA guidelines, 4 Jul 2022, upheld 28 Mar 2025)."""

    PACKAGING = "packaging"
    SERVICE_CHARGE = "service_charge"
    DELIVERY = "delivery"


class PaymentMethod(StrEnum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"
    WALLET = "wallet"
    ONLINE = "online"
    DUE = "due"


class PaymentStatus(StrEnum):
    """No `refunded`. A refund is a new negative payment, never a status on the original row:
    `docs/schema.md` eliminated a refund table for that reason, and payments are append-only."""

    SUCCESS = "success"
    FAILED = "failed"


class GstScheme(StrEnum):
    """Which GST scheme a restaurant is under. It decides the document, not merely the rate.

    `regular` issues a tax invoice and collects CGST + SGST. `composition` pays tax on turnover,
    may NOT collect it from customers, and issues a bill of supply (CGST Act s.10; Rule 5(1)(f)).
    Both are commonly called "5%", which is the trap. `unregistered` collects nothing and issues a
    plain bill.
    """

    REGULAR = "regular"
    COMPOSITION = "composition"
    UNREGISTERED = "unregistered"


class TaxRegime(StrEnum):
    """`non_gst` is alcoholic liquor for human consumption: outside GST under Article 366(12A),
    taxed by the state. Such a line is never split into CGST and SGST."""

    GST = "gst"
    NON_GST = "non_gst"


class DocumentType(StrEnum):
    TAX_INVOICE = "tax_invoice"
    BILL_OF_SUPPLY = "bill_of_supply"


class InvoiceStatus(StrEnum):
    """A cancelled invoice keeps its number: GSTR-1 Table 13 reports cancelled documents."""

    ISSUED = "issued"
    CANCELLED = "cancelled"


class IdempotencyState(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class CashSessionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class CashMovementType(StrEnum):
    """Cash out of the till that is not a refund. One table for both, because a payout and a
    post-close correction have identical shape, and two tables would be two places to sum."""

    PAYOUT = "payout"
    ADJUSTMENT = "adjustment"


# ---------------------------------------------------------------- M10 · customers & feedback


class PreferenceType(StrEnum):
    """What a customer always wants. `ALLERGY` is the only one the kitchen is told about, and the
    telling is `customer_preference.is_critical` rather than this value — a spice level can be
    critical to nobody, and a restaurant may decide a dietary rule is."""

    DIETARY = "dietary"
    ALLERGY = "allergy"
    SPICE_LEVEL = "spice_level"
    SEATING = "seating"
    OTHER = "other"


class ConsentPurpose(StrEnum):
    """One purpose per consent row (`docs/compliance-rules.md` §B2).

    Purpose limitation, stated concretely: "a phone number collected for a bill is not marketing
    consent". Granting one of these grants nothing else, and withdrawing one withdraws nothing else.
    """

    ORDER_CONTACT = "order_contact"
    SERVICE_RECOGNITION = "service_recognition"
    FEEDBACK_FOLLOWUP = "feedback_followup"
    MARKETING = "marketing"


class ContactSource(StrEnum):
    """How a piece of customer input reached us — shared by `feedback` and `customer_consent`.

    One enum rather than two because the four ways are the same four ways, and because the value is
    read the same way in both places: a `STAFF` rating and a `STAFF` consent both mean an employee
    entered it on somebody's behalf, which is legitimate and must be visible.
    """

    QR = "qr"
    APP = "app"
    STAFF = "staff"
    CALL = "call"


class ComplaintCategory(StrEnum):
    FOOD_QUALITY = "food_quality"
    SERVICE = "service"
    DELAY = "delay"
    BILLING = "billing"
    HYGIENE = "hygiene"
    STAFF_CONDUCT = "staff_conduct"
    OTHER = "other"


class ComplaintSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplaintStatus(StrEnum):
    """`RESOLVED` means somebody wrote down what was done; `CLOSED` means it is finished with.

    The gap between them is deliberate: a complaint can be resolved and still open on somebody's
    screen until the manager agrees it is done.
    """

    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ConversationType(StrEnum):
    """What a thread is for. `TASK` and `COMPLAINT` threads carry `ref_type`/`ref_id`.

    `ANNOUNCEMENT` exists because `docs/schema.md` declares it and a later module may want it.
    **Nothing in M11 creates one** (M11 spec, Not in scope): a broadcast nobody may reply to needs
    a permission the P1 design does not contain, and a group containing everybody already reaches
    everybody.
    """

    DIRECT = "direct"
    GROUP = "group"
    TASK = "task"
    COMPLAINT = "complaint"
    ANNOUNCEMENT = "announcement"


class MessagePriority(StrEnum):
    """Sorting and colour, and deliberately nothing else in M11.

    No push, no email, no SMS: `notification` is M14's table and escalation tiers are M14's problem
    (vision doc §25). An `URGENT` message sorts its conversation to the top of every participant's
    inbox and renders in the locked alert colour. That is the whole feature.
    """

    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(StrEnum):
    """The lifecycle, held as a transition table in the service rather than scattered `if`s.

    `VERIFIED` is a separate state from `COMPLETED` on purpose, and it is the module's reason to
    exist: somebody did the work, and somebody else agrees it was done. Collapsing the two would
    leave "the fryer was cleaned" as an unverifiable claim by the person who was asked to clean it.
    """

    CREATED = "created"
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFIED = "verified"
    CANCELLED = "cancelled"


class AttachmentOwnerType(StrEnum):
    """One `attachment` table, six owners (`docs/schema.md` §10).

    M11 gives three of them a screen — message, task and the waste photo M09 has been waiting for.
    The other three are authorised and unbuilt on purpose (M11 spec decision 6): the trigger for a
    screen is somebody asking for one.
    """

    MESSAGE = "message"
    TASK = "task"
    COMPLAINT = "complaint"
    WASTAGE_EVENT = "wastage_event"
    FEEDBACK = "feedback"
    GOODS_RECEIPT = "goods_receipt"


class AttachmentStatus(StrEnum):
    """`PENDING` until the bytes are in the store and have been checked.

    With the S3 driver the API never sees the bytes, so nothing about a `PENDING` row may be
    trusted: the size is a claim and the content type is a claim. `READY` means the store was asked
    how big the object is and its first bytes were read back and matched. A `PENDING` row older
    than an hour is swept along with any object behind it.
    """

    PENDING = "pending"
    READY = "ready"


class ShiftAssignmentStatus(StrEnum):
    """Where a rostered person stands on the day.

    **`PRESENT` and `LATE` are derived at clock-in; `ABSENT` and `LEAVE` are said by a person.**
    Nothing in the background flips a status — there is no job that marks people absent at eleven
    at night. Somebody who never clocked in stays `SCHEDULED`, and the roster renders that as "did
    not clock in", which is the truth. Storing an `ABSENT` nobody asserted would put a
    disciplinary fact in the database with no author.
    """

    SCHEDULED = "scheduled"
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    LEAVE = "leave"


class PerformancePeriodType(StrEnum):
    """A week or a month. Nothing shorter, because a day of a restaurant is weather."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"


class PerformancePeriodStatus(StrEnum):
    """`draft -> published -> finalised`, and **publish is the freeze** (ADR 0011).

    While draft every metric is computed live. On publish they are written into
    `performance_score` and never recomputed, for the same reason `theoretical_food_cost` is frozen
    at settlement: a later void must not rewrite the basis on which a bonus was paid.
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    FINALISED = "finalised"


class PerformanceMetricKind(StrEnum):
    """Whether a metric carries weight, and the whole of ADR 0011's second decision.

    `CONTEXT` metrics are shown beside the score and contribute **zero**. A waiter penalised for the
    tandoor running slow will correctly conclude the system is stupid and ignore all of it - so
    kitchen delay, section footfall, table size and tips are context, and showing them is what makes
    a low score explainable rather than accusatory.
    """

    CONTROLLABLE = "controllable"
    CONTEXT = "context"


class PerformanceNoteKind(StrEnum):
    """Who is talking, and whether an answer is owed.

    A `DISPUTE` is raised by the person being measured, and a period **cannot be published while
    one is unanswered**. `docs/workload-fairness.md`'s ethics review: visibility without recourse is
    the shape of surveillance rather than of feedback.
    """

    CONTEXT = "context"
    DISPUTE = "dispute"


class AwardType(StrEnum):
    """What recognition can be, and it need not be money.

    In Indian restaurants non-cash recognition often lands harder than a small bonus - a name on a
    board by the kitchen door is cheap and works (`docs/workload-fairness.md`).
    """

    CASH = "cash"
    LEAVE = "leave"
    SHIFT_PREFERENCE = "shift_preference"
    MEAL = "meal"
    RECOGNITION_ONLY = "recognition_only"
