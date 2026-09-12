"""What the ledger's queries actually return. Chunk B of M05.

The FEFO ordering tests are the ones worth writing carefully. FEFO is easy to write, easy to
believe, and silently wrong in two specific ways — NULL expiry sorting first, and exhausted batches
still being offered — both of which produce plausible-looking results until food rots on a shelf.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MovementBasis, MovementType
from app.core.tenancy import TenantScope
from app.models.inventory import StockBatch, StockMovement
from app.models.stock import StockItem
from app.models.tenancy import Organization, Restaurant
from app.repositories.inventory import StockBatchRepository, StockMovementRepository

TODAY = date(2026, 9, 12)


class World:
    __slots__ = ("item", "restaurant", "scope")

    def __init__(self, restaurant: Restaurant, item: StockItem, scope: TenantScope) -> None:
        self.restaurant = restaurant
        self.item = item
        self.scope = scope


async def _world(session: AsyncSession, slug: str) -> World:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id, name=slug.title(), code=slug[:3].upper()
    )
    session.add(restaurant)
    await session.flush()
    item = StockItem(
        restaurant_id=restaurant.id,
        kind="ingredient",
        code="PANEER",
        name="Paneer",
        base_unit="g",
        current_unit_cost=Decimal("0.360000"),
        is_active=True,
    )
    session.add(item)
    await session.flush()
    return World(
        restaurant,
        item,
        TenantScope(organization_id=organization.id, restaurant_id=restaurant.id),
    )


async def _received(
    session: AsyncSession,
    world: World,
    *,
    code: str,
    quantity: str,
    expiry: date | None,
    cost: str = "0.360000",
    received_offset_days: int = 0,
) -> StockBatch:
    """A batch plus the receipt movement that put stock in it — always together.

    A batch without its receipt movement has `quantity_received` on paper and nothing on hand,
    which is exactly the state the product must never invent for itself.
    """
    batch = StockBatch(
        restaurant_id=world.restaurant.id,
        stock_item_id=world.item.id,
        batch_code=code,
        quantity_received=Decimal(quantity),
        unit_cost=Decimal(cost),
        received_at=datetime.now(UTC) + timedelta(days=received_offset_days),
        expiry_date=expiry,
        source="purchase",
    )
    session.add(batch)
    await session.flush()
    session.add(
        StockMovement(
            restaurant_id=world.restaurant.id,
            stock_batch_id=batch.id,
            stock_item_id=world.item.id,
            type=MovementType.RECEIPT,
            quantity_delta=Decimal(quantity),
            unit_cost=Decimal(cost),
            basis=MovementBasis.ACTUAL,
            occurred_at=datetime.now(UTC),
            business_date=TODAY,
        )
    )
    await session.flush()
    return batch


async def _consume(
    session: AsyncSession, world: World, batch: StockBatch, quantity: str, *, basis: str
) -> None:
    session.add(
        StockMovement(
            restaurant_id=world.restaurant.id,
            stock_batch_id=batch.id,
            stock_item_id=world.item.id,
            type=MovementType.CONSUMPTION,
            quantity_delta=Decimal(quantity),
            unit_cost=batch.unit_cost,
            basis=basis,
            occurred_at=datetime.now(UTC),
            business_date=TODAY,
        )
    )
    await session.flush()


class TestFefoSelection:
    async def test_the_soonest_expiry_is_offered_first(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "fefo-order")
        await _received(
            db_session, world, code="LATE", quantity="500", expiry=TODAY + timedelta(days=30)
        )
        await _received(
            db_session, world, code="SOON", quantity="500", expiry=TODAY + timedelta(days=2)
        )
        await _received(
            db_session, world, code="MID", quantity="500", expiry=TODAY + timedelta(days=10)
        )

        positions = await StockBatchRepository(db_session, world.scope).batches_for_consumption(
            world.item.id
        )

        assert [p.expiry_date for p in positions] == [
            TODAY + timedelta(days=2),
            TODAY + timedelta(days=10),
            TODAY + timedelta(days=30),
        ]

    async def test_an_undated_batch_is_used_after_every_dated_one(
        self, db_session: AsyncSession
    ) -> None:
        """Postgres sorts NULLs *first* on ASC by default.

        Without `NULLS LAST` this returns the undated batch before the perishable one — which is
        not merely a different order, it is the opposite of FEFO, and the perishable batch is the
        one that then rots.
        """
        world = await _world(db_session, "fefo-nulls")
        await _received(db_session, world, code="UNDATED", quantity="500", expiry=None)
        await _received(
            db_session, world, code="DATED", quantity="500", expiry=TODAY + timedelta(days=5)
        )

        positions = await StockBatchRepository(db_session, world.scope).batches_for_consumption(
            world.item.id
        )

        assert [p.expiry_date for p in positions] == [TODAY + timedelta(days=5), None]

    async def test_an_exhausted_batch_is_not_offered(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "fefo-empty")
        spent = await _received(
            db_session, world, code="SPENT", quantity="500", expiry=TODAY + timedelta(days=1)
        )
        await _consume(db_session, world, spent, "-500", basis=MovementBasis.THEORETICAL)
        await _received(
            db_session, world, code="FULL", quantity="500", expiry=TODAY + timedelta(days=9)
        )

        positions = await StockBatchRepository(db_session, world.scope).batches_for_consumption(
            world.item.id
        )

        # The spent batch expires sooner, so a selection that ignored the remaining quantity would
        # return it first and hand the caller nothing to consume.
        assert [p.remaining for p in positions] == [Decimal("500.0000")]

    async def test_an_item_with_no_batches_offers_nothing_rather_than_failing(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "fefo-none")

        positions = await StockBatchRepository(db_session, world.scope).batches_for_consumption(
            world.item.id
        )

        assert positions == []


class TestOnHand:
    async def test_it_is_the_sum_of_movements(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "onhand-sum")
        batch = await _received(db_session, world, code="B1", quantity="1000", expiry=None)
        await _consume(db_session, world, batch, "-250", basis=MovementBasis.THEORETICAL)
        await _consume(db_session, world, batch, "-100", basis=MovementBasis.ACTUAL)

        rows = await StockMovementRepository(db_session, world.scope).on_hand()

        assert len(rows) == 1
        # Both bases count towards the book. That is spec decision 1: what may never be summed
        # across bases is a *consumption* figure, not the position itself.
        assert rows[0].quantity == Decimal("650.0000")
        assert rows[0].code == "PANEER"

    async def test_a_negative_position_is_returned_not_hidden(
        self, db_session: AsyncSession
    ) -> None:
        """Spec decision 2. A negative is the most useful row this query can return: it means
        stock was consumed that nobody recorded receiving."""
        world = await _world(db_session, "onhand-negative")
        batch = await _received(db_session, world, code="B1", quantity="100", expiry=None)
        await _consume(db_session, world, batch, "-400", basis=MovementBasis.THEORETICAL)

        rows = await StockMovementRepository(db_session, world.scope).on_hand()

        assert [r.quantity for r in rows] == [Decimal("-300.0000")]

    async def test_an_item_that_nets_to_zero_is_hidden_by_default(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "onhand-zero")
        batch = await _received(db_session, world, code="B1", quantity="100", expiry=None)
        await _consume(db_session, world, batch, "-100", basis=MovementBasis.THEORETICAL)

        repository = StockMovementRepository(db_session, world.scope)

        assert await repository.on_hand() == []
        assert len(await repository.on_hand(include_zero=True)) == 1

    async def test_value_uses_each_batch_own_cost(self, db_session: AsyncSession) -> None:
        """Stock bought at two prices must not be valued at whichever cost appeared last."""
        world = await _world(db_session, "onhand-value")
        await _received(
            db_session, world, code="CHEAP", quantity="100", expiry=None, cost="0.200000"
        )
        await _received(
            db_session, world, code="DEAR", quantity="100", expiry=None, cost="0.400000"
        )

        rows = await StockMovementRepository(db_session, world.scope).on_hand()

        # 100 x 0.2 + 100 x 0.4 = 60, not 200 x 0.4 = 80.
        assert rows[0].value == Decimal("60.000000")

    async def test_another_restaurant_position_is_invisible(self, db_session: AsyncSession) -> None:
        mine = await _world(db_session, "onhand-mine")
        theirs = await _world(db_session, "onhand-theirs")
        await _received(db_session, theirs, code="T1", quantity="900", expiry=None)

        rows = await StockMovementRepository(db_session, mine.scope).on_hand()

        assert rows == []


class TestConsumptionByBasis:
    async def test_the_two_bases_are_reported_separately(self, db_session: AsyncSession) -> None:
        """Invariant 7. The signature takes one basis so a caller *cannot* ask for the sum."""
        world = await _world(db_session, "basis-split")
        batch = await _received(db_session, world, code="B1", quantity="1000", expiry=None)
        await _consume(db_session, world, batch, "-200", basis=MovementBasis.THEORETICAL)
        await _consume(db_session, world, batch, "-250", basis=MovementBasis.ACTUAL)

        repository = StockMovementRepository(db_session, world.scope)
        theoretical = await repository.consumption_by_basis(
            start=TODAY, end=TODAY, basis=MovementBasis.THEORETICAL
        )
        actual = await repository.consumption_by_basis(
            start=TODAY, end=TODAY, basis=MovementBasis.ACTUAL
        )

        assert theoretical[world.item.id] == Decimal("200.0000")
        assert actual[world.item.id] == Decimal("250.0000")
        # The variance is the caller's subtraction, deliberately: 50 g unaccounted for.
        assert actual[world.item.id] - theoretical[world.item.id] == Decimal("50.0000")

    async def test_a_window_outside_the_movements_returns_nothing(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "basis-window")
        batch = await _received(db_session, world, code="B1", quantity="500", expiry=None)
        await _consume(db_session, world, batch, "-100", basis=MovementBasis.THEORETICAL)

        found = await StockMovementRepository(db_session, world.scope).consumption_by_basis(
            start=TODAY + timedelta(days=1),
            end=TODAY + timedelta(days=7),
            basis=MovementBasis.THEORETICAL,
        )

        assert found == {}


class TestExpiry:
    async def test_only_dated_batches_with_stock_left_are_returned(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "expiry-list")
        await _received(
            db_session, world, code="SOON", quantity="100", expiry=TODAY + timedelta(days=2)
        )
        await _received(db_session, world, code="UNDATED", quantity="100", expiry=None)
        spent = await _received(
            db_session, world, code="SPENT", quantity="100", expiry=TODAY + timedelta(days=1)
        )
        await _consume(db_session, world, spent, "-100", basis=MovementBasis.THEORETICAL)
        await _received(
            db_session, world, code="FAR", quantity="100", expiry=TODAY + timedelta(days=90)
        )

        rows = await StockBatchRepository(db_session, world.scope).expiring_before(
            TODAY + timedelta(days=7)
        )

        # Undated is excluded (nothing to warn about), spent is excluded (nothing left to lose),
        # and the far one is outside the window.
        assert [r.expiry_date for r in rows] == [TODAY + timedelta(days=2)]


class TestNewestBatchForShortfall:
    async def test_it_returns_the_most_recently_received(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "shortfall-newest")
        await _received(
            db_session,
            world,
            code="OLD",
            quantity="100",
            expiry=None,
            cost="0.100000",
            received_offset_days=-5,
        )
        await _received(
            db_session,
            world,
            code="NEW",
            quantity="100",
            expiry=None,
            cost="0.900000",
            received_offset_days=0,
        )

        batch = await StockBatchRepository(db_session, world.scope).newest_batch_for_update(
            world.item.id
        )

        assert batch is not None
        # A shortfall is charged at the newest cost, which is the best available estimate of what
        # the unrecorded stock actually cost.
        assert batch.batch_code == "NEW"

    async def test_it_returns_none_when_the_item_has_never_been_received(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "shortfall-empty")

        assert (
            await StockBatchRepository(db_session, world.scope).newest_batch_for_update(
                world.item.id
            )
            is None
        )

    async def test_it_does_not_reach_another_restaurants_batch(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _world(db_session, "shortfall-mine")
        theirs = await _world(db_session, "shortfall-theirs")
        await _received(db_session, theirs, code="THEIRS", quantity="100", expiry=None)

        found = await StockBatchRepository(db_session, mine.scope).newest_batch_for_update(
            uuid.UUID(str(theirs.item.id))
        )

        assert found is None
