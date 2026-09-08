"""baseline - no tables yet

M00 creates no tables. This revision exists so alembic_version is stamped from day one, which is
what lets /ready answer "migrations at head" truthfully before any feature module runs.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
