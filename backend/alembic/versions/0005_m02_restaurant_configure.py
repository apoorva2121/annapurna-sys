"""m02 - the restaurant.configure permission, and a fingerprint that makes this migration required

`restaurant.configure` is M02's permission, held by owner and admin only: a manager runs a shift,
and changing what a day means or what tax is charged is not running a shift (M02 spec decision 1).

**Why this migration exists at all.** Migration 0002 seeds the access-control catalogue by *reading*
`app/core/permissions.json` at migration time, so a fresh database always matches the file — which
is why the whole test suite went green when `restaurant.configure` was added to the file and nothing
else. A database that has already run 0002 is the case that breaks: alembic will not re-run it, the
new permission never reaches `permission`, and owner and admin silently lack it while every test
passes. That is a staging-only failure, which is the worst kind to find by deploying.

So the catalogue is reconciled again here. The reconciliation is an upsert, identical in effect to
0002's, and safe to run against a database that already has every row.

**The fingerprint below is the part that makes this repeatable.** `tests/test_permission_seed.py`
hashes the catalogue file and asserts some migration declares that exact hash. Edit the catalogue
without shipping a migration and that test fails, naming this file as the example to copy. Before
it existed, the tests asserting "the file and the database agree" could not fail for the one reason
anybody would want them to, because both sides read the same file.

Revision ID: 0005_m02_restaurant_configure
Revises: 0004_m02_restaurant_setup
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0005_m02_restaurant_configure"
down_revision: str | None = "0004_m02_restaurant_setup"
branch_labels: str | None = None
depends_on: str | None = None

# The catalogue this migration was written against, as a canonical-JSON sha256 (`_` keys excluded,
# so editing the readme does not demand a migration). Recomputed and compared by
# tests/test_permission_seed.py — see that file for how to produce a new one.
CATALOGUE_FINGERPRINT = "sha256:04dc58278470725d3cc164710696025e7a4d2b50fb0116f41203e57b0db46753"

_CATALOGUE_PATH = Path(__file__).resolve().parents[2] / "app" / "core" / "permissions.json"


def _catalogue() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    return {key: value for key, value in raw.items() if not key.startswith("_")}


def _reconcile_catalogue() -> None:
    """Bring `permission`, `role` and `role_permission` back in line with the file.

    Core SQL rather than the ORM, for the same reason 0002 does it: a migration must keep working
    when the models it was written against have moved on.
    """
    catalogue = _catalogue()
    connection = op.get_bind()

    permission_ids: dict[str, uuid.UUID] = {}
    for permission in catalogue["permissions"]:
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
        permission_ids[permission["code"]] = connection.execute(
            sa.text("SELECT id FROM permission WHERE code = :code"), {"code": permission["code"]}
        ).scalar_one()

    for role in catalogue["roles"]:
        role_id = connection.execute(
            sa.text("SELECT id FROM role WHERE code = :code AND organization_id IS NULL"),
            {"code": role["code"]},
        ).scalar_one()
        # Replaced wholesale rather than merged, so that removing a grant from the file removes it
        # here too. Revoking matters as much as granting.
        connection.execute(
            sa.text("DELETE FROM role_permission WHERE role_id = :role_id"), {"role_id": role_id}
        )
        for code in role["permissions"]:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO role_permission (role_id, permission_id)
                    VALUES (:role_id, :permission_id)
                    """
                ),
                {"role_id": role_id, "permission_id": permission_ids[code]},
            )


def upgrade() -> None:
    _reconcile_catalogue()


def downgrade() -> None:
    """Remove the permission this migration introduced, and the grants that reference it.

    Only `restaurant.configure` is withdrawn, not the whole catalogue: everything else here predates
    this migration, and a downgrade that deleted rows 0002 created would leave the database in a
    state no migration describes.
    """
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM role_permission
             WHERE permission_id IN (SELECT id FROM permission WHERE code = 'restaurant.configure')
            """
        )
    )
    connection.execute(sa.text("DELETE FROM permission WHERE code = 'restaurant.configure'"))
