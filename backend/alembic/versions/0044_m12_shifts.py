"""m12 - the roster, and the two foreign keys M07 and M09 left behind

Two tables from `docs/schema.md` §11, plus three constraints on tables that already exist.

Four things are deliberate.

**1. `cash_session.shift_id` and `wastage_event.shift_id` become real foreign keys here.** Both
were created as bare columns with a comment saying why - "No foreign key: `shift` is M12's.
Nullable so M07 does not wait on a roster." This is M12. They stay nullable, because a restaurant
may run without a roster and must still be able to log waste and open a till, and **nothing is
backfilled**: rows written before a roster existed have no shift and must keep saying so.
Backfilling a plausible shift onto historical waste would manufacture attribution nobody made,
into exactly the table whose value is that it is honest.

**2. `dining_area` gains `UNIQUE (id, restaurant_id)`.** Not decoration: it is what lets
`shift_assignment` reference a section with the composite tenant key every other child in this
schema uses, so a roster cannot put somebody in another restaurant's dining room even by way of a
bug in a repository. Additive, and it changes nothing about how the table behaves.

**3. A shift's times are `time`, not instants.** A shift is "six in the evening", which stays six
in the evening across a daylight-saving change that a stored instant would not survive. Where a
shift actually sits in real time is derived per business date by `app/core/shift_window.py`.

**4. The check constraints are the ones a status can lie about.** `present` and `late` both mean
somebody clocked in, so a row claiming either without a `clock_in_at` is refused - otherwise a
manager could set `present` on an empty row and M17 would later count hours nobody worked.

Revision ID: 0044_m12_shifts
Revises: 0043_m11_issues
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044_m12_shifts"
down_revision: str | None = "0043_m11_issues"
branch_labels: str | None = None
depends_on: str | None = None

# `docs/schema.md` §11. `present`/`late` are derived at clock-in; `absent`/`leave` are said by a
# person. Nothing in the background flips one.
_STATUSES = ("scheduled", "present", "absent", "late", "leave")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_dining_area_id_restaurant", "dining_area", ["id", "restaurant_id"]
    )

    # ------------------------------------------------------------------- shift
    op.create_table(
        "shift",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        # Local wall-clock, not instants. See the module docstring.
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_shift_id_restaurant"),
        sa.UniqueConstraint("restaurant_id", "name", name="uq_shift_restaurant_name"),
    )
    op.create_index("ix_shift_restaurant", "shift", ["restaurant_id"])

    # -------------------------------------------------------- shift_assignment
    op.create_table(
        "shift_assignment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "restaurant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("restaurant.id"),
            nullable=False,
        ),
        sa.Column("shift_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employee.id"),
            nullable=False,
        ),
        # ADR 0011: what makes an assist derivable, so nobody has to log helping a colleague.
        sa.Column("dining_area_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="scheduled"),
        sa.Column("clock_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clock_out_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint(
            "shift_id", "employee_id", "business_date", name="uq_shift_assignment_once"
        ),
        sa.ForeignKeyConstraint(
            ["shift_id", "restaurant_id"],
            ["shift.id", "shift.restaurant_id"],
            name="fk_shift_assignment_shift",
        ),
        sa.ForeignKeyConstraint(
            ["dining_area_id", "restaurant_id"],
            ["dining_area.id", "dining_area.restaurant_id"],
            name="fk_shift_assignment_area",
        ),
        sa.CheckConstraint(_in("status", _STATUSES), name="ck_shift_assignment_status"),
        sa.CheckConstraint(
            "clock_out_at IS NULL OR clock_in_at IS NOT NULL",
            name="ck_shift_assignment_out_needs_in",
        ),
        sa.CheckConstraint(
            "clock_out_at IS NULL OR clock_out_at >= clock_in_at",
            name="ck_shift_assignment_out_after_in",
        ),
        sa.CheckConstraint(
            "status NOT IN ('present', 'late') OR clock_in_at IS NOT NULL",
            name="ck_shift_assignment_attended_has_a_time",
        ),
    )
    op.create_index(
        "ix_shift_assignment_restaurant_date",
        "shift_assignment",
        ["restaurant_id", "business_date"],
    )
    op.create_index(
        "ix_shift_assignment_employee_date", "shift_assignment", ["employee_id", "business_date"]
    )

    # ------------------------------- the two columns that have been waiting
    op.create_foreign_key("fk_cash_session_shift", "cash_session", "shift", ["shift_id"], ["id"])
    op.create_foreign_key("fk_wastage_event_shift", "wastage_event", "shift", ["shift_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_wastage_event_shift", "wastage_event", type_="foreignkey")
    op.drop_constraint("fk_cash_session_shift", "cash_session", type_="foreignkey")
    op.drop_table("shift_assignment")
    op.drop_table("shift")
    op.drop_constraint("uq_dining_area_id_restaurant", "dining_area", type_="unique")
