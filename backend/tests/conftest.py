"""Shared fixtures.

Environment defaults are set before any app import because app.main builds the application at
import time, and Settings fails the boot without them — which is the behaviour we want in
production and must therefore work around here rather than weaken.
"""

from __future__ import annotations

import os

os.environ["ENV"] = "local"
os.environ["DEBUG"] = "false"
os.environ["LOG_LEVEL"] = "INFO"
# Assigned, not setdefault: a DATABASE_URL inherited from the environment (CI used to export a
# reachable one) would make test_ready_fails_when_the_database_is_unreachable pass locally and fail
# in CI. Tests that need a real database take it from the `postgres_url` fixture, explicitly.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1:1/test"

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
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        yield container.get_connection_url()
