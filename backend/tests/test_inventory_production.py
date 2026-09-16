"""Production and stock counts. Chunk D of M05 — the two transactional operations.

Production is where the cost engine meets the ledger: a batch of gravy costs what *this* batch of
onions cost, not what onions cost today. Counts are where an insider would work, so the tests here
are as much about the refusals as about the happy path.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import MovementBasis, MovementType, StockCountStatus
from app.core.errors import AppError
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.inventory import StockMovement
from app.models.setup import Station
from app.models.stock import PreparationProfile, Recipe, RecipeLine, StockItem
from app.models.tenancy import Organization, Restaurant
from app.services.inventory import InventoryService


@dataclass(frozen=True, slots=True)
class World:
    """Explicitly typed rather than built from `**kwargs`.

    The first version of this set attributes through `setattr`, which mypy cannot follow — it
    produced 152 errors in this file alone and would have hidden a real typo behind the noise.
    """

    restaurant: Restaurant
    onion: StockItem
    tomato: StockItem
    gravy: StockItem
    actor: Actor
    approver: Actor
    service: InventoryService


async def _employee(
    session: AsyncSession, organization_id: uuid.UUID, code: str, name: str
) -> Employee:
    employee = Employee(
        organization_id=organization_id,
        employee_code=code,
        full_name=name,
        joined_on=date(2026, 1, 1),
        employment_type="full_time",
        is_active=True,
    )
    session.add(employee)
    await session.flush()
    return employee


async def _world(session: AsyncSession, slug: str) -> World:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name=slug.title(),
        code=slug[:3].upper(),
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
    )
    session.add(restaurant)
    await session.flush()

    counter = await _employee(session, organization.id, f"{slug[:3].upper()}-1", "Store Manager")
    approver = await _employee(session, organization.id, f"{slug[:3].upper()}-2", "Head Chef")

    def _ingredient(code: str, cost: str) -> StockItem:
        item = StockItem(
            restaurant_id=restaurant.id,
            kind="ingredient",
            code=code,
            name=code.title(),
            base_unit="g",
            current_unit_cost=Decimal(cost),
            is_active=True,
        )
        session.add(item)
        return item

    station = Station(restaurant_id=restaurant.id, code="prep", name="Prep", seq=0, is_active=True)
    session.add(station)
    await session.flush()

    onion = _ingredient("ONION", "0.040000")
    tomato = _ingredient("TOMATO", "0.030000")
    gravy = StockItem(
        restaurant_id=restaurant.id,
        kind="preparation",
        code="GRAVY",
        name="Base Gravy",
        base_unit="g",
        current_unit_cost=Decimal("0.100000"),
        is_active=True,
    )
    session.add(gravy)
    await session.flush()

    # 1,000 g of inputs yield 800 g of gravy — a fifth boils off, which is what makes the output
    # cost more per gram than its inputs did.
    session.add(
        PreparationProfile(
            stock_item_id=gravy.id,
            batch_yield=Decimal("800"),
            shelf_life_hours=48,
            station_id=station.id,
            prep_minutes=45,
        )
    )
    recipe = Recipe(
        restaurant_id=restaurant.id,
        produces_stock_item_id=gravy.id,
        version=1,
        is_current=True,
        effective_from=datetime.now(UTC),
        unit_cost=Decimal("0.100000"),
        source="typed",
    )
    session.add(recipe)
    await session.flush()
    session.add_all(
        [
            RecipeLine(
                restaurant_id=restaurant.id,
                recipe_id=recipe.id,
                component_id=onion.id,
                quantity=Decimal("600"),
                seq=0,
            ),
            RecipeLine(
                restaurant_id=restaurant.id,
                recipe_id=recipe.id,
                component_id=tomato.id,
                quantity=Decimal("400"),
                seq=1,
            ),
        ]
    )
    await session.flush()

    scope = TenantScope(organization_id=organization.id, restaurant_id=restaurant.id)
    actor = Actor(
        employee_id=counter.id,
        organization_id=organization.id,
        restaurant_id=restaurant.id,
        full_name="Store Manager",
        permissions=frozenset(),
        rank=10,
    )
    approver_actor = Actor(
        employee_id=approver.id,
        organization_id=organization.id,
        restaurant_id=restaurant.id,
        full_name="Head Chef",
        permissions=frozenset(),
        rank=20,
    )
    return World(
        restaurant=restaurant,
        onion=onion,
        tomato=tomato,
        gravy=gravy,
        actor=actor,
        approver=approver_actor,
        service=InventoryService(session, scope),
    )


async def _stock(world: World, item: StockItem) -> Decimal:
    return await world.service.movements.quantity_for_item(item.id)


class TestProduction:
    async def test_it_consumes_inputs_and_creates_the_output(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "prod-basic")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.onion.id,
            quantity=Decimal("5000"),
            unit_cost=Decimal("0.04"),
        )
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.tomato.id,
            quantity=Decimal("5000"),
            unit_cost=Decimal("0.03"),
        )

        batch = await world.service.produce_batch(
            world.actor, stock_item_id=world.gravy.id, quantity=Decimal("800")
        )

        assert await _stock(world, world.onion) == Decimal("4400.0000")
        assert await _stock(world, world.tomato) == Decimal("4600.0000")
        assert await _stock(world, world.gravy) == Decimal("800.0000")
        assert batch.source == "production"

    async def test_the_output_costs_what_the_inputs_cost_including_yield_loss(
        self, db_session: AsyncSession
    ) -> None:
        """600 g onion at 0.04 + 400 g tomato at 0.03 = 36.00, over 800 g out = 0.045 per g.

        The inputs averaged 0.036/g; the output is 0.045/g. That 25% uplift is the fifth that
        boiled off, and pricing the output at its inputs' average would quietly understate every
        dish made from it.
        """
        world = await _world(db_session, "prod-cost")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.onion.id,
            quantity=Decimal("5000"),
            unit_cost=Decimal("0.04"),
        )
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.tomato.id,
            quantity=Decimal("5000"),
            unit_cost=Decimal("0.03"),
        )

        batch = await world.service.produce_batch(
            world.actor, stock_item_id=world.gravy.id, quantity=Decimal("800")
        )

        assert Decimal(str(batch.unit_cost)) == Decimal("0.045")

    async def test_it_uses_what_the_inputs_actually_cost_not_the_current_price(
        self, db_session: AsyncSession
    ) -> None:
        """Onions bought cheap last week make cheap gravy today, whatever onions cost now."""
        world = await _world(db_session, "prod-historic")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.onion.id,
            quantity=Decimal("5000"),
            unit_cost=Decimal("0.01"),
        )
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.tomato.id,
            quantity=Decimal("5000"),
            unit_cost=Decimal("0.01"),
        )

        batch = await world.service.produce_batch(
            world.actor, stock_item_id=world.gravy.id, quantity=Decimal("800")
        )

        # 1000 g of input at 0.01 = 10.00, over 800 g = 0.0125 — nothing to do with the items'
        # `current_unit_cost` of 0.04 and 0.03.
        assert Decimal(str(batch.unit_cost)) == Decimal("0.0125")

    async def test_it_scales_to_a_part_batch(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "prod-scale")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.onion.id,
            quantity=Decimal("5000"),
            unit_cost=Decimal("0.04"),
        )
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.tomato.id,
            quantity=Decimal("5000"),
            unit_cost=Decimal("0.03"),
        )

        await world.service.produce_batch(
            world.actor, stock_item_id=world.gravy.id, quantity=Decimal("400")
        )

        # Half a batch takes half the inputs.
        assert await _stock(world, world.onion) == Decimal("4700.0000")
        assert await _stock(world, world.tomato) == Decimal("4800.0000")

    async def test_producing_without_stock_still_works_and_records_the_shortfall(
        self, db_session: AsyncSession
    ) -> None:
        """Spec decision 2 reaches through production too — a kitchen does not stop cooking
        because the storeroom paperwork is behind."""
        world = await _world(db_session, "prod-empty")

        batch = await world.service.produce_batch(
            world.actor, stock_item_id=world.gravy.id, quantity=Decimal("800")
        )

        assert await _stock(world, world.onion) == Decimal("-600.0000")
        assert await _stock(world, world.gravy) == Decimal("800.0000")
        # Costed off the items' current prices, which is the only estimate available.
        assert Decimal(str(batch.unit_cost)) == Decimal("0.045")

    async def test_an_ingredient_cannot_be_produced(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "prod-ingredient")

        with pytest.raises(AppError) as raised:
            await world.service.produce_batch(
                world.actor, stock_item_id=world.onion.id, quantity=Decimal("100")
            )
        assert raised.value.code == "not_a_preparation"
        assert "Receive it" in raised.value.message

    async def test_production_is_marked_actual_not_theoretical(
        self, db_session: AsyncSession
    ) -> None:
        """What came out of the pot was observed; what went in was inferred from the recipe."""
        world = await _world(db_session, "prod-basis")
        await world.service.produce_batch(
            world.actor, stock_item_id=world.gravy.id, quantity=Decimal("800")
        )

        rows = (
            await db_session.scalars(
                select(StockMovement).where(StockMovement.type == MovementType.PRODUCTION)
            )
        ).all()
        assert [row.basis for row in rows] == [MovementBasis.ACTUAL]

        consumed = (
            await db_session.scalars(
                select(StockMovement).where(StockMovement.type == MovementType.CONSUMPTION)
            )
        ).all()
        assert {row.basis for row in consumed} == {MovementBasis.THEORETICAL}

    async def test_a_failure_mid_production_leaves_neither_half(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Acceptance criterion 4. Production is two halves and neither may land alone.

        A production that consumed its inputs and then failed to create its output would *destroy*
        stock on the books — the onions gone, no gravy to show for them, and nothing to indicate
        why. The opposite failure invents stock from nothing. Both are worse than the operation not
        happening, and both are the kind of corruption that is discovered weeks later during a count
        with no way left to explain it.

        The failure is injected at the last possible moment — after every input has been consumed,
        while the output batch is being built — because that is the window where a partial write is
        actually possible. The rollback is to a savepoint rather than the whole transaction so the
        fixture survives and the assertion is about the production alone.
        """
        world = await _world(db_session, "prod-atomic")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.onion.id,
            quantity=Decimal("5000"),
            unit_cost=Decimal("0.04"),
        )
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.tomato.id,
            quantity=Decimal("5000"),
            unit_cost=Decimal("0.03"),
        )
        onion_before = await _stock(world, world.onion)
        tomato_before = await _stock(world, world.tomato)

        async def explode(_business_date: object) -> str:
            raise RuntimeError("the disk caught fire while naming the batch")

        monkeypatch.setattr(world.service, "_next_batch_code", explode)

        savepoint = await db_session.begin_nested()
        with pytest.raises(RuntimeError):
            await world.service.produce_batch(
                world.actor, stock_item_id=world.gravy.id, quantity=Decimal("800")
            )
        await savepoint.rollback()

        # The inputs are untouched, and no gravy exists.
        assert await _stock(world, world.onion) == onion_before
        assert await _stock(world, world.tomato) == tomato_before
        assert await _stock(world, world.gravy) == Decimal("0")


