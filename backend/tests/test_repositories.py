"""Tenant isolation, tested at the layer that enforces it.

CLAUDE.md calls this the product's #1 bug class, and the reason it is a bug class rather than a bug
is that it is invisible: a forgotten filter returns *more* data, so nothing errors, nothing looks
broken, and the defect is found by a customer seeing another customer's staff. These tests exist so
that the failure is loud and immediate instead.

The rule being tested has two levels, because the threat model has two attackers:
  - a different **organization** must be invisible — the hard tenant boundary
  - a different **restaurant** in the same organization must be invisible too, because
    "a manager reads another branch's staff" is its own entry in the M01 threat table
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EmploymentType, UserAccountStatus
from app.core.tenancy import TenantScope
from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee, UserAccount
from app.models.tenancy import Organization, Restaurant
from app.repositories.employee import EmployeeRepository


class Tenant:
    """One organization with one restaurant and a role to assign — the smallest complete tenant."""

    def __init__(self, organization: Organization, restaurant: Restaurant, role: Role) -> None:
        self.organization = organization
        self.restaurant = restaurant
        self.role = role

    @property
    def scope(self) -> TenantScope:
        return TenantScope(organization_id=self.organization.id, restaurant_id=self.restaurant.id)


async def _tenant(session: AsyncSession, slug: str) -> Tenant:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(organization_id=organization.id, name=slug.title(), code="R1")
    role = Role(organization_id=organization.id, code="manager", name="Manager")
    session.add_all([restaurant, role])
    await session.flush()
    return Tenant(organization, restaurant, role)


async def _employee(
    session: AsyncSession,
    tenant: Tenant,
    name: str,
    *,
    assign_to: Restaurant | None = None,
) -> Employee:
    employee = Employee(
        organization_id=tenant.organization.id,
        employee_code=name.replace(" ", "").upper()[:8],
        full_name=name,
        joined_on=date(2026, 1, 1),
        employment_type=EmploymentType.FULL_TIME,
    )
    session.add(employee)
    await session.flush()
    if assign_to is not None:
        session.add(
            EmployeeRoleAssignment(
                employee_id=employee.id, restaurant_id=assign_to.id, role_id=tenant.role.id
            )
        )
        await session.flush()
    return employee


class TestTheScopeCannotBeSkipped:
    def test_a_repository_cannot_be_built_without_a_scope(self) -> None:
        """The structural guarantee. If a scope were optional, the one call site that omits it is
        the leak — and it would look exactly like every other call site in review."""
        with pytest.raises(TypeError):
            EmployeeRepository()  # type: ignore[call-arg]


class TestCrossOrganizationIsolation:
    async def test_listing_never_returns_another_organizations_employees(
        self, db_session: AsyncSession
    ) -> None:
        spice = await _tenant(db_session, "spice-garden")
        tandoor = await _tenant(db_session, "tandoor-house")
        await _employee(db_session, spice, "Ramesh Iyer", assign_to=spice.restaurant)
        await _employee(db_session, tandoor, "Priya Nair", assign_to=tandoor.restaurant)

        visible = await EmployeeRepository(db_session, tandoor.scope).list_visible()

        assert [employee.full_name for employee in visible] == ["Priya Nair"]

    async def test_fetching_another_organizations_employee_by_id_returns_nothing(
        self, db_session: AsyncSession
    ) -> None:
        """Manual test D1. Not 403 — *nothing*. A 403 on a real id and a 404 on a made-up one
        together confirm which ids exist, which is a slower version of the same leak."""
        spice = await _tenant(db_session, "spice-garden")
        tandoor = await _tenant(db_session, "tandoor-house")
        theirs = await _employee(db_session, spice, "Ramesh Iyer", assign_to=spice.restaurant)

        found = await EmployeeRepository(db_session, tandoor.scope).get(theirs.id)

        assert found is None

    async def test_updating_another_organizations_employee_finds_nothing_to_update(
        self, db_session: AsyncSession
    ) -> None:
        # Reads are the obvious hole; writes are the dangerous one. A repository that scopes SELECT
        # but not UPDATE lets one tenant edit another's rows without ever reading them.
        spice = await _tenant(db_session, "spice-garden")
        tandoor = await _tenant(db_session, "tandoor-house")
        theirs = await _employee(db_session, spice, "Ramesh Iyer", assign_to=spice.restaurant)

        found = await EmployeeRepository(db_session, tandoor.scope).get_for_update(theirs.id)

        assert found is None

    async def test_a_login_does_not_resolve_to_an_employee_in_another_organization(
        self, db_session: AsyncSession
    ) -> None:
        """The path where the organization filter is the *only* thing standing in the way.

        Found by mutation testing: deleting the organization filter left the two tests above green,
        because the branch-assignment filter excludes another organization's staff as a side effect
        (their restaurant id never matches ours). This lookup runs at login, before a restaurant is
        known, so it uses the organization filter alone — and getting it wrong would hand one
        tenant's session to another tenant's account.
        """
        spice = await _tenant(db_session, "spice-garden")
        tandoor = await _tenant(db_session, "tandoor-house")
        account = UserAccount(
            organization_id=spice.organization.id,
            email="owner@spicegarden.test",
            status=UserAccountStatus.ACTIVE,
        )
        db_session.add(account)
        await db_session.flush()
        theirs = await _employee(db_session, spice, "Ramesh Iyer", assign_to=spice.restaurant)
        theirs.user_account_id = account.id
        await db_session.flush()

        found = await EmployeeRepository(db_session, tandoor.scope).get_by_user_account(account.id)

        assert found is None


class TestCrossRestaurantIsolationInsideOneOrganization:
    async def test_an_employee_assigned_only_to_another_branch_is_not_visible(
        self, db_session: AsyncSession
    ) -> None:
        """The subtler half. Both branches belong to one company, so the organization filter
        passes — and without the assignment filter, a branch manager reads head office's staff."""
        chain = await _tenant(db_session, "big-chain")
        second_branch = Restaurant(
            organization_id=chain.organization.id, name="Branch Two", code="R2"
        )
        db_session.add(second_branch)
        await db_session.flush()

        await _employee(db_session, chain, "Branch One Cook", assign_to=chain.restaurant)
        theirs = await _employee(db_session, chain, "Branch Two Cook", assign_to=second_branch)

        repository = EmployeeRepository(db_session, chain.scope)

        assert [e.full_name for e in await repository.list_visible()] == ["Branch One Cook"]
        assert await repository.get(theirs.id) is None

    async def test_an_employee_assigned_to_both_branches_is_visible_from_both(
        self, db_session: AsyncSession
    ) -> None:
        # ADR 0007: one person may hold roles at several restaurants. The filter must not turn
        # that into "visible at whichever one we happened to join first".
        chain = await _tenant(db_session, "big-chain")
        second_branch = Restaurant(
            organization_id=chain.organization.id, name="Branch Two", code="R2"
        )
        db_session.add(second_branch)
        await db_session.flush()

        employee = await _employee(db_session, chain, "Roaming Manager", assign_to=chain.restaurant)
        db_session.add(
            EmployeeRoleAssignment(
                employee_id=employee.id, restaurant_id=second_branch.id, role_id=chain.role.id
            )
        )
        await db_session.flush()

        from_branch_two = EmployeeRepository(
            db_session,
            TenantScope(organization_id=chain.organization.id, restaurant_id=second_branch.id),
        )
        assert await from_branch_two.get(employee.id) is not None

    async def test_an_employee_appears_once_even_with_several_roles_here(
        self, db_session: AsyncSession
    ) -> None:
        # The join fans out per assignment. Without a DISTINCT the staff list shows one person
        # three times, which reads as a data bug to whoever is looking at it.
        chain = await _tenant(db_session, "big-chain")
        employee = await _employee(db_session, chain, "Busy Person", assign_to=chain.restaurant)
        extra = Role(organization_id=chain.organization.id, code="waiter", name="Waiter")
        db_session.add(extra)
        await db_session.flush()
        db_session.add(
            EmployeeRoleAssignment(
                employee_id=employee.id, restaurant_id=chain.restaurant.id, role_id=extra.id
            )
        )
        await db_session.flush()

        visible = await EmployeeRepository(db_session, chain.scope).list_visible()

        assert [e.full_name for e in visible] == ["Busy Person"]


