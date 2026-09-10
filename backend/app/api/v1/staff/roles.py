"""The role and permission catalogue, for the role-assignment screen.

Read-only in M01. Customising a role is a later concern; what the UI needs now is the list of roles
it may offer and the human-readable meaning of each permission, so the screen can explain what a
grant actually does rather than showing an opaque string.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.repositories.access import AccessRepository
from app.schemas.identity import PermissionResponse, RoleResponse

router = APIRouter(tags=["roles"])

_ViewDep = Annotated[Actor, Depends(require_permission(PermissionCode.ROLE_VIEW))]


@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(_actor: _ViewDep, session: SessionDep) -> list[RoleResponse]:
    """Ordered by seniority, so the assignment screen reads top-down the way an org chart does.

    Returns every role, including ones this actor may not grant. The UI shows them so a manager
    can see that an Owner role exists and understand why it is not offered; the *grant* is refused
    by the service, which is where the seniority rule belongs.
    """
    roles = await AccessRepository(session).system_roles()
    return [RoleResponse.model_validate(role) for role in roles]


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(_actor: _ViewDep, session: SessionDep) -> list[PermissionResponse]:
    permissions = await AccessRepository(session).all_permissions()
    return [PermissionResponse.model_validate(permission) for permission in permissions]
