"""The API contract for M01. SQLAlchemy models never cross this boundary.

Two rules run through every schema here, both security controls rather than style:

- `extra="forbid"` everywhere, so mass assignment is impossible. A client cannot set `is_active`
  or `organization_id` by adding a field the endpoint did not ask for.
- Nothing that could carry a credential is ever declared on a *response*. There is no field named
  `password_hash`, `mfa_secret` or `refresh_token_hash` in this file at all, so no serialiser can
  emit one by accident.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import EmploymentType
from app.core.identifiers import is_email, is_phone, normalise_identifier


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ReadSchema(BaseModel):
    # from_attributes so a service can hand back an ORM object and get a validated contract; the
    # allow-list of fields below is what keeps the model's other columns out of the response.
    model_config = ConfigDict(extra="forbid", from_attributes=True)


# --------------------------------------------------------------------------- auth


class LoginRequest(_Schema):
    # "identifier" rather than "email": waiters and kitchen staff log in with a phone number, and
    # naming the field `email` would make the API lie about that on day one.
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("identifier")
    @classmethod
    def _normalise(cls, value: str) -> str:
        # One login, however it is typed (G-18): "98765 43210" signs in as "+919876543210".
        return normalise_identifier(value)


class PasswordChangeRequest(_Schema):
    current_password: str = Field(min_length=1, max_length=1024)
    # docs/security.md: length is the control that matters. A composition rule ("one capital, one
    # symbol") pushes people towards Passw0rd! and is not worth the friction.
    new_password: str = Field(min_length=10, max_length=1024)


class RefreshRequest(_Schema):
    """Present only for clients that cannot use the cookie — the browser app sends neither field
    and relies on the httpOnly cookie instead."""

    refresh_token: str | None = None


class ChooseOrganizationRequest(_Schema):
    """The second step of signing in, when the password opened accounts in more than one
    organization (backlog-issues B4). The pass stands in for the password, which is not sent
    again."""

    ticket: str = Field(min_length=1, max_length=200)
    organization_id: uuid.UUID


class OrganizationOption(_Schema):
    id: uuid.UUID
    name: str


class OrganizationChoiceResponse(_Schema):
    """What `POST /auth/login` answers instead of a session when the password opens accounts in more
    than one organization. No token and no cookie: nobody is signed in until one is chosen."""

    choose_organization: bool = True
    ticket: str
    expires_in_seconds: int
    organizations: list[OrganizationOption]


class RestaurantSummary(_ReadSchema):
    id: uuid.UUID
    name: str
    code: str
    timezone: str
    currency: str
    # Both halves of the business-day rule travel together, because either one alone is useless.
    # The browser has to produce a business date before it can make a request — the default in a
    # date field, the heading over today's figures — and `frontend/src/shared/businessDay.ts` needs
    # the zone *and* the start time to do it. Without this the UI falls back to the browser's clock,
    # which is how "joined on" came to default to yesterday for five and a half hours a day in
    # India. ADR 0004.
    business_day_start: time
    # So every screen can warn that the licence printed on its bills has lapsed (backlog B8).
    fssai_licence_expires_on: date | None = None
    # The restaurant-wide look and its festive schedule. Here rather than only on the settings
    # endpoint, for the same reason `business_day_start` is: that one is owner-and-admin-only, and
    # a theme has to render for the waiter too. Nothing here is sensitive — it is paint.
    theme: dict[str, Any] = Field(default_factory=lambda: {"default": None, "schedule": []})

    @classmethod
    def of(cls, restaurant: Any) -> RestaurantSummary:
        """Build from a `Restaurant`, lifting the theme out of the `settings` JSONB.

        A classmethod rather than a validator so the lift happens in one place: four endpoints build
        this summary, and a theme that appeared on three of them would be a bug nobody notices until
        a festive day looks wrong on exactly one screen.
        """
        summary = cls.model_validate(restaurant)
        stored = getattr(restaurant, "settings", {}).get("theme")
        if isinstance(stored, dict):
            schedule = stored.get("schedule")
            summary.theme = {
                "default": stored.get("default"),
                "schedule": schedule if isinstance(schedule, list) else [],
            }
        return summary


class SwitchRestaurantRequest(_Schema):
    """Which branch to move this session to. Nothing else: the person is already authenticated,
    and the endpoint decides for itself whether they work there."""

    restaurant_id: uuid.UUID


class SessionResponse(_Schema):
    """What the client gets after a successful login or refresh.

    The refresh token is *not* here. It is set as an httpOnly cookie, so script running on the page
    cannot read it — which is the difference between an XSS bug costing one session and costing a
    permanent account takeover.
    """

    access_token: str
    expires_in_seconds: int
    employee_id: uuid.UUID
    full_name: str
    restaurant: RestaurantSummary
    roles: list[str]
    permissions: list[str]
    # Somebody else set this password; the client sends the person to change it. Not a refusal —
    # an account that cannot sign in cannot have its password changed by its owner (P1-6).
    password_change_required: bool = False


class MeResponse(_Schema):
    """Drives permission-aware navigation.

    Not in docs/modules.md, and added deliberately: without it the client would have to infer what
    to show from a role name, which is exactly the anti-pattern ADR 0007 forbids.
    """

    employee_id: uuid.UUID
    full_name: str
    employee_code: str
    restaurant: RestaurantSummary
    # Every branch this person may switch to, including the current one (finding S12). The client
    # cannot offer a switcher without it, and deriving the list in the browser would be a second
    # implementation of the rule `POST /auth/switch` already enforces.
    #
    # At most twenty, always including the current one (backlog-issues B3): `/auth/me` runs on every
    # app load, and an unbounded list is the worst one to let grow. The rest page from
    # `GET /auth/restaurants`.
    restaurants: list[RestaurantSummary] = []
    has_more_restaurants: bool = False
    roles: list[str]
    permissions: list[str]
    # Whether this person serves tables. Sent because some screens are about *working the floor*
    # rather than about authority, and authority cannot express it: an owner holds every
    # permission there is (`["*"]`, expanded), so no permission can ever be absent from them.
    # See migration 0057.
    takes_tables: bool = False


class RestaurantPageResponse(_Schema):
    """The branches this person may switch to, a page at a time."""

    items: list[RestaurantSummary]
    next_cursor: uuid.UUID | None = None


# ----------------------------------------------------------------------- employees


class EmployeeResponse(_ReadSchema):
    id: uuid.UUID
    employee_code: str
    full_name: str
    phone: str | None
    joined_on: date
    employment_type: EmploymentType
    is_active: bool
    # Serves tables, and may therefore be recorded as the waiter on one. A fact about the job
    # rather than a permission — see migration 0057 for why a permission could not express it.
    takes_tables: bool
    deactivated_at: datetime | None
    # Whether this person can sign in at all. The account id itself is not exposed: it is of no
    # use to a client and it is the join key to the credentials table.
    has_login: bool
    roles: list[str] = Field(default_factory=list)


class EmployeeListResponse(_Schema):
    items: list[EmployeeResponse]
    # Cursor rather than a page number: uuid7 sorts in creation order, so this stays stable while
    # rows are being inserted (engineering-standards §3).
    next_cursor: uuid.UUID | None = None


def _two_letters(value: str | None) -> str | None:
    """At least two letters; initials, dots and digits may sit beside them ("S. Patil", "Ravi 2").

    Owner decision D15 (backlog-issues B12): `12345` was accepted as somebody's name."""
    if value is None:
        return None
    if sum(character.isalpha() for character in value) < 2:
        raise ValueError("Use at least two letters. Initials and digits are fine, like S. Patil.")
    return value


