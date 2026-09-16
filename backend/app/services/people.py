"""Who did something, as a person reads it: name, employee code and roles (backlog-issues B12, D13).

Tills and deliveries stored the employee id and showed nobody. This resolves many ids in two
statements whatever their number: the employees (organization-scoped, so a person who has since left
this branch is still named) and their roles here.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CATALOGUE
from app.core.tenancy import TenantScope
from app.repositories.access import AccessRepository
from app.repositories.employee import EmployeeRepository


@dataclass(frozen=True, slots=True)
class Person:
    id: uuid.UUID
    full_name: str
    employee_code: str
    roles: tuple[str, ...]


_ROLE_NAMES = {role.code: role.name for role in CATALOGUE.roles}


async def people(
    session: AsyncSession, scope: TenantScope, ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, Person]:
    wanted = sorted({employee_id for employee_id in ids if employee_id is not None}, key=str)
    if not wanted:
        return {}
    employees = await EmployeeRepository(session, scope).by_ids(wanted)
    roles = await AccessRepository(session).roles_for_employees(
        [employee.id for employee in employees], scope.restaurant_id
    )
    return {
        employee.id: Person(
            id=employee.id,
            full_name=employee.full_name,
            employee_code=employee.employee_code,
            roles=tuple(
                _ROLE_NAMES.get(code, code.replace("_", " ").title()) for code in roles[employee.id]
            ),
        )
        for employee in employees
    }
