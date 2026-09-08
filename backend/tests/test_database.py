"""Migration reversibility and the N+1 guard, both against a real Postgres."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.helpers.queries import assert_max_queries

_BACKEND = Path(__file__).resolve().parents[1]


def _alembic_config(url: str) -> Config:
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_migrations_run_up_down_and_up_again(postgres_url: str) -> None:
    """A migration that cannot be undone is a migration you cannot deploy on a Friday."""
    config = _alembic_config(postgres_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


async def test_query_counter_counts_statements(postgres_url: str) -> None:
    engine = create_async_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            with assert_max_queries(engine, 2):
                await conn.execute(text("SELECT 1"))
                await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def test_query_counter_fails_when_the_budget_is_exceeded(postgres_url: str) -> None:
    engine = create_async_engine(postgres_url)
    try:
        async with engine.connect() as conn:
            with pytest.raises(AssertionError, match="at most 1"), assert_max_queries(engine, 1):
                await conn.execute(text("SELECT 1"))
                await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()