class EmployeeCreateRequest(_Schema):
    full_name: str = Field(min_length=1, max_length=200)
    employee_code: str = Field(min_length=1, max_length=40)
    joined_on: date
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    phone: str | None = Field(default=None, max_length=20)
    date_of_birth: date | None = None
    # Optional on purpose: ADR 0007 requires an employee who never logs in to be a normal thing,
    # not a workaround.
    login_identifier: str | None = Field(default=None, max_length=320)
    initial_password: str | None = Field(default=None, min_length=10, max_length=1024)

    _name = field_validator("full_name")(_two_letters)

    @field_validator("login_identifier")
    @classmethod
    def _normalise_login(cls, value: str | None) -> str | None:
        """Stored one way (G-18), and refused when it is neither a phone number nor an email."""
        if value is None or not value.strip():
            return None
        normal = normalise_identifier(value)
        if not (is_email(normal) or is_phone(normal)):
            raise ValueError("not a phone number or an email address")
        return normal

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().replace(" ", "")
        digits = cleaned.removeprefix("+")
        if not digits.isdigit() or not 7 <= len(digits) <= 15:
            raise ValueError("not a valid phone number")
        return cleaned


class EmployeeCodeResponse(_Schema):
    """The next free employee code, for the add-employee form to fill in (decision D19)."""

    employee_code: str


class EmployeeUpdateRequest(_Schema):
    """Every field optional — a PATCH changes what it names and nothing else.

    Note what is absent: `is_active` is not here. Deactivation is its own endpoint because it has
    to revoke sessions in the same transaction, and a field on a general-purpose update is far too
    easy to set without that happening.
    """

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    date_of_birth: date | None = None
    employment_type: EmploymentType | None = None
    takes_tables: bool | None = None

    _name = field_validator("full_name")(_two_letters)
    _validate_phone = field_validator("phone")(EmployeeCreateRequest._validate_phone.__func__)  # type: ignore[attr-defined]


class RoleAssignmentRequest(_Schema):
    """The whole set, not a delta. Sending the complete list makes removal expressible and makes
    two concurrent edits resolve to one of the two states rather than to a merge of both."""

    role_ids: list[uuid.UUID] = Field(max_length=20)


class PasswordResetRequest(_Schema):
    new_password: str = Field(min_length=10, max_length=1024)


# --------------------------------------------------------------- roles & catalogue


class RoleResponse(_ReadSchema):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    rank: int
    is_system: bool


class PermissionResponse(_ReadSchema):
    code: str
    resource: str
    action: str
    description: str
