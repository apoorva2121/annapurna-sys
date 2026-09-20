"""The flag that lets a laptop show a populated report, and the rule that keeps it on the laptop.

Reports exclude demo organizations so seeded trading can never be mistaken for a restaurant's
books. The side effect, found by the owner on 2026-09-19, is that **nobody had ever seen a
populated report** — every screen rendered zeros in every environment, so there was nothing to give
feedback on.

`SEED_REVIEWABLE` clears the flag after everything has been generated. These tests are the guard
rails: the default must be unchanged, and the exception must not be available anywhere a real
restaurant's data might live.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.tenancy import Organization
from app.seed.identity import seed_identity
from app.seed.reviewable import FLAG, NotReviewableError, seed_reviewable, wanted


async def _demo_count(session: AsyncSession) -> int:
    found = await session.scalar(select(func.count(Organization.id)).where(Organization.is_demo))
    return int(found or 0)


class TestTheDefaultIsUnchanged:
    async def test_without_the_flag_nothing_happens(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`make seed` must keep producing a demo world excluded from reports.

        This is the test that matters most: the exception has to be something somebody asks for,
        never something they get by running the ordinary command.
        """
        monkeypatch.delenv(FLAG, raising=False)
        await seed_identity(db_session)
        await db_session.flush()
        before = await _demo_count(db_session)

        changed = await seed_reviewable(db_session)

        assert before > 0, "nothing was seeded — this test would otherwise pass vacuously"
        assert changed == 0
        assert await _demo_count(db_session) == before

    @pytest.mark.parametrize("value", ["", "0", "no", "false", "maybe"])
    def test_only_an_explicit_yes_counts(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        """A variable that happens to exist is not consent. `SEED_REVIEWABLE=0` must mean no."""
        monkeypatch.setenv(FLAG, value)

        assert wanted() is False


class TestTheGuard:
    async def test_it_is_refused_outside_a_local_environment(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Staging carries the demo world on purpose and production must never hold seeded trading.

        The refusal is the point. Clearing this flag is how demo figures start counting as a
        restaurant's takings, and there is no argument for that anywhere but a laptop.
        """
        monkeypatch.setenv(FLAG, "1")
        monkeypatch.setenv("ENV", "staging")
        # `Settings` refuses to build for staging without one — its own boot guard, firing before
        # this one. Supplied so the test reaches the refusal it is actually about.
        monkeypatch.setenv("JWT_SECRET", "not-the-committed-one-and-long-enough-to-pass")
        get_settings.cache_clear()

        try:
            with pytest.raises(NotReviewableError) as refused:
                await seed_reviewable(db_session)
        finally:
            monkeypatch.setenv("ENV", "local")
            monkeypatch.delenv("JWT_SECRET", raising=False)
            get_settings.cache_clear()

        # The message has to say why, not just no: whoever hits this is trying to demo something.
        assert "local" in str(refused.value)


class TestWhenItIsAskedFor:
    async def test_it_clears_the_flag_so_reports_can_see_the_trading(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(FLAG, "1")
        await seed_identity(db_session)
        await db_session.flush()
        assert await _demo_count(db_session) > 0

        changed = await seed_reviewable(db_session)

        assert changed > 0
        assert await _demo_count(db_session) == 0

    async def test_running_it_twice_is_harmless(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`make seed` is run casually and repeatedly."""
        monkeypatch.setenv(FLAG, "1")
        await seed_identity(db_session)
        await db_session.flush()
        await seed_reviewable(db_session)

        again = await seed_reviewable(db_session)

        assert again == 0
