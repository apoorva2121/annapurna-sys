"""m05 - stock.view, stock.receive, stock.produce, stock.adjust and stock.count

Five permissions for the inventory ledger, taken verbatim from `seed/organization.yaml`'s P1
design rather than invented. An earlier draft of this migration coined `stock.move` and
`stock.count.approve` instead, and `tests/test_permissions_catalogue.py` refused them as
"enforced by the application but appearing nowhere in the design" — which was the right call and
is exactly the drift that test exists to catch. The design is the finer-grained of the two.

The grants carry meaning worth reading rather than being a flat "storeroom people can do storeroom
things":

- **The chef holds `stock.produce` and not `stock.receive`.** A kitchen turns ingredients into
  gravy; it does not sign for the sack at the door. Separating them means a cook cannot quietly
  book in stock that never arrived.
- **`kitchen_staff` holds `stock.view` alone.** Seeing what is on the shelf is the job; changing
  what the book says it is, is not.
- **`stock.adjust` is its own permission** because an adjustment is the one movement nobody
  observed, which makes it the one an insider would use to erase a shortfall.

Separation of duties on counts is *not* carried by a permission, deliberately. Approval is refused
when the approver is the counter, in the service and again by a CHECK constraint on `stock_count`,
so the control holds even for a path that forgets to ask — a permission split would have been
weaker, since one person holding both permissions is ordinary.

Written as its own migration rather than folded into 0015 for the reason
`tests/test_permission_seed.py` documents at length: a database that has already run 0002 never
re-reads `permissions.json`, so a catalogue change with no migration behind it reaches staging as
a silently missing grant while every local test stays green.

Revision ID: 0016_m05_inventory_permissions
Revises: 0015_m05_inventory
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0016_m05_inventory_permissions"
down_revision: str | None = "0015_m05_inventory"
branch_labels: str | None = None
depends_on: str | None = None

# The catalogue this migration was written against, as a canonical-JSON sha256. Recomputed and
# compared by tests/test_permission_seed.py.
CATALOGUE_FINGERPRINT = "sha256:cd96846231fe75adb80b27e06d50e32e3b6f56a9dac2c964cad7c36383b93deb"

_PERMISSIONS = (
    {
        "code": "stock.view",
        "resource": "stock",
        "action": "view",
        "description": (
            "See what is on hand, what is expiring, and the movements behind both. Read-only: it "
            "shows the position, it cannot change it."
        ),
    },
    {
        "code": "stock.receive",
        "resource": "stock",
        "action": "receive",
        "description": (
            "Record a delivery arriving. Held by the store manager, who takes the delivery, and "
            "by the manager and owner above them."
        ),
    },
    {
        "code": "stock.produce",
        "resource": "stock",
        "action": "produce",
        "description": (
            "Make a preparation batch, consuming its inputs. The chef holds this and not "
            "stock.receive: a kitchen turns ingredients into gravy, it does not sign for the sack."
        ),
    },
    {
        "code": "stock.adjust",
        "resource": "stock",
        "action": "adjust",
        "description": (
            "Post a correction to the ledger. The one movement nobody observed, which makes it "
            "the one an insider would use to erase a shortfall - so it always carries a reason "
            "and always writes an audit row."
        ),
    },
    {
        "code": "stock.count",
        "resource": "stock",
        "action": "count",
        "description": (
            "Open a count sheet, record what is on the shelf, and approve the result. Approval is "
            "what posts the corrections, and the service refuses an approver who is also the "
            "counter - a control carried by a CHECK constraint as well, so it holds for a path "
            "that forgets to ask."
        ),
    },
)

_GRANTS = {
    "stock.view": ("owner", "admin", "manager", "chef", "kitchen_staff", "store_manager"),
    "stock.receive": ("owner", "admin", "manager", "store_manager"),
    # The chef produces but does not receive.
    "stock.produce": ("owner", "admin", "manager", "chef", "store_manager"),
    "stock.adjust": ("owner", "admin", "manager", "store_manager"),
    "stock.count": ("owner", "admin", "manager", "store_manager"),
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
    codes = tuple(permission["code"] for permission in _PERMISSIONS)
    connection.execute(
        sa.text(
            """
            DELETE FROM role_permission
             WHERE permission_id IN (SELECT id FROM permission WHERE code = ANY(:codes))
            """
        ),
        {"codes": list(codes)},
    )
    connection.execute(
        sa.text("DELETE FROM permission WHERE code = ANY(:codes)"), {"codes": list(codes)}
    )
