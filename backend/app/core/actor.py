"""Who is making this request.

An `Actor` is only ever built from a verified token plus a database read — never from anything the
client supplies directly. That is the whole point: a `restaurant_id` taken from a query parameter
would make tenant scoping decorative.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.tenancy import TenantScope


@dataclass(frozen=True, slots=True)
class Actor:
    """An authenticated employee, acting at one restaurant.

    Frozen, so nothing can add a permission to an actor mid-request. A guest token can never
    produce one of these — guests are a separate realm with a separate token type (ADR 0009), and
    that separation is structural rather than a check somebody has to remember to write.
    """

    employee_id: uuid.UUID
    organization_id: uuid.UUID
    restaurant_id: uuid.UUID
    full_name: str
    permissions: frozenset[str]
    # The most senior role held here. Governs who may appoint whom; see permissions.may_assign_rank.
    rank: int
    session_id: uuid.UUID | None = None

    @property
    def scope(self) -> TenantScope:
        return TenantScope(organization_id=self.organization_id, restaurant_id=self.restaurant_id)

    def holds(self, permission: str) -> bool:
        return permission in self.permissions
