"""m14 - audit.view, and the role the P1 design withholds it from

One code, already in the P1 design (`seed/organization.yaml`), granted to the **owner**, the
**administrator** and the **accountant**.

**A manager is deliberately not given it**, and that is the design's line rather than this module's
preference. The person who runs the floor is frequently the *subject* of the record — a void, a
discount, a price change, an attendance correction — and a record its subject curates is not a
record. The same design withholds `report.financial.view` from a manager for a related reason, and
M13 shipped that.

The administrator holds it because M01's block gives an administrator configuration and people,
and reviewing who granted which role is exactly that job. The accountant holds it because a
disputed bill and a missing float are questions the books ask.

**The notification centre gets no permission at all.** What it shows is already decided by what a
person can act on — a waiter sees their own overdue tasks because a food-cost condition is not
theirs to act on, not because a check refuses them. A permission here would be a second, weaker
copy of that rule, and the two would drift.

A separate migration from the module's other work, for the reason `tests/test_permission_seed.py`
documents: a database that has already run 0002 never re-reads `permissions.json`.

Revision ID: 0050_m14_permissions
Revises: 0049_m14_notifications
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0050_m14_permissions"
down_revision: str | None = "0049_m14_notifications"
branch_labels: str | None = None
depends_on: str | None = None

# Recomputed and compared by tests/test_permission_seed.py.
CATALOGUE_FINGERPRINT = "sha256:7700dfd74ff114887cd376f7e7401ebac6cec139c12e678d8211c1d941c07325"

_DESCRIPTION = (
    "Read the audit trail: who changed a price, who voided a bill, who granted a role, and what "
    "the value was before and after. Held by the owner, the administrator and the accountant. A "
    "manager is deliberately not given it - the person who runs the floor is frequently the "
    "subject of the record, and a record its subject curates is not a record."
)

_PERMISSION = {
    "code": "audit.view",
    "resource": "audit",
    "action": "view",
    "description": _DESCRIPTION,
}

_ROLES = ("owner", "admin", "accountant")


def upgrade() -> None:
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
        sa.text("SELECT id FROM permission WHERE code = :code"), {"code": "audit.view"}
    ).scalar_one()
    for role_code in _ROLES:
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
             WHERE permission_id IN (SELECT id FROM permission WHERE code = 'audit.view')
            """
        )
    )
    connection.execute(sa.text("DELETE FROM permission WHERE code = 'audit.view'"))
