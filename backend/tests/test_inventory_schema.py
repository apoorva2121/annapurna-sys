"""The guarantees migration 0015 makes at the database, not in a service.

These are the rules that must hold even when a future path forgets to ask, so every one of them is
asserted against a real Postgres rather than against a repository's good intentions. If any of
these can be violated, every number M13 computes from the ledger is fiction.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MovementBasis, MovementType
from app.models.inventory import StockBatch, StockMovement
from app.models.stock import StockItem
from app.models.tenancy import Organization, Restaurant


async def _restaurant(session: AsyncSession, slug: str) -> Restaurant:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id, name=slug.title(), code=slug[:2].upper()
    )
    session.add(restaurant)
    await session.flush()
    return restaurant


async def _item(session: AsyncSession, restaurant: Restaurant, code: str = "PANEER") -> StockItem:
    item = StockItem(
        restaurant_id=restaurant.id,
        kind="ingredient",
        code=code,
        name=code.title(),
        base_unit="g",
        current_unit_cost=Decimal("0.360000"),
        is_active=True,
    )
    session.add(item)
    await session.flush()
    return item


async def _batch(
    session: AsyncSession, restaurant: Restaurant, item: StockItem, *, code: str = "B1"
) -> StockBatch:
    batch = StockBatch(
        restaurant_id=restaurant.id,
        stock_item_id=item.id,
        batch_code=code,
        quantity_received=Decimal("1000.0000"),
        unit_cost=Decimal("0.360000"),
        received_at=datetime.now(UTC),
        source="purchase",
    )
    session.add(batch)
    await session.flush()
    return batch


async def _movement(
    session: AsyncSession,
    restaurant: Restaurant,
    item: StockItem,
    batch: StockBatch,
    *,
    delta: str = "1000.0000",
) -> StockMovement:
    movement = StockMovement(
        restaurant_id=restaurant.id,
        stock_batch_id=batch.id,
        stock_item_id=item.id,
        type=MovementType.RECEIPT,
        quantity_delta=Decimal(delta),
        unit_cost=Decimal("0.360000"),
        basis=MovementBasis.ACTUAL,
        occurred_at=datetime.now(UTC),
        business_date=date(2026, 9, 12),
    )
    session.add(movement)
    await session.flush()
    return movement


class TestTheLedgerIsAppendOnly:
    """Invariant 2, enforced by Postgres.

    As a repository convention this is one careless `session.merge()` away from silent violation,
    and afterwards no test can see it — the row simply looks different. So the database refuses.
    """

    async def test_updating_a_movement_is_refused(self, db_session: AsyncSession) -> None:
        restaurant = await _restaurant(db_session, "append-one")
        item = await _item(db_session, restaurant)
        batch = await _batch(db_session, restaurant, item)
        movement = await _movement(db_session, restaurant, item, batch)

        with pytest.raises(DBAPIError) as raised:
            await db_session.execute(
                text("UPDATE stock_movement SET quantity_delta = 1 WHERE id = :id"),
                {"id": movement.id},
            )
        assert "append-only" in str(raised.value)
        # The message names the remedy, because whoever hits this is mid-change and needs to know
        # what to do instead of merely that they may not.
        assert "adjustment" in str(raised.value)

    async def test_deleting_a_movement_is_refused(self, db_session: AsyncSession) -> None:
        restaurant = await _restaurant(db_session, "append-two")
        item = await _item(db_session, restaurant)
        batch = await _batch(db_session, restaurant, item)
        movement = await _movement(db_session, restaurant, item, batch)

        with pytest.raises(DBAPIError) as raised:
            await db_session.execute(
                text("DELETE FROM stock_movement WHERE id = :id"), {"id": movement.id}
            )
        assert "append-only" in str(raised.value)


class TestTenantSafetyIsStructural:
    """CLAUDE.md calls cross-tenant leakage the #1 bug class in this product.

    Everywhere else it is prevented by a repository taking the tenant scope. Here it is prevented
    by a composite foreign key, so it holds even for a path that never goes through a repository —
    a migration, a seed script, or psql.
    """

    async def test_a_batch_cannot_reference_another_restaurants_item(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _restaurant(db_session, "tenant-mine")
        theirs = await _restaurant(db_session, "tenant-theirs")
        their_item = await _item(db_session, theirs)

        db_session.add(
            StockBatch(
                restaurant_id=mine.id,
                stock_item_id=their_item.id,
                batch_code="STOLEN",
                quantity_received=Decimal("1"),
                unit_cost=Decimal("1"),
                received_at=datetime.now(UTC),
                source="purchase",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_movement_cannot_reference_another_restaurants_batch(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _restaurant(db_session, "tenant-m2")
        theirs = await _restaurant(db_session, "tenant-t2")
        my_item = await _item(db_session, mine)
        their_item = await _item(db_session, theirs)
        their_batch = await _batch(db_session, theirs, their_item)

        db_session.add(
            StockMovement(
                restaurant_id=mine.id,
                stock_batch_id=their_batch.id,
                stock_item_id=my_item.id,
                type=MovementType.CONSUMPTION,
                quantity_delta=Decimal("-1"),
                unit_cost=Decimal("1"),
                basis=MovementBasis.THEORETICAL,
                occurred_at=datetime.now(UTC),
                business_date=date(2026, 9, 12),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestTheConstraintsThatCatchNonsense:
    async def test_a_zero_movement_is_refused(self, db_session: AsyncSession) -> None:
        """Always a bug, and it silently pollutes every count and average downstream."""
        restaurant = await _restaurant(db_session, "zero-delta")
        item = await _item(db_session, restaurant)
        batch = await _batch(db_session, restaurant, item)

        db_session.add(
            StockMovement(
                restaurant_id=restaurant.id,
                stock_batch_id=batch.id,
                stock_item_id=item.id,
                type=MovementType.ADJUSTMENT,
                quantity_delta=Decimal("0"),
                unit_cost=Decimal("0.36"),
                basis=MovementBasis.ACTUAL,
                occurred_at=datetime.now(UTC),
                business_date=date(2026, 9, 12),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_reference_must_be_a_pair_or_absent(self, db_session: AsyncSession) -> None:
        """`ref_type` without `ref_id` is a dangling pointer that reads as a real link."""
        restaurant = await _restaurant(db_session, "ref-pair")
        item = await _item(db_session, restaurant)
        batch = await _batch(db_session, restaurant, item)

        db_session.add(
            StockMovement(
                restaurant_id=restaurant.id,
                stock_batch_id=batch.id,
                stock_item_id=item.id,
                type=MovementType.CONSUMPTION,
                quantity_delta=Decimal("-5"),
                unit_cost=Decimal("0.36"),
                basis=MovementBasis.THEORETICAL,
                occurred_at=datetime.now(UTC),
                business_date=date(2026, 9, 12),
                ref_type="order",
                ref_id=None,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_batch_code_is_unique_per_restaurant_but_not_across_them(
        self, db_session: AsyncSession
    ) -> None:
        one = await _restaurant(db_session, "code-one")
        two = await _restaurant(db_session, "code-two")
        item_one = await _item(db_session, one)
        item_two = await _item(db_session, two)

        await _batch(db_session, one, item_one, code="SHARED")
        # The same code at a different restaurant is not a collision — tenants do not share a
        # batch-numbering namespace, and forcing them to would leak one restaurant's volume.
        await _batch(db_session, two, item_two, code="SHARED")

        db_session.add(
            StockBatch(
                restaurant_id=one.id,
                stock_item_id=item_one.id,
                batch_code="SHARED",
                quantity_received=Decimal("1"),
                unit_cost=Decimal("1"),
                received_at=datetime.now(UTC),
                source="purchase",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestOnHandIsNeverStored:
    async def test_no_table_carries_a_quantity_on_hand_column(
        self, db_session: AsyncSession
    ) -> None:
        """Invariant 2's failure mode is two sources of truth that agree until one matters.

        A structural test rather than a review habit: the moment somebody adds a cached balance
        column to make a screen faster, this fails and they have to argue for it deliberately.
        """
        rows = await db_session.execute(
            text(
                """
                SELECT table_name, column_name FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND (column_name LIKE '%%on_hand%%' OR column_name LIKE '%%quantity_balance%%'
                        OR column_name LIKE '%%current_quantity%%' OR column_name = 'stock_level')
                """
            )
        )
        assert rows.all() == []
