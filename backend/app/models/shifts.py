"""The roster — `docs/schema.md` §11, migration 0044.

Two tables, and the semantics are the work. Argued in `docs/modules/M12-shifts-spec.md`.

**A shift is a template; an assignment is a person on a date.** `shift` has no date and belongs to
nobody, which is what makes a week cheap to fill in: a handful of shifts x a handful of people x
seven days, as taps rather than forms.

**`start_time > end_time` is legal** and means the shift crosses midnight — the evening shift of a
place that closes at two. The instants it occupies are never stored: `app/core/shift_window.py`
derives them from the assignment's `business_date`, which is the only arrangement in which a roster
edited next week still describes last week correctly.

**`dining_area_id` is what makes an assist derivable** (ADR 0011). An order taken at a table in
somebody else's section *is* a colleague helping, and deriving it means nobody has to remember to
log it. One row per person per shift per date, so one section — a waiter covering two is expressed
as the assists it produces, which is exactly the signal M17 wants.

**A missed clock-out stays open.** No background job closes it at a guessed time, because M17 would
later normalise against that guess and a wrong denominator is worse than a missing one.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ShiftAssignmentStatus
from app.models.base import Base, TimestampedUUIDMixin


def _uuid() -> Any:
    return postgresql.UUID(as_uuid=True)


def _values(members: Any) -> str:
    return ", ".join(f"'{member.value}'" for member in members)


class Shift(TimestampedUUIDMixin, Base):
    """'Morning', 'Evening'. Deactivated, never deleted (ADR 0008, master-data tier): assignments
    point at it forever and a report on last quarter must still be able to name it."""

    __tablename__ = "shift"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_shift_id_restaurant"),
        UniqueConstraint("restaurant_id", "name", name="uq_shift_restaurant_name"),
        Index("ix_shift_restaurant", "restaurant_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Local wall-clock times, not instants. A shift is "six in the evening", which stays six in the
    # evening across a daylight-saving change that an instant would not survive.
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ShiftAssignment(TimestampedUUIDMixin, Base):
    """One person, on one shift, on one business date."""

    __tablename__ = "shift_assignment"
    __table_args__ = (
        UniqueConstraint(
            "shift_id", "employee_id", "business_date", name="uq_shift_assignment_once"
        ),
        ForeignKeyConstraint(
            ["shift_id", "restaurant_id"],
            ["shift.id", "shift.restaurant_id"],
            name="fk_shift_assignment_shift",
        ),
        ForeignKeyConstraint(
            ["dining_area_id", "restaurant_id"],
            ["dining_area.id", "dining_area.restaurant_id"],
            name="fk_shift_assignment_area",
        ),
        CheckConstraint(
            f"status IN ({_values(ShiftAssignmentStatus)})", name="ck_shift_assignment_status"
        ),
        # A clock-out without a clock-in is a shift nobody worked, and an out before an in is a
        # negative duration M17 would later divide by.
        CheckConstraint(
            "clock_out_at IS NULL OR clock_in_at IS NOT NULL",
            name="ck_shift_assignment_out_needs_in",
        ),
        CheckConstraint(
            "clock_out_at IS NULL OR clock_out_at >= clock_in_at",
            name="ck_shift_assignment_out_after_in",
        ),
        # Present and late both mean somebody clocked in. Without this, a manager could set
        # `present` on a row with no times and M17 would count hours that were never worked.
        CheckConstraint(
            "status NOT IN ('present', 'late') OR clock_in_at IS NOT NULL",
            name="ck_shift_assignment_attended_has_a_time",
        ),
        Index("ix_shift_assignment_restaurant_date", "restaurant_id", "business_date"),
        Index("ix_shift_assignment_employee_date", "employee_id", "business_date"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    shift_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    # The section they cover. Nullable: a chef, a cleaner and an accountant have none.
    dining_area_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=ShiftAssignmentStatus.SCHEDULED.value
    )
    clock_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clock_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Loaded explicitly with `selectinload`, never lazily: a week's roster is forty rows and naming
    # the shift on each of them lazily would be forty queries — the N+1 every list screen in this
    # product is tested against.
    shift: Mapped[Shift] = relationship(lazy="raise")
