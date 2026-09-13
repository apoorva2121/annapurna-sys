"""Idempotency for the writes where a duplicate is money or stock (ADR 0010; M07 spec decision 8).

A waiter taps "Settle" and the network stalls, so they tap again. A store manager taps "Book it in"
over restaurant wifi twice. Without this, both are two effects: a customer charged twice, a delivery
booked twice. Four rules:

**1 · The key is the client's, made when the person tapped, and scoped to the restaurant.** It lives
24 hours (ADR 0010). An expired key can be claimed again.

**2 · The claim is written in the same transaction as the effect.** A duplicate that arrives while
the first is still running waits on the unique index (see `IdempotencyKeyRepository.claim`), then
finds a finished request and replays its response. A first attempt that fails rolls its claim back
with everything else, so the honest retry after a dropped connection or a 500 runs again rather than
replaying a failure. **An error is never stored.**

**3 · Same key and same request is a replay; same key and a different request is a 409.** The
second case is a client bug — a key reused across two different deliveries — not a retry, and
replaying the first response for it would tell the person their second delivery was booked when it
was not.

**4 · The request is identified by method, path and exact body.** A retry sends the same bytes,
because the client re-sends the same variables.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import IdempotencyState
from app.core.errors import AppError, ConflictError
from app.core.tenancy import TenantScope
from app.repositories.idempotency import IdempotencyKeyRepository

KEY_LIFETIME = timedelta(hours=24)

# The length migration 0019's CHECK allows, and the characters a `crypto.randomUUID()` key uses.
_KEY = re.compile(r"^[A-Za-z0-9_\-:.]{16,128}$")


@dataclass(frozen=True, slots=True)
class Claimed:
    """This request holds the key and must record its response before it commits."""

    claim_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class Replay:
    """The key was already used for exactly this request, which finished with this response."""

    status_code: int
    body: dict[str, Any]


def request_fingerprint(method: str, path: str, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(method.upper().encode("ascii"))
    digest.update(b" ")
    digest.update(path.encode("utf-8"))
    digest.update(b"\n")
    digest.update(body)
    return f"sha256:{digest.hexdigest()}"


_IN_PROGRESS = (
    "idempotency.in_progress",
    "This request is still being processed. Wait a moment, then reload before trying again.",
)


class IdempotencyService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self._keys = IdempotencyKeyRepository(session, scope)

    async def begin(
        self, actor: Actor, *, key: str | None, endpoint: str, fingerprint: str
    ) -> Claimed | Replay:
        if key is None:
            raise AppError(
                "idempotency.key_required",
                "This action needs an Idempotency-Key header, created when the button was pressed.",
                status_code=422,
            )
        if not _KEY.fullmatch(key):
            raise AppError(
                "idempotency.key_invalid",
                "An Idempotency-Key is 16 to 128 letters, digits, dashes, dots, colons "
                "or underscores.",
                status_code=422,
            )

        now = datetime.now(UTC)
        # Twice at most: once normally, and once more if the row we collided with vanished (its
        # holder's transaction rolled back after our insert gave up) or had expired.
        for _ in range(2):
            claim_id = await self._keys.claim(
                key=key,
                endpoint=endpoint,
                request_hash=fingerprint,
                actor_employee_id=actor.employee_id,
                expires_at=now + KEY_LIFETIME,
            )
            if claim_id is not None:
                return Claimed(claim_id)

            existing = await self._keys.by_key(key)
            if existing is None:
                continue
            if existing.expires_at <= now:
                await self._keys.discard_expired(key, now)
                continue
            if existing.request_hash != fingerprint:
                raise ConflictError(
                    "idempotency.key_reused",
                    "This Idempotency-Key was already used for a different request.",
                    details={"endpoint": existing.endpoint},
                )
            if (
                existing.state != IdempotencyState.COMPLETED
                or existing.response_status is None
                or existing.response_body is None
            ):
                raise ConflictError(*_IN_PROGRESS)
            return Replay(status_code=existing.response_status, body=dict(existing.response_body))
        raise ConflictError(*_IN_PROGRESS)

    async def complete(self, claimed: Claimed, *, status_code: int, body: dict[str, Any]) -> None:
        await self._keys.complete(claimed.claim_id, status_code=status_code, body=body)
