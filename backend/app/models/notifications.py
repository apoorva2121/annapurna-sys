"""What a *person* did about a condition. Not the condition itself.

**There is no background job in this product**, and that decides the shape of this table. ADR 0005
puts scheduled work in a container invocation and none is deployed. A `notification` table filled
by a job that is not running is a notification centre that is silently empty — the worst failure
available, because it looks exactly like *nothing is wrong*.

So the centre is **derived**: every condition it shows is a query the product can already answer —
stock gone negative, a batch expiring, a complaint nobody has resolved, a task past its time, a
till that did not balance, a count waiting for a second person. This table stores only the part
that cannot be derived, which is what somebody *did* about one: read it, or dismissed it.

**`condition_key` is the identity, and getting it right is the whole design.** It names *this*
condition — "paneer expiring on the 21st", not "something is expiring" — so dismissing one batch
does not dismiss the next, and a condition that resolves and recurs comes back rather than staying
silently dismissed for ever. It is built by the service from the ids the condition is about.

**What this costs, written down so it is a decision rather than an accident:** a notification for a
condition that has since resolved simply disappears. For a restaurant that is the right behaviour —
nobody wants Tuesday's low-stock warning on Thursday when the delivery came on Wednesday — and it
is why this table has no `title`, no `body` and no `severity`. Those belong to the condition, are
computed with it, and a stored copy would be a second source of truth that silently drifts, which
is what `docs/schema.md` eliminated three tables for.

`docs/schema.md` §12 sketched a stored-notification table with `channels` and `dispatched_at` for
Phase 2's push and email. Those columns are **not** here: this codebase already carries a backlog
row about `customer.visit_count` and `lifetime_value` — columns nothing writes — as a defect class,
and adding two more knowingly would be repeating it. Phase 2 adds them with the code that fills
them, which is a two-column migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampedUUIDMixin


def _uuid() -> Any:
    return postgresql.UUID(as_uuid=True)


class Notification(TimestampedUUIDMixin, Base):
    """One person's state against one condition."""

    __tablename__ = "notification"
    __table_args__ = (
        # One row per person per condition. The upsert that marks something read relies on it, and
        # without it a double tap on a phone writes two rows and the count never reaches zero.
        UniqueConstraint(
            "restaurant_id",
            "recipient_employee_id",
            "condition_key",
            name="uq_notification_recipient_condition",
        ),
        # The centre's own query: what has this person not dealt with?
        Index(
            "ix_notification_unread",
            "restaurant_id",
            "recipient_employee_id",
            postgresql_where=None,
        ),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    recipient_employee_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    # "stock.negative:<stock_item_id>", "task.overdue:<task_id>", "cash.variance:<session_id>".
    # The service builds it; nothing else parses it.
    condition_key: Mapped[str] = mapped_column(Text, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Read means "I have seen it"; dismissed means "I do not want to see it again while it lasts".
    # Two different acts, and a centre that conflated them would either nag or hide.
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
