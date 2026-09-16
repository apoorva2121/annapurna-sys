"""m10 - customer.view, customer.manage, feedback.view, complaint.manage

Four permissions taken verbatim from `seed/organization.yaml`'s P1 design. Like M08 and M09, this
module amends that design not at all - the third in a row, and the reason is worth keeping: the
shipped catalogue must be a *subset* of the design (`test_the_shipped_catalogue_is_a_subset_of_the_
p1_design`), so a fifth code invented here would be changing the design inside a migration.

**A waiter holds `customer.view` and `feedback.view`, and that is the design being right rather
than generous.** `docs/customer-experience.md` puts the regular's card on the waiter's screen -
"7th visit, usually orders Butter Chicken + Butter Naan, no onion/garlic, last visit rated 5" - and
calls remembering a preference "a small delight" against asking for the fourth time, which is "a
small insult". A waiter who cannot see a customer cannot greet one.

**A waiter does not hold `customer.manage` or `complaint.manage`.** Editing somebody's details and
owning a complaint are both accountable acts, and the design puts them with the manager.

**The kitchen roles hold none of the four.** A chef sees grams, not diners; the allergy that must
reach them reaches them on the ticket (spec decision 9), copied at attach time, not by reading a
customer record.

**`admin` holds none either**, following 0018, 0020, 0031 and 0034: the design's administrator is
configuration and people, not commerce and not customers.

**What this migration deliberately does not do.** DPDP erasure is irreversible and destroys data,
and it sits under `customer.manage` beside editing a name, because the design has no finer code.
Whether a manager should be able to erase a customer is a question for the owner, and it is in
`docs/backlog.md` next to the `admin` stock-permissions row rather than answered here. A migration
is the wrong place to decide who may do what in a live restaurant.

A separate migration from 0036, for the reason `tests/test_permission_seed.py` documents: a database
that has already run 0002 never re-reads `permissions.json`.

Revision ID: 0037_m10_permissions
Revises: 0036_m10_customers
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0037_m10_permissions"
down_revision: str | None = "0036_m10_customers"
branch_labels: str | None = None
depends_on: str | None = None

# The catalogue this migration was written against, as a canonical-JSON sha256. Recomputed and
# compared by tests/test_permission_seed.py.
CATALOGUE_FINGERPRINT = "sha256:e7a5d929ca518c5b88d6249e401e54d9ed557dc9cd3644609cbc041c6eecdf58"

_PERMISSIONS = (
    {
        "code": "customer.view",
        "resource": "customer",
        "action": "view",
        "description": "See a customer's profile: their number, how often they have been, what they usually order and how they like it. Held by a waiter as well as a manager, because greeting a regular by name and remembering they eat no onion is the whole point of keeping the record - asking a regular for the fourth time whether they eat onion is a small insult, and remembering is a small delight. A person sees the customers of the restaurant they are working in, not the whole organization's.",
    },
    {
        "code": "customer.manage",
        "resource": "customer",
        "action": "manage",
        "description": "Create and edit a customer, record their preferences, capture or withdraw a consent, export everything held about them, and erase them at their request. Erasure destroys every detail that names a person and keeps every order, because a bill is a financial record; it cannot be undone, and afterwards the same person returning is a new customer with no history.",
    },
    {
        "code": "feedback.view",
        "resource": "feedback",
        "action": "view",
        "description": "Read what diners said: the three questions from the QR code on the bill, per order and per day. Held by a waiter deliberately - a rating is about a table they served, and somebody who cannot see how their service landed cannot improve it. What nobody can do is submit feedback on their own tables: that needs the token printed on the guest's bill.",
    },
    {
        "code": "complaint.manage",
        "resource": "complaint",
        "action": "manage",
        "description": "Log a complaint, give it an owner, and record what was actually done about it - a comp, a remake, a refund, an apology. A complaint nobody owns is worse than no system, which is why assigning is part of the same permission as logging. Whether the customer came back afterwards is not typed by anybody: it is derived from the order ledger, because it is the only honest measure of recovery and it becomes true weeks after everyone has forgotten.",
    },
)

_GRANTS = {
    # The design's own lines, verbatim. A waiter greets; a manager owns. The owner is listed
    # explicitly rather than by a wildcard: `permissions.json` enumerates every code an owner holds
    # and `test_owner_holds_every_permission` compares the two, so a code the owner is missing is a
    # red build rather than a screen an owner cannot open.
    "customer.view": ("owner", "manager", "waiter"),
    "customer.manage": ("owner", "manager"),
    "feedback.view": ("owner", "manager", "waiter"),
    "complaint.manage": ("owner", "manager"),
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
