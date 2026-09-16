"""Operational endpoints. Three questions, three answers, no business logic."""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.db import database_reachable, migrations_at_head
from app.schemas.ops import HealthResponse, ReadyResponse, VersionResponse

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Process is alive. Deliberately checks no dependency — the load balancer must not kill a
    healthy container because Postgres blinked."""
    return HealthResponse(status="ok")


@router.get("/ready")
async def ready() -> JSONResponse:
    """Database reachable and migrations at head. This is the deploy gate: a container whose
    migrations are behind the code must not receive traffic."""
    database = await database_reachable()
    migrated = await migrations_at_head() if database else False
    payload = ReadyResponse(
        ready=database and migrated, database=database, migrations_at_head=migrated
    )
    code = status.HTTP_200_OK if payload.ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=code, content=payload.model_dump())


@router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    """The first thing to check when staging behaves oddly."""
    settings = get_settings()
    return VersionResponse(
        git_sha=settings.git_sha, built_at=settings.built_at, env=settings.env.value
    )
