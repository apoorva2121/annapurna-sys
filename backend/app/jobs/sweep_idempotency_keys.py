"""`make sweep-keys` — i.e. `python -m app.jobs.sweep_idempotency_keys`: delete expired keys.

ADR 0010 says keys expire after 24 hours, "swept by a nightly job". The project has no scheduler
yet, so this is the job, run by hand or by the host's cron until one exists (backlog-issues B10).

Restaurant by restaurant, each through the scoped repository: a sweep cannot reach another tenant's
rows by construction, which is CLAUDE.md invariant 1 held even for maintenance. Its own engine and
one transaction, like `app.seed`.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.tenancy import TenantScope
from app.models.tenancy import Restaurant
from app.repositories.account import LoginAttemptRepository
from app.repositories.idempotency import IdempotencyKeyRepository

logger = logging.getLogger("app.jobs.sweep_idempotency_keys")


# Sign-in attempts decide nothing after the longest throttle window (minutes, B5); a day is margin.
LOGIN_ATTEMPTS_KEPT = timedelta(days=1)


async def sweep(session: AsyncSession, now: datetime) -> int:
    """Every restaurant's expired keys, one scoped delete each, then sign-in attempts older than a
    day (they belong to no tenant). Returns how many idempotency keys went."""
    restaurants = await session.execute(select(Restaurant.id, Restaurant.organization_id))
    removed = 0
    for restaurant_id, organization_id in restaurants.tuples().all():
        scope = TenantScope(organization_id=organization_id, restaurant_id=restaurant_id)
        removed += await IdempotencyKeyRepository(session, scope).sweep_expired(now)
    attempts = await LoginAttemptRepository(session).sweep_older_than(now - LOGIN_ATTEMPTS_KEPT)
    logger.info("login_attempt.swept", extra={"removed": attempts})
    return removed


async def _main() -> None:
    engine = create_async_engine(get_settings().database_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            removed = await sweep(session, datetime.now(UTC))
            await session.commit()
        logger.info("idempotency.swept", extra={"removed": removed})
    finally:
        await engine.dispose()


def run() -> int:
    configure_logging()
    asyncio.run(_main())
    return 0


if __name__ == "__main__":
    sys.exit(run())
