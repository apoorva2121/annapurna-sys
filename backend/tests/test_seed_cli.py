"""`python -m app.seed` — the thing `make seed` actually runs.

Invoked through `asyncio.to_thread` because the entry point calls `asyncio.run()`, which refuses
to nest inside the loop pytest-asyncio is already running. A thread gives it the bare interpreter
it has in production, rather than reaching past it to await an internal coroutine — which would
test a different code path from the one `make seed` takes.

Covered separately from `seed_identity` because the entry point owns the parts that only exist
outside a test: it builds its own engine, owns one transaction for the whole run, and turns the two
predictable failures into exit codes a human can act on. A green `seed_identity` proves none of
that works.

Each test gets its own database rather than the shared migrated one, because this entry point
*commits*. Sharing would leak nineteen employees into every other test in the session.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.seed.__main__ import run
from tests.conftest import _BACKEND


@pytest.fixture
def pointed_at(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str], None]]:
    """Point Settings at a given database for one test.

    The cache is cleared on both sides: conftest sets a deliberately unreachable DATABASE_URL, and
    a Settings object left cached here would carry this test's database into the next one.
    """

    def point(url: str) -> None:
        monkeypatch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()

    yield point
    get_settings.cache_clear()


async def _counts(url: str) -> dict[str, int]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return {
                table: int(
                    (await connection.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608
                )
                for table in ("organization", "restaurant", "employee", "employee_role_assignment")
            }
    finally:
        await engine.dispose()


async def test_it_seeds_an_empty_database_and_reports_success(
    fresh_database: str, pointed_at: Callable[[str], None]
) -> None:
    pointed_at(fresh_database)

    assert await asyncio.to_thread(run) == 0

    counts = await _counts(fresh_database)
    assert counts["organization"] == 2
    assert counts["restaurant"] == 3
    assert counts["employee"] == 19
    # 20 assignments for 19 employees: one person (EMP003) holds a role at both Spice Garden
    # branches. That is the only reason `POST /auth/switch` can be exercised by hand at all — the
    # switcher renders nothing for someone who works at a single restaurant (M02, finding S12).
    assert counts["employee_role_assignment"] == 20


async def test_running_it_twice_commits_nothing_the_second_time(
    fresh_database: str, pointed_at: Callable[[str], None]
) -> None:
    """The real-world invocation: somebody runs `make seed` again because they forgot they had.

    Proved against committed rows rather than a rolled-back transaction, because the transaction
    boundary is exactly what this entry point owns and what the service-level test cannot see.
    """
    pointed_at(fresh_database)

    assert await asyncio.to_thread(run) == 0
    after_first = await _counts(fresh_database)
    assert await asyncio.to_thread(run) == 0
    assert await _counts(fresh_database) == after_first


async def test_it_exits_nonzero_when_the_seed_data_is_missing(
    fresh_database: str, pointed_at: Callable[[str], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A distinct, non-zero code, because the data lives at the repository root while the backend
    runs from /app — this is much the most likely way `make seed` fails on someone's machine."""
    pointed_at(fresh_database)
    monkeypatch.setenv("SEED_DIR", str(_BACKEND / "does-not-exist"))

    assert await asyncio.to_thread(run) == 2


async def test_it_exits_nonzero_when_the_role_catalogue_is_not_seeded(
    fresh_database: str, pointed_at: Callable[[str], None]
) -> None:
    """Seeding before migrating. Without the system roles there is nothing to assign, and guessing
    a role would hand someone permissions nobody granted."""
    pointed_at(fresh_database)
    engine = create_async_engine(fresh_database)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM role_permission"))
            await connection.execute(text("DELETE FROM role WHERE organization_id IS NULL"))
    finally:
        await engine.dispose()

    assert await asyncio.to_thread(run) == 3
