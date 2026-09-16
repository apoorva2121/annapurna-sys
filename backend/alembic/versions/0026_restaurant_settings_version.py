"""restaurant settings version - a stale settings save is refused, not written over

Backlog-issues B6 (row "Server-owned form state is never reconciled after a save"). The settings
screen sends the theme and the table rules whole, by design, so a save from a page opened before
somebody else's change silently undid it. `settings_version` counts saves of these settings; a save
carries the version its page was read at, and a mismatch is a 409 the person sees.

Its own counter rather than `menu_version` or a row-wide version: a menu edit or busy mode switched on
from the floor must not make an open settings page look out of date.

Revision ID: 0026_restaurant_settings_version
Revises: 0025_login_throttle
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0026_restaurant_settings_version"
down_revision: str | None = "0025_login_throttle"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "restaurant",
        sa.Column("settings_version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("restaurant", "settings_version")
