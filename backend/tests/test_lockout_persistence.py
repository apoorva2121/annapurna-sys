"""Acceptance criterion 3: five failed attempts lock the account.

**This was shipped broken and had a green test.** `_record_failure` incremented the counter and
flushed it, but the login endpoint commits only on success — so the `InvalidCredentialsError` that
follows tears down the request, the session closes without committing, and the increment is
discarded. Five wrong passwords left `failed_attempts` at 0 in a real database. The
credential-stuffing control in `docs/security.md` did nothing at all.

The existing test passed because it drives the service inside the shared `db_session` transaction,
which is never rolled back: a write that will not survive the request is still perfectly visible to
the test that made it. That is the same failure mode as the two lying tests already recorded in
`docs/plan/m01-build-log.md`, and it is why these tests use `fresh_database` and real sessions —
one session per attempt, committed or rolled back exactly as a request would.

The general rule, third time in this module: *a test that shares a transaction with the code it
tests cannot prove anything about durability.*
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.enums import EmploymentType, UserAccountStatus
from app.core.errors import AppError
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee, UserAccount
from app.models.tenancy import Organization, Restaurant
from app.services.auth import AuthService, InvalidCredentialsError

IDENTIFIER = "locked@example.test"
PASSWORD = "Staging#2026"  # noqa: S105

# Each attempt opens its own session from this, which is what makes the tests mean anything.
SessionFactory = async_sessionmaker[AsyncSession]


@pytest.fixture
async def sessions(fresh_database: str) -> AsyncIterator[SessionFactory]:
    """A session factory against a real database, so each attempt is its own transaction."""
    engine = create_async_engine(fresh_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as setup:
        await _one_person(setup)
        await setup.commit()
    yield factory
    await engine.dispose()


async def _one_person(session: AsyncSession) -> None:
    organization = Organization(name="Spice Garden", slug="spice-garden")
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(organization_id=organization.id, name="Spice Garden", code="R1")
    session.add(restaurant)
    await session.flush()
    account = UserAccount(
        organization_id=organization.id,
        email=IDENTIFIER,
        password_hash=hash_password(PASSWORD),
        status=UserAccountStatus.ACTIVE,
    )
    session.add(account)
    await session.flush()
    employee = Employee(
        organization_id=organization.id,
        user_account_id=account.id,
        employee_code="E001",
        full_name="Locked Out",
        joined_on=date(2026, 1, 1),
        employment_type=EmploymentType.FULL_TIME,
    )
    session.add(employee)
    await session.flush()
    role = (
        await session.scalars(
            select(Role).where(Role.code == "waiter", Role.organization_id.is_(None))
        )
    ).first()
    assert role is not None
    session.add(
        EmployeeRoleAssignment(
            employee_id=employee.id, restaurant_id=restaurant.id, role_id=role.id
        )
    )


async def _attempt(factory: SessionFactory, password: str) -> Exception | None:
    """One login, in its own session, torn down exactly as a failed request tears one down.

    Nothing here commits on the failure path — that is the whole point. If the service relies on
    the caller to commit its counter, the counter is lost, and this returns as if nothing happened.
    """
    async with factory() as session:
        try:
            await AuthService(session).login(IDENTIFIER, password)
        except AppError as error:
            return error
        await session.commit()
        return None


async def _counter(factory: SessionFactory) -> tuple[int, bool]:
    async with factory() as session:
        account = await session.scalar(select(UserAccount).where(UserAccount.email == IDENTIFIER))
        assert account is not None
        return account.failed_attempts, account.locked_until is not None


async def test_a_failed_attempt_is_remembered_after_the_request_ends(
    sessions: SessionFactory,
) -> None:
    """The single assertion that would have caught this. One wrong password, then look in a
    different session — which is all "the next request" means."""
    assert await _attempt(sessions, "wrong") is not None

    attempts, _locked = await _counter(sessions)
    assert attempts == 1, (
        "the failed attempt was not durable — it was rolled back with the request that failed, "
        "so no number of wrong passwords will ever reach the lockout threshold"
    )


async def test_five_failures_lock_the_account(sessions: SessionFactory) -> None:
    for _ in range(get_settings().lockout_threshold):
        assert await _attempt(sessions, "wrong") is not None

    attempts, locked = await _counter(sessions)
    assert attempts >= get_settings().lockout_threshold
    assert locked, "five failures did not set locked_until"


async def test_the_correct_password_is_refused_while_locked(sessions: SessionFactory) -> None:
    """Acceptance criterion 3's real teeth. A lockout that the right password walks through is not
    a lockout, and this is the exact sequence the manual script's step B4 runs."""
    for _ in range(get_settings().lockout_threshold):
        await _attempt(sessions, "wrong")

    error = await _attempt(sessions, PASSWORD)

    assert error is not None, "the correct password signed in despite the account being locked"
    assert isinstance(error, AppError)
    assert error.code == "auth.locked"
    # The person needs to know roughly how long, or they will simply keep trying.
    assert "minute" in error.message


async def test_a_successful_login_clears_the_counter(sessions: SessionFactory) -> None:
    """Otherwise yesterday's four typos plus today's one lock someone out mid-service."""
    for _ in range(get_settings().lockout_threshold - 1):
        await _attempt(sessions, "wrong")

    assert await _attempt(sessions, PASSWORD) is None

    attempts, locked = await _counter(sessions)
    assert attempts == 0
    assert not locked


async def test_an_unknown_identifier_still_fails_the_same_way(sessions: SessionFactory) -> None:
    """The fix must not make a failed lookup behave differently from a wrong password — that is the
    enumeration hole the whole login path is built to avoid."""
    async with sessions() as session:
        with pytest.raises(InvalidCredentialsError):
            await AuthService(session).login("nobody@example.test", "wrong")
