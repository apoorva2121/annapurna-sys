"""m08 - an issue number for every error the kitchen can raise

Ten codes, from `kot.not_found` to `kot.unroutable`. Backlog-issues B12 and owner decisions D11 and
D12: a code such as `kot.served_is_the_floors` never appears on a screen. A person reads the
error's own sentence and "Issue 1176", which is a number they can read out on the phone.

A separate migration rather than an edit to 0029, for the reason that file states in its own
docstring and `tests/test_permission_seed.py` explains at length for the sibling catalogue: a
database that has already run 0029 never re-reads `issues.json`. Without this, the ten sentences
would exist locally, every test would pass, and a chef in a real kitchen would meet a blank where
the issue number should be.

The catalogue is copied from a **frozen snapshot** beside this file rather than read from
`app/core/issues.json`, so this migration keeps applying the catalogue it was written against even
after the eleventh code is added. That is 0029's pattern and the reason it exists.

The two messages worth reading are `kot.served_is_the_floors` and `kot.out_of_order`, because both
are refusals a person meets while holding a plate. Neither says "denied": the first names the screen
that *can* do it, and the second names the step that comes next. A chef reading an error at two
metres needs to know what to press, not that they pressed the wrong thing.

Revision ID: 0032_m08_kitchen_issues
Revises: 0031_m08_kitchen_permissions
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0032_m08_kitchen_issues"
down_revision: str | None = "0031_m08_kitchen_permissions"
branch_labels: str | None = None
depends_on: str | None = None

ISSUES_FINGERPRINT = "sha256:8589bf7df733c68a2b2693b320f5ec4aad106636d0da757195b292004d744823"

_CATALOGUE_PATH = (
    Path(__file__).resolve().parents[1] / "catalogues" / "0032_m08_kitchen_issues.json"
)

# The codes this migration is for. Named rather than derived, so `downgrade` removes exactly what
# `upgrade` added and not whatever the snapshot happens to contain.
_ADDED = (
    "kot.not_found",
    "kot.finished",
    "kot.out_of_order",
    "kot.served_is_the_floors",
    "kot.line_not_found",
    "kot.line_finished",
    "kot.line_status",
    "kot.line_out_of_order",
    "kot.remake_reason",
    "kot.unroutable",
)


def upgrade() -> None:
    catalogue: dict[str, Any] = json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    connection = op.get_bind()
    for issue in catalogue["issues"]:
        # Every row, not only the new ones: the wording of an existing issue may have been
        # improved in the same edit, and a catalogue that is half this file and half 0029's is a
        # catalogue nobody can reason about. `number` and `code` are both unique, so the conflict
        # is resolved on the number and the code is corrected with it.
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
