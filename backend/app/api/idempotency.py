"""The route half of idempotency: read the header and the body, then claim the key or replay.

**Called inside a handler, after its dependencies have authorised the actor — never as a dependency
of its own.** A dependency would be resolved alongside authorisation rather than after it, so a
missing key could answer before a missing permission: telling a caller who may not post a delivery
how to format a request that posts one.

A handler using this builds its response **before** committing, records it with `complete`, and
only then commits, so the ledger holds exactly what was returned and holds it atomically with the
effect.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.services.idempotency import (
    Claimed,
    IdempotencyService,
    Replay,
    request_fingerprint,
)

IDEMPOTENCY_HEADER = "Idempotency-Key"
# Set on a replayed response, so a client (and a person reading a network log) can tell a replay
# from a second effect.
REPLAYED_HEADER = "Idempotent-Replayed"


@dataclass(frozen=True, slots=True)
class IdempotentCall:
    service: IdempotencyService
    outcome: Claimed | Replay

    @property
    def replay(self) -> JSONResponse | None:
        if isinstance(self.outcome, Replay):
            return JSONResponse(
                status_code=self.outcome.status_code,
                content=self.outcome.body,
                headers={REPLAYED_HEADER: "true"},
            )
        return None

    async def complete(self, status_code: int, response: BaseModel) -> None:
        if isinstance(self.outcome, Claimed):
            await self.service.complete(
                self.outcome, status_code=status_code, body=response.model_dump(mode="json")
            )


async def begin_idempotent(request: Request, session: AsyncSession, actor: Actor) -> IdempotentCall:
    route = request.scope.get("route")
    template = getattr(route, "path", request.url.path)
    service = IdempotencyService(session, actor.scope)
    outcome = await service.begin(
        actor,
        key=request.headers.get(IDEMPOTENCY_HEADER),
        endpoint=f"{request.method} {template}",
        fingerprint=request_fingerprint(request.method, request.url.path, await request.body()),
    )
    return IdempotentCall(service=service, outcome=outcome)
