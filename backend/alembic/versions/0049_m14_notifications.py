"""m14 - the notification table, and the three columns it deliberately does not have

One table, and the interesting part is what is missing from it.

**`docs/schema.md` §12 sketched a stored notification** — `severity`, `title`, `body`, `channels`,
`dispatched_at` — a row somebody writes and somebody else reads. That shape needs a writer, and
**there is no background job in this product**: ADR 0005 puts scheduled work in a container
invocation and none is deployed. A notification table filled by a job that is not running is a
notification centre that is silently empty, which is the worst failure available because it looks
exactly like *nothing is wrong*.

So the centre is derived from conditions the product can already answer, and this table holds only
what cannot be derived: what a person *did* about one. Read it, or dismissed it.

**No `title`, `body` or `severity`.** They belong to the condition, are computed with it, and a
stored copy goes stale the moment the condition moves — a "stock is low" row still saying 200 g
after the delivery arrived. `docs/schema.md` eliminated `dish_stats`, `chef_performance` and
`waiter_performance` with one sentence this inherits: *"These are queries, not tables. Storing them
creates a second source of truth that silently drifts."*

**No `channels` or `dispatched_at` either**, and that is a departure from the M14 spec, which said
to keep them so Phase 2's push and email would not need a redesign. This codebase already carries a
backlog row about `customer.visit_count` and `lifetime_value` — columns nothing writes — as a
defect class that shipped a screen reading numbers nobody maintained. Adding two more knowingly
would be repeating it for a saving of one migration. Phase 2 adds them with the code that fills
them.

**`condition_key` is the identity, and it is the whole design.** It names *this* condition —
`stock.negative:<stock_item_id>`, `task.overdue:<task_id>` — so dismissing paneer's warning does
not dismiss the next batch's, and a condition that resolves and recurs comes back rather than
staying silently dismissed for ever. The unique constraint is what the upsert relies on: without
it, two taps on a phone write two rows and the unread count never reaches zero.

Revision ID: 0049_m14_notifications
Revises: 0048_m13_report_indexes
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0049_m14_notifications"
down_revision: str | None = "0048_m13_report_indexes"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "notification",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("condition_key", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("dismissed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurant.id"]),
        sa.ForeignKeyConstraint(["recipient_employee_id"], ["employee.id"]),
        sa.UniqueConstraint(
            "restaurant_id",
            "recipient_employee_id",
            "condition_key",
            name="uq_notification_recipient_condition",
        ),
    )
    op.create_index(
        "ix_notification_unread",
        "notification",
        ["restaurant_id", "recipient_employee_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_unread", table_name="notification")
    op.drop_table("notification")
