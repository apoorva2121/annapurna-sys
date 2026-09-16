"""m10 - an issue number for every error complaints and feedback can raise

Five codes, 1203 to 1207. Backlog-issues B12 and owner decisions D11 and D12: a code such as
`customer.already_erased` never appears on a screen. A person reads the error's own sentence and
"Issue 1195", which is a number they can read out on the phone.

**`feedback.already_recorded` says whose feedback stands, not that something failed.** A manager
meets it when they try to write down a rating for a bill a guest already rated themselves, and the
right thing to tell them is that the guest's own answer is the one on the record. "Already exists"
would read as a system refusing a legitimate act; this reads as the system being right.

**`order.settled` says where the customer goes instead.** It is met by a waiter attaching somebody
to a bill that was settled a moment ago — CLAUDE.md invariant 6, enforced by a trigger — and without
it the database's own refusal would reach them as "Something went wrong". What they need to be told
is not that orders are immutable; it is to put the customer on the next one.

**`complaint.transition_invalid` does not explain the state machine.** A complaint that has moved on
since somebody opened the screen is a stale screen, and the useful instruction is to reload — not a
sentence naming which transitions are permitted from `closed`.

M09's lesson 3, followed this time: the codes and their numbers land in the same commit as the code
that raises them, rather than being found by `test_every_raised_code_has_an_issue` at the gate
thirty-two minutes into a run.

A separate migration from 0036 and 0037, for the reason `tests/test_issue_catalogue.py` documents: a
database that has already run 0029 never re-reads `issues.json`, so an edit without a migration is a
sentence that exists locally and never reaches staging.

Revision ID: 0040_m10_complaint_issues
Revises: 0039_m10_guest_issues
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0040_m10_complaint_issues"
down_revision: str | None = "0039_m10_guest_issues"
branch_labels: str | None = None
depends_on: str | None = None

ISSUES_FINGERPRINT = "sha256:321f24003825967f064b7bdd4dbce1c260b709c08fcd47151a20232a9990e047"

_CATALOGUE_PATH = (
    Path(__file__).resolve().parents[1] / "catalogues" / "0040_m10_complaint_issues.json"
)

# The codes this migration is for, so `downgrade` removes exactly what `upgrade` added rather than
# whatever the snapshot happens to contain.
_ADDED = (
    "complaint.not_found",
    "complaint.transition_invalid",
    "feedback.not_found",
    "feedback.already_recorded",
    "order.settled",
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
