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
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import create_app

_BACKEND = Path(__file__).resolve().parents[1]


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


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    """The schema, built the way production builds it — by running the migrations, not by
    `create_all`. A model and its migration drifting apart is a real defect class, and creating
    tables from metadata in tests is precisely how it stays hidden."""
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(config, "head")
    return postgres_url


@pytest.fixture
async def db_session(migrated_url: str) -> AsyncIterator[AsyncSession]:
    """A session whose work is rolled back when the test ends.

    Everything runs inside one outer transaction that is never committed, so tests share a single
    migrated database without seeing each other's rows and without truncation between them.
    """
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            # join_transaction_mode="create_savepoint" is what makes constraint tests possible: an
            # IntegrityError rolls the session back to its savepoint instead of destroying the
            # outer transaction, so the fixture can still clean up afterwards. Without it, every
            # test that asserts the database rejects something dies in teardown.
            factory = async_sessionmaker(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            async with factory() as session:
                yield session
            if transaction.is_active:
                await transaction.rollback()
    finally:
        await engine.dispose()
