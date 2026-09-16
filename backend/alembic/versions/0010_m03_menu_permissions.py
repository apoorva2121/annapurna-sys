"""m03 - menu.view, menu.manage and menu.price

Three permissions, and a change of pattern that a backlog row asked for.

**The rows are inlined, not read from `permissions.json`.** Migration 0005 reads the live catalogue
file when it *runs*, which means a database stopped at 0004 and upgraded months later applies a
catalogue from the future — and its wholesale `DELETE FROM role_permission` reconciles against it.
That was benign while the catalogue only ever grew; it stops being benign the first time a
permission is *removed* from the file, at which point replaying 0005 revokes a grant that later
revisions assume is present. `docs/backlog.md` filed it with "un-defer with M03's first permission",
and this is M03's first permission.

So this migration states exactly what it introduces and nothing else. It is readable in five years
without the file beside it, and replaying it cannot apply a decision made after it was written.
The fingerprint test (`tests/test_permission_seed.py`) still forces a migration per catalogue edit,
which is the guarantee that actually matters — and this migration is the second catalogue edit,
which is what proves that test still works now the pattern has changed.

**Three permissions, not two, and the split came from the product's own plan rather than from me.**
The M03 spec proposed a binary `menu.view` / `menu.edit` with editing held by owner and admin. Then
`seed/organization.yaml` — the P1 design, written long before this module — turned out to already
answer the question, and to answer it better:

    - menu.view, menu.manage
    # deliberately NOT granted: menu.price, report.financial.view, ...  - these are the owner's.

A manager fixing a typo in a dish name, or adding the special that starts on Friday, is an ordinary
Tuesday. A manager quietly raising a price and pocketing the difference on cash orders is the threat
the M03 spec's own table names. `menu.manage` and `menu.price` are the line between those two, and a
binary permission cannot draw it — it either hands a manager the money path or stops them doing
their job. Spec decision 2 is revised accordingly.

Revision ID: 0010_m03_menu_permissions
Revises: 0009_m03_menu
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0010_m03_menu_permissions"
down_revision: str | None = "0009_m03_menu"
branch_labels: str | None = None
depends_on: str | None = None

# The catalogue this migration was written against, as a canonical-JSON sha256 (`_` keys excluded,
# so editing the readme does not demand a migration). Recomputed and compared by
# tests/test_permission_seed.py — see that file for how to produce a new one.
CATALOGUE_FINGERPRINT = "sha256:212b60b173a37f9a453bc3683a581a53699dd5a58bc611689d23616e60a14e68"

_PERMISSIONS = (
    {
        "code": "menu.view",
        "resource": "menu",
        "action": "view",
        "description": (
            "Read the menu: categories, dishes, variants and modifiers. A waiter cannot take an "
            "order without it."
        ),
    },
    {
        "code": "menu.manage",
        "resource": "menu",
        "action": "manage",
        "description": (
            "Create and change categories, dishes, variants and modifiers — everything about the "
            "menu except what it costs."
        ),
    },
    {
        "code": "menu.price",
        "resource": "menu",
        "action": "price",
        "description": (
            "Set a variant's price and its tax group. Separate from menu.manage because it is the "
            "money path: seed/organization.yaml withholds it from a manager by name."
        ),
    },
)

# Exactly `seed/organization.yaml`'s P1 design, which is where the manager line comes from:
#
#     - menu.view, menu.manage
#     # deliberately NOT granted: menu.price, report.financial.view, ...  - these are the owner's.
#
# `owner` holds `*` in that file and is listed here because the shipped catalogue enumerates it.
# `admin` gets `menu.view` only: admin is roles, employees and configuration, not the menu.
# `chef` gets `menu.view` and nothing priced — "a chef sees grams, not rupees".
# `kitchen_staff`, `store_manager`, `cleaner` and `accountant` are absent from the menu entirely,
# which is also the design's answer rather than an omission.
_GRANTS = {
    "menu.view": ("owner", "admin", "manager", "chef", "waiter"),
    "menu.manage": ("owner", "manager"),
    "menu.price": ("owner",),
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
            # System roles only (`organization_id IS NULL`). A tenant that has defined its own role
            # decides its own grants; this migration must not reach into one.
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
    """Withdraw only what this migration introduced.

    Deleting the grants first, then the permissions: the other order leaves `role_permission` rows
    pointing at nothing, which the foreign key would refuse anyway but less legibly.
    """
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
