"""m18 - two compliance permissions, and why seeing is not deciding

Both are the P1 design's (`seed/organization.yaml`), and the split between them is the point.

**`compliance.view` goes to the owner, the administrator, the manager and the accountant.** A
manager runs the floor, and the floor is where an expired licence is discovered by an inspector.
Withholding the list from the person most able to act on it would be the wrong kind of caution —
this is unlike `audit.view`, which the manager is deliberately not given because the manager is
frequently the *subject* of that record. A compliance finding is about the restaurant.

**`compliance.act` goes to the owner and the administrator only.** Acknowledging and suppressing
are decisions, and a suppression is the row an inspection reads: *"we were told, and here is what
we said about it."* Deciding that a licence warning does not matter is not a floor decision.

Nothing here decides what may block a user. That is settled in `app/core/compliance.py`, where a
rule whose status is not `in_force` cannot be constructed with `critical` severity — a permission
is about who may look, not about what the product is entitled to assert.

Revision ID: 0054_m18_permissions
Revises: 0053_m18_compliance
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0054_m18_permissions"
down_revision: str | None = "0053_m18_compliance"
branch_labels: str | None = None
depends_on: str | None = None

# Recomputed and compared by tests/test_permission_seed.py.
CATALOGUE_FINGERPRINT = "sha256:e98a63eebfe9f7deab48da8f1dd1fbaad393fe798b1b4064de7be7a1a91ca86a"

_VIEW = (
    "See what in this restaurant's configuration puts its licences at risk: an expired or "
    "malformed FSSAI number, a missing GSTIN, dishes with no allergen statement. Every finding "
    "cites the instrument it comes from and the date that citation was checked, so a person can "
    "verify the product's working rather than trust it."
)
_ACT = (
    "Acknowledge a finding, or set one aside with a reason. **Suppression is a recorded decision, "
    "not a deletion** - the finding stays in the export with the reason attached, because advice "
    "ignored is still advice given, and the export is what an owner hands an inspector. The "
    "owner's and the administrator's: deciding a licence warning does not matter is not a floor "
    "decision."
)

_PERMISSIONS = (
    {
        "code": "compliance.view",
        "resource": "compliance",
        "action": "view",
        "description": _VIEW,
    },
    {
        "code": "compliance.act",
        "resource": "compliance",
        "action": "act",
        "description": _ACT,
    },
)

_GRANTS = {
    "compliance.view": ("owner", "admin", "manager", "accountant"),
    "compliance.act": ("owner", "admin"),
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
