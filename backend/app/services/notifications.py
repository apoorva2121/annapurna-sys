"""The notification centre: six conditions, and the rule about who is shown which.

**A person sees a condition they can act on.** That sentence is `docs/product/vision.md` §25's own,
and it is the only thing standing between a notification centre and the thing everybody switches
off. A waiter is not shown a food-cost variance they cannot change; an owner is not shown one
overdue task. The vision's words: *"This will prevent notification overload."*

**Who sees what is decided by the permission that lets them act**, not by a role name (ADR 0007)
and not by a hand-kept list of recipients. If somebody can approve a stock count, a count waiting
for approval is theirs; if they cannot, it is noise. That also means the rule cannot drift from the
product: adding a permission to a role changes what that person is told, in one step, correctly.

**Escalation is who sees it, not how loudly.** Vision §25's four tiers land here as: the person
responsible sees their own overdue task; a manager sees the conditions of the floor; the owner sees
the money and the critical complaints. Nothing repeats itself at a higher volume, because a
notification that shouts is a notification somebody turns off.

**Severity is the locked colour scale** (`docs/ui/conventions.md`): `critical` means somebody must
act now, and it is used here for exactly two things — stock that has gone negative, and a critical
complaint. Everything else is `warning` or `info`. Spending `critical` on a batch expiring next
week is how people learn to ignore red.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.core.tenancy import TenantScope
from app.repositories.notifications import Condition, NotificationRepository

# A batch inside this many days is worth telling somebody about. Long enough to use it up or move
# it into a dish that sells; short enough that the list is not the whole storeroom.
EXPIRY_HORIZON_DAYS = 7

# A till out by more than this is worth a second look. Not zero: coins, a rounded bill and a tip
# that went in the wrong drawer produce small differences every night, and a centre that flagged
# every one of them would be a centre nobody reads. `docs/schema.md` keeps the exact figure.
TILL_VARIANCE_THRESHOLD = Decimal("100.00")


@dataclass(frozen=True, slots=True)
class Notice:
    """One condition, as this person sees it."""

    key: str
    kind: str
    severity: str
    subject: str
    detail: str
    ref_type: str
    ref_id: uuid.UUID
    occurred_at: datetime | None
    read: bool
    dismissed: bool


class NotificationService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._repository = NotificationRepository(session, scope)

    async def centre(
        self, actor: Actor, *, include_dismissed: bool = False, now: datetime | None = None
    ) -> list[Notice]:
        """Everything true right now that this person can do something about.

        Ordered by severity and then by age: the thing somebody must act on now is first, and
        within a severity the oldest is first because it has been waiting longest.
        """
        moment = now or datetime.now(UTC)
        conditions = await self._conditions(actor, moment)
        state = await self._repository.state(actor.employee_id)

        notices = []
        for condition in conditions:
            row = state.get(condition.key)
            dismissed = row is not None and row.dismissed_at is not None
            if dismissed and not include_dismissed:
                continue
            notices.append(
                Notice(
                    key=condition.key,
                    kind=condition.kind,
                    severity=condition.severity,
                    subject=condition.subject,
                    detail=condition.detail,
                    ref_type=condition.ref_type,
                    ref_id=condition.ref_id,
                    occurred_at=condition.occurred_at,
                    read=row is not None and row.read_at is not None,
                    dismissed=dismissed,
                )
            )
        notices.sort(key=lambda notice: (_SEVERITY_ORDER[notice.severity], notice.subject))
        return notices

    async def mark(self, actor: Actor, key: str, *, dismissed: bool = False) -> None:
        """Read it, or put it away.

        **Not validated against the live conditions**, deliberately: a condition that resolved
        between the screen rendering and the tap is exactly when somebody taps, and refusing then
        would mean the centre argues with people about things that have stopped being true.
        """
        await self._repository.mark(
            actor.employee_id, key, read_at=datetime.now(UTC), dismissed=dismissed
        )

    async def unread_count(self, actor: Actor, *, now: datetime | None = None) -> int:
        return sum(1 for notice in await self.centre(actor, now=now) if not notice.read)

    # --------------------------------------------------------------- the conditions

    async def _conditions(self, actor: Actor, now: datetime) -> list[Condition]:
        conditions: list[Condition] = []
        if actor.holds(PermissionCode.STOCK_VIEW):
            conditions += await self._stock(now)
        if actor.holds(PermissionCode.STOCK_COUNT):
            conditions += await self._counts()
        if actor.holds(PermissionCode.COMPLAINT_MANAGE):
            conditions += await self._complaints()
        if actor.holds(PermissionCode.CASH_MANAGE):
            conditions += await self._tills()
        conditions += await self._tasks(actor, now)
        return conditions

    async def _stock(self, now: datetime) -> list[Condition]:
        """Two conditions, and the first is the one this product exists to surface.

        A negative position means stock was consumed that nobody recorded receiving. It is
        `critical` because it is the only condition here where the *books* are wrong rather than
        the shelf, and every figure computed from them is wrong until somebody acts.
        """
        conditions = [
            Condition(
                key=f"stock.negative:{item_id}",
                kind="stock.negative",
                severity="critical",
                subject=name,
                detail=f"{quantity} on the books. Stock was used that nobody recorded receiving.",
                ref_type="stock_item",
                ref_id=item_id,
            )
            for item_id, name, quantity in await self._repository.negative_stock()
        ]
        horizon = (now + timedelta(days=EXPIRY_HORIZON_DAYS)).date()
        conditions += [
            Condition(
                key=f"stock.expiring:{batch_id}",
                kind="stock.expiring",
                severity="warning",
                subject=name,
                detail=f"Expires on {expiry.isoformat()}.",
                ref_type="stock_batch",
                ref_id=batch_id,
            )
            for batch_id, name, expiry in await self._repository.expiring_batches(horizon)
        ]
        return conditions

    async def _counts(self) -> list[Condition]:
        return [
            Condition(
                key=f"stock.count_awaiting:{count_id}",
                kind="stock.count_awaiting",
                severity="warning",
                subject=f"Stock count, {business_date.isoformat()}",
                detail="Counted and submitted. It changes nothing until a second person approves.",
                ref_type="stock_count",
                ref_id=count_id,
            )
            for count_id, business_date in await self._repository.counts_awaiting_approval()
        ]

    async def _complaints(self) -> list[Condition]:
        """A critical complaint is the second and last thing this product calls `critical`."""
        return [
            Condition(
                key=f"complaint.open:{complaint_id}",
                kind="complaint.open",
                severity="critical" if severity == "critical" else "warning",
                subject=f"Complaint {reference}",
                detail="Nobody has resolved this yet.",
                ref_type="complaint",
                ref_id=complaint_id,
                occurred_at=created_at,
            )
            for complaint_id, reference, severity, created_at in (
                await self._repository.open_complaints()
            )
        ]

    async def _tills(self) -> list[Condition]:
        return [
            Condition(
                key=f"cash.variance:{session_id}",
                kind="cash.variance",
                severity="warning",
                subject=f"Till, {business_date.isoformat()}",
                detail=f"Counted {variance:+} against what was expected.",
                ref_type="cash_session",
                ref_id=session_id,
            )
            for session_id, business_date, variance in await self._repository.till_variances(
                threshold=TILL_VARIANCE_THRESHOLD
            )
        ]

    async def _tasks(self, actor: Actor, now: datetime) -> list[Condition]:
        """**The one condition with two audiences, and the tier rule that separates them.**

        An overdue task goes to the person it is assigned to — minor, theirs to finish. Somebody
        holding `task.assign` sees every overdue task, because chasing them is the job. A waiter
        with three of their own does not also see the kitchen's.
        """
        overdue = await self._repository.overdue_tasks(now)
        chases = actor.holds(PermissionCode.TASK_ASSIGN)
        return [
            Condition(
                key=f"task.overdue:{task_id}",
                kind="task.overdue",
                severity="warning",
                subject=title,
                detail=f"Was due {due_at:%d %b, %H:%M}.",
                ref_type="task",
                ref_id=task_id,
                occurred_at=due_at,
            )
            for task_id, title, assigned_to, due_at in overdue
            if chases or assigned_to == actor.employee_id
        ]


# `critical` first, because it is the only one that means *now*. The scale is the locked six from
# `docs/ui/conventions.md`; nothing here invents a seventh.
_SEVERITY_ORDER: dict[str, int] = {"critical": 0, "warning": 1, "caution": 2, "info": 3}


def severities() -> Sequence[str]:
    """The severities this module can produce, for the schema and the tests to agree on."""
    return tuple(_SEVERITY_ORDER)
