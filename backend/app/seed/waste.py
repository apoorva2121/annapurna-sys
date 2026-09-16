"""Wastage reasons, and a few days of waste, so the summary opens on something.

`seed/operations.yaml` has carried twelve reasons across the four stages since M00 and nothing has
read them until now. They are the P1 design and they are used verbatim, including the six marked
`requires_photo` — those are the six where a photograph is what makes the reason code honest, and
the flag is stored and not enforced until M11 owns `attachment` (`docs/modules/M09-waste-spec.md`
decision 4).

**What the events plant, and what they deliberately do not.** `docs/seed-data.md` has fourteen
planted signals and four of them are this module's — makhani gravy over-produced every Tue/Wed (1),
paneer expiring twice a month (2), staff meals (10) and comps (11). **The volume that makes those
readable is M15's**, the same line the orders seeder draws: a hundred and twenty days of history is
a generator, not a seeder. So this plants a handful across all four stages, shaped like those
signals so M15 has a pattern to scale rather than invent, and enough that the summary screen opens
on a number rather than on a zero.

Three things are deliberate beyond "some rows exist":

**Prep is the biggest line.** `docs/waste-model.md` puts prep at 4-8% of food cost and calls it "the
biggest and the least measured". A seed where the four stages came out level would quietly teach
whoever reads the screen that they are level.

**One event is left awaiting approval.** The reason marked `requires_approval` produces a row
nobody has signed, so the state exists on screen without a demonstrator having to construct it -
the same reasoning as M05's negative stock and M07's ₹50-short till.

**One day in the range has no waste at all.** `docs/seed-data.md` rule 3 asks for "a day the waste
log was skipped", and a summary that assumes every day has a row is exactly the bug perfectly clean
data hides.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.stock import StockItem
from app.models.tenancy import Restaurant
from app.models.waste import WastageEvent, WastageReason
from app.seed.setup import load_operations
from app.services.waste import WastageService

logger = logging.getLogger(__name__)

_FOR_RESTAURANT = "SG_KOREGAON"


@dataclass(frozen=True, slots=True)
class WasteSummarySeed:
    reasons_created: int = 0
    events_created: int = 0


# What gets thrown away, by which reason, how long ago, and how much — in base units, because the
# seeder speaks to the service the way a screen does and the screen sends its own unit flag.
#
# Weighted so prep is the biggest line, which is what `docs/waste-model.md` says it is in life.
# `days_ago=1` is deliberately absent: that is the day the log was skipped.
_EVENTS: tuple[tuple[str, str, int, str], ...] = (
    # Prep — the biggest and the least measured. Makhani gravy over-produced, planted signal 1.
    ("OVER_PREPARATION", "PANEER", 4, "900"),
    ("OVER_PREPARATION", "PANEER", 3, "1200"),
    ("TRIM_LOSS", "PANEER", 3, "300"),
    ("OVER_PREPARATION", "PANEER", 0, "800"),
    # Storage — paneer over-ordered on a Monday, planted signal 2. Needs approval, and does not
    # get it: the awaiting-approval state has to exist on screen without anybody constructing it.
    ("EXPIRED", "PANEER", 2, "600"),
    # Service — a dish sent back. Links to nothing: M08 does not book waste for a remake, because
    # the dish may be reheated rather than binned, and a person decides.
    ("WRONG_ORDER", "PANEER", 2, "250"),
    # Receiving — the cheapest money in the product, and the smallest line here.
    ("QUALITY_REJECT", "PANEER", 4, "400"),
)


async def seed_waste(session: AsyncSession, data: dict[str, Any] | None = None) -> WasteSummarySeed:
    """Reasons from `operations.yaml`, then a few days of events. Safe to run repeatedly.

    Does not commit — the caller owns the transaction, which is what lets the suite seed inside one
    it rolls back. Idempotent: a restaurant that already has waste is left alone, because waste in
    it is waste somebody logged.
    """
    data = data or load_operations()
    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == _FOR_RESTAURANT))
    if restaurant is None:
        return WasteSummarySeed()

    created = await _reasons(session, restaurant.id, data.get("wastage_reasons", []))

    existing = await session.scalar(
        select(func.count(WastageEvent.id)).where(WastageEvent.restaurant_id == restaurant.id)
    )
    if existing:
        return WasteSummarySeed(reasons_created=created)

    events = await _events(session, restaurant)
    summary = WasteSummarySeed(reasons_created=created, events_created=events)
    logger.info("seed.waste.complete", extra={"summary": summary})
    return summary


async def _reasons(session: AsyncSession, restaurant_id: Any, rows: list[dict[str, Any]]) -> int:
    """The twelve from `operations.yaml`, verbatim. Existing codes are left alone."""
    present = set(
        (
            await session.scalars(
                select(WastageReason.code).where(WastageReason.restaurant_id == restaurant_id)
            )
        ).all()
    )
    created = 0
    for row in rows:
        code = str(row["code"])
        if code in present:
            continue
        session.add(
            WastageReason(
                restaurant_id=restaurant_id,
                code=code,
                name=str(row["name"]),
                stage=str(row["stage"]),
                requires_photo=bool(row.get("requires_photo", False)),
                requires_approval=bool(row.get("requires_approval", False)),
            )
        )
        created += 1
    await session.flush()
    return created


async def _events(session: AsyncSession, restaurant: Restaurant) -> int:
    """A few days of waste, through the service — never by writing rows.

    The service is what pairs each event with its stock movement and computes the cost from the
    batches FEFO took it from. A seeder writing the rows itself would demo a cost the product never
    calculated, which is the same rule the orders seeder follows for a bill.
    """
    scope = TenantScope(organization_id=restaurant.organization_id, restaurant_id=restaurant.id)
    service = WastageService(session, scope)
    actor = await _actor(session, restaurant)
    if actor is None:
        return 0

    reasons = {
        reason.code: reason
        for reason in await session.scalars(
            select(WastageReason).where(WastageReason.restaurant_id == restaurant.id)
        )
    }
    items = {
        item.code: item
        for item in await session.scalars(
            select(StockItem).where(StockItem.restaurant_id == restaurant.id)
        )
    }

    now = datetime.now(UTC)
    created = 0
    for reason_code, item_code, days_ago, quantity in _EVENTS:
        reason = reasons.get(reason_code)
        item = items.get(item_code)
        if reason is None or item is None:
            # A reason or an item the seed does not have. Skipped rather than fatal: the seeder
            # must not fail a whole demo because one dish was renamed.
            continue
        await service.log(
            actor,
            stock_item_id=item.id,
            wastage_reason_id=reason.id,
            quantity=Decimal(quantity),
            occurred_at=now - timedelta(days=days_ago),
        )
        created += 1
    return created


async def _actor(session: AsyncSession, restaurant: Restaurant) -> Actor | None:
    """Whoever logs it. The chef, because in a real kitchen the chef is who notices."""
    employee = await session.scalar(
        select(Employee)
        .where(Employee.organization_id == restaurant.organization_id)
        .order_by(Employee.employee_code)
        .limit(1)
    )
    if employee is None:
        return None
    return Actor(
        employee_id=employee.id,
        organization_id=restaurant.organization_id,
        restaurant_id=restaurant.id,
        full_name=employee.full_name,
        permissions=frozenset({"wastage.log"}),
        rank=0,
        session_id=None,
    )
