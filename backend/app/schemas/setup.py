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
from itertools import pairwise
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


# --------------------------------------------------------------------------- theme


class ThemeWindow(_Schema):
    """A festive theme, for a stretch of days.

    Dates rather than a recurring rule: Deepavali is not on a fixed date, and a rule that tried to
    express "the lunar calendar" would be wrong in its second year. A restaurant sets the dates it
    cares about, which is also how it actually thinks about them.
    """

    theme: str = Field(min_length=1, max_length=40)
    starts_on: date
    ends_on: date

    _strip_theme = field_validator("theme", mode="before")(_strip)


class ThemeSettings(_Schema):
    """The restaurant-wide look, deferred here from the UI work.

    **The theme id is not validated against a list.** The themes live in
    `frontend/src/shared/theme/themes.ts`, and duplicating their ids here would create the second
    catalogue that finding M12 is about — two lists, free to disagree, with the server's copy
    authoritative over a file it cannot see. An id the client does not recognise falls back to the
    default look, which is a degradation rather than a failure, and the settings screen offers a
    picker so a typo is not reachable through the UI.

    What *is* validated is the part the client cannot sensibly resolve: that a window ends no
    earlier than it starts, and that two windows do not claim the same day.
    """

    default: str | None = Field(default=None, max_length=40)
    schedule: list[ThemeWindow] = Field(default_factory=list, max_length=24)

    _strip_default = field_validator("default", mode="before")(_strip)

    @model_validator(mode="after")
    def _windows_are_ordered_and_disjoint(self) -> ThemeSettings:
        for window in self.schedule:
            if window.ends_on < window.starts_on:
                raise ValueError(
                    f"{window.theme!r} ends on {window.ends_on} but starts on {window.starts_on}"
                )
        # Overlap is refused rather than resolved by precedence. Two themes claiming one day has no
        # right answer, and picking the first silently would make the second window disappear on a
        # date nobody is looking at.
        ordered = sorted(self.schedule, key=lambda window: window.starts_on)
        for earlier, later in pairwise(ordered):
            if later.starts_on <= earlier.ends_on:
                raise ValueError(
                    f"{earlier.theme!r} and {later.theme!r} both cover {later.starts_on}"
                )
        return self


# --------------------------------------------------------------------------- the restaurant


class PostalAddress(_Schema):
    """The restaurant's address, structured — because the column is and the bill needs it to be.

    `restaurant.address` is JSONB and `seed/organization.yaml` writes an object into it. This was
    typed `str | None` until external review found it, which made `GET /staff/restaurant` raise a
    `ValidationError` — a 500 — for **every seeded restaurant**, on the first screen of the module.
    Every test fixture built a restaurant without an address, so the whole suite stayed green and
    only `make seed` produced the failing shape.

    Structured rather than a free-text blob because the parts are needed separately: a bill prints
    the lines, and `state` is what decides CGST/SGST versus IGST on every invoice this restaurant
    issues. A single string would have to be re-parsed by each of those, differently.

    Every field is optional except `line1` and `city`: onboarding collects an address before it
    collects a complete one, and refusing a half-known address would block the first screen a new
    restaurant sees.
    """

    line1: str = Field(min_length=1, max_length=120)
    line2: str | None = Field(default=None, max_length=120)
    city: str = Field(min_length=1, max_length=80)
    state: str | None = Field(default=None, max_length=80)
    # Six digits, never leading zero. It prints on the bill and appears on a GST filing, and a typo
    # is caught by nothing downstream.
    pincode: str | None = Field(default=None, pattern=r"^[1-9][0-9]{5}$")

    _strip_line1 = field_validator("line1", "line2", "city", "state", mode="before")(_strip)


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
    address: PostalAddress | None
    # Lives in the `settings` JSONB rather than in columns: it is genuinely configuration, unlike
    # the FSSAI licence that finding S13 moved *out* of settings because it prints on every bill.
    theme: ThemeSettings = ThemeSettings()