class TestStockCounts:
    async def test_nothing_reaches_the_ledger_until_approval(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "count-gated")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.onion.id,
            quantity=Decimal("1000"),
            unit_cost=Decimal("0.04"),
        )

        count = await world.service.open_count(world.actor, stock_item_ids=[world.onion.id])
        await world.service.record_counted(count.id, counts={world.onion.id: Decimal("940")})
        await world.service.submit_count(count.id)

        # Submitted, not approved: the book has not moved.
        assert await _stock(world, world.onion) == Decimal("1000.0000")

        await world.service.approve_count(world.approver, count.id)

        assert await _stock(world, world.onion) == Decimal("940.0000")

    async def test_the_variance_is_valued_in_rupees(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "count-variance")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.onion.id,
            quantity=Decimal("1000"),
            unit_cost=Decimal("0.04"),
        )
        count = await world.service.open_count(world.actor, stock_item_ids=[world.onion.id])

        updated = await world.service.record_counted(
            count.id, counts={world.onion.id: Decimal("940")}
        )

        # 60 g short at 0.04 = 2.40 of leakage, and negative because it is missing.
        assert Decimal(str(updated.lines[0].variance_value)) == Decimal("-2.40")

    async def test_nobody_approves_their_own_count(self, db_session: AsyncSession) -> None:
        """A count is the one document that can make a shortfall official."""
        world = await _world(db_session, "count-self")
        count = await world.service.open_count(world.actor, stock_item_ids=[world.onion.id])
        await world.service.submit_count(count.id)

        with pytest.raises(AppError) as raised:
            await world.service.approve_count(world.actor, count.id)
        assert raised.value.code == "self_approval"
        assert raised.value.status_code == 403

    async def test_a_draft_cannot_be_approved(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "count-draft")
        count = await world.service.open_count(world.actor, stock_item_ids=[world.onion.id])

        with pytest.raises(AppError) as raised:
            await world.service.approve_count(world.approver, count.id)
        assert raised.value.code == "count_not_submitted"

    async def test_approving_twice_is_refused(self, db_session: AsyncSession) -> None:
        """Otherwise the correction posts twice and the book overshoots the shelf."""
        world = await _world(db_session, "count-twice")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.onion.id,
            quantity=Decimal("500"),
            unit_cost=Decimal("0.04"),
        )
        count = await world.service.open_count(world.actor, stock_item_ids=[world.onion.id])
        await world.service.record_counted(count.id, counts={world.onion.id: Decimal("450")})
        await world.service.submit_count(count.id)
        await world.service.approve_count(world.approver, count.id)

        with pytest.raises(AppError) as raised:
            await world.service.approve_count(world.approver, count.id)
        assert raised.value.code == "count_already_approved"
        assert await _stock(world, world.onion) == Decimal("450.0000")

    async def test_a_submitted_count_cannot_be_edited(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "count-frozen")
        count = await world.service.open_count(world.actor, stock_item_ids=[world.onion.id])
        await world.service.submit_count(count.id)

        with pytest.raises(AppError) as raised:
            await world.service.record_counted(count.id, counts={world.onion.id: Decimal("999")})
        assert raised.value.code == "count_not_draft"

    async def test_the_correction_is_an_adjustment_and_stays_visible(
        self, db_session: AsyncSession
    ) -> None:
        """A variance report that hid its adjustments would let a shortfall be declared away."""
        world = await _world(db_session, "count-adjustment")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.onion.id,
            quantity=Decimal("500"),
            unit_cost=Decimal("0.04"),
        )
        count = await world.service.open_count(world.actor, stock_item_ids=[world.onion.id])
        await world.service.record_counted(count.id, counts={world.onion.id: Decimal("480")})
        await world.service.submit_count(count.id)
        await world.service.approve_count(world.approver, count.id)

        adjustments = (
            await db_session.scalars(
                select(StockMovement).where(StockMovement.type == MovementType.ADJUSTMENT)
            )
        ).all()
        assert len(adjustments) == 1
        assert Decimal(str(adjustments[0].quantity_delta)) == Decimal("-20")
        assert "Stock count" in (adjustments[0].note or "")

    async def test_a_line_that_matches_the_book_posts_nothing(
        self, db_session: AsyncSession
    ) -> None:
        """A zero movement is refused by the database, so a perfect count must write no row."""
        world = await _world(db_session, "count-exact")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.onion.id,
            quantity=Decimal("500"),
            unit_cost=Decimal("0.04"),
        )
        count = await world.service.open_count(world.actor, stock_item_ids=[world.onion.id])
        await world.service.record_counted(count.id, counts={world.onion.id: Decimal("500")})
        await world.service.submit_count(count.id)
        await world.service.approve_count(world.approver, count.id)

        adjustments = await db_session.scalar(
            select(func.count())
            .select_from(StockMovement)
            .where(StockMovement.type == MovementType.ADJUSTMENT)
        )
        assert adjustments == 0

    async def test_an_empty_count_is_refused(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "count-empty")

        with pytest.raises(AppError) as raised:
            await world.service.open_count(world.actor, stock_item_ids=[])
        assert raised.value.code == "no_items"

    async def test_the_count_is_approved_and_recorded(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "count-status")
        count = await world.service.open_count(world.actor, stock_item_ids=[world.onion.id])
        await world.service.submit_count(count.id)

        approved = await world.service.approve_count(world.approver, count.id)

        assert approved.status == StockCountStatus.APPROVED
        assert approved.approved_by == world.approver.employee_id