class TestTheNewlyCreatedEmployee:
    async def test_an_employee_with_no_assignment_yet_is_still_visible_to_their_creator(
        self, db_session: AsyncSession
    ) -> None:
        """A manager may create staff but not assign roles, so there is a real window where an
        employee belongs to nobody. Filtering purely on assignment would make the person a manager
        just created invisible to that manager — the feature would look broken on first use."""
        spice = await _tenant(db_session, "spice-garden")
        await _employee(db_session, spice, "Just Hired", assign_to=None)

        visible = await EmployeeRepository(db_session, spice.scope).list_visible()

        assert [employee.full_name for employee in visible] == ["Just Hired"]

    async def test_an_unassigned_employee_is_still_invisible_to_another_organization(
        self, db_session: AsyncSession
    ) -> None:
        # The exception above must not become a hole: unassigned means "not placed yet", never
        # "visible to everyone".
        spice = await _tenant(db_session, "spice-garden")
        tandoor = await _tenant(db_session, "tandoor-house")
        theirs = await _employee(db_session, spice, "Just Hired", assign_to=None)

        assert await EmployeeRepository(db_session, tandoor.scope).get(theirs.id) is None


class TestListing:
    async def test_inactive_employees_are_excluded_by_default_but_findable(
        self, db_session: AsyncSession
    ) -> None:
        # ADR 0008: deactivated, never deleted. The list defaults to active because that is the
        # question being asked, but the row must remain reachable.
        spice = await _tenant(db_session, "spice-garden")
        gone = await _employee(db_session, spice, "Left Last Month", assign_to=spice.restaurant)
        gone.is_active = False
        await db_session.flush()

        repository = EmployeeRepository(db_session, spice.scope)

        assert await repository.list_visible() == []
        assert [e.full_name for e in await repository.list_visible(is_active=None)] == [
            "Left Last Month"
        ]

    async def test_the_page_size_is_capped(self, db_session: AsyncSession) -> None:
        """engineering-standards §3: no unbounded result set. A caller asking for 10,000 rows gets
        the maximum, not a query that reads the whole table."""
        spice = await _tenant(db_session, "spice-garden")
        for index in range(5):
            await _employee(db_session, spice, f"Person {index}", assign_to=spice.restaurant)

        visible = await EmployeeRepository(db_session, spice.scope).list_visible(limit=10_000)

        assert len(visible) <= 100


