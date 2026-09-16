"""m08 - kot.view and kot.update

Two permissions taken verbatim from `seed/organization.yaml`'s P1 design. **This module amends the
design for the first time since M05: not at all.** M07 had to add `cash.manage` to it; M08 needs
nothing, because whoever wrote that file in P1 had already thought about who drives a kitchen
display.

**The waiter's grant is the line worth reading.** A waiter holds `kot.view` and does *not* hold
`kot.update`. The floor watches the kitchen and does not drive it: a waiter can see that table
six's mains are still `preparing` without being able to declare them ready, which is the difference
between information and a way to make the numbers look better.

**Neither permission can mark anything served**, and that is the module's main internal control
rather than an omission. A dish is served when it reaches a table, which the kitchen cannot see, so
`served` is written from the order path behind permissions the waiter already holds. A cook who
clears a rail of food that never left the pass therefore settles nothing and hides nothing - all
they do is widen the gap between `ready_at` and `served_at`, which is exactly the thing a manager
should be able to see.

`admin` is granted neither, as in 0018 and 0020: the P1 design gives an administrator configuration
and people, not service. `accountant` and `store_manager` likewise - a kitchen display answers no
question either of them asks.

A separate migration rather than part of 0030, for the reason `tests/test_permission_seed.py`
documents: a database that already ran 0002 never re-reads `permissions.json`.

Revision ID: 0031_m08_kitchen_permissions
Revises: 0030_m08_kitchen
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0031_m08_kitchen_permissions"
down_revision: str | None = "0030_m08_kitchen"
branch_labels: str | None = None
depends_on: str | None = None

# The catalogue this migration was written against, as a canonical-JSON sha256. Recomputed and
# compared by tests/test_permission_seed.py.
CATALOGUE_FINGERPRINT = "sha256:b90084c3fda1caefde5957e03b7ce335aaed6409aa537fa10f57dc5f32843c46"

_PERMISSIONS = (
    {
        "code": "kot.view",
        "resource": "kot",
        "action": "view",
        "description": "See the kitchen display: what each station has to cook, how long each ticket has been waiting, and which are late. A waiter holds this and not kot.update, which is the design's own line - the floor watches the kitchen and does not drive it.",
    },
    {
        "code": "kot.update",
        "resource": "kot",
        "action": "update",
        "description": "Move a ticket through the kitchen - acknowledge it, start it, mark it ready - and ask for a remake with a reason. It never marks anything served: a dish is served when it reaches a table, which the kitchen cannot see, so that is written from the order screen by whoever carried it.",
    },
)

_GRANTS = {
    # Everyone who works a pass or runs a service.
    "kot.view": ("owner", "manager", "chef", "kitchen_staff", "waiter"),
    # Everyone except the waiter. The floor watches; the kitchen drives.
    "kot.update": ("owner", "manager", "chef", "kitchen_staff"),
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
