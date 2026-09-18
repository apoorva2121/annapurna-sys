"""m11 - message.send, task.view, task.assign, task.complete

**Not one of these four codes is new.** `seed/organization.yaml`'s P1 design already carried them,
already granted three of them to every role including `cleaner`, and already drew the line between
writing down your own work and giving work to somebody else. Reading the design before writing this
migration removed three invented codes - `conversation.view`, `attachment.manage`, `task.manage` -
and one whole feature from M11, which is the fourth module in a row where the design turned out to
be ahead of the spec.

**`message.send` on every role is the design being right rather than generous.** A communication
module a cleaner cannot use is a communication module the restaurant will not adopt: the person who
finds the broken freezer at 6am is exactly the person who holds no other permission. `cleaner` had
zero permissions before this migration and has three after it, all three of them here.

**There is no `conversation.view`, and that is the point.** The control that matters is
participation: you read a thread because a participant row says so, and a permission catalogue
cannot express "this thread, not that one". A repository scope can, and does.

**`task.assign` stays with the owner and the manager**, as the design has it. A chef, a store
manager and a waiter hold `task.view` and `task.complete`, which is enough to write down their own
work and to finish what they were asked to do. Widening it would have been convenient and would
have made "who told you to do that" unanswerable.

A separate migration from 0041, for the reason `tests/test_permission_seed.py` documents: a
database that has already run 0002 never re-reads `permissions.json`.

Revision ID: 0042_m11_permissions
Revises: 0041_m11_communication
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0042_m11_permissions"
down_revision: str | None = "0041_m11_communication"
branch_labels: str | None = None
depends_on: str | None = None

# The catalogue this migration was written against, as a canonical-JSON sha256. Recomputed and
# compared by tests/test_permission_seed.py.
CATALOGUE_FINGERPRINT = "sha256:4cc1a040fb14105a4ebec2c96ce55fd31550dd37fe6a434bbe2a8a26546d5669"

_PERMISSIONS = (
    {
        "code": "message.send",
        "resource": "message",
        "action": "send",
        "description": "Take part in the restaurant's conversations: read the threads you are in, post to them, and attach a photograph or a document. Held by every role, cleaner included, because the person who finds the broken freezer at 6am is exactly the person with no other permissions. It does not open every thread - you see a conversation because you are a participant in it, and being added to one is somebody's decision, not a permission.",
    },
    {
        "code": "task.view",
        "resource": "task",
        "action": "view",
        "description": "See the work assigned to you, and write down work for yourself. Held by every role. Somebody without task.assign sees their own tasks and the ones they created, never the whole restaurant's board.",
    },
    {
        "code": "task.assign",
        "resource": "task",
        "action": "assign",
        "description": "Give work to somebody else, move it to a different person, change what it says, cancel it, and verify that finished work was actually done. Giving a colleague a task is a manager's act, which is why it is separate from writing one down for yourself. Verifying your own completed work is refused unless you are the owner - the person who did the work is not the person who says it was done.",
    },
    {
        "code": "task.complete",
        "resource": "task",
        "action": "complete",
        "description": "Move a task you were assigned along its lifecycle - accept it, start it, finish it. Held by every role, and the service refuses it on somebody else's task: nobody completes work on another person's behalf, because that is the one thing the record exists to prevent.",
    },
)

# Every system role in the catalogue. Written out rather than selected with a wildcard, because
# `test_every_role_can_take_part` reads this module's intent from here: a role added later must
# fail a test rather than silently lose its voice.
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
    "message.send": _EVERY_ROLE,
    "task.view": _EVERY_ROLE,
    "task.complete": _EVERY_ROLE,
    "task.assign": ("owner", "manager"),
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
