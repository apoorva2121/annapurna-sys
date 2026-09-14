"""waiter assignment - the order.assign permission

Found discussing the order workflow with the owner (2026-09-14): `order.waiter_employee_id` was set to
whoever opened the order and could not be changed or seen, so a manager seating a table for a waiter,
or a cashier keying in an aggregator order, was credited as its waiter.

**No new column and no new table.** The waiter column and its index exist since M07. Every change to
it is an `audit_log` row (`order.waiter_assigned`: from, to, by whom, when, why), which is the history
a shift handover needs, and the one place M17 will read it from.

**`order.assign`.** Choosing who serves a table when opening it for someone else, and moving an order
from one waiter to another with a reason. Owner and manager. Added to `seed/organization.yaml`'s design
first, and seeded here with its rows written inline, never read from the live catalogue file.

Revision ID: 0023_waiter_assignment
Revises: 0022_table_after_the_bill
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0023_waiter_assignment"
down_revision: str | None = "0022_table_after_the_bill"
branch_labels: str | None = None
depends_on: str | None = None

# The catalogue this migration was written against, as a canonical-JSON sha256. Recomputed and
# compared by tests/test_permission_seed.py.
CATALOGUE_FINGERPRINT = "sha256:8506b6725a100a9470bf2981c024d42180b8c9a24d8105b25e7441c8452ed202"

_PERMISSION = {
    "code": "order.assign",
    "resource": "order",
    "action": "assign",
    "description": "Choose who serves a table when opening an order for someone else, and move an order from one waiter to another with a reason. Held by owner and manager: a waiter may claim an order nobody is serving, but taking a table somebody is serving would take its credit, which M17 turns into a performance score.",
}

_GRANTED_TO = ("owner", "manager")


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
