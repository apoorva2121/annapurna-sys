"""m17, m18 - an issue number for every refusal these two modules can raise

Thirteen codes, 1267 to 1279, and they arrive in one migration because they were **missed in two**.
M17 and M18 each shipped their refusals without a catalogue entry, so a person meeting one of them
saw a sentence and no number to quote. `tests/test_issue_catalogue.py` caught it — which is the
test doing its job, a full gate later than it should have been read.

**Ten of the thirteen are M17's, and the four about a dispute are the ones worth reading.** A
refusal aimed at somebody challenging their own performance figures has a narrow path to walk: it
must say no without sounding like an accusation, because `docs/workload-fairness.md` opens by
naming what a measurement system does to morale when it is built carelessly.

> *"You can only challenge your own figures. If somebody else's look wrong, say so to them."*

Not *"you are not authorised"*. The overwhelmingly common cause is tapping the wrong row, and the
sentence points at the human thing to do instead.

> *"Somebody has challenged their figures and nobody has answered yet. Answer it first - that is
> what makes this a conversation rather than a verdict."*

The refusal that blocks a publish. It gives the reason rather than the rule, because a manager who
understands why will answer the dispute, and a manager who is only told "blocked" will look for a
way around it.

**And the weights one names all three constraints at once** rather than refusing three times:
they must sum to one, only controllable metrics may carry weight, and volume may not outweigh
accuracy and rating together. Three separate refusals would be three separate attempts.

M18's three are plainer, except the last. *"The reason stays on the record with your name against
it, and it is part of what an inspector would read"* — a person setting a licence warning aside is
entitled to know that before they type, and it is the same sentence the screen shows above the box.

A separate migration from 0051-0054, for the reason `tests/test_issue_catalogue.py` documents: a
database that has already run 0029 never re-reads `issues.json`.

Revision ID: 0055_m17_m18_issues
Revises: 0054_m18_permissions
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0055_m17_m18_issues"
down_revision: str | None = "0054_m18_permissions"
branch_labels: str | None = None
depends_on: str | None = None

ISSUES_FINGERPRINT = "sha256:68ba1c864b6c8eb66a7214e545418c01bc0dad88627d3a56e2566e9d762bad61"

_CATALOGUE_PATH = Path(__file__).resolve().parents[1] / "catalogues" / "0055_m17_m18_issues.json"

_ADDED = (
    "incentive_scheme.not_found",
    "incentive.weights_invalid",
    "performance_period.not_found",
    "performance.period_backwards",
    "performance.already_published",
    "performance.dispute_open",
    "performance_note.not_found",
    "performance.not_a_dispute",
    "performance.dispute_not_yours",
    "recognition.citation_required",
    "compliance_finding.not_found",
    "compliance_finding.already_resolved",
    "compliance.reason_required",
)


def upgrade() -> None:
    catalogue: dict[str, Any] = json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    connection = op.get_bind()
    for issue in catalogue["issues"]:
        connection.execute(
            sa.text(
                """
                INSERT INTO issue (id, number, code, text)
                VALUES (:id, :number, :code, :text)
                ON CONFLICT (number) DO UPDATE
                    SET code = EXCLUDED.code,
                        text = EXCLUDED.text,
                        updated_at = now()
                """
            ),
            {"id": uuid.uuid4(), **issue},
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM issue WHERE code = ANY(:codes)"), {"codes": list(_ADDED)}
    )
