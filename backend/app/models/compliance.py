"""Two tables, and the reason the record is the product rather than a side effect.

M14's notification centre is derived and stores only what a person did about a condition, because a
condition that resolves should disappear. **This is the opposite case.** The export here is what an
owner hands an inspector, and it has to reconstruct *what was known when* — which today's data
cannot do, however carefully it is queried.

So a finding is a row, and `compliance_event` is append-only: `raised`, `acknowledged`, `resolved`,
`suppressed`. **Acknowledging is an event, not a status flip**, and suppression is a recorded
decision rather than a deletion. Advice ignored is still advice given.

**There is no `compliance_rule` table.** A rule is a query plus a citation, and a query does not
live in a row (`app/core/compliance.py`). A table would hold the words and leave the detection in
code, free to disagree with it.

**`raised_at` is when the product first noticed.** There is no background job (ADR 0005), so
evaluation runs when somebody opens the screen. That is stated on the export rather than implied,
because an inspection is exactly the wrong place to discover a date meant something else.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.compliance import Severity
from app.models.base import Base, TimestampedUUIDMixin


def _uuid() -> Any:
    return postgresql.UUID(as_uuid=True)


def _values(members: Any) -> str:
    return ", ".join(f"'{member.value}'" for member in members)


def _values_of(names: tuple[str, ...]) -> str:
    return ", ".join(f"'{name}'" for name in names)


_STATES = ("open", "acknowledged", "suppressed", "resolved")
_EVENTS = ("raised", "acknowledged", "suppressed", "resolved", "reopened")


class ComplianceFinding(TimestampedUUIDMixin, Base):
    """One thing that is wrong at one restaurant, and what has happened to it since.

    **One open finding per rule per restaurant.** A licence does not expire twice; re-raising the
    same rule while it is still open would turn the list into a log and the card into noise.
    """

    __tablename__ = "compliance_finding"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_compliance_finding_id_restaurant"),
        CheckConstraint(f"state IN ({_values_of(_STATES)})", name="ck_compliance_finding_state"),
        CheckConstraint(
            f"severity IN ({_values(Severity)})", name="ck_compliance_finding_severity"
        ),
        # Resolved means the condition stopped being true, and the row says when.
        CheckConstraint(
            "(state = 'resolved') = (resolved_at IS NOT NULL)",
            name="ck_compliance_finding_resolution",
        ),
        Index("ix_compliance_finding_open", "restaurant_id", "state"),
        # One *live* finding per rule per restaurant. A licence does not expire twice, and
        # re-raising while the first is still open would turn the list into a log. Resolved rows
        # are excluded because the same rule may legitimately fire again next year.
        Index(
            "uq_compliance_finding_live",
            "restaurant_id",
            "rule_code",
            unique=True,
            postgresql_where=text("state <> 'resolved'"),
        ),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    # The rule's code, from `app/core/compliance.py`. Not a foreign key, because the catalogue is
    # code: a finding raised by a rule that is later withdrawn keeps its code and its words, which
    # is what an inspection asks about.
    rule_code: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    # The three sentences, frozen as they were when the finding was raised. The catalogue's wording
    # may improve; what an owner was told must not change underneath them.
    title: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    # The facts that raised it, so somebody can check the product's working rather than trust it.
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ComplianceEvent(TimestampedUUIDMixin, Base):
    """Append-only. What happened to a finding, and who did it.

    Nothing updates or deletes one of these, which is what makes the export a record rather than a
    screenshot of the present.
    """

    __tablename__ = "compliance_event"
    __table_args__ = (
        CheckConstraint(f"type IN ({_values_of(_EVENTS)})", name="ck_compliance_event_type"),
        # Suppressing is the one act that requires a reason: an owner may dismiss a finding, and
        # what they say is the record of the decision.
        CheckConstraint(
            "type <> 'suppressed' OR reason IS NOT NULL", name="ck_compliance_event_reason"
        ),
        Index("ix_compliance_event_finding", "compliance_finding_id", "occurred_at"),
        # The composite tenant key: an event cannot name another restaurant's finding even
        # through a bug in a repository.
        ForeignKeyConstraint(
            ["compliance_finding_id", "restaurant_id"],
            ["compliance_finding.id", "compliance_finding.restaurant_id"],
        ),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    compliance_finding_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    # Nullable: the product raises and resolves findings, and no person did that.
    actor_employee_id: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
