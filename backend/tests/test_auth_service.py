"""The authentication rules, tested as behaviour rather than as implementation.

Every test here maps to a numbered acceptance criterion in docs/modules/M01-identity-spec.md or to
a row in its threat table. Auth is the module where "almost right" is a breach, so the failure
paths get more attention than the happy one.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EmploymentType, UserAccountStatus
from app.core.errors import AppError
from app.core.permissions import PermissionCode
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee, UserAccount, UserSession
from app.models.tenancy import Organization, Restaurant
from app.services.auth import AuthService, OrganizationChoiceNeeded

PASSWORD = "Staging#2026"  # noqa: S105


class Fixture:
    def __init__(
        self,
        organization: Organization,
        restaurant: Restaurant,
        account: UserAccount,
        employee: Employee,
    ) -> None:
        self.organization = organization
        self.restaurant = restaurant
        self.account = account
        self.employee = employee


async def _system_role(session: AsyncSession, code: str) -> Role:
    role = (
        await session.scalars(select(Role).where(Role.code == code, Role.organization_id.is_(None)))
    ).first()
    assert role is not None, f"system role {code} should have been seeded by the migration"
    return role


async def _setup(
    session: AsyncSession,
    *,
    slug: str = "spice-garden",
    role_code: str = "manager",
    email: str | None = "manager@spicegarden.test",
    phone: str | None = None,
    assign_role: bool = True,
) -> Fixture:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(organization_id=organization.id, name=slug.title(), code="R1")
    account = UserAccount(
        organization_id=organization.id,
        email=email,
        phone=phone,
        password_hash=await hash_password(PASSWORD),
        status=UserAccountStatus.ACTIVE,
    )
    session.add_all([restaurant, account])
    await session.flush()
    employee = Employee(
        organization_id=organization.id,
        user_account_id=account.id,
        employee_code="EMP001",
        full_name="Test Person",
        joined_on=date(2026, 1, 1),
        employment_type=EmploymentType.FULL_TIME,
    )
    session.add(employee)
    await session.flush()
    if assign_role:
        role = await _system_role(session, role_code)
        session.add(
            EmployeeRoleAssignment(
                employee_id=employee.id, restaurant_id=restaurant.id, role_id=role.id
            )
        )
        await session.flush()
    return Fixture(organization, restaurant, account, employee)


class TestLogin:
    async def test_a_seeded_manager_can_log_in(self, db_session: AsyncSession) -> None:
        fixture = await _setup(db_session)

        result = await AuthService(db_session).login("manager@spicegarden.test", PASSWORD)

        assert result.employee.id == fixture.employee.id
        assert result.restaurant.id == fixture.restaurant.id
        assert result.access_token
        assert result.refresh_token

    async def test_the_permissions_come_from_the_seeded_catalogue(
        self, db_session: AsyncSession
    ) -> None:
        await _setup(db_session, role_code="waiter")

        result = await AuthService(db_session).login("manager@spicegarden.test", PASSWORD)

        # A waiter holds exactly what the catalogue grants a waiter, and nothing else. Written as
        # a literal rather than derived from `permissions_for_role`, so that widening a waiter's
        # powers has to be a deliberate edit here — the failure mode this guards is a resolver that
        # quietly returns everything, which looks like it works.
        #
        # It was `frozenset()` until M03, when the P1 design's `menu.view` reached every role that
        # works a shift: a waiter who cannot read the menu cannot take an order.
        #
        # M07 added the four a waiter needs to take and settle a bill, and deliberately not
        # `order.void`, `order.discount` or `cash.manage` — the design's classic leakage vectors.
        #
        # M08 added `kot.view` and deliberately **not** `kot.update`: a waiter watches the kitchen
        # display and cannot drive it. Being able to see that table six's mains are still
        # `preparing` is information; being able to declare them ready is a way to make the numbers
        # look better.
        #
        # M10 added `customer.view` and `feedback.view`, both from the P1 design and both for the
        # same reason: `docs/customer-experience.md` puts the regular's card on the waiter's screen
        # — "7th visit, usually orders Butter Chicken + Butter Naan, no onion/garlic" — and a rating
        # is about a table this person served. Deliberately **not** `customer.manage`: editing
        # somebody's details, and erasing them, are accountable acts that belong to a manager.
        assert result.permissions == frozenset(
            {
                "customer.view",
                "feedback.view",
                "kot.view",
                "menu.view",
                "order.create",
                "order.modify",
                "order.settle",
                "order.view",
            }
        )

    async def test_a_phone_number_logs_in_the_same_way_an_email_does(
        self, db_session: AsyncSession
    ) -> None:
        await _setup(db_session, email=None, phone="+919876543210")

        result = await AuthService(db_session).login("+919876543210", PASSWORD)

        assert result.access_token

    async def test_the_email_is_matched_case_insensitively(self, db_session: AsyncSession) -> None:
        # Nobody types their address the same way twice on a phone keyboard.
        await _setup(db_session)

        result = await AuthService(db_session).login("Manager@SpiceGarden.test", PASSWORD)

        assert result.access_token

    async def test_last_login_is_recorded(self, db_session: AsyncSession) -> None:
        fixture = await _setup(db_session)

        await AuthService(db_session).login("manager@spicegarden.test", PASSWORD)

        await db_session.refresh(fixture.account)
        assert fixture.account.last_login_at is not None


class TestLoginFailuresAreIndistinguishable:
    """Acceptance criterion 2. An attacker must not be able to learn which addresses are
    registered, which is what makes a targeted password-guessing campaign possible."""

    async def test_a_wrong_password_and_an_unknown_address_give_the_identical_error(
        self, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        service = AuthService(db_session)

        with pytest.raises(AppError) as wrong_password:
            await service.login("manager@spicegarden.test", "not-the-password")
        with pytest.raises(AppError) as unknown_address:
            await service.login("nobody@spicegarden.test", PASSWORD)

        assert wrong_password.value.code == unknown_address.value.code
        assert wrong_password.value.message == unknown_address.value.message
        assert wrong_password.value.status_code == unknown_address.value.status_code

    async def test_the_error_does_not_name_the_field_that_was_wrong(
        self, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)

        with pytest.raises(AppError) as failure:
            await AuthService(db_session).login("manager@spicegarden.test", "wrong")

        message = failure.value.message.lower()
        # The message must name *both* possibilities or neither, never one. "Invalid login or
        # password" is correct; "wrong password" would confirm the address exists, and "no such
        # user" would confirm it does not.
        for singles_out_a_field in (
            "wrong password",
            "incorrect password",
            "invalid password",
            "no such",
            "not found",
            "does not exist",
            "unknown user",
            "unregistered",
        ):
            assert singles_out_a_field not in message, message
        assert " or " in message, f"the message should name both possibilities: {message}"

    async def test_an_unknown_address_still_costs_a_password_verification(
        self, db_session: AsyncSession
    ) -> None:
        """Timing is part of the response. Skipping the hash for an unknown address makes that
        request measurably faster, which leaks exactly what the identical message hides."""
        await _setup(db_session)
        service = AuthService(db_session)

        started = datetime.now(UTC)
        with pytest.raises(AppError):
            await service.login("nobody@spicegarden.test", PASSWORD)
        unknown_duration = datetime.now(UTC) - started

        # Argon2 at the configured cost is milliseconds, not microseconds. A skipped verification
        # would return in well under a millisecond.
        assert unknown_duration > timedelta(milliseconds=5)

    async def test_an_account_with_no_password_set_cannot_log_in(
        self, db_session: AsyncSession
    ) -> None:
        # status=invited, password_hash NULL. A blank password must not match a blank column.
        fixture = await _setup(db_session)
        fixture.account.password_hash = None
        fixture.account.status = UserAccountStatus.INVITED
        await db_session.flush()

        with pytest.raises(AppError):
            await AuthService(db_session).login("manager@spicegarden.test", "")


async def _no_wait(seconds: float) -> None:
    """Stands in for the sign-in delay, so a test never waits it out."""


class TestNoAutomaticLock:
    """Acceptance criterion 3 as amended by backlog-issues B5 (decision D28, guardrail G-15).

    Wrong passwords slow a login down and never lock it; a lock is set only by a person. That the
    failures are remembered across requests is proven in `tests/test_lockout_persistence.py`.
    """

    async def test_wrong_passwords_never_lock_out_the_right_one(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.services.auth._pause", _no_wait)
        fixture = await _setup(db_session)
        service = AuthService(db_session)
        for _ in range(6):
            with pytest.raises(AppError):
                await service.login("manager@spicegarden.test", "wrong")

        result = await service.login("manager@spicegarden.test", PASSWORD)

        assert result.access_token
        await db_session.refresh(fixture.account)
        assert fixture.account.locked_until is None

    async def test_a_lock_set_by_a_person_is_revealed_only_to_the_right_password(
        self, db_session: AsyncSession
    ) -> None:
        """Checked after the password, like a suspension: a stranger guessing gets the usual
        refusal, and only someone who knows the password learns the account is locked."""
        fixture = await _setup(db_session)
        fixture.account.locked_until = datetime.now(UTC) + timedelta(hours=1)
        await db_session.flush()
        service = AuthService(db_session)

        with pytest.raises(AppError) as guessed:
            await service.login("manager@spicegarden.test", "wrong")
        with pytest.raises(AppError) as known:
            await service.login("manager@spicegarden.test", PASSWORD)

        assert guessed.value.code == "auth.invalid_credentials"
        assert known.value.code == "auth.locked"
        assert "owner" in known.value.message.lower()


class TestWhoMayLogIn:
    async def test_a_deactivated_employee_cannot_log_in(self, db_session: AsyncSession) -> None:
        fixture = await _setup(db_session)
        fixture.employee.is_active = False
        await db_session.flush()

        with pytest.raises(AppError):
            await AuthService(db_session).login("manager@spicegarden.test", PASSWORD)

    async def test_a_suspended_account_cannot_log_in(self, db_session: AsyncSession) -> None:
        fixture = await _setup(db_session)
        fixture.account.status = UserAccountStatus.SUSPENDED
        await db_session.flush()

        with pytest.raises(AppError):
            await AuthService(db_session).login("manager@spicegarden.test", PASSWORD)

    async def test_an_employee_with_no_restaurant_yet_is_told_why(
        self, db_session: AsyncSession
    ) -> None:
        """The real window created by managers creating staff before roles are assigned. This is
        after authentication, so a specific message leaks nothing and saves a support call."""
        await _setup(db_session, assign_role=False)

        with pytest.raises(AppError) as refused:
            await AuthService(db_session).login("manager@spicegarden.test", PASSWORD)

        assert refused.value.code == "auth.no_restaurant"


class TestTheAwkwardEdges:
    """Paths that are hard to reach and expensive to get wrong."""

    async def test_an_identifier_matching_two_organizations_asks_which_one(
        self, db_session: AsyncSession
    ) -> None:
        """A consultant working for two restaurant groups holds the same address in both. The
        right password for both asks which organization — never guessing, which would sign someone
        into the wrong company's data (backlog-issues B4, D1a). Tested over HTTP in
        `tests/test_sign_in_choice.py`."""
        await _setup(db_session, slug="spice-garden")
        await _setup(db_session, slug="tandoor-house")  # same email, different organization

        with pytest.raises(OrganizationChoiceNeeded) as asked:
            await AuthService(db_session).login("manager@spicegarden.test", PASSWORD)

        assert sorted(each.slug for each in asked.value.organizations) == [
            "spice-garden",
            "tandoor-house",
        ]

    async def test_a_deactivated_restaurant_refuses_login(self, db_session: AsyncSession) -> None:
        # An organization that stopped paying, or a branch that closed. The person is real and
        # their password is right; there is simply nowhere to sign in to.
        fixture = await _setup(db_session)
        fixture.restaurant.is_active = False
        await db_session.flush()

        with pytest.raises(AppError) as refused:
            await AuthService(db_session).login("manager@spicegarden.test", PASSWORD)

        assert refused.value.code == "auth.no_restaurant"

    async def test_an_account_suspended_after_login_cannot_refresh(
        self, db_session: AsyncSession
    ) -> None:
        # Suspension has to bite at refresh, for the same reason deactivation does: the access
        # token already issued cannot be recalled.
        fixture = await _setup(db_session)
        service = AuthService(db_session)
        result = await service.login("manager@spicegarden.test", PASSWORD)
        fixture.account.status = UserAccountStatus.SUSPENDED
        await db_session.flush()

        with pytest.raises(AppError) as refused:
            await service.refresh(result.refresh_token)

        assert refused.value.code == "auth.session_invalid"

    async def test_an_employee_with_no_login_cannot_change_a_password(
        self, db_session: AsyncSession
    ) -> None:
        # ADR 0007: a cleaner may have no user_account at all. Asking them to change a password
        # must be a clear error, not an AttributeError on None.
        fixture = await _setup(db_session)
        fixture.employee.user_account_id = None
        await db_session.flush()

        with pytest.raises(AppError) as refused:
            await AuthService(db_session).change_own_password(
                fixture.employee, None, PASSWORD, "NewPassword#2026"
            )

        assert refused.value.code == "auth.no_login"


class TestRefreshRotation:
    """Acceptance criterion 6."""

    async def test_refreshing_returns_a_different_token(self, db_session: AsyncSession) -> None:
        await _setup(db_session)
        service = AuthService(db_session)
        first = await service.login("manager@spicegarden.test", PASSWORD)

        second = await service.refresh(first.refresh_token)

        assert second.refresh_token != first.refresh_token

    async def test_the_old_token_stops_working(self, db_session: AsyncSession) -> None:
        await _setup(db_session)
        service = AuthService(db_session)
        first = await service.login("manager@spicegarden.test", PASSWORD)
        await service.refresh(first.refresh_token)

        with pytest.raises(AppError):
            await service.refresh(first.refresh_token)

    async def test_replaying_a_rotated_token_kills_the_whole_family(
        self, db_session: AsyncSession
    ) -> None:
        """Theft detection. A rotated token being presented again means two parties hold tokens
        from one login, so the safe assumption is that one of them is not the owner — and every
        session descended from that login dies, forcing a fresh password."""
        await _setup(db_session)
        service = AuthService(db_session)
        first = await service.login("manager@spicegarden.test", PASSWORD)
        second = await service.refresh(first.refresh_token)

        with pytest.raises(AppError):
            await service.refresh(first.refresh_token)

        # The thief's replay also invalidated the legitimate holder's current token.
        with pytest.raises(AppError):
            await service.refresh(second.refresh_token)

    async def test_a_made_up_token_is_refused(self, db_session: AsyncSession) -> None:
        await _setup(db_session)
        with pytest.raises(AppError):
            await AuthService(db_session).refresh("not-a-real-token")

    async def test_an_expired_session_cannot_be_refreshed(self, db_session: AsyncSession) -> None:
        await _setup(db_session)
        service = AuthService(db_session)
        result = await service.login("manager@spicegarden.test", PASSWORD)
        row = (await db_session.scalars(select(UserSession))).first()
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.flush()

        with pytest.raises(AppError):
            await service.refresh(result.refresh_token)

    async def test_a_deactivated_employee_cannot_refresh(self, db_session: AsyncSession) -> None:
        """The access token cannot be revoked, only outlived — so refresh is where deactivation
        actually bites. Skipping this check would let a dismissed employee stay signed in for as
        long as they kept refreshing."""
        fixture = await _setup(db_session)
        service = AuthService(db_session)
        result = await service.login("manager@spicegarden.test", PASSWORD)
        fixture.employee.is_active = False
        await db_session.flush()

        with pytest.raises(AppError):
            await service.refresh(result.refresh_token)

    async def test_a_role_change_takes_effect_on_refresh(self, db_session: AsyncSession) -> None:
        # Acceptance criterion: a permission change must not wait for the token to expire.
        fixture = await _setup(db_session, role_code="manager")
        service = AuthService(db_session)
        result = await service.login("manager@spicegarden.test", PASSWORD)
        assert PermissionCode.EMPLOYEE_CREATE in result.permissions

        await db_session.execute(
            delete(EmployeeRoleAssignment).where(
                EmployeeRoleAssignment.employee_id == fixture.employee.id
            )
        )
        waiter = await _system_role(db_session, "waiter")
        db_session.add(
            EmployeeRoleAssignment(
                employee_id=fixture.employee.id,
                restaurant_id=fixture.restaurant.id,
                role_id=waiter.id,
            )
        )
        await db_session.flush()

        refreshed = await service.refresh(result.refresh_token)

        assert PermissionCode.EMPLOYEE_CREATE not in refreshed.permissions


class TestLogout:
    async def test_logging_out_revokes_the_presented_session(
        self, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        service = AuthService(db_session)
        result = await service.login("manager@spicegarden.test", PASSWORD)

        await service.logout(result.refresh_token)

        with pytest.raises(AppError):
            await service.refresh(result.refresh_token)

    async def test_logging_out_twice_is_not_an_error(self, db_session: AsyncSession) -> None:
        # The browser retries, the network hiccups. Logout must be idempotent or a user sees an
        # error while doing the safe thing.
        await _setup(db_session)
        service = AuthService(db_session)
        result = await service.login("manager@spicegarden.test", PASSWORD)

        await service.logout(result.refresh_token)
        await service.logout(result.refresh_token)

    async def test_logging_out_does_not_touch_other_sessions(
        self, db_session: AsyncSession
    ) -> None:
        # Signing out of the till must not sign you out of your phone.
        await _setup(db_session)
        service = AuthService(db_session)
        till = await service.login("manager@spicegarden.test", PASSWORD)
        phone = await service.login("manager@spicegarden.test", PASSWORD)

        await service.logout(till.refresh_token)

        assert await service.refresh(phone.refresh_token)


class TestPasswordChange:
    """Acceptance criterion 5."""

    async def test_the_password_actually_changes(self, db_session: AsyncSession) -> None:
        fixture = await _setup(db_session)
        service = AuthService(db_session)
        session = await service.login("manager@spicegarden.test", PASSWORD)

        await service.change_own_password(
            fixture.employee, session.session_id, PASSWORD, "NewPassword#2026"
        )

        with pytest.raises(AppError):
            await service.login("manager@spicegarden.test", PASSWORD)
        assert await service.login("manager@spicegarden.test", "NewPassword#2026")

    async def test_the_current_password_must_be_correct(self, db_session: AsyncSession) -> None:
        # Otherwise anyone borrowing an unlocked tablet owns the account permanently.
        fixture = await _setup(db_session)
        service = AuthService(db_session)
        session = await service.login("manager@spicegarden.test", PASSWORD)

        with pytest.raises(AppError):
            await service.change_own_password(
                fixture.employee, session.session_id, "wrong", "NewPassword#2026"
            )

    async def test_every_other_session_is_revoked_but_this_one_survives(
        self, db_session: AsyncSession
    ) -> None:
        """The reason to change a password is usually that someone else may have it. Leaving their
        session alive would make the change pointless; killing your own would sign you out of the
        screen you just used."""
        fixture = await _setup(db_session)
        service = AuthService(db_session)
        mine = await service.login("manager@spicegarden.test", PASSWORD)
        theirs = await service.login("manager@spicegarden.test", PASSWORD)

        await service.change_own_password(
            fixture.employee, mine.session_id, PASSWORD, "NewPassword#2026"
        )

        with pytest.raises(AppError):
            await service.refresh(theirs.refresh_token)
        assert await service.refresh(mine.refresh_token)
