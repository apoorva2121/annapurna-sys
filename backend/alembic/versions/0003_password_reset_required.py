"""m01-r · a reset password must be changed before the account is the person's again

Finding P1-6, guardrail G-4. Resetting someone's password is a legitimate act — a waiter forgets
theirs at 7pm and the owner fixes it. What is not legitimate is the standing consequence: without
this flag the owner now knows a working password for that account indefinitely, and every order,
void and discount made with it is attributed to the waiter.

The flag is set by `EmployeeService.reset_password` and cleared by `AuthService.change_own_password`,
so the window in which someone else knows the password ends the first time the real owner of the
account signs in.

Revision ID: 0003_password_reset_required
Revises: 0002_m01_identity
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_password_reset_required"
down_revision: str | None = "0002_m01_identity"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "user_account",
        sa.Column(
            "password_reset_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("user_account", "password_reset_required")
