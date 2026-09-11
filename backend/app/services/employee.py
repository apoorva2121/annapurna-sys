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

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import EmploymentType, UserAccountStatus
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.permissions import may_assign_rank
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.audit import AuditLog
from app.models.identity import Employee, UserAccount
from app.repositories.access import AccessRepository
from app.repositories.account import UserSessionRepository
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


class EmployeeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.access = AccessRepository(session)
        self.sessions = UserSessionRepository(session)

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

        await self._audit(
            actor,
            "employee.create",
            employee.id,
            None,
            {
                "full_name": employee.full_name,
                "employee_code": employee.employee_code,
                "has_login": account_id is not None,
            },
        )
        return employee

    async def _reject_duplicate_code(self, actor: Actor, employee_code: str) -> None:
        # Caught here so the caller gets a readable message rather than a database constraint
        # error rendered as a 500.
        existing = (
            await self.session.scalars(
                select(Employee).where(
                    Employee.organization_id == actor.organization_id,
                    Employee.employee_code == employee_code.strip(),
                )
            )
        ).first()
        if existing is not None:
            raise ConflictError(
                "employee.code_taken",
                f"Employee code {employee_code} is already in use.",
            )

    async def _create_login(self, actor: Actor, identifier: str, password: str | None) -> uuid.UUID:
        identifier = identifier.strip()
        is_email = "@" in identifier
        email = identifier.lower() if is_email else None
        phone = None if is_email else identifier

        clash = (
            await self.session.scalars(
                select(UserAccount).where(
                    UserAccount.organization_id == actor.organization_id,
                    (UserAccount.email == email) if is_email else (UserAccount.phone == phone),
                )
            )
        ).first()
        if clash is not None:
            raise ConflictError(
                "employee.login_taken", "That phone number or email is already in use."
            )

        account = UserAccount(
            organization_id=actor.organization_id,
            email=email,
            phone=phone,
            password_hash=hash_password(password) if password else None,
            # No password yet means invited, not active: the account exists and cannot be signed
            # in to until someone sets one.
            status=UserAccountStatus.ACTIVE if password else UserAccountStatus.INVITED,
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

        before = {field: getattr(employee, field) for field in changes}
        for field, value in changes.items():
            setattr(employee, field, value)
        await self.session.flush()

        await self._audit(
            actor, "employee.update", employee.id, _jsonable(before), _jsonable(changes)
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

        await self._audit(
            actor,
            "employee.deactivate",
            employee.id,
            {"is_active": True},
            {"is_active": False, "sessions_revoked": revoked},
        )
        return employee

    async def reactivate_employee(self, actor: Actor, employee_id: uuid.UUID) -> Employee:
        employee = await self._repository(actor).get_for_update(employee_id)
        if employee is None:
            raise _not_found()
        employee.is_active = True
        employee.deactivated_at = None
        await self.session.flush()
        await self._audit(
            actor, "employee.reactivate", employee.id, {"is_active": False}, {"is_active": True}
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
        await self._audit(
            actor,
            "employee.role.assign",
            employee.id,
            {"roles": list(before.role_codes)},
            {"roles": list(after.role_codes)},
        )
        return after.role_codes

    async def _load_roles(self, actor: Actor, role_ids: Sequence[uuid.UUID]) -> list[Role]:
        if not role_ids:
            return []
        roles = (
            await self.session.scalars(
                select(Role).where(
                    Role.id.in_(list(role_ids)),
                    # A role belongs either to this organization or to the system templates.
                    # Without this, one tenant could assign another tenant's custom role.
                    (Role.organization_id == actor.organization_id)
                    | (Role.organization_id.is_(None)),
                )
            )
        ).all()
        if len(roles) != len(set(role_ids)):
            raise NotFoundError("role.not_found", "One of those roles does not exist.")
        return list(roles)

    async def _rank_of(self, employee: Employee, actor: Actor) -> int:
        resolved = await self.access.resolve(employee.id, actor.restaurant_id)
        return resolved.rank

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
        self._reject_if_more_senior(actor, await self._rank_of(employee, actor))

        if employee.user_account_id is None:
            raise AppError(
                "employee.no_login", "That employee does not have a login.", status_code=400
            )
        account = await self.session.get(UserAccount, employee.user_account_id)
        if account is None:
            raise AppError(
                "employee.no_login", "That employee does not have a login.", status_code=400
            )

        account.password_hash = hash_password(new_password)
        account.status = UserAccountStatus.ACTIVE
        # A reset also clears a lockout — otherwise the fix for "I am locked out" does not fix it.
        account.failed_attempts = 0
        account.locked_until = None
        await self.session.flush()
        revoked = await self.sessions.revoke_all_for_account(account.id)
        await self.session.flush()

        await self._audit(
            actor,
            "employee.password.reset",
            employee.id,
            None,
            {"sessions_revoked": revoked},
        )

    # ------------------------------------------------------------------- audit

    async def _audit(
        self,
        actor: Actor,
        action: str,
        entity_id: uuid.UUID,
        old_value: dict[str, object] | None,
        new_value: dict[str, object] | None,
    ) -> None:
        """Append-only, and never carries a credential.

        The redaction is at the call site rather than in the writer, because this table is readable
        by anyone holding the audit permission — a password hash landing here would be a leak with
        a long tail.
        """
        self.session.add(
            AuditLog(
                restaurant_id=actor.restaurant_id,
                actor_employee_id=actor.employee_id,
                action=action,
                entity_type="employee",
                entity_id=entity_id,
                old_value=old_value,
                new_value=new_value,
                occurred_at=datetime.now(UTC),
            )
        )
        await self.session.flush()


def _jsonable(values: dict[str, object]) -> dict[str, object]:
    """dates and enums do not survive a jsonb round trip on their own."""
    return {
        key: (value.isoformat() if isinstance(value, date | datetime) else str(value))
        if value is not None
        else None
        for key, value in values.items()
    }
