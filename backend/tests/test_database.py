"""Migration reversibility and the N+1 guard, both against a real Postgres."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import (
    database_reachable,
    get_engine,
    get_sessionmaker,
    migrations_at_head,
)
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


def test_readiness_is_true_against_a_migrated_database(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure path of /ready was covered from the start; the success path was not, which left
    the deploy gate's actual green condition unproven."""
    command.upgrade(_alembic_config(postgres_url), "head")

    monkeypatch.setenv("DATABASE_URL", postgres_url)
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    async def _check() -> tuple[bool, bool]:
        reachable = await database_reachable()
        at_head = await migrations_at_head()
        await get_engine().dispose()
        return reachable, at_head

    try:
        reachable, at_head = asyncio.run(_check())
    finally:
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()

    assert reachable is True
    assert at_head is True


def test_migrations_at_head_is_false_before_any_migration_runs(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    command.downgrade(_alembic_config(postgres_url), "base")

    monkeypatch.setenv("DATABASE_URL", postgres_url)
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    async def _check() -> bool:
        at_head = await migrations_at_head()
        await get_engine().dispose()
        return at_head

    try:
        at_head = asyncio.run(_check())
    finally:
        command.upgrade(_alembic_config(postgres_url), "head")
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()

    assert at_head is False


async def test_the_fssai_licence_survives_a_downgrade(postgres_url: str) -> None:
    """Migration 0004 moves a legally required number out of a JSON blob and into a column.

    A downgrade that simply dropped the column would delete an FSSAI licence that prints on every
    bill, so 0004's downgrade returns it to `settings` first. Asserted because "reversible" has to
    mean "without losing data", not merely "the table is gone again".
    """
    config = _alembic_config(postgres_url)
    await asyncio.to_thread(command.upgrade, config, "head")

    engine = create_async_engine(postgres_url)
    try:
        async with engine.begin() as conn:
            organization_id = (
                await conn.execute(
                    text(
                        "INSERT INTO organization (id, name, slug, plan, is_demo) "
                        "VALUES (gen_random_uuid(), 'Licence Co', 'licence-co', 'trial', true) "
                        "RETURNING id"
                    )
                )
            ).scalar_one()
            await conn.execute(
                text(
                    # timezone, currency and is_active carry Python-side defaults rather than
                    # server ones, so a raw INSERT has to supply them.
                    "INSERT INTO restaurant "
                    "  (id, organization_id, name, code, timezone, currency, is_active, "
                    "   fssai_licence) "
                    "VALUES (gen_random_uuid(), :org, 'Licence Test', 'LIC1', 'Asia/Kolkata', "
                    "        'INR', true, '11522998000123')"
                ),
                {"org": organization_id},
            )

        await asyncio.to_thread(command.downgrade, config, "0003_password_reset_required")

        async with engine.begin() as conn:
            stored = (
                await conn.execute(
                    text("SELECT settings ->> 'fssai_licence' FROM restaurant WHERE code = 'LIC1'")
                )
            ).scalar_one()
        assert stored == "11522998000123", (
            "the downgrade dropped the FSSAI licence instead of returning it to settings"
        )

        await asyncio.to_thread(command.upgrade, config, "head")
        async with engine.begin() as conn:
            restored = (
                await conn.execute(text("SELECT fssai_licence FROM restaurant WHERE code = 'LIC1'"))
            ).scalar_one()
            await conn.execute(text("DELETE FROM restaurant WHERE code = 'LIC1'"))
            await conn.execute(text("DELETE FROM organization WHERE slug = 'licence-co'"))
        assert restored == "11522998000123"
    finally:
        await engine.dispose()


async def test_0008_collapses_rate_rows_into_one_group_and_back(postgres_url: str) -> None:
    """M03 decision 1's migration, asserted on the only thing that matters: the data.

    0008 splits one table into two. Two rates of the same name were one lineage under M02's rule —
    0007's exclusion constraint said so — so they must collapse to **one** group with **two** rates,
    and the codes must come out as the ones `seed/operations.yaml` has always carried.

    The downgrade then has to put the name back on every rate row. A downgrade that dropped
    `tax_group` without restoring `tax_rate.name` would leave the table NOT NULL-violating and the
    rates unidentifiable, which is a migration that is reversible only in the sense that the tables
    are gone again.
    """
    config = _alembic_config(postgres_url)
    # Up to head first, then back to 0007. The container may arrive at base or at head depending on
    # what ran before, and `downgrade` from base is an error rather than a no-op.
    await asyncio.to_thread(command.upgrade, config, "head")
    await asyncio.to_thread(command.downgrade, config, "0007_tax_group_no_overlap")

    engine = create_async_engine(postgres_url)
    try:
        async with engine.begin() as conn:
            organization_id = (
                await conn.execute(
                    text(
                        "INSERT INTO organization (id, name, slug, plan, is_demo) "
                        "VALUES (gen_random_uuid(), 'Tax Co', 'tax-co', 'trial', true) "
                        "RETURNING id"
                    )
                )
            ).scalar_one()
            restaurant_id = (
                await conn.execute(
                    text(
                        "INSERT INTO restaurant "
                        "  (id, organization_id, name, code, timezone, currency, is_active) "
                        "VALUES (gen_random_uuid(), :org, 'Tax Test', 'TAX1', 'Asia/Kolkata', "
                        "        'INR', true) RETURNING id"
                    ),
                    {"org": organization_id},
                )
            ).scalar_one()
            # One lineage, superseded once: 5% until March, 12% from April. Plus a second,
            # genuinely different class that is live at the same time — the seed's own shape.
            for name, rate, start, end in (
                ("GST 5% (restaurant, no ITC)", "0.0500", date(2025, 1, 1), date(2026, 3, 31)),
                ("GST 5% (restaurant, no ITC)", "0.1200", date(2026, 4, 1), None),
                ("GST 18% (packaged/beverage)", "0.1800", date(2025, 1, 1), None),
            ):
                await conn.execute(
                    text(
                        "INSERT INTO tax_group "
                        "  (id, restaurant_id, name, rate, is_inclusive, effective_from, "
                        "   effective_to) "
                        "VALUES (gen_random_uuid(), :r, :n, :rate, false, :start, :end)"
                    ),
                    {"r": restaurant_id, "n": name, "rate": rate, "start": start, "end": end},
                )

        await asyncio.to_thread(command.upgrade, config, "head")

        async with engine.begin() as conn:
            groups = (
                await conn.execute(
                    text("SELECT code, name FROM tax_group WHERE restaurant_id = :r ORDER BY code"),
                    {"r": restaurant_id},
                )
            ).all()
            # Three rows in, two groups out. The two 5% rows were one lineage and collapse.
            assert [row[0] for row in groups] == ["GST18", "GST5"], groups

            rates = [
                (row[0], row[1], row[2])
                for row in (
                    await conn.execute(
                        text(
                            "SELECT g.code, r.rate::text, r.effective_from::text "
                            "FROM tax_rate r JOIN tax_group g ON g.id = r.tax_group_id "
                            "WHERE r.restaurant_id = :r ORDER BY g.code, r.effective_from"
                        ),
                        {"r": restaurant_id},
                    )
                ).all()
            ]
            assert rates == [
                ("GST18", "0.1800", "2025-01-01"),
                ("GST5", "0.0500", "2025-01-01"),
                ("GST5", "0.1200", "2026-04-01"),
            ], rates

        await asyncio.to_thread(command.downgrade, config, "0007_tax_group_no_overlap")

        async with engine.begin() as conn:
            restored = [
                (row[0], row[1])
                for row in (
                    await conn.execute(
                        text(
                            "SELECT name, rate::text FROM tax_group WHERE restaurant_id = :r "
                            "ORDER BY name, rate"
                        ),
                        {"r": restaurant_id},
                    )
                ).all()
            ]
            assert restored == [
                ("GST 18% (packaged/beverage)", "0.1800"),
                ("GST 5% (restaurant, no ITC)", "0.0500"),
                ("GST 5% (restaurant, no ITC)", "0.1200"),
            ], restored

        await asyncio.to_thread(command.upgrade, config, "head")
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM tax_rate WHERE restaurant_id = :r"), {"r": restaurant_id}
            )
            await conn.execute(
                text("DELETE FROM tax_group WHERE restaurant_id = :r"), {"r": restaurant_id}
            )
            await conn.execute(text("DELETE FROM restaurant WHERE code = 'TAX1'"))
            await conn.execute(text("DELETE FROM organization WHERE slug = 'tax-co'"))
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- 0024


