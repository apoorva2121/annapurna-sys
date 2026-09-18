"""m13 - report.operational.view and report.financial.view

Both codes are the P1 design's, and **the split between them is the point**.

`report.operational.view` goes to the owner, the manager, the store manager and the accountant:
what each dish sold and earned, how long the kitchen took, what was thrown away. These are the
numbers somebody running a service can act on before the next one.

`report.financial.view` goes to the owner and the **accountant** only. A manager is deliberately
not given it, which is the design's own line: running the floor and reading the books are different
jobs. The consequence for the screens is that the money reports are not manager screens with blanks
in them - they are screens a manager does not have, and the route refuses rather than redacting. A
disabled figure invites somebody to go looking for the endpoint.

The same design gives the accountant `audit.view` and withholds it from the manager for the same
reason, which M14 acts on.

**The resource carries the dot, and the P1 design's own row does not.** `seed/organization.yaml`
lists these two as `resource: report, action: operational_view`, which composes to
`report.operational_view` — not the code the same row names. The shipped catalogue validates that a
code equals `resource.action`, so it is shipped the way `employee.role.assign` already is: the
resource is `report.operational` and the action is `view`. The **code** is the design's, unchanged,
which is what `test_the_shipped_catalogue_is_a_subset_of_the_p1_design` compares; the resource and
action are metadata that had to compose.

A separate migration from the module's other work, for the reason `tests/test_permission_seed.py`
documents: a database that has already run 0002 never re-reads `permissions.json`.

Revision ID: 0047_m13_permissions
Revises: 0046_m12_issues
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0047_m13_permissions"
down_revision: str | None = "0046_m12_issues"
branch_labels: str | None = None
depends_on: str | None = None

# Recomputed and compared by tests/test_permission_seed.py. Filled in by the wiring step, which
# edits permissions.json and this constant together — they are one change.
CATALOGUE_FINGERPRINT = "sha256:a1cf286d3a118c61941fba04171f907797028465dc659e99b870d672a0c1521a"

_OPERATIONAL = (
    "Read the operational reports: what each dish sold and earned, where it sits on the menu, how "
    "long it took the kitchen, and what was thrown away. Held by a manager and a store manager as "
    "well as the owner, because these are the numbers somebody running a service can actually act "
    "on before the next one."
)
_FINANCIAL = (
    "Read the money: revenue, covers, average bill, the payment split, and the food-cost variance "
    "that shows what was used against what the recipes say should have been. Held by the owner and "
    "the accountant. A manager is deliberately not given it - running the floor and reading the "
    "books are different jobs, and the design draws that line rather than showing a manager a "
    "screen full of blanks."
)

_PERMISSIONS = (
    {
        "code": "report.operational.view",
        "resource": "report.operational",
        "action": "view",
        "description": _OPERATIONAL,
    },
    {
        "code": "report.financial.view",
        "resource": "report.financial",
        "action": "view",
        "description": _FINANCIAL,
    },
)

_GRANTS = {
    "report.operational.view": ("owner", "manager", "store_manager", "accountant"),
    "report.financial.view": ("owner", "accountant"),
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
