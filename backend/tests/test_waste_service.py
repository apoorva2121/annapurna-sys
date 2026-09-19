"""Logging waste writes two rows or none, and the cost is the batches' own.

The first of those is `docs/schema.md` §8's rule — "every `wastage_event` writes a paired
`stock_movement` of type `wastage` in the same transaction; never one without the other" — and the
two ways of breaking it fail differently, which is why both directions are tested:

- an **event with no movement** is waste everybody can see in a report that never left the stock
  book, so the variance number is silently wrong in the direction that hides theft;
- a **movement with no event** is stock gone with no reason, no person and no stage, which is the
  mystery shrinkage this product exists to eliminate.

The second is `docs/waste-model.md`'s: never require the person logging to know the cost. So the
cost is asserted to the paisa against the batches FEFO actually took it from — not today's price,
and not an average.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import MovementType, WastageStage
from app.core.errors import ConflictError, NotFoundError
from app.core.tenancy import TenantScope
from app.models.inventory import StockBatch, StockMovement
from app.models.waste import WastageEvent, WastageReason
from app.services.waste import REF_TYPE, WastageService
from tests.test_inventory_schema import _item, _restaurant
from tests.test_waste_schema import _reason, _reporter


def _actor(restaurant: object, employee_id: uuid.UUID) -> Actor:
    return Actor(
        employee_id=employee_id,
        organization_id=restaurant.organization_id,  # type: ignore[attr-defined]
        restaurant_id=restaurant.id,  # type: ignore[attr-defined]
        full_name="Waste Reporter",
        permissions=frozenset({"wastage.log", "wastage.approve"}),
        rank=0,
        session_id=None,
    )


async def _batch(
    session: AsyncSession,
    restaurant: object,
    item: object,
    *,
    code: str,
    quantity: str,
    unit_cost: str,
) -> StockBatch:
    """One delivery, at its own price. FEFO takes the soonest-expiring first, so two batches at
    different prices are what make "the batches' own cost" a testable claim rather than a slogan."""
    batch = StockBatch(
        restaurant_id=restaurant.id,  # type: ignore[attr-defined]
        stock_item_id=item.id,  # type: ignore[attr-defined]
        batch_code=code,
        quantity_received=Decimal(quantity),
        unit_cost=Decimal(unit_cost),
        received_at=datetime.now(UTC),
        source="purchase",
    )
    session.add(batch)
    await session.flush()
    session.add(
        StockMovement(
            restaurant_id=restaurant.id,  # type: ignore[attr-defined]
            stock_batch_id=batch.id,
            stock_item_id=item.id,  # type: ignore[attr-defined]
            type=MovementType.RECEIPT,
            quantity_delta=Decimal(quantity),
            unit_cost=Decimal(unit_cost),
            basis="actual",
            occurred_at=datetime.now(UTC),
            business_date=datetime.now(UTC).date(),
        )
    )
    await session.flush()
    return batch


async def _world(
    session: AsyncSession, slug: str, *, stage: str = WastageStage.STORAGE, **reason_kwargs: object
) -> tuple[object, object, WastageReason, Actor]:
    restaurant = await _restaurant(session, slug)
    item = await _item(session, restaurant, "PANEER")
    reason = await _reason(session, restaurant.id, "EXPIRED", stage=stage, **reason_kwargs)
    reporter = await _reporter(session, restaurant.organization_id)
    return restaurant, item, reason, _actor(restaurant, reporter.id)


def _service(session: AsyncSession, restaurant: object) -> WastageService:
    return WastageService(
        session,
        TenantScope(
            organization_id=restaurant.organization_id,  # type: ignore[attr-defined]
            restaurant_id=restaurant.id,  # type: ignore[attr-defined]
        ),
    )


class TestTheEventAndItsMovementAreOne:
    async def test_logging_waste_writes_both(self, db_session: AsyncSession) -> None:
        restaurant, item, reason, actor = await _world(db_session, "wsone")
        await _batch(db_session, restaurant, item, code="B1", quantity="1000", unit_cost="0.36")

        event = await _service(db_session, restaurant).log(
            actor,
            stock_item_id=item.id,  # type: ignore[attr-defined]
            wastage_reason_id=reason.id,
            quantity=Decimal("250"),
        )

        movements = (
            await db_session.scalars(
                select(StockMovement).where(
                    StockMovement.ref_type == REF_TYPE, StockMovement.ref_id == event.id
                )
            )
        ).all()
        assert len(movements) == 1
        assert movements[0].type == MovementType.WASTAGE
        # Negative: it left the shelf. The ledger is signed and on-hand is the sum of it.
        assert Decimal(str(movements[0].quantity_delta)) == Decimal("-250.0000")

    async def test_a_movement_is_actual_never_theoretical(self, db_session: AsyncSession) -> None:
        """Invariant 7. Somebody physically threw this away; it is not derived from a recipe, and
        summing the two bases into one consumption figure destroys the leakage number this product
        exists to surface."""
        restaurant, item, reason, actor = await _world(db_session, "wsbasis")
        await _batch(db_session, restaurant, item, code="B1", quantity="1000", unit_cost="0.36")

        event = await _service(db_session, restaurant).log(
            actor,
            stock_item_id=item.id,  # type: ignore[attr-defined]
            wastage_reason_id=reason.id,
            quantity=Decimal("250"),
        )

        movement = await db_session.scalar(
            select(StockMovement).where(StockMovement.ref_id == event.id)
        )
        assert movement is not None
        assert movement.basis == "actual"

    async def test_a_refused_log_leaves_neither_row(self, db_session: AsyncSession) -> None:
        """The other direction, and the one a test is most likely to skip.

        A reason that does not exist is refused *after* nothing has been written; the point is that
        the count of both tables is unchanged, so a future ordering that wrote the event first and
        validated afterwards would fail here.
        """
        restaurant, item, _, actor = await _world(db_session, "wsrefused")
        await _batch(db_session, restaurant, item, code="B1", quantity="1000", unit_cost="0.36")
        service = _service(db_session, restaurant)

        before_events = await db_session.scalar(select(func.count(WastageEvent.id)))
        before_movements = await db_session.scalar(
            select(func.count(StockMovement.id)).where(StockMovement.ref_type == REF_TYPE)
        )

        with pytest.raises(NotFoundError):
            await service.log(
                actor,
                stock_item_id=item.id,  # type: ignore[attr-defined]
                wastage_reason_id=uuid.uuid4(),
                quantity=Decimal("250"),
            )

        assert await db_session.scalar(select(func.count(WastageEvent.id))) == before_events
        assert (
            await db_session.scalar(
                select(func.count(StockMovement.id)).where(StockMovement.ref_type == REF_TYPE)
            )
            == before_movements
        )


class TestTheCostIsTheBatches:
    async def test_the_cost_is_what_the_batch_cost_to_the_paisa(
        self, db_session: AsyncSession
    ) -> None:
        restaurant, item, reason, actor = await _world(db_session, "wscost")
        await _batch(db_session, restaurant, item, code="B1", quantity="1000", unit_cost="0.36")

        event = await _service(db_session, restaurant).log(
            actor,
            stock_item_id=item.id,  # type: ignore[attr-defined]
            wastage_reason_id=reason.id,
            quantity=Decimal("250"),
        )

        # 250 g at ₹0.36/g.
        assert Decimal(str(event.cost_value)) == Decimal("90.00")

    async def test_waste_spanning_two_batches_costs_what_each_batch_cost(
        self, db_session: AsyncSession
    ) -> None:
        """The claim that makes "never today's price, never an average" real.

        400 g wasted out of a 300 g batch at ₹0.30 and a 700 g batch at ₹0.50: ₹90.00 from the
        first and ₹50.00 from the second. An average price would say ₹176.00 and a current price
        would say ₹200.00, and both would be wrong in a way nobody could see from the report.
        """
        restaurant, item, reason, actor = await _world(db_session, "wsfefo")
        await _batch(db_session, restaurant, item, code="B1", quantity="300", unit_cost="0.30")
        await _batch(db_session, restaurant, item, code="B2", quantity="700", unit_cost="0.50")

        event = await _service(db_session, restaurant).log(
            actor,
            stock_item_id=item.id,  # type: ignore[attr-defined]
            wastage_reason_id=reason.id,
            quantity=Decimal("400"),
        )

        assert Decimal(str(event.cost_value)) == Decimal("140.00")

    async def test_wasting_stock_that_was_never_received_still_records_it(
        self, db_session: AsyncSession
    ) -> None:
        """M05's rule, inherited: a consumption never refuses. The shortfall is recorded and
        on-hand goes negative, because a kitchen that cannot log the waste in front of it is a
        kitchen that stops logging."""
        restaurant, item, reason, actor = await _world(db_session, "wsshort")

        event = await _service(db_session, restaurant).log(
            actor,
            stock_item_id=item.id,  # type: ignore[attr-defined]
            wastage_reason_id=reason.id,
            quantity=Decimal("250"),
        )

        assert event.id is not None
        assert Decimal(str(event.quantity)) == Decimal("250")


class TestApproval:
    async def test_the_person_who_logged_it_cannot_approve_it(
        self, db_session: AsyncSession
    ) -> None:
        """The control standing between an expensive reason code and somebody logging theft as
        waste. It is worth nothing if one person can be both people — the same line M05 draws for a
        stock count's approver, and holds with a CHECK constraint as well."""
        restaurant, item, reason, actor = await _world(
            db_session, "wsapprove", requires_approval=True
        )
        await _batch(db_session, restaurant, item, code="B1", quantity="1000", unit_cost="0.36")
        service = _service(db_session, restaurant)
        event = await service.log(
            actor,
            stock_item_id=item.id,  # type: ignore[attr-defined]
            wastage_reason_id=reason.id,
            quantity=Decimal("250"),
        )

        with pytest.raises(ConflictError) as raised:
            await service.approve(actor, event.id)
        assert raised.value.code == "wastage.approver_is_reporter"

    async def test_somebody_else_may_approve_it(self, db_session: AsyncSession) -> None:
        restaurant, item, reason, actor = await _world(
            db_session, "wsapprovetwo", requires_approval=True
        )
        await _batch(db_session, restaurant, item, code="B1", quantity="1000", unit_cost="0.36")
        service = _service(db_session, restaurant)
        event = await service.log(
            actor,
            stock_item_id=item.id,  # type: ignore[attr-defined]
            wastage_reason_id=reason.id,
            quantity=Decimal("250"),
        )
        manager = await _reporter(db_session, restaurant.organization_id)  # type: ignore[attr-defined]

        approved = await service.approve(_actor(restaurant, manager.id), event.id)

        assert approved.approved_by == manager.id
        assert approved.approved_at is not None

    async def test_approving_twice_is_refused(self, db_session: AsyncSession) -> None:
        restaurant, item, reason, actor = await _world(
            db_session, "wsapprovethrice", requires_approval=True
        )
        await _batch(db_session, restaurant, item, code="B1", quantity="1000", unit_cost="0.36")
        service = _service(db_session, restaurant)
        event = await service.log(
            actor,
            stock_item_id=item.id,  # type: ignore[attr-defined]
            wastage_reason_id=reason.id,
            quantity=Decimal("250"),
        )
        manager = await _reporter(db_session, restaurant.organization_id)  # type: ignore[attr-defined]
        await service.approve(_actor(restaurant, manager.id), event.id)

        with pytest.raises(ConflictError) as raised:
            await service.approve(_actor(restaurant, manager.id), event.id)
        assert raised.value.code == "wastage.already_approved"


