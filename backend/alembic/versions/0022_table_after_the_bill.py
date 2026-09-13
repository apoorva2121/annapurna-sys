"""m07 follow-up - a table's life after the bill: cleaning_since, and floor.manage

Found in the M07 manual pass on 2026-09-13 (backlog: "After a bill, a table cannot be cleared from
the floor, and tapping it opens an empty order"). Settlement sent a table to `cleaning` and nothing
ever brought it back; tapping it to clear it opened an empty order instead.

**`restaurant_table.cleaning_since`.** When a table started being cleared. The floor derives "free
after the cleaning time" from it at the moment it is read, so there is no background job to stop
running unnoticed. A CHECK keeps it honest in both directions: set exactly when the status is
`cleaning`, so a code path that changes the status and forgets the timestamp fails loudly instead of
leaving a table that is never ready, or ready for ever. Tables already being cleared are backfilled
from `updated_at`, which is when their status was last set.

**`floor.manage`.** Switching busy mode on from the floor, so a settled table is free at once instead
of being cleared first. Owner and manager only: it changes how every table behaves, and a waiter
switching it would skip cleaning for the whole room. Added to `seed/organization.yaml`'s design first,
which `tests/test_permissions_catalogue.py` requires, and seeded here with its rows written inline —
never read from the live catalogue file (backlog: "migration 0005 reads the live catalogue").

Revision ID: 0022_table_after_the_bill
Revises: 0021_m07_second_reader
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0022_table_after_the_bill"
down_revision: str | None = "0021_m07_second_reader"
branch_labels: str | None = None
depends_on: str | None = None

# The catalogue this migration was written against, as a canonical-JSON sha256. Recomputed and
# compared by tests/test_permission_seed.py.
CATALOGUE_FINGERPRINT = "sha256:c6d6665ee276a4f06d2039d7fb30d64130401ee3d7cf2ba27b408ce8e4af7d0b"

_PERMISSION = {
    "code": "floor.manage",
    "resource": "floor",
    "action": "manage",
    "description": "Switch busy mode on or off for the floor, so a settled table is free at once instead of being cleared first. It switches itself off at the next business day. Held by owner and manager: it changes how the whole floor behaves, not one table.",
}

_GRANTED_TO = ("owner", "manager")


def upgrade() -> None:
    op.add_column(
        "restaurant_table",
        sa.Column("cleaning_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE restaurant_table SET cleaning_since = updated_at WHERE status = 'cleaning'")
    op.create_check_constraint(
        "ck_restaurant_table_cleaning_since",
        "restaurant_table",
        "(status = 'cleaning') = (cleaning_since IS NOT NULL)",
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO permission (id, code, resource, action, description)
            VALUES (:id, :code, :resource, :action, :description)
            ON CONFLICT (code) DO UPDATE
                SET resource = EXCLUDED.resource,
                    action = EXCLUDED.action,
                    description = EXCLUDED.description,
                    updated_at = now()
            """
        ),
        {"id": uuid.uuid4(), **_PERMISSION},
    )
    permission_id = connection.execute(
        sa.text("SELECT id FROM permission WHERE code = :code"), {"code": _PERMISSION["code"]}
    ).scalar_one()
    for role_code in _GRANTED_TO:
        # System roles only. A tenant that defined its own role decides its own grants.
        role_id = connection.execute(
            sa.text("SELECT id FROM role WHERE code = :code AND organization_id IS NULL"),
            {"code": role_code},
        ).scalar_one()
        connection.execute(
            sa.text(
                """
                INSERT INTO role_permission (role_id, permission_id)
                VALUES (:role_id, :permission_id)
                ON CONFLICT DO NOTHING
                """
            ),
            {"role_id": role_id, "permission_id": permission_id},
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM role_permission
             WHERE permission_id IN (SELECT id FROM permission WHERE code = :code)
            """
        ),
        {"code": _PERMISSION["code"]},
    )
    connection.execute(
        sa.text("DELETE FROM permission WHERE code = :code"), {"code": _PERMISSION["code"]}
    )
    op.drop_constraint("ck_restaurant_table_cleaning_since", "restaurant_table", type_="check")
    op.drop_column("restaurant_table", "cleaning_since")