class TestTheAdversarialReviewFindings:
    """Three defects found by reading this module back, with the test that would have caught each.

    None were found by the existing suite, and each was invisible for a different reason — which is
    the argument for the review step rather than for more of the same tests.
    """

    async def test_each_production_references_its_own_batch(self, db_session: AsyncSession) -> None:
        """**The real bug.** Consumption movements referenced `recipe.id`, not the batch.

        Every batch of gravy ever made therefore shared one reference, so "show me the movements
        this production wrote" returned every production of that recipe since the beginning — and
        M13's rule that a metric drills through to *its own* rows was quietly unmeetable.

        Nothing failed. The data looked right, the totals were right, and the reference pointed at
        a real row. It was wrong only in what it could answer.
        """
        world = await _world(db_session, "review-ref")
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.onion.id,
            quantity=Decimal("50000"),
            unit_cost=Decimal("0.04"),
        )
        await world.service.receive_stock(
            world.actor,
            stock_item_id=world.tomato.id,
            quantity=Decimal("50000"),
            unit_cost=Decimal("0.03"),
        )

        first = await world.service.produce_batch(
            world.actor, stock_item_id=world.gravy.id, quantity=Decimal("800")
        )
        second = await world.service.produce_batch(
            world.actor, stock_item_id=world.gravy.id, quantity=Decimal("800")
        )

        refs = (
            await db_session.scalars(
                select(StockMovement.ref_id).where(StockMovement.ref_type == "production_batch")
            )
        ).all()

        assert first.id != second.id
        # Two productions, two distinct references — and every movement of each points at its own.
        assert set(refs) == {first.id, second.id}
        assert refs.count(first.id) == refs.count(second.id)

    async def test_a_count_tolerates_the_same_item_listed_twice(
        self, db_session: AsyncSession
    ) -> None:
        """`uq_stock_count_line_count_item` turned an obvious client typo into a 500.

        Deduplicating is the right answer rather than rejecting: asking the same item to be counted
        twice is harmless and unambiguous, and an error here would be the product being pedantic
        about something it can simply handle.
        """
        world = await _world(db_session, "review-dupe")

        count = await world.service.open_count(
            world.actor,
            stock_item_ids=[world.onion.id, world.tomato.id, world.onion.id],
        )

        loaded = await world.service.counts.get_with_lines(count.id)
        assert loaded is not None
        assert len(loaded.lines) == 2

    async def test_consumption_reaches_batches_through_the_scoped_repository(
        self, db_session: AsyncSession
    ) -> None:
        """The third finding was a latent one rather than a live bug.

        `consume` fetched each batch with `session.get`, which reads by primary key with no tenant
        filter at all. It was safe, because the id came from a scoped query a line earlier — but an
        unscoped read sitting in the hot path of the product's most-written table is exactly how
        the #1 bug class gets reintroduced by whoever edits the loop next.

        This asserts the behaviour that matters: one restaurant's consumption never touches
        another's stock, however the batch is fetched.
        """
        mine = await _world(db_session, "review-mine")
        theirs = await _world(db_session, "review-theirs")
        await theirs.service.receive_stock(
            theirs.actor,
            stock_item_id=theirs.onion.id,
            quantity=Decimal("9000"),
            unit_cost=Decimal("0.04"),
        )

        result = await mine.service.consume(
            mine.actor,
            stock_item_id=mine.onion.id,
            quantity=Decimal("100"),
            basis=MovementBasis.THEORETICAL,
        )

        # Entirely a shortfall: the other restaurant's 9,000 g was never reachable.
        assert result.shortfall == Decimal("100")
        assert await _stock(theirs, theirs.onion) == Decimal("9000.0000")


