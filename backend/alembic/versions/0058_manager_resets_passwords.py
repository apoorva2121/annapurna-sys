"""A manager may reset a password, because the login screen already said they could

The owner's report, 2026-09-19: *"all the others can ask it from manager or owner."* Half of that
was true. Reading `seed/organization.yaml`, only `owner` held `employee.password.reset` — the
`owner` role is `["*"]`, which the seeder expands into every permission. No other role had it, not
even `admin`.

**So the product told people something false.** The login screen's "Forgot password?" disclosure
reads: *"Ask your manager or the owner. They set a new one from Staff, and you choose your own the
next time you sign in."* A manager asked for a reset could not perform one. The sentence was right
about the intent and wrong about the product.

**Escalation was already closed, which is why this is a one-line grant.** An earlier version of
this finding assumed the reset endpoint had no seniority check and that granting this would open a
path from manager to owner. It does not: `EmployeeService.reset_password` calls
`may_reset_password`, which requires **strictly** more senior — *"a password is the ability to be
that person: every order, void, discount and audit row afterwards names the victim"* — with one
exception for two owners, so co-owners can help each other and an owner is not locked out of their
own restaurant with no recovery path.

A manager therefore still cannot reset an owner's or an admin's password. They can reset the staff
who actually get locked out: waiters, kitchen staff, cleaners. That case happens weekly; an owner
being locked out does not.

**`password_reset_required` is what keeps this honest.** The reset sets it, so the standing ability
of whoever performed it to sign in as that person ends the moment the account's real owner next
signs in and chooses their own (P1-6). Granting the permission does not weaken that, and
`tests/test_employee_endpoints.py` holds it.

Revision ID: 0058_manager_resets_passwords
Revises: 0057_takes_tables
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0058_manager_resets_passwords"
down_revision = "0057_takes_tables"
branch_labels = None
depends_on = None

_PERMISSION = "employee.password.reset"
_ROLE = "manager"


def upgrade() -> None:
    connection = op.get_bind()
    # System roles are global (`organization_id IS NULL`), so this is one row, not one per tenant.
    # `ON CONFLICT DO NOTHING` because `make seed` may already have granted it on a database
    # created after the YAML change.
    connection.execute(
        sa.text(
            """
            INSERT INTO role_permission (role_id, permission_id)
            SELECT role.id, permission.id
              FROM role, permission
             WHERE role.code = :role
               AND role.organization_id IS NULL
               AND permission.code = :permission
            ON CONFLICT DO NOTHING
            """
        ),
        {"role": _ROLE, "permission": _PERMISSION},
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM role_permission
             WHERE role_id IN (
                     SELECT id FROM role
                      WHERE code = :role AND organization_id IS NULL
                   )
               AND permission_id IN (SELECT id FROM permission WHERE code = :permission)
            """
        ),
        {"role": _ROLE, "permission": _PERMISSION},
    )
