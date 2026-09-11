"""Builds the demo world M01's manual pass is written against.

Everything here is **get-or-create by natural key**, because `make seed` is a command people run
casually and repeatedly. The failure this guards against is not "seeding crashed" — that is
obvious and cheap. It is "seeding a second time silently doubled every employee", which looks fine
until a list endpoint returns two of everyone and the numbers in a report are twice what they
should be.

The natural keys are the ones the database already enforces as unique, so the code and the
constraints agree on what "the same row" means:

    organization  slug
    restaurant    (organization_id, code)
    user_account  (organization_id, email)
    employee      (organization_id, employee_code)
    assignment    (employee_id, restaurant_id, role_id)

Roles are *not* created here. The nine system templates are seeded by migration (ADR 0007) so that
access control is version-controlled and diffable; this module only reads them and would rather
fail loudly than invent one.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import UserAccountStatus
from app.core.errors import AppError
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee, UserAccount
from app.models.tenancy import Organization, Restaurant
from app.seed.loader import (
    EmployeeRecord,
    OrganizationRecord,
    RestaurantRecord,
    SeedData,
    load_seed_data,
)

logger = logging.getLogger(__name__)


class MissingSystemRoleError(RuntimeError):
    """The catalogue migration has not run, or a role was renamed in the YAML but not in
    permissions.json. Either way the seed cannot guess which role was meant."""


@dataclass(frozen=True, slots=True)
class SeedSummary:
    """What the run actually changed, so `make seed` can say so rather than printing "done"."""

    organizations_created: int = 0
    restaurants_created: int = 0
    employees_created: int = 0
    logins_created: int = 0
    assignments_created: int = 0

    @property
    def created_nothing(self) -> bool:
        return not any(
            (
                self.organizations_created,
                self.restaurants_created,
                self.employees_created,
                self.logins_created,
                self.assignments_created,
            )
        )


async def seed_identity(session: AsyncSession, data: SeedData | None = None) -> SeedSummary:
    """Create the demo organizations, restaurants, logins and staff. Safe to run repeatedly.

    Does not commit — the caller owns the transaction, which is what lets the test suite seed
    inside a transaction it rolls back.
    """
    _refuse_outside_local()
    data = data or load_seed_data()
    roles = await _system_roles_by_code(session)

    organizations: dict[str, Organization] = {}
    restaurants: dict[str, Restaurant] = {}
    counts = _Counter()

    for org_record in data.organizations:
        organizations[org_record.code], created = await _organization(
            session, org_record, data.is_demo
        )
        counts.organizations += created

    # Explicit, because the next loop reads `organization.id` to build restaurants. It works
    # without this line, on autoflush — but only by accident of statement ordering, and an
    # accident is not something the next person should have to re-derive.
    await session.flush()

    for restaurant_record in data.restaurants:
        organization = organizations[restaurant_record.organization]
        restaurants[restaurant_record.code], created = await _restaurant(
            session, organization, restaurant_record
        )
        counts.restaurants += created

    # Flush once here rather than per row: every employee below needs the organization and
    # restaurant ids, and nothing before this point depends on anything after it.
    await session.flush()

    for employee_record in data.employees:
        restaurant = restaurants[employee_record.restaurant]
        await _employee(session, restaurant, employee_record, data.password, roles, counts)

    await session.flush()
    summary = SeedSummary(
        organizations_created=counts.organizations,
        restaurants_created=counts.restaurants,
        employees_created=counts.employees,
        logins_created=counts.logins,
        assignments_created=counts.assignments,
    )
    logger.info("seed.identity.complete", extra={"summary": summary})
    return summary


def _refuse_outside_local() -> None:
    """Refuse to build the demo world anywhere but a developer's machine.

    Every seeded login is `status=ACTIVE` with a password that is committed to this repository, in
    a file whose own header prints it. On staging that is an owner account for anyone who has read
    the source — which is defect 5 in this module's build log (the committed JWT secret that would
    have shipped to staging) wearing different clothes.

    `is_demo` is not the control people assume it is: it keeps these organizations out of reports,
    and does nothing whatsoever about signing in.

    No override flag, deliberately, for the same reason `Settings` offers none for the JWT secret.
    Seeding a real environment should require changing this code and thinking about why.
    """
    settings = get_settings()
    if settings.is_local:
        return
    raise AppError(
        "seed.not_local",
        f"Refusing to seed demo data when ENV={settings.env.value}. Every seeded login uses a "
        "password committed to this repository; creating them outside local would hand an owner "
        "account to anyone who can read the source.",
        status_code=400,
    )


class _Counter:
    """Mutable tally. A dataclass would be copied through every helper; this is passed by reference
    so each helper can record what it did without returning a tuple of five numbers."""

    __slots__ = ("assignments", "employees", "logins", "organizations", "restaurants")

    def __init__(self) -> None:
        self.organizations = 0
        self.restaurants = 0
        self.employees = 0
        self.logins = 0
        self.assignments = 0


async def _system_roles_by_code(session: AsyncSession) -> dict[str, Role]:
    rows = (await session.scalars(select(Role).where(Role.organization_id.is_(None)))).all()
    return {role.code: role for role in rows}


def _role_or_fail(roles: dict[str, Role], code: str, employee_code: str) -> Role:
    role = roles.get(code)
    if role is None:
        raise MissingSystemRoleError(
            f"Employee {employee_code} wants the role {code!r}, which is not a seeded system role. "
            "Run the migrations first (`make migrate`)."
        )
    return role


async def _organization(
    session: AsyncSession, record: OrganizationRecord, is_demo: bool
) -> tuple[Organization, int]:
    existing = await session.scalar(select(Organization).where(Organization.slug == record.slug))
    if existing is not None:
        return existing, 0

    organization = Organization(
        name=record.name,
        slug=record.slug,
        billing_email=record.billing_email,
        plan=record.plan,
        # Seeded organizations are excluded from every report, so a sales demo can never be
        # mistaken for a real restaurant's numbers.
        is_demo=is_demo,
    )
    session.add(organization)
    return organization, 1


async def _restaurant(
    session: AsyncSession, organization: Organization, record: RestaurantRecord
) -> tuple[Restaurant, int]:
    existing = await session.scalar(
        select(Restaurant).where(
            Restaurant.organization_id == organization.id,
            Restaurant.code == record.code,
        )
    )
    if existing is not None:
        return existing, 0

    hour, minute = (int(part) for part in record.business_day_start.split(":")[:2])
    restaurant = Restaurant(
        organization_id=organization.id,
        name=record.name,
        code=record.code,
        timezone=record.timezone,
        currency=record.currency,
        # ADR 0004: not midnight. The 01:30 order books to the day that is still being served.
        business_day_start=time(hour, minute),
        gstin=record.gstin,
        address=record.address,
        # No column of its own yet; M02 owns restaurant settings and will give it one if it earns
        # one. Losing it here would mean re-entering it from the YAML later.
        settings={"fssai_licence": record.fssai_licence} if record.fssai_licence else {},
    )
    session.add(restaurant)
    return restaurant, 1


async def _employee(
    session: AsyncSession,
    restaurant: Restaurant,
    record: EmployeeRecord,
    password: str,
    roles: dict[str, Role],
    counts: _Counter,
) -> None:
    organization_id = restaurant.organization_id
    role = _role_or_fail(roles, record.role, record.code)

    employee = await session.scalar(
        select(Employee).where(
            Employee.organization_id == organization_id,
            Employee.employee_code == record.code,
        )
    )
    if employee is not None:
        # Already here, so their roles belong to whoever has been running the restaurant since.
        # Re-asserting the YAML would undo real decisions: demote someone through the UI, run
        # `make seed` again for an unrelated reason, and they are silently a manager once more —
        # with no audit row, because the seed writes none. The seed builds the world once; it does
        # not manage it afterwards.
        return

    account_id = await _login(session, organization_id, record, password, counts)
    employee = Employee(
        organization_id=organization_id,
        user_account_id=account_id,
        employee_code=record.code,
        full_name=record.name,
        phone=record.phone,
        joined_on=record.joined,
        employment_type=record.employment_type,
    )
    session.add(employee)
    await session.flush()
    counts.employees += 1

    await _assignment(session, employee.id, restaurant.id, role.id, counts)


async def _login(
    session: AsyncSession,
    organization_id: uuid.UUID,
    record: EmployeeRecord,
    password: str,
    counts: _Counter,
) -> uuid.UUID | None:
    """None is a valid outcome and the point of ADR 0007.

    Cleaners and part-time kitchen staff are referenced by shifts, tasks and wastage events while
    never holding a password. If the seed gave everyone a login, the first restaurant to onboard
    would be the first real test of that path.
    """
    if record.login is None:
        return None

    email = record.login.strip().lower()
    existing = await session.scalar(
        select(UserAccount).where(
            UserAccount.organization_id == organization_id,
            UserAccount.email == email,
        )
    )
    if existing is not None:
        return existing.id

    account = UserAccount(
        organization_id=organization_id,
        email=email,
        # Both identifiers, deliberately: the M01 spec makes phone the honest default for waiters
        # and kitchen staff, and a seed that only carried emails would leave that path untested
        # against real data.
        phone=record.phone,
        password_hash=hash_password(password),
        status=UserAccountStatus.ACTIVE,
    )
    session.add(account)
    await session.flush()
    counts.logins += 1
    return account.id


async def _assignment(
    session: AsyncSession,
    employee_id: uuid.UUID,
    restaurant_id: uuid.UUID,
    role_id: uuid.UUID,
    counts: _Counter,
) -> None:
    existing = await session.scalar(
        select(EmployeeRoleAssignment).where(
            EmployeeRoleAssignment.employee_id == employee_id,
            EmployeeRoleAssignment.restaurant_id == restaurant_id,
            EmployeeRoleAssignment.role_id == role_id,
        )
    )
    if existing is not None:
        return
    session.add(
        EmployeeRoleAssignment(
            employee_id=employee_id,
            restaurant_id=restaurant_id,
            role_id=role_id,
            # Nobody appointed these people; the seed did. Recording a real employee here would
            # make the audit trail claim someone made a decision they did not make.
            assigned_by=None,
        )
    )
    counts.assignments += 1
