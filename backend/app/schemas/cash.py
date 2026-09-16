"""The API contract for the till.

Money is a string in JSON, never a float. **Expected cash, the adjusted variance and every total are
response fields only**: the server derives them from payment and movement rows, and a client that
could send one could send the answer it wanted (`docs/security.md` A04).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import CashMovementType, CashSessionStatus
from app.schemas.people import AdjusterResponse, PersonResponse


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ReadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


Reason = Annotated[str, Field(min_length=3, max_length=280)]


class CashOpenRequest(_Schema):
    opening_float: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class CashCountRequest(_Schema):
    """One denomination and how many of it. ₹2,000 is the largest note in circulation."""

    denomination: Annotated[Decimal, Field(gt=0, le=2000, max_digits=12, decimal_places=2)]
    quantity: int = Field(ge=0, le=100_000)


class CashCloseRequest(_Schema):
    counts: list[CashCountRequest] = Field(min_length=1, max_length=30)


class CashPayoutRequest(_Schema):
    amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
    reason: Reason

    _clean = field_validator("reason", mode="before")(_strip)


class CashAdjustmentRequest(_Schema):
    """Signed: positive for cash found, negative for cash that turned out to be missing."""

    amount: Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
    reason: Reason

    _clean = field_validator("reason", mode="before")(_strip)

    @model_validator(mode="after")
    def _moves_something(self) -> Self:
        if self.amount == 0:
            raise ValueError("An adjustment of nothing is not an adjustment.")
        return self


class CashCountResponse(_ReadSchema):
    denomination: Decimal
    quantity: int


class CashMovementResponse(_ReadSchema):
    id: uuid.UUID
    type: CashMovementType
    amount: Decimal
    reason: str
    recorded_by: uuid.UUID
    occurred_at: datetime
    # By name, code and role (D13); and whether the person who closed the till recorded it (D16).
    recorded_by_person: PersonResponse | None = None
    by_closer: bool = False


class CashSessionSummary(_Schema):
    id: uuid.UUID
    status: CashSessionStatus
    opened_at: datetime
    opened_by: uuid.UUID
    opening_float: Decimal
    business_date: date
    closed_at: datetime | None
    closed_by: uuid.UUID | None
    counted_cash: Decimal | None
    variance: Decimal | None
    cash_taken: Decimal
    payouts: Decimal
    adjustments: Decimal
    expected_cash: Decimal
    adjusted_variance: Decimal | None
    # Decision D13: who closed and who adjusted, shown beside the figures.
    closed_by_person: PersonResponse | None = None
    adjusted_by: list[AdjusterResponse] = Field(default_factory=list)


class CashSessionResponse(CashSessionSummary):
    counts: list[CashCountResponse]
    movements: list[CashMovementResponse]


class CashSessionListResponse(_Schema):
    items: list[CashSessionSummary]
    next_cursor: uuid.UUID | None = None


class CashOutsideTillResponse(_Schema):
    """Cash taken today that went into no till (decision D3, backlog-issues B7). Allowed — most
    restaurants will not use the till in month 1 — but no cash-up expects it, so it is said."""

    business_date: date
    cash_taken: Decimal
    payments: int