class TestTwoMoreRefusals:
    async def test_a_preparation_with_no_current_recipe_says_so(
        self, db_session: AsyncSession
    ) -> None:
        """A preparation profile without a recipe: the item exists, the method to make it does not.

        Reachable in real life — somebody creates the preparation, then the recipe is written
        later, and in between a cook tries to make it.
        """
        world = await _world(db_session, "refuse-no-recipe")
        orphan = StockItem(
            restaurant_id=world.restaurant.id,
            kind="preparation",
            code="MARINADE",
            name="Marinade",
            base_unit="ml",
            current_unit_cost=Decimal("0.200000"),
            is_active=True,
        )
        db_session.add(orphan)
        await db_session.flush()
        db_session.add(
            PreparationProfile(
                stock_item_id=orphan.id,
                batch_yield=Decimal("500"),
                shelf_life_hours=24,
                station_id=(
                    await db_session.scalars(
                        select(Station).where(Station.restaurant_id == world.restaurant.id)
                    )
                )
                .one()
                .id,
                prep_minutes=10,
            )
        )
        await db_session.flush()

        with pytest.raises(AppError) as raised:
            await world.service.produce_batch(
                world.actor, stock_item_id=orphan.id, quantity=Decimal("500")
            )
        assert raised.value.code == "no_current_recipe"

    async def test_submitting_a_count_twice_is_refused(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "refuse-resubmit")
        count = await world.service.open_count(world.actor, stock_item_ids=[world.onion.id])
        await world.service.submit_count(count.id)

        with pytest.raises(AppError) as raised:
            await world.service.submit_count(count.id)
        assert raised.value.code == "count_not_draft"
