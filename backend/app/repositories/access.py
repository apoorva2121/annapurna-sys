"""Resolving what someone may actually do.

This is the query behind `require_permission()`, so it runs on essentially every authenticated
request. It is deliberately one round trip: assignment → role → role_permission → permission,
aggregated in SQL. Resolving it in Python would mean a query per role and a query per role's
permissions, which is the N+1 that engineering-standards §3 exists to prevent — on the hottest
path in the application.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import MOST_JUNIOR_RANK
from app.models.access import EmployeeRoleAssignment, Permission, Role, RolePermission


class ResolvedAccess:
    """What one person may do at one restaurant.

    `rank` is the most senior role they hold there, because seniority is the best of what you have,
    not the average — a person who is a manager and a waiter is a manager.
    """

    __slots__ = ("permissions", "rank", "role_codes")

    def __init__(self, permissions: frozenset[str], rank: int, role_codes: tuple[str, ...]) -> None:
        self.permissions = permissions
        self.rank = rank
        self.role_codes = role_codes


class AccessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(self, employee_id: uuid.UUID, restaurant_id: uuid.UUID) -> ResolvedAccess:
        """Empty permissions and the most junior rank when the person holds no role here.

        Fails closed: someone with no assignment at this restaurant gets nothing, rather than an
        exception a caller might catch and treat as "carry on".
        """
        rows = (
            await self.session.execute(
                select(Permission.code, Role.code, Role.rank)
                .select_from(EmployeeRoleAssignment)
                .join(Role, Role.id == EmployeeRoleAssignment.role_id)
                .outerjoin(RolePermission, RolePermission.role_id == Role.id)
                .outerjoin(Permission, Permission.id == RolePermission.permission_id)
                .where(
                    EmployeeRoleAssignment.employee_id == employee_id,
                    EmployeeRoleAssignment.restaurant_id == restaurant_id,
                )
            )
        ).all()

        if not rows:
            return ResolvedAccess(frozenset(), MOST_JUNIOR_RANK, ())

        permissions = {code for code, _role_code, _rank in rows if code is not None}
        role_codes = {role_code for _code, role_code, _rank in rows}
        rank = min(rank for _code, _role_code, rank in rows)
        return ResolvedAccess(frozenset(permissions), rank, tuple(sorted(role_codes)))

    async def restaurants_for_employee(self, employee_id: uuid.UUID) -> Sequence[uuid.UUID]:
        """Every restaurant this person holds a role at, in a stable order.

        Ordered so that a person assigned to two branches lands on the same one every time they
        log in — an arbitrary order would move someone's home screen between sessions.
        """
        query = (
            select(EmployeeRoleAssignment.restaurant_id)
            .where(EmployeeRoleAssignment.employee_id == employee_id)
            .group_by(EmployeeRoleAssignment.restaurant_id)
            .order_by(
                func.min(EmployeeRoleAssignment.created_at), EmployeeRoleAssignment.restaurant_id
            )
        )
        return (await self.session.scalars(query)).all()

    async def most_senior_rank_anywhere(self, employee_id: uuid.UUID) -> int:
        """This person's seniority across the whole organization, ignoring branch.

        Used for **account-level** authority: the password, the login and the employment are one
        thing per person, however many branches they work at. `resolve()` answers the branch-local
        question and is right for branch-local resources; using it for an account is the bug
        (P1-2, G-4).

        The attack it allowed: an admin at head office who also covers shifts as a waiter at
        branch B resolves to *waiter* rank there, so B's manager outranks them locally and may
        reset their password — then signs in as an admin. Rank is `min`, because seniority is the
        best role you hold, not the average.

        `MOST_JUNIOR_RANK` for someone holding no role anywhere: fails closed, and is the newly
        created employee nobody has assigned yet.
        """
        rank = await self.session.scalar(
            select(func.min(Role.rank))
            .select_from(EmployeeRoleAssignment)
            .join(Role, Role.id == EmployeeRoleAssignment.role_id)
            .where(EmployeeRoleAssignment.employee_id == employee_id)
        )
        return MOST_JUNIOR_RANK if rank is None else int(rank)

    async def roles_for_employees(
        self, employee_ids: Sequence[uuid.UUID], restaurant_id: uuid.UUID
    ) -> dict[uuid.UUID, list[str]]:
        """Role codes for many people at one restaurant, in one statement.

        `resolve()` answers the same question for one person and is the right call on a detail
        page. Calling it per row to render a list is the N+1 that `tests/test_query_counts.py`
        exists to refuse: fifty staff became fifty-one queries, every time anyone opened the
        screen.

        Every requested id is present in the result, mapped to an empty list when the person holds
        no role here. A dict built only from the rows the join returned would silently drop them —
        and the person with no assignment yet is exactly the one a manager just created.
        """
        roles: dict[uuid.UUID, list[str]] = {employee_id: [] for employee_id in employee_ids}
        if not roles:
            return roles

        rows = await self.session.execute(
            select(EmployeeRoleAssignment.employee_id, Role.code)
            .join(Role, Role.id == EmployeeRoleAssignment.role_id)
            .where(
                EmployeeRoleAssignment.employee_id.in_(list(roles)),
                EmployeeRoleAssignment.restaurant_id == restaurant_id,
            )
            # Sorted so a row's roles read the same on every request, matching `resolve()`.
            .order_by(Role.code)
        )
        for employee_id, code in rows:
            roles[employee_id].append(code)
        return roles

    async def assignments_at(
        self, employee_id: uuid.UUID, restaurant_id: uuid.UUID
    ) -> Sequence[EmployeeRoleAssignment]:
        query = select(EmployeeRoleAssignment).where(
            EmployeeRoleAssignment.employee_id == employee_id,
            EmployeeRoleAssignment.restaurant_id == restaurant_id,
        )
        return (await self.session.scalars(query)).all()

    async def roles_available_to(
        self, role_ids: Sequence[uuid.UUID], organization_id: uuid.UUID
    ) -> Sequence[Role]:
        """The subset of `role_ids` this organization may actually use.

        Either its own custom roles or the system templates (`organization_id IS NULL`). The filter
        is the point: without it one tenant could assign a role belonging to another simply by
        knowing its id. The caller compares the count it gets back with the count it asked for and
        refuses the whole request if any id fell outside.
        """
        if not role_ids:
            return []
        query = select(Role).where(
            Role.id.in_(list(role_ids)),
            (Role.organization_id == organization_id) | (Role.organization_id.is_(None)),
        )
        return (await self.session.scalars(query)).all()

    async def system_roles(self) -> Sequence[Role]:
        query = select(Role).where(Role.organization_id.is_(None)).order_by(Role.rank, Role.code)
        return (await self.session.scalars(query)).all()

    async def get_role(self, role_id: uuid.UUID) -> Role | None:
        return await self.session.get(Role, role_id)

    async def all_permissions(self) -> Sequence[Permission]:
        return (await self.session.scalars(select(Permission).order_by(Permission.code))).all()