class RestaurantUpdateRequest(_Schema):
    """Every field optional; only what is sent is changed.

    `name` and `code` are absent on purpose. The code is referenced by the seed and by operational
    data, and renaming the restaurant is an organization-level act rather than a setup one — M02's
    permission is `restaurant.configure`, which is about how the restaurant *runs*.
    """

    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    business_day_start: time | None = None
    # Structure, not merely length. The M02 threat table asks for these to be
    # "format-validated, not merely non-empty", because the attack it describes is substituting a
    # supplier's number so bills carry someone else's tax identity — and a typo is only found at
    # return time. GSTIN: 2-digit state code, 10-character PAN, entity digit, 'Z', checksum.
    gstin: str | None = Field(
        default=None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
    )
    fssai_licence: str | None = Field(default=None, pattern=r"^[0-9]{14}$")
    # Cleared with an explicit null: a cloud kitchen with no shopfront is a real thing.
    address: PostalAddress | None = None
    theme: ThemeSettings | None = None


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


class TaxRateResponse(_ReadSchema):
    id: uuid.UUID
    # A string in JSON — "0.0500" is five percent. Never a float: the rate is copied onto every
    # order line and cited by an invoice (ADR 0004, CLAUDE.md invariant 3).
    rate: Decimal
    is_inclusive: bool
    effective_from: date
    # NULL means "still current". Set when a replacement rate supersedes this one.
    effective_to: date | None


class TaxGroupResponse(_ReadSchema):
    """A tax class and every rate it has ever charged, newest first.

    The rates travel with the group because that is what the screen shows and what a menu item
    needs: an item names the group, and which rate applies depends on the business date.
    """

    id: uuid.UUID
    # Stable, immutable, unique per restaurant. `seed/operations.yaml` has always carried it.
    code: str
    name: str
    is_active: bool
    rates: list[TaxRateResponse]


class TaxGroupListResponse(_Schema):
    items: list[TaxGroupResponse]
    next_cursor: uuid.UUID | None = None


class TaxGroupCreateRequest(_Schema):
    """A new tax class, with the rate it charges from day one.

    Group and first rate are created together because a group charging nothing is not yet usable by
    a menu item, and leaving it creatable would let someone attach a dish to a tax class with no
    rate — a 500 at order time, in M07, months from here.
    """

    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z][A-Z0-9_]*$")
    name: str = Field(min_length=1, max_length=80)
    rate: Decimal = Field(ge=0, le=1, max_digits=6, decimal_places=4)
    is_inclusive: bool = False
    effective_from: date

    _strip_code = field_validator("code", mode="before")(_strip)
    _strip_name = field_validator("name", mode="before")(_strip)


class TaxGroupUpdateRequest(_Schema):
    """Name and active flag only.

    `code` is immutable because `menu_item_variant`, `seed/operations.yaml` and every future recipe
    join on it — the same rule `station.code` follows. The rate is not here either: rates live in
    their own rows and a change is a new one, because both are copied onto orders and cited by
    invoices. Editing either in place would restate tax already charged and reported — a filing
    problem, not a data-quality one. The schema is where that is enforced first: there is no field
    here to send.
    """

    name: str | None = Field(default=None, min_length=1, max_length=80)
    is_active: bool | None = None

    _strip_name = field_validator("name", mode="before")(_strip)


class TaxRateCreateRequest(_Schema):
    """A new rate for an existing group, superseding whatever it currently charges.

    There is no `supersedes_id`: the group already says which rate is being replaced, because only
    one rate of a group can be live on any date. M02 made the caller name the superseded row and
    then had to check that the name matched — a step that existed only because the group had no
    identity of its own.
    """

    rate: Decimal = Field(ge=0, le=1, max_digits=6, decimal_places=4)
    is_inclusive: bool = False
    effective_from: date
