"""The staff API contract for customers, feedback and complaints.

Separate from `app/schemas/guest.py` and never imported by it, which is ADR 0009's duplication
working as intended: a field added here cannot appear in a guest response, because no guest route
can answer with anything defined in this file and suite 5 proves it.

**Phone numbers are here and nowhere near a guest response.** A staff member holding `customer.view`
reads them; a diner holding a bill token never does, not even their own, because a response that
echoed a number back would be an oracle for whether we hold it (`docs/security.md`: "No
enumeration").

**Money is a string in JSON, never a float** (CLAUDE.md invariant 3).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.core.enums import (
    ComplaintCategory,
    ComplaintSeverity,
    ComplaintStatus,
    ConsentPurpose,
    ContactSource,
    PreferenceType,
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


# --------------------------------------------------------------------------- customer


class CustomerPreferenceResponse(_Schema):
    id: uuid.UUID
    type: PreferenceType
    value: str
    # The flag that decides whether the kitchen is told. An allergy is not a preference.
    is_critical: bool


class ConsentStateResponse(_Schema):
    """The current state of one purpose: the latest row in the ledger, flattened for a screen.

    `granted_at` is when the standing answer was given — a grant or a withdrawal — so a profile can
    show "marketing: off since 3 March" without the screen reading the whole history.
    """

    purpose: ConsentPurpose
    granted: bool
    occurred_at: datetime
    notice_version: str
    notice_language: str
    source: ContactSource


class CustomerResponse(_Schema):
    id: uuid.UUID
    phone: str
    name: str | None
    email: str | None
    first_visit_at: datetime | None
    last_visit_at: datetime | None
    visit_count: int
    lifetime_value: Decimal
    birthday: date | None
    anniversary: date | None
    # True once the DPDP erasure path has run. The row is still here because every order pointing at
    # it is a financial record; everything that named a person is gone.
    is_erased: bool
    is_active: bool
    preferences: list[CustomerPreferenceResponse]
    consents: list[ConsentStateResponse]


class CustomerListItem(_Schema):
    """The list is deliberately thinner than the profile. A screen showing every customer's birthday
    is a screen somebody photographs."""

    id: uuid.UUID
    phone: str
    name: str | None
    visit_count: int
    last_visit_at: datetime | None
    is_erased: bool


class CustomerListResponse(_Schema):
    items: list[CustomerListItem]
    next_cursor: uuid.UUID | None = None


class CustomerCreateRequest(_Schema):
    # Loose on purpose: Indian numbers are written with and without +91, with and without spaces,
    # and a validator strict enough to be useful here would refuse a real number at a busy counter.
    # `app/core/phone.py` normalises; this only bounds the length.
    phone: str = Field(min_length=8, max_length=20)
    name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    birthday: date | None = None
    anniversary: date | None = None

    _strip_name = field_validator("name", "email", mode="before")(_strip)


class CustomerUpdateRequest(_Schema):
    """No `phone`. It is the natural key: changing it silently merges or splits a person's history,
    and both are things somebody should have to do deliberately."""

    name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    birthday: date | None = None
    anniversary: date | None = None
    is_active: bool | None = None

    _strip_name = field_validator("name", "email", mode="before")(_strip)


class PreferenceCreateRequest(_Schema):
    type: PreferenceType
    value: str = Field(min_length=1, max_length=120)
    is_critical: bool = False

    _strip_value = field_validator("value", mode="before")(_strip)


class AttachCustomerRequest(_Schema):
    customer_id: uuid.UUID


class OrderCustomerResponse(_Schema):
    """What the waiter's screen shows after attaching somebody.

    `allergy_note` is echoed back deliberately: it is what the kitchen will be told, and the person
    who just attached the customer is the last one who can catch it being wrong. Null when there is
    nothing to warn about, which is the common case and must not read as a failure.
    """

    order_id: uuid.UUID
    customer_id: uuid.UUID
    allergy_note: str | None


class ConsentWriteRequest(_Schema):
    """One purpose per call. There is no way to express "all of them", which is the point:
    `docs/compliance-rules.md` §B2's purpose limitation is that a phone number collected for a bill
    is not marketing consent."""

    purpose: ConsentPurpose
    granted: bool
    notice_version: str = Field(min_length=1, max_length=40)
    notice_language: str = Field(min_length=2, max_length=8)


# --------------------------------------------------------------------------- feedback


class FeedbackLineResponse(_Schema):
    id: uuid.UUID
    order_line_id: uuid.UUID
    menu_item_variant_id: uuid.UUID
    rating: int
    comment: str | None


class FeedbackResponse(_Schema):
    id: uuid.UUID
    order_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    overall_rating: int | None
    food_rating: int | None
    service_rating: int | None
    cleanliness_rating: int | None
    would_return: bool | None
    waiter_employee_id: uuid.UUID | None
    comment: str | None
    # Visible everywhere, deliberately. A manager filling the form for a customer is legitimate;
    # hiding that it happened is not, and M17 pays attention to these numbers.
    source: ContactSource
    submitted_at: datetime
    business_date: date
    lines: list[FeedbackLineResponse]


class FeedbackListResponse(_Schema):
    items: list[FeedbackResponse]
    next_cursor: uuid.UUID | None = None


class StaffFeedbackCreateRequest(_Schema):
    """A manager writing down a conversation. `source` is fixed by the route, never sent."""

    order_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    overall_rating: int | None = Field(default=None, ge=1, le=5)
    food_rating: int | None = Field(default=None, ge=1, le=5)
    service_rating: int | None = Field(default=None, ge=1, le=5)
    cleanliness_rating: int | None = Field(default=None, ge=1, le=5)
    would_return: bool | None = None
    comment: str | None = Field(default=None, max_length=2000)


# --------------------------------------------------------------------------- complaints


class ComplaintResponse(_Schema):
    id: uuid.UUID
    customer_id: uuid.UUID | None
    order_id: uuid.UUID | None
    order_line_id: uuid.UUID | None
    feedback_id: uuid.UUID | None
    category: ComplaintCategory
    severity: ComplaintSeverity
    description: str
    reported_by: uuid.UUID | None
    assigned_to: uuid.UUID | None
    status: ComplaintStatus
    resolution: str | None
    compensation_amount: Decimal | None
    resolved_at: datetime | None
    closed_at: datetime | None
    business_date: date
    # Derived from the order ledger at read time, never stored (spec decision 8). None when the
    # complaint is not resolved yet, because "did they come back" has no meaning before then.
    customer_returned: bool | None


class ComplaintListResponse(_Schema):
    items: list[ComplaintResponse]
    next_cursor: uuid.UUID | None = None


class ComplaintCreateRequest(_Schema):
    category: ComplaintCategory
    severity: ComplaintSeverity
    description: str = Field(min_length=1, max_length=2000)
    customer_id: uuid.UUID | None = None
    order_id: uuid.UUID | None = None
    order_line_id: uuid.UUID | None = None
    feedback_id: uuid.UUID | None = None
    assigned_to: uuid.UUID | None = None

    _strip_description = field_validator("description", mode="before")(_strip)


class ComplaintAssignRequest(_Schema):
    assigned_to: uuid.UUID


class ComplaintResolveRequest(_Schema):
    """What was actually done. Required, and the database agrees: a complaint cannot reach
    `resolved` with an empty resolution, which is the paperwork this module exists to refuse."""

    resolution: str = Field(min_length=1, max_length=2000)
    compensation_amount: Decimal | None = Field(default=None, ge=0)

    _strip_resolution = field_validator("resolution", mode="before")(_strip)


# --------------------------------------------------------------------------- history & export


class CustomerVisitLine(_Schema):
    order_id: uuid.UUID
    business_date: date
    total: Decimal
    # What they had, by name. Not the waiter, not the station: this is a customer's history, and
    # M17 is where a person's work is looked at, with the fairness rules that come with it.
    items: list[str]


class CustomerHistoryResponse(_Schema):
    visits: list[CustomerVisitLine]
    feedback: list[FeedbackResponse]
    complaints: list[ComplaintResponse]


class CustomerExportResponse(_Schema):
    """The DPDP access right (§B2), built now rather than as a later scramble.

    Everything this product holds about one person, in one response: the profile, every preference,
    the whole consent ledger, every visit, every rating, every complaint. Per-customer and never
    bulk — a bulk export of the customer list is a competitor's most valuable asset and exists in
    nobody's API surface.
    """

    exported_at: AwareDatetime
    customer: CustomerResponse
    consent_history: list[ConsentStateResponse]
    history: CustomerHistoryResponse


class ErasureResponse(_Schema):
    """What was destroyed and what deliberately survives, so the screen can say both."""

    customer_id: uuid.UUID
    erased_at: AwareDatetime
    preferences_deleted: int
    # Unchanged, and shown to prove it: erasure must not move a rupee (acceptance criterion 5).
    orders_retained: int
    lifetime_value_retained: Decimal
