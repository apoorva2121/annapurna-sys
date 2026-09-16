"""login throttle - remembered attempts instead of an automatic lock

Backlog-issues B5 (remediation R5a, guardrail G-15, owner decision D28).

Five wrong passwords used to lock an account for fifteen minutes: anyone who knew a waiter's phone
number could lock them out mid-service, from anywhere (P1-5), and "locked" was an answer only a real
login could get. **`login_attempt`** remembers attempts by a hash of the login and by network, so
sign-in can wait longer after each wrong password for one login and refuse a network that keeps
failing. `user_account.locked_until` stays, set only by a person.

Revision ID: 0025_login_throttle
Revises: 0024_logins_per_organization
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_login_throttle"
down_revision: str | None = "0024_logins_per_organization"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "login_attempt",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("identifier_hash", sa.Text(), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_login_attempt_identifier", "login_attempt", ["identifier_hash", "created_at"]
    )
    op.create_index("ix_login_attempt_ip", "login_attempt", ["ip_address", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_login_attempt_ip", table_name="login_attempt")
    op.drop_index("ix_login_attempt_identifier", table_name="login_attempt")
    op.drop_table("login_attempt")
