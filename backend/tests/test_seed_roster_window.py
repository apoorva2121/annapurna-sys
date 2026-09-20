"""The roster and the trading must cover the same days, or every workload figure is wrong.

Found on 2026-09-19, when the owner asked to see the workload screen. `seed/generate.py` writes
**120 days** of orders; `seed/shifts.py` reached **three days back** and clocked only two of them.
`PerformanceRepository.worked()` reads hours from `shift_assignment`, so a workload period of a
month would have divided 120 days of orders by 2 days of attendance: every per-hour figure inflated
roughly sixtyfold, and attendance reading as though the whole team missed nearly every shift.

**That is worse than an empty screen.** Zeros are obviously nothing. These would have been
plausible numbers that were wrong, on the one module whose output can reach somebody's pay
(ADR 0011, `docs/workload-fairness.md`), and an owner shown that screen would have drawn
conclusions about real people from an artefact of the seed.

The fix is not a larger constant — a constant can drift again. The two windows now read the same
`SEED_DAYS`, and these tests are what stop somebody changing one of them alone.
"""

from __future__ import annotations

import pytest

from app.seed import generate, shifts


def test_the_roster_reaches_exactly_as_far_back_as_the_generated_trading() -> None:
    """The coupling, asserted rather than trusted to a comment.

    If these two ever differ again, a workload score divides one window by the other and the result
    is wrong in a way that looks fine.
    """
    assert shifts._days_back() == generate.DEFAULT_DAYS


def test_seed_days_shortens_the_roster_and_the_trading_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`make seed-small` sets `SEED_DAYS=7` for a laptop. It must shorten both.

    A version that shortened only the trading would leave a week of orders against four months of
    rostered hours — the same defect in the opposite direction, and just as plausible-looking.
    """
    monkeypatch.setenv("SEED_DAYS", "7")

    assert shifts._days_back() == 7


def test_the_default_is_the_generator_s_own_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing set, both fall back to the same number rather than to two constants."""
    monkeypatch.delenv("SEED_DAYS", raising=False)

    assert shifts._days_back() == generate.DEFAULT_DAYS
    assert generate.DEFAULT_DAYS == 120
