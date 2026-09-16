"""m10 - an issue number for every error the customer module can raise

Five codes, 1192 to 1196. Backlog-issues B12 and owner decisions D11 and D12: a code such as
`customer.already_erased` never appears on a screen. A person reads the error's own sentence and
"Issue 1195", which is a number they can read out on the phone.

Two of the five are worth reading rather than skimming, because they are the sentences somebody
meets while holding a real conversation with a customer:

**`customer.phone_taken`** does not say "duplicate". It says what to do — open the existing profile
— because the person hitting it is at a counter with a diner in front of them, and "already exists"
without a next step is how a second row for the same person gets made anyway with a digit changed.

**`customer.erased`** has to explain a refusal that is *correct* and looks like a bug. Somebody is
trying to record a preference for a person whose details were erased at their own request, and the
sentence has to make that land as a decision the customer made rather than a system failure.

M09's lesson 3, followed this time: the codes and their numbers land in the same commit as the code
that raises them, rather than being found by `test_every_raised_code_has_an_issue` at the gate
thirty-two minutes into a run.

A separate migration from 0036 and 0037, for the reason `tests/test_issue_catalogue.py` documents: a
database that has already run 0029 never re-reads `issues.json`, so an edit without a migration is a
sentence that exists locally and never reaches staging.

Revision ID: 0038_m10_customer_issues
Revises: 0037_m10_permissions
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0038_m10_customer_issues"
down_revision: str | None = "0037_m10_permissions"
branch_labels: str | None = None
depends_on: str | None = None

ISSUES_FINGERPRINT = "sha256:af7848cf73f7e7b783239593127865126ddb702918db938bb377b750301e2728"

_CATALOGUE_PATH = (
    Path(__file__).resolve().parents[1] / "catalogues" / "0038_m10_customer_issues.json"
)

# The codes this migration is for, so `downgrade` removes exactly what `upgrade` added rather than
# whatever the snapshot happens to contain.
_ADDED = (
    "customer.not_found",
    "customer.phone_taken",
    "customer.erased",
    "customer.already_erased",
    "customer.preference_not_found",
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
