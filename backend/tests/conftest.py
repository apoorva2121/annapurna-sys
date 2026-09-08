"""Shared fixtures.

Environment defaults are set before any app import because app.main builds the application at
import time, and Settings fails the boot without them — which is the behaviour we want in
production and must therefore work around here rather than weaken.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENV", "local")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("LOG_LEVEL", "INFO")
# Deliberately unroutable. Most tests must not need a database, and /ready has to be provably 503
# when one is absent.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:1/test")

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """One real Postgres per test run. Never SQLite — this product depends on timestamptz,
    NUMERIC, partial indexes, jsonb and FOR UPDATE, none of which SQLite models faithfully."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        yield container.get_connection_url()
