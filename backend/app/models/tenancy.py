"""Organization and restaurant — the two scopes every other row hangs from.

An organization is the customer (a restaurant group, often of one). A restaurant is a branch, and
is the tenant boundary for operational data: `restaurant_id` is the filter that keeps one
restaurant's orders, stock and staff invisible to another (ADR 0003).
"""

from __future__ import annotations

import uuid
from datetime import time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import OrganizationPlan
from app.models.base import Base, TimestampedUUIDMixin

_PLANS = ", ".join(f"'{member.value}'" for member in OrganizationPlan)


class Organization(TimestampedUUIDMixin, Base):
    __tablename__ = "organization"
    __table_args__ = (CheckConstraint(f"plan IN ({_PLANS})", name="ck_organization_plan"),)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    billing_email: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[str] = mapped_column(Text, nullable=False, default=OrganizationPlan.TRIAL)
    # Seeded demo organizations are excluded from every report, so a sales demo can never be
    # mistaken for a real restaurant's numbers.
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Restaurant(TimestampedUUIDMixin, Base):
    __tablename__ = "restaurant"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_restaurant_org_code"),
        Index("ix_restaurant_organization_id", "organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    # IANA zone, not an offset: offsets change twice a year in some jurisdictions and India's
    # does not, but the column outlives that assumption.
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Asia/Kolkata")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    # NOT midnight (ADR 0004). A restaurant closing at 2am must have that 2am counted against the
    # previous business day, or every daily figure it reads is wrong.
    business_day_start: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(5, 0), server_default="05:00"
    )
    gstin: Mapped[str | None] = mapped_column(Text)
    # A column rather than a key in `settings` (finding S13). It prints on every bill and is a
    # legal requirement for a food business in India — that is not configuration. M01's seed put it
    # in `settings` only because no column existed yet; migration 0004 moves it.
    fssai_licence: Mapped[str | None] = mapped_column(Text)
    address: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    settings: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
