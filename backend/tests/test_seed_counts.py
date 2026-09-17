"""The physical count the seed plants, so the variance screen opens on something.

Invariant 7 calls the gap between theoretical and actual consumption the core product insight. The
demo world had only the theoretical half — settlement wrote consumption from recipes, and nothing
ever counted a shelf — so the variance screen was empty and `docs/seed-data.md`'s signal 9 existed
only in the specification.

Each test is about a *state that cannot be demonstrated without it*, in the spirit of
`test_seed_customers.py`, rather than about a row count.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import StockCountStatus
from app.models.inventory import StockCount, StockCountLine, StockMovement
from app.models.stock import StockItem
from app.seed.counts import seed_counts
from app.seed.identity import seed_identity
from app.seed.inventory import seed_inventory
from app.seed.menu import seed_menu
from app.seed.setup import seed_setup
from app.seed.stock import seed_stock


@pytest.fixture
async def counted(db_session: AsyncSession) -> AsyncSession:
    await seed_identity(db_session)
    await seed_setup(db_session)
    await seed_menu(db_session)
    await seed_stock(db_session)
    await seed_inventory(db_session)
    await seed_counts(db_session)
    return db_session


async def _lines(session: AsyncSession, status: StockCountStatus) -> dict[str, StockCountLine]:
    rows = (
        await session.execute(
            select(StockItem.code, StockCountLine)
            .join(StockCountLine, StockCountLine.stock_item_id == StockItem.id)
            .join(StockCount, StockCount.id == StockCountLine.stock_count_id)
            .where(StockCount.status == status)
        )
    ).all()
    return dict(rows)  # type: ignore[arg-type]


async def test_an_approved_count_exists_so_the_variance_screen_is_not_empty(
    counted: AsyncSession,
) -> None:
    approved = (
        await counted.scalars(
            select(StockCount).where(StockCount.status == StockCountStatus.APPROVED)
        )
    ).all()
    assert approved, "no approved count: the variance screen would open on nothing"


async def test_the_count_shows_variance_in_both_directions_and_one_clean_line(
    counted: AsyncSession,
) -> None:
    """A sheet where every line is short reads as theft; one where every line is exact reads as a
    fixture. Both teach the wrong idea of what a normal count looks like."""
    lines = await _lines(counted, StockCountStatus.APPROVED)
    variances = [Decimal(str(line.variance_value)) for line in lines.values()]

    assert any(v < 0 for v in variances), "nothing short — the shelf always agreed with the book"
    assert any(v > 0 for v in variances), "nothing over — a count only ever finds losses"
    assert any(v == 0 for v in variances), "no line reconciled exactly"


async def test_signal_nine_lands_where_there_is_stock_to_lose(counted: AsyncSession) -> None:
    """`docs/seed-data.md` signal 9 is portion drift on makhani, and the first version of this
    seeder planted it on `PREP_MAKHANI` — a preparation, which `seed_inventory` gives no opening
    stock, so 12% of a zero book position was a variance of exactly nothing.

    What a storeroom observes instead is the gravy's *ingredients* running short."""
    lines = await _lines(counted, StockCountStatus.APPROVED)
    for code in ("CREAM", "TOMATO"):
        line = lines.get(code)
        assert line is not None, f"{code} is not on the count sheet"
        assert Decimal(str(line.variance_value)) < 0, f"{code} shows no shortfall"


async def test_approval_reached_the_ledger_as_adjustments(counted: AsyncSession) -> None:
    """Invariant 2: stock is a ledger and a correction is a new movement, never an edit. Approval
    is the only thing that writes them, so their absence would mean the count stopped at paper."""
    adjustments = (
        await counted.scalars(select(StockMovement).where(StockMovement.type == "adjustment"))
    ).all()
    assert adjustments, "an approved count wrote nothing to the ledger"


async def test_one_count_is_left_unfinished(counted: AsyncSession) -> None:
    """`docs/seed-data.md` asks for "a forgotten stock count" beside the missing feedback and the
    voided orders — the demo is meant to be plausible, not tidy."""
    drafts = (
        await counted.scalars(select(StockCount).where(StockCount.status == StockCountStatus.DRAFT))
    ).all()
    assert drafts, "every count was finished, which is not what a storeroom looks like"


async def test_running_the_seeder_twice_does_not_count_the_storeroom_again(
    counted: AsyncSession,
) -> None:
    """Re-counting an already-counted storeroom would write a second set of adjustments against a
    position somebody may have since corrected."""
    before = len((await counted.scalars(select(StockCount))).all())
    summary = await seed_counts(counted)
    after = len((await counted.scalars(select(StockCount))).all())

    assert summary.created_nothing
    assert before == after
