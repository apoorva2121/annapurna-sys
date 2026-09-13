"""m07 - order.view, order.create, order.modify, order.settle, order.void, order.discount, cash.manage

Six permissions taken verbatim from `seed/organization.yaml`'s P1 design, and one amendment to it.

**The grants are the design's, and the waiter's are the ones that matter.** A waiter holds
`order.settle`, because the person at the table is the person who takes the money, and does *not*
hold `order.void` or `order.discount`, which the design itself calls the classic leakage vectors.
Cancelling a paid cash bill is how the cash disappears, so it needs someone more senior, a reason,
and an invoice that keeps its number.

**`cash.manage` is an amendment, made in the design first.** The P1 design had no cash permission,
and `tests/test_permissions_catalogue.py` refuses any code the design lacks, as it has been right to
twice. So the M07 spec added `cash.manage` for owner and manager to `seed/organization.yaml`, and
this catalogue follows it. A waiter takes cash and never closes the till that cash went into.

**The accountant reads every order and changes none.** `order.view` is the whole of its order
path: reconciling the day's takings needs every bill, and no bill should be alterable by the person
reconciling it.

`admin` is granted nothing here, as in 0018: the P1 design gives an administrator configuration and
people, not commerce.

A separate migration rather than part of 0019, for the reason `tests/test_permission_seed.py`
documents: a database that already ran 0002 never re-reads `permissions.json`.

Revision ID: 0020_m07_order_permissions
Revises: 0019_m07_orders
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0020_m07_order_permissions"
down_revision: str | None = "0019_m07_orders"
branch_labels: str | None = None
depends_on: str | None = None

# The catalogue this migration was written against, as a canonical-JSON sha256. Recomputed and
# compared by tests/test_permission_seed.py.
CATALOGUE_FINGERPRINT = "sha256:d112b9fa60e54144df05ec25a8aae467e9f4dd695ed0e9ccd3b15a05381bfa49"

_PERMISSIONS = (
    {
        "code": "order.view",
        "resource": "order",
        "action": "view",
        "description": "See orders, bills, invoices and credit notes. The accountant holds this and nothing else on the order path: reconciling the day's takings means reading every bill and changing none.",
    },
    {
        "code": "order.create",
        "resource": "order",
        "action": "create",
        "description": "Open an order for a table, a takeaway or a delivery.",
    },
    {
        "code": "order.modify",
        "resource": "order",
        "action": "modify",
        "description": "Add, change and send dishes, mark them served, split a bill, add packaging or an optional service charge, and cancel an order that was never settled. The server recomputes every price and tax from the menu; the client sends only what was ordered.",
    },
    {
        "code": "order.settle",
        "resource": "order",
        "action": "settle",
        "description": "Take payment and settle a bill, which numbers the invoice, posts the stock the dishes consumed and freezes their food cost. Held by a waiter, because the person at the table is the person who takes the money.",
    },
    {
        "code": "order.void",
        "resource": "order",
        "action": "void",
        "description": "Cancel an invoice on its day of issue, or issue a credit note and refund against a settled bill. Not held by a waiter: cancelling a paid cash bill is how the cash disappears, so it needs a more senior person and a reason, and a cancelled invoice keeps its number.",
    },
    {
        "code": "order.discount",
        "resource": "order",
        "action": "discount",
        "description": "Apply a discount or a comp, always with a reason and always with this person's name on it. Not held by a waiter: the P1 design names discounts one of the classic leakage vectors.",
    },
    {
        "code": "cash.manage",
        "resource": "cash",
        "action": "manage",
        "description": "Open and close the till, count the cash, and record payouts and post-close adjustments. Added to the P1 design by the M07 spec: a waiter takes cash and never closes the till that cash went into.",
    },
)

_GRANTS = {
    "order.view": ("owner", "manager", "waiter", "accountant"),
    "order.create": ("owner", "manager", "waiter"),
    "order.modify": ("owner", "manager", "waiter"),
    # The person at the table takes the money.
    "order.settle": ("owner", "manager", "waiter"),
    # The classic leakage vectors: never a waiter.
    "order.void": ("owner", "manager"),
    "order.discount": ("owner", "manager"),
    # The M07 amendment. A waiter takes cash and never closes the till.
    "cash.manage": ("owner", "manager"),
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