class TestAccountLookup:
    """Identifier resolution is **global**, and creating a login is what must keep it unambiguous.

    This used to be org-scoped, with the reasoning that a global lookup would let one tenant
    confirm an address is registered to another. That reasoning was wrong in an instructive way:
    login never used this method — it built the same query inline, without the organization filter,
    because the login form asks for an identifier and not a tenant. So the scoped method protected
    nothing and made the clash check in `_create_login` look safe while it let one tenant take an
    identifier belonging to another and lock its owner out permanently.

    The confirmation risk is real but is answered where it actually arises: the staff form says
    only "already in use" and never which organization holds it.
    """

    async def test_it_finds_every_organization_holding_an_identifier(
        self, db_session: AsyncSession
    ) -> None:
        """Login needs *all* the matches, because more than one means it must refuse rather than
        guess which tenant the person meant."""
        spice = await _tenant(db_session, "spice-garden")
        tandoor = await _tenant(db_session, "tandoor-house")
        for tenant in (spice, tandoor):
            db_session.add(
                UserAccount(
                    organization_id=tenant.organization.id,
                    email="shared@example.test",
                    status=UserAccountStatus.ACTIVE,
                )
            )
        await db_session.flush()

        from app.repositories.account import UserAccountRepository

        found = await UserAccountRepository(db_session).find_all_by_identifier(
            "shared@example.test"
        )

        assert len(found) == 2

    async def test_an_identifier_held_by_another_tenant_counts_as_taken(
        self, db_session: AsyncSession
    ) -> None:
        """The check that closes the lockout attack. Someone else's identifier is not available,
        whatever organization the person asking belongs to."""
        spice = await _tenant(db_session, "spice-garden")
        await _tenant(db_session, "tandoor-house")
        db_session.add(
            UserAccount(
                organization_id=spice.organization.id,
                email="owner@spicegarden.test",
                status=UserAccountStatus.ACTIVE,
            )
        )
        await db_session.flush()

        from app.repositories.account import UserAccountRepository

        accounts = UserAccountRepository(db_session)
        # Taken inside its own organization; free in another (backlog-issues B4, D1).
        assert await accounts.identifier_taken_in(spice.organization.id, "OWNER@spicegarden.test")
        tandoor = await accounts.identifier_taken_in(
            (await _tenant(db_session, "tandoor-two")).organization.id, "owner@spicegarden.test"
        )
        assert not tandoor

    async def test_an_unused_identifier_is_free(self, db_session: AsyncSession) -> None:
        await _tenant(db_session, "spice-garden")

        from app.repositories.account import UserAccountRepository

        spice = await _tenant(db_session, "spice-garden-two")
        assert not await UserAccountRepository(db_session).identifier_taken_in(
            spice.organization.id, "nobody@example.test"
        )

    async def test_a_phone_resolves_the_same_way_an_email_does(
        self, db_session: AsyncSession
    ) -> None:
        # The approved login default for waiters and kitchen staff.
        spice = await _tenant(db_session, "spice-garden")
        account = UserAccount(
            organization_id=spice.organization.id,
            phone="+919876543210",
            status=UserAccountStatus.ACTIVE,
        )
        db_session.add(account)
        await db_session.flush()

        from app.repositories.account import UserAccountRepository

        found = await UserAccountRepository(db_session).find_all_by_identifier("+919876543210")

        assert [row.id for row in found] == [account.id]
