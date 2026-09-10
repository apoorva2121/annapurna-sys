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
