"""The API contract for the roster and the clock.

**Clocking in takes no body at all**, and that is the contract's main feature. There is no
`employee_id` to send, so clocking somebody else in is not a permission that could be granted by
mistake — it is a field that does not exist (M12 spec decision 3).

**A correction requires a reason**, in the schema and again in the service. A manager asserting
somebody else's attendance is a real act with a real author, and a reason that a client could omit
is a reason nobody would write.

**Times are local wall-clock (`time`), dates are business dates.** A shift is "six in the evening",
which stays six in the evening across a daylight-saving change that an instant would not survive;
where it actually sits in real time is derived per business date by `app/core/shift_window.py`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.core.enums import ShiftAssignmentStatus


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ShiftCreateRequest(_Schema):
    name: str = Field(min_length=1, max_length=60)
    start_time: time
    # May be earlier than `start_time`: that is a shift crossing midnight, which is what an evening
    # shift in a place that closes at two actually is.
    end_time: time


class ShiftUpdateRequest(_Schema):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    start_time: time | None = None
    end_time: time | None = None
    is_active: bool | None = None


class ShiftResponse(_Schema):
    id: uuid.UUID
    name: str
    start_time: time
    end_time: time
    # Derived, so a screen never has to compare two times to know how to render one.
    crosses_midnight: bool
    is_active: bool


class AssignmentCreateRequest(_Schema):
    shift_id: uuid.UUID
    employee_id: uuid.UUID
    business_date: date
    # ADR 0011: the column that makes an assist derivable. Null for a chef, a cleaner, an
    # accountant — anybody with no section.
    dining_area_id: uuid.UUID | None = None


class AssignmentUpdateRequest(_Schema):
    """A manager correcting a time or a section. The reason is not optional."""

    clock_in_at: AwareDatetime | None = None
    clock_out_at: AwareDatetime | None = None
    dining_area_id: uuid.UUID | None = None
    reason: str = Field(min_length=1, max_length=500)


class AssignmentStatusRequest(_Schema):
    """`absent`, `leave` or back to `scheduled`. `present` and `late` are what clocking in means,
    and the service refuses to let anybody assert one of those by hand."""

    status: ShiftAssignmentStatus


class AssignmentResponse(_Schema):
    id: uuid.UUID
    shift_id: uuid.UUID
    shift_name: str
    start_time: time
    end_time: time
    employee_id: uuid.UUID
    employee_name: str | None
    dining_area_id: uuid.UUID | None
    business_date: date
    status: ShiftAssignmentStatus
    clock_in_at: datetime | None
    clock_out_at: datetime | None
    # True when somebody clocked in and never clocked out. Shown as open rather than closed at a
    # guessed time, because M17 normalises per hour worked and a wrong denominator is worse than a
    # missing one.
    is_open: bool


class RosterResponse(_Schema):
    since: date
    until: date
    items: list[AssignmentResponse]


class ShiftListResponse(_Schema):
    items: list[ShiftResponse]


class OnNowEntry(_Schema):
    assignment_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None
    shift_name: str
    dining_area_id: uuid.UUID | None
    status: ShiftAssignmentStatus


class OnNowResponse(_Schema):
    business_date: date
    items: list[OnNowEntry]
