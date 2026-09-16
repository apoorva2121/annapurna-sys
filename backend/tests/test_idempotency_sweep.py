"""Expired idempotency keys are swept (ADR 0010, backlog-issues B10).

Expiry was honoured — an expired key can be claimed again — but nothing deleted old rows, so the
table grew by a row per money or stock write for ever. The sweep runs restaurant by restaurant,
each through the scoped repository, so it cannot reach another tenant's rows by construction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import IdempotencyState
from app.core.tenancy import TenantScope
from app.jobs.sweep_idempotency_keys import sweep
from app.models.identity import LoginAttempt
from app.models.orders import IdempotencyKey
from app.repositories.idempotency import IdempotencyKeyRepository
from tests.test_setup_endpoints import World, _world

NOW = datetime(2026, 9, 14, 3, 0, tzinfo=UTC)


async def _key(session: AsyncSession, world: World, key: str, *, expires_at: datetime) -> None:
    session.add(
        IdempotencyKey(
            restaurant_id=world.restaurant.id,
            key=key,
            endpoint="POST /api/v1/staff/goods-receipts",
            request_hash="0" * 64,
            state=IdempotencyState.COMPLETED,
            response_status=201,
            response_body={},
            expires_at=expires_at,
        )
    )
    await session.flush()


async def _left(session: AsyncSession) -> list[str]:
    return sorted((await session.scalars(select(IdempotencyKey.key))).all())


def _scope(world: World) -> TenantScope:
    return TenantScope(organization_id=world.organization.id, restaurant_id=world.restaurant.id)


class TestTheSweep:
    async def test_expired_keys_go_and_live_keys_stay(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "owner")
        await _key(db_session, world, "expired-an-hour-ago", expires_at=NOW - timedelta(hours=1))
        await _key(db_session, world, "live-for-another-hour", expires_at=NOW + timedelta(hours=1))

        removed = await IdempotencyKeyRepository(db_session, _scope(world)).sweep_expired(NOW)

        assert removed == 1
        assert await _left(db_session) == ["live-for-another-hour"]

    async def test_one_restaurants_sweep_leaves_another_restaurants_keys_alone(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _world(db_session, "owner")
        theirs = await _world(db_session, "owner", slug="tandoor-house")
        await _key(db_session, mine, "mine-expired-000001", expires_at=NOW - timedelta(hours=1))
        await _key(db_session, theirs, "theirs-expired-0001", expires_at=NOW - timedelta(hours=1))

        await IdempotencyKeyRepository(db_session, _scope(mine)).sweep_expired(NOW)

        assert await _left(db_session) == ["theirs-expired-0001"]

    async def test_the_job_sweeps_every_restaurant(self, db_session: AsyncSession) -> None:
        mine = await _world(db_session, "owner")
        theirs = await _world(db_session, "owner", slug="tandoor-house")
        await _key(db_session, mine, "mine-expired-000001", expires_at=NOW - timedelta(hours=1))
        await _key(db_session, theirs, "theirs-expired-0001", expires_at=NOW - timedelta(hours=1))
        await _key(db_session, theirs, "theirs-still-live-01", expires_at=NOW + timedelta(hours=1))

        removed = await sweep(db_session, NOW)

        assert removed == 2
        assert await _left(db_session) == ["theirs-still-live-01"]

    async def test_the_job_forgets_sign_in_attempts_older_than_a_day(
        self, db_session: AsyncSession
    ) -> None:
        """B5's `login_attempt` rows decide nothing after the longest window (minutes), and its
        model says they are swept with the keys. A day is the margin."""
        old = LoginAttempt(identifier_hash="a" * 64, ip_address=None, succeeded=False)
        recent = LoginAttempt(identifier_hash="b" * 64, ip_address=None, succeeded=False)
        db_session.add_all([old, recent])
        await db_session.flush()
        old.created_at = NOW - timedelta(days=1, minutes=1)
        recent.created_at = NOW - timedelta(hours=23)
        await db_session.flush()

        await sweep(db_session, NOW)

        kept = (await db_session.scalars(select(LoginAttempt.identifier_hash))).all()
        assert list(kept) == ["b" * 64]
