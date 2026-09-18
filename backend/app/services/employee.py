"""Employee lifecycle: create, edit, deactivate, and who may appoint whom.

Two rules in this file are security controls rather than business logic, and both exist because
`employee.role.assign` is held by managers:

1. **Nobody edits their own roles.** Closes the direct route to self-promotion.
2. **Nobody grants a role more senior than their own.** Closes the indirect route — promoting an
   ally who then promotes you back.

Neither can be expressed as a permission, because in M01 a manager and an owner hold the same seven
permissions. Seniority lives in `role.rank`, and these are the only two places it is consulted.

Every change that alters what someone can do writes an `audit_log` row. That is what makes the
owner-visibility promise real: the event exists from the moment it happens, and M14 turns it into
a notification without M01 having to change.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.audit import record
from app.core.enums import EmploymentType, UserAccountStatus
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.identifiers import normalise_identifier
from app.core.permissions import may_assign_rank, may_reset_password
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee, UserAccount
from app.repositories.access import AccessRepository
from app.repositories.account import UserAccountRepository, UserSessionRepository
from app.repositories.employee import EmployeeRepository


@dataclass(frozen=True, slots=True)
class NewEmployee:
    full_name: str
    employee_code: str
    joined_on: date
    employment_type: EmploymentType
    phone: str | None = None
    date_of_birth: date | None = None
    login_identifier: str | None = None
    initial_password: str | None = None


def _not_found() -> NotFoundError:
    """One shape for "outside your scope" and "does not exist".

    Distinguishing them would confirm which ids are real, which is a slower version of the leak
    tenant scoping exists to prevent (manual test D1).
    """
    return NotFoundError("employee.not_found", "That employee was not found.")


# `EMP017`, `E000`, `K7`: letters then digits.
_CODE_SHAPE = re.compile(r"^([A-Za-z]*)(\d+)$")


def next_employee_code(existing: Iterable[str]) -> str:
    """The next free code in the organization's own style (decision D19, backlog-issues B12).

    The prefix most codes use, one past the highest number with it, padded to the widest such number
    — `EMP017` → `EMP018`. `EMP001` when nothing is numbered yet. A suggestion only: the unique
    constraint still decides, and a person may type another."""
    codes = [code.strip() for code in existing]
    shaped = [match for code in codes if (match := _CODE_SHAPE.match(code))]
    if not shaped:
        return "EMP001"
    prefix = Counter(match.group(1) for match in shaped).most_common(1)[0][0]
    same = [match for match in shaped if match.group(1) == prefix]
    width = max(len(match.group(2)) for match in same)
    taken = {code.upper() for code in codes}
    number = max(int(match.group(2)) for match in same) + 1
    while f"{prefix}{number:0{width}d}".upper() in taken:
        number += 1
    return f"{prefix}{number:0{width}d}"


class EmployeeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.access = AccessRepository(session)
        self.sessions = UserSessionRepository(session)
        self.accounts = UserAccountRepository(session)

    def _repository(self, actor: Actor) -> EmployeeRepository:
        return EmployeeRepository(self.session, actor.scope)

    # -------------------------------------------------------------------- read

    async def list_employees(
        self,
        actor: Actor,
        *,
        is_active: bool | None = True,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[Employee]:
        return await self._repository(actor).list_visible(
            is_active=is_active, limit=limit, after=after
        )

    async def get_employee(self, actor: Actor, employee_id: uuid.UUID) -> Employee:
        employee = await self._repository(actor).get(employee_id)
        if employee is None:
            raise _not_found()
        return employee

    async def roles_of(self, employee_id: uuid.UUID, restaurant_id: uuid.UUID) -> list[str]:
        resolved = await self.access.resolve(employee_id, restaurant_id)
        return list(resolved.role_codes)

    async def roles_of_many(
        self, employees: Sequence[Employee], restaurant_id: uuid.UUID
    ) -> dict[uuid.UUID, list[str]]:
        """The list-endpoint counterpart to `roles_of`. One query for the whole page."""
        return await self.access.roles_for_employees(
            [employee.id for employee in employees], restaurant_id
        )

    # ------------------------------------------------------------------ create

    async def create_employee(self, actor: Actor, data: NewEmployee) -> Employee:
        """Creates the person, and optionally a login. Never a role.

        Role assignment is a separate, separately-permissioned call. Folding it in here would let
        anyone holding `employee.create` grant roles as a side effect, which would make the
        seniority ladder trivially bypassable.
        """
        await self._reject_duplicate_code(actor, data.employee_code)

        account_id: uuid.UUID | None = None
        if data.login_identifier:
            account_id = await self._create_login(
                actor, data.login_identifier, data.initial_password
            )

        employee = Employee(
            organization_id=actor.organization_id,
            user_account_id=account_id,
            employee_code=data.employee_code.strip(),
            full_name=data.full_name.strip(),
            phone=data.phone,
            date_of_birth=data.date_of_birth,
            joined_on=data.joined_on,
            employment_type=data.employment_type,
        )
        self.session.add(employee)
        await self.session.flush()

        record(
            self.session,
            actor,
            action="employee.create",
            entity="employee",
            entity_id=employee.id,
            new={
                "full_name": employee.full_name,
                "employee_code": employee.employee_code,
                "has_login": account_id is not None,
            },
        )
        return employee

    async def next_code(self, actor: Actor) -> str:
        """The code the add-employee form fills in (D19)."""
        return next_employee_code(await self._repository(actor).codes())

    async def _reject_duplicate_code(self, actor: Actor, employee_code: str) -> None:
        # Caught here so the caller gets a readable message rather than a database constraint
        # error rendered as a 500.
        if await self._repository(actor).code_exists(employee_code):
            raise ConflictError(
                "employee.code_taken",
                f"Employee code {employee_code} is already in use.",
            )

    async def _create_login(self, actor: Actor, identifier: str, password: str | None) -> uuid.UUID:
        identifier = normalise_identifier(identifier)
        is_email = "@" in identifier
        email = identifier if is_email else None
        phone = None if is_email else identifier

        # Unique inside this organization (backlog-issues B4, decision D1). Another organization may
        # hold the same login: sign-in matches the password first and asks which organization only
        # when it opens more than one, so a second holder takes nothing from the first. The unique
        # constraint is the guarantee; this check is the sentence a manager reads. The message
        # never says who holds it.
        if await self.accounts.identifier_taken_in(actor.organization_id, identifier):
            raise ConflictError(
                "employee.login_taken", "That phone number or email is already in use."
            )

        account = UserAccount(
            organization_id=actor.organization_id,
            email=email,
            phone=phone,
            password_hash=await hash_password(password) if password else None,
            # No password yet means invited, not active: the account exists and cannot be signed
            # in to until someone sets one.
            status=UserAccountStatus.ACTIVE if password else UserAccountStatus.INVITED,
            # Somebody else chose this password, so the same rule as a reset applies: the person
            # changes it the first time they sign in, and until they do, anything done with the
            # account is attributed to them while the creator still knows the credential.
            # Conditional, not unconditional — an invited account has no password to change, and
            # flagging it would demand a change nobody can make.
            password_reset_required=password is not None,
        )
        self.session.add(account)
        await self.session.flush()
        return account.id

    # ------------------------------------------------------------------ update

    async def update_employee(
        self, actor: Actor, employee_id: uuid.UUID, changes: dict[str, object]
    ) -> Employee:
        employee = await self._repository(actor).get_for_update(employee_id)
        if employee is None:
            raise _not_found()
        # P1-6: this had no seniority check at all. A name and a phone number are not harmless —
        # the name prints on a bill and the number is how a supplier reaches that person.
        self._reject_if_more_senior(actor, await self._rank_of(employee, actor))

        before = {field: getattr(employee, field) for field in changes}
        for field, value in changes.items():
            setattr(employee, field, value)
        await self.session.flush()

        record(
            self.session,
            actor,
            action="employee.update",
            entity="employee",
            entity_id=employee.id,
            old=_jsonable(before),
            new=_jsonable(changes),
        )
        return employee

    # ------------------------------------------------------- activate/deactivate

    async def deactivate_employee(self, actor: Actor, employee_id: uuid.UUID) -> Employee:
        """Acceptance criterion 4: every session dies in the same transaction as the flag flips.

        One action, not three. If revocation were a separate call, the window between them would
        be exactly when a dismissed employee is most motivated to use it.
        """
        employee = await self._repository(actor).get_for_update(employee_id)
        if employee is None:
            raise _not_found()
        if employee.id == actor.employee_id:
            # Locking yourself out mid-service is never the intent, and it can leave a restaurant
            # with nobody able to sign in.
            raise AppError(
                "employee.cannot_deactivate_self",
                "You cannot deactivate your own account.",
                status_code=400,
            )
        self._reject_if_more_senior(actor, await self._rank_of(employee, actor))

        employee.is_active = False
        employee.deactivated_at = datetime.now(UTC)
        revoked = 0
        if employee.user_account_id is not None:
            revoked = await self.sessions.revoke_all_for_account(employee.user_account_id)
        await self.session.flush()

        record(
            self.session,
            actor,
            action="employee.deactivate",
            entity="employee",
            entity_id=employee.id,
            old={"is_active": True},
            new={"is_active": False, "sessions_revoked": revoked},
        )
        return employee

    async def reactivate_employee(self, actor: Actor, employee_id: uuid.UUID) -> Employee:
        employee = await self._repository(actor).get_for_update(employee_id)
        if employee is None:
            raise _not_found()
        # The same guard deactivation uses. Without it a manager can undo an owner's offboarding
        # decision — not an escalation by itself, since the sessions stay revoked, but it is
        # attacker 1 and 4 in docs/security.md getting a dismissed colleague back on the payroll.
        self._reject_if_more_senior(actor, await self._rank_of(employee, actor))

        employee.is_active = True
        employee.deactivated_at = None
        await self.session.flush()
        record(
            self.session,
            actor,
            action="employee.reactivate",
            entity="employee",
            entity_id=employee.id,
            old={"is_active": False},
            new={"is_active": True},
        )
        return employee

    # ------------------------------------------------------------------- roles

    async def set_roles(
        self, actor: Actor, employee_id: uuid.UUID, role_ids: Sequence[uuid.UUID]
    ) -> Sequence[str]:
        """The escalation-sensitive path. Both guards live here.

        Sessions are revoked afterwards because a permission change must not wait for a token to
        expire — someone demoted keeps their old permissions for up to the access-token lifetime
        otherwise.
        """
        if employee_id == actor.employee_id:
            raise PermissionDeniedError(
                "employee.cannot_change_own_roles",
                "You cannot change your own roles. Ask someone more senior.",
            )

        employee = await self._repository(actor).get_for_update(employee_id)
        if employee is None:
            raise _not_found()
        # Judged organization-wide, before anything is deleted (P1-2). The per-assignment check
        # below only ever saw the roles held *at this branch*, so a branch manager could strip the
        # junior role a senior person happened to hold there — and, because the loop deletes as it
        # goes, the deletion happened before anything noticed who they really were.
        self._reject_if_more_senior(actor, await self._rank_of(employee, actor))

        roles = await self._load_roles(actor, role_ids)
        for role in roles:
            if not may_assign_rank(actor.rank, role.rank):
                raise PermissionDeniedError(
                    "employee.role_too_senior",
                    f"You cannot grant the {role.name} role, because it is more senior than yours.",
                )

        before = await self.access.resolve(employee.id, actor.restaurant_id)
        existing = await self.access.assignments_at(employee.id, actor.restaurant_id)
        # Guard the other direction too: someone junior must not be able to strip a senior
        # person's roles, which would be a denial of service against the owner.
        for assignment in existing:
            held = await self.access.get_role(assignment.role_id)
            if held is not None and not may_assign_rank(actor.rank, held.rank):
                raise PermissionDeniedError(
                    "employee.role_too_senior",
                    "You cannot change the roles of someone more senior than you.",
                )
            await self.session.delete(assignment)
        await self.session.flush()

        for role in roles:
            self.session.add(
                EmployeeRoleAssignment(
                    employee_id=employee.id,
                    restaurant_id=actor.restaurant_id,
                    role_id=role.id,
                    assigned_by=actor.employee_id,
                )
            )
        await self.session.flush()

        if employee.user_account_id is not None:
            await self.sessions.revoke_all_for_account(employee.user_account_id)

        after = await self.access.resolve(employee.id, actor.restaurant_id)
        record(
            self.session,
            actor,
            action="employee.role.assign",
            entity="employee",
            entity_id=employee.id,
            old={"roles": list(before.role_codes)},
            new={"roles": list(after.role_codes)},
        )
        return after.role_codes

    async def _load_roles(self, actor: Actor, role_ids: Sequence[uuid.UUID]) -> list[Role]:
        if not role_ids:
            return []
        # Scoped in the repository: a role belongs either to this organization or to the system
        # templates, and without that filter one tenant could assign another tenant's custom role.
        roles = await self.access.roles_available_to(role_ids, actor.organization_id)
        if len(roles) != len(set(role_ids)):
            raise NotFoundError("role.not_found", "One of those roles does not exist.")
        return list(roles)

    async def _rank_of(self, employee: Employee, actor: Actor) -> int:
        """Organization-wide, never branch-local (P1-2, G-4).

        `actor` is no longer consulted and is kept only so the call sites read the same. Resolving
        the target's rank at the *actor's* restaurant is what let a branch manager take over anyone
        senior who also held a junior role at that branch.
        """
        _ = actor
        return await self.access.most_senior_rank_anywhere(employee.id)

    def _reject_if_more_senior(self, actor: Actor, target_rank: int) -> None:
        if not may_assign_rank(actor.rank, target_rank):
            raise PermissionDeniedError(
                "employee.more_senior",
                "You cannot change someone more senior than you.",
            )

    # ---------------------------------------------------------------- password

    async def reset_password(self, actor: Actor, employee_id: uuid.UUID, new_password: str) -> None:
        """Resetting someone else's password. Ends every session they have.

        The seniority check matters here as much as for roles: without it, a manager could reset
        the owner's password and take the account.
        """
        employee = await self._repository(actor).get_for_update(employee_id)
        if employee is None:
            raise _not_found()
        if not may_reset_password(actor.rank, await self._rank_of(employee, actor)):
            # Stricter than every other guard here, because a password is not authority *over* a
            # person, it is the ability to *be* them (P1-6). See permissions.may_reset_password.
            raise PermissionDeniedError(
                "employee.more_senior",
                "You cannot set a password for this person. Ask someone more senior.",
            )

        if employee.user_account_id is None:
            raise AppError(
                "employee.no_login", "That employee does not have a login.", status_code=400
            )
        account = await self.session.get(UserAccount, employee.user_account_id)
        if account is None:
            raise AppError(
                "employee.no_login", "That employee does not have a login.", status_code=400
            )

        account.password_hash = await hash_password(new_password)
        account.status = UserAccountStatus.ACTIVE
        # Somebody else now knows this password. The flag ends that the first time the account's
        # real owner signs in and changes it (P1-6).
        account.password_reset_required = True
        # A reset also clears a lockout — otherwise the fix for "I am locked out" does not fix it.
        account.failed_attempts = 0
        account.locked_until = None
        await self.session.flush()
        revoked = await self.sessions.revoke_all_for_account(account.id)
        await self.session.flush()

        record(
            self.session,
            actor,
            action="employee.password.reset",
            entity="employee",
            entity_id=employee.id,
            new={"sessions_revoked": revoked},
        )

    # ------------------------------------------------------------------- audit


def _jsonable(values: dict[str, object]) -> dict[str, object]:
    """dates and enums do not survive a jsonb round trip on their own."""
    return {
        key: (value.isoformat() if isinstance(value, date | datetime) else str(value))
        if value is not None
        else None
        for key, value in values.items()
    }
