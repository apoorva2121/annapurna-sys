"""The idempotency ledger's queries. What a key *means* is the service's; this reads and writes.

`claim` is the whole mechanism, and it is one statement: `INSERT … ON CONFLICT DO NOTHING`.

When a second request arrives carrying a key that a first request has inserted but not yet
committed, Postgres makes the second insert **wait on the unique index** until the first
transaction ends. If the first commits, the second inserts nothing and reads the committed row. If
the first rolls back, the second's insert goes through and it proceeds as though it were first.
Serialisation comes from the database rather than from application code racing a SELECT against
an INSERT — which is the race this table exists to close.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert

from app.core.enums import IdempotencyState
from app.models.orders import IdempotencyKey
from app.repositories.base import RestaurantScopedRepository


class IdempotencyKeyRepository(RestaurantScopedRepository[IdempotencyKey]):
    model = IdempotencyKey

    async def claim(
        self,
        *,
        key: str,
        endpoint: str,
        request_hash: str,
        actor_employee_id: uuid.UUID,
        expires_at: datetime,
    ) -> uuid.UUID | None:
        """Insert the key for this request, or return None if the restaurant already holds it."""
        statement = (
            insert(IdempotencyKey)
            .values(
                restaurant_id=self.scope.restaurant_id,
                key=key,
                endpoint=endpoint,
                request_hash=request_hash,
                state=IdempotencyState.IN_PROGRESS,
                expires_at=expires_at,
                actor_employee_id=actor_employee_id,
            )
            .on_conflict_do_nothing(
                index_elements=[IdempotencyKey.restaurant_id, IdempotencyKey.key]
            )
            .returning(IdempotencyKey.id)
        )
        claimed: uuid.UUID | None = await self.session.scalar(statement)
        return claimed

    async def by_key(self, key: str) -> IdempotencyKey | None:
        query = (
            self.scoped().where(IdempotencyKey.key == key).execution_options(populate_existing=True)
        )
        return (await self.session.scalars(query)).first()

    async def discard_expired(self, key: str, now: datetime) -> None:
        """Forget an expired key so it can be claimed again. Scoped, and only an expired row."""
        await self.session.execute(
            delete(IdempotencyKey).where(
                IdempotencyKey.restaurant_id == self.scope.restaurant_id,
                IdempotencyKey.key == key,
                IdempotencyKey.expires_at <= now,
            )
        )

    async def complete(
        self, claim_id: uuid.UUID, *, status_code: int, body: dict[str, Any]
    ) -> None:
        await self.session.execute(
            update(IdempotencyKey)
            .where(
                IdempotencyKey.id == claim_id,
                IdempotencyKey.restaurant_id == self.scope.restaurant_id,
            )
            .values(
                state=IdempotencyState.COMPLETED,
                response_status=status_code,
                response_body=body,
            )
        )
