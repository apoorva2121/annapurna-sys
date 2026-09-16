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
