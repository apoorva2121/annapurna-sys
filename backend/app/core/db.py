"""Async engine, session factory, and the two readiness checks /ready depends on."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    # pool_pre_ping costs one round trip and removes the whole class of "stale connection after the
    # database restarted" errors that otherwise surface as random 500s.
    return create_async_engine(settings.database_url, pool_pre_ping=True, echo=False)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. One session per request, always closed."""
    async with get_sessionmaker()() as session:
        yield session


async def database_reachable() -> bool:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


def _current_revision(sync_conn: Connection) -> str | None:
    return MigrationContext.configure(sync_conn).get_current_revision()


async def migrations_at_head() -> bool:
    """False when the database is behind the code — the deploy gate that prevents a half-migrated
    container serving traffic."""
    try:
        head = ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_current_head()
        async with get_engine().connect() as conn:
            current = await conn.run_sync(_current_revision)
    except Exception:
        return False
    return current == head
