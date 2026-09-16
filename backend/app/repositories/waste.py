"""Queries over waste. Business rules live in the service, not here.

Three of these carry weight.

**`summary` groups by stage and then by reason, in one statement.** `docs/waste-model.md` is
explicit that a single total is "a number nobody can act on" — the report this module exists for
reads *"₹14,800 prep over-production (47%)"*, and that shape is a `GROUP BY` rather than four
queries and some Python.

**It reads `wastage_event`, never `stock_movement`.** The two are deliberately not the same
question: the ledger holds every movement including `staff_meal` and `complimentary`, which are
**not waste** and whose inclusion would poison the variance number this module exists to produce.
Summing the ledger by `type = 'wastage'` would give the same answer today and silently the wrong
one the moment a movement is written by any path other than this module's.

**Nothing here writes a stock movement.** That is `InventoryService`'s, called by `WastageService`
inside one transaction, so FEFO, per-batch cost and the append-only ledger stay in the one place
M05 built them.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.waste import WastageEvent, WastageReason
from app.repositories.base import RestaurantScopedRepository, page_size


@dataclass(frozen=True, slots=True)
class StageTotal:
    """One line of the report: a stage, a reason, what it cost and how many times."""

    stage: str
    reason_code: str
    reason_name: str
    events: int
    cost_value: Decimal


class WastageReasonRepository(RestaurantScopedRepository[WastageReason]):
    model = WastageReason

    async def list_all(self, *, include_inactive: bool = False) -> Sequence[WastageReason]:
        """Ordered by stage then name, because the logging screen groups by stage and a chef
        picking a reason at speed should find them in the same place every time."""
        query = self.scoped()
        if not include_inactive:
            query = query.where(WastageReason.is_active.is_(True))
        return (
            await self.session.scalars(query.order_by(WastageReason.stage, WastageReason.name))
        ).all()

    async def by_code(self, code: str) -> WastageReason | None:
        result = await self.session.scalars(self.scoped().where(WastageReason.code == code))
        return result.first()


class WastageEventRepository(RestaurantScopedRepository[WastageEvent]):
    model = WastageEvent

    async def list_page(
        self,
        *,
        business_date: date | None = None,
        stage: str | None = None,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[WastageEvent]:
        """Newest first. Ids are UUIDv7 and so time-ordered, which makes the id the cursor."""
        query = self.scoped().options(selectinload(WastageEvent.reason))
        if business_date is not None:
            query = query.where(WastageEvent.business_date == business_date)
        if stage is not None:
            query = query.join(
                WastageReason, WastageReason.id == WastageEvent.wastage_reason_id
            ).where(WastageReason.stage == stage)
        if after is not None:
            query = query.where(WastageEvent.id < after)
        return (
            await self.session.scalars(
                query.order_by(WastageEvent.id.desc()).limit(page_size(limit))
            )
        ).all()

    async def summary(self, *, since: date, until: date) -> list[StageTotal]:
        """What was lost, by stage and reason, over a business-date range.

        One statement whatever the range. The share of the total is computed by the caller from
        these rows rather than in SQL: a window function would round each share independently and
        the four stages would not add to a hundred, which is the first thing anybody checks.
        """
        rows = await self.session.execute(
            select(
                WastageReason.stage,
                WastageReason.code,
                WastageReason.name,
                func.count(WastageEvent.id),
                func.coalesce(func.sum(WastageEvent.cost_value), 0),
            )
            .join(WastageReason, WastageReason.id == WastageEvent.wastage_reason_id)
            .where(
                WastageEvent.restaurant_id == self.scope.restaurant_id,
                WastageEvent.business_date >= since,
                WastageEvent.business_date <= until,
            )
            .group_by(WastageReason.stage, WastageReason.code, WastageReason.name)
            .order_by(func.sum(WastageEvent.cost_value).desc())
        )
        return [
            StageTotal(
                stage=stage,
                reason_code=code,
                reason_name=name,
                events=int(events),
                cost_value=Decimal(str(cost)),
            )
            for stage, code, name, events, cost in rows.all()
        ]

    async def with_reason(self, event_id: uuid.UUID) -> WastageEvent | None:
        result = await self.session.scalars(
            self.scoped()
            .options(selectinload(WastageEvent.reason))
            .where(WastageEvent.id == event_id)
        )
        return result.first()
