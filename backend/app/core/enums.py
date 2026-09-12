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
