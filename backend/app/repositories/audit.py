"""Reading the audit trail, and reading the things it is about.

Two repositories, and the first one exists for a reason worth stating plainly.

**`AuditSubjectRepository` is why the decorator does not call `session.get()`.** A decorator that
loaded an entity by primary key alone would be the single unscoped read in this codebase, sitting
inside the mechanism that records who did what — the worst possible place for the one exception.
Invariant 1 has none: every query goes through a repository that takes the tenant scope, and this
is that repository for the general case.

**It resolves a model from its table name through SQLAlchemy's own registry**, so `entity="order"`
cannot drift from the table `audit_log.entity_type` records. A name with no mapper is an error at
the first call rather than a row nobody can join.

**It refuses a model that carries neither tenant column.** Silently skipping the filter for such a
model is how a reference table's read becomes the precedent for skipping it elsewhere.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import scrub
from app.core.tenancy import TenantScope
from app.models.audit import AuditLog
from app.models.base import Base
from app.repositories.base import RestaurantScopedRepository, ScopedRepository, page_size


def model_for(entity: str) -> type[Base]:
    """The mapped class whose table is `entity`.

    Read from `Base.registry` rather than a hand-kept dictionary: a dictionary is a second place to
    remember, and this module exists because of what happens to things people must remember.
    """
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if getattr(model, "__tablename__", None) == entity:
            return model
    raise LookupError(f"no mapped table is called '{entity}' — check the @audited entity name")


class AuditSubjectRepository(ScopedRepository[Base]):
    """Loads the thing an audit row is about, tenant-scoped, whatever table it is in."""

    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        super().__init__(session, scope)

    async def snapshot(self, entity: str, entity_id: uuid.UUID) -> dict[str, object] | None:
        """Every column of one row, scrubbed and JSON-safe — or `None` if it is not there.

        **Columns, not the entity, and that is not a micro-optimisation.** The first version loaded
        the mapped object and called `session.expire()` on it to see the after-state. It worked, and
        it also expired *the caller's* object: the route that had just created a stock item then
        serialised it, found its eagerly-loaded `ingredient` gone, and died on `lazy="raise"`. An
        audit decorator that changes what the method it wraps returns is worse than no decorator.

        A column select touches no identity map and disturbs nothing. After a flush it reads what
        the database holds, which is exactly what the after-state means.
        """
        model = model_for(entity)
        table = model.__table__
        row = (await self.session.execute(self._scoped(model, entity_id))).mappings().first()
        if row is None:
            return None
        return scrub({column.name: row[column.name] for column in table.columns})

    def _scoped(self, model: type[Base], entity_id: uuid.UUID) -> Select[Any]:
        table = model.__table__
        statement = select(*table.columns).where(table.c.id == entity_id)
        if "restaurant_id" in table.c:
            return statement.where(table.c.restaurant_id == self.scope.restaurant_id)
        if "organization_id" in table.c:
            return statement.where(table.c.organization_id == self.scope.organization_id)
        raise LookupError(
            f"'{model.__tablename__}' carries neither restaurant_id nor organization_id, so an "
            f"audit of it cannot be tenant-scoped. Audit a table that is owned by somebody."
        )


class AuditLogRepository(RestaurantScopedRepository[AuditLog]):
    """The trail itself, for the viewer.

    **Three filters and no free-text search** (decision 7). Entity, actor and date range are the
    three ways somebody actually arrives at this screen: *what happened to this order*, *what did
    this person do*, *what happened on Tuesday*. A search over `old_value` would be a second copy
    of everything in the product, outside every retention story — the same refusal M11 made about
    message search.
    """

    model = AuditLog

    async def page(
        self,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        actor_employee_id: uuid.UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[AuditLog]:
        """Newest first, bounded, keyset-paged on the id — the same shape every list in this
        codebase uses, so a trail with a million rows costs what a trail with fifty costs."""
        query = self.scoped()
        if entity_type is not None:
            query = query.where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            query = query.where(AuditLog.entity_id == entity_id)
        if actor_employee_id is not None:
            query = query.where(AuditLog.actor_employee_id == actor_employee_id)
        if since is not None:
            query = query.where(AuditLog.occurred_at >= since)
        if until is not None:
            query = query.where(AuditLog.occurred_at <= until)
        if after is not None:
            query = query.where(AuditLog.id < after)
        return (
            await self.session.scalars(query.order_by(AuditLog.id.desc()).limit(page_size(limit)))
        ).all()

    async def actors(self) -> Sequence[uuid.UUID]:
        """Who appears in this restaurant's trail, for the viewer's filter.

        Distinct over an index-backed column rather than a join to `employee`: the screen needs the
        names, and it already has them from the staff list it renders beside this.
        """
        statement = (
            select(AuditLog.actor_employee_id)
            .where(
                AuditLog.restaurant_id == self.scope.restaurant_id,
                AuditLog.actor_employee_id.is_not(None),
            )
            .distinct()
            .limit(page_size(None))
        )
        return [row for row in (await self.session.scalars(statement)).all() if row is not None]
