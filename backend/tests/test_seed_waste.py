"""The reasons and the waste the seed plants, so M09's screens open on something.

`docs/seed-data.md`'s principle, once more: a demo that opens on an empty summary and a reason list
somebody has to type is a demo of an empty product. These tests stop the planted state quietly
disappearing — and because the seeder goes through `WastageService`, they also prove a seeded event
is costed by exactly the code a real one is.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MovementType, WastageStage
from app.models.inventory import StockMovement
from app.models.tenancy import Restaurant
from app.models.waste import WastageEvent, WastageReason
from app.seed.identity import seed_identity
from app.seed.inventory import seed_inventory
from app.seed.menu import seed_menu
from app.seed.setup import seed_setup
from app.seed.stock import seed_stock
from app.seed.waste import seed_waste
from app.services.waste import REF_TYPE


@pytest.fixture
async def seeded(db_session: AsyncSession) -> AsyncSession:
    await seed_identity(db_session)
    await seed_setup(db_session)
    await seed_menu(db_session)
    await seed_stock(db_session)
    await seed_inventory(db_session)
    return db_session


async def _koregaon(session: AsyncSession) -> Restaurant:
    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == "SG_KOREGAON"))
    assert restaurant is not None
    return restaurant


async def test_the_twelve_reasons_arrive_across_all_four_stages(seeded: AsyncSession) -> None:
    """They have been in `seed/operations.yaml` since M00 and nothing read them until M09."""
    summary = await seed_waste(seeded)
    restaurant = await _koregaon(seeded)

    assert summary.reasons_created == 12
    reasons = (
        await seeded.scalars(
            select(WastageReason).where(WastageReason.restaurant_id == restaurant.id)
        )
    ).all()
    stages = {reason.stage for reason in reasons}
    assert stages == {
        WastageStage.RECEIVING,
        WastageStage.STORAGE,
        WastageStage.PREP,
        WastageStage.SERVICE,
    }


async def test_the_photo_flags_are_carried_verbatim(seeded: AsyncSession) -> None:
    """Six of the twelve want a photograph, and the seed does not quietly drop them to make M09's
    unenforced flag look tidy. The flag is stored and honoured the day M11 lands."""
    await seed_waste(seeded)
    restaurant = await _koregaon(seeded)

    wanting = (
        await seeded.scalars(
            select(WastageReason.code).where(
                WastageReason.restaurant_id == restaurant.id,
                WastageReason.requires_photo.is_(True),
            )
        )
    ).all()

    assert set(wanting) == {
        "SHORT_DELIVERY",
        "QUALITY_REJECT",
        "EXPIRED",
        "SPOILAGE",
        "STORAGE_FAILURE",
        "CUSTOMER_RETURN",
    }


async def test_the_summary_opens_on_a_number_rather_than_a_zero(seeded: AsyncSession) -> None:
    summary = await seed_waste(seeded)
    restaurant = await _koregaon(seeded)

    assert summary.events_created > 0
    events = (
        await seeded.scalars(
            select(WastageEvent).where(WastageEvent.restaurant_id == restaurant.id)
        )
    ).all()
    assert all(Decimal(str(event.cost_value)) > 0 for event in events), (
        "a seeded event with no cost means the seeder wrote rows instead of calling the service"
    )


async def test_prep_is_the_biggest_line(seeded: AsyncSession) -> None:
    """`docs/waste-model.md` puts prep at 4-8% of food cost and calls it the biggest and the least
    measured. A seed where the four stages came out level would quietly teach whoever reads the
    screen that they are level."""
    await seed_waste(seeded)
    restaurant = await _koregaon(seeded)

    rows = await seeded.execute(
        select(WastageReason.stage, WastageEvent.cost_value)
        .join(WastageReason, WastageReason.id == WastageEvent.wastage_reason_id)
        .where(WastageEvent.restaurant_id == restaurant.id)
    )
    by_stage: dict[str, Decimal] = {}
    for stage, cost in rows.all():
        by_stage[stage] = by_stage.get(stage, Decimal("0")) + Decimal(str(cost))

    assert by_stage[WastageStage.PREP] == max(by_stage.values())


async def test_every_seeded_event_has_its_movement(seeded: AsyncSession) -> None:
    """The rule the whole module rests on, checked against seeded data as well as written data:
    never an event without its movement."""
    await seed_waste(seeded)
    restaurant = await _koregaon(seeded)

    events = (
        await seeded.scalars(
            select(WastageEvent.id).where(WastageEvent.restaurant_id == restaurant.id)
        )
    ).all()
    movements = (
        await seeded.scalars(
            select(StockMovement.ref_id).where(
                StockMovement.restaurant_id == restaurant.id,
                StockMovement.ref_type == REF_TYPE,
                StockMovement.type == MovementType.WASTAGE,
            )
        )
    ).all()

    assert set(events) == set(movements)


async def test_one_event_is_left_awaiting_approval(seeded: AsyncSession) -> None:
    """So the state exists on screen without a demonstrator constructing it — the same reasoning
    as M05's negative stock and M07's till counted ₹50 short."""
    await seed_waste(seeded)
    restaurant = await _koregaon(seeded)

    rows = await seeded.execute(
        select(WastageEvent.approved_at)
        .join(WastageReason, WastageReason.id == WastageEvent.wastage_reason_id)
        .where(
            WastageEvent.restaurant_id == restaurant.id,
            WastageReason.requires_approval.is_(True),
        )
    )
    unapproved = [approved_at for (approved_at,) in rows.all() if approved_at is None]

    assert unapproved, "nothing is awaiting approval, so that state cannot be demonstrated"


async def test_a_day_in_the_range_has_no_waste_at_all(seeded: AsyncSession) -> None:
    """`docs/seed-data.md` rule 3 asks for "a day the waste log was skipped". Perfectly clean data
    hides the bugs real data finds, and a summary assuming every day has a row is one of them."""
    await seed_waste(seeded)
    restaurant = await _koregaon(seeded)

    days = set(
        (
            await seeded.scalars(
                select(WastageEvent.business_date).where(
                    WastageEvent.restaurant_id == restaurant.id
                )
            )
        ).all()
    )
    span = (max(days) - min(days)).days + 1

    assert len(days) < span, "every day in the range has waste, so no day was skipped"


async def test_seeding_again_logs_no_second_round_of_waste(seeded: AsyncSession) -> None:
    """Waste already in a restaurant is waste somebody logged. Re-running the seed must not double
    the ledger, which it would: every event is a stock consumption."""
    first = await seed_waste(seeded)
    second = await seed_waste(seeded)

    assert first.events_created > 0
    assert second.events_created == 0
    assert second.reasons_created == 0
