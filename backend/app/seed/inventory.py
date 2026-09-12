"""Opening stock, so the ledger has something in it before anyone touches the app.

Three things are planted here and each is deliberate.

**An opening batch for every ingredient.** A storeroom with nothing in it makes the on-hand screen
an empty table, which demonstrates nothing and, worse, makes every subsequent consumption look like
a shortfall. The quantities are a plausible week's holding rather than a round number, so the screen
reads like a real storeroom rather than a fixture.

**One item deliberately near expiry**, so the expiry list has something to warn about without
anybody having to construct it. `docs/seed-data.md`'s principle: a demo that requires the
demonstrator to first create the problem is a demo of an empty product.

**One item deliberately negative.** This is the one that matters. A negative position means stock
was consumed that nobody recorded receiving — the cold-start reality
`docs/onboarding-cold-start.md` describes, and the single most useful thing this product can tell a
restaurant that has never kept records. The seed plants it so the banner is on screen the first
time anybody opens the app, rather than being a path somebody has to discover.

It is planted by *consuming* rather than by writing a negative movement directly, because that is
how it happens in life: stock goes out through the kitchen, and the delivery was never entered.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import MovementBasis
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.inventory import StockMovement
from app.models.stock import StockItem
from app.models.tenancy import Restaurant
from app.services.inventory import InventoryService

logger = logging.getLogger(__name__)

# Roughly a week's holding for a restaurant of this size, keyed by base unit. Not round numbers:
# a storeroom that holds exactly 10,000 g of everything reads as a fixture, and the point of the
# demo is that it reads as a kitchen.
_OPENING = {"g": Decimal("8400"), "ml": Decimal("6200"), "unit": Decimal("120")}

# The two planted signals, by stock item code.
_NEAR_EXPIRY = "PANEER"
# Consumed without a recorded delivery. Onion, because it is the thing a kitchen gets through
# fastest and the thing nobody writes down.
_UNRECORDED = "ONION"
_UNRECORDED_QUANTITY = Decimal("2000")


@dataclass(frozen=True, slots=True)
class InventorySummary:
    batches_created: int = 0
    negatives_planted: int = 0

    @property
    def created_nothing(self) -> bool:
        return not any((self.batches_created, self.negatives_planted))


async def seed_inventory(session: AsyncSession) -> InventorySummary:
    """Idempotent: if any movement exists for a restaurant, that restaurant is left alone.

    Re-running `make seed` must not stack a second week of opening stock on top of the first. The
    check is for *any* movement rather than for a marker row, because a ledger with rows in it has
    already been used and re-seeding it would corrupt somebody's real position.
    """
    restaurants = (await session.scalars(select(Restaurant))).all()
    batches = 0
    negatives = 0

    for restaurant in restaurants:
        existing = await session.scalar(
            select(func.count())
            .select_from(StockMovement)
            .where(StockMovement.restaurant_id == restaurant.id)
        )
        if existing:
            continue

        employee = (
            await session.scalars(
                select(Employee).where(Employee.organization_id == restaurant.organization_id)
            )
        ).first()
        if employee is None:
            continue

        actor = Actor(
            employee_id=employee.id,
            organization_id=restaurant.organization_id,
            restaurant_id=restaurant.id,
            full_name=employee.full_name,
            permissions=frozenset(),
            rank=100,
        )
        service = InventoryService(
            session,
            TenantScope(organization_id=restaurant.organization_id, restaurant_id=restaurant.id),
        )
        items = (
            await session.scalars(
                select(StockItem).where(
                    StockItem.restaurant_id == restaurant.id,
                    StockItem.kind == "ingredient",
                    StockItem.is_active.is_(True),
                )
            )
        ).all()

        now = datetime.now(UTC)
        for item in items:
            if item.code == _UNRECORDED:
                # Deliberately receives nothing. The consumption below is what makes it negative.
                continue
            quantity = _OPENING.get(str(item.base_unit), Decimal("1000"))
            expiry = None
            if item.code == _NEAR_EXPIRY:
                expiry = (now + timedelta(days=2)).date()
            await service.receive_stock(
                actor,
                stock_item_id=item.id,
                quantity=quantity,
                unit_cost=Decimal(str(item.current_unit_cost)),
                expiry_date=expiry,
                source="opening",
                occurred_at=now - timedelta(days=1),
            )
            batches += 1

        unrecorded = next((item for item in items if item.code == _UNRECORDED), None)
        if unrecorded is not None:
            # Consumed, not written negative by hand. This is how it happens in a real kitchen:
            # the onions went into the pot and the delivery note never reached the system.
            await service.consume(
                actor,
                stock_item_id=unrecorded.id,
                quantity=_UNRECORDED_QUANTITY,
                basis=MovementBasis.THEORETICAL,
                occurred_at=now,
            )
            negatives += 1

    return InventorySummary(batches_created=batches, negatives_planted=negatives)
