"""Facts about a restaurant, looked up without a scope — because they are what *establishes* one.

Every other repository in this product takes a `TenantScope` and cannot be constructed without it,
which is CLAUDE.md invariant 1's structural half. These two queries are the exceptions, and keeping
them in one small file under one heading is what makes a third exception visible if somebody adds
one.

Both are safe to run unscoped for the same reason: the argument is an id the caller already holds
and the server itself supplied — a restaurant resolved from a signed token, or from an actor.
Neither takes anything a guest typed.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenancy import Restaurant


async def organization_of(session: AsyncSession, restaurant_id: uuid.UUID) -> uuid.UUID | None:
    """Which organization a restaurant belongs to.

    Needed by the guest realm, whose token deliberately carries no organization: that is how a chain
    recognises a diner across branches, and it is none of a table's business. The server knowing it
    about its own restaurant is not the token growing a claim.
    """
    found = await session.scalar(
        select(Restaurant.organization_id).where(Restaurant.id == restaurant_id)
    )
    return None if found is None else uuid.UUID(str(found))


async def name_of(session: AsyncSession, restaurant_id: uuid.UUID) -> str:
    """What a guest sees at the top of the screen.

    Public — it is on the door — and the only thing about the restaurant a guest response carries.
    """
    found = await session.scalar(select(Restaurant.name).where(Restaurant.id == restaurant_id))
    return str(found or "")
