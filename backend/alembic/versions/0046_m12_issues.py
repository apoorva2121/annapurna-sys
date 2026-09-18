"""m12 - an issue number for every refusal the roster and the clock can raise

Seventeen codes, 1250 to 1266. Backlog-issues B12 and owner decisions D11 and D12: a code
such as `shift.already_clocked_in` never appears on a screen. A person reads the error's own
sentence and its number, which they can read out on the phone.

**Five of them are the clock's, and they are five rather than one on purpose.** A waiter standing
at the door at eleven in the morning with a phone in one hand will not debug a single "cannot
clock in": already in, already out, not in yet, not today's shift, not yours. Each says which of
those it is and what to do about it.

**"You can only clock in and out of your own shifts. A manager can correct a time."** The one
worth reading. It has to refuse without accusing - the overwhelmingly common cause is somebody
tapping the wrong row - while naming the legitimate path for the case where a phone really was
dead. Buddy punching is what the rule is for; a sentence that said so would insult ninety-nine
people to reach the hundredth.

A separate migration from 0044 and 0045, for the reason `tests/test_issue_catalogue.py`
documents: a database that has already run 0029 never re-reads `issues.json`.

Revision ID: 0046_m12_issues
Revises: 0045_m12_permissions
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0046_m12_issues"
down_revision: str | None = "0045_m12_permissions"
branch_labels: str | None = None
depends_on: str | None = None

ISSUES_FINGERPRINT = "sha256:56f7e97dcac7c6af931479cabebc236fac7cc43fa870aa7770648bb06d4033b6"

_CATALOGUE_PATH = Path(__file__).resolve().parents[1] / "catalogues" / "0046_m12_issues.json"

_ADDED = (
    "shift.name_taken",
    "shift.not_found",
    "shift.inactive",
    "shift.too_long",
    "shift.assignment_not_found",
    "shift.person_not_found",
    "shift.area_not_found",
    "shift.already_assigned",
    "shift.already_started",
    "shift.range_invalid",
    "shift.not_yours",
    "shift.already_clocked_in",
    "shift.already_clocked_out",
    "shift.not_clocked_in",
    "shift.not_today",
    "shift.reason_required",
    "shift.status_not_settable",
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
