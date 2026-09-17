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
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.business_day import business_date_of
from app.core.enums import MovementBasis, MovementType, StockCountScope, StockCountStatus
from app.core.errors import AppError, NotFoundError
from app.core.tenancy import TenantScope
from app.models.audit import AuditLog
from app.models.inventory import StockBatch, StockCount, StockCountLine, StockMovement
from app.models.stock import PreparationProfile
from app.models.tenancy import Restaurant
from app.repositories.inventory import (
    OnHandRow,
    StockBatchRepository,
    StockCountRepository,
    StockMovementRepository,
)
from app.repositories.stock import RecipeRepository, StockItemRepository
from app.services.purchase_units import to_base_units, unusual_price_problem

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
        self.recipes = RecipeRepository(session, scope)
        self.counts = StockCountRepository(session, scope)

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

    async def _in_base_units(
        self, item: Any, quantity: Decimal, unit_cost: Decimal, *, confirmed: bool
    ) -> tuple[Decimal, Decimal]:
        """What was typed on the invoice, as the ledger holds it (backlog-issues B12e).

        The supplier sells by the kilo and `stock_movements` is in grams (invariant 5). One
        conversion, here, so no screen does the arithmetic and no float crosses the boundary.
        The sanity check is the owner's: a plate of cabbage costing more than a car came from a
        price typed against the wrong unit, where 40 was a plausible number and the unit was not.
        """
        # `StockItem.ingredient` is lazy="raise", so the profile is read deliberately and only
        # when the form asked for a conversion - not on every delivery.
        with_profile = await self.items.get_with_profile(item.id)
        profile = with_profile.ingredient if with_profile is not None else None
        if profile is None:
            raise AppError(
                "stock_receipt.no_purchase_unit",
                f"{item.name} is not bought by a separate unit, so a delivery of it is counted "
                f"in {item.base_unit}.",
                status_code=422,
            )
        factor = _dec(profile.purchase_to_base)
        base_quantity, base_price = to_base_units(quantity, unit_cost, factor)
        if not confirmed:
            current = item.current_unit_cost
            problem = unusual_price_problem(
                item_name=item.name,
                purchase_unit=profile.purchase_unit,
                purchase_to_base=factor,
                base_price=base_price,
                current_unit_cost=_dec(current) if current is not None else None,
            )
            if problem is not None:
                raise AppError("stock_receipt.unusual_price", problem, status_code=422)
        return base_quantity, base_price

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
        item: Any = None,
        per_purchase_unit: bool = False,
        confirm_unusual_price: bool = False,
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

        # A caller that already loaded the item under this scope passes it, so a delivery reads each
        # item once rather than twice (backlog-issues B9). The shortcut is trusted only for this
        # restaurant's own item: matching ids alone would let a caller hand over another tenant's
        # row and skip the scoped lookup entirely (invariant 1). Anything else is looked up here.
        if (
            item is None
            or item.id != stock_item_id
            or item.restaurant_id != self.scope.restaurant_id
        ):
            item = await self._require_item(stock_item_id)
        if per_purchase_unit:
            quantity, unit_cost = await self._in_base_units(
                item, quantity, unit_cost, confirmed=confirm_unusual_price
            )
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

    async def quantity_in_base_units(self, stock_item_id: uuid.UUID, quantity: Decimal) -> Decimal:
        """A quantity typed in the item's purchase unit, as the ledger holds it.

        The quantity half of `_in_base_units`, for callers that carry no price. M09's waste form is
        the first: a cook thinks in half a kilo of paneer, not five hundred grams, so the screen
        labels its presets in the purchase unit and the **server** does the one conversion — the
        same rule the receiving form follows, and for the same reason. A quantity divided by a
        thousand in a browser is the float round-trip invariant 3 forbids.

        There is no price to sanity-check here, so none of `_in_base_units`'s unusual-price
        machinery applies; the two are deliberately not merged, because a shared function with half
        its parameters unused is how the price check eventually gets skipped by the caller that
        does have one.
        """
        item = await self._require_item(stock_item_id)
        with_profile = await self.items.get_with_profile(item.id)
        profile = with_profile.ingredient if with_profile is not None else None
        if profile is None:
            raise AppError(
                "stock.no_purchase_unit",
                f"{item.name} is not bought by a separate unit, so it is counted in "
                f"{item.base_unit}.",
                status_code=422,
            )
        base_quantity, _ = to_base_units(quantity, Decimal("0"), _dec(profile.purchase_to_base))
        return base_quantity

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
            # Through the scoped repository, not `session.get`. The id came from a scoped query
            # so this is safe today, but `session.get` fetches by primary key with no tenant
            # filter at all — and an unscoped read sitting in the hot path of the product's
            # most-written table is how the #1 bug class gets reintroduced by the next person to
            # edit this loop.
            batch = await self.batches.get(position.batch_id)
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

    # ------------------------------------------------------------------ production

    async def produce_batch(
        self,
        actor: Actor,
        *,
        stock_item_id: uuid.UUID,
        quantity: Decimal,
        occurred_at: datetime | None = None,
    ) -> StockBatch:
        """Make a preparation: consume the inputs **and** create the output, atomically.

        Either both halves land or neither does. A production that consumed its inputs and failed
        to create its output would destroy stock on the books; one that created its output without
        consuming would invent it. Both are worse than the operation simply failing, which is why
        there is no partial path through here.

        The output's `unit_cost` is **what the inputs actually cost**, divided by what came out.
        Not the recipe's frozen cost and not the item's current price: this batch of gravy cost what
        this batch of onions cost, and that is the number every dish made from it should carry.

        Yield loss is implicit and correct. If the inputs total 1,200 g and the batch yields
        1,000 g, the output costs 20% more per gram than its inputs did — which is exactly what
        reduction does to a sauce.
        """
        if quantity <= 0:
            raise AppError("invalid_quantity", "A production must make more than zero.")

        item = await self._require_item(stock_item_id)
        profile = await self.session.get(PreparationProfile, stock_item_id)
        if profile is None:
            raise AppError(
                "not_a_preparation",
                f"{item.name} is an ingredient, not a preparation. Receive it rather than make it.",
            )
        recipe = await self.recipes.current_for_preparation(stock_item_id)
        if recipe is None:
            raise AppError(
                "no_current_recipe",
                f"{item.name} has no current recipe, so there is nothing to make it from.",
                {"stock_item_id": str(stock_item_id)},
            )

        batch_yield = _dec(profile.batch_yield)
        scale = quantity / batch_yield
        moment = occurred_at or datetime.now(UTC)
        business_date = await self.business_date_now(moment)

        loaded = await self.recipes.get_with_lines(recipe.id)
        if loaded is None:  # pragma: no cover - fetched a moment ago
            raise AppError("no_current_recipe", "That recipe disappeared while it was in use.")

        expiry: date | None = None
        if profile.shelf_life_hours:
            expiry = (moment + timedelta(hours=int(profile.shelf_life_hours))).date()

        # **The output batch is created BEFORE the inputs are consumed, and that ordering is the
        # fix to a real defect.** The first version referenced the consumption movements to
        # `recipe.id`, which meant every batch of gravy ever made shared one reference — so
        # "show me the movements this production wrote" returned every production of that recipe
        # since the beginning, and M13's requirement that a metric drills through to *its own*
        # rows was quietly unmeetable. The batch is the production, so the batch's id is the
        # reference. Its cost is set below, once the inputs have been priced.
        output = StockBatch(
            restaurant_id=self.scope.restaurant_id,
            stock_item_id=stock_item_id,
            batch_code=await self._next_batch_code(business_date),
            quantity_received=quantity,
            unit_cost=Decimal("0"),
            received_at=moment,
            expiry_date=expiry,
            source="production",
        )
        self.session.add(output)
        await self.session.flush()

        input_cost = Decimal("0")
        for line in loaded.lines:
            consumed = await self.consume(
                actor,
                stock_item_id=line.component_id,
                quantity=_dec(line.quantity) * scale,
                basis=MovementBasis.THEORETICAL,
                ref_type="production_batch",
                ref_id=output.id,
                occurred_at=moment,
            )
            input_cost += consumed.total_value

        # `stock_batch` carries no append-only trigger — only `stock_movement` does — so settling
        # the cost here is legitimate rather than a workaround. Nothing has read it in between:
        # this is all one transaction.
        output.unit_cost = input_cost / quantity

        self._movement(
            batch=output,
            stock_item_id=stock_item_id,
            movement_type=MovementType.PRODUCTION,
            quantity_delta=quantity,
            unit_cost=_dec(output.unit_cost),
            basis=MovementBasis.ACTUAL,
            occurred_at=moment,
            business_date=business_date,
            actor=actor,
            ref_type="production_batch",
            ref_id=output.id,
        )
        await self.session.flush()
        self._audit(
            actor,
            "stock.produced",
            output.id,
            {
                "stock_item_id": str(stock_item_id),
                "quantity": str(quantity),
                "input_cost": str(input_cost),
            },
        )
        return output

    # ------------------------------------------------------------------ counts

    async def open_count(
        self,
        actor: Actor,
        *,
        stock_item_ids: Sequence[uuid.UUID],
        count_scope: str = StockCountScope.FULL,
        occurred_at: datetime | None = None,
    ) -> StockCount:
        """Start a count sheet, freezing the book position on every line as it is written.

        `system_quantity` is captured now and never recomputed. The ledger keeps moving while
        somebody walks the storeroom with a clipboard, and a variance recalculated at approval
        against a book that has since changed is not the variance anybody observed.
        """
        if not stock_item_ids:
            raise AppError("no_items", "A count needs at least one item to count.")
        # Deduplicated, order preserved. `uq_stock_count_line_count_item` would otherwise turn a
        # client that sent the same item twice into an IntegrityError — a 500 for something that
        # is obviously harmless and obviously the caller's typo.
        stock_item_ids = list(dict.fromkeys(stock_item_ids))

        moment = occurred_at or datetime.now(UTC)
        count = StockCount(
            restaurant_id=self.scope.restaurant_id,
            counted_at=moment,
            business_date=await self.business_date_now(moment),
            scope=count_scope,
            status=StockCountStatus.DRAFT,
            counted_by=actor.employee_id,
        )
        self.session.add(count)
        await self.session.flush()

        for stock_item_id in stock_item_ids:
            await self._require_item(stock_item_id)
            system = await self.movements.quantity_for_item(stock_item_id)
            self.session.add(
                StockCountLine(
                    restaurant_id=self.scope.restaurant_id,
                    stock_count_id=count.id,
                    stock_item_id=stock_item_id,
                    system_quantity=system,
                    # Floored at zero, not copied. A negative book position is meaningful — stock
                    # went out that nobody recorded coming in, which the seed plants deliberately
                    # and `docs/onboarding-cold-start.md` calls the most useful thing this product
                    # can tell a restaurant with no records. A negative *count* is not: a shelf
                    # cannot hold minus four kilos, and `ck_stock_count_line_counted` says so.
                    #
                    # Copying the book across meant that opening a count on the one item most worth
                    # counting raised CheckViolationError and reached the storeman as "Something
                    # went wrong". Zero is also what they will write down, and it leaves the whole
                    # negative position as the variance, which is the number that matters.
                    counted_quantity=max(system, Decimal("0")),
                    variance_value=Decimal("0"),
                )
            )
        await self.session.flush()
        return count

    async def record_counted(
        self, count_id: uuid.UUID, *, counts: dict[uuid.UUID, Decimal]
    ) -> StockCount:
        """Write what was actually on the shelf, and value the gap in rupees."""
        count = await self.counts.get_with_lines(count_id)
        if count is None:
            raise NotFoundError("stock_count_not_found", "That stock count does not exist here.")
        if count.status != StockCountStatus.DRAFT:
            raise AppError(
                "count_not_draft",
                "A count can only be edited while it is a draft. A submitted count is fixed.",
            )

        for line in count.lines:
            if line.stock_item_id not in counts:
                continue
            counted = counts[line.stock_item_id]
            if counted < 0:
                raise AppError("invalid_quantity", "A counted quantity cannot be negative.")
            item = await self._require_item(line.stock_item_id)
            line.counted_quantity = counted
            # Negative means less on the shelf than the book claims, which is the direction that
            # costs money. Valued at the item's current cost rather than a batch's: stock that has
            # gone missing is not attributable to any one batch, precisely because it is missing.
            line.variance_value = (counted - _dec(line.system_quantity)) * _dec(
                item.current_unit_cost
            )
        await self.session.flush()
        return count

    async def submit_count(self, count_id: uuid.UUID) -> StockCount:
        count = await self.counts.get_for_update(count_id)
        if count is None:
            raise NotFoundError("stock_count_not_found", "That stock count does not exist here.")
        if count.status != StockCountStatus.DRAFT:
            raise AppError("count_not_draft", "This count has already been submitted.")
        count.status = StockCountStatus.SUBMITTED
        await self.session.flush()
        return count

    async def approve_count(self, actor: Actor, count_id: uuid.UUID) -> StockCount:
        """Approval is the only thing that reaches the ledger.

        Two rules the storeroom depends on.

        **Nobody approves their own count.** The person who walked the shelves and the person who
        accepts the result must differ, because a count is the one document that can make a
        shortfall official — and if one person can do both, the control is decorative. The database
        carries the same constraint, so it holds even for a path that forgets to ask.

        **Approval cannot run twice.** The count is locked and its status checked under that lock,
        so two approvals racing cannot both post adjustments and double the correction.
        """
        count = await self.counts.get_for_update(count_id)
        if count is None:
            raise NotFoundError("stock_count_not_found", "That stock count does not exist here.")
        if count.status == StockCountStatus.APPROVED:
            raise AppError("count_already_approved", "This count has already been approved.")
        if count.status != StockCountStatus.SUBMITTED:
            raise AppError(
                "count_not_submitted", "A count must be submitted before it can be approved."
            )
        if count.counted_by is not None and count.counted_by == actor.employee_id:
            raise AppError(
                "self_approval",
                "A count must be approved by somebody other than the person who counted it.",
                status_code=403,
            )

        for line in await self.counts.lines_of(count_id):
            delta = _dec(line.counted_quantity) - _dec(line.system_quantity)
            if delta == 0:
                continue
            await self.adjust(
                actor,
                stock_item_id=line.stock_item_id,
                quantity_delta=delta,
                reason=f"Stock count {count.business_date:%Y-%m-%d}: {line.reason or 'counted'}",
                occurred_at=count.counted_at,
            )

        count.status = StockCountStatus.APPROVED
        count.approved_by = actor.employee_id
        await self.session.flush()
        self._audit(
            actor, "stock.count_approved", count.id, {"business_date": str(count.business_date)}
        )
        return count
