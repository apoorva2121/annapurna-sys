"""m11 - an issue number for every error a conversation, a task or an attachment can raise

Forty-two codes, 1208 to 1249 — forty of this module's, and two the gate found. Backlog-issues B12 and owner decisions D11 and D12: a code such as
`task.cannot_verify_own_work` never appears on a screen. A person reads the error's own sentence
and "Issue 1234", which is a number they can read out on the phone.

Three of the sentences were written more carefully than the rest, and for the same reason M09's
approval message was:

**"Somebody else has to check work you finished yourself."** A refusal a manager meets at the end
of a long shift must read as a rule that applies to everybody, not as a suspicion about them.

**"That file is not the kind of file it claims to be, so it was discarded."** The person who
attached it is almost never the person who made it what it is, so the sentence says what happened
to the file rather than what they did.

**"A conversation between two people cannot take a third. Start a group."** Every refusal in this
module names the thing to do instead, because a communication tool that says no without saying
what next is one people route around.

A separate migration from 0041 and 0042, for the reason `tests/test_issue_catalogue.py` documents:
a database that has already run 0029 never re-reads `issues.json`, so an edit without a migration
is a sentence that exists locally and never reaches staging.

Revision ID: 0043_m11_issues
Revises: 0042_m11_permissions
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0043_m11_issues"
down_revision: str | None = "0042_m11_permissions"
branch_labels: str | None = None
depends_on: str | None = None

ISSUES_FINGERPRINT = "sha256:ed1cc7b990a0871b46edebdc90fe9982b7156476e64439fe8ce61a1a9b19f814"

_CATALOGUE_PATH = Path(__file__).resolve().parents[1] / "catalogues" / "0043_m11_issues.json"

# The codes this migration is for, so `downgrade` removes exactly what `upgrade` added rather than
# whatever the snapshot happens to contain.
_ADDED = (
    "attachment.type_not_allowed",
    "attachment.too_large",
    "attachment.not_uploaded",
    "attachment.size_mismatch",
    "attachment.content_mismatch",
    "attachment.already_confirmed",
    "attachment.not_yours",
    "attachment.not_found",
    "attachment.owner_not_found",
    "attachment.not_your_message",
    "attachment.not_your_task",
    "attachment.not_your_wastage",
    "attachment.not_permitted",
    "attachment.not_in_conversation",
    "conversation.type_not_creatable",
    "conversation.direct_needs_one_person",
    "conversation.direct_has_no_title",
    "conversation.not_yours",
    "conversation.direct_is_closed",
    "conversation.direct_cannot_be_left",
    "conversation.cannot_remove",
    "conversation.not_a_participant",
    "conversation.person_not_found",
    "conversation.not_found",
    "message.empty",
    "message.not_found",
    "message.not_yours",
    "message.reply_not_found",
    "message.not_in_conversation",
    "task.not_found",
    "task.not_yours",
    "task.not_permitted",
    "task.transition_not_allowed",
    "task.cannot_verify_own_work",
    "task.cannot_cancel",
    "task.finished",
    "task.person_not_found",
    "task.complaint_not_found",
    "task.assignee_unchanged",
    "task.title_required",
    # Not M11 codes, and they belong here anyway. Both arrived with the staging-seed work on the
    # m10 branch without an issue number, and `tests/test_issue_catalogue.py` found them at this
    # module's gate — which is exactly what that test is for.
    "seed.no_password",
    "seed.committed_password",
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
