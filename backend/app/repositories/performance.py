"""Every figure a score is made of, and the four tables that hold what cannot be derived.

**Nothing here is stored while a period is draft.** Every metric is computed from orders, tickets,
feedback and shifts at read time, which is `docs/schema.md`'s elimination of `waiter_performance`
still holding. Publication is what turns the answers into rows, once, in `PerformanceService`.

**Every metric comes back with its count.** `docs/workload-fairness.md` §5 names attribution as the
weakest link — a captain entering orders for a section, a complaint recorded against the server
rather than the kitchen — and the mitigation is that a wrong attribution shows up as a wrong
*number of things*, which a person can point at. A rate alone hides it.

**Assists are derived, never logged.** An assist is an order served outside the waiter's own
section, from `order → order_table → restaurant_table → dining_area` against the roster's
`shift_assignment.dining_area_id`. Asking somebody to log their own helpfulness produces a log of
who remembers to log, which measures the wrong thing and rewards the wrong person.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, and_, case, func, select

from app.core.enums import (
    OrderLineStatus,
    OrderStatus,
    PerformancePeriodStatus,
    ShiftAssignmentStatus,
)
from app.models.customers import Complaint, Feedback
from app.models.identity import Employee
from app.models.kitchen import KotTicket
from app.models.orders import Order, OrderLine, OrderTable
from app.models.performance import (
    IncentiveScheme,
    PerformanceNote,
    PerformancePeriod,
    PerformanceScore,
    RecognitionAward,
)
from app.models.setup import RestaurantTable
from app.models.shifts import ShiftAssignment
from app.repositories.base import RestaurantScopedRepository, page_size


@dataclass(frozen=True, slots=True)
class Worked:
    """What somebody actually worked in a period. The normalisation denominator."""

    employee_id: uuid.UUID
    hours: Decimal
    shifts: int
    rostered: int
    # Days excluded from the attendance denominator: approved leave, sickness, and the rest of
    # `app/core/scoring.py`'s tested list. Counted so the screen can say *why* a denominator is
    # smaller than a month.
    excused: int


@dataclass(frozen=True, slots=True)
class Served:
    """What somebody served, and how much of it was somebody else's section."""

    employee_id: uuid.UUID
    orders: int
    covers: int
    assists: int


@dataclass(frozen=True, slots=True)
class Quality:
    """Whether it went well: the errors, the ratings and the complaints attributable to a person."""

    employee_id: uuid.UUID
    lines: int
    cancelled_lines: int
    ratings: int
    rating_total: int
    complaints: int


