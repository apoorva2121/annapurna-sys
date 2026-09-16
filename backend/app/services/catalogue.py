"""The role and permission catalogue, as the role-assignment screen needs it.

Thin on purpose. It exists so `api/v1/staff/roles.py` calls a service rather than a repository —
the layering rule in `docs/engineering-standards.md` §1 — and so the *policy* question of which
roles a tenant may see has one home rather than being decided in a route today and somewhere else
when custom roles arrive in a later module.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.models.access import Permission, Role
from app.repositories.access import AccessRepository


class CatalogueService:
    def __init__(self, session: AsyncSession) -> None:
        self.access = AccessRepository(session)

    async def roles_for(self, actor: Actor) -> Sequence[Role]:
        """Every role this organization may use, ordered by seniority so the screen reads top-down
        the way an org chart does.

        Includes roles the actor may not *grant*. That is deliberate: a manager seeing that an
        Owner role exists, and being refused when they try to assign it, is clearer than a list
        that silently omits it and leaves them wondering. The refusal belongs to the seniority
        ladder in `EmployeeService`, which is where it can explain itself.
        """
        _ = actor
        # M01 ships only the system templates. When an organization can define its own, this is the
        # one place that changes — not the route.
        return await self.access.system_roles()

    async def permissions(self) -> Sequence[Permission]:
        """The whole vocabulary, so the screen can say what a grant actually does rather than
        showing an opaque string."""
        return await self.access.all_permissions()
