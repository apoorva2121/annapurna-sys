"""m02 - a session remembers which branch it is at

`POST /auth/switch` (finding S12) moves a session to another branch of the same organization. The
access token it mints carries the new `restaurant_id`, which is enough for fifteen minutes — and then
the token expires, the browser refreshes it, and `refresh()` resolves the restaurant through
`_home_restaurant()`, which returns the person's *first* one.

So without this column the switch works and then silently undoes itself, mid-task, with no error and
nothing on screen to explain it. It would be reported as "the app keeps jumping back to the other
branch", which is not a sentence anyone can debug, and it would be reported by a manager rather than
by a test.

Nullable, because every session that predates this migration has no recorded choice and must keep
working: `refresh()` reads NULL as "wherever login would put you", which is exactly what those
sessions were already doing.

`ON DELETE SET NULL` rather than a hard reference: deleting a restaurant is not something the product
does, but if it ever happened the sessions attached to it should fall back to the home branch rather
than refuse to refresh. The service checks the assignment on every refresh regardless, so a stale
value here can only ever cost a redirect, never access.

Revision ID: 0006_session_restaurant
Revises: 0005_m02_restaurant_configure

The revision id is shorter than this file's subject deserves because alembic's `version_num` column
is `varchar(32)`, and a longer id fails at migration time with a truncation error that says nothing
about revision ids.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006_session_restaurant"
down_revision: str | None = "0005_m02_restaurant_configure"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("user_session", sa.Column("restaurant_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_user_session_restaurant",
        "user_session",
        "restaurant",
        ["restaurant_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Losing the column loses only where each session had navigated to; every session keeps working
    # and lands at its home branch on the next refresh. Nothing to preserve first.
    op.drop_constraint("fk_user_session_restaurant", "user_session", type_="foreignkey")
    op.drop_column("user_session", "restaurant_id")
