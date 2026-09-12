"""The rules for moving stock. Every write to the ledger goes through here.

Four rules, and they are why this file exists rather than routes calling repositories:

**1 · A batch and its receipt movement are written together, always.** A batch alone is a paper
quantity with nothing on hand — the exact fiction invariant 2 exists to prevent. Nothing in this
service creates one without the other.

**2 · A consumption is never refused for insufficient stock** (spec decision 2, approved). Refusing
would mean M07 cannot settle an order because the storeroom paperwork is behind — the system would
stop a restaurant taking money over a bookkeeping gap. Instead the shortfall is recorded, on-hand
goes negative, and the negative is surfaced. That is not a tolerated bug: it is the most useful
signal this product emits, because it means stock is being consumed that nobody recorded receiving,
which is precisely the cold-start reality `docs/onboarding-cold-start.md` describes.

**3 · Cost travels with the stock, not with the clock.** A movement copies its batch's `unit_cost`,
so what a consumption cost is what that stock actually cost, not what the item is worth today.

**4 · `business_date` is computed, never assumed.** ADR 0004: a restaurant closing at 2am books that
consumption to the day before. `date.today()` here would be wrong for every late-night restaurant
in the country, and wrong by five and a half hours for all of them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.business_day import business_date_of
from app.core.enums import MovementBasis, MovementType
from app.core.errors import AppError, NotFoundError
from app.core.tenancy import TenantScope
from app.models.audit import AuditLog
from app.models.inventory import StockBatch, StockMovement
from app.models.tenancy import Restaurant
from app.repositories.inventory import (
    OnHandRow,
    StockBatchRepository,
    StockMovementRepository,
)
from app.repositories.stock import StockItemRepository

# A movement that consumes must be one of these. Kept as a set rather than checked inline so the
# list is visible in one place when M09 (waste) and M07 (orders) start calling in.
_CONSUMING_TYPES = frozenset(
    {
        MovementType.CONSUMPTION,
        MovementType.WASTAGE,
        MovementType.STAFF_MEAL,
        MovementType.COMPLIMENTARY,
    }
)


def _dec(value: object) -> Decimal:
    """Numeric columns are declared `Mapped[object]` across this codebase, so a value read back
    off a model is statically `object` even though it is always a `Decimal` at runtime. One
    conversion helper rather than a cast at every call site, and it goes through `str` so a float
    that somehow reached the column becomes an exact Decimal rather than a binary approximation."""
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class ConsumptionLine:
    """One batch's share of a consumption, and what it cost."""

    batch_id: uuid.UUID
    quantity: Decimal
    unit_cost: Decimal

    @property
    def value(self) -> Decimal:
        return self.quantity * self.unit_cost


@dataclass(frozen=True, slots=True)
class ConsumptionResult:
    """What a consumption actually did, including the part it could not cover.

    `shortfall` is the quantity that had no batch to come from. It is returned rather than raised
    so the caller — M07's settlement, eventually — can carry on and let the alert surface it.
    """

    lines: tuple[ConsumptionLine, ...]
    shortfall: Decimal

    @property
    def total_value(self) -> Decimal:
        return sum((line.value for line in self.lines), Decimal("0"))


