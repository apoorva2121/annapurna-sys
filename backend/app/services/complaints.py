"""Complaints: an owner, a resolution, and a recovery figure nobody types.

`docs/customer-experience.md`: **"A logged complaint that nobody resolves is worse than no
system."**
It is worse because it manufactures evidence that somebody was told and nothing happened, which is
the document a lawyer reads out. So this service is shaped around the two fields that make a
complaint recoverable rather than recorded — who owns it, and what was done.

Three rules.

**1 · Resolved means somebody wrote down what was done.** Enforced by a check constraint, not by a
screen: `status IN ('resolved','closed')` requires `resolved_at` and `resolution`. A dropdown that
can be set to Resolved with an empty box is how a complaint system becomes paperwork.

**2 · `customer_returned` is derived and no endpoint writes it.** It becomes true weeks after
everybody has forgotten the complaint exists, so a column somebody must remember to tick would be
false for ever. It is a query: is there an order for this customer after `resolved_at`? Always
current, impossible to flatter, and there is no column for a stale copy to live in
(`docs/modules/M10-customers-spec.md` decision 8).

**3 · Severity is the complainant's, not the resolver's.** Nothing here downgrades a severity when
a complaint is resolved. A `critical` hygiene complaint that was handled well is still a `critical`
hygiene complaint, and a month of them is the pattern M13 is supposed to find.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.business_day import business_date_of, financial_year_of
from app.core.enums import ComplaintStatus
from app.core.errors import ConflictError, NotFoundError
from app.core.tenancy import TenantScope
from app.models.customers import Complaint
from app.repositories.customers import ComplaintRepository
from app.repositories.setup import RestaurantRepository

logger = logging.getLogger(__name__)

# `open → investigating → resolved → closed`, and the shortcuts a real conversation takes. A
# complaint settled at the table in one minute goes straight to `resolved`; nothing is gained by
# making somebody click through `investigating` first.
_ALLOWED: dict[str, frozenset[str]] = {
    ComplaintStatus.OPEN: frozenset({ComplaintStatus.INVESTIGATING, ComplaintStatus.RESOLVED}),
    ComplaintStatus.INVESTIGATING: frozenset({ComplaintStatus.RESOLVED}),
    ComplaintStatus.RESOLVED: frozenset({ComplaintStatus.CLOSED, ComplaintStatus.INVESTIGATING}),
    # Terminal. Reopening is a new complaint, because the second time is its own event and a
    # complaint that keeps reopening looks, in every report, like one complaint.
    ComplaintStatus.CLOSED: frozenset(),
}


class ComplaintService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._complaints = ComplaintRepository(session, scope)
        self._restaurants = RestaurantRepository(session, scope)

    async def create(
        self,
        actor: Actor,
        *,
        category: str,
        severity: str,
        description: str,
        customer_id: uuid.UUID | None = None,
        order_id: uuid.UUID | None = None,
        order_line_id: uuid.UUID | None = None,
        feedback_id: uuid.UUID | None = None,
        assigned_to: uuid.UUID | None = None,
        business_date: date | None = None,
    ) -> Complaint:
        """Log it, and give it a number a person can say out loud.

        The reference is short, per restaurant, per financial year — the same shape as the invoice
        series, so it restarts small rather than reaching six digits in the second year. A manager
        on the phone to a customer should not be reading out a UUID.
        """
        day = business_date or await self._business_date()
        year = financial_year_of(day)
        complaint = Complaint(
            restaurant_id=self.scope.restaurant_id,
            customer_id=customer_id,
            order_id=order_id,
            order_line_id=order_line_id,
            feedback_id=feedback_id,
            reference=await self._next_reference(year),
            category=category,
            severity=severity,
            description=description,
            reported_by=actor.employee_id,
            assigned_to=assigned_to,
            status=ComplaintStatus.OPEN,
            business_date=day,
            financial_year=year,
        )
        self.session.add(complaint)
        await self.session.flush()
        logger.info(
            "complaint.logged",
            extra={"severity": severity, "category": category, "assigned": assigned_to is not None},
        )
        return complaint

    async def list_open(self) -> Sequence[Complaint]:
        return await self._complaints.list_open()

    async def get(self, complaint_id: uuid.UUID) -> Complaint:
        return await self._require(complaint_id)

    async def assign(self, complaint_id: uuid.UUID, assigned_to: uuid.UUID) -> Complaint:
        """An owner, which is the field that separates a complaint system from paperwork.

        `docs/customer-experience.md`: "A logged complaint that nobody resolves is worse than no
        system." Assigning moves it to `investigating` when it is still `open`, because a complaint
        somebody is holding is not one nobody has looked at.
        """
        complaint = await self._require(complaint_id)
        complaint.assigned_to = assigned_to
        if complaint.status == ComplaintStatus.OPEN:
            complaint.status = ComplaintStatus.INVESTIGATING
        await self.session.flush()
        return complaint

    async def close(self, complaint_id: uuid.UUID) -> Complaint:
        """Finished with. Separate from `resolved` on purpose: a complaint can be resolved and still
        sit on somebody's screen until the manager agrees it is done."""
        complaint = await self._require(complaint_id)
        self._check_transition(complaint.status, ComplaintStatus.CLOSED)
        complaint.status = ComplaintStatus.CLOSED
        complaint.closed_at = datetime.now(UTC)
        await self.session.flush()
        return complaint

    async def _business_date(self) -> date:
        restaurant = await self._restaurants.get()
        if restaurant is None:
            raise NotFoundError("restaurant.not_found", "That restaurant does not exist.")
        return business_date_of(
            datetime.now(UTC), restaurant.timezone, restaurant.business_day_start
        )

    async def _next_reference(self, financial_year: str) -> str:
        """The next number in this restaurant's series for this year.

        Not a global counter and not the row count: a unique constraint on
        `(restaurant_id, financial_year, reference)` is what actually guarantees uniqueness, and
        two managers logging a complaint in the same second lose the race rather than the number.
        """
        highest = await self._complaints.highest_reference(financial_year)
        return str(highest + 1)

    async def resolve(
        self,
        complaint_id: uuid.UUID,
        *,
        resolution: str,
        compensation_amount: Decimal | None = None,
    ) -> Complaint:
        complaint = await self._require(complaint_id)
        self._check_transition(complaint.status, ComplaintStatus.RESOLVED)

        complaint.status = ComplaintStatus.RESOLVED
        complaint.resolution = resolution
        complaint.compensation_amount = compensation_amount
        complaint.resolved_at = datetime.now(UTC)
        await self.session.flush()
        logger.info(
            "complaint.resolved",
            extra={"severity": complaint.severity, "category": complaint.category},
        )
        return complaint

    async def returned_after_resolution(self, complaint: Complaint) -> bool | None:
        """`None` while the complaint is unresolved — "did they come back" has no meaning yet, and
        answering `false` would read as "they did not", which is a different and untrue thing."""
        if complaint.resolved_at is None or complaint.customer_id is None:
            return None
        return await self._complaints.returned_after(complaint.customer_id, complaint.resolved_at)

    async def _require(self, complaint_id: uuid.UUID) -> Complaint:
        complaint = await self._complaints.get(complaint_id)
        if complaint is None:
            raise NotFoundError("complaint.not_found", "That complaint no longer exists.")
        return complaint

    @staticmethod
    def _check_transition(current: str, target: str) -> None:
        if target not in _ALLOWED.get(current, frozenset()):
            raise ConflictError(
                "complaint.transition_invalid",
                "This complaint has moved on since you opened it. Reload to see where it is.",
            )
