"""The write path: receive, consume, adjust. Chunk C of M05.

The consumption tests are the heart of this file. FEFO across several batches, and the approved
decision that a consumption is **never refused** — it records the shortfall, drives on-hand
negative, and says so, rather than blocking a restaurant from taking money because the storeroom
paperwork is behind.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import MovementBasis, MovementType
from app.core.errors import AppError, NotFoundError
from app.core.tenancy import TenantScope
from app.models.audit import AuditLog
from app.models.identity import Employee
from app.models.inventory import StockMovement
from app.models.stock import StockItem
from app.models.tenancy import Organization, Restaurant
from app.services.inventory import InventoryService


class World:
    __slots__ = ("actor", "item", "restaurant", "service")

    def __init__(
        self, restaurant: Restaurant, item: StockItem, actor: Actor, service: InventoryService
    ) -> None:
        self.restaurant = restaurant
        self.item = item
        self.actor = actor
        self.service = service


async def _world(
    session: AsyncSession, slug: str, *, timezone: str = "Asia/Kolkata", cost: str = "0.360000"
) -> World:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name=slug.title(),
        code=slug[:3].upper(),
        timezone=timezone,
        business_day_start=time(5, 0),
    )
    session.add(restaurant)
    await session.flush()
    employee = Employee(
        organization_id=organization.id,
        employee_code=f"{slug[:3].upper()}-1",
        full_name="Store Manager",
        joined_on=date(2026, 1, 1),
        employment_type="full_time",
        is_active=True,
    )
    session.add(employee)
    await session.flush()
    item = StockItem(
        restaurant_id=restaurant.id,
        kind="ingredient",
        code="PANEER",
        name="Paneer",
        base_unit="g",
        current_unit_cost=Decimal(cost),
        is_active=True,
    )
    session.add(item)
    await session.flush()

    scope = TenantScope(organization_id=organization.id, restaurant_id=restaurant.id)
    actor = Actor(
        employee_id=employee.id,
        organization_id=organization.id,
        restaurant_id=restaurant.id,
        full_name="Store Manager",
        permissions=frozenset(),
        rank=10,
    )
    return World(restaurant, item, actor, InventoryService(session, scope))


async def _on_hand(world: World) -> Decimal:
    rows = await world.service.on_hand(include_zero=True)
    return rows[0].quantity if rows else Decimal("0")


class TestReceiving:
    async def test_a_batch_and_its_receipt_movement_are_written_together(
        self, db_session: AsyncSession
    ) -> None:
        """A batch without its movement is a paper quantity with nothing on hand."""
        world = await _world(db_session, "recv-pair")

        batch = await world.service.receive_stock(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("5000"),
            unit_cost=Decimal("0.36"),
        )

        movements = (
            await db_session.scalars(
                select(StockMovement).where(StockMovement.stock_batch_id == batch.id)
            )
        ).all()
        assert len(movements) == 1
        assert movements[0].type == MovementType.RECEIPT
        # A receipt is physically observed, so it is `actual`. The whole variance calculation rests
        # on receipts being the anchor.
        assert movements[0].basis == MovementBasis.ACTUAL
        assert await _on_hand(world) == Decimal("5000.0000")

    async def test_it_is_audited(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "recv-audit")

        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("100"),
            unit_cost=Decimal("0.36"),
        )

        entry = (
            await db_session.scalars(select(AuditLog).where(AuditLog.action == "stock.received"))
        ).first()
        assert entry is not None

    async def test_a_receipt_of_zero_is_refused_and_says_what_to_do_instead(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "recv-zero")

        with pytest.raises(AppError) as raised:
            await world.service.receive_stock(
                world.actor,
                stock_item_id=world.item.id,
                quantity=Decimal("0"),
                unit_cost=Decimal("0.36"),
            )
        assert "adjustment" in raised.value.message

    async def test_another_restaurants_item_cannot_be_received_into(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _world(db_session, "recv-mine")
        theirs = await _world(db_session, "recv-theirs")

        with pytest.raises(NotFoundError):
            await mine.service.receive_stock(
                theirs.actor,
                stock_item_id=theirs.item.id,
                quantity=Decimal("10"),
                unit_cost=Decimal("1"),
            )

    async def test_another_restaurants_item_cannot_be_passed_in_as_a_shortcut(
        self, db_session: AsyncSession
    ) -> None:
        """The shortcut that saves a read must not become a way around the tenant check.

        `receive_stock` accepts an already-loaded item so a delivery reads each one once rather
        than twice (backlog-issues B9). Matching ids is not enough to trust it: the item has to
        belong to this restaurant, or the scoped lookup has to happen anyway and refuse it.
        """
        mine = await _world(db_session, "recv-shortcut-mine")
        theirs = await _world(db_session, "recv-shortcut-theirs")

        with pytest.raises(NotFoundError):
            await mine.service.receive_stock(
                mine.actor,
                stock_item_id=theirs.item.id,
                quantity=Decimal("10"),
                unit_cost=Decimal("1"),
                item=theirs.item,
            )

    async def test_the_business_date_is_the_restaurants_not_the_servers(
        self, db_session: AsyncSession
    ) -> None:
        """ADR 0004. 02:00 IST belongs to the previous business day, and the naive answer is wrong
        by a day for every late-closing restaurant and by 5h30m for all of them."""
        world = await _world(db_session, "recv-businessday")
        # 2026-09-13 02:00 IST == 2026-09-12 20:30 UTC. Before the 05:00 cut, so it
        # books to the 12th.
        late_night = datetime(2026, 9, 12, 20, 30, tzinfo=UTC)

        batch = await world.service.receive_stock(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("10"),
            unit_cost=Decimal("1"),
            occurred_at=late_night,
        )

        movement = (
            await db_session.scalars(
                select(StockMovement).where(StockMovement.stock_batch_id == batch.id)
            )
        ).one()
        assert movement.business_date == date(2026, 9, 12)


class TestConsumingFefo:
    async def test_it_takes_from_the_soonest_expiring_batch_first(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "consume-fefo")
        today = await world.service.business_date_now()
        late = await world.service.receive_stock(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("1000"),
            unit_cost=Decimal("0.30"),
            expiry_date=today + timedelta(days=30),
        )
        soon = await world.service.receive_stock(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("1000"),
            unit_cost=Decimal("0.50"),
            expiry_date=today + timedelta(days=2),
        )

        result = await world.service.consume(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("400"),
            basis=MovementBasis.THEORETICAL,
        )

        assert result.shortfall == Decimal("0")
        assert [line.batch_id for line in result.lines] == [soon.id]
        # Costed at the batch it actually came from, not at the item's current price.
        assert result.total_value == Decimal("200.00")
        assert late.id not in {line.batch_id for line in result.lines}

    async def test_it_spans_batches_when_one_is_not_enough(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "consume-span")
        today = await world.service.business_date_now()
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("300"),
            unit_cost=Decimal("0.50"),
            expiry_date=today + timedelta(days=1),
        )
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("300"),
            unit_cost=Decimal("0.20"),
            expiry_date=today + timedelta(days=5),
        )

        result = await world.service.consume(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("500"),
            basis=MovementBasis.THEORETICAL,
        )

        assert result.shortfall == Decimal("0")
        assert [line.quantity for line in result.lines] == [Decimal("300"), Decimal("200")]
        # 300 x 0.50 + 200 x 0.20 = 190. A single blended cost would not produce this.
        assert result.total_value == Decimal("190.00")
        assert await _on_hand(world) == Decimal("100.0000")


class TestConsumingIsNeverRefused:
    """Spec decision 2, approved. The most important behaviour in this module."""

    async def test_it_records_a_shortfall_and_goes_negative(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "short-negative")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("100"),
            unit_cost=Decimal("0.40"),
        )

        result = await world.service.consume(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("250"),
            basis=MovementBasis.THEORETICAL,
        )

        assert result.shortfall == Decimal("150")
        assert await _on_hand(world) == Decimal("-150.0000")

    async def test_the_shortfall_movement_says_what_is_wrong(
        self, db_session: AsyncSession
    ) -> None:
        """The note is read by whoever is confused, so it names the cause and the remedy."""
        world = await _world(db_session, "short-note")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("10"),
            unit_cost=Decimal("1"),
        )

        await world.service.consume(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("60"),
            basis=MovementBasis.THEORETICAL,
        )

        notes = (
            await db_session.scalars(
                select(StockMovement.note).where(StockMovement.note.isnot(None))
            )
        ).all()
        assert any("without a recorded receipt" in (note or "") for note in notes)

    async def test_an_item_never_received_can_still_be_consumed(
        self, db_session: AsyncSession
    ) -> None:
        """The cold-start case: a restaurant that has recorded no purchases at all.

        This must not raise. It creates a placeholder batch to hold the shortfall, because
        `stock_movement.stock_batch_id` is NOT NULL — and making it nullable to accommodate this
        would weaken the tenant-safe composite foreign key for every row in the table.
        """
        world = await _world(db_session, "short-virgin", cost="0.75")

        result = await world.service.consume(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("40"),
            basis=MovementBasis.THEORETICAL,
        )

        assert result.shortfall == Decimal("40")
        assert await _on_hand(world) == Decimal("-40.0000")
        # Charged at the item's current cost, which is the only estimate available. Asserted
        # exactly: an `or` here would let the test pass while the cost was silently zero, and a
        # zero-costed shortfall is exactly the kind of figure that quietly flatters a food cost.
        assert len(result.lines) == 1
        assert result.lines[0].unit_cost == Decimal("0.750000")
        assert result.total_value == Decimal("30.000000")

    async def test_a_consumption_of_zero_is_still_refused(self, db_session: AsyncSession) -> None:
        """Never refusing for *insufficient stock* is not the same as accepting nonsense."""
        world = await _world(db_session, "short-zero")

        with pytest.raises(AppError):
            await world.service.consume(
                world.actor,
                stock_item_id=world.item.id,
                quantity=Decimal("0"),
                basis=MovementBasis.THEORETICAL,
            )

    async def test_a_non_consuming_type_is_refused(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "short-type")

        with pytest.raises(AppError) as raised:
            await world.service.consume(
                world.actor,
                stock_item_id=world.item.id,
                quantity=Decimal("5"),
                basis=MovementBasis.THEORETICAL,
                movement_type=MovementType.RECEIPT,
            )
        assert "adjustment" in raised.value.message


class TestAdjusting:
    async def test_it_moves_the_position_and_is_audited(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "adjust-basic")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("100"),
            unit_cost=Decimal("1"),
        )

        await world.service.adjust(
            world.actor,
            stock_item_id=world.item.id,
            quantity_delta=Decimal("-15"),
            reason="Spilled a tray",
        )

        assert await _on_hand(world) == Decimal("85.0000")
        entry = (
            await db_session.scalars(select(AuditLog).where(AuditLog.action == "stock.adjusted"))
        ).first()
        assert entry is not None
        # **The reason moved in M14, and this is the better place for it.** `audit_log` has no
        # `reason` column, so a why goes in the metadata block beside the values it explains —
        # which is where M07's waiter handover and M12's attendance correction already put theirs,
        # and where the audit viewer reads it from to render it as a reason. In `new_value` it
        # would show on that screen as a *field that changed*, which is not what happened: nothing
        # changed from one reason to another.
        assert entry.audit_metadata == {"reason": "Spilled a tray"}
        assert entry.new_value is not None
        assert entry.new_value["quantity_delta"] == "-15"

    async def test_a_reason_is_mandatory(self, db_session: AsyncSession) -> None:
        """The one movement nobody observed is the one an insider would use to erase a shortfall."""
        world = await _world(db_session, "adjust-reason")

        with pytest.raises(AppError) as raised:
            await world.service.adjust(
                world.actor,
                stock_item_id=world.item.id,
                quantity_delta=Decimal("-5"),
                reason="   ",
            )
        assert raised.value.code == "reason_required"

    async def test_an_adjustment_of_zero_is_refused(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "adjust-zero")

        with pytest.raises(AppError):
            await world.service.adjust(
                world.actor,
                stock_item_id=world.item.id,
                quantity_delta=Decimal("0"),
                reason="Nothing happened",
            )

    async def test_an_adjustment_stays_its_own_type(self, db_session: AsyncSession) -> None:
        """A variance report that hid adjustments would let somebody declare a shortfall away."""
        world = await _world(db_session, "adjust-type")
        await world.service.adjust(
            world.actor,
            stock_item_id=world.item.id,
            quantity_delta=Decimal("20"),
            reason="Found a sack behind the door",
        )

        count = await db_session.scalar(
            select(func.count())
            .select_from(StockMovement)
            .where(StockMovement.type == MovementType.ADJUSTMENT)
        )
        assert count == 1


class TestTheLedgerAddsUp:
    async def test_on_hand_equals_the_movement_sum_after_many_operations(
        self, db_session: AsyncSession
    ) -> None:
        """Acceptance criterion 1, at a size a single test can afford.

        The exhaustive 1,000-operation property version lives in `test_inventory_property.py`;
        this is the cheap version that runs on every commit and would catch a gross error early.
        """
        world = await _world(db_session, "ledger-sums")
        expected = Decimal("0")

        for index in range(12):
            await world.service.receive_stock(
                world.actor,
                stock_item_id=world.item.id,
                quantity=Decimal("100"),
                unit_cost=Decimal("0.50"),
            )
            expected += Decimal("100")
            if index % 3 == 0:
                await world.service.consume(
                    world.actor,
                    stock_item_id=world.item.id,
                    quantity=Decimal("250"),
                    basis=MovementBasis.THEORETICAL,
                )
                expected -= Decimal("250")

        ledger_sum = await db_session.scalar(
            select(func.coalesce(func.sum(StockMovement.quantity_delta), 0)).where(
                StockMovement.restaurant_id == world.restaurant.id
            )
        )
        assert await _on_hand(world) == expected
        assert Decimal(str(ledger_sum)) == expected

    async def test_a_consumption_reference_is_carried_onto_every_line(
        self, db_session: AsyncSession
    ) -> None:
        """M07 needs to answer "show me the movements this order wrote"."""
        world = await _world(db_session, "ledger-ref")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("50"),
            unit_cost=Decimal("1"),
        )
        order_id = uuid.uuid4()

        await world.service.consume(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("80"),
            basis=MovementBasis.THEORETICAL,
            ref_type="order",
            ref_id=order_id,
        )

        refs = (
            await db_session.scalars(
                select(StockMovement.ref_id).where(StockMovement.ref_type == "order")
            )
        ).all()
        # Both the covered part and the shortfall carry the reference — a caller tracing an order
        # must not find half of its consumption.
        assert len(refs) == 2
        assert set(refs) == {order_id}


class TestTheRefusalsNobodyHadRead:
    """The error branches, each of which is a sentence somebody reads while confused.

    `test_stock_service.py` puts it best: an untested error message is an error message nobody has
    read. These were found by the coverage gate rather than by review — the suite was green while a
    handful of refusals had never once been executed.
    """

    async def test_a_negative_unit_cost_is_refused(self, db_session: AsyncSession) -> None:
        """The schema blocks this too. The service check is defence in depth, for the seeder and
        any future caller that does not come through HTTP."""
        world = await _world(db_session, "refuse-cost")

        with pytest.raises(AppError) as raised:
            await world.service.receive_stock(
                world.actor,
                stock_item_id=world.item.id,
                quantity=Decimal("10"),
                unit_cost=Decimal("-1"),
            )
        assert raised.value.code == "invalid_cost"

    async def test_producing_zero_is_refused(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "refuse-produce")

        with pytest.raises(AppError) as raised:
            await world.service.produce_batch(
                world.actor, stock_item_id=world.item.id, quantity=Decimal("0")
            )
        assert raised.value.code == "invalid_quantity"

    async def test_producing_something_with_no_recipe_says_so(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "refuse-norecipe")

        with pytest.raises(AppError) as raised:
            await world.service.produce_batch(
                world.actor, stock_item_id=world.item.id, quantity=Decimal("100")
            )
        # An ingredient, so the earlier of the two refusals fires and points at the right verb.
        assert raised.value.code == "not_a_preparation"

    async def test_recording_against_a_count_that_does_not_exist(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "refuse-count-missing")

        with pytest.raises(NotFoundError):
            await world.service.record_counted(uuid.uuid4(), counts={world.item.id: Decimal("1")})

    async def test_submitting_a_count_that_does_not_exist(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "refuse-submit-missing")

        with pytest.raises(NotFoundError):
            await world.service.submit_count(uuid.uuid4())

    async def test_approving_a_count_that_does_not_exist(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "refuse-approve-missing")

        with pytest.raises(NotFoundError):
            await world.service.approve_count(world.actor, uuid.uuid4())

    async def test_a_negative_counted_quantity_is_refused(self, db_session: AsyncSession) -> None:
        """You cannot have minus four kilos of paneer on a shelf. A negative *book* position is
        meaningful; a negative *count* is somebody mistyping."""
        world = await _world(db_session, "refuse-negative-count")
        count = await world.service.open_count(world.actor, stock_item_ids=[world.item.id])

        with pytest.raises(AppError) as raised:
            await world.service.record_counted(count.id, counts={world.item.id: Decimal("-4")})
        assert raised.value.code == "invalid_quantity"

    async def test_a_count_can_be_opened_on_an_item_whose_book_position_is_negative(
        self, db_session: AsyncSession
    ) -> None:
        """The regression for a 500 the seed found.

        `open_count` pre-fills every line's `counted_quantity` from the book so the sheet opens on
        the position it is checking. A *negative* book position is meaningful — stock went out that
        nobody recorded coming in, which `docs/onboarding-cold-start.md` calls the most useful
        thing this product can tell a restaurant that has never kept records, and which the seed
        plants deliberately on ONION. But `ck_stock_count_line_counted` says `counted_quantity >=
        0`, because a shelf cannot hold minus four kilos.

        So the two were in direct conflict: opening a count that included the unrecorded item
        raised CheckViolationError from Postgres, and a storeman counting the one item most worth
        counting got "Something went wrong".

        The sheet now opens at zero for such an item, which is also what the storeman will write:
        the shelf is empty, and the variance is the whole negative book position.
        """
        world = await _world(db_session, "count-negative-book")
        await world.service.consume(
            world.actor,
            stock_item_id=world.item.id,
            quantity=Decimal("50"),
            basis=MovementBasis.THEORETICAL,
        )

        count = await world.service.open_count(world.actor, stock_item_ids=[world.item.id])
        refreshed = await world.service.counts.get_with_lines(count.id)
        assert refreshed is not None
        line = refreshed.lines[0]
        assert Decimal(str(line.system_quantity)) < 0, "the book should be negative here"
        assert Decimal(str(line.counted_quantity)) == 0, (
            "the sheet must open at zero rather than at a negative the constraint forbids"
        )

    async def test_recording_an_item_the_sheet_does_not_list_is_ignored(
        self, db_session: AsyncSession
    ) -> None:
        """Silently skipped rather than refused: a partial count sheet is a normal thing, and a
        client sending one extra item has made a harmless mistake the server can absorb."""
        world = await _world(db_session, "refuse-extra-item")
        other = StockItem(
            restaurant_id=world.restaurant.id,
            kind="ingredient",
            code="GHEE",
            name="Ghee",
            base_unit="g",
            current_unit_cost=Decimal("0.900000"),
            is_active=True,
        )
        db_session.add(other)
        await db_session.flush()
        count = await world.service.open_count(world.actor, stock_item_ids=[world.item.id])

        updated = await world.service.record_counted(count.id, counts={other.id: Decimal("50")})

        assert len(updated.lines) == 1
        assert updated.lines[0].stock_item_id == world.item.id


class TestOnHandFilteredToSomeItems:
    async def test_it_can_be_asked_about_named_items_only(self, db_session: AsyncSession) -> None:
        """The path M13 will use: a report about five ingredients should not read the storeroom."""
        world = await _world(db_session, "onhand-filtered")
        other = StockItem(
            restaurant_id=world.restaurant.id,
            kind="ingredient",
            code="GHEE",
            name="Ghee",
            base_unit="g",
            current_unit_cost=Decimal("0.900000"),
            is_active=True,
        )
        db_session.add(other)
        await db_session.flush()
        for item_id in (world.item.id, other.id):
            await world.service.receive_stock(
                world.actor,
                stock_item_id=item_id,
                quantity=Decimal("100"),
                unit_cost=Decimal("1"),
            )

        rows = await world.service.movements.on_hand(stock_item_ids=[other.id])

        assert [row.code for row in rows] == ["GHEE"]
