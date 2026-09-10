"""m01 - identity, roles and permissions

Ten tables and the access-control catalogue they are useless without.

The catalogue is seeded here rather than by a script because ADR 0007 requires access control to be
version-controlled and diffable: a fresh database is correctly locked down the moment it is
migrated, with nobody having to remember a second command.

The seed reads `app/core/permissions.json` and reconciles the database to it, so it is idempotent —
running it twice changes nothing, and a later migration can call the same reconcile after the file
is edited. `tests/test_permission_seed.py` asserts the two agree, so editing the JSON without
shipping a migration fails the build rather than silently doing nothing.

Revision ID: 0002_m01_identity
Revises: 0001_baseline
Create Date: 2026-09-10
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_m01_identity"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Resolved relative to this file so the migration works from the repo, the container and CI alike.
_CATALOGUE_PATH = Path(__file__).resolve().parents[2] / "app" / "core" / "permissions.json"


def _catalogue() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    return {key: value for key, value in raw.items() if not key.startswith("_")}


def _seed_catalogue() -> None:
    """Reconcile permission, role and role_permission to the catalogue file.

    Deliberately written with core SQL rather than the ORM: a migration must keep working when the
    models it was written against have moved on, and importing app.models here would couple this
    file's correctness to code written twelve modules from now.
    """
    catalogue = _catalogue()
    connection = op.get_bind()

    permission_ids: dict[str, uuid.UUID] = {}
    for permission in catalogue["permissions"]:
        permission_id = uuid.uuid4()
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
            {"id": permission_id, **permission},
        )
        stored = connection.execute(
            sa.text("SELECT id FROM permission WHERE code = :code"), {"code": permission["code"]}
        ).scalar_one()
        permission_ids[permission["code"]] = stored

    for role in catalogue["roles"]:
        connection.execute(
            sa.text(
                """
                INSERT INTO role (id, organization_id, code, name, description, is_system)
                VALUES (:id, NULL, :code, :name, :description, true)
                ON CONFLICT (code) WHERE organization_id IS NULL DO UPDATE
                    SET name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        updated_at = now()
                """
            ),
            {
                "id": uuid.uuid4(),
                "code": role["code"],
                "name": role["name"],
                "description": role["description"],
            },
        )
        role_id = connection.execute(
            sa.text("SELECT id FROM role WHERE code = :code AND organization_id IS NULL"),
            {"code": role["code"]},
        ).scalar_one()

        # Revoking a permission is as important as granting one, so the grant list is replaced
        # wholesale rather than merged. A permission removed from the JSON is removed here.
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
    op.create_table(
        "organization",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("billing_email", sa.Text(), nullable=True),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "plan IN ('trial', 'active', 'suspended', 'cancelled')", name="ck_organization_plan"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "permission",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "restaurant",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("business_day_start", sa.Time(), server_default="05:00", nullable=False),
        sa.Column("gstin", sa.Text(), nullable=True),
        sa.Column("address", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "settings", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_restaurant_org_code"),
    )
    op.create_index(
        "ix_restaurant_organization_id", "restaurant", ["organization_id"], unique=False
    )
    op.create_table(
        "role",
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_role_org_code"),
    )
    # ON CONFLICT (organization_id, code) needs a unique index it can use as an arbiter, and a
    # NULLable column in a UNIQUE constraint does not provide one for NULL rows. System roles are
    # exactly the NULL rows, so they get their own partial unique index.
    op.create_index(
        "uq_role_system_code",
        "role",
        ["code"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )
    op.create_table(
        "user_account",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("mfa_secret", sa.Text(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('invited', 'active', 'suspended', 'locked')", name="ck_user_account_status"
        ),
        sa.CheckConstraint(
            "email IS NOT NULL OR phone IS NOT NULL", name="ck_user_account_has_an_identifier"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "email", name="uq_user_account_org_email"),
        sa.UniqueConstraint("organization_id", "phone", name="uq_user_account_org_phone"),
    )
    op.create_table(
        "employee",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_account_id", sa.UUID(), nullable=True),
        sa.Column("employee_code", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("joined_on", sa.Date(), nullable=False),
        sa.Column("employment_type", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "employment_type IN ('full_time', 'part_time', 'contract')",
            name="ck_employee_employment_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "employee_code", name="uq_employee_org_code"),
        sa.UniqueConstraint("user_account_id"),
    )
    op.create_index(
        "ix_employee_org_active", "employee", ["organization_id", "is_active"], unique=False
    )
    op.create_table(
        "role_permission",
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("permission_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permission.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )
    op.create_table(
        "user_session",
        sa.Column("user_account_id", sa.UUID(), nullable=False),
        sa.Column("refresh_token_hash", sa.Text(), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("device_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refresh_token_hash"),
    )
    op.create_index(
        "ix_user_session_account_expiry",
        "user_session",
        ["user_account_id", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_session_live",
        "user_session",
        ["user_account_id"],
        unique=False,
        postgresql_where="revoked_at IS NULL",
    )
    op.create_table(
        "audit_log",
        sa.Column("restaurant_id", sa.UUID(), nullable=True),
        sa.Column("actor_employee_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_employee_id"], ["employee.id"]),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_log_actor",
        "audit_log",
        ["restaurant_id", "actor_employee_id", "occurred_at"],
        unique=False,
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"], unique=False)
    op.create_index(
        "ix_audit_log_restaurant_time", "audit_log", ["restaurant_id", "occurred_at"], unique=False
    )
    op.create_table(
        "employee_role_assignment",
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("restaurant_id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("assigned_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["assigned_by"], ["employee.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employee.id"]),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "employee_id", "restaurant_id", "role_id", name="uq_assignment_employee_restaurant_role"
        ),
    )
    op.create_index(
        "ix_assignment_employee_restaurant",
        "employee_role_assignment",
        ["employee_id", "restaurant_id"],
        unique=False,
    )
    op.create_index(
        "ix_assignment_restaurant_role",
        "employee_role_assignment",
        ["restaurant_id", "role_id"],
        unique=False,
    )

    _seed_catalogue()


def downgrade() -> None:
    # The catalogue rows need no explicit cleanup: they live only in tables dropped below.
    op.drop_index("ix_assignment_restaurant_role", table_name="employee_role_assignment")
    op.drop_index("ix_assignment_employee_restaurant", table_name="employee_role_assignment")
    op.drop_table("employee_role_assignment")
    op.drop_index("ix_audit_log_restaurant_time", table_name="audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_index("ix_audit_log_actor", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index(
        "ix_user_session_live", table_name="user_session", postgresql_where="revoked_at IS NULL"
    )
    op.drop_index("ix_user_session_account_expiry", table_name="user_session")
    op.drop_table("user_session")
    op.drop_table("role_permission")
    op.drop_index("ix_employee_org_active", table_name="employee")
    op.drop_table("employee")
    op.drop_table("user_account")
    op.drop_index(
        "uq_role_system_code",
        table_name="role",
        postgresql_where=sa.text("organization_id IS NULL"),
    )
    op.drop_table("role")
    op.drop_index("ix_restaurant_organization_id", table_name="restaurant")
    op.drop_table("restaurant")
    op.drop_table("permission")
    op.drop_table("organization")