class PerformanceRepository(RestaurantScopedRepository[PerformanceScore]):
    model = PerformanceScore

    # ---------------------------------------------------------------- the live metrics

    async def worked(self, *, since: date, until: date) -> list[Worked]:
        """Hours from the roster's own clock, and the days that do not count against anybody.

        `shift_assignment` holds what happened; `status` holds what kind of absence it was. Leave
        and sickness are excused rather than missed, which is the difference between a fair
        attendance figure and one that quietly penalises people for being ill.
        """
        # **Leave is excused; absent is not.** M12's own enum draws that line — `leave` is a
        # person who said in advance, `absent` is a person who did not turn up. Counting the first
        # against somebody is the failure `docs/workload-fairness.md` §4 names: it looks neutral
        # and quietly disadvantages exactly the people employment law protects.
        excused = ShiftAssignmentStatus.LEAVE.value
        statement = (
            select(
                ShiftAssignment.employee_id,
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    ShiftAssignment.clock_in_at.is_not(None),
                                    ShiftAssignment.clock_out_at.is_not(None),
                                ),
                                func.extract(
                                    "epoch",
                                    ShiftAssignment.clock_out_at - ShiftAssignment.clock_in_at,
                                )
                                / 3600,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.count(ShiftAssignment.id).filter(ShiftAssignment.clock_in_at.is_not(None)),
                func.count(ShiftAssignment.id),
                func.count(ShiftAssignment.id).filter(ShiftAssignment.status == excused),
            )
            .where(
                ShiftAssignment.restaurant_id == self.scope.restaurant_id,
                ShiftAssignment.business_date >= since,
                ShiftAssignment.business_date <= until,
            )
            .group_by(ShiftAssignment.employee_id)
        )
        return [
            Worked(
                employee_id=row[0],
                hours=Decimal(str(row[1])).quantize(Decimal("0.01")),
                shifts=int(row[2]),
                rostered=int(row[3]),
                excused=int(row[4]),
            )
            for row in (await self.session.execute(statement)).all()
        ]

    async def served(self, *, since: date, until: date) -> list[Served]:
        """Orders, covers, and the ones served outside the person's own section.

        The assist join is the interesting half: an order's primary table names a dining area, and
        the roster names the area that person was on. Where they differ, somebody helped.
        """
        section = (
            select(ShiftAssignment.employee_id, ShiftAssignment.dining_area_id)
            .where(
                ShiftAssignment.restaurant_id == self.scope.restaurant_id,
                ShiftAssignment.business_date >= since,
                ShiftAssignment.business_date <= until,
                ShiftAssignment.dining_area_id.is_not(None),
            )
            .distinct()
            .subquery()
        )
        statement = (
            select(
                Order.waiter_employee_id,
                func.count(func.distinct(Order.id)),
                func.coalesce(func.sum(Order.covers), 0),
                func.count(func.distinct(Order.id)).filter(
                    and_(
                        section.c.dining_area_id.is_not(None),
                        RestaurantTable.dining_area_id != section.c.dining_area_id,
                    )
                ),
            )
            .select_from(Order)
            .outerjoin(
                OrderTable,
                and_(OrderTable.order_id == Order.id, OrderTable.is_primary.is_(True)),
            )
            .outerjoin(RestaurantTable, RestaurantTable.id == OrderTable.restaurant_table_id)
            .outerjoin(section, section.c.employee_id == Order.waiter_employee_id)
            .where(
                Order.restaurant_id == self.scope.restaurant_id,
                Order.status == OrderStatus.SETTLED.value,
                Order.waiter_employee_id.is_not(None),
                Order.business_date >= since,
                Order.business_date <= until,
            )
            .group_by(Order.waiter_employee_id)
        )
        return [
            Served(employee_id=row[0], orders=int(row[1]), covers=int(row[2]), assists=int(row[3]))
            for row in (await self.session.execute(statement)).all()
        ]

    async def quality(self, *, since: date, until: date) -> list[Quality]:
        """Errors, ratings and complaints, each attributed the way its own module records it."""
        lines = (
            select(
                Order.waiter_employee_id.label("employee_id"),
                func.count(OrderLine.id).label("lines"),
                func.count(OrderLine.id)
                .filter(OrderLine.status == OrderLineStatus.CANCELLED.value)
                .label("cancelled"),
            )
            .join(Order, Order.id == OrderLine.order_id)
            .where(
                Order.restaurant_id == self.scope.restaurant_id,
                Order.waiter_employee_id.is_not(None),
                Order.business_date >= since,
                Order.business_date <= until,
            )
            .group_by(Order.waiter_employee_id)
            .subquery()
        )
        ratings = (
            select(
                Feedback.waiter_employee_id.label("employee_id"),
                func.count(Feedback.id).label("ratings"),
                func.coalesce(func.sum(Feedback.overall_rating), 0).label("total"),
            )
            .where(
                Feedback.restaurant_id == self.scope.restaurant_id,
                Feedback.waiter_employee_id.is_not(None),
                Feedback.business_date >= since,
                Feedback.business_date <= until,
            )
            .group_by(Feedback.waiter_employee_id)
            .subquery()
        )
        complaints = (
            select(
                Order.waiter_employee_id.label("employee_id"),
                func.count(Complaint.id).label("complaints"),
            )
            .join(Order, Order.id == Complaint.order_id)
            .where(
                Complaint.restaurant_id == self.scope.restaurant_id,
                Order.waiter_employee_id.is_not(None),
                Complaint.business_date >= since,
                Complaint.business_date <= until,
            )
            .group_by(Order.waiter_employee_id)
            .subquery()
        )
        statement = (
            select(
                lines.c.employee_id,
                lines.c.lines,
                lines.c.cancelled,
                func.coalesce(ratings.c.ratings, 0),
                func.coalesce(ratings.c.total, 0),
                func.coalesce(complaints.c.complaints, 0),
            )
            .select_from(lines)
            .outerjoin(ratings, ratings.c.employee_id == lines.c.employee_id)
            .outerjoin(complaints, complaints.c.employee_id == lines.c.employee_id)
        )
        return [
            Quality(
                employee_id=row[0],
                lines=int(row[1]),
                cancelled_lines=int(row[2]),
                ratings=int(row[3]),
                rating_total=int(row[4]),
                complaints=int(row[5]),
            )
            for row in (await self.session.execute(statement)).all()
        ]

    async def kitchen_delay_minutes(self, *, since: date, until: date) -> Decimal:
        """How far past its target the kitchen ran, on average. **Context, for everybody.**

        One figure rather than one per person, because it is the thing nobody on the floor
        controls — and that is exactly why it is shown beside their score.
        """
        statement = select(
            func.coalesce(
                func.avg(
                    func.extract("epoch", KotTicket.ready_at - KotTicket.printed_at) / 60
                    - KotTicket.target_minutes
                ),
                0,
            )
        ).where(
            KotTicket.restaurant_id == self.scope.restaurant_id,
            KotTicket.ready_at.is_not(None),
            KotTicket.business_date >= since,
            KotTicket.business_date <= until,
        )
        return Decimal(str(await self.session.scalar(statement) or 0)).quantize(Decimal("0.01"))

    # ------------------------------------------------------------------ the stored rows

    async def scheme(self, scheme_id: uuid.UUID) -> IncentiveScheme | None:
        return (
            await self.session.scalars(
                select(IncentiveScheme).where(
                    IncentiveScheme.id == scheme_id,
                    IncentiveScheme.restaurant_id == self.scope.restaurant_id,
                )
            )
        ).first()

    async def active_scheme(self) -> IncentiveScheme | None:
        return (
            await self.session.scalars(
                select(IncentiveScheme)
                .where(
                    IncentiveScheme.restaurant_id == self.scope.restaurant_id,
                    IncentiveScheme.is_active.is_(True),
                )
                .order_by(IncentiveScheme.effective_from.desc())
            )
        ).first()

    async def period(self, period_id: uuid.UUID) -> PerformancePeriod | None:
        return (
            await self.session.scalars(
                select(PerformancePeriod).where(
                    PerformancePeriod.id == period_id,
                    PerformancePeriod.restaurant_id == self.scope.restaurant_id,
                )
            )
        ).first()

    async def periods(self, *, limit: int | None = None) -> Sequence[PerformancePeriod]:
        return (
            await self.session.scalars(
                select(PerformancePeriod)
                .where(PerformancePeriod.restaurant_id == self.scope.restaurant_id)
                .order_by(PerformancePeriod.period_start.desc())
                .limit(page_size(limit))
            )
        ).all()

    async def scores(self, period_id: uuid.UUID) -> Sequence[PerformanceScore]:
        return (
            await self.session.scalars(
                self._scores_of(period_id).order_by(PerformanceScore.points.desc())
            )
        ).all()

    async def score_for(
        self, period_id: uuid.UUID, employee_id: uuid.UUID
    ) -> PerformanceScore | None:
        return (
            await self.session.scalars(
                self._scores_of(period_id).where(PerformanceScore.employee_id == employee_id)
            )
        ).first()

    def _scores_of(self, period_id: uuid.UUID) -> Select[tuple[PerformanceScore]]:
        return select(PerformanceScore).where(
            PerformanceScore.restaurant_id == self.scope.restaurant_id,
            PerformanceScore.performance_period_id == period_id,
        )

    async def notes(
        self, period_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> Sequence[PerformanceNote]:
        query = select(PerformanceNote).where(
            PerformanceNote.restaurant_id == self.scope.restaurant_id,
            PerformanceNote.performance_period_id == period_id,
        )
        if employee_id is not None:
            query = query.where(PerformanceNote.employee_id == employee_id)
        return (await self.session.scalars(query.order_by(PerformanceNote.created_at))).all()

    async def unanswered_disputes(self, period_id: uuid.UUID) -> int:
        """The count that blocks a publish.

        `docs/workload-fairness.md`'s ethics review: visibility without recourse is the shape of
        surveillance rather than of feedback. So a period cannot be frozen while somebody's
        challenge to it has not been answered — accepted, or declined with a reason.
        """
        statement = select(func.count(PerformanceNote.id)).where(
            PerformanceNote.restaurant_id == self.scope.restaurant_id,
            PerformanceNote.performance_period_id == period_id,
            PerformanceNote.kind == "dispute",
            PerformanceNote.answered_at.is_(None),
        )
        return int(await self.session.scalar(statement) or 0)

    async def without_a_login(
        self, employee_ids: Sequence[uuid.UUID]
    ) -> Sequence[tuple[uuid.UUID, str]]:
        """Which of these people have no way to sign in, and so no way to see their own score.

        ADR 0011 §3 promises that **every employee can always see their own figures and the inputs
        they were computed from**, and grants `performance.view.own` to every role to make that
        structural rather than a setting. ADR 0007 makes an employee without a `user_account`
        normal — in the seed, two kitchen staff and both cleaners. Those people are measured
        (shifts, tasks and wastage all reference them) and cannot open the application, so the
        guarantee fails silently for the lowest-paid staff it exists to protect.

        **Both the id and the name.** The id is what the caller filters on; the name is what it
        shows, because the answer reaches somebody who has to go and do something about it and
        "two people" is not actionable while "Ravi and Sunita" is.
        """
        if not employee_ids:
            return []
        rows = await self.session.execute(
            select(Employee.id, Employee.full_name)
            .where(
                Employee.organization_id == self.scope.organization_id,
                Employee.id.in_(list(employee_ids)),
                Employee.user_account_id.is_(None),
            )
            .order_by(Employee.full_name)
        )
        return [(row[0], row[1]) for row in rows.all()]

    async def awards(self, *, employee_id: uuid.UUID | None = None) -> Sequence[RecognitionAward]:
        query = select(RecognitionAward).where(
            RecognitionAward.restaurant_id == self.scope.restaurant_id
        )
        if employee_id is not None:
            query = query.where(RecognitionAward.employee_id == employee_id)
        return (
            await self.session.scalars(query.order_by(RecognitionAward.granted_at.desc()).limit(50))
        ).all()

    async def published_periods(self, *, limit: int = 2) -> Sequence[PerformancePeriod]:
        """The most recent published periods — what the stop rule looks at."""
        return (
            await self.session.scalars(
                select(PerformancePeriod)
                .where(
                    PerformancePeriod.restaurant_id == self.scope.restaurant_id,
                    PerformancePeriod.status != PerformancePeriodStatus.DRAFT.value,
                )
                .order_by(PerformancePeriod.period_start.desc())
                .limit(limit)
            )
        ).all()
