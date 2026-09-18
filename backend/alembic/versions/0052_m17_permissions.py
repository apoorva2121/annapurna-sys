"""m17 - five performance permissions, and the one that goes to everybody

All five are the P1 design's (`seed/organization.yaml`). Four are ordinary grants. The first is not.

**`performance.view.own` is granted to every role, and the design says "EVERY role. Always."**
ADR 0011's third decision explains why in a sentence worth reading before touching this file:

> *"A score an employee cannot see is surveillance and lowers morale; the same score, visible with
> its inputs shown, is feedback and raises it. This is the decision that determines which of the two
> this feature becomes, so it is a structural guarantee rather than a setting."*

So it is granted to the cleaner, the kitchen hand and the waiter as well as the owner, and
`tests/test_m17_scoring.py` asserts no role is missing it. A future migration that revokes it from
somebody is a migration that changes what this feature *is*, and should be argued for on those
terms.

**The resource carries the dot, and the code does not change.** `performance.view.own` composes
from `resource: performance, action: view_own` as `performance.view_own` — not the code the P1
design names. The shipped catalogue validates that a code equals `resource.action`, so it ships as
`performance.view` + `own`, the way `employee.role.assign` already does and the way M13 shipped
`report.operational.view`. The **code** is the design's, unchanged, which is what
`test_the_shipped_catalogue_is_a_subset_of_the_p1_design` compares.

The other four follow the design: `performance.view.team` to the owner, the manager and the chef;
`performance.publish` and `incentive.configure` to the owner alone, because they decide what the
restaurant pays people to do; `recognition.award` to the owner and the manager, because a manager is
who notices.

Revision ID: 0052_m17_permissions
Revises: 0051_m17_performance
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0052_m17_permissions"
down_revision: str | None = "0051_m17_performance"
branch_labels: str | None = None
depends_on: str | None = None

# Recomputed and compared by tests/test_permission_seed.py.
CATALOGUE_FINGERPRINT = "sha256:9dcda0208d675f10ea737e2db51284ea12a316820f6af9aa0295df8908d93577"

_OWN = (
    "See your own performance figures and everything they are computed from. **Held by every role, "
    "and it is not removable by configuration** (ADR 0011): a score an employee cannot see is "
    "surveillance and lowers morale; the same score, visible with its inputs, is feedback and "
    "raises it. Which of those two this feature becomes is decided by this line."
)
_TEAM = (
    "See the team's performance figures. Top contributors are visible to everyone who holds it; a "
    "bottom ranking is not returned by any endpoint in this product, and below five scored people "
    "the team view shows nobody but the viewer - with three waiters, naming the top two names the "
    "third."
)
_PUBLISH = (
    "Freeze a period. Publishing writes the computed figures into `performance_score` and they are "
    "never recomputed, because a later void must not rewrite the basis on which a bonus was paid. "
    "The owner's, because it is the act that turns a measurement into a payment."
)
_CONFIGURE = (
    "Set the weights a score is computed from. The owner's alone: it decides what the restaurant "
    "pays people to do, and a volume weight above the combined accuracy and rating weights is "
    "refused on save because it would pay people to rush."
)
_AWARD = (
    "Grant an award - cash, leave, a preferred shift, a meal, or simple recognition - with a "
    "citation saying what it is for. **Granted by a person, never by a score** (ADR 0011): data "
    "informs the decision and never makes it."
)

_PERMISSIONS = (
    {
        "code": "performance.view.own",
        "resource": "performance.view",
        "action": "own",
        "description": _OWN,
    },
    {
        "code": "performance.view.team",
        "resource": "performance.view",
        "action": "team",
        "description": _TEAM,
    },
    {
        "code": "performance.publish",
        "resource": "performance",
        "action": "publish",
        "description": _PUBLISH,
    },
    {
        "code": "incentive.configure",
        "resource": "incentive",
        "action": "configure",
        "description": _CONFIGURE,
    },
    {
        "code": "recognition.award",
        "resource": "recognition",
        "action": "award",
        "description": _AWARD,
    },
)

# `performance.view.own` is deliberately absent from this map: it goes to *every* system role, which
# the loop below does by asking the database for them rather than by listing them here. A list
# would be a place to forget somebody, and forgetting somebody is the failure mode.
_GRANTS = {
    "performance.view.team": ("owner", "manager", "chef"),
    "performance.publish": ("owner",),
    "incentive.configure": ("owner",),
    "recognition.award": ("owner", "manager"),
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

    # Every system role, asked for rather than listed.
    connection.execute(
        sa.text(
            """
            INSERT INTO role_permission (role_id, permission_id)
            SELECT role.id, permission.id
              FROM role, permission
             WHERE role.organization_id IS NULL
               AND permission.code = 'performance.view.own'
            ON CONFLICT DO NOTHING
            """
        )
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
