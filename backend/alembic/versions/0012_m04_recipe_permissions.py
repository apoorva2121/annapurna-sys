"""m04 - recipe.view, recipe.manage and cost.view

Inlined rather than read from `permissions.json`, following the pattern 0010 established and the
backlog row that asked for it: a migration must state what it introduces, so replaying it cannot
apply a decision made after it was written.

**The grant that matters is the one that is missing.** `seed/organization.yaml` gives the chef
`recipe.view` and `recipe.manage` and stops:

    - code: chef
        - menu.view, recipe.view, recipe.manage
      # NOT granted: any price, cost or financial permission. A chef sees grams, not rupees.

So the person who owns the recipe is deliberately not shown what it costs, and the manager — who
holds `cost.view` — cannot change the recipe that produces the number. That is a separation of
duties the P1 design drew on purpose, and it is why M04 has three permissions rather than two.

`admin` holds none of these. Admin is roles, employees and configuration; the kitchen is not admin.

Revision ID: 0012_m04_recipe_permissions
Revises: 0011_m04_stock_recipes
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0012_m04_recipe_permissions"
down_revision: str | None = "0011_m04_stock_recipes"
branch_labels: str | None = None
depends_on: str | None = None

# The catalogue this migration was written against, as a canonical-JSON sha256. Recomputed and
# compared by tests/test_permission_seed.py.
CATALOGUE_FINGERPRINT = "sha256:1792261a7a503bae7568c33735256567f1a4e70903274678d045e5df87a0de40"

_PERMISSIONS = (
    {
        "code": "recipe.view",
        "resource": "recipe",
        "action": "view",
        "description": "Read recipes and their quantities. A chef reads recipes — that is the job.",
    },
    {
        "code": "recipe.manage",
        "resource": "recipe",
        "action": "manage",
        "description": (
            "Create stock items and recipe versions. Held by the chef, who owns the recipe, and "
            "the owner."
        ),
    },
    {
        "code": "cost.view",
        "resource": "cost",
        "action": "view",
        "description": (
            "See what a dish costs and what it earns. Deliberately not the chef's: "
            "seed/organization.yaml's design says a chef sees grams, not rupees."
        ),
    },
)

_GRANTS = {
    "recipe.view": ("owner", "manager", "chef", "kitchen_staff", "store_manager"),
    "recipe.manage": ("owner", "chef"),
    "cost.view": ("owner", "manager"),
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
