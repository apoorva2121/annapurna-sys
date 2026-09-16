"""Repository base classes. Queries live here; business rules do not.

Two classes rather than one, and the split is the point. Most M01 entities belong to an
*organization* (an employee is employed by the company, not by a branch), while operational data
belongs to a *restaurant*. Naming the two differently means a reviewer can see which boundary a
repository enforces from its declaration line, instead of reading the query to find out.

Neither class can be constructed without a scope. That is the structural half of CLAUDE.md
invariant 1 — the half that does not depend on anyone remembering.
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantScope
from app.models.base import Base

# engineering-standards §3: no unbounded result set, default page 50, maximum 100.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


def page_size(requested: int | None) -> int:
    """Clamp rather than reject. A caller asking for 10,000 rows gets the maximum — the query stays
    bounded and the caller is not made to handle an error for something harmless."""
    if requested is None:
        return DEFAULT_PAGE_SIZE
    return max(1, min(requested, MAX_PAGE_SIZE))


class ScopedRepository[ModelT: Base]:
    """Common ancestor. Holds the session and the scope, and nothing else."""

    model: ClassVar[Any]

    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope


class OrgScopedRepository[ModelT: Base](ScopedRepository[ModelT]):
    """For entities owned by the organization: employee, user_account, role.

    `scoped()` is the only select a subclass should start from. Starting from a bare
    `select(Model)` is a review rejection, and the four generic suites are what catch it when
    review does not.
    """

    def scoped(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(self.model.organization_id == self.scope.organization_id)


class RestaurantScopedRepository[ModelT: Base](ScopedRepository[ModelT]):
    """For entities owned by one restaurant: everything operational, from M02 onward.

    A separate class from the organization-scoped one on purpose — silently applying whichever
    filter the model happens to support is how a table ends up scoped to the wrong thing.
    """

    def scoped(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(self.model.restaurant_id == self.scope.restaurant_id)

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        result = await self.session.scalars(self.scoped().where(self.model.id == entity_id))
        return result.first()
