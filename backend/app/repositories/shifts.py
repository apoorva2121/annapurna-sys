"""Queries over the roster. Business rules live in the service, not here.

Two of these carry weight.

**`covering` is the one the order screen calls**, so it is one indexed query and not a scan:
assignments on a business date, with their shift and their section loaded, filtered in Python only
by the crossing-midnight predicate — which is pure arithmetic over columns already in hand
(`app/core/shift_window.py`) and cannot be expressed in SQL without duplicating the timezone rule
in a second place.

**Nothing here writes a status.** `present` and `late` are derived at clock-in by the service;
`absent` and `leave` are set by a person through it. A repository that could set a status would be
a second door into a decision that has to have an author.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.shifts import Shift, ShiftAssignment
from app.repositories.base import RestaurantScopedRepository, page_size


class ShiftRepository(RestaurantScopedRepository[Shift]):
    model = Shift

    async def list_all(self, *, include_inactive: bool = False) -> Sequence[Shift]:
        statement = self.scoped().order_by(Shift.start_time, Shift.name)
        if not include_inactive:
            statement = statement.where(Shift.is_active.is_(True))
        return (await self.session.scalars(statement)).all()

    async def by_name(self, name: str) -> Shift | None:
        return (await self.session.scalars(self.scoped().where(Shift.name == name))).first()


class ShiftAssignmentRepository(RestaurantScopedRepository[ShiftAssignment]):
    model = ShiftAssignment

    async def roster(
        self, *, since: date, until: date, limit: int | None = None
    ) -> Sequence[ShiftAssignment]:
        """A date range, with each assignment's shift already loaded.

        `selectinload` rather than a lazy relationship: a week's roster is thirty or forty rows and
        naming the shift on each of them would be thirty or forty queries — the N+1 that every
        list screen in this product is tested against.
        """
        statement = (
            self.scoped()
            .where(
                ShiftAssignment.business_date >= since,
                ShiftAssignment.business_date <= until,
            )
            .order_by(ShiftAssignment.business_date, ShiftAssignment.id)
            .limit(page_size(limit))
        )
        return (await self.session.scalars(statement)).all()

    async def on(self, business_date: date) -> Sequence[ShiftAssignment]:
        statement = self.scoped().where(ShiftAssignment.business_date == business_date)
        return (await self.session.scalars(statement)).all()

    async def mine(
        self, employee_id: uuid.UUID, *, since: date, until: date
    ) -> Sequence[ShiftAssignment]:
        statement = (
            self.scoped()
            .where(
                ShiftAssignment.employee_id == employee_id,
                ShiftAssignment.business_date >= since,
                ShiftAssignment.business_date <= until,
            )
            .order_by(ShiftAssignment.business_date)
        )
        return (await self.session.scalars(statement)).all()

    async def existing(
        self, *, shift_id: uuid.UUID, employee_id: uuid.UUID, business_date: date
    ) -> ShiftAssignment | None:
        statement = self.scoped().where(
            ShiftAssignment.shift_id == shift_id,
            ShiftAssignment.employee_id == employee_id,
            ShiftAssignment.business_date == business_date,
        )
        return (await self.session.scalars(statement)).first()

    async def with_shift(self, assignment_id: uuid.UUID) -> ShiftAssignment | None:
        statement = (
            self.scoped()
            .where(ShiftAssignment.id == assignment_id)
            .options(selectinload(ShiftAssignment.shift))
        )
        return (await self.session.scalars(statement)).first()

    async def covering_candidates(
        self, business_date: date
    ) -> Sequence[tuple[ShiftAssignment, Shift]]:
        """Every assignment on a business date, paired with its shift.

        One query, because the caller then applies the crossing-midnight predicate in Python: that
        rule needs the restaurant's timezone and `business_day_start`, and expressing it in SQL
        would put the product's most load-bearing time rule in a second place
        (`docs/decisions/0004-money-time-units.md`).
        """
        statement = (
            select(ShiftAssignment, Shift)
            .join(Shift, Shift.id == ShiftAssignment.shift_id)
            .where(
                ShiftAssignment.restaurant_id == self.scope.restaurant_id,
                ShiftAssignment.business_date == business_date,
            )
            .order_by(ShiftAssignment.id)
        )
        return [(row[0], row[1]) for row in (await self.session.execute(statement)).all()]
