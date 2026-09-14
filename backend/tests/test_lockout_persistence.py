"""Wrong passwords slow a login down; they never lock it (backlog-issues B5, G-15, decision D28).

**What changed.** Acceptance criterion 3 locked an account for fifteen minutes after five wrong
passwords. Anyone who knew a waiter's phone number could lock them out mid-service, from anywhere
(P1-5), and "account locked" was an answer only a real login could get, which told a stranger the
login existed. Now each wrong password for one login waits a little longer than the last, a network
that keeps failing is refused for a while, and an account is locked only by a person.

**Why these tests use `fresh_database`.** The first lockout shipped broken under a green test: the
failure was counted inside the request that failed, and rolled back with it. A delay that depends on
remembered failures has the same trap, so every attempt here is its own session, committed or rolled
back exactly as a request would be. *A test that shares a transaction with the code it tests cannot
prove anything about durability.*
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.enums import EmploymentType, UserAccountStatus
from app.core.errors import AppError
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee, LoginAttempt, UserAccount
from app.models.tenancy import Organization, Restaurant
from app.services.auth import AuthService, InvalidCredentialsError

IDENTIFIER = "locked@example.test"
PASSWORD = "Staging#2026"  # noqa: S105
NETWORK = "203.0.113.7"
ANOTHER_NETWORK = "198.51.100.9"

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


@pytest.fixture
def pauses(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The delays sign-in asked for, recorded instead of waited out."""
    recorded: list[float] = []

    async def record(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr("app.services.auth._pause", record)
    return recorded


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
        full_name="Suresh Patil",
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


async def _attempt(
    factory: SessionFactory,
    password: str,
    *,
    identifier: str = IDENTIFIER,
    network: str = NETWORK,
) -> Exception | None:
    """One sign-in, in its own session, torn down exactly as a failed request tears one down."""
    async with factory() as session:
        try:
            await AuthService(session).login(identifier, password, ip_address=network)
        except AppError as error:
            return error
        await session.commit()
        return None


async def _failures(factory: SessionFactory) -> int:
    async with factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(LoginAttempt).where(LoginAttempt.succeeded.is_(False))
        )
        return int(count or 0)


@pytest.mark.usefixtures("pauses")
async def test_a_failed_attempt_is_remembered_after_the_request_ends(
    sessions: SessionFactory,
) -> None:
    """The assertion that would have caught the first lockout. One wrong password, then look in a
    different session — which is all "the next request" means."""
    assert await _attempt(sessions, "wrong") is not None

    assert await _failures(sessions) == 1, (
        "the failed attempt was rolled back with the request that failed, so no number of wrong "
        "passwords would ever slow anyone down"
    )


@pytest.mark.usefixtures("pauses")
async def test_wrong_passwords_never_lock_out_the_right_one(sessions: SessionFactory) -> None:
    """Five guesses by a stranger must not keep a waiter from signing in at 7pm on a Saturday."""
    for _ in range(5):
        assert isinstance(await _attempt(sessions, "wrong"), InvalidCredentialsError)

    assert await _attempt(sessions, PASSWORD) is None


async def test_the_sixth_wrong_attempt_waits_at_least_two_seconds(
    sessions: SessionFactory, pauses: list[float]
) -> None:
    for _ in range(5):
        await _attempt(sessions, "wrong")
    pauses.clear()

    await _attempt(sessions, "wrong")

    assert pauses, "the sixth wrong password was answered at once"
    assert pauses[0] >= 2


async def test_a_login_nobody_holds_waits_exactly_as_long_and_fails_the_same_way(
    sessions: SessionFactory, pauses: list[float]
) -> None:
    """The enumeration hole the old lock opened. A stranger learns nothing from the wait or the
    answer about whether a login exists."""
    seen = {}
    for identifier in (IDENTIFIER, "nobody@example.test"):
        for _ in range(5):
            await _attempt(sessions, "wrong", identifier=identifier)
        pauses.clear()
        error = await _attempt(sessions, "wrong", identifier=identifier)
        seen[identifier] = (type(error), list(pauses))

    assert seen[IDENTIFIER] == seen["nobody@example.test"]


async def test_signing_in_clears_the_wait(sessions: SessionFactory, pauses: list[float]) -> None:
    """Otherwise yesterday's four typos plus today's one slow someone down mid-service."""
    for _ in range(5):
        await _attempt(sessions, "wrong")
    assert await _attempt(sessions, PASSWORD) is None
    pauses.clear()

    await _attempt(sessions, "wrong")

    assert pauses == []


@pytest.mark.usefixtures("pauses")
async def test_a_network_that_keeps_failing_is_refused_and_no_other_is(
    sessions: SessionFactory,
) -> None:
    """Thirty failures from one network inside ten minutes. The refusal is about the network, so it
    is the same for a real login and one nobody holds."""
    for _ in range(30):
        await _attempt(sessions, "wrong", identifier="nobody@example.test")

    refused = await _attempt(sessions, PASSWORD)
    elsewhere = await _attempt(sessions, PASSWORD, network=ANOTHER_NETWORK)

    assert isinstance(refused, AppError)
    assert refused.code == "auth.too_many_attempts"
    assert refused.status_code == 429
    assert elsewhere is None
