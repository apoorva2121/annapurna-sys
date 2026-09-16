"""Staff management endpoints.

Every handler here is four lines or fewer of its own: authorise via the dependency, call one
service, shape the response. No business rule and no database access lives in this file
(engineering-standards §1) — which is what lets the generic suites reason about these routes by
walking the routing table rather than by reading them.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.models.identity import Employee
from app.repositories.base import DEFAULT_PAGE_SIZE
from app.schemas.identity import (
    EmployeeCodeResponse,
    EmployeeCreateRequest,
    EmployeeListResponse,
    EmployeeResponse,
    EmployeeUpdateRequest,
    PasswordResetRequest,
    RoleAssignmentRequest,
)
from app.services.employee import EmployeeService, NewEmployee

router = APIRouter(prefix="/employees", tags=["employees"])

_ViewDep = Annotated[Actor, Depends(require_permission(PermissionCode.EMPLOYEE_VIEW))]
_CreateDep = Annotated[Actor, Depends(require_permission(PermissionCode.EMPLOYEE_CREATE))]
_EditDep = Annotated[Actor, Depends(require_permission(PermissionCode.EMPLOYEE_EDIT))]
_DeactivateDep = Annotated[Actor, Depends(require_permission(PermissionCode.EMPLOYEE_DEACTIVATE))]
_AssignDep = Annotated[Actor, Depends(require_permission(PermissionCode.EMPLOYEE_ROLE_ASSIGN))]
_ResetDep = Annotated[Actor, Depends(require_permission(PermissionCode.EMPLOYEE_PASSWORD_RESET))]


def _shape(employee: Employee, roles: list[str]) -> EmployeeResponse:
    """The response, given roles already in hand.

    Split from `_render` so the list endpoint can resolve every row's roles in one query. Building
    the response and fetching what it needs are separate concerns, and fusing them is what made the
    list O(n) queries.
    """
    return EmployeeResponse(
        id=employee.id,
        employee_code=employee.employee_code,
        full_name=employee.full_name,
        phone=employee.phone,
        joined_on=employee.joined_on,
        employment_type=employee.employment_type,
        is_active=employee.is_active,
        deactivated_at=employee.deactivated_at,
        has_login=employee.user_account_id is not None,
        roles=roles,
    )


async def _render(
    service: EmployeeService, employee: Employee, restaurant_id: uuid.UUID
) -> EmployeeResponse:
    """One employee. A single extra query, which is correct on a detail page."""
    return _shape(employee, await service.roles_of(employee.id, restaurant_id))


@router.get("", response_model=EmployeeListResponse)
async def list_employees(
    actor: _ViewDep,
    session: SessionDep,
    # An explicit flag rather than a tri-state `is_active`. A query string cannot express "either"
    # for a boolean — `?is_active=` is a validation error, not "both" — so the tri-state only
    # worked from Python and would have been undiscoverable from the UI.
    include_inactive: Annotated[bool, Query()] = False,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    cursor: Annotated[uuid.UUID | None, Query()] = None,
) -> EmployeeListResponse:
    service = EmployeeService(session)
    employees = await service.list_employees(
        actor, is_active=None if include_inactive else True, limit=limit, after=cursor
    )
    # One query for the whole page's roles, not one per row (tests/test_query_counts.py).
    roles = await service.roles_of_many(employees, actor.restaurant_id)
    items = [_shape(employee, roles[employee.id]) for employee in employees]
    # Only offer a cursor when the page was full; otherwise the client makes one more round trip
    # to learn what it already knows.
    # DEFAULT_PAGE_SIZE rather than a literal 50: the repository decides the page size, and a
    # second copy of that number here would silently stop matching the day it changes — the client
    # would then be told there is no next page when there is, and the rest of the roster would
    # simply not exist as far as the UI is concerned.
    next_cursor = items[-1].id if len(items) == (limit or DEFAULT_PAGE_SIZE) else None
    return EmployeeListResponse(items=items, next_cursor=next_cursor)


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: EmployeeCreateRequest, actor: _CreateDep, session: SessionDep
) -> EmployeeResponse:
    service = EmployeeService(session)
    employee = await service.create_employee(
        actor,
        NewEmployee(
            full_name=payload.full_name,
            employee_code=payload.employee_code,
            joined_on=payload.joined_on,
            employment_type=payload.employment_type,
            phone=payload.phone,
            date_of_birth=payload.date_of_birth,
            login_identifier=payload.login_identifier,
            initial_password=payload.initial_password,
        ),
    )
    await session.commit()
    return await _render(service, employee, actor.restaurant_id)


@router.get("/next-code", response_model=EmployeeCodeResponse)
async def next_employee_code(actor: _CreateDep, session: SessionDep) -> EmployeeCodeResponse:
    """The next free employee code, for the add-employee form to fill in (decision D19). Declared
    before `/{employee_id}`, which would otherwise read "next-code" as an id and refuse it."""
    return EmployeeCodeResponse(employee_code=await EmployeeService(session).next_code(actor))


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: uuid.UUID, actor: _ViewDep, session: SessionDep
) -> EmployeeResponse:
    service = EmployeeService(session)
    employee = await service.get_employee(actor, employee_id)
    return await _render(service, employee, actor.restaurant_id)


@router.patch("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: uuid.UUID,
    payload: EmployeeUpdateRequest,
    actor: _EditDep,
    session: SessionDep,
) -> EmployeeResponse:
    service = EmployeeService(session)
    # exclude_unset, so "not mentioned" and "explicitly set to null" stay distinguishable — a
    # PATCH that clears a phone number must be expressible.
    changes = payload.model_dump(exclude_unset=True)
    employee = await service.update_employee(actor, employee_id, changes)
    await session.commit()
    return await _render(service, employee, actor.restaurant_id)


@router.post("/{employee_id}/deactivate", response_model=EmployeeResponse)
async def deactivate_employee(
    employee_id: uuid.UUID, actor: _DeactivateDep, session: SessionDep
) -> EmployeeResponse:
    service = EmployeeService(session)
    employee = await service.deactivate_employee(actor, employee_id)
    await session.commit()
    return await _render(service, employee, actor.restaurant_id)


@router.post("/{employee_id}/reactivate", response_model=EmployeeResponse)
async def reactivate_employee(
    employee_id: uuid.UUID, actor: _DeactivateDep, session: SessionDep
) -> EmployeeResponse:
    service = EmployeeService(session)
    employee = await service.reactivate_employee(actor, employee_id)
    await session.commit()
    return await _render(service, employee, actor.restaurant_id)


@router.post("/{employee_id}/roles", response_model=EmployeeResponse)
async def set_roles(
    employee_id: uuid.UUID,
    payload: RoleAssignmentRequest,
    actor: _AssignDep,
    session: SessionDep,
) -> EmployeeResponse:
    service = EmployeeService(session)
    # Read before the change, not after: see below.
    employee = await service.get_employee(actor, employee_id)
    roles = await service.set_roles(actor, employee_id, payload.role_ids)
    await session.commit()
    # Rendered from what we already hold rather than re-reading through the visibility filter.
    # Removing someone's last role at this restaurant makes them invisible here by definition, so
    # a re-read answered 404 for a change that had just succeeded — the legitimate case being an
    # owner taking a waiter off this branch's roster.
    return _shape(employee, list(roles))


@router.post("/{employee_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    employee_id: uuid.UUID,
    payload: PasswordResetRequest,
    actor: _ResetDep,
    session: SessionDep,
) -> None:
    await EmployeeService(session).reset_password(actor, employee_id, payload.new_password)
    await session.commit()
