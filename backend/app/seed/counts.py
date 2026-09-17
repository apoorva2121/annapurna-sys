"""A physical count, so the variance screen has something to show.

**Why this exists.** Invariant 7 calls the gap between theoretical and actual consumption "the core
product insight": recipes say what a dish *should* have used, a physical count says what the shelf
*actually* holds, and the difference is the thing a restaurant is paying for. Until this seeder,
the demo world had one half of that and not the other — every settled order wrote theoretical
consumption, and nothing ever counted the shelf. The variance screen was empty, which demonstrates
nothing, and `docs/seed-data.md`'s signal 9 ("Butter Chicken consumes 12% more gravy than recipe",
proving *portion drift / theoretical-vs-actual*) was planted in the specification and absent from
the data.

**Two counts, because one of them is meant to be unfinished.** `docs/seed-data.md` §"Plausible, not
perfect" asks for "a forgotten stock count" alongside the missing feedback and the voided orders.
So one count is walked, submitted and approved — reaching the ledger as `adjustment` movements —
and a second is opened and left in draft, exactly as a count gets abandoned when service starts.

**Who approves.** `approve_count` refuses to let the person who walked the shelves accept their own
result, which is the storeroom's one real control. The seeder therefore needs two employees and
passes a different one to the approval, rather than working around the rule.

This is a *single* count, not the 120 days signal 9 really wants. Making that signal statistically
visible needs the generator M15 owns; this makes the screen honest in the meantime, and the
variance it plants points the right way.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import StockCountScope
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.inventory import StockCount
from app.models.stock import StockItem
from app.models.tenancy import Restaurant
from app.services.inventory import InventoryService

logger = logging.getLogger(__name__)

# The sheet somebody actually walks: the expensive things and the things that move fastest, not the
# whole storeroom. A partial count is also the honest scope — `StockCountScope` exists because a
# spot check of six items must never be extrapolated to the rest.
_COUNTED = ("PREP_MAKHANI", "PANEER", "BUTTER", "CREAM", "CASHEW", "TOMATO")

# What the shelf holds as a fraction of what the book says.
#
# `PREP_MAKHANI` is signal 9. The book believes the recipes; the shelf is 12% shorter, because
# Butter Chicken has been going out with a heavier ladle than the recipe writes down. That is the
# number `docs/seed-data.md` plants, and it is the one a variance report has to surface.
#
# The rest are small and in both directions, because a count sheet where every line is exact reads
# as a fixture and a count sheet where every line is short reads as theft. Two items are left at
# 1.00: some things really do reconcile, and a screen that never shows a clean line teaches the
# wrong lesson about what normal looks like.
_ACTUAL_FRACTION = {
    # Signal 9, and **not** on `PREP_MAKHANI` even though the signal is about gravy. A preparation
    # is made and used within the day, so `seed_inventory` gives opening stock to ingredients and
    # not to preparations: the gravy's book position is zero, and 12% of nothing is nothing. The
    # first version of this seeder put the signal there and planted a variance of ₹0.00.
    #
    # What a storeroom actually observes when a heavier ladle goes out is that the gravy's
    # *ingredients* run short against the book. Cream and tomato are the two that move most in
    # makhani, so the 12% lands there, which is both where it is visible and where it is true.
    "CREAM": Decimal("0.88"),
    "TOMATO": Decimal("0.88"),
    # Counted and reconciled. A sheet where every line has a variance reads as theft rather than as
    # a storeroom, and a screen that never shows a clean line teaches the wrong idea of normal.
    "PREP_MAKHANI": Decimal("1.00"),
    "PANEER": Decimal("0.97"),
    "BUTTER": Decimal("1.02"),
    "CASHEW": Decimal("0.94"),
}

# The forgotten one. Opened on a different corner of the storeroom and never finished.
_ABANDONED = ("GHEE", "ONION")


@dataclass(frozen=True, slots=True)
class CountSummary:
    counts_approved: int = 0
    counts_abandoned: int = 0
    lines_counted: int = 0

    @property
    def created_nothing(self) -> bool:
        return self.counts_approved == 0 and self.counts_abandoned == 0


def _actor(employee: Employee, restaurant: Restaurant) -> Actor:
    return Actor(
        employee_id=employee.id,
        organization_id=restaurant.organization_id,
        restaurant_id=restaurant.id,
        full_name=employee.full_name,
        permissions=frozenset(),
        rank=100,
    )


async def seed_counts(session: AsyncSession) -> CountSummary:
    """Idempotent per restaurant: a restaurant with any count already has one.

    The check is for an existing count rather than a marker, for the reason `seed_inventory`
    documents about movements — a storeroom that has been counted has been used, and re-counting it
    would write adjustments against somebody's real position.
    """
    approved = 0
    abandoned = 0
    lines = 0

    for restaurant in (await session.scalars(select(Restaurant))).all():
        existing = await session.scalar(
            select(func.count())
            .select_from(StockCount)
            .where(StockCount.restaurant_id == restaurant.id)
        )
        if existing:
            continue

        # Two, because nobody approves their own count.
        employees = (
            await session.scalars(
                select(Employee)
                .where(Employee.organization_id == restaurant.organization_id)
                .order_by(Employee.employee_code)
            )
        ).all()
        if len(employees) < 2:
            continue
        walker, approver = employees[0], employees[1]

        service = InventoryService(
            session,
            TenantScope(organization_id=restaurant.organization_id, restaurant_id=restaurant.id),
        )

        items = {
            item.code: item
            for item in (
                await session.scalars(
                    select(StockItem).where(StockItem.restaurant_id == restaurant.id)
                )
            ).all()
        }
        counted = [items[code] for code in _COUNTED if code in items]
        if not counted:
            continue

        count = await service.open_count(
            _actor(walker, restaurant),
            stock_item_ids=[item.id for item in counted],
            count_scope=StockCountScope.PARTIAL,
        )
        # `open_count` froze the book position on every line; what the shelf held is a fraction of
        # it. Read the lines back rather than recomputing the book, so the seeded variance is the
        # one the count itself recorded.
        refreshed = await service.counts.get_with_lines(count.id)
        if refreshed is None:  # pragma: no cover - open_count just created it
            continue
        code_of = {item.id: item.code for item in counted}
        on_the_shelf: dict[uuid.UUID, Decimal] = {}
        for line in refreshed.lines:
            fraction = _ACTUAL_FRACTION.get(code_of.get(line.stock_item_id, ""), Decimal("1"))
            # `str()` because `StockCountLine.system_quantity` is annotated `Mapped[object]` —
            # one of 68 Numeric columns in this codebase that are, so mypy cannot see it is a
            # Decimal. It is one at runtime. See the backlog row about invariant 3 and typing.
            book = Decimal(str(line.system_quantity))
            on_the_shelf[line.stock_item_id] = (book * fraction).quantize(Decimal("0.001"))
        await service.record_counted(count.id, counts=on_the_shelf)
        await service.submit_count(count.id)
        await service.approve_count(_actor(approver, restaurant), count.id)
        approved += 1
        lines += len(on_the_shelf)

        forgotten = [items[code] for code in _ABANDONED if code in items]
        if forgotten:
            await service.open_count(
                _actor(walker, restaurant),
                stock_item_ids=[item.id for item in forgotten],
                count_scope=StockCountScope.SPOT,
            )
            abandoned += 1

    summary = CountSummary(
        counts_approved=approved, counts_abandoned=abandoned, lines_counted=lines
    )
    logger.info("seed.counts.complete", extra={"summary": str(summary)})
    return summary
