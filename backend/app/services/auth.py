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

import asyncio
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
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
from app.models.identity import Employee, SignInChoice, UserAccount, UserSession
from app.models.tenancy import Organization, Restaurant
from app.repositories.access import AccessRepository, ResolvedAccess
from app.repositories.account import (
    SignInChoiceRepository,
    UserAccountRepository,
    UserSessionRepository,
)
from app.repositories.employee import EmployeeRepository

logger = logging.getLogger(__name__)

# One message for every way a login can fail. Deliberately not parameterised: the moment it varies,
# it tells an attacker which addresses are real.
_REJECTED_CODE = "auth.invalid_credentials"
_REJECTED_MESSAGE = "Invalid login or password."

# How many branches `/auth/me` embeds (backlog-issues B3). It runs on every app load; the rest page
# from `GET /auth/restaurants`.
EMBEDDED_BRANCHES = 20

# How long the pass lasts when a password opens accounts in more than one organization (B4, D1a).
CHOICE_SECONDS = 120


@lru_cache
def _decoy_hash() -> str:
    """Verified against when no account matches, so an unknown identifier costs the same time as a
    wrong password.

    Computed on first use rather than at import: hashing at import time would make this module
    unimportable without a full Settings (breaking any tooling that merely reads the routing
    table) and would put an argon2 hash on the critical path of every process start.
    """
    return hash_password("a-password-nobody-has-and-nobody-needs-to-guess")


class InvalidCredentialsError(AppError):
    def __init__(self) -> None:
        super().__init__(_REJECTED_CODE, _REJECTED_MESSAGE, status_code=401)


def _no_longer_signed_in() -> AppError:
    """A valid token whose employee or restaurant no longer resolves — dismissed mid-session, or a
    restaurant deactivated under them. The same answer as never having signed in."""
    return AppError("auth.required", "Please sign in.", status_code=401)


@dataclass(frozen=True, slots=True)
class Profile:
    """What `GET /auth/me` answers, before it becomes a schema."""

    employee: Employee
    restaurant: Restaurant
    access: ResolvedAccess
    # Every branch this person holds a role at, including the current one. The client cannot offer a
    # switcher without it, and deriving the list in the browser would be a second implementation of
    # the rule the server already enforces at `POST /auth/switch`. At most `EMBEDDED_BRANCHES`,
    # always including the current one.
    restaurants: list[Restaurant]
    has_more_restaurants: bool = False


def _embedded(branches: list[Restaurant], current: Restaurant) -> list[Restaurant]:
    """The first twenty branches, always including the current one: the switcher shows it selected,
    and a list without it would render an empty control."""
    embedded = branches[:EMBEDDED_BRANCHES]
    if any(branch.id == current.id for branch in embedded):
        return embedded
    if all(branch.id != current.id for branch in branches):
        return embedded
    return [*embedded[: EMBEDDED_BRANCHES - 1], current]


class OrganizationChoiceNeeded(Exception):  # noqa: N818 - a signal, not a failure
    """The password opened accounts in more than one organization: ask which (B4, decision D1a).

    Raised rather than returned so `login` keeps one return type for its twenty callers; the route
    commits the pass and answers 200 with it. Not an `AppError`, because nothing went wrong.
    """

    def __init__(self, ticket: str, organizations: Sequence[Organization]) -> None:
        super().__init__("choose an organization")
        self.ticket = ticket
        self.organizations = list(organizations)
        self.expires_in_seconds = CHOICE_SECONDS


