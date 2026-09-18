"""Five tables, and the reason each is the only one of its kind that had to be stored.

`docs/schema.md` eliminated `waiter_performance` and `chef_performance` with a sentence this module
inherits rather than re-argues: *"These are queries, not tables. Storing them creates a second
source of truth that silently drifts."* That reasoning still holds for **live** metrics. It stops
holding the moment a number has been used to pay somebody.

ADR 0011: *"a later correction — a voided order, a re-attributed complaint, an edited recipe — must
not silently rewrite the basis on which a bonus was already paid. An employee who screenshots their
score must find that score unchanged next month."*

So exactly four things are stored that cannot be derived — **the frozen snapshot, the manager's
note, the award that was granted, and the scheme** — and everything else stays a query.

**`performance_score` is append-only in spirit and frozen in fact.** It is written once, at
publication, and nothing in this codebase updates it. The same shape as `theoretical_food_cost` on a
settled order.

**A note can be written by the employee, not only about them.** `docs/workload-fairness.md`'s ethics
review found that visibility without recourse is the shape of surveillance rather than of feedback,
so a note carries who wrote it and whether it is a dispute — and a period refuses to publish while
a dispute on it is unanswered.
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
    Index,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    AwardType,
    PerformanceNoteKind,
    PerformancePeriodStatus,
    PerformancePeriodType,
)
from app.models.base import Base, TimestampedUUIDMixin


def _uuid() -> Any:
    return postgresql.UUID(as_uuid=True)


def _values(members: Any) -> str:
    return ", ".join(f"'{member.value}'" for member in members)


class IncentiveScheme(TimestampedUUIDMixin, Base):
    """The owner's weighting. Configuration, not results.

    **The volume rule lives in the service, not here**, and that is deliberate: it is a comparison
    between three values inside one JSON document, and a CHECK constraint expressing it would be
    unreadable in exactly the place a reader most needs to understand it. It is enforced on save
    and unit-tested, which is what ADR 0011 asks for.
    """

    __tablename__ = "incentive_scheme"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_incentive_scheme_id_restaurant"),
        CheckConstraint(
            f"period_type IN ({_values(PerformancePeriodType)})",
            name="ck_incentive_scheme_period_type",
        ),
        Index("ix_incentive_scheme_restaurant_active", "restaurant_id", "is_active"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    period_type: Mapped[str] = mapped_column(Text, nullable=False)
    # {"accuracy": 0.25, "rating": 0.20, ...}; sums to 1, and volume <= accuracy + rating.
    weights: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)


class PerformancePeriod(TimestampedUUIDMixin, Base):
    """A week or a month, and the moment its numbers stopped being able to move."""

    __tablename__ = "performance_period"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_performance_period_id_restaurant"),
        UniqueConstraint(
            "restaurant_id",
            "incentive_scheme_id",
            "period_start",
            name="uq_performance_period_start",
        ),
        CheckConstraint(
            f"status IN ({_values(PerformancePeriodStatus)})", name="ck_performance_period_status"
        ),
        CheckConstraint("period_end >= period_start", name="ck_performance_period_order"),
        # Published means frozen, and the row has to carry the evidence of when and by whom. A
        # period claiming to be published with no moment attached is a period nobody can audit.
        CheckConstraint(
            "(status = 'draft') = (published_at IS NULL AND published_by IS NULL)",
            name="ck_performance_period_publication",
        ),
        Index("ix_performance_period_restaurant_status", "restaurant_id", "status"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    incentive_scheme_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("incentive_scheme.id"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=PerformancePeriodStatus.DRAFT.value
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))


class PerformanceScore(TimestampedUUIDMixin, Base):
    """**Frozen on publish. Never recomputed.** ADR 0011.

    `metrics` holds each figure with its classification, because a score an employee cannot take
    apart is a score they cannot argue with:

        {"covers_per_hour": {"value": "5.6", "kind": "controllable", "count": 214},
         "kitchen_delay_minutes": {"value": "8.1", "kind": "context", "count": 61}}

    The `count` is there for the attribution problem `docs/workload-fairness.md` §5 names: a wrong
    attribution then shows up as a wrong *number of things*, which a person can point at, rather
    than as an unexplained score, which they cannot.
    """

    __tablename__ = "performance_score"
    __table_args__ = (
        UniqueConstraint(
            "performance_period_id", "employee_id", name="uq_performance_score_period_employee"
        ),
        CheckConstraint("hours_worked >= 0", name="ck_performance_score_hours"),
        CheckConstraint("points >= 0", name="ck_performance_score_points"),
        Index("ix_performance_score_restaurant_employee", "restaurant_id", "employee_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    performance_period_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("performance_period.id"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    # The normalisation denominator. Every metric is a rate, because a raw total measures the
    # roster rather than the person.
    hours_worked: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    points: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    # Computed at publication and **never exposed as a bottom-ranked list**: the top is shown to the
    # team, the rest only to the person and their manager. The column exists so "you were third of
    # nine" can be said to somebody about themselves.
    rank_in_period: Mapped[int | None] = mapped_column(SmallInteger)


class PerformanceNote(TimestampedUUIDMixin, Base):
    """Context that travels with the score — including the employee's own.

    *"was training the new hire"*, *"section was closed from nine"*, and, from the other side,
    *"these covers were Ramesh's tables, I was on the pass"*. A note carries who wrote it and
    whether it is a dispute, and **a period cannot be published while a dispute is unanswered**.
    """

    __tablename__ = "performance_note"
    __table_args__ = (
        CheckConstraint(
            f"kind IN ({_values(PerformanceNoteKind)})", name="ck_performance_note_kind"
        ),
        # An answered dispute names its answer. A dispute marked answered with nothing attached is
        # the failure mode the ethics review was worried about, wearing a tick.
        CheckConstraint(
            "kind <> 'dispute' OR (answered_at IS NULL) = (answered_by IS NULL)",
            name="ck_performance_note_answer_pair",
        ),
        Index("ix_performance_note_period_employee", "performance_period_id", "employee_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    performance_period_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("performance_period.id"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    author_employee_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, default=PerformanceNoteKind.CONTEXT.value
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    # A manager's note about somebody can be private; a dispute never is, because its whole purpose
    # is that the person raising it can see what happened to it.
    visible_to_employee: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_by: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    answer: Mapped[str | None] = mapped_column(Text)


class RecognitionAward(TimestampedUUIDMixin, Base):
    """Granted by a human. Never by a score.

    ADR 0011's fourth decision, and `citation` is the load-bearing column: what it is for, in words,
    shown to the employee. An award with a number and no sentence is a payment; an award with a
    sentence is recognition, and the difference is the entire point of the feature.
    """

    __tablename__ = "recognition_award"
    __table_args__ = (
        CheckConstraint(f"type IN ({_values(AwardType)})", name="ck_recognition_award_type"),
        # Cash carries an amount; recognition does not. A cash award with no amount is a promise
        # nobody can hold anybody to.
        CheckConstraint(
            "(type = 'cash') = (amount IS NOT NULL)", name="ck_recognition_award_amount"
        ),
        CheckConstraint("amount IS NULL OR amount > 0", name="ck_recognition_award_positive"),
        Index("ix_recognition_award_employee", "restaurant_id", "employee_id", "granted_at"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    # Nullable: a manager may recognise something the moment it happens, with no period behind it.
    performance_period_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid(), ForeignKey("performance_period.id")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    citation: Mapped[str] = mapped_column(Text, nullable=False)
    granted_by: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
