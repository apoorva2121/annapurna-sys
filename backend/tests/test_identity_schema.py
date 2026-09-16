"""The invariants, asserted against Postgres rather than against our own good intentions.

Application code is the first line of defence and the database is the last one. Every rule below is
something that must hold even if a service forgets, a migration is hand-run, or someone opens psql
at 2am. If a constraint here is missing, the failure is silent: bad rows accumulate and are found
much later, by which time they are load-bearing.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EmploymentType, OrganizationPlan, RoleCode, UserAccountStatus
from app.models.access import EmployeeRoleAssignment, Permission, Role
from app.models.identity import Employee, UserAccount
from app.models.tenancy import Organization, Restaurant


async def _organization(session: AsyncSession, slug: str = "spice-garden") -> Organization:
    organization = Organization(
        name="Spice Garden Hospitality", slug=slug, plan=OrganizationPlan.TRIAL
    )
    session.add(organization)
    await session.flush()
    return organization


async def _restaurant(
    session: AsyncSession, organization: Organization, code: str = "SG1"
) -> Restaurant:
    restaurant = Restaurant(organization_id=organization.id, name="Spice Garden", code=code)
    session.add(restaurant)
    await session.flush()
    return restaurant


async def _account(
    session: AsyncSession, organization: Organization, **kwargs: object
) -> UserAccount:
    defaults: dict[str, object] = {
        "organization_id": organization.id,
        "email": "owner@spicegarden.test",
        "status": UserAccountStatus.ACTIVE,
    }
    account = UserAccount(**(defaults | kwargs))
    session.add(account)
    await session.flush()
    return account


async def _employee(
    session: AsyncSession, organization: Organization, **kwargs: object
) -> Employee:
    defaults: dict[str, object] = {
        "organization_id": organization.id,
        "employee_code": "EMP001",
        "full_name": "Ramesh Iyer",
        "joined_on": date(2026, 1, 15),
        "employment_type": EmploymentType.FULL_TIME,
    }
    employee = Employee(**(defaults | kwargs))
    session.add(employee)
    await session.flush()
    return employee


class TestUserAccount:
    async def test_an_account_with_neither_email_nor_phone_is_rejected(
        self, db_session: AsyncSession
    ) -> None:
        # An account nobody can sign in to is not a valid account. schema.md §1 makes this a CHECK
        # precisely because "the form requires one of them" is not a guarantee.
        organization = await _organization(db_session)
        with pytest.raises(IntegrityError):
            await _account(db_session, organization, email=None, phone=None)

    async def test_a_phone_only_account_is_valid(self, db_session: AsyncSession) -> None:
        # The approved default for waiters and kitchen staff, who often have no working email.
        organization = await _organization(db_session)
        account = await _account(db_session, organization, email=None, phone="+919876543210")
        assert account.id is not None

    async def test_one_email_cannot_be_used_twice_in_an_organization(
        self, db_session: AsyncSession
    ) -> None:
        organization = await _organization(db_session)
        await _account(db_session, organization)
        with pytest.raises(IntegrityError):
            await _account(db_session, organization)

    async def test_one_phone_cannot_be_used_twice_in_an_organization(
        self, db_session: AsyncSession
    ) -> None:
        organization = await _organization(db_session)
        await _account(db_session, organization, email=None, phone="+919876543210")
        with pytest.raises(IntegrityError):
            await _account(db_session, organization, email=None, phone="+919876543210")

    async def test_the_same_email_may_exist_in_two_different_organizations(
        self, db_session: AsyncSession
    ) -> None:
        """Uniqueness is per tenant, not global. A globally unique email would let one restaurant
        group discover that an address is registered to another — and would block a genuine
        consultant who works for two."""
        first = await _organization(db_session, slug="spice-garden")
        second = await _organization(db_session, slug="tandoor-house")
        await _account(db_session, first)
        await _account(db_session, second)  # must not raise

    async def test_an_unknown_status_is_rejected(self, db_session: AsyncSession) -> None:
        organization = await _organization(db_session)
        with pytest.raises((IntegrityError, DBAPIError)):
            await _account(db_session, organization, status="pending")


class TestEmployee:
    async def test_an_employee_can_exist_with_no_login_at_all(
        self, db_session: AsyncSession
    ) -> None:
        """ADR 0007's central claim, and M01 acceptance criterion 10. A cleaner is referenced by
        tasks and shifts without ever having a password."""
        organization = await _organization(db_session)
        employee = await _employee(db_session, organization, user_account_id=None)
        assert employee.user_account_id is None

    async def test_one_login_cannot_belong_to_two_employees(self, db_session: AsyncSession) -> None:
        # Otherwise a second employee row silently inherits the first person's sessions.
        organization = await _organization(db_session)
        account = await _account(db_session, organization)
        await _employee(db_session, organization, user_account_id=account.id)
        with pytest.raises(IntegrityError):
            await _employee(
                db_session, organization, employee_code="EMP002", user_account_id=account.id
            )

    async def test_employee_code_is_unique_within_an_organization(
        self, db_session: AsyncSession
    ) -> None:
        organization = await _organization(db_session)
        await _employee(db_session, organization)
        with pytest.raises(IntegrityError):
            await _employee(db_session, organization, full_name="Someone Else")

    async def test_an_unknown_employment_type_is_rejected(self, db_session: AsyncSession) -> None:
        organization = await _organization(db_session)
        with pytest.raises((IntegrityError, DBAPIError)):
            await _employee(db_session, organization, employment_type="intern")


class TestRolesAndPermissions:
    async def test_system_roles_are_seeded_by_the_migration(self, db_session: AsyncSession) -> None:
        """The catalogue ships with the schema (ADR 0007), so a fresh database is usable without
        anyone remembering to run a script."""
        roles = (
            await db_session.scalars(Role.__table__.select().with_only_columns(Role.code))
        ).all()
        assert set(roles) >= {member.value for member in RoleCode}

    async def test_the_permission_catalogue_is_seeded_by_the_migration(
        self, db_session: AsyncSession
    ) -> None:
        codes = (
            await db_session.scalars(
                Permission.__table__.select().with_only_columns(Permission.code)
            )
        ).all()
        assert "employee.view" in set(codes)

    async def test_a_permission_code_cannot_be_registered_twice(
        self, db_session: AsyncSession
    ) -> None:
        db_session.add(
            Permission(code="employee.view", resource="employee", action="view", description="dup")
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_person_cannot_hold_the_same_role_twice_at_one_restaurant(
        self, db_session: AsyncSession
    ) -> None:
        # A duplicate assignment is harmless until someone counts rows to decide something.
        organization = await _organization(db_session)
        restaurant = await _restaurant(db_session, organization)
        employee = await _employee(db_session, organization)
        role = Role(organization_id=organization.id, code="manager", name="Manager")
        db_session.add(role)
        await db_session.flush()

        for _ in range(2):
            db_session.add(
                EmployeeRoleAssignment(
                    employee_id=employee.id, restaurant_id=restaurant.id, role_id=role.id
                )
            )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_one_person_can_hold_different_roles_at_different_restaurants(
        self, db_session: AsyncSession
    ) -> None:
        """ADR 0007: a manager at one branch may be a waiter at another. The unique constraint must
        not accidentally forbid this."""
        organization = await _organization(db_session)
        first = await _restaurant(db_session, organization, code="SG1")
        second = await _restaurant(db_session, organization, code="SG2")
        employee = await _employee(db_session, organization)
        manager = Role(organization_id=organization.id, code="manager", name="Manager")
        waiter = Role(organization_id=organization.id, code="waiter", name="Waiter")
        db_session.add_all([manager, waiter])
        await db_session.flush()

        db_session.add_all(
            [
                EmployeeRoleAssignment(
                    employee_id=employee.id, restaurant_id=first.id, role_id=manager.id
                ),
                EmployeeRoleAssignment(
                    employee_id=employee.id, restaurant_id=second.id, role_id=waiter.id
                ),
            ]
        )
        await db_session.flush()  # must not raise


class TestConventions:
    async def test_every_timestamp_is_stored_with_a_timezone(
        self, db_session: AsyncSession
    ) -> None:
        """ADR 0004. A naive timestamp column is a bug that only appears when a restaurant's
        business day is computed near midnight."""
        organization = await _organization(db_session)
        assert organization.created_at.tzinfo is not None

    async def test_ids_are_time_ordered(self, db_session: AsyncSession) -> None:
        organization = await _organization(db_session)
        first = await _employee(db_session, organization, employee_code="EMP001")
        second = await _employee(db_session, organization, employee_code="EMP002")
        assert first.id < second.id

    async def test_deactivating_an_employee_keeps_the_row(self, db_session: AsyncSession) -> None:
        # ADR 0008 master-data tier: never hard deleted, because historical orders point here.
        organization = await _organization(db_session)
        employee = await _employee(db_session, organization)
        employee.is_active = False
        employee.deactivated_at = datetime.now(UTC)
        await db_session.flush()
        assert employee.id is not None
