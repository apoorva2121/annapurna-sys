"""m09 - wastage.log and wastage.approve

Two permissions taken verbatim from `seed/organization.yaml`'s P1 design. Like M08, this module
amends that design not at all.

**The split is a separation of duties, and it is the module's main internal control.** The people
who log most of the waste - the chef and the kitchen staff - hold `wastage.log` and **not**
`wastage.approve`. Logging theft as waste is the one thing this module cannot prevent, only make
visible and expensive, and an approver who is never the person logging is what makes the expensive
reasons - expiry, quality rejection, storage failure - cost somebody a conversation.

**A waiter holds neither**, which is the design's own line and worth stating because it is easy to
assume otherwise: waste is a kitchen and storeroom event, and a dish a customer sent back is
recorded by whoever takes it off the bill, not by whoever carried it.

**`admin` holds neither either**, following 0018, 0020 and 0031: the design's administrator is
configuration and people, not service. (Migration 0016 granted admin five stock permissions the
design does not give it, which is recorded in `docs/backlog.md` rather than changed here - revoking
a permission in a live restaurant is the owner's decision, not a tidy-up.)

A separate migration from 0033, for the reason `tests/test_permission_seed.py` documents: a
database that has already run 0002 never re-reads `permissions.json`.

Revision ID: 0034_m09_waste_permissions
Revises: 0033_m09_waste
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0034_m09_waste_permissions"
down_revision: str | None = "0033_m09_waste"
branch_labels: str | None = None
depends_on: str | None = None

# The catalogue this migration was written against, as a canonical-JSON sha256. Recomputed and
# compared by tests/test_permission_seed.py.
CATALOGUE_FINGERPRINT = "sha256:802c436a688c126149741299d1aa160f3ff210cefb8a7a000e3d8aaa9f006784"

_PERMISSIONS = (
    {
        "code": "wastage.log",
        "resource": "wastage",
        "action": "log",
        "description": "Record something thrown away: what, how much and why. The cost is computed by the server from the batches the stock actually came out of and is never asked of the person logging - a cook does not know what a kilo of paneer cost on the day it was delivered, and asking would either get a guess or stop them logging at all. Held by the chef, the kitchen staff, the manager and the store manager; a waiter does not hold it.",
    },
    {
        "code": "wastage.approve",
        "resource": "wastage",
        "action": "approve",
        "description": "Sign off waste logged against a reason the restaurant marked as needing approval - the expensive ones, such as expiry and quality rejection. It is the control standing between a reason code and somebody logging theft as waste, which is why the manager and the store manager hold it and the people who log most of the waste do not.",
    },
)

_GRANTS = {
    # Everyone who handles food or stock.
    "wastage.log": ("owner", "manager", "store_manager", "chef", "kitchen_staff"),
    # Not the people who log it. That is the point.
    "wastage.approve": ("owner", "manager", "store_manager"),
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
