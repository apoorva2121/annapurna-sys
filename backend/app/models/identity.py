"""Authentication and the employment record — deliberately three tables, not one (ADR 0007).

`user_account` knows how to sign someone in and nothing else. `employee` knows who a person is and
carries no credentials. The link between them is nullable, because a cleaner referenced by shifts
and wastage events may never have a password, and a customer will eventually authenticate without
being an employee at all.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EmploymentType, UserAccountStatus
from app.models.base import Base, TimestampedUUIDMixin

_STATUSES = ", ".join(f"'{member.value}'" for member in UserAccountStatus)
_EMPLOYMENT_TYPES = ", ".join(f"'{member.value}'" for member in EmploymentType)


class UserAccount(TimestampedUUIDMixin, Base):
    """Credentials only. Knows nothing about restaurants or jobs."""

    __tablename__ = "user_account"
    __table_args__ = (
        # An account nobody can sign in to is not a valid account.
        CheckConstraint(
            "email IS NOT NULL OR phone IS NOT NULL", name="ck_user_account_has_an_identifier"
        ),
        CheckConstraint(f"status IN ({_STATUSES})", name="ck_user_account_status"),
        # Uniqueness is per tenant, never global: a globally unique email would let one restaurant
        # group probe whether an address is registered to another, and would block a consultant
        # who genuinely works for two.
        UniqueConstraint("organization_id", "email", name="uq_user_account_org_email"),
        UniqueConstraint("organization_id", "phone", name="uq_user_account_org_phone"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False
    )
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    # Null while invited-but-not-activated. Argon2id, never reversible, never returned by any API.
    password_hash: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=UserAccountStatus.INVITED)
    # The column exists from day one so enabling MFA later is a feature, not a migration on a live
    # table. No enrolment flow in M01 (M01 spec, Not in scope).
    mfa_secret: Mapped[str | None] = mapped_column(Text)
    # Set when somebody else sets this account's password, cleared when its owner changes it. The
    # reset itself is legitimate; what this ends is the standing ability of whoever performed it to
    # sign in as this person afterwards (P1-6).
    password_reset_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(TimestampedUUIDMixin, Base):
    """One refresh token, stored hashed.

    Hashed rather than plaintext so a stolen database dump yields hashes rather than live sessions
    — the same reasoning as the password column, applied to the credential that outlives it.
    """

    __tablename__ = "user_session"
    __table_args__ = (
        Index("ix_user_session_account_expiry", "user_account_id", "expires_at"),
        # Revocation sweeps read this: "every live session for this account".
        Index(
            "ix_user_session_live",
            "user_account_id",
            postgresql_where="revoked_at IS NULL",
        ),
    )

    user_account_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("user_account.id"), nullable=False
    )
    refresh_token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # Every rotation of a refresh token belongs to the family started at login. Replaying a
    # rotated token revokes the whole family, so a stolen token is worth one use at most.
    family_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    device_info: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Which branch this session has navigated to (`POST /auth/switch`, finding S12). NULL means
    # "wherever login would put you", which is what every session did before the column existed.
    #
    # It is a *preference*, never an authorisation: `refresh()` re-checks the assignment every time
    # and falls back to the home branch if the role is gone. A stale value here can cost a redirect
    # and cannot grant access.
    restaurant_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id", ondelete="SET NULL")
    )


class Employee(TimestampedUUIDMixin, Base):
    """The business profile. Owned by the organization; roles are assigned per restaurant."""

    __tablename__ = "employee"
    __table_args__ = (
        CheckConstraint(
            f"employment_type IN ({_EMPLOYMENT_TYPES})", name="ck_employee_employment_type"
        ),
        UniqueConstraint("organization_id", "employee_code", name="uq_employee_org_code"),
        Index("ix_employee_org_active", "organization_id", "is_active"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False
    )
    # Nullable and unique: an employee without a login is normal (ADR 0007), and one login must
    # never map to two people or the second silently inherits the first's sessions.
    user_account_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("user_account.id"), unique=True
    )
    employee_code: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    joined_on: Mapped[date] = mapped_column(Date, nullable=False)
    employment_type: Mapped[str] = mapped_column(
        Text, nullable=False, default=EmploymentType.FULL_TIME
    )
    # Master-data tier (ADR 0008): deactivated, never deleted. Historical orders, shifts and
    # wastage events point at this row forever.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
