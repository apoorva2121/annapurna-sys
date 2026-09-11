"""`make seed` must produce the world `docs/manual-tests/M01-identity.md` is written against.

The manual script names five logins and a password. If the seed produces anything else, the first
twenty minutes of the manual pass are spent discovering that rather than testing the product — so
the names are asserted here rather than trusted.

Idempotency gets its own test because the realistic failure is not "seeding is broken", it is
"seeding a second time silently doubled every employee", which looks fine until a list endpoint
returns two of everyone.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RoleCode
from app.models.access import EmployeeRoleAssignment
from app.models.identity import Employee, UserAccount
from app.models.tenancy import Organization, Restaurant
from app.seed import seed_identity, seed_password
from app.services.auth import AuthService, InvalidCredentialsError

SEED_PASSWORD_VALUE = seed_password()

# The five the manual script logs in as. Nothing else in this module may rename them.
MANUAL_SCRIPT_LOGINS = (
    "owner@spicegarden.test",
    "manager@spicegarden.test",
    "waiter1@spicegarden.test",
    "chef@spicegarden.test",
    "manager@tandoorhouse.test",
)


@pytest.fixture
async def seeded(db_session: AsyncSession) -> AsyncSession:
    await seed_identity(db_session)
    return db_session


async def _count(session: AsyncSession, model: type) -> int:
    return int((await session.scalar(select(func.count()).select_from(model))) or 0)


# ------------------------------------------------------------------ what it builds


async def test_it_creates_two_organizations(seeded: AsyncSession) -> None:
    """Two organizations, not one with two restaurants.

    `docs/seed-data.md`: the second tenant exists so tenant-isolation tests have something to fail
    against. One organization with two branches is a weaker boundary and would let a leak pass.
    """
    names = sorted((await seeded.scalars(select(Organization.name))).all())
    assert names == ["Spice Garden Hospitality", "Tandoor House"]


async def test_each_organization_has_its_own_restaurant(seeded: AsyncSession) -> None:
    rows = (
        await seeded.execute(
            select(Organization.slug, Restaurant.code).join(
                Restaurant, Restaurant.organization_id == Organization.id
            )
        )
    ).all()
    assert sorted(tuple(row) for row in rows) == [
        ("spice-garden", "SG_KOREGAON"),
        ("tandoor-house", "TH_BANER"),
    ]


async def test_seeded_organizations_are_marked_as_demo(seeded: AsyncSession) -> None:
    """is_demo excludes them from every report, so a demo is never read as real numbers."""
    flags = (await seeded.scalars(select(Organization.is_demo))).all()
    assert list(flags) == [True, True]


async def test_the_restaurant_business_day_does_not_start_at_midnight(
    seeded: AsyncSession,
) -> None:
    """Invariant 4. A restaurant closing at 2am must book that 2am against the previous day."""
    starts = (await seeded.scalars(select(Restaurant.business_day_start))).all()
    assert {start.isoformat() for start in starts} == {"05:00:00"}


# ------------------------------------------------------------------------ logins


@pytest.mark.parametrize("identifier", MANUAL_SCRIPT_LOGINS)
async def test_every_login_the_manual_script_names_can_sign_in(
    seeded: AsyncSession, identifier: str
) -> None:
    result = await AuthService(seeded).login(identifier, SEED_PASSWORD_VALUE)
    assert result.access_token


async def test_a_seeded_person_can_sign_in_with_their_phone_number(
    seeded: AsyncSession,
) -> None:
    """Phone login is the honest default for waiters and kitchen staff (M01 spec, decision 2), so
    the seed has to exercise it — an email-only seed would leave the path untested on real data."""
    account = await seeded.scalar(
        select(UserAccount).where(UserAccount.email == "waiter1@spicegarden.test")
    )
    assert account is not None and account.phone
    result = await AuthService(seeded).login(account.phone, SEED_PASSWORD_VALUE)
    assert result.access_token


async def test_the_wrong_password_is_still_refused(seeded: AsyncSession) -> None:
    with pytest.raises(InvalidCredentialsError):
        await AuthService(seeded).login("owner@spicegarden.test", "not-the-seed-password")


async def test_the_owner_lands_on_their_own_restaurant(seeded: AsyncSession) -> None:
    """Acceptance criterion 1: the owner logs in and sees a page naming their restaurant."""
    result = await AuthService(seeded).login("owner@spicegarden.test", SEED_PASSWORD_VALUE)
    assert result.restaurant.code == "SG_KOREGAON"
    assert result.role_codes == (RoleCode.OWNER.value,)


async def test_the_tandoor_house_manager_lands_on_the_other_tenant(
    seeded: AsyncSession,
) -> None:
    """The whole point of the second organization: probe D1 needs these to be genuinely apart."""
    result = await AuthService(seeded).login("manager@tandoorhouse.test", SEED_PASSWORD_VALUE)
    assert result.restaurant.code == "TH_BANER"


# -------------------------------------------------------------------- ADR 0007


async def test_some_employees_have_no_login_at_all(seeded: AsyncSession) -> None:
    """ADR 0007 has to be visible in the demo, not merely supported by the schema.

    Cleaners and part-time kitchen staff are referenced by shifts, tasks and wastage events and
    frequently never hold a password. If the seed gave everyone a login, the first real restaurant
    to onboard would be the first test of that path.
    """
    without = (
        await seeded.scalars(select(Employee.full_name).where(Employee.user_account_id.is_(None)))
    ).all()
    assert len(list(without)) >= 1


async def test_everyone_seeded_has_a_role_somewhere(seeded: AsyncSession) -> None:
    """An employee with no assignment cannot sign in (`auth.no_restaurant`) and would look like a
    broken seed rather than a deliberate one."""
    employees = await _count(seeded, Employee)
    with_a_role = await seeded.scalar(
        select(func.count(func.distinct(EmployeeRoleAssignment.employee_id)))
    )
    assert with_a_role == employees


# ---------------------------------------------------------------- idempotency


async def test_seeding_twice_does_not_double_anything(seeded: AsyncSession) -> None:
    """`make seed` is run casually and repeatedly. Doubling is silent and corrupts every count."""
    before = {
        model: await _count(seeded, model)
        for model in (Organization, Restaurant, Employee, UserAccount, EmployeeRoleAssignment)
    }
    await seed_identity(seeded)
    after = {
        model: await _count(seeded, model)
        for model in (Organization, Restaurant, Employee, UserAccount, EmployeeRoleAssignment)
    }
    assert after == before


async def test_seeding_twice_leaves_the_logins_working(seeded: AsyncSession) -> None:
    """A re-seed that rewrote password hashes to something else would pass the count test above and
    still lock every tester out."""
    await seed_identity(seeded)
    result = await AuthService(seeded).login("owner@spicegarden.test", SEED_PASSWORD_VALUE)
    assert result.access_token


# -------------------------------------------------------------------- secrets


async def test_no_seeded_password_is_stored_in_clear(seeded: AsyncSession) -> None:
    hashes = (await seeded.scalars(select(UserAccount.password_hash))).all()
    assert hashes, "the seed created no credentials at all"
    for stored in hashes:
        assert stored is not None
        assert SEED_PASSWORD_VALUE not in stored
        assert stored.startswith("$argon2id$")
