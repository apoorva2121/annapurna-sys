"""m17 - the five tables that store what cannot be derived

`docs/schema.md` §13, and the reason it is five rather than one:

> Live metrics remain **queries** (`docs/schema.md` eliminated `waiter_performance` for good
> reason). Stored here is only what cannot be derived: a frozen snapshot, a manager's note, an
> award that was granted, and the scheme.

That elimination still holds for live metrics. It stops holding the moment a number has been used
to pay somebody — ADR 0011: *"an employee who screenshots their score must find that score
unchanged next month."*

Four constraints carry weight here, and each is a sentence from the ethics review made
un-forgettable:

**1. A published period names when and by whom.** `ck_performance_period_publication` pairs the
status with the moment. A period claiming to be published with no evidence attached is a freeze
nobody can audit, which is the same as no freeze.

**2. An answered dispute names its answer.** `ck_performance_note_answer_pair`. A dispute marked
answered with nothing attached is the failure the review was worried about, wearing a tick.

**3. A cash award carries an amount and a recognition does not.**
`ck_recognition_award_amount`. A cash award with no amount is a promise nobody can be held to.

**4. Hours and points are never negative.** The normalisation denominator is hours worked; a
negative one would invert every rate on the screen silently.

**The volume-weight rule is deliberately not a constraint.** `volume <= accuracy + rating` is a
comparison between three values inside one JSON document, and a CHECK expressing it would be
unreadable in the one place a reader most needs to understand it. It is enforced on save and
unit-tested, which is what ADR 0011 asks for.

Revision ID: 0051_m17_performance
Revises: 0050_m14_permissions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0051_m17_performance"
down_revision: str | None = "0050_m14_permissions"
branch_labels: str | None = None
depends_on: str | None = None

_PERIOD_TYPES = ("weekly", "monthly")
_PERIOD_STATUSES = ("draft", "published", "finalised")
_NOTE_KINDS = ("context", "dispute")
_AWARD_TYPES = ("cash", "leave", "shift_preference", "meal", "recognition_only")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "incentive_scheme",
        sa.Column("id", _uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("period_type", sa.Text(), nullable=False),
        sa.Column("weights", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("effective_from", sa.Date(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_incentive_scheme_id_restaurant"),
        sa.CheckConstraint(_in("period_type", _PERIOD_TYPES), name="ck_incentive_scheme_period_type"),
    )
    op.create_index(
        "ix_incentive_scheme_restaurant_active", "incentive_scheme", ["restaurant_id", "is_active"]
    )

    op.create_table(
        "performance_period",
        sa.Column("id", _uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("incentive_scheme_id", _uuid(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("published_by", _uuid()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.ForeignKeyConstraint(["published_by"], ["employee.id"]),
        # The composite tenant key every child in this schema carries: a period cannot name another
        # restaurant's scheme even through a bug in a repository.
        sa.ForeignKeyConstraint(
            ["incentive_scheme_id", "restaurant_id"],
            ["incentive_scheme.id", "incentive_scheme.restaurant_id"],
        ),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_performance_period_id_restaurant"),
        sa.UniqueConstraint(
            "restaurant_id", "incentive_scheme_id", "period_start", name="uq_performance_period_start"
        ),
        sa.CheckConstraint(_in("status", _PERIOD_STATUSES), name="ck_performance_period_status"),
        sa.CheckConstraint("period_end >= period_start", name="ck_performance_period_order"),
        sa.CheckConstraint(
            "(status = 'draft') = (published_at IS NULL AND published_by IS NULL)",
            name="ck_performance_period_publication",
        ),
    )
    op.create_index(
        "ix_performance_period_restaurant_status", "performance_period", ["restaurant_id", "status"]
    )

    op.create_table(
        "performance_score",
        sa.Column("id", _uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("performance_period_id", _uuid(), nullable=False),
        sa.Column("employee_id", _uuid(), nullable=False),
        sa.Column("hours_worked", sa.Numeric(8, 2), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("points", sa.Numeric(8, 2), nullable=False),
        sa.Column("rank_in_period", sa.SmallInteger()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.ForeignKeyConstraint(
            ["performance_period_id", "restaurant_id"],
            ["performance_period.id", "performance_period.restaurant_id"],
        ),
        sa.UniqueConstraint(
            "performance_period_id", "employee_id", name="uq_performance_score_period_employee"
        ),
        sa.CheckConstraint("hours_worked >= 0", name="ck_performance_score_hours"),
        sa.CheckConstraint("points >= 0", name="ck_performance_score_points"),
    )
    op.create_index(
        "ix_performance_score_restaurant_employee",
        "performance_score",
        ["restaurant_id", "employee_id"],
    )

    op.create_table(
        "performance_note",
        sa.Column("id", _uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("performance_period_id", _uuid(), nullable=False),
        sa.Column("employee_id", _uuid(), nullable=False),
        sa.Column("author_employee_id", _uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default="context"),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "visible_to_employee", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.Column("answered_by", _uuid()),
        sa.Column("answer", sa.Text()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.ForeignKeyConstraint(["author_employee_id"], ["employee.id"]),
        sa.ForeignKeyConstraint(["answered_by"], ["employee.id"]),
        sa.ForeignKeyConstraint(
            ["performance_period_id", "restaurant_id"],
            ["performance_period.id", "performance_period.restaurant_id"],
        ),
        sa.CheckConstraint(_in("kind", _NOTE_KINDS), name="ck_performance_note_kind"),
        sa.CheckConstraint(
            "kind <> 'dispute' OR (answered_at IS NULL) = (answered_by IS NULL)",
            name="ck_performance_note_answer_pair",
        ),
    )
    op.create_index(
        "ix_performance_note_period_employee",
        "performance_note",
        ["performance_period_id", "employee_id"],
    )

    op.create_table(
        "recognition_award",
        sa.Column("id", _uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("performance_period_id", _uuid()),
        sa.Column("employee_id", _uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2)),
        sa.Column("citation", sa.Text(), nullable=False),
        sa.Column("granted_by", _uuid(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.ForeignKeyConstraint(["granted_by"], ["employee.id"]),
        sa.ForeignKeyConstraint(
            ["performance_period_id", "restaurant_id"],
            ["performance_period.id", "performance_period.restaurant_id"],
        ),
        sa.CheckConstraint(_in("type", _AWARD_TYPES), name="ck_recognition_award_type"),
        sa.CheckConstraint("(type = 'cash') = (amount IS NOT NULL)", name="ck_recognition_award_amount"),
        sa.CheckConstraint("amount IS NULL OR amount > 0", name="ck_recognition_award_positive"),
    )
    op.create_index(
        "ix_recognition_award_employee",
        "recognition_award",
        ["restaurant_id", "employee_id", "granted_at"],
    )


def downgrade() -> None:
    op.drop_table("recognition_award")
    op.drop_table("performance_note")
    op.drop_table("performance_score")
    op.drop_table("performance_period")
    op.drop_table("incentive_scheme")
