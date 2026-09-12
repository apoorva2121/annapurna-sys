"""Queries over the stock ledger. Business rules live in the service, not here.

The two that matter are `on_hand` and `batches_for_consumption`, and both are written as single
SQL statements rather than as a fetch-then-loop in Python. That is not a micro-optimisation: a
Python loop over movements would be O(movements) in memory for a table that grows forever, and it
would be wrong under concurrency because the rows it read are not locked.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import aliased, selectinload

from app.core.enums import MovementType
from app.models.inventory import StockBatch, StockCount, StockCountLine, StockMovement
from app.models.stock import StockItem
from app.repositories.base import RestaurantScopedRepository, page_size


@dataclass(frozen=True, slots=True)
class OnHandRow:
    """One item's derived position. Nothing here is stored; every field is computed."""

    stock_item_id: uuid.UUID
    code: str
    name: str
    base_unit: str
    quantity: Decimal
    value: Decimal


@dataclass(frozen=True, slots=True)
class BatchPosition:
    """A batch and what is left of it, for FEFO selection."""

    batch_id: uuid.UUID
    unit_cost: Decimal
    remaining: Decimal
    expiry_date: date | None


class StockBatchRepository(RestaurantScopedRepository[StockBatch]):
    model = StockBatch

    async def get_by_code(self, batch_code: str) -> StockBatch | None:
        result = await self.session.scalars(
            self.scoped().where(StockBatch.batch_code == batch_code)
        )
        return result.first()

    async def batches_for_consumption(self, stock_item_id: uuid.UUID) -> list[BatchPosition]:
        """Batches with stock left, first-expired-first-out, **locked for update**.

        Two things here are load-bearing.

        **`NULLS LAST`.** A batch with no expiry date must be used *after* every dated one, not
        before. Postgres sorts NULLs first on ASC by default, so omitting this would consume the
        undated batch first and leave the perishable one to rot — the exact opposite of FEFO.

        **`with_for_update` on the batch rows.** Two cooks consuming the same paneer at the same
        moment must not both read "800 g left" and both take 500 g. Locking the batch rows
        serialises them, so the second transaction reads the position the first one left behind.
        The lock is taken on `stock_batch` rather than on the movements because the batch is the
        thing being contended for, and it is a stable row to lock — movements are inserted, so
        there is nothing there to lock until it is too late.

        Batches that are already empty or negative are excluded: there is nothing to take from
        them, and including them would spread one consumption across a long tail of exhausted rows.

        **Two statements, not one, and Postgres leaves no choice** — `SELECT ... FOR UPDATE` is
        rejected outright when combined with `GROUP BY`, so the remaining quantity cannot be
        aggregated in the locking query. Locking first and aggregating second is also the correct
        order: once this transaction holds the batch rows, no other writer can reach them, so the
        movement sums read afterwards cannot move underneath it. The lock is the serialisation
        point; the aggregate merely reports what it found there.
        """
        locked = await self.session.execute(
            select(StockBatch.id, StockBatch.unit_cost, StockBatch.expiry_date)
            .where(
                StockBatch.restaurant_id == self.scope.restaurant_id,
                StockBatch.stock_item_id == stock_item_id,
            )
            .order_by(StockBatch.expiry_date.asc().nulls_last(), StockBatch.received_at.asc())
            .with_for_update()
        )
        ordered = locked.all()
        if not ordered:
            return []

        totals = await self.session.execute(
            select(
                StockMovement.stock_batch_id,
                func.coalesce(func.sum(StockMovement.quantity_delta), 0),
            )
            .where(
                StockMovement.restaurant_id == self.scope.restaurant_id,
                StockMovement.stock_batch_id.in_([row[0] for row in ordered]),
            )
            .group_by(StockMovement.stock_batch_id)
        )
        remaining_by_batch = {row[0]: row[1] for row in totals.all()}

        return [
            BatchPosition(
                batch_id=row[0],
                unit_cost=row[1],
                remaining=remaining_by_batch[row[0]],
                expiry_date=row[2],
            )
            for row in ordered
            if remaining_by_batch.get(row[0], Decimal(0)) > 0
        ]

    async def newest_batch_for_update(self, stock_item_id: uuid.UUID) -> StockBatch | None:
        """The batch a shortfall is charged against when nothing has stock left.

        Consumption is never refused (spec decision 2), so when every batch is exhausted the
        remainder has to land somewhere. It lands on the most recently received batch, whose
        `unit_cost` is the best available estimate of what the missing stock actually cost.
        """
        result = await self.session.scalars(
            self.scoped()
            .where(StockBatch.stock_item_id == stock_item_id)
            .order_by(StockBatch.received_at.desc())
            .limit(1)
            .with_for_update()
        )
        return result.first()

    async def expiring_before(
        self, cutoff: date, *, limit: int | None = None
    ) -> list[BatchPosition]:
        """Dated batches with stock left, soonest first. Backed by `ix_stock_batch_expiry`."""
        remaining = func.coalesce(func.sum(StockMovement.quantity_delta), 0)
        statement = (
            select(
                StockBatch.id,
                StockBatch.unit_cost,
                remaining.label("remaining"),
                StockBatch.expiry_date,
            )
            .join(StockMovement, StockMovement.stock_batch_id == StockBatch.id)
            .where(
                StockBatch.restaurant_id == self.scope.restaurant_id,
                StockBatch.expiry_date.isnot(None),
                StockBatch.expiry_date <= cutoff,
            )
            .group_by(StockBatch.id, StockBatch.unit_cost, StockBatch.expiry_date)
            .having(remaining > 0)
            .order_by(StockBatch.expiry_date.asc())
            .limit(page_size(limit))
        )
        rows = await self.session.execute(statement)
        return [
            BatchPosition(batch_id=row[0], unit_cost=row[1], remaining=row[2], expiry_date=row[3])
            for row in rows.all()
        ]


