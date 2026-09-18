"""m18 - two tables, and the one thing they are for

M14's notification centre stores only what a person *did* about a condition, and derives the
condition itself, because a condition that resolves should stop appearing. **This is the opposite
case**, and the difference is the export: what an owner hands an inspector has to reconstruct *what
was known when*, which today's data cannot do however carefully it is queried.

So a finding is a row and `compliance_event` is append-only. Three constraints carry the weight:

**1. One live finding per rule per restaurant.** A partial unique index over
`state <> 'resolved'`, not a plain one: the same rule may legitimately fire again next year, and a
full unique index would make the second expiry unrecordable.

**2. Resolved names when.** `(state = 'resolved') = (resolved_at IS NOT NULL)`. A row claiming to
be resolved with no moment attached is the kind of gap an inspection finds.

**3. Suppressing requires a reason.** An owner may dismiss a finding; what they said is the record
of the decision, and advice ignored is still advice given.

**There is no `compliance_rule` table.** A rule is a query plus a citation, and a query does not
live in a row — the catalogue is `app/core/compliance.py`, where the detection and the words cannot
drift apart. A table would hold only the words and leave the detection in code, free to disagree
with it.

Revision ID: 0053_m18_compliance
Revises: 0052_m17_permissions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0053_m18_compliance"
down_revision: str | None = "0052_m17_permissions"
branch_labels: str | None = None
depends_on: str | None = None

_STATES = ("open", "acknowledged", "suppressed", "resolved")
_SEVERITIES = ("critical", "warning", "advisory")
_EVENTS = ("raised", "acknowledged", "suppressed", "resolved", "reopened")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "compliance_finding",
        sa.Column("id", _uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        # Not a foreign key: the catalogue is code. A finding raised by a rule later withdrawn keeps
        # its code and its words, which is exactly what an inspection asks about.
        sa.Column("rule_code", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="open"),
        # The three sentences, frozen as they were when the finding was raised. The catalogue's
        # wording may improve; what an owner was told must not change underneath them.
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("risk", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_compliance_finding_id_restaurant"),
        sa.CheckConstraint(_in("state", _STATES), name="ck_compliance_finding_state"),
        sa.CheckConstraint(_in("severity", _SEVERITIES), name="ck_compliance_finding_severity"),
        sa.CheckConstraint(
            "(state = 'resolved') = (resolved_at IS NOT NULL)",
            name="ck_compliance_finding_resolution",
        ),
    )
    op.create_index("ix_compliance_finding_open", "compliance_finding", ["restaurant_id", "state"])
    op.create_index(
        "uq_compliance_finding_live",
        "compliance_finding",
        ["restaurant_id", "rule_code"],
        unique=True,
        postgresql_where=sa.text("state <> 'resolved'"),
    )

    op.create_table(
        "compliance_event",
        sa.Column("id", _uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("restaurant_id", _uuid(), nullable=False),
        sa.Column("compliance_finding_id", _uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        # Nullable: the product raises and resolves findings, and no person did that.
        sa.Column("actor_employee_id", _uuid()),
        sa.Column("reason", sa.Text()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.ForeignKeyConstraint(["actor_employee_id"], ["employee.id"]),
        sa.ForeignKeyConstraint(
            ["compliance_finding_id", "restaurant_id"],
            ["compliance_finding.id", "compliance_finding.restaurant_id"],
        ),
        sa.CheckConstraint(_in("type", _EVENTS), name="ck_compliance_event_type"),
        sa.CheckConstraint(
            "type <> 'suppressed' OR reason IS NOT NULL", name="ck_compliance_event_reason"
        ),
    )
    op.create_index(
        "ix_compliance_event_finding", "compliance_event", ["compliance_finding_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_table("compliance_event")
    op.drop_table("compliance_finding")
