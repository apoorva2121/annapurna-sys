"""Authentication: who you are, for how long, and how that ends.

The organising idea is that an **access token cannot be revoked, only outlived**. Everything that
must take effect immediately — a dismissal, a role change, a password change — is therefore
enforced when the refresh token is exchanged, not by trying to chase the access token. That makes
the access-token lifetime the worst-case window for a stale permission, and it is why that lifetime
is fifteen minutes rather than a day.

The other organising idea is that a failed login must give away nothing: same code, same message,
same status, and the same amount of time spent, whether the address exists or not.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import UserAccountStatus
from app.core.errors import AppError
from app.core.ids import uuid7
from app.core.security import (
    hash_password,
    hash_refresh_token,
    issue_access_token,
    new_refresh_token,
    verify_password,
)
from app.models.identity import Employee, UserAccount, UserSession
from app.models.tenancy import Restaurant
from app.repositories.access import AccessRepository, ResolvedAccess
from app.repositories.account import UserAccountRepository, UserSessionRepository

logger = logging.getLogger(__name__)

# One message for every way a login can fail. Deliberately not parameterised: the moment it varies,
# it tells an attacker which addresses are real.
_REJECTED_CODE = "auth.invalid_credentials"
_REJECTED_MESSAGE = "Invalid login or password."

# Verified against when no account matches, so an unknown address costs the same time as a wrong
# password. Hashed once at import, not per request.
_DECOY_HASH = hash_password("a-password-nobody-has-and-nobody-needs-to-guess")


class InvalidCredentialsError(AppError):
    def __init__(self) -> None:
        super().__init__(_REJECTED_CODE, _REJECTED_MESSAGE, status_code=401)


@dataclass(frozen=True, slots=True)
class LoginResult:
    access_token: str
    refresh_token: str
    session_id: uuid.UUID
    employee: Employee
    restaurant: Restaurant
    permissions: frozenset[str]
    rank: int
    role_codes: tuple[str, ...]


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.accounts = UserAccountRepository(session)
        self.sessions = UserSessionRepository(session)
        self.access = AccessRepository(session)

    # ------------------------------------------------------------------ login

    async def login(
        self,
        identifier: str,
        password: str,
        *,
        ip_address: str | None = None,
        device_info: dict[str, object] | None = None,
    ) -> LoginResult:
        account = await self._find_account(identifier)

        if account is None:
            # Spend the time anyway. A fast rejection here is a timing oracle that undoes the
            # identical error message entirely.
            verify_password(password, _DECOY_HASH)
            raise InvalidCredentialsError

        self._reject_if_locked(account)

        if not verify_password(password, account.password_hash):
            await self._record_failure(account)
            raise InvalidCredentialsError

        if account.status != UserAccountStatus.ACTIVE:
            # Checked after the password so a suspended account is not distinguishable from a
            # wrong password by anyone who does not already know the password.
            raise InvalidCredentialsError

        await self._record_success(account)
        employee = await self._employee_for(account)
        restaurant = await self._home_restaurant(employee)
        resolved = await self.access.resolve(employee.id, restaurant.id)
        return await self._start_session(
            account, employee, restaurant, resolved, ip_address, device_info
        )

    async def _find_account(self, identifier: str) -> UserAccount | None:
        """Resolved across organizations, because the login form asks for an identifier and not a
        tenant, and month 1 has no subdomain per restaurant.

        This does not leak: every failure below returns the same thing. An identifier that matches
        in two organizations is refused the same way — safe, and rare enough that the fix is
        backlogged rather than built (docs/backlog.md).
        """
        normalised = identifier.strip().lower()
        matches = (
            await self.session.scalars(
                select(UserAccount).where(
                    (UserAccount.email == normalised) | (UserAccount.phone == identifier.strip())
                )
            )
        ).all()
        if len(matches) > 1:
            logger.warning("auth.ambiguous_identifier", extra={"match_count": len(matches)})
            return None
        return matches[0] if matches else None

    def _reject_if_locked(self, account: UserAccount) -> None:
        if account.locked_until is None or account.locked_until <= datetime.now(UTC):
            return
        remaining = account.locked_until - datetime.now(UTC)
        minutes = max(1, round(remaining.total_seconds() / 60))
        # A distinct code here, because being locked out is something the person needs to
        # understand — and it is only reachable by someone who already knows the address exists.
        raise AppError(
            "auth.locked",
            f"Too many failed attempts. Try again in about {minutes} minute"
            f"{'s' if minutes != 1 else ''}, or ask an owner to unlock it.",
            {"retry_after_minutes": minutes},
            status_code=429,
        )

    async def _record_failure(self, account: UserAccount) -> None:
        settings = get_settings()
        account.failed_attempts += 1
        if account.failed_attempts >= settings.lockout_threshold:
            account.locked_until = datetime.now(UTC) + timedelta(minutes=settings.lockout_minutes)
            logger.warning("auth.account_locked", extra={"account_id": str(account.id)})
        await self.session.flush()

    async def _record_success(self, account: UserAccount) -> None:
        # Cleared, so yesterday's four typos plus today's one do not lock someone out mid-service.
        account.failed_attempts = 0
        account.locked_until = None
        account.last_login_at = datetime.now(UTC)
        await self.session.flush()

    async def _employee_for(self, account: UserAccount) -> Employee:
        employee = (
            await self.session.scalars(
                select(Employee).where(Employee.user_account_id == account.id)
            )
        ).first()
        if employee is None or not employee.is_active:
            # A dismissed person keeps their user_account row so history stays intact, so
            # employment is what decides whether they may sign in.
            raise InvalidCredentialsError
        return employee

    async def _home_restaurant(self, employee: Employee) -> Restaurant:
        restaurant_ids = await self.access.restaurants_for_employee(employee.id)
        if not restaurant_ids:
            # Past authentication, so naming the real reason leaks nothing and saves a support
            # call. This happens whenever a manager creates staff before roles are assigned.
            raise AppError(
                "auth.no_restaurant",
                "Your account is not set up for any restaurant yet. Ask your manager to assign "
                "you a role.",
                status_code=403,
            )
        restaurant = await self.session.get(Restaurant, restaurant_ids[0])
        if restaurant is None or not restaurant.is_active:
            raise AppError(
                "auth.no_restaurant",
                "Your restaurant is not active. Ask the owner to check the account.",
                status_code=403,
            )
        return restaurant

    async def _start_session(
        self,
        account: UserAccount,
        employee: Employee,
        restaurant: Restaurant,
        resolved: ResolvedAccess,
        ip_address: str | None,
        device_info: dict[str, object] | None,
        family_id: uuid.UUID | None = None,
    ) -> LoginResult:
        settings = get_settings()
        raw_token, token_hash = new_refresh_token()
        session_row = UserSession(
            user_account_id=account.id,
            refresh_token_hash=token_hash,
            # A new login starts a new family; a refresh continues the existing one.
            family_id=family_id or uuid7(),
            device_info=device_info,
            ip_address=ip_address,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
        )
        self.session.add(session_row)
        await self.session.flush()

        permissions = resolved.permissions
        access_token = issue_access_token(
            employee_id=str(employee.id),
            organization_id=str(employee.organization_id),
            restaurant_id=str(restaurant.id),
            permissions=sorted(permissions),
        )
        return LoginResult(
            access_token=access_token,
            refresh_token=raw_token,
            session_id=session_row.id,
            employee=employee,
            restaurant=restaurant,
            permissions=permissions,
            rank=resolved.rank,
            role_codes=resolved.role_codes,
        )

    # ---------------------------------------------------------------- refresh

    async def refresh(self, raw_token: str, *, ip_address: str | None = None) -> LoginResult:
        """Rotate the token, and re-check everything that may have changed since login.

        This is where deactivation, suspension and role changes actually take effect, because the
        access token they would otherwise have to invalidate cannot be recalled.
        """
        token_hash = hash_refresh_token(raw_token)
        live = await self.sessions.find_live_by_hash(token_hash)

        if live is None:
            await self._handle_replay(token_hash)
            raise AppError("auth.session_invalid", "Please sign in again.", status_code=401)

        account = await self.accounts.get(live.user_account_id)
        if account is None or account.status != UserAccountStatus.ACTIVE:
            raise AppError("auth.session_invalid", "Please sign in again.", status_code=401)

        employee = await self._employee_for(account)
        restaurant = await self._home_restaurant(employee)
        resolved = await self.access.resolve(employee.id, restaurant.id)

        # Retire the presented token before issuing its replacement, so the two never overlap.
        live.revoked_at = datetime.now(UTC)
        await self.session.flush()

        return await self._start_session(
            account, employee, restaurant, resolved, ip_address, live.device_info, live.family_id
        )

    async def _handle_replay(self, token_hash: str) -> None:
        """A token we have seen before but retired is the signature of theft.

        Two parties now hold tokens descended from one login and only one of them is the real
        owner, so the whole family dies and both are forced back to a password. Losing a session
        is a small cost; leaving a stolen one alive is not.
        """
        known = await self.sessions.find_any_by_hash(token_hash)
        if known is None:
            return
        revoked = await self.sessions.revoke_family(known.family_id)
        logger.warning(
            "auth.refresh_token_replayed",
            extra={"family_id": str(known.family_id), "sessions_revoked": revoked},
        )

    # ----------------------------------------------------------------- logout

    async def logout(self, raw_token: str) -> None:
        """Idempotent. The browser retries and the network drops; a second logout must not be an
        error while someone is doing the safe thing."""
        live = await self.sessions.find_live_by_hash(hash_refresh_token(raw_token))
        if live is None:
            return
        live.revoked_at = datetime.now(UTC)
        await self.session.flush()

    # ------------------------------------------------------- password change

    async def change_own_password(
        self,
        employee: Employee,
        current_session_id: uuid.UUID | None,
        current_password: str,
        new_password: str,
    ) -> None:
        """Acceptance criterion 5: every other session dies, this one survives.

        The reason to change a password is usually that somebody else might have it, so leaving
        their session alive would make the change pointless. Killing the current one would sign the
        person out of the screen they just used, which teaches them not to do it again.
        """
        if employee.user_account_id is None:
            raise AppError("auth.no_login", "This employee has no login.", status_code=400)
        account = await self.accounts.get(employee.user_account_id)
        if account is None:
            raise AppError("auth.no_login", "This employee has no login.", status_code=400)

        if not verify_password(current_password, account.password_hash):
            raise AppError(
                "auth.current_password_wrong",
                "Your current password is not correct.",
                status_code=400,
            )

        account.password_hash = hash_password(new_password)
        await self.session.flush()
        await self.sessions.revoke_all_for_account(account.id, except_session_id=current_session_id)
        await self.session.flush()
