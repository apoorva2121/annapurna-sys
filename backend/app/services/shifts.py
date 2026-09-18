"""The roster, the clock, and who is on the floor right now.

Four rules carry this module, and each one is a decision rather than a mechanism.

**You clock yourself in.** `clock_in` takes no employee id — not as a check that could be forgotten
but as a parameter that does not exist. Buddy punching is the oldest fraud in hospitality and the
schema cannot prevent it; what the design can do is refuse to make it convenient, and make the
alternative leave a mark. A manager crediting somebody's attendance does it through `correct`,
which needs `shift.manage`, needs a reason, and writes an audit row naming both values.

**`present` and `late` are derived at clock-in; `absent` and `leave` are said by a person.**
Nothing in the background flips a status. Somebody who never clocked in stays `scheduled`, and the
roster renders that as "did not clock in" — which is the truth, where an `absent` nobody asserted
would be a disciplinary fact in the database with no author.

**A missed clock-out stays open.** No job closes it at a guessed time, because M17 normalises per
hour worked and a wrong denominator is worse than a missing one.

**Each refusal is its own message.** A waiter with a phone in one hand at the start of service will
not debug a single "cannot clock in", so there are five refusals and five sentences.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import shift_window
from app.core.actor import Actor
from app.core.audit import record
from app.core.enums import ShiftAssignmentStatus
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.tenancy import TenantScope
from app.models.shifts import Shift, ShiftAssignment
from app.models.tenancy import Restaurant
from app.repositories.employee import EmployeeRepository
from app.repositories.setup import DiningAreaRepository, RestaurantRepository
from app.repositories.shifts import ShiftAssignmentRepository, ShiftRepository

logger = logging.getLogger(__name__)

# How far the roster screen looks by default: this week and next.
DEFAULT_ROSTER_DAYS = 14


@dataclass(frozen=True, slots=True)
class OnNow:
    """Who is covering what, right now."""

    assignment: ShiftAssignment
    shift: Shift


class ShiftService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._shifts = ShiftRepository(session, scope)
        self._assignments = ShiftAssignmentRepository(session, scope)
        self._employees = EmployeeRepository(session, scope)
        self._areas = DiningAreaRepository(session, scope)
        self._restaurants = RestaurantRepository(session, scope)

    # ------------------------------------------------------------------ shifts

    async def shifts(self, *, include_inactive: bool = False) -> Sequence[Shift]:
        return await self._shifts.list_all(include_inactive=include_inactive)

    async def create_shift(self, *, name: str, start: time, end: time) -> Shift:
        self._check_length(start, end)
        if await self._shifts.by_name(name) is not None:
            raise ConflictError(
                "shift.name_taken", f"This restaurant already has a shift called {name}."
            )
        shift = Shift(
            restaurant_id=self.scope.restaurant_id,
            name=name,
            start_time=start,
            end_time=end,
            is_active=True,
        )
        self.session.add(shift)
        await self.session.flush()
        return shift

    async def update_shift(
        self,
        shift_id: uuid.UUID,
        *,
        name: str | None = None,
        start: time | None = None,
        end: time | None = None,
        is_active: bool | None = None,
    ) -> Shift:
        shift = await self._shift(shift_id)
        new_start = start if start is not None else shift.start_time
        new_end = end if end is not None else shift.end_time
        self._check_length(new_start, new_end)
        if name is not None and name != shift.name:
            if await self._shifts.by_name(name) is not None:
                raise ConflictError(
                    "shift.name_taken", f"This restaurant already has a shift called {name}."
                )
            shift.name = name
        shift.start_time = new_start
        shift.end_time = new_end
        if is_active is not None:
            # Deactivated, never deleted (ADR 0008): assignments point at it forever, and a report
            # on last quarter must still be able to name it.
            shift.is_active = is_active
        await self.session.flush()
        return shift

    # ------------------------------------------------------------- assignments

    async def roster(
        self, *, since: date | None = None, until: date | None = None
    ) -> Sequence[ShiftAssignment]:
        start = since or await self.today()
        finish = until or start + timedelta(days=DEFAULT_ROSTER_DAYS)
        if finish < start:
            raise AppError(
                "shift.range_invalid", "That date range runs backwards.", status_code=422
            )
        return await self._assignments.roster(since=start, until=finish)

    async def mine(
        self, actor: Actor, *, days: int = DEFAULT_ROSTER_DAYS
    ) -> Sequence[ShiftAssignment]:
        today = await self.today()
        return await self._assignments.mine(
            actor.employee_id, since=today - timedelta(days=1), until=today + timedelta(days=days)
        )

    async def assign(
        self,
        *,
        shift_id: uuid.UUID,
        employee_id: uuid.UUID,
        business_date: date,
        dining_area_id: uuid.UUID | None,
    ) -> ShiftAssignment:
        shift = await self._shift(shift_id)
        if not shift.is_active:
            raise AppError(
                "shift.inactive",
                f"{shift.name} is no longer used. Reactivate it before staffing it.",
                status_code=422,
            )
        employee = await self._employees.get_assigned_here(employee_id)
        if employee is None or not employee.is_active:
            raise NotFoundError("shift.person_not_found", "That person does not work here.")
        if dining_area_id is not None and await self._areas.get(dining_area_id) is None:
            raise NotFoundError("shift.area_not_found", "That section does not exist.")

        assignment = ShiftAssignment(
            restaurant_id=self.scope.restaurant_id,
            shift_id=shift_id,
            employee_id=employee_id,
            dining_area_id=dining_area_id,
            business_date=business_date,
            status=ShiftAssignmentStatus.SCHEDULED.value,
        )
        self.session.add(assignment)
        try:
            await self.session.flush()
        except IntegrityError as error:
            # The unique constraint, read as the thing a person did: they staffed somebody twice.
            raise ConflictError(
                "shift.already_assigned",
                "That person is already on this shift for that day.",
            ) from error
        return assignment

    async def unassign(self, assignment_id: uuid.UUID) -> None:
        """Only before it starts. After that it is a record, and the way to say somebody did not
        work is `absent` — which has an author."""
        assignment = await self._assignment(assignment_id)
        span = await self._span(assignment)
        if datetime.now(UTC) >= span.starts_at or assignment.clock_in_at is not None:
            raise ConflictError(
                "shift.already_started",
                "That shift has started, so it is a record now. Mark the person absent instead.",
            )
        await self.session.delete(assignment)
        await self.session.flush()

    async def set_status(
        self, actor: Actor, assignment_id: uuid.UUID, status: ShiftAssignmentStatus
    ) -> ShiftAssignment:
        """`absent` and `leave` only. `present` and `late` are what clocking in means, and a
        manager asserting one of those on a row with no times is what the check constraint and this
        refusal both exist to prevent."""
        if status not in (
            ShiftAssignmentStatus.ABSENT,
            ShiftAssignmentStatus.LEAVE,
            ShiftAssignmentStatus.SCHEDULED,
        ):
            raise AppError(
                "shift.status_not_settable",
                "Present and late are what clocking in means. Correct the time instead.",
                status_code=422,
            )
        assignment = await self._assignment(assignment_id)
        before = assignment.status
        assignment.status = status.value
        await self.session.flush()
        record(
            self.session,
            actor,
            action="shift.status_set",
            entity="shift_assignment",
            entity_id=assignment.id,
            old={"status": before},
            new={"status": status.value},
        )
        return assignment

    async def correct(
        self,
        actor: Actor,
        assignment_id: uuid.UUID,
        *,
        clock_in_at: datetime | None,
        clock_out_at: datetime | None,
        dining_area_id: uuid.UUID | None,
        reason: str,
    ) -> ShiftAssignment:
        """A manager fixing a time. **Needs a reason, and leaves a mark.**

        "Suresh's phone was dead" is a legitimate, recorded, attributable act. It is not the same
        act as clocking in, and the record must not make the two look alike.
        """
        if not reason.strip():
            raise AppError(
                "shift.reason_required",
                "Say why the time is being changed. Somebody else's attendance is being asserted.",
                status_code=422,
            )
        assignment = await self._assignment(assignment_id)
        before = {
            "clock_in_at": _iso(assignment.clock_in_at),
            "clock_out_at": _iso(assignment.clock_out_at),
            "dining_area_id": str(assignment.dining_area_id or ""),
        }
        if clock_in_at is not None:
            assignment.clock_in_at = clock_in_at
            span = await self._span(assignment)
            assignment.status = (
                ShiftAssignmentStatus.LATE.value
                if shift_window.is_late(clock_in_at, span, grace_minutes=await self._grace())
                else ShiftAssignmentStatus.PRESENT.value
            )
        if clock_out_at is not None:
            assignment.clock_out_at = clock_out_at
        if dining_area_id is not None:
            if await self._areas.get(dining_area_id) is None:
                raise NotFoundError("shift.area_not_found", "That section does not exist.")
            assignment.dining_area_id = dining_area_id
        await self.session.flush()
        # Every attendance correction, because the alternative is a roster that can be edited
        # after the fact to change who was responsible — and M17 freezes a published period
        # precisely so that editing one afterwards cannot move a score.
        record(
            self.session,
            actor,
            action="shift.corrected",
            entity="shift_assignment",
            entity_id=assignment.id,
            old=before,
            new={
                "clock_in_at": _iso(assignment.clock_in_at),
                "clock_out_at": _iso(assignment.clock_out_at),
                "dining_area_id": str(assignment.dining_area_id or ""),
            },
            reason=reason,
        )
        return assignment

    # ------------------------------------------------------------------- clock

    async def clock_in(self, actor: Actor, assignment_id: uuid.UUID) -> ShiftAssignment:
        assignment = await self._own(actor, assignment_id)
        if assignment.clock_in_at is not None:
            raise ConflictError("shift.already_clocked_in", "You are already clocked in.")
        today = await self.today()
        if assignment.business_date != today:
            raise ConflictError(
                "shift.not_today",
                "That shift is not today's. You can only clock in to a shift you are working now.",
            )
        moment = datetime.now(UTC)
        span = await self._span(assignment)
        assignment.clock_in_at = moment
        assignment.status = (
            ShiftAssignmentStatus.LATE.value
            if shift_window.is_late(moment, span, grace_minutes=await self._grace())
            else ShiftAssignmentStatus.PRESENT.value
        )
        await self.session.flush()
        logger.info(
            "shift.clocked_in",
            extra={
                "restaurant_id": str(self.scope.restaurant_id),
                "assignment_id": str(assignment.id),
                "status": assignment.status,
            },
        )
        return assignment

    async def clock_out(self, actor: Actor, assignment_id: uuid.UUID) -> ShiftAssignment:
        assignment = await self._own(actor, assignment_id)
        if assignment.clock_in_at is None:
            raise ConflictError(
                "shift.not_clocked_in", "You have not clocked in to this shift yet."
            )
        if assignment.clock_out_at is not None:
            raise ConflictError("shift.already_clocked_out", "You are already clocked out.")
        assignment.clock_out_at = datetime.now(UTC)
        await self.session.flush()
        return assignment

    # ----------------------------------------------------------------- on now

    async def on_now(self, *, moment: datetime | None = None) -> list[OnNow]:
        """Who is covering which section right now — the manager's glance, and the lookup order
        assignment uses."""
        now = moment or datetime.now(UTC)
        restaurant = await self._restaurant()
        today = shift_window.business_day_for(
            now, restaurant.timezone, restaurant.business_day_start
        )
        found: list[OnNow] = []
        # Yesterday as well: a shift that crosses midnight belongs to yesterday's business date and
        # is still running at 00:30. Leaving it out is how the late rush has nobody on the floor.
        for business_date in (today - timedelta(days=1), today):
            for assignment, shift in await self._assignments.covering_candidates(business_date):
                if shift_window.covers(
                    now,
                    business_day=business_date,
                    start=shift.start_time,
                    end=shift.end_time,
                    timezone=restaurant.timezone,
                    business_day_start=restaurant.business_day_start,
                ):
                    found.append(OnNow(assignment=assignment, shift=shift))
        return found

    async def waiter_for_area(
        self, dining_area_id: uuid.UUID, *, moment: datetime | None = None
    ) -> uuid.UUID | None:
        """The one waiter covering a section right now, or nobody.

        **Ambiguity assigns nobody**, and that is the rule rather than a limitation: a wrong waiter
        is worse than none, because it is somebody else's performance score (ADR 0011) and somebody
        else's name on an audit row. Zero on the section, or two, both answer `None`.
        """
        covering = [
            row
            for row in await self.on_now(moment=moment)
            if row.assignment.dining_area_id == dining_area_id
        ]
        if len(covering) != 1:
            return None
        return covering[0].assignment.employee_id

    async def today(self) -> date:
        restaurant = await self._restaurant()
        return shift_window.business_day_for(
            datetime.now(UTC), restaurant.timezone, restaurant.business_day_start
        )

    # --------------------------------------------------------------- internals

    def _check_length(self, start: time, end: time) -> None:
        span = shift_window.span_of(
            business_day=date(2026, 1, 1),
            start=start,
            end=end,
            timezone="UTC",
            business_day_start=time(0, 0),
        )
        hours = (span.ends_at - span.starts_at).total_seconds() / 3600
        if hours > shift_window.MAX_SHIFT_HOURS:
            raise AppError(
                "shift.too_long",
                f"A shift cannot be longer than {shift_window.MAX_SHIFT_HOURS} hours.",
                status_code=422,
            )

    async def _shift(self, shift_id: uuid.UUID) -> Shift:
        shift = await self._shifts.get(shift_id)
        if shift is None:
            raise NotFoundError("shift.not_found", "That shift does not exist here.")
        return shift

    async def _assignment(self, assignment_id: uuid.UUID) -> ShiftAssignment:
        assignment = await self._assignments.get(assignment_id)
        if assignment is None:
            raise NotFoundError(
                "shift.assignment_not_found", "That shift assignment does not exist here."
            )
        return assignment

    async def _own(self, actor: Actor, assignment_id: uuid.UUID) -> ShiftAssignment:
        """**There is no way to clock in somebody else**, so this is the only check there is to
        make: the row has to be the actor's own."""
        assignment = await self._assignment(assignment_id)
        if assignment.employee_id != actor.employee_id:
            raise PermissionDeniedError(
                "shift.not_yours",
                "You can only clock in and out of your own shifts. A manager can correct a time.",
            )
        return assignment

    async def _restaurant(self) -> Restaurant:
        restaurant = await self._restaurants.get()
        if restaurant is None:  # pragma: no cover - the actor's own restaurant always exists
            raise NotFoundError("restaurant.not_found", "This restaurant no longer exists.")
        return restaurant

    async def _grace(self) -> int:
        return shift_window.grace_minutes_from((await self._restaurant()).settings)

    async def _span(self, assignment: ShiftAssignment) -> shift_window.ShiftSpan:
        shift = await self._shift(assignment.shift_id)
        restaurant = await self._restaurant()
        return shift_window.span_of(
            business_day=assignment.business_date,
            start=shift.start_time,
            end=shift.end_time,
            timezone=restaurant.timezone,
            business_day_start=restaurant.business_day_start,
        )


def _iso(moment: datetime | None) -> str:
    return "" if moment is None else moment.isoformat()
