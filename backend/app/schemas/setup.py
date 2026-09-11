"""The API contract for restaurant setup — settings, the floor, the stations, the tax rates.

Three things here are deliberate and would be wrong if copied casually into a later module:

**A rate is a string in JSON, never a number.** `"0.0500"` is five percent. engineering-standards §4
requires it for money and the same reasoning applies to the multiplier: a rate that arrives as a
JavaScript float has already lost the exactness that makes the tax on a bill reproducible. Pydantic
serialises `Decimal` as a string here because the model is configured to.

**Update requests use `None` to mean "not supplied", so nothing can be blanked by omission.** Every
field on a PATCH body is optional, which makes "leave it alone" and "set it to null" the same JSON
for a nullable column. Where that distinction matters — `effective_to`, `fssai_licence` — the
service is told explicitly which keys the client actually sent (`model_fields_set`), rather than
guessing from the value.

**`extra="forbid"` everywhere**, inherited from the base classes. A PATCH that misspells a field
name is refused rather than silently doing nothing, which is the failure people spend an afternoon
on: the request succeeds, returns 200, and changes nothing.
"""

from __future__ import annotations

import uuid
from datetime import date, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import TableStatus


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ReadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


def _strip(value: Any) -> Any:
    """Strip **before** the length constraint, not after.

    An "after" validator runs once `min_length` has already passed, so `"   "` satisfies
    `min_length=1` as three characters and is then stripped to nothing — creating a dining area
    with an empty name and a 201 to say it went well. Stripping first means the constraint sees
    what will actually be stored.

    Non-strings pass through untouched so that a wrong type still produces Pydantic's own type
    error rather than an AttributeError from here.
    """
    return value.strip() if isinstance(value, str) else value


# --------------------------------------------------------------------------- the restaurant


class RestaurantResponse(_ReadSchema):
    id: uuid.UUID
    name: str
    code: str
    timezone: str
    currency: str
    business_day_start: time
    gstin: str | None
    # A column since 0004 (finding S13): it prints on every bill and is a legal requirement for a
    # food business in India, so it is not a settings key.
    fssai_licence: str | None
    address: str | None


class RestaurantUpdateRequest(_Schema):
    """Every field optional; only what is sent is changed.

    `name` and `code` are absent on purpose. The code is referenced by the seed and by operational
    data, and renaming the restaurant is an organization-level act rather than a setup one — M02's
    permission is `restaurant.configure`, which is about how the restaurant *runs*.
    """

    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    business_day_start: time | None = None
    gstin: str | None = Field(default=None, max_length=15)
    fssai_licence: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=500)


# --------------------------------------------------------------------------- the floor


class DiningAreaResponse(_ReadSchema):
    id: uuid.UUID
    name: str
    seq: int
    is_active: bool


class DiningAreaListResponse(_Schema):
    items: list[DiningAreaResponse]
    next_cursor: uuid.UUID | None = None


class DiningAreaCreateRequest(_Schema):
    name: str = Field(min_length=1, max_length=80)
    # Defaults to the end of the list rather than to 0, which would put every new area first.
    seq: int | None = Field(default=None, ge=0, le=32767)

    _strip_name = field_validator("name", mode="before")(_strip)


class DiningAreaUpdateRequest(_Schema):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    seq: int | None = Field(default=None, ge=0, le=32767)
    # ADR 0008: deactivated, never deleted. A table in this area that hosted an order last year
    # must still resolve.
    is_active: bool | None = None

    _strip_name = field_validator("name", mode="before")(_strip)


class TableResponse(_ReadSchema):
    id: uuid.UUID
    dining_area_id: uuid.UUID
    code: str
    seats: int
    status: TableStatus
    is_active: bool


class TableListResponse(_Schema):
    items: list[TableResponse]
    next_cursor: uuid.UUID | None = None


class TableCreateRequest(_Schema):
    dining_area_id: uuid.UUID
    # "T4" is what staff say out loud and what prints on a KOT.
    code: str = Field(min_length=1, max_length=20)
    seats: int = Field(ge=1, le=100)

    _strip_code = field_validator("code", mode="before")(_strip)


class TableUpdateRequest(_Schema):
    dining_area_id: uuid.UUID | None = None
    code: str | None = Field(default=None, min_length=1, max_length=20)
    seats: int | None = Field(default=None, ge=1, le=100)
    # Live state, and the only field here that changes during service rather than during setup.
    # `reserved` is set by hand by a manager taking a walk-in booking (M02 spec decision 3).
    status: TableStatus | None = None
    is_active: bool | None = None

    _strip_code = field_validator("code", mode="before")(_strip)


# --------------------------------------------------------------------------- the kitchen


class StationResponse(_ReadSchema):
    id: uuid.UUID
    code: str
    name: str
    seq: int
    is_active: bool


class StationListResponse(_Schema):
    items: list[StationResponse]
    next_cursor: uuid.UUID | None = None


class StationCreateRequest(_Schema):
    """`code` is a contract, not free text: `seed/menu.yaml` already routes dishes by `tandoor`,
    `main_kitchen` and `chinese`, and M08 will render one column per station."""

    code: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=80)
    seq: int | None = Field(default=None, ge=0, le=32767)

    _strip_name = field_validator("name", mode="before")(_strip)


class StationUpdateRequest(_Schema):
    """No `code`. Renaming a code orphans the menu routing that points at it, so the display name
    is editable and the identifier is not — the distinction the schema exists to make."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    seq: int | None = Field(default=None, ge=0, le=32767)
    is_active: bool | None = None

    _strip_name = field_validator("name", mode="before")(_strip)


# --------------------------------------------------------------------------- tax


class TaxGroupResponse(_ReadSchema):
    id: uuid.UUID
    name: str
    # A string in JSON — "0.0500" is five percent. Never a float: the rate is copied onto every
    # order line and cited by an invoice (ADR 0004, CLAUDE.md invariant 3).
    rate: Decimal
    is_inclusive: bool
    effective_from: date
    # NULL means "still current". Set when a replacement rate supersedes this one.
    effective_to: date | None


class TaxGroupListResponse(_Schema):
    items: list[TaxGroupResponse]
    next_cursor: uuid.UUID | None = None


class TaxGroupCreateRequest(_Schema):
    """Creating a rate, or replacing one.

    A rate change is a **new row**, never an edit (M02 spec decision 2). Passing `supersedes_id`
    closes the named row the day before this one starts and opens this one — done in a single
    service call so the two rows cannot end up overlapping or leaving a gap.
    """

    name: str = Field(min_length=1, max_length=80)
    rate: Decimal = Field(ge=0, le=1, max_digits=6, decimal_places=4)
    is_inclusive: bool = False
    effective_from: date
    supersedes_id: uuid.UUID | None = None

    _strip_name = field_validator("name", mode="before")(_strip)


class TaxGroupUpdateRequest(_Schema):
    """Name only.

    The rate and the dates are immutable once the row exists, because both are copied onto orders
    and cited by invoices. Editing them in place would restate tax already charged and reported —
    a filing problem, not a data-quality one. The schema is where that is enforced first: there is
    no field here to send.
    """

    name: str = Field(min_length=1, max_length=80)

    _strip_name = field_validator("name", mode="before")(_strip)