class TestTheSummary:
    async def test_it_groups_by_stage_and_reason(self, db_session: AsyncSession) -> None:
        """`docs/waste-model.md`: a single total is a number nobody can act on. The report this
        module exists for reads "₹14,800 prep over-production (47%)", and that shape needs the
        stage and the reason on every line."""
        restaurant, item, storage_reason, actor = await _world(db_session, "wssummary")
        prep_reason = await _reason(
            db_session,
            restaurant.id,  # type: ignore[attr-defined]
            "OVER_PREPARATION",
            stage=WastageStage.PREP,
        )
        await _batch(db_session, restaurant, item, code="B1", quantity="5000", unit_cost="0.40")
        service = _service(db_session, restaurant)
        # **Not `datetime.now(UTC).date()`.** The event's business date is computed in the
        # restaurant's timezone against `business_day_start` (invariant 4), and a UTC date
        # disagrees with it for thirty minutes every day: at 23:40 UTC it is 05:10 in Kolkata, so
        # the business date has rolled to tomorrow while the UTC date has not. This test passed for
        # nine modules and then failed inside that window on a full gate run:
        #
        #     KeyError: <WastageStage.PREP: 'prep'>
        #
        # The service already knows the answer, so ask it rather than recomputing it — which is
        # also the only version that stays true if the restaurant is ever not in Kolkata.
        today = await service.business_date_now()

        for reason_id, quantity in (
            (storage_reason.id, Decimal("100")),
            (prep_reason.id, Decimal("300")),
            (prep_reason.id, Decimal("200")),
        ):
            await service.log(
                actor,
                stock_item_id=item.id,  # type: ignore[attr-defined]
                wastage_reason_id=reason_id,
                quantity=quantity,
            )

        summary = await service.summary(since=today, until=today)

        by_stage = {line.stage: line for line in summary}
        assert by_stage[WastageStage.PREP].events == 2
        assert by_stage[WastageStage.PREP].cost_value == Decimal("200.00")
        assert by_stage[WastageStage.STORAGE].events == 1
        assert by_stage[WastageStage.STORAGE].cost_value == Decimal("40.00")
        # Biggest first: the report's whole job is to say where to look.
        assert summary[0].stage == WastageStage.PREP

    async def test_staff_meals_and_comps_never_appear(self, db_session: AsyncSession) -> None:
        """The separation `docs/waste-model.md` §4 insists on. Indian restaurants feed staff,
        always; counted as waste it looks like theft and poisons every variance number.

        This holds structurally rather than by filtering: the summary reads `wastage_event`, and a
        staff meal is a `stock_movement` with no event behind it. A version that summed the ledger
        by movement type would give the same answer today and the wrong one for ever after.
        """
        restaurant, item, reason, actor = await _world(db_session, "wsstaffmeal")
        await _batch(db_session, restaurant, item, code="B1", quantity="5000", unit_cost="0.40")
        service = _service(db_session, restaurant)
        # The business date, not the UTC one. See the note in `test_it_groups_by_stage_and_reason`.
        today = await service.business_date_now()
        await service.log(
            actor,
            stock_item_id=item.id,  # type: ignore[attr-defined]
            wastage_reason_id=reason.id,
            quantity=Decimal("100"),
        )
        # A staff meal, through the ledger directly — no wastage event, because it is not waste.
        await service._inventory.consume(
            actor,
            stock_item_id=item.id,  # type: ignore[attr-defined]
            quantity=Decimal("900"),
            basis="actual",
            movement_type=MovementType.STAFF_MEAL,
        )

        summary = await service.summary(since=today, until=today)

        assert sum(line.cost_value for line in summary) == Decimal("40.00")