async def _logins_at_0023(url: str, organizations: dict[str, list[str]]) -> None:
    """Downgrade a fresh database to 0023 and write logins exactly as they were typed then."""
    from app.core.enums import UserAccountStatus
    from app.models.identity import UserAccount
    from app.models.tenancy import Organization

    config = _alembic_config(url)
    await asyncio.to_thread(command.downgrade, config, "0023_waiter_assignment")
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine)() as session:
            for slug, logins in organizations.items():
                organization = Organization(name=slug.title(), slug=slug)
                session.add(organization)
                await session.flush()
                for login in logins:
                    is_email = "@" in login
                    session.add(
                        UserAccount(
                            organization_id=organization.id,
                            email=login if is_email else None,
                            phone=None if is_email else login,
                            status=UserAccountStatus.ACTIVE,
                        )
                    )
            await session.commit()
    finally:
        await engine.dispose()


async def test_0024_stores_every_existing_login_one_way(fresh_database: str) -> None:
    """Logins typed before B4 are normalised once, so the spelling a person uses at the counter
    matches the row a manager created months ago (G-18)."""
    await _logins_at_0023(
        fresh_database,
        {"spice-garden": ["98765 43210", "09876500000", "+91 98765 11111", " Chef@Spice.Test "]},
    )

    await asyncio.to_thread(command.upgrade, _alembic_config(fresh_database), "head")

    engine = create_async_engine(fresh_database)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(text("SELECT email, phone FROM user_account"))
            stored = {value for row in rows for value in row if value is not None}
    finally:
        await engine.dispose()
    assert stored == {"+919876543210", "+919876500000", "+919876511111", "chef@spice.test"}


async def test_0024_stops_and_names_logins_that_become_one(fresh_database: str) -> None:
    """Two rows in one organization that are one phone number cannot both survive, and choosing
    which person keeps it is not a migration's call. It stops and says which."""
    await _logins_at_0023(
        fresh_database,
        {
            "spice-garden": ["98765 43210", "+91 98765 43210"],
            # The same number in another organization is fine (D1).
            "tandoor-house": ["9876543210"],
        },
    )

    with pytest.raises(Exception, match=r"\+919876543210"):
        await asyncio.to_thread(command.upgrade, _alembic_config(fresh_database), "head")

    # A migration that fails must still close its connection. `alembic/env.py` disposed of its
    # engine only on success, so this test left an asyncpg connection open, and pytest reported it
    # as an unraisable warning inside whichever test ran next (the B4a gate failed in
    # `test_idempotency.py`). Asked of the database directly, so the leak fails this test.
    engine = create_async_engine(fresh_database)
    try:
        async with engine.connect() as connection:
            others = await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                )
            )
    finally:
        await engine.dispose()
    assert others == 0, f"a failed migration left {others} connection(s) open"