class StockMovementRepository(RestaurantScopedRepository[StockMovement]):
    model = StockMovement

    def _on_hand_select(self) -> Select[tuple[uuid.UUID, object, object]]:
        """`SUM(quantity_delta)` per item — the only definition of on-hand there is.

        The value column sums `delta * unit_cost` rather than multiplying the total quantity by a
        single cost, because a item's stock is generally several batches bought at different
        prices. Multiplying at the end would value today's stock at whichever cost happened to
        appear last.
        """
        return select(
            StockMovement.stock_item_id,
            func.sum(StockMovement.quantity_delta).label("quantity"),
            func.sum(StockMovement.quantity_delta * StockMovement.unit_cost).label("value"),
        ).where(StockMovement.restaurant_id == self.scope.restaurant_id)

    async def on_hand(
        self, *, stock_item_ids: Sequence[uuid.UUID] | None = None, include_zero: bool = False
    ) -> list[OnHandRow]:
        """Every item's derived position, joined to the item so a screen can render it.

        `include_zero=False` hides items that have netted to exactly zero, which is the common
        case for a storeroom with hundreds of items and a handful in play. **Negatives are never
        hidden** — a negative position is the most useful thing this query can return, because it
        means stock was consumed that nobody recorded receiving (spec decision 2).
        """
        totals = self._on_hand_select().group_by(StockMovement.stock_item_id).subquery()
        item = aliased(StockItem)
        statement = (
            select(
                item.id,
                item.code,
                item.name,
                item.base_unit,
                func.coalesce(totals.c.quantity, 0),
                func.coalesce(totals.c.value, 0),
            )
            .join(totals, totals.c.stock_item_id == item.id)
            .where(item.restaurant_id == self.scope.restaurant_id)
            .order_by(item.name)
        )
        if stock_item_ids is not None:
            statement = statement.where(item.id.in_(list(stock_item_ids)))
        if not include_zero:
            statement = statement.where(totals.c.quantity != 0)
        rows = await self.session.execute(statement)
        return [
            OnHandRow(
                stock_item_id=row[0],
                code=row[1],
                name=row[2],
                base_unit=row[3],
                quantity=row[4],
                value=row[5],
            )
            for row in rows.all()
        ]

    async def quantity_for_item(self, stock_item_id: uuid.UUID) -> Decimal:
        """One item's position. Returns zero when the item has never moved."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(StockMovement.quantity_delta), 0)).where(
                StockMovement.restaurant_id == self.scope.restaurant_id,
                StockMovement.stock_item_id == stock_item_id,
            )
        )
        return Decimal(str(result.scalar_one()))

    async def consumption_by_basis(
        self, *, start: date, end: date, basis: str
    ) -> dict[uuid.UUID, Decimal]:
        """Consumption over a business-date window, for **one basis only**.

        The signature takes a single `basis` deliberately. Invariant 7's failure mode is a helper
        that sums both and returns one number, so this function is shaped to make that impossible
        to ask for — a caller wanting the variance calls it twice and subtracts, which is the
        arithmetic it should be doing anyway.
        """
        rows = await self.session.execute(
            select(
                StockMovement.stock_item_id,
                func.sum(func.abs(StockMovement.quantity_delta)),
            )
            .where(
                StockMovement.restaurant_id == self.scope.restaurant_id,
                StockMovement.type == MovementType.CONSUMPTION,
                StockMovement.basis == basis,
                StockMovement.business_date >= start,
                StockMovement.business_date <= end,
            )
            .group_by(StockMovement.stock_item_id)
        )
        return {row[0]: row[1] for row in rows.all()}

    async def for_item(
        self, stock_item_id: uuid.UUID, *, limit: int | None = None
    ) -> Sequence[StockMovement]:
        result = await self.session.scalars(
            self.scoped()
            .where(StockMovement.stock_item_id == stock_item_id)
            .order_by(StockMovement.occurred_at.desc())
            .limit(page_size(limit))
        )
        return result.all()


class StockCountRepository(RestaurantScopedRepository[StockCount]):
    model = StockCount

    async def get_with_lines(self, count_id: uuid.UUID) -> StockCount | None:
        result = await self.session.scalars(
            self.scoped().where(StockCount.id == count_id).options(selectinload(StockCount.lines))
        )
        return result.first()

    async def get_for_update(self, count_id: uuid.UUID) -> StockCount | None:
        """Locked, because approval posts movements and must not run twice concurrently."""
        result = await self.session.scalars(
            self.scoped().where(StockCount.id == count_id).with_for_update()
        )
        return result.first()

    async def list_recent(self, *, limit: int | None = None) -> Sequence[StockCount]:
        result = await self.session.scalars(
            self.scoped().order_by(StockCount.counted_at.desc()).limit(page_size(limit))
        )
        return result.all()

    async def lines_of(self, count_id: uuid.UUID) -> Sequence[StockCountLine]:
        result = await self.session.scalars(
            select(StockCountLine).where(
                and_(
                    StockCountLine.restaurant_id == self.scope.restaurant_id,
                    StockCountLine.stock_count_id == count_id,
                )
            )
        )
        return result.all()
