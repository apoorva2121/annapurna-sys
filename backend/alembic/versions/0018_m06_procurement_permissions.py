"""m06 - supplier.view, supplier.manage and purchase.manage

Three permissions for procurement, taken verbatim from `seed/organization.yaml`'s P1 design.
`tests/test_permissions_catalogue.py` refuses a code that appears nowhere in the design, and it was
right to do so twice already in this project's history, so nothing is invented here.

**The interesting line is the one that is absent.** There is no `goods_receipt.create`. Posting a
delivery writes the stock ledger, so it sits behind `stock.receive` — the permission
`seed/organization.yaml` gives to the store manager who actually takes the delivery. Keeping it
there rather than folding it into `purchase.manage` buys separation of duties from the design
itself:

- the **accountant** holds `purchase.manage` and `supplier.view`, and *not* `stock.receive`, so the
  person who reconciles supplier invoices may raise an order and may never sign for one;
- the **chef** holds none of the three, so a kitchen cannot book in a sack it then cooks;
- the **store manager** holds all of them, because running the store room *is* the job.

In a four-person restaurant one human will hold both sides, which is entirely ordinary. That is why
`purchase_order.created_by` and `goods_receipt.received_by` are both stored and both shown: the
control is visibility, not a block it would be absurd to enforce.

`admin` is deliberately granted **nothing** here. The P1 design gives an administrator system
configuration and people, not commerce — `restaurant.configure`, roles, employees, audit — and
supplier prices are commerce. (M05's migration was more generous to `admin` than the design was;
this one is not, and the divergence is worth noticing rather than copying.)

Written as its own migration rather than folded into 0017 for the reason
`tests/test_permission_seed.py` documents at length: a database that has already run 0002 never
re-reads `permissions.json`, so a catalogue change with no migration behind it reaches staging as a
silently missing grant while every local test stays green.

Revision ID: 0018_m06_procurement_permissions
Revises: 0017_m06_procurement
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0018_m06_procurement_permissions"
down_revision: str | None = "0017_m06_procurement"
branch_labels: str | None = None
depends_on: str | None = None

# The catalogue this migration was written against, as a canonical-JSON sha256. Recomputed and
# compared by tests/test_permission_seed.py.
CATALOGUE_FINGERPRINT = "sha256:11d2a662671374e2c871b50748c154ad18c1bd6cefb501b4b75626295557154e"

_PERMISSIONS = (
    {
        "code": "supplier.view",
        "resource": "supplier",
        "action": "view",
        "description": (
            "See the supplier list, purchase orders, goods receipts and the supplier variance "
            "report. Read-only, and commercially sensitive: it is who you buy from and what you "
            "pay."
        ),
    },
    {
        "code": "supplier.manage",
        "resource": "supplier",
        "action": "manage",
        "description": (
            "Add or change a supplier. Not held by the kitchen: inventing a supplier is how "
            "purchases get laundered, so create and edit are audited with the actor and a "
            "supplier is deactivated, never deleted."
        ),
    },
    {
        "code": "purchase.manage",
        "resource": "purchase",
        "action": "manage",
        "description": (
            "Raise, send and cancel purchase orders. Separate from stock.receive on purpose - "
            "posting a delivery writes the stock ledger, so it is the ledger's permission, and "
            "the accountant who reconciles invoices can raise an order without ever signing for "
            "one."
        ),
    },
)

_GRANTS = {
    "supplier.view": ("owner", "manager", "store_manager", "accountant"),
    # The accountant reconciles; they do not choose who the restaurant buys from.
    "supplier.manage": ("owner", "manager", "store_manager"),
    "purchase.manage": ("owner", "manager", "store_manager", "accountant"),
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
