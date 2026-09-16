"""Customers, feedback and complaints — `docs/schema.md` §9, migration 0036.

Argued in `docs/modules/M10-customers-spec.md`. Four things here are load-bearing:

**1 · Two ids: the organization owns the record, the branch owns the view.** A chain recognises the
same diner across branches, and a regular whose allergy is known at one branch has the same allergy
at the next — so the tenant column is `organization_id`, as it is on `employee`. But the *view* is
not the organization's: a manager reads the customers of the branches they are assigned to, and
`home_restaurant_id` is what a customer with no orders yet is attributed by. Owner's decision,
2026-09-16, argued in `docs/modules/M10-customers-spec.md` decision 5.

**2 · Consent is a ledger, not a column.** `customer_consent` is append-only: a grant is a row and a
withdrawal is a row, and the current state of a purpose is the latest row for it.
`docs/compliance-rules.md` §B2 asks for one row per purpose, never a single boolean, with the notice
version and language retained — because what somebody was shown is part of what they agreed to, and
a consent history that can be rewritten is not evidence of anything.

**3 · An allergy is not a preference.** `is_critical` is the flag that decides whether the kitchen
is told, and the telling is a *copy* taken when the customer is attached to the order — never a live
join. A preference deleted next week must not change what the kitchen was warned about on a ticket
it has already cooked.

**4 · `complaint` has no `customer_returned` column**, deliberately, and §9 says so. Whether the
customer came back is derived from the order ledger at read time. The column would be a stale copy
of a derivation that is always right, and nobody would ever remember to update it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    ComplaintCategory,
    ComplaintSeverity,
    ComplaintStatus,
    ConsentPurpose,
    ContactSource,
    PreferenceType,
)
from app.models.base import Base, TimestampedUUIDMixin


def _uuid() -> Any:
    return postgresql.UUID(as_uuid=True)


def _values(members: Any) -> str:
    return ", ".join(f"'{member.value}'" for member in members)


class Customer(TimestampedUUIDMixin, Base):
    """A diner the restaurant recognises. Organization-scoped, because a chain is one relationship.

    `phone` is the natural key and is NOT NULL, which is why erasure writes a placeholder rather
    than a null — and why, after erasure, the same person returning is a new customer with no
    history. That is what erasure means.
    """

    __tablename__ = "customer"
    __table_args__ = (
        ForeignKeyConstraint(
            ["home_restaurant_id"], ["restaurant.id"], name="fk_customer_home_restaurant"
        ),
        UniqueConstraint("organization_id", "phone", name="uq_customer_organization_phone"),
        UniqueConstraint("id", "organization_id", name="uq_customer_id_organization"),
        UniqueConstraint("user_account_id", name="uq_customer_user_account"),
        CheckConstraint("visit_count >= 0", name="ck_customer_visit_count"),
        CheckConstraint("lifetime_value >= 0", name="ck_customer_lifetime_value"),
        Index("ix_customer_organization_last_visit", "organization_id", "last_visit_at"),
        Index("ix_customer_home_restaurant", "home_restaurant_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("organization.id"), nullable=False
    )
    user_account_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid(), ForeignKey("user_account.id")
    )
    # Where this person was first written down. Nullable: a guest who arrives through a table QR is
    # attributed by the order they rated, not by a counter.
    home_restaurant_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    first_visit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_visit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    visit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lifetime_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    birthday: Mapped[date | None] = mapped_column(Date)
    anniversary: Mapped[date | None] = mapped_column(Date)
    # Set once by the DPDP erasure path and never cleared. The row stays: every order pointing at
    # it is a financial record.
    erased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    preferences: Mapped[list[CustomerPreference]] = relationship(
        back_populates="customer", lazy="raise", cascade="all, delete-orphan"
    )

    @property
    def is_erased(self) -> bool:
        return self.erased_at is not None


class CustomerPreference(TimestampedUUIDMixin, Base):
    """What this person always wants, and the one kind the kitchen is told about.

    `is_critical` means allergy. `docs/customer-experience.md` puts the rest — spice level, seating,
    "usually orders Butter Chicken" — on the waiter's screen, and they stay there: a ticket carrying
    a regular's seating preference is noise, and noise on a ticket is how a real allergy gets
    skimmed past.
    """

    __tablename__ = "customer_preference"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customer.id", "customer.organization_id"],
            name="fk_customer_preference_customer_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "customer_id", "type", "value", name="uq_customer_preference_customer_type_value"
        ),
        CheckConstraint(f"type IN ({_values(PreferenceType)})", name="ck_customer_preference_type"),
        Index(
            "ix_customer_preference_critical",
            "customer_id",
            postgresql_where=text("is_critical"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    customer: Mapped[Customer] = relationship(back_populates="preferences", lazy="raise")


class CustomerConsent(TimestampedUUIDMixin, Base):
    """One row per consent event, per purpose. Append-only.

    A withdrawal is a new row with `granted = False`, which is what makes withdrawal exactly as easy
    as granting (§B2) and what makes the history provable. Nothing updates a row here.
    """

    __tablename__ = "customer_consent"
    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customer.id", "customer.organization_id"],
            name="fk_customer_consent_customer_tenant",
        ),
        CheckConstraint(
            f"purpose IN ({_values(ConsentPurpose)})", name="ck_customer_consent_purpose"
        ),
        CheckConstraint(f"source IN ({_values(ContactSource)})", name="ck_customer_consent_source"),
        Index(
            "ix_customer_consent_lookup",
            "customer_id",
            "purpose",
            text("occurred_at DESC"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notice_version: Mapped[str] = mapped_column(Text, nullable=False)
    notice_language: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    # Null when the guest ticked it themselves — the case §B2 cares most about.
    captured_by: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Feedback(TimestampedUUIDMixin, Base):
    """Three questions, and never a fourth.

    The QR form asks `food_rating`, `service_rating` and `would_return`, plus an optional comment.
    `overall_rating` and `cleanliness_rating` are for `source in (staff, call)`: a manager writing
    down a conversation is not filling a three-tap form.

    One row per order, by unique index. "Never ask twice in one visit" is not a screen rule —
    a guest who taps twice on a slow network gets the first row back, unchanged.
    """

    __tablename__ = "feedback"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "restaurant_id"],
            ["order.id", "order.restaurant_id"],
            name="fk_feedback_order_tenant",
        ),
        UniqueConstraint("id", "restaurant_id", name="uq_feedback_id_restaurant"),
        CheckConstraint(f"source IN ({_values(ContactSource)})", name="ck_feedback_source"),
        CheckConstraint(
            "overall_rating IS NULL OR overall_rating BETWEEN 1 AND 5",
            name="ck_feedback_overall_rating",
        ),
        CheckConstraint(
            "food_rating IS NULL OR food_rating BETWEEN 1 AND 5", name="ck_feedback_food_rating"
        ),
        CheckConstraint(
            "service_rating IS NULL OR service_rating BETWEEN 1 AND 5",
            name="ck_feedback_service_rating",
        ),
        CheckConstraint(
            "cleanliness_rating IS NULL OR cleanliness_rating BETWEEN 1 AND 5",
            name="ck_feedback_cleanliness_rating",
        ),
        CheckConstraint(
            "overall_rating IS NOT NULL OR food_rating IS NOT NULL "
            "OR service_rating IS NOT NULL OR cleanliness_rating IS NOT NULL "
            "OR would_return IS NOT NULL OR comment IS NOT NULL",
            name="ck_feedback_says_something",
        ),
        Index(
            "uq_feedback_order",
            "order_id",
            unique=True,
            postgresql_where=text("order_id IS NOT NULL"),
        ),
        Index("ix_feedback_restaurant_date", "restaurant_id", "business_date"),
        Index("ix_feedback_restaurant_waiter", "restaurant_id", "waiter_employee_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    customer_id: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("customer.id"))
    overall_rating: Mapped[int | None] = mapped_column(SmallInteger)
    food_rating: Mapped[int | None] = mapped_column(SmallInteger)
    service_rating: Mapped[int | None] = mapped_column(SmallInteger)
    cleanliness_rating: Mapped[int | None] = mapped_column(SmallInteger)
    would_return: Mapped[bool | None] = mapped_column(Boolean)
    waiter_employee_id: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)

    lines: Mapped[list[FeedbackLine]] = relationship(
        back_populates="feedback", lazy="raise", cascade="all, delete-orphan"
    )


class FeedbackLine(TimestampedUUIDMixin, Base):
    """A rating against one dish on one order line.

    Optional everywhere: the three questions are the module, and a per-dish rating is what a guest
    who wants to say more can add. `menu_item_variant_id` is carried alongside the order line so
    M13 can ask "how is this dish rated" without walking every order.
    """

    __tablename__ = "feedback_line"
    __table_args__ = (
        ForeignKeyConstraint(
            ["feedback_id", "restaurant_id"],
            ["feedback.id", "feedback.restaurant_id"],
            name="fk_feedback_line_feedback_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["order_line_id", "restaurant_id"],
            ["order_line.id", "order_line.restaurant_id"],
            name="fk_feedback_line_order_line_tenant",
        ),
        ForeignKeyConstraint(
            ["menu_item_variant_id", "restaurant_id"],
            ["menu_item_variant.id", "menu_item_variant.restaurant_id"],
            name="fk_feedback_line_variant_tenant",
        ),
        UniqueConstraint("feedback_id", "order_line_id", name="uq_feedback_line_once_per_line"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_feedback_line_rating"),
        Index("ix_feedback_line_variant", "menu_item_variant_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    feedback_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    order_line_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    menu_item_variant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)

    feedback: Mapped[Feedback] = relationship(back_populates="lines", lazy="raise")


class Complaint(TimestampedUUIDMixin, Base):
    """Something went wrong, who owns it, and what was done about it.

    `docs/customer-experience.md`: "A logged complaint that nobody resolves is worse than no
    system." So an owner and a resolution are what the table is shaped around — `resolved` without
    a written resolution is refused by a check constraint, not by a screen.

    No `customer_returned` column. Whether they came back is a question the order ledger answers
    correctly for ever; a column would be a copy of it that nobody updates.
    """

    __tablename__ = "complaint"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "restaurant_id"],
            ["order.id", "order.restaurant_id"],
            name="fk_complaint_order_tenant",
        ),
        ForeignKeyConstraint(
            ["order_line_id", "restaurant_id"],
            ["order_line.id", "order_line.restaurant_id"],
            name="fk_complaint_order_line_tenant",
        ),
        ForeignKeyConstraint(
            ["feedback_id", "restaurant_id"],
            ["feedback.id", "feedback.restaurant_id"],
            name="fk_complaint_feedback_tenant",
        ),
        UniqueConstraint("id", "restaurant_id", name="uq_complaint_id_restaurant"),
        UniqueConstraint(
            "restaurant_id", "financial_year", "reference", name="uq_complaint_reference_per_year"
        ),
        CheckConstraint(
            f"category IN ({_values(ComplaintCategory)})", name="ck_complaint_category"
        ),
        CheckConstraint(
            f"severity IN ({_values(ComplaintSeverity)})", name="ck_complaint_severity"
        ),
        CheckConstraint(f"status IN ({_values(ComplaintStatus)})", name="ck_complaint_status"),
        CheckConstraint(
            "status NOT IN ('resolved', 'closed') "
            "OR (resolved_at IS NOT NULL AND resolution IS NOT NULL)",
            name="ck_complaint_resolution_pair",
        ),
        CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL)", name="ck_complaint_closed_pair"
        ),
        CheckConstraint(
            "compensation_amount IS NULL OR compensation_amount >= 0",
            name="ck_complaint_compensation_not_negative",
        ),
        Index("ix_complaint_restaurant_status", "restaurant_id", "status"),
        Index("ix_complaint_restaurant_date", "restaurant_id", "business_date"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("customer.id"))
    order_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    order_line_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    feedback_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    # What a person says out loud. "Complaint 47" is quotable on a phone call and a UUID is not,
    # which is why `order.order_number` and `employee_code` exist beside their ids too.
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reported_by: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default=ComplaintStatus.OPEN)
    resolution: Mapped[str | None] = mapped_column(Text)
    compensation_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    # The Indian financial year the reference belongs to, in the "2026-27" form
    # `app/core/business_day.py` produces for invoice numbering. Stored rather than derived so the
    # uniqueness is a constraint the database enforces, not a rule a service remembers.
    financial_year: Mapped[str] = mapped_column(Text, nullable=False)
