"""m10 - an issue number for every error the guest surface can raise

Six codes, 1197 to 1202. Backlog-issues B12 and owner decisions D11 and D12: a code such as
`customer.already_erased` never appears on a screen. A person reads the error's own sentence and
"Issue 1195", which is a number they can read out on the phone.

**`guest.session_expired` is deliberately the answer to four different questions.** A slug that
does not exist, a slug on a deactivated table, a token that expired, a token for an order that was
voided: one code, one sentence, every time. `docs/security.md` is explicit - "no enumeration: guest
lookups return the same response whether or not the number exists" - and a guest cannot act on the
difference anyway. They scan again or ask a waiter, which is what the sentence tells them to do.

**`guest.too_many_requests` says "this connection", not "you".** The limiter counts by network
address, so the person who meets it may be the fifth guest on a restaurant's wifi rather than
whoever caused the burst. A message blaming them would be both rude and wrong.

M09's lesson 3, followed this time: the codes and their numbers land in the same commit as the code
that raises them, rather than being found by `test_every_raised_code_has_an_issue` at the gate
thirty-two minutes into a run.

A separate migration from 0036 and 0037, for the reason `tests/test_issue_catalogue.py` documents: a
database that has already run 0029 never re-reads `issues.json`, so an edit without a migration is a
sentence that exists locally and never reaches staging.

Revision ID: 0039_m10_guest_issues
Revises: 0038_m10_customer_issues
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0039_m10_guest_issues"
down_revision: str | None = "0038_m10_customer_issues"
branch_labels: str | None = None
depends_on: str | None = None

ISSUES_FINGERPRINT = "sha256:93624f48e11f84dcf5ebf3421467a8459caf0da49971f3642f9385898daf596c"

_CATALOGUE_PATH = Path(__file__).resolve().parents[1] / "catalogues" / "0039_m10_guest_issues.json"

# The codes this migration is for, so `downgrade` removes exactly what `upgrade` added rather than
# whatever the snapshot happens to contain.
_ADDED = (
    "guest.session_expired",
    "guest.too_many_requests",
    "guest.order_not_found",
    "feedback.order_not_found",
    "consent.nothing_to_withdraw",
    "consent.purpose_not_offered",
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