def _choice_expired() -> AppError:
    # One answer for a used pass, an expired pass, and an organization the pass never offered: the
    # screen's response to all three is the same — sign in again.
    return AppError(
        "auth.choice_expired", "That took too long. Please sign in again.", status_code=401
    )


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
    # True when somebody else set this password. The client routes to the change-password screen;
    # the server does not refuse the session, because a person who cannot sign in cannot change it.
    password_change_required: bool = False


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.accounts = UserAccountRepository(session)
        self.sessions = UserSessionRepository(session)
        self.choices = SignInChoiceRepository(session)
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
        matches = await self.accounts.find_all_by_identifier(identifier)
        if not matches:
            # Spend the time anyway. A fast rejection here is a timing oracle that undoes the
            # identical error message entirely.
            verify_password(password, _decoy_hash())
            raise InvalidCredentialsError
        if len(matches) == 1:
            return await self._sign_in(matches[0], password, ip_address, device_info)
        return await self._sign_in_one_of(matches, password, ip_address, device_info)

    async def _sign_in(
        self,
        account: UserAccount,
        password: str,
        ip_address: str | None,
        device_info: dict[str, object] | None,
    ) -> LoginResult:
        self._reject_if_locked(account)

        if not verify_password(password, account.password_hash):
            await self._record_failure(account)
            raise InvalidCredentialsError

        if account.status != UserAccountStatus.ACTIVE:
            # Checked after the password so a suspended account is not distinguishable from a
            # wrong password by anyone who does not already know the password.
            raise InvalidCredentialsError

        return await self._open_session(account, ip_address, device_info)

    async def _open_session(
        self,
        account: UserAccount,
        ip_address: str | None,
        device_info: dict[str, object] | None,
    ) -> LoginResult:
        await self._record_success(account)
        employee = await self._employee_for(account)
        restaurant = await self._home_restaurant(employee)
        resolved = await self.access.resolve(employee.id, restaurant.id)
        return await self._start_session(
            account, employee, restaurant, resolved, ip_address, device_info
        )

    async def _sign_in_one_of(
        self,
        matches: Sequence[UserAccount],
        password: str,
        ip_address: str | None,
        device_info: dict[str, object] | None,
    ) -> LoginResult:
        """One login held in more than one organization (backlog-issues B4, decision D1a).

        **The password decides first.** Only the accounts it opens — active, unlocked, and still
        employed — are considered, so another organization holding the same email changes nothing
        for its owner: the owner's password opens only the owner's account, and they go straight in.
        Only when it opens more than one does sign-in ask which, with a single-use two-minute pass.

        Two things accepted and recorded in the build log: every match costs a verification, so a
        login held in two organizations answers a little slower than one; and a wrong password
        against several accounts is not counted here — B5 counts attempts per login (decision D1d).
        """
        now = datetime.now(UTC)
        opened: list[UserAccount] = []
        for account in matches:
            # On a worker thread (G-6): one argon2 verification per match must not hold the event
            # loop, which every other request in the process is waiting on.
            matched = await asyncio.to_thread(verify_password, password, account.password_hash)
            usable_account = account.status == UserAccountStatus.ACTIVE and (
                account.locked_until is None or account.locked_until <= now
            )
            if matched and usable_account:
                opened.append(account)
        usable: list[UserAccount] = []
        for account in opened:
            employee = await self.accounts.employee_for(account.id)
            if employee is not None and employee.is_active:
                usable.append(account)
        if not usable:
            raise InvalidCredentialsError
        if len(usable) == 1:
            return await self._open_session(usable[0], ip_address, device_info)

        raw, token_hash = new_refresh_token()
        self.session.add(
            SignInChoice(
                token_hash=token_hash,
                account_ids=[account.id for account in usable],
                expires_at=now + timedelta(seconds=CHOICE_SECONDS),
            )
        )
        await self.session.flush()
        organizations = await self.accounts.organizations(
            [account.organization_id for account in usable]
        )
        raise OrganizationChoiceNeeded(raw, organizations)

    async def choose_organization(
        self,
        ticket: str,
        organization_id: uuid.UUID,
        *,
        ip_address: str | None = None,
        device_info: dict[str, object] | None = None,
    ) -> LoginResult:
        """The second step: sign in where the person chose, with the pass (B4, decision D1a).

        The pass is used in the statement that proves it unused and unexpired. An organization it
        never offered is refused the same way as an expired pass, and the refusal rolls back, so the
        pass stays usable for the right choice until it expires.
        """
        choice = await self.choices.claim(hash_refresh_token(ticket))
        if choice is None:
            raise _choice_expired()
        for account_id in choice.account_ids:
            account = await self.accounts.get(account_id)
            if (
                account is not None
                and account.organization_id == organization_id
                and account.status == UserAccountStatus.ACTIVE
            ):
                return await self._open_session(account, ip_address, device_info)
        raise _choice_expired()

    def _reject_if_locked(self, account: UserAccount) -> None:
        if account.locked_until is None or account.locked_until <= datetime.now(UTC):
            return
        remaining = account.locked_until - datetime.now(UTC)
        minutes = max(1, round(remaining.total_seconds() / 60))
        # A distinct code here, because being locked out is something the person needs to
        # understand and act on.
        #
        # It does cost something: this runs before the password is verified, so five wrong guesses
        # against a real identifier return 429 while an identifier that does not exist returns 401
        # — an enumeration oracle that the identical-failure work elsewhere in this file otherwise
        # closes. Accepted for now because the alternative is refusing to tell a locked-out person
        # why they cannot sign in, mid-service, which is worse for a restaurant. Recorded in
        # docs/backlog.md rather than left as a comment nobody revisits.
        raise AppError(
            "auth.locked",
            f"Too many failed attempts. Try again in about {minutes} minute"
            f"{'s' if minutes != 1 else ''}, or ask an owner to unlock it.",
            {"retry_after_minutes": minutes},
            status_code=429,
        )

    async def _record_failure(self, account: UserAccount) -> None:
        """The one write in this service that commits itself, and it has to.

        Everywhere else the API layer owns the transaction and commits on success. A failed login
        has no success: the caller raises `InvalidCredentialsError`, FastAPI tears the request
        down, and `get_session` closes the session without committing — taking this increment with
        it. The counter then never reaches the threshold, no matter how many attempts are made, and
        the lockout in `docs/security.md` silently does nothing. That is how this shipped, with a
        green test: the test drove the service inside one transaction it never rolled back, so a
        write that could not survive a request was still visible to the assertion that followed it.

        Committing here is safe because nothing else is pending — login only reads until this
        point — and because this record must outlive precisely the failure that produces it.

        **That safety is a precondition, not a property.** It holds only while `/login` writes
        nothing else before this line. G-11 plans an `audit_log` row for failed logins; when it
        lands, this commit stops meaning "only my counter" and the ordering of the two writes
        becomes load-bearing. Whoever adds it owns that decision.
        """
        settings = get_settings()
        account.failed_attempts += 1
        if account.failed_attempts >= settings.lockout_threshold:
            account.locked_until = datetime.now(UTC) + timedelta(minutes=settings.lockout_minutes)
            logger.warning("auth.account_locked", extra={"account_id": str(account.id)})
        await self.session.commit()

    async def _record_success(self, account: UserAccount) -> None:
        # Cleared, so yesterday's four typos plus today's one do not lock someone out mid-service.
        account.failed_attempts = 0
        account.locked_until = None
        account.last_login_at = datetime.now(UTC)
        await self.session.flush()

    async def _employee_for(self, account: UserAccount) -> Employee:
        employee = await self.accounts.employee_for(account.id)
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

    async def _restaurant_for_session(
        self, employee: Employee, remembered: uuid.UUID | None
    ) -> Restaurant:
        """Where this session is, re-checked rather than trusted.

        `user_session.restaurant_id` is a preference, not an authorisation. It is honoured only if
        the person still holds a role there — so a manager whose role at the second branch is
        removed while they are working there is returned to their home branch on the next refresh
        rather than kept somewhere they no longer belong. Falling back is safe in a way that raising
        is not: the alternative to a redirect would be a session that cannot refresh at all.
        """
        if remembered is None:
            return await self._home_restaurant(employee)
        allowed = await self.access.restaurants_for_employee(employee.id)
        if remembered not in set(allowed):
            return await self._home_restaurant(employee)
        restaurant = await self.session.get(Restaurant, remembered)
        if restaurant is None or not restaurant.is_active:
            return await self._home_restaurant(employee)
        return restaurant

    async def switch_restaurant(
        self, actor: Actor, restaurant_id: uuid.UUID, raw_refresh_token: str | None
    ) -> LoginResult:
        """Move this session to another branch the same person works at (finding S12).

        Refuses with **404 rather than 403** for a restaurant in another organization, for the same
        reason every scoped lookup in this product does: a 403 confirms the id names something real,
        and this is the one endpoint whose whole job is to change tenant scope.

        The two refusals are deliberately indistinguishable — "not yours" and "you do not work
        there" answer identically, so the endpoint cannot be used to enumerate the branches an
        organization has.

        Permissions are **re-resolved at the target**, never carried across. An owner at one branch
        who waits tables at another must arrive as a waiter; carrying the old set would be privilege
        escalation performed by navigating, with nothing in any log to suggest it happened.
        """
        employee = await EmployeeRepository(self.session, actor.scope).get_assigned_here(
            actor.employee_id
        )
        if employee is None:
            raise _no_longer_signed_in()

        allowed = set(await self.access.restaurants_for_employee(employee.id))
        restaurant = await self.session.get(Restaurant, restaurant_id)
        # The organization check is what makes this a tenant boundary rather than a preference.
        # `allowed` alone would already refuse another tenant's branch, but only because nobody is
        # assigned across organizations today — a structural check should not rest on that.
        if (
            restaurant is None
            or restaurant.organization_id != employee.organization_id
            or restaurant_id not in allowed
            or not restaurant.is_active
        ):
            raise AppError(
                "auth.restaurant_not_available",
                "You do not work at that restaurant.",
                status_code=404,
            )

        # Remembered on the session row, so the choice outlives the fifteen-minute token that made
        # it. Without this the next refresh returns the person to their home branch mid-task.
        # Matched by hash **and by account**. The cookie and the access token are two independent
        # inputs the caller supplies separately, so honouring a hash alone let someone present their
        # own token with another person's cookie and point that person's session at a branch of
        # their choosing. Contained downstream — `_restaurant_for_session` re-validates on the
        # victim's next refresh — but "authorise A, then write to B's row" is not a shape to leave
        # in the one endpoint whose job is changing tenant scope. Found by external review.
        #
        # A cookie that is not this person's is ignored rather than refused: it is a stale
        # credential, not something the caller can be told about, and the switch itself is already
        # authorised.
        if raw_refresh_token and employee.user_account_id is not None:
            live = await self.sessions.find_live_by_hash_for_account(
                hash_refresh_token(raw_refresh_token), employee.user_account_id
            )
            if live is not None:
                live.restaurant_id = restaurant_id
        await self.session.flush()

        resolved = await self.access.resolve(employee.id, restaurant_id)
        # **A new access token, scoped to the target.** This is the whole point: the client's
        # current token still names the old restaurant, and every later request is scoped by the
        # token rather than by anything the response body says. Returning only a profile would have
        # produced an endpoint that reports success and changes nothing.
        #
        # The *refresh* token is deliberately not rotated. This is the same session continuing, not
        # a new one — rotating here would end the family and log the person out of their other tabs
        # for having navigated.
        return LoginResult(
            access_token=issue_access_token(
                employee_id=str(employee.id),
                organization_id=str(employee.organization_id),
                restaurant_id=str(restaurant.id),
                permissions=sorted(resolved.permissions),
            ),
            refresh_token="",
            session_id=actor.session_id or uuid7(),
            employee=employee,
            restaurant=restaurant,
            permissions=resolved.permissions,
            rank=resolved.rank,
            role_codes=tuple(resolved.role_codes),
        )

    async def _restaurants_of(self, employee: Employee) -> list[Restaurant]:
        """Ordered as `restaurants_for_employee` orders them, so a switcher does not reshuffle.

        Two statements whatever the number of branches — the ids, then the rows — where this was a
        `session.get` per branch on the path every app load takes (backlog-issues B3).
        """
        ids = await self.access.restaurants_for_employee(employee.id)
        found = await self.access.active_restaurants(ids)
        return [found[restaurant_id] for restaurant_id in ids if restaurant_id in found]

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
            # Carried across every rotation, so the branch someone navigated to survives the
            # fifteen-minute token they navigated with.
            restaurant_id=restaurant.id,
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
            password_change_required=account.password_reset_required,
        )

    # ---------------------------------------------------------------- refresh

    async def refresh(self, raw_token: str, *, ip_address: str | None = None) -> LoginResult:
        """Rotate the token, and re-check everything that may have changed since login.

        This is where deactivation, suspension and role changes actually take effect, because the
        access token they would otherwise have to invalidate cannot be recalled.
        """
        token_hash = hash_refresh_token(raw_token)
        # Claimed, not read: the row is retired in the same statement that proves it was live, so
        # two refreshes presenting one token cannot both succeed. Read-then-write let both pass the
        # liveness check and mint a session each — which silently defeated the family-based theft
        # detection this table exists for. Found by external review.
        live = await self.sessions.claim_for_rotation(token_hash)

        if live is None:
            await self._handle_replay(token_hash)
            raise AppError("auth.session_invalid", "Please sign in again.", status_code=401)

        account = await self.accounts.get(live.user_account_id)
        if account is None or account.status != UserAccountStatus.ACTIVE:
            raise AppError("auth.session_invalid", "Please sign in again.", status_code=401)

        employee = await self._employee_for(account)
        restaurant = await self._restaurant_for_session(employee, live.restaurant_id)
        resolved = await self.access.resolve(employee.id, restaurant.id)

        # Already retired by `claim_for_rotation` above, in the same statement that proved it live.
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
        # Committed here, like the failure counter, and for the same reason (G-1): the caller is
        # about to raise 401 and the route will never reach its own commit, so without this the
        # revocation is rolled back by the very response that reports it.
        #
        # Safe only while `/refresh` has written nothing else by this point — currently true, and a
        # precondition rather than a property. See `_record_failure` for the same note.
        #
        # The consequence of getting this wrong is backwards, which is what made it easy to miss:
        # the thief who presents the stolen token *first* is handed a working session, while the
        # only person inconvenienced is the real owner, whose next refresh is refused. The whole
        # point of killing the family is that neither party keeps a session.
        await self.session.commit()
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

    # ------------------------------------------------------------------- me

    async def profile(self, actor: Actor) -> Profile:
        """Everything the client needs to render permission-aware navigation.

        The actor already carries most of this, but it is rebuilt from the database rather than
        trusted: `permissions` on the token is a snapshot, and a role changed a minute ago must not
        keep working until the token expires.
        """
        employee = await EmployeeRepository(self.session, actor.scope).get_assigned_here(
            actor.employee_id
        )
        if employee is None:
            raise _no_longer_signed_in()
        restaurant = await self.session.get(Restaurant, actor.restaurant_id)
        if restaurant is None:
            raise _no_longer_signed_in()
        resolved = await self.access.resolve(actor.employee_id, actor.restaurant_id)
        branches = await self._restaurants_of(employee)
        embedded = _embedded(branches, restaurant)
        return Profile(
            employee=employee,
            restaurant=restaurant,
            access=resolved,
            restaurants=embedded,
            has_more_restaurants=len(branches) > len(embedded),
        )

    async def branches(
        self, actor: Actor, *, limit: int, after: uuid.UUID | None
    ) -> tuple[list[Restaurant], uuid.UUID | None]:
        """Every branch this person may switch to, a page at a time, in the order `/auth/me` embeds
        them (backlog-issues B3). The cursor is the last branch's id; an unknown one ends the list
        rather than restarting it."""
        employee = await EmployeeRepository(self.session, actor.scope).get_assigned_here(
            actor.employee_id
        )
        if employee is None:
            raise _no_longer_signed_in()
        ordered = await self._restaurants_of(employee)
        ids = [restaurant.id for restaurant in ordered]
        start = 0 if after is None else (ids.index(after) + 1 if after in ids else len(ids))
        page = ordered[start : start + limit]
        more = start + len(page) < len(ordered)
        return page, (page[-1].id if more and page else None)

    async def session_id_for_token(self, raw_token: str | None) -> uuid.UUID | None:
        """Which session a presented refresh token belongs to, if it is still live.

        Used to spare the caller's own session when a password change revokes the others. None is
        an ordinary answer: a native client that holds no cookie simply loses every session,
        including its own, which is safe rather than convenient.
        """
        if not raw_token:
            return None
        row = await self.sessions.find_live_by_hash(hash_refresh_token(raw_token))
        return row.id if row else None

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
        # Whatever anyone else knew is now stale, so the requirement is satisfied.
        account.password_reset_required = False
        await self.session.flush()
        await self.sessions.revoke_all_for_account(account.id, except_session_id=current_session_id)
        await self.session.flush()
