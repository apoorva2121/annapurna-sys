"""The rules that decide whether this feature raises morale or destroys it.

`docs/workload-fairness.md` opens with the sentence this whole file exists for:

> **A measurement system aimed at morale can destroy morale if built carelessly.**

Every test here is one of the ways it could be built carelessly, made impossible. They are not
arithmetic tests — the arithmetic is the easy part — they are the guardrails, and a guardrail with
no test is a paragraph in a document.

**The freeze** is the most important. ADR 0011: *"an employee who screenshots their score must find
that score unchanged next month."* If a published score can move when an order is voted away
afterwards, every other promise in this module is decoration.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import (
    OrderStatus,
    OrderType,
    PerformanceNoteKind,
    PerformancePeriodStatus,
    ShiftAssignmentStatus,
)
from app.core.errors import AppError, ConflictError
from app.core.scoring import (
    MIN_TEAM_SIZE,
    SUGGESTED_WEIGHTS,
    SchemeError,
    validate_weights,
    visible_team,
)
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.orders import Order
from app.models.performance import PerformanceScore
from app.models.shifts import Shift, ShiftAssignment
from app.models.tenancy import Organization, Restaurant
from app.services.performance import PerformanceService

_DAY = date(2026, 9, 16)


class World:
    def __init__(self, organization: Organization, restaurant: Restaurant) -> None:
        self.organization = organization
        self.restaurant = restaurant
        self.people: list[Employee] = []

    @property
    def scope(self) -> TenantScope:
        return TenantScope(organization_id=self.organization.id, restaurant_id=self.restaurant.id)

    def actor(self, index: int = 0) -> Actor:
        person = self.people[index]
        return Actor(
            employee_id=person.id,
            organization_id=self.organization.id,
            restaurant_id=self.restaurant.id,
            full_name=person.full_name,
            permissions=frozenset(),
            rank=0,
        )


async def _world(session: AsyncSession, *, people: int = 2) -> World:
    organization = Organization(name="Spice Garden", slug=f"sg-{uuid.uuid4().hex[:8]}")
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name="Koregaon Park",
        code=f"KP{uuid.uuid4().hex[:6]}",
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
    )
    session.add(restaurant)
    await session.flush()
    world = World(organization, restaurant)
    for index in range(people):
        person = Employee(
            organization_id=organization.id,
            employee_code=f"E{uuid.uuid4().hex[:6]}",
            full_name=f"Person {index}",
            joined_on=date(2026, 1, 1),
        )
        session.add(person)
        world.people.append(person)
    await session.flush()
    return world


async def _shift(session: AsyncSession, world: World) -> Shift:
    shift = Shift(
        restaurant_id=world.restaurant.id,
        name=f"Dinner {uuid.uuid4().hex[:4]}",
        start_time=time(17, 0),
        end_time=time(1, 0),
        is_active=True,
    )
    session.add(shift)
    await session.flush()
    return shift


async def _worked(
    session: AsyncSession,
    world: World,
    shift: Shift,
    person: Employee,
    *,
    hours: int,
    business_date: date = _DAY,
    status: str = ShiftAssignmentStatus.PRESENT.value,
) -> ShiftAssignment:
    start = datetime.combine(business_date, time(17, 0), tzinfo=UTC)
    assignment = ShiftAssignment(
        restaurant_id=world.restaurant.id,
        shift_id=shift.id,
        employee_id=person.id,
        business_date=business_date,
        status=status,
        clock_in_at=start if status != ShiftAssignmentStatus.LEAVE.value else None,
        clock_out_at=(
            start + timedelta(hours=hours) if status != ShiftAssignmentStatus.LEAVE.value else None
        ),
    )
    session.add(assignment)
    await session.flush()
    return assignment


async def _served(
    session: AsyncSession,
    world: World,
    person: Employee,
    *,
    covers: int,
    business_date: date = _DAY,
) -> Order:
    order = Order(
        restaurant_id=world.restaurant.id,
        order_number=f"O{uuid.uuid4().hex[:8]}",
        type=OrderType.DINE_IN.value,
        channel="pos",
        status=OrderStatus.SETTLED.value,
        covers=covers,
        waiter_employee_id=person.id,
        placed_at=datetime.combine(business_date, time(20, 0), tzinfo=UTC),
        settled_at=datetime.combine(business_date, time(21, 0), tzinfo=UTC),
        business_date=business_date,
    )
    session.add(order)
    await session.flush()
    return order


async def _scheme_and_period(session: AsyncSession, world: World) -> tuple[uuid.UUID, uuid.UUID]:
    service = PerformanceService(session, world.scope)
    scheme = await service.create_scheme(
        world.actor(),
        name="Starting point",
        period_type="weekly",
        weights=dict(SUGGESTED_WEIGHTS),
        effective_from=_DAY - timedelta(days=30),
    )
    period = await service.open_period(
        world.actor(),
        scheme_id=scheme.id,
        period_start=_DAY - timedelta(days=6),
        period_end=_DAY,
    )
    return scheme.id, period.id


# --------------------------------------------------------------------- the weight rule


class TestVolumeNeverStandsAlone:
    """ADR 0011's rule, and the one that keeps the whole feature honest.

    *"Without that rule the system pays people to rush, which is the opposite of the goal."*
    """

    def test_the_suggested_weights_are_accepted(self) -> None:
        parsed = validate_weights(dict(SUGGESTED_WEIGHTS))

        assert sum(parsed.values()) == Decimal("1.00")
        assert parsed["volume"] <= parsed["accuracy"] + parsed["rating"]

    def test_a_volume_heavy_scheme_is_refused(self) -> None:
        with pytest.raises(SchemeError, match="pays people to rush"):
            validate_weights(
                {"volume": "0.50", "accuracy": "0.20", "rating": "0.20", "speed": "0.10"}
            )

    def test_volume_exactly_equal_to_accuracy_plus_rating_is_allowed(self) -> None:
        """The boundary, because "must not exceed" and "must be less than" are different rules and
        the one in ADR 0011 is the first."""
        parsed = validate_weights(
            {"volume": "0.40", "accuracy": "0.20", "rating": "0.20", "speed": "0.20"}
        )

        assert parsed["volume"] == Decimal("0.40")

    def test_a_context_metric_cannot_carry_weight(self) -> None:
        """A waiter penalised for the tandoor running slow will correctly conclude the system is
        stupid and ignore all of it."""
        with pytest.raises(SchemeError, match="context, not something a person controls"):
            validate_weights({"accuracy": "0.50", "kitchen_delay": "0.50"})

    def test_weights_that_do_not_add_up_are_refused(self) -> None:
        with pytest.raises(SchemeError, match="have to add up to 1"):
            validate_weights({"accuracy": "0.50", "rating": "0.20"})

    def test_a_metric_this_product_does_not_compute_is_refused(self) -> None:
        with pytest.raises(SchemeError, match="not a metric this product computes"):
            validate_weights({"charisma": "1.00"})

    async def test_the_service_refuses_it_with_a_sentence_rather_than_a_code(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)

        with pytest.raises(AppError) as raised:
            await PerformanceService(db_session, world.scope).create_scheme(
                world.actor(),
                name="Rush",
                period_type="weekly",
                weights={"volume": "0.60", "accuracy": "0.20", "rating": "0.20"},
                effective_from=_DAY,
            )

        assert "pays people to rush" in raised.value.message


# --------------------------------------------------------------------- the freeze


class TestThePublishedPeriodNeverMoves:
    async def test_a_correction_after_publication_does_not_move_the_score(
        self, db_session: AsyncSession
    ) -> None:
        """**The test this module would be worst without.**

        ADR 0011: *"an employee who screenshots their score must find that score unchanged next
        month."* A later correction must not rewrite the basis on which a bonus was already paid.

        The correction used here is M12's own attendance correction — a manager fixing a clock-out
        somebody forgot — because it is a real, supported, audited operation rather than a
        contrived one. It moves `hours_worked`, which is the normalisation denominator, so it moves
        **every rate on the screen** if the figures are not frozen.

        A void would have been the other candidate and the database refuses it: a settled order is
        immutable (invariant 6), which is the same principle one layer down.
        """
        world = await _world(db_session)
        shift = await _shift(db_session, world)
        assignment = await _worked(db_session, world, shift, world.people[0], hours=8)
        await _served(db_session, world, world.people[0], covers=40)
        _, period_id = await _scheme_and_period(db_session, world)
        service = PerformanceService(db_session, world.scope)

        await service.publish(world.actor(), period_id)
        frozen = await service.mine(world.actor(), period_id)
        assert frozen is not None

        # Half the hours, a month later. Live, this would double every per-hour figure.
        assert assignment.clock_out_at is not None
        assignment.clock_out_at = assignment.clock_out_at - timedelta(hours=4)
        await db_session.flush()

        after = await service.mine(world.actor(), period_id)
        assert after is not None
        assert after.points == frozen.points
        assert after.hours == frozen.hours
        assert after.metrics["volume"].value == frozen.metrics["volume"].value

    async def test_a_published_period_is_not_published_twice(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)
        shift = await _shift(db_session, world)
        await _worked(db_session, world, shift, world.people[0], hours=8)
        _, period_id = await _scheme_and_period(db_session, world)
        service = PerformanceService(db_session, world.scope)
        await service.publish(world.actor(), period_id)

        with pytest.raises(ConflictError, match="already published"):
            await service.publish(world.actor(), period_id)

    async def test_publication_records_when_and_by_whom(self, db_session: AsyncSession) -> None:
        """A freeze nobody can audit is the same as no freeze, and the database says so."""
        world = await _world(db_session)
        shift = await _shift(db_session, world)
        await _worked(db_session, world, shift, world.people[0], hours=8)
        _, period_id = await _scheme_and_period(db_session, world)

        period = await PerformanceService(db_session, world.scope).publish(world.actor(), period_id)

        assert period.status == PerformancePeriodStatus.PUBLISHED.value
        assert period.published_at is not None
        assert period.published_by == world.actor().employee_id


# --------------------------------------------------------------------- the dispute


class TestAnEmployeeCanArgue:
    """`docs/workload-fairness.md`'s ethics review, question 1.

    Visibility lets somebody see their score; nothing let them challenge it, and visibility without
    recourse is the shape of surveillance rather than of feedback.
    """

    async def test_a_period_with_an_unanswered_dispute_cannot_be_published(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)
        shift = await _shift(db_session, world)
        await _worked(db_session, world, shift, world.people[0], hours=8)
        _, period_id = await _scheme_and_period(db_session, world)
        service = PerformanceService(db_session, world.scope)

        await service.add_note(
            world.actor(),
            period_id=period_id,
            employee_id=world.actor().employee_id,
            note="Those covers were Ramesh's tables; I was on the pass.",
            kind=PerformanceNoteKind.DISPUTE.value,
        )

        with pytest.raises(ConflictError, match="has not had an answer"):
            await service.publish(world.actor(), period_id)

    async def test_answering_it_lets_the_period_publish(self, db_session: AsyncSession) -> None:
        """Answered means *accepted, or declined with a reason* — in writing, by a named person."""
        world = await _world(db_session)
        shift = await _shift(db_session, world)
        await _worked(db_session, world, shift, world.people[0], hours=8)
        _, period_id = await _scheme_and_period(db_session, world)
        service = PerformanceService(db_session, world.scope)
        note = await service.add_note(
            world.actor(),
            period_id=period_id,
            employee_id=world.actor().employee_id,
            note="Those were not my tables.",
            kind=PerformanceNoteKind.DISPUTE.value,
        )

        answered = await service.answer_dispute(
            world.actor(1), note.id, answer="Checked the roster; you are right. Adjusted."
        )
        period = await service.publish(world.actor(), period_id)

        assert answered.answered_by == world.actor(1).employee_id
        assert answered.answer
        assert period.status == PerformancePeriodStatus.PUBLISHED.value

    async def test_a_dispute_is_raised_by_the_person_it_is_about(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)
        _, period_id = await _scheme_and_period(db_session, world)

        with pytest.raises(AppError, match="raised by the person whose figures"):
            await PerformanceService(db_session, world.scope).add_note(
                world.actor(),
                period_id=period_id,
                employee_id=world.people[1].id,
                note="I dispute Ramesh's numbers.",
                kind=PerformanceNoteKind.DISPUTE.value,
            )

    async def test_a_dispute_is_always_visible_to_the_person_who_raised_it(
        self, db_session: AsyncSession
    ) -> None:
        """Even when the caller asks otherwise: a challenge somebody cannot see the state of is not
        a challenge."""
        world = await _world(db_session)
        _, period_id = await _scheme_and_period(db_session, world)

        note = await PerformanceService(db_session, world.scope).add_note(
            world.actor(),
            period_id=period_id,
            employee_id=world.actor().employee_id,
            note="Not my tables.",
            kind=PerformanceNoteKind.DISPUTE.value,
            visible_to_employee=False,
        )

        assert note.visible_to_employee is True


# --------------------------------------------------------------------- what is never shown


class TestNoBottomRanking:
    async def test_below_five_scored_people_nobody_sees_anybody_else(
        self, db_session: AsyncSession
    ) -> None:
        """With three waiters, naming the top two names the third — which defeats the rule by
        arithmetic rather than by intent."""
        world = await _world(db_session, people=3)
        shift = await _shift(db_session, world)
        for index, person in enumerate(world.people):
            await _worked(db_session, world, shift, person, hours=8)
            await _served(db_session, world, person, covers=10 * (index + 1))
        _, period_id = await _scheme_and_period(db_session, world)
        service = PerformanceService(db_session, world.scope)

        team = await service.team(period_id, world.actor().employee_id)

        assert [line.employee_id for line in team] == [world.actor().employee_id]

    async def test_a_big_enough_team_sees_the_top_and_its_own_row(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, people=6)
        shift = await _shift(db_session, world)
        for index, person in enumerate(world.people):
            await _worked(db_session, world, shift, person, hours=8)
            await _served(db_session, world, person, covers=10 * (index + 1))
        _, period_id = await _scheme_and_period(db_session, world)
        service = PerformanceService(db_session, world.scope)

        # The *lowest* scorer asks, which is the case the rule exists for.
        viewer = world.people[0].id
        team = await service.team(period_id, viewer)

        assert viewer in {line.employee_id for line in team}
        assert len(team) < len(world.people), "the whole team is a ranking with a bottom in it"

    def test_the_threshold_is_five(self) -> None:
        assert MIN_TEAM_SIZE == 5
        assert visible_team(5) is True
        assert visible_team(4) is False


# --------------------------------------------------------------------- fairness of the figures


class TestTheFiguresAreFair:
    async def test_a_four_hour_and_an_eight_hour_shift_are_comparable(
        self, db_session: AsyncSession
    ) -> None:
        """Normalisation is what stops the score measuring the roster instead of the person."""
        world = await _world(db_session, people=2)
        shift = await _shift(db_session, world)
        await _worked(db_session, world, shift, world.people[0], hours=4)
        await _worked(db_session, world, shift, world.people[1], hours=8)
        await _served(db_session, world, world.people[0], covers=20)
        await _served(db_session, world, world.people[1], covers=40)
        _, period_id = await _scheme_and_period(db_session, world)

        lines = {
            line.employee_id: line
            for line in await PerformanceService(db_session, world.scope).draft(period_id)
        }

        # Same covers per hour, so the same volume metric — despite one working twice as long.
        assert lines[world.people[0].id].metrics["volume"].value == (
            lines[world.people[1].id].metrics["volume"].value
        )

    async def test_approved_leave_is_not_a_missed_shift(self, db_session: AsyncSession) -> None:
        """`docs/workload-fairness.md` §4: counting it against somebody looks neutral and quietly
        disadvantages exactly the people employment law protects."""
        world = await _world(db_session)
        shift = await _shift(db_session, world)
        await _worked(db_session, world, shift, world.people[0], hours=8)
        await _worked(
            db_session,
            world,
            shift,
            world.people[0],
            hours=0,
            business_date=_DAY - timedelta(days=1),
            status=ShiftAssignmentStatus.LEAVE.value,
        )
        _, period_id = await _scheme_and_period(db_session, world)

        line = await PerformanceService(db_session, world.scope).mine(world.actor(), period_id)

        assert line is not None
        assert line.metrics["attendance"].value == Decimal("1.0000")

    async def test_nobody_rating_you_is_not_a_bad_rating(self, db_session: AsyncSession) -> None:
        """A quiet week is not a bad review, and a zero would read as one."""
        world = await _world(db_session)
        shift = await _shift(db_session, world)
        await _worked(db_session, world, shift, world.people[0], hours=8)
        _, period_id = await _scheme_and_period(db_session, world)

        line = await PerformanceService(db_session, world.scope).mine(world.actor(), period_id)

        assert line is not None
        assert line.metrics["rating"].count == 0

    async def test_every_metric_carries_the_count_behind_it(self, db_session: AsyncSession) -> None:
        """§5's mitigation for the attribution problem: a wrong attribution shows up as a wrong
        *number of things*, which a person can point at, rather than as an unexplained score."""
        world = await _world(db_session)
        shift = await _shift(db_session, world)
        await _worked(db_session, world, shift, world.people[0], hours=8)
        await _served(db_session, world, world.people[0], covers=24)
        _, period_id = await _scheme_and_period(db_session, world)

        line = await PerformanceService(db_session, world.scope).mine(world.actor(), period_id)

        assert line is not None
        assert line.metrics["volume"].count == 24
        assert all(metric.count >= 0 for metric in line.metrics.values())

    async def test_the_kitchen_is_context_and_carries_no_weight(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)
        shift = await _shift(db_session, world)
        await _worked(db_session, world, shift, world.people[0], hours=8)
        _, period_id = await _scheme_and_period(db_session, world)

        line = await PerformanceService(db_session, world.scope).mine(world.actor(), period_id)

        assert line is not None
        assert line.metrics["kitchen_delay"].weighted is False


# --------------------------------------------------------------------- the primary screen


class TestTheDistributionScreen:
    async def test_it_shows_who_carries_more_than_their_share_of_the_roster(
        self, db_session: AsyncSession
    ) -> None:
        """**The finding this module exists for**, and it is about the rota rather than the person:
        a share of the covers above a share of the hours."""
        world = await _world(db_session, people=2)
        shift = await _shift(db_session, world)
        await _worked(db_session, world, shift, world.people[0], hours=4)
        await _worked(db_session, world, shift, world.people[1], hours=8)
        await _served(db_session, world, world.people[0], covers=60)
        await _served(db_session, world, world.people[1], covers=20)

        shares = await PerformanceService(db_session, world.scope).distribution(
            since=_DAY - timedelta(days=6), until=_DAY
        )

        busiest = shares[0]
        assert busiest.employee_id == world.people[0].id
        assert busiest.carrying_more_than_their_hours is True


# --------------------------------------------------------------------- awards


class TestAwardsAreGrantedByPeople:
    async def test_an_award_needs_a_citation(self, db_session: AsyncSession) -> None:
        """An award with a number and no sentence is a payment; with a sentence it is recognition,
        and the difference is what the module is for."""
        world = await _world(db_session)

        with pytest.raises(AppError, match="Say what it is for"):
            await PerformanceService(db_session, world.scope).grant_award(
                world.actor(),
                employee_id=world.people[1].id,
                award_type="recognition_only",
                citation="   ",
            )

    async def test_a_cash_award_carries_an_amount_and_recognition_does_not(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)
        service = PerformanceService(db_session, world.scope)

        cash = await service.grant_award(
            world.actor(),
            employee_id=world.people[1].id,
            award_type="cash",
            citation="Covered two shifts at no notice in the week of the wedding party.",
            amount=Decimal("2000.00"),
        )
        recognition = await service.grant_award(
            world.actor(),
            employee_id=world.people[1].id,
            award_type="recognition_only",
            citation="Trained the new hire without being asked.",
        )

        assert cash.amount == Decimal("2000.00")
        assert recognition.amount is None
        assert recognition.granted_by == world.actor().employee_id


class TestTheScoresAreScopedToTheirRestaurant:
    async def test_another_restaurants_scores_are_not_visible(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _world(db_session)
        theirs = await _world(db_session)
        shift = await _shift(db_session, theirs)
        await _worked(db_session, theirs, shift, theirs.people[0], hours=8)
        _, their_period = await _scheme_and_period(db_session, theirs)
        await PerformanceService(db_session, theirs.scope).publish(theirs.actor(), their_period)

        rows = list(
            (
                await db_session.scalars(
                    select(PerformanceScore).where(
                        PerformanceScore.restaurant_id == mine.restaurant.id
                    )
                )
            ).all()
        )

        assert rows == []
        assert (
            await PerformanceService(db_session, mine.scope)._repository.period(their_period)
            is None
        )
