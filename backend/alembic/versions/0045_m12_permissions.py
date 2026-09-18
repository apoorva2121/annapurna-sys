"""m12 - shift.view and shift.manage

Both codes are the P1 design's, and **one grant is deliberately wider than the design's**.

`seed/organization.yaml` gives `shift.view` to the manager. This migration gives it to every
system role, for the reason M11's `message.send` is universal: a roster nobody can read is a
noticeboard in a locked room, and the clock-in button is useless to the person it exists for if a
permission stands in front of it.

**The widening is safe because the permission opens the screen and the scope decides the
content.** A front-line role sees its own assignments and who is covering which section right now
- which it can establish by looking around the room - while staffing, statuses and corrections
stay behind `shift.manage`. The amendment is recorded on the line itself in
`seed/organization.yaml`, the way M07's `cash.manage` and the floor's `floor.manage` are.

**`admin` is not granted `shift.manage`**, following the design: the administrator is
configuration and people, not the running of a service.

**There is no `shift.clock`.** Clocking in declares `shift.view` and the service enforces that the
assignment is the actor's own - a permission cannot express "your row, not his", and that is the
only control that stands between this and buddy punching.

A separate migration from 0044, for the reason `tests/test_permission_seed.py` documents: a
database that has already run 0002 never re-reads `permissions.json`.

Revision ID: 0045_m12_permissions
Revises: 0044_m12_shifts
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0045_m12_permissions"
down_revision: str | None = "0044_m12_shifts"
branch_labels: str | None = None
depends_on: str | None = None

CATALOGUE_FINGERPRINT = "sha256:e5637f65f00ebd6e0f5c68fe18cf36456e629668898511e0db1d5d9bc04260c1"

_PERMISSIONS = (
    {
        "code": "shift.view",
        "resource": "shift",
        "action": "view",
        "description": "Read the roster and clock yourself in and out. Held by every role: a roster nobody can read is a noticeboard in a locked room. What it shows depends on who is asking - somebody without shift.manage sees their own shifts and who is covering which section right now, never the corrections or the whole week's statuses.",
    },
    {
        "code": "shift.manage",
        "resource": "shift",
        "action": "manage",
        "description": "Create shifts, put people on them, set somebody absent or on leave, and correct a clock time. A correction always needs a reason and always writes an audit entry, because asserting somebody else's attendance is not the same act as their clocking in and the record must not make the two look alike.",
    },
)

_EVERY_ROLE = (
    "owner",
    "admin",
    "manager",
    "chef",
    "kitchen_staff",
    "waiter",
    "store_manager",
    "cleaner",
    "accountant",
)

_GRANTS = {
    "shift.view": _EVERY_ROLE,
    "shift.manage": ("owner", "manager"),
}


def upgrade() -> None:
    connection = op.get_bind()

    for permission in _PERMISSIONS:
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
            {"id": uuid.uuid4(), **permission},
        )

    for code, roles in _GRANTS.items():
        permission_id = connection.execute(
            sa.text("SELECT id FROM permission WHERE code = :code"), {"code": code}
        ).scalar_one()
        for role_code in roles:
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
    codes = [permission["code"] for permission in _PERMISSIONS]
    connection.execute(
        sa.text(
            """
            DELETE FROM role_permission
             WHERE permission_id IN (SELECT id FROM permission WHERE code = ANY(:codes))
            """
        ),
        {"codes": codes},
    )
    connection.execute(sa.text("DELETE FROM permission WHERE code = ANY(:codes)"), {"codes": codes})
