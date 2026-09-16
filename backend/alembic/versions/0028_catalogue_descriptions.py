"""catalogue descriptions - every permission and role reads as today's catalogue says

Backlog-issues B10. Migrations 0002 and 0005 now apply the catalogue they were written against rather
than the live file. Later catalogue migrations upsert only the permissions they introduce, so without
this one a fresh database would keep 0002's and 0005's wording for the first eight permissions and
the system roles, including 0005's double-encoded dashes. This reconciles the whole catalogue from a
frozen copy of today's file: permissions, role names, ranks and descriptions, and the grants.

Revision ID: 0028_catalogue_descriptions
Revises: 0027_menu_labelling
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0028_catalogue_descriptions"
down_revision: str | None = "0027_menu_labelling"
branch_labels: str | None = None
depends_on: str | None = None

CATALOGUE_FINGERPRINT = "sha256:8506b6725a100a9470bf2981c024d42180b8c9a24d8105b25e7441c8452ed202"

_CATALOGUE_PATH = (
    Path(__file__).resolve().parents[1] / "catalogues" / "0028_catalogue_descriptions.json"
)


def _catalogue() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    return loaded


def upgrade() -> None:
    catalogue = _catalogue()
    connection = op.get_bind()
    permission_ids: dict[str, Any] = {}
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
        connection.execute(
            sa.text(
                """
                INSERT INTO role (id, organization_id, code, name, rank, description, is_system)
                VALUES (:id, NULL, :code, :name, :rank, :description, true)
                ON CONFLICT (code) WHERE organization_id IS NULL DO UPDATE
                    SET name = EXCLUDED.name,
                        rank = EXCLUDED.rank,
                        description = EXCLUDED.description,
                        updated_at = now()
                """
            ),
            {
                "id": uuid.uuid4(),
                "code": role["code"],
                "name": role["name"],
                "rank": role["rank"],
                "description": role["description"],
            },
        )
        role_id = connection.execute(
            sa.text("SELECT id FROM role WHERE code = :code AND organization_id IS NULL"),
            {"code": role["code"]},
        ).scalar_one()
        connection.execute(
            sa.text("DELETE FROM role_permission WHERE role_id = :role_id"), {"role_id": role_id}
        )
        for code in role["permissions"]:
            connection.execute(
                sa.text(
                    "INSERT INTO role_permission (role_id, permission_id) "
                    "VALUES (:role_id, :permission_id)"
                ),
                {"role_id": role_id, "permission_id": permission_ids[code]},
            )


def downgrade() -> None:
    """Nothing to undo: the rows are the ones 0027 already had, with today's words. Putting back an
    older description would restore text nobody wants, including 0005's broken dashes."""
