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

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.db import get_session
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
async def api(db_connection: AsyncConnection) -> AsyncIterator[FastAPI]:
    """The real application, wired to the test's transaction but **not** to the test's session.

    Each request opens its own session and closes it when the request ends — exactly what
    `app.core.db.get_session` does in production. That is the whole point of this fixture, and it is
    guardrail G-2.

    The previous version yielded one long-lived session to every request. It looked harmless and it
    made this suite unable to see a rollback: a handler that flushed and then raised left its work
    visible to the next request and to the assertions, because nothing ever closed the session. The
    account lockout shipped inoperative underneath 262 passing tests for exactly that reason
    (P1-1) — the counter was rolled back in production and survived in the tests.

    With a session per request, a handler that forgets to commit fails here instead of in a
    restaurant.

    **What this fixture cannot test, and what to use instead.** Every session here shares one
    connection and one transaction, so two "concurrent" requests are the same transaction: they
    share locks, and a `SELECT … FOR UPDATE` never contends. A test asserting that a row lock
    prevents a lost update, or that two simultaneous writes resolve to one, would pass here while
    proving nothing. `commit()` is also `RELEASE SAVEPOINT` rather than a real `COMMIT`, so a
    failure that only occurs at commit time — a deferred constraint, a serialization error — cannot
    surface either.

    Anything of that shape takes `fresh_database` and its own connections. R6's refresh-rotation
    grace window (G-19) is the next test with this property; write it there, not here.
    """
    application = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        async with _session_factory(db_connection)() as session:
            yield session

    application.dependency_overrides[get_session] = _session_override
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def api_client(api: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=api)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def fresh_database(postgres_url: str) -> AsyncIterator[str]:
    """An empty, migrated database of its own, dropped afterwards.

    For the handful of tests that must observe **real commit boundaries**. The `db_session` fixture
    below wraps everything in one transaction that is never committed, which is exactly right for
    isolation and exactly wrong for proving that a write survives the request that made it — a
    rolled-back write is still visible inside the transaction that made it.

    The lockout counter is the case that proved this matters: it had a green test and did not work.
    """
    import uuid as _uuid

    name = f"t_{_uuid.uuid4().hex[:12]}"
    admin = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await admin.dispose()

    url = postgres_url.rsplit("/", 1)[0] + f"/{name}"
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    # In a thread: alembic's async env.py calls asyncio.run(), which cannot nest inside the loop
    # this fixture runs in.
    await asyncio.to_thread(command.upgrade, config, "head")

    yield url

    admin = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        await admin.dispose()


@pytest.fixture
async def db_connection(migrated_url: str) -> AsyncIterator[AsyncConnection]:
    """One connection and one outer transaction per test, rolled back at the end.

    Sessions are built *from* this rather than being the unit of isolation themselves, which is what
    lets the test and the application hold separate sessions over the same rolled-back transaction —
    the arrangement production has, where every request gets its own session against a shared pool.
    """
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            yield connection
            if transaction.is_active:
                await transaction.rollback()
    finally:
        await engine.dispose()


def _session_factory(connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    # join_transaction_mode="create_savepoint" is what makes constraint tests possible: an
    # IntegrityError rolls the session back to its savepoint instead of destroying the outer
    # transaction, so the fixture can still clean up afterwards. Without it, every test that asserts
    # the database rejects something dies in teardown.
    #
    # It is also what makes the honest `api` fixture below work: a handler's commit() releases its
    # savepoint rather than the outer transaction, and a handler that *fails* rolls back to that
    # savepoint — discarding exactly what production would discard.
    return async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    """The session a test uses to arrange its own fixtures and assert against afterwards.

    Note it is *not* the session the application uses — see `api`. After a request, re-read through
    this session rather than trusting an object it loaded earlier: the two sessions have separate
    identity maps, and that is the point.
    """
    async with _session_factory(db_connection)() as session:
        yield session
