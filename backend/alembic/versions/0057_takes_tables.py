"""Who may be recorded as a table's waiter, as a fact about the person rather than a permission

The owner's decision of 2026-09-19: *"tables should be assigned to only waiters and not manager or
owner, or admin."*

**Why this is a column and not a permission.** The obvious implementation is a new permission, and
it cannot work. The `owner` role is seeded with `permissions: ["*"]`, which the identity seeder
**expands into every permission in the catalogue** — 55 of them today, and any new one tomorrow.
So an owner holds, by construction, every permission that exists, and **nothing can be hidden from
an owner by adding a permission.** Checking the role name instead is refused by ADR 0007, which is
the rule that keeps navigation and authority out of the business of knowing what a role is called.

That leaves the honest modelling, which is also the truer one: *taking tables is a fact about a
person's job, not a grant of authority.* A manager who genuinely covers the floor on Fridays can
be marked as taking tables; an owner who never waits a table is not. It is per person rather than
per role, which is how a small restaurant actually works — and it is the owner's to set, which a
permission derived from a role would not have been.

**What it changes.** `AccessRepository.order_takers` is the single place that answers "who may
serve a table", and it filtered on the `order.create` permission — whose docstring said it
"includes a manager covering the floor". It now also requires `takes_tables`. Both checks stay:
the person must be able to take an order *and* be somebody who takes tables.

**The backfill, and why it is defensible.** Every employee currently assigned the system `waiter`
role gets `takes_tables = true`; everybody else gets `false`. That is a one-time data decision made
from the product's own system role, not a runtime check on a role name — and the whole point of
the column is that the owner can change it per person afterwards. A restaurant where the manager
really does serve tables sets that manager's flag and the product agrees with reality.

**Default `false`, not `true`.** A new employee is not creditable as a waiter until somebody says
so. The failure of a wrong default here is a manager silently appearing in waiter performance
figures (ADR 0011), which is the defect this migration exists to end.

Revision ID: 0057_takes_tables
Revises: 0056_jain_is_vegetarian
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0057_takes_tables"
down_revision = "0056_jain_is_vegetarian"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employee",
        sa.Column(
            "takes_tables",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="This person serves tables and may be credited as a table's waiter (ADR 0011).",
        ),
    )
    # The backfill. `employee_role_assignment` is per restaurant, so a person who waits tables at
    # one branch and manages another is marked as taking tables — correct: the flag says what they
    # do, and the branch they do it at is already decided by the assignment they were given.
    op.execute(
        """
        UPDATE employee
        SET takes_tables = true
        WHERE id IN (
            SELECT era.employee_id
            FROM employee_role_assignment AS era
            JOIN role ON role.id = era.role_id
            WHERE role.code = 'waiter'
        )
        """
    )


def downgrade() -> None:
    op.drop_column("employee", "takes_tables")
