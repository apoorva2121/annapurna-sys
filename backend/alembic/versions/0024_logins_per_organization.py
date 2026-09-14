"""logins per organization - every login stored one way, and the sign-in choice

Backlog-issues B4 (remediation R6, owner decisions D1 and D1a).

**Every existing login is normalised once**: emails lowercased, phone numbers written as E.164 with
India's +91 when no country was given (G-18). If two logins in one organization become the same login,
the migration **stops and names them**: which person keeps the number is not a migration's call. The
same login in two organizations is fine — a login is unique per organization (D1).

**`sign_in_choice`.** When a password opens accounts in more than one organization, sign-in hands back
a single-use pass valid for two minutes and asks which organization (D1a), so the password is never
sent twice. Only the pass's hash is stored, and the accounts it may open.

The normalisation is **not reversed** on downgrade: the old spellings are not recoverable and were
never meaningful.

Revision ID: 0024_logins_per_organization
Revises: 0023_waiter_assignment
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_logins_per_organization"
down_revision: str | None = "0023_waiter_assignment"
branch_labels: str | None = None
depends_on: str | None = None

# A frozen copy of `app/core/identifiers.normalise_identifier` as it stood on 2026-09-14. A migration
# never imports application code: that function may change, and this migration must keep meaning
# what it meant when it ran.
_SEPARATORS = re.compile(r"[\s\-().]")
_INDIA = "+91"


def _normalise(raw: str) -> str:
    """Frozen copy of normalise_identifier, 2026-09-14."""
    value = raw.strip()
    if "@" in value:
        return value.lower()
    compact = _SEPARATORS.sub("", value)
    if compact.startswith("+"):
        digits = compact[1:]
        return f"+{digits}" if digits.isdigit() and 8 <= len(digits) <= 15 else value
    if not compact.isdigit():
        return value
    if compact.startswith("00") and 8 <= len(compact) - 2 <= 15:
        return f"+{compact[2:]}"
    if len(compact) == 10:
        return f"{_INDIA}{compact}"
    if len(compact) == 11 and compact.startswith("0"):
        return f"{_INDIA}{compact[1:]}"
    if len(compact) == 12 and compact.startswith("91"):
        return f"+{compact}"
    return value


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, organization_id, email, phone FROM user_account")
    ).all()
    holders: dict[tuple[object, str], list[object]] = {}
    changes = []
    for row in rows:
        email = None if row.email is None else _normalise(row.email)
        phone = None if row.phone is None else _normalise(row.phone)
        for value in (email, phone):
            if value is not None:
                holders.setdefault((row.organization_id, value), []).append(row.id)
        if (email, phone) != (row.email, row.phone):
            changes.append({"id": row.id, "email": email, "phone": phone})
    clashes = sorted(
        f"{value} ({len(ids)} logins in organization {organization})"
        for (organization, value), ids in holders.items()
        if len(ids) > 1
    )
    if clashes:
        raise RuntimeError(
            "These logins become one login once normalised. Decide which person keeps each, change "
            "the others, and run the migration again: " + "; ".join(clashes)
        )
    for change in changes:
        connection.execute(
            sa.text("UPDATE user_account SET email = :email, phone = :phone WHERE id = :id"), change
        )

    op.create_table(
        "sign_in_choice",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("account_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("token_hash", name="uq_sign_in_choice_token_hash"),
    )
    op.create_index("ix_sign_in_choice_expires", "sign_in_choice", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sign_in_choice_expires", table_name="sign_in_choice")
    op.drop_table("sign_in_choice")
