"""Employee queries, scoped at both levels.

The visibility rule here is the security-critical part of M01, so it is written once, in one place,
and every read goes through it:

    an employee is visible when they belong to this organization
    AND (they hold a role at this restaurant OR they hold no role anywhere yet)

The organization clause is the hard tenant boundary. The assignment clause is the branch boundary
from the threat table. The "no role anywhere yet" exception exists because a manager may create
staff but not assign roles (the approved permission matrix), which leaves a real window where a
person belongs to no restaurant — and without the exception, the employee a manager just created
would be invisible to that manager.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, exists, select

from app.models.access import EmployeeRoleAssignment
from app.models.identity import Employee
from app.repositories.base import OrgScopedRepository, page_size


class EmployeeRepository(OrgScopedRepository[Employee]):
    model = Employee

    def _visible(self) -> Select[tuple[Employee]]:
        """The one definition of "this restaurant's staff". Everything else calls this."""
        assigned_here = exists(
            select(EmployeeRoleAssignment.id).where(
                EmployeeRoleAssignment.employee_id == Employee.id,
                EmployeeRoleAssignment.restaurant_id == self.scope.restaurant_id,
            )
        )
        assigned_anywhere = exists(
            select(EmployeeRoleAssignment.id).where(
                EmployeeRoleAssignment.employee_id == Employee.id
            )
        )
        # EXISTS rather than a JOIN: a join against a person holding three roles here returns them
        # three times, and the staff list showing one person repeatedly reads as a data bug.
        return self.scoped().where(assigned_here | ~assigned_anywhere)

    async def list_visible(
        self,
        *,
        is_active: bool | None = True,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[Employee]:
        """`is_active=None` includes deactivated staff, who are never deleted (ADR 0008).

        Paged by id rather than OFFSET: uuid7 sorts in creation order, so the primary key is a
        valid cursor and pagination stays stable while rows are being inserted.
        """
        query = self._visible()
        if is_active is not None:
            query = query.where(Employee.is_active.is_(is_active))
        if after is not None:
            query = query.where(Employee.id > after)
        query = query.order_by(Employee.id).limit(page_size(limit))
        return (await self.session.scalars(query)).all()

    async def get(self, employee_id: uuid.UUID) -> Employee | None:
        """None, never an exception, for anything outside the scope.

        The caller turns this into a 404. Returning 403 for a real id belonging to another tenant
        and 404 for one that does not exist would confirm which ids are real — a slower version of
        the leak this method exists to prevent.
        """
        result = await self.session.scalars(self._visible().where(Employee.id == employee_id))
        return result.first()

    async def get_for_update(self, employee_id: uuid.UUID) -> Employee | None:
        """Scoped exactly like `get`, and separate only so the intent is visible at the call site.

        Scoping reads but not writes is the version of this bug that survives review, because the
        read path is the one everybody tests.
        """
        result = await self.session.scalars(
            self._visible().where(Employee.id == employee_id).with_for_update()
        )
        return result.first()

    async def get_by_user_account(self, user_account_id: uuid.UUID) -> Employee | None:
        """Used at login, before a restaurant is known, so it scopes by organization only."""
        result = await self.session.scalars(
            self.scoped().where(Employee.user_account_id == user_account_id)
        )
        return result.first()

    async def code_exists(self, employee_code: str) -> bool:
        """Whether this organization already employs someone with this code.

        Asked before an insert so the caller can answer with a readable conflict rather than let a
        unique constraint surface as a 500. The database is still the authority — this is a better
        message, not the guarantee.
        """
        existing = await self.session.scalars(
            self.scoped().where(Employee.employee_code == employee_code.strip())
        )
        return existing.first() is not None

    async def get_assigned_here(self, employee_id: uuid.UUID) -> Employee | None:
        """The stricter lookup, used to rebuild the actor from a token on every request.

        Unlike `get`, this has no "unassigned employees are visible" exception. That exception
        exists so a manager can see the person they just created; extending it to the actor path
        would mean an employee with no role anywhere could act at any restaurant in the
        organization. They would resolve to zero permissions and be refused anyway, but a
        structural rule beats relying on a downstream check.
        """
        assigned_here = exists(
            select(EmployeeRoleAssignment.id).where(
                EmployeeRoleAssignment.employee_id == Employee.id,
                EmployeeRoleAssignment.restaurant_id == self.scope.restaurant_id,
            )
        )
        result = await self.session.scalars(
            self.scoped().where(Employee.id == employee_id, assigned_here)
        )
        return result.first()
