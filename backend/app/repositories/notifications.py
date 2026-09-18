"""The conditions the notification centre shows, and the state a person has against them.

**Every condition here is a query that already existed somewhere in this product.** Nothing is
computed by a job, nothing is stored, and nothing can go stale: a warning about stock disappears
the moment the delivery is recorded, because the warning *is* the query.

Six conditions, and the reason each is here rather than something else:

**Stock gone negative** — food is being used that nobody recorded receiving.
`docs/onboarding-cold-start.md` says this is week one for a real restaurant, and it is the most
useful signal this product emits.

**A batch expiring** — money about to be thrown away, with days of warning.

**A stock count waiting** — a second person has to approve it, and until they do the ledger is
still wrong in the way the count found.

**An open complaint** — a customer is waiting, and M10 gave every complaint a reference a person
can read out on the phone.

**An overdue task** — somebody agreed to do something by a time, and the time has passed.

**A till that did not balance** — the one figure in M07 that says money is missing, and without
this it is visible exactly once, on the evening it was counted.

**Each query is bounded and index-backed.** The centre is opened constantly — it is the first thing
somebody looks at — so a condition that cost a table scan would be paid for on every load.

**Nothing here decides who sees what.** That is the service's, because it is a rule about people
rather than about rows (`docs/product/vision.md` §25: *"a person sees a condition they can act
on"*).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.enums import CashSessionStatus, ComplaintStatus, StockCountStatus, TaskStatus
from app.models.communication import Task
from app.models.customers import Complaint
from app.models.inventory import StockBatch, StockCount, StockMovement
from app.models.notifications import Notification
from app.models.orders import CashSession
from app.models.stock import StockItem
from app.repositories.base import RestaurantScopedRepository, page_size

# How many of any one kind of condition the centre will show. A restaurant with four hundred
# negative items has one problem, not four hundred notifications, and the screen says so.
PER_CONDITION = 20


@dataclass(frozen=True, slots=True)
class Condition:
    """One thing that is true right now and that somebody can act on.

    `key` is its stable identity — the thing a dismissal is remembered against. It names *this*
    condition, so dismissing paneer's warning leaves the next batch's alone.
    """

    key: str
    kind: str
    severity: str
    subject: str
    detail: str
    ref_type: str
    ref_id: uuid.UUID
    occurred_at: datetime | None = None


class NotificationRepository(RestaurantScopedRepository[Notification]):
    model = Notification

    # ------------------------------------------------------------------ the state

    async def state(self, employee_id: uuid.UUID) -> dict[str, Notification]:
        """What this person has already read or dismissed, by condition key.

        One query for the whole centre rather than one per condition: the screen renders a page of
        them and an N+1 here would be paid on every load of the first screen anybody opens.
        """
        rows = await self.session.scalars(
            self.scoped().where(Notification.recipient_employee_id == employee_id)
        )
        return {row.condition_key: row for row in rows}

    async def mark(
        self, employee_id: uuid.UUID, key: str, *, read_at: datetime, dismissed: bool
    ) -> None:
        """Upsert on the unique key, because two taps on a phone are one act.

        Without `ON CONFLICT` the second tap writes a second row and the unread count never
        reaches zero — a bug that only appears on a slow connection, which is every phone in a
        restaurant basement.
        """
        values = {
            "restaurant_id": self.scope.restaurant_id,
            "recipient_employee_id": employee_id,
            "condition_key": key,
            "read_at": read_at,
            "dismissed_at": read_at if dismissed else None,
        }
        statement = insert(Notification).values(**values)
        await self.session.execute(
            statement.on_conflict_do_update(
                constraint="uq_notification_recipient_condition",
                set_={
                    "read_at": statement.excluded.read_at,
                    "dismissed_at": (
                        statement.excluded.dismissed_at if dismissed else Notification.dismissed_at
                    ),
                    "updated_at": read_at,
                },
            )
        )

    # ------------------------------------------------------------- the conditions

    async def negative_stock(self) -> Sequence[tuple[uuid.UUID, str, Decimal]]:
        """Items whose ledger sums below zero: stock used that nobody recorded receiving.

        Summed rather than read off a column, because invariant 2 says current stock is *derived*.
        """
        statement = (
            select(
                StockItem.id,
                StockItem.name,
                func.coalesce(func.sum(StockMovement.quantity_delta), 0).label("quantity"),
            )
            .join(StockMovement, StockMovement.stock_item_id == StockItem.id)
            .where(StockItem.restaurant_id == self.scope.restaurant_id)
            .group_by(StockItem.id, StockItem.name)
            .having(func.coalesce(func.sum(StockMovement.quantity_delta), 0) < 0)
            .order_by(func.coalesce(func.sum(StockMovement.quantity_delta), 0))
            .limit(PER_CONDITION)
        )
        rows = await self.session.execute(statement)
        return [(row[0], row[1], Decimal(str(row[2]))) for row in rows]

    async def expiring_batches(self, before: date) -> Sequence[tuple[uuid.UUID, str, date]]:
        statement = (
            select(StockBatch.id, StockItem.name, StockBatch.expiry_date)
            .join(StockItem, StockItem.id == StockBatch.stock_item_id)
            .where(
                StockBatch.restaurant_id == self.scope.restaurant_id,
                StockBatch.expiry_date.is_not(None),
                StockBatch.expiry_date <= before,
            )
            .order_by(StockBatch.expiry_date)
            .limit(PER_CONDITION)
        )
        return [(row[0], row[1], row[2]) for row in (await self.session.execute(statement))]

    async def counts_awaiting_approval(self) -> Sequence[tuple[uuid.UUID, date]]:
        statement = (
            select(StockCount.id, StockCount.business_date)
            .where(
                StockCount.restaurant_id == self.scope.restaurant_id,
                StockCount.status == StockCountStatus.SUBMITTED.value,
            )
            .order_by(StockCount.business_date)
            .limit(PER_CONDITION)
        )
        return [(row[0], row[1]) for row in (await self.session.execute(statement))]

    async def open_complaints(self) -> Sequence[tuple[uuid.UUID, str, str, datetime]]:
        statement = (
            select(Complaint.id, Complaint.reference, Complaint.severity, Complaint.created_at)
            .where(
                Complaint.restaurant_id == self.scope.restaurant_id,
                Complaint.status.notin_(
                    (ComplaintStatus.RESOLVED.value, ComplaintStatus.CLOSED.value)
                ),
            )
            .order_by(Complaint.created_at)
            .limit(PER_CONDITION)
        )
        return [(row[0], row[1], row[2], row[3]) for row in (await self.session.execute(statement))]

    async def overdue_tasks(
        self, now: datetime
    ) -> Sequence[tuple[uuid.UUID, str, uuid.UUID | None, datetime]]:
        statement = (
            select(Task.id, Task.title, Task.assigned_to, Task.due_at)
            .where(
                Task.restaurant_id == self.scope.restaurant_id,
                Task.due_at.is_not(None),
                Task.due_at < now,
                Task.status.notin_(
                    (
                        TaskStatus.COMPLETED.value,
                        TaskStatus.VERIFIED.value,
                        TaskStatus.CANCELLED.value,
                    )
                ),
            )
            .order_by(Task.due_at)
            .limit(PER_CONDITION)
        )
        return [(row[0], row[1], row[2], row[3]) for row in (await self.session.execute(statement))]

    async def till_variances(
        self, *, threshold: Decimal, limit: int | None = None
    ) -> Sequence[tuple[uuid.UUID, date, Decimal]]:
        """Closed tills whose count did not match what the system expected.

        Both directions: cash *found* is as much a sign of something wrong as cash missing, and a
        till that is consistently over is a till somebody is rounding into.
        """
        statement = (
            select(CashSession.id, CashSession.business_date, CashSession.variance)
            .where(
                CashSession.restaurant_id == self.scope.restaurant_id,
                CashSession.status == CashSessionStatus.CLOSED.value,
                func.abs(CashSession.variance) >= threshold,
            )
            .order_by(CashSession.business_date.desc())
            .limit(page_size(limit) if limit else PER_CONDITION)
        )
        rows = await self.session.execute(statement)
        return [(row[0], row[1], Decimal(str(row[2]))) for row in rows]
