"""m09 - an issue number for every error waste can raise

Eight codes, 1183 to 1190. Backlog-issues B12 and owner decisions D11 and D12: a code such as
`wastage.approver_is_reporter` never appears on a screen. A person reads the error's own sentence
and "Issue 1189", which is a number they can read out on the phone.

The wording worth reading is that one. A refusal a cook meets while holding a tray of spoiled food
must not read as an accusation, or they stop logging and the module becomes fiction
(`docs/waste-model.md`). So it says what has to happen and why, rather than what went wrong:
"Somebody else has to approve waste you logged yourself. That is the point of approval: a second
person looked."

A separate migration from 0033 and 0034, for the reason `tests/test_issue_catalogue.py` documents:
a database that has already run 0029 never re-reads `issues.json`, so an edit without a migration
is a sentence that exists locally and never reaches staging.

Revision ID: 0035_m09_waste_issues
Revises: 0034_m09_waste_permissions
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0035_m09_waste_issues"
down_revision: str | None = "0034_m09_waste_permissions"
branch_labels: str | None = None
depends_on: str | None = None

ISSUES_FINGERPRINT = "sha256:674eb17a7428cfc83b09609bce0ba5b8d8cec7e389d2676a40a892c974b8890f"

_CATALOGUE_PATH = Path(__file__).resolve().parents[1] / "catalogues" / "0035_m09_waste_issues.json"

# The codes this migration is for, so `downgrade` removes exactly what `upgrade` added rather than
# whatever the snapshot happens to contain.
_ADDED = (
    "wastage.not_found",
    "wastage.reason_not_found",
    "wastage.reason_inactive",
    "wastage.reason_code_taken",
    "wastage.quantity_invalid",
    "wastage.already_approved",
    "wastage.approver_is_reporter",
    "wastage.range_invalid",
)


def upgrade() -> None:
    catalogue: dict[str, Any] = json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    connection = op.get_bind()
    for issue in catalogue["issues"]:
        # Every row, not only the new ones: the wording of an existing issue may have been improved
        # in the same edit, and a catalogue that is half this file and half an earlier one is a
        # catalogue nobody can reason about.
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