class InventoryService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self.batches = StockBatchRepository(session, scope)
        self.movements = StockMovementRepository(session, scope)
        self.items = StockItemRepository(session, scope)

    # ------------------------------------------------------------------ helpers

    async def _restaurant(self) -> Restaurant:
        restaurant = await self.session.get(Restaurant, self.scope.restaurant_id)
        if restaurant is None:  # pragma: no cover - the scope cannot name a missing restaurant
            raise NotFoundError("restaurant_not_found", "This restaurant no longer exists.")
        return restaurant

    async def business_date_now(self, moment: datetime | None = None) -> date:
        """The business date an instant belongs to, in the restaurant's own timezone.

        Every movement this service writes goes through here rather than through `date.today()`,
        which is the single most likely place for a five-and-a-half-hour error to enter.
        """
        restaurant = await self._restaurant()
        return business_date_of(
            moment or datetime.now(UTC), restaurant.timezone, restaurant.business_day_start
        )

    async def _require_item(self, stock_item_id: uuid.UUID) -> Any:
        item = await self.items.get(stock_item_id)
        if item is None:
            raise NotFoundError(
                "stock_item_not_found",
                "That stock item does not exist at this restaurant.",
                {"stock_item_id": str(stock_item_id)},
            )
        return item

    def _audit(
        self,
        actor: Actor,
        action: str,
        entity_id: uuid.UUID,
        new_value: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                restaurant_id=actor.restaurant_id,
                actor_employee_id=actor.employee_id,
                action=action,
                entity_type="stock_movement",
                entity_id=entity_id,
                old_value=None,
                new_value=new_value,
            )
        )

    def _movement(
        self,
        *,
        batch: StockBatch,
        stock_item_id: uuid.UUID,
        movement_type: str,
        quantity_delta: Decimal,
        unit_cost: Decimal,
        basis: str,
        occurred_at: datetime,
        business_date: date,
        actor: Actor | None,
        ref_type: str | None = None,
        ref_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> StockMovement:
        movement = StockMovement(
            restaurant_id=self.scope.restaurant_id,
            stock_batch_id=batch.id,
            stock_item_id=stock_item_id,
            type=movement_type,
            quantity_delta=quantity_delta,
            unit_cost=unit_cost,
            basis=basis,
            occurred_at=occurred_at,
            business_date=business_date,
            actor_employee_id=actor.employee_id if actor else None,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note,
        )
        self.session.add(movement)
        return movement

    # ------------------------------------------------------------------ receive

    async def receive_stock(
        self,
        actor: Actor,
        *,
        stock_item_id: uuid.UUID,
        quantity: Decimal,
        unit_cost: Decimal,
        batch_code: str | None = None,
        expiry_date: date | None = None,
        storage_location: str | None = None,
        source: str = "purchase",
        occurred_at: datetime | None = None,
    ) -> StockBatch:
        """Stock arrives: one batch and its receipt movement, in one transaction.

        `basis` is `actual` — somebody physically counted this in off a delivery. Receipts are the
        anchor the whole variance calculation rests on, which is why an unrecorded one shows up
        later as a negative rather than as nothing at all.
        """
        if quantity <= 0:
            raise AppError(
                "invalid_quantity",
                "A receipt must be for more than zero. To correct a mistake, record an adjustment.",
            )
        if unit_cost < 0:
            raise AppError("invalid_cost", "A unit cost cannot be negative.")

        await self._require_item(stock_item_id)
        moment = occurred_at or datetime.now(UTC)
        business_date = await self.business_date_now(moment)

        batch = StockBatch(
            restaurant_id=self.scope.restaurant_id,
            stock_item_id=stock_item_id,
            batch_code=batch_code or await self._next_batch_code(business_date),
            quantity_received=quantity,
            unit_cost=unit_cost,
            received_at=moment,
            expiry_date=expiry_date,
            storage_location=storage_location,
            source=source,
        )
        self.session.add(batch)
        await self.session.flush()

        self._movement(
            batch=batch,
            stock_item_id=stock_item_id,
            movement_type=MovementType.RECEIPT,
            quantity_delta=quantity,
            unit_cost=unit_cost,
            basis=MovementBasis.ACTUAL,
            occurred_at=moment,
            business_date=business_date,
            actor=actor,
        )
        await self.session.flush()
        self._audit(
            actor,
            "stock.received",
            batch.id,
            {"stock_item_id": str(stock_item_id), "quantity": str(quantity)},
        )
        return batch

    async def _next_batch_code(self, business_date: date) -> str:
        """A readable, unique-per-restaurant code when the caller does not supply one.

        Date-prefixed so a human reading a shelf label can tell roughly when it arrived, with a
        short random tail because two deliveries of the same item on one day are ordinary.
        """
        return f"{business_date:%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"

    # ------------------------------------------------------------------ consume

    async def consume(
        self,
        actor: Actor | None,
        *,
        stock_item_id: uuid.UUID,
        quantity: Decimal,
        basis: str,
        movement_type: str = MovementType.CONSUMPTION,
        ref_type: str | None = None,
        ref_id: uuid.UUID | None = None,
        occurred_at: datetime | None = None,
        note: str | None = None,
    ) -> ConsumptionResult:
        """Take `quantity` out of stock, FEFO, **never refusing**.

        The walk is: take from the soonest-expiring batch that has something left, then the next,
        until the requested quantity is covered. If the batches run out first, the remainder is
        still recorded — charged to the most recently received batch at its cost, because that is
        the best available estimate of what the missing stock cost. On-hand goes negative and the
        on-hand screen says so.

        If the item has never been received at all there is no batch to charge, so a zero-quantity
        `opening` batch is created to hold the shortfall. That batch is a placeholder and says so
        in its code: the alternative is a nullable `stock_batch_id`, which would weaken the
        movement's tenant-safe composite foreign key for every row in the table to accommodate a
        case the product wants to make loud rather than easy.
        """
        if quantity <= 0:
            raise AppError("invalid_quantity", "A consumption must be for more than zero.")
        if movement_type not in _CONSUMING_TYPES:
            raise AppError(
                "invalid_movement_type",
                f"{movement_type} does not take stock out. Use an adjustment instead.",
            )

        await self._require_item(stock_item_id)
        moment = occurred_at or datetime.now(UTC)
        business_date = await self.business_date_now(moment)

        outstanding = quantity
        lines: list[ConsumptionLine] = []

        for position in await self.batches.batches_for_consumption(stock_item_id):
            if outstanding <= 0:
                break
            taken = min(outstanding, position.remaining)
            batch = await self.session.get(StockBatch, position.batch_id)
            if batch is None:  # pragma: no cover - locked a moment ago
                continue
            self._movement(
                batch=batch,
                stock_item_id=stock_item_id,
                movement_type=movement_type,
                quantity_delta=-taken,
                unit_cost=_dec(position.unit_cost),
                basis=basis,
                occurred_at=moment,
                business_date=business_date,
                actor=actor,
                ref_type=ref_type,
                ref_id=ref_id,
                note=note,
            )
            lines.append(
                ConsumptionLine(
                    batch_id=position.batch_id,
                    quantity=taken,
                    unit_cost=_dec(position.unit_cost),
                )
            )
            outstanding -= taken

        if outstanding > 0:
            await self._record_shortfall(
                actor,
                stock_item_id=stock_item_id,
                quantity=outstanding,
                basis=basis,
                movement_type=movement_type,
                occurred_at=moment,
                business_date=business_date,
                ref_type=ref_type,
                ref_id=ref_id,
                lines=lines,
            )

        await self.session.flush()
        return ConsumptionResult(lines=tuple(lines), shortfall=max(outstanding, Decimal("0")))

    async def _record_shortfall(
        self,
        actor: Actor | None,
        *,
        stock_item_id: uuid.UUID,
        quantity: Decimal,
        basis: str,
        movement_type: str,
        occurred_at: datetime,
        business_date: date,
        ref_type: str | None,
        ref_id: uuid.UUID | None,
        lines: list[ConsumptionLine],
    ) -> None:
        batch = await self.batches.newest_batch_for_update(stock_item_id)
        if batch is None:
            item = await self._require_item(stock_item_id)
            batch = StockBatch(
                restaurant_id=self.scope.restaurant_id,
                stock_item_id=stock_item_id,
                batch_code=f"UNRECORDED-{uuid.uuid4().hex[:8].upper()}",
                quantity_received=Decimal("0"),
                unit_cost=_dec(item.current_unit_cost),
                received_at=occurred_at,
                source="opening",
            )
            self.session.add(batch)
            await self.session.flush()

        self._movement(
            batch=batch,
            stock_item_id=stock_item_id,
            movement_type=movement_type,
            quantity_delta=-quantity,
            unit_cost=_dec(batch.unit_cost),
            basis=basis,
            occurred_at=occurred_at,
            business_date=business_date,
            actor=actor,
            ref_type=ref_type,
            ref_id=ref_id,
            note=(
                "Consumed without a recorded receipt. On-hand is negative by this amount until a "
                "receipt or a stock count explains it."
            ),
        )
        lines.append(
            ConsumptionLine(batch_id=batch.id, quantity=quantity, unit_cost=_dec(batch.unit_cost))
        )

    # ------------------------------------------------------------------ adjust

    async def adjust(
        self,
        actor: Actor,
        *,
        stock_item_id: uuid.UUID,
        quantity_delta: Decimal,
        reason: str,
        occurred_at: datetime | None = None,
    ) -> StockMovement:
        """A deliberate correction. Always `actual`, always reasoned, always audited.

        An adjustment is the one movement a human invents rather than observes, which makes it the
        one an insider would use to erase a shortfall. So the reason is mandatory, the audit row is
        written here, and `MovementType.ADJUSTMENT` keeps it separately visible in every report —
        a variance that hides its adjustments is a variance somebody has already edited.
        """
        if quantity_delta == 0:
            raise AppError("invalid_quantity", "An adjustment of zero changes nothing.")
        if not reason.strip():
            raise AppError(
                "reason_required",
                "An adjustment needs a reason. It is the only movement nobody observed.",
            )

        await self._require_item(stock_item_id)
        moment = occurred_at or datetime.now(UTC)
        business_date = await self.business_date_now(moment)

        batch = await self.batches.newest_batch_for_update(stock_item_id)
        if batch is None:
            item = await self._require_item(stock_item_id)
            batch = StockBatch(
                restaurant_id=self.scope.restaurant_id,
                stock_item_id=stock_item_id,
                batch_code=f"OPENING-{uuid.uuid4().hex[:8].upper()}",
                quantity_received=Decimal("0"),
                unit_cost=_dec(item.current_unit_cost),
                received_at=moment,
                source="opening",
            )
            self.session.add(batch)
            await self.session.flush()

        movement = self._movement(
            batch=batch,
            stock_item_id=stock_item_id,
            movement_type=MovementType.ADJUSTMENT,
            quantity_delta=quantity_delta,
            unit_cost=_dec(batch.unit_cost),
            basis=MovementBasis.ACTUAL,
            occurred_at=moment,
            business_date=business_date,
            actor=actor,
            note=reason.strip(),
        )
        await self.session.flush()
        self._audit(
            actor,
            "stock.adjusted",
            movement.id,
            {
                "stock_item_id": str(stock_item_id),
                "quantity_delta": str(quantity_delta),
                "reason": reason.strip(),
            },
        )
        return movement

    # ------------------------------------------------------------------ reads

    async def on_hand(self, *, include_zero: bool = False) -> list[OnHandRow]:
        return await self.movements.on_hand(include_zero=include_zero)

    async def expiring(self, *, within_days: int = 7) -> list[Any]:
        cutoff = await self.business_date_now()
        return await self.batches.expiring_before(cutoff + timedelta(days=within_days))
