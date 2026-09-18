"""The till: a float in, cash taken, payouts out, and a count at the end. Chunk I of M07.

Spec decision 11, and `docs/modules.md`'s cash reconciliation. Four rules:

**1 · Expected cash is derived, never stored.** The opening float, plus every cash payment posted to
the till — a refund is negative, and posts to the till open when it is given — minus the payouts
made from it. Payments and payouts are append-only, so a closed till's figure cannot move after
the fact (acceptance criterion 16).

**2 · The variance is stored at close and never corrected away.** Counted minus expected, frozen
with the count. Finding the missing ₹400 in the wrong drawer next morning is an **adjustment**: a
new row with a reason, recorded by somebody other than the person who closed the till — M05's
count-approval rule, held the same way. The adjusted variance is shown beside the original, never
instead of it, because "short by ₹400, found next day" and "never short" are different evenings.

**3 · A payout is a row.** ₹300 handed to the vegetable seller comes out of the till with an amount,
a reason and a name, and cannot exceed what the till should hold.

**4 · One till at a time.** Two counters is a real restaurant and out of scope for month 1;
migration 0019's partial unique index holds it even when two managers open a till in the same
second.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.audit import record
from app.core.business_day import business_date_of
from app.core.enums import CashMovementType, CashSessionStatus
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.money import format_inr
from app.core.permissions import OWNER_RANK
from app.core.tenancy import TenantScope
from app.models.orders import CashCount, CashMovement, CashSession
from app.models.tenancy import Restaurant
from app.repositories.orders import CashSessionRepository, PaymentRepository, TillTotals
from app.repositories.setup import RestaurantRepository
from app.services.people import Person, people
from app.services.shifts import ShiftService

logger = logging.getLogger(__name__)


def _dec(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class TillPosition:
    """A till and the figures derived from its rows. Nothing here is stored except the variance."""

    till: CashSession
    totals: TillTotals
    # By name (D13): who closed it, and who adjusted it afterwards, first to last.
    closer: Person | None = None
    adjusters: tuple[Person, ...] = ()

    @property
    def expected(self) -> Decimal:
        return _dec(self.till.opening_float) + self.totals.cash_taken - self.totals.payouts

    @property
    def adjusted_variance(self) -> Decimal | None:
        if self.till.variance is None:
            return None
        return _dec(self.till.variance) + self.totals.adjustments


class CashService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._tills = CashSessionRepository(session, scope)

    # ------------------------------------------------------------------ reads

    async def detail(
        self, till_id: uuid.UUID
    ) -> tuple[TillPosition, Sequence[CashCount], Sequence[CashMovement], dict[uuid.UUID, Person]]:
        """The till, its counts and movements, and everyone they name (D13)."""
        till = await self._tills.get(till_id)
        if till is None:
            raise NotFoundError("cash_session.not_found", "That till session does not exist.")
        position = await self._position_of(till)
        movements = await self._tills.movements_of(till.id)
        named = await people(
            self.session, self.scope, [till.closed_by, *(row.recorded_by for row in movements)]
        )
        adjusters: list[Person] = []
        for row in movements:
            person = named.get(row.recorded_by)
            if (
                row.type == CashMovementType.ADJUSTMENT
                and person is not None
                and person not in adjusters
            ):
                adjusters.append(person)
        position = replace(
            position,
            closer=named.get(till.closed_by) if till.closed_by is not None else None,
            adjusters=tuple(adjusters),
        )
        return position, await self._tills.counts_of(till.id), movements, named

    async def list_tills(
        self, *, limit: int | None = None, after: uuid.UUID | None = None
    ) -> list[TillPosition]:
        """A page of tills with their derived figures, in three statements whatever its size."""
        tills = await self._tills.list_page(limit=limit, after=after)
        ids = [till.id for till in tills]
        totals = await self._tills.totals_for(ids)
        adjusted = await self._tills.adjusters_for(ids)
        named = await people(
            self.session,
            self.scope,
            [till.closed_by for till in tills]
            + [who for each in adjusted.values() for who in each],
        )
        return [
            TillPosition(
                till=till,
                totals=totals[till.id],
                closer=named.get(till.closed_by) if till.closed_by is not None else None,
                adjusters=tuple(named[who] for who in adjusted[till.id] if who in named),
            )
            for till in tills
        ]

    async def outside_any_till(self) -> tuple[date, Decimal, int]:
        """Today's cash that went into no till, and how many payments (decision D3). Today is the
        restaurant's business day, not the calendar's."""
        restaurant = await self._restaurant()
        today = business_date_of(
            datetime.now(UTC), restaurant.timezone, restaurant.business_day_start
        )
        amount, payments = await PaymentRepository(self.session, self.scope).cash_outside_any_till(
            today
        )
        return today, amount, payments

    # ------------------------------------------------------------------ the day

    async def open(self, actor: Actor, *, opening_float: Decimal) -> uuid.UUID:
        already = await self._tills.open_id()
        if already is not None:
            raise ConflictError(
                "cash.session_open",
                "A till is already open. Close it before opening another.",
                details={"session_id": str(already)},
            )
        restaurant = await self._restaurant()
        now = datetime.now(UTC)
        till = CashSession(
            restaurant_id=self.scope.restaurant_id,
            status=CashSessionStatus.OPEN,
            opened_at=now,
            opened_by=actor.employee_id,
            opening_float=opening_float,
            business_date=business_date_of(now, restaurant.timezone, restaurant.business_day_start),
            shift_id=await self._my_shift(actor),
        )
        self.session.add(till)
        try:
            await self.session.flush()
        except IntegrityError as error:
            # Two managers in the same second: the index answered for the check above.
            raise ConflictError(
                "cash.session_open", "A till was opened a moment ago. Reload to see it."
            ) from error
        record(
            self.session,
            actor,
            action="cash.open",
            entity="cash_session",
            entity_id=till.id,
            new={"opening_float": opening_float},
        )
        await self.session.flush()
        logger.info("cash.opened", extra={"session_id": str(till.id)})
        return till.id

    async def payout(
        self, actor: Actor, till_id: uuid.UUID, *, amount: Decimal, reason: str
    ) -> None:
        till = await self._locked(till_id)
        if till.status == CashSessionStatus.CLOSED:
            raise ConflictError(
                "cash.session_closed", "This till is closed. A payout comes out of the open till."
            )
        position = await self._position_of(till)
        if amount > position.expected:
            raise AppError(
                "cash.payout_exceeds_till",
                f"Not enough cash in the till. Only {format_inr(position.expected)} is available.",
                details={"expected": str(position.expected)},
                status_code=422,
            )
        await self._movement(actor, till, CashMovementType.PAYOUT, amount, reason)
        # A payout adds a `cash_movement`; the till row itself does not change, so there is no
        # diff to take. The fact goes through the same writer the decorator uses.
        record(
            self.session,
            actor,
            action="cash.payout",
            entity="cash_session",
            entity_id=till.id,
            new={"amount": amount},
            reason=reason,
        )
        await self.session.flush()

    async def close(
        self, actor: Actor, till_id: uuid.UUID, *, counts: Sequence[tuple[Decimal, int]]
    ) -> None:
        till = await self._locked(till_id)
        if till.status == CashSessionStatus.CLOSED:
            raise ConflictError("cash.session_closed", "This till is already closed.")
        denominations = [denomination for denomination, _ in counts]
        if len(set(denominations)) != len(denominations):
            raise AppError(
                "cash.count_duplicate", "Each note or coin is counted once.", status_code=422
            )

        counted = sum(
            (denomination * quantity for denomination, quantity in counts), Decimal("0.00")
        )
        position = await self._position_of(till)
        variance = counted - position.expected
        for denomination, quantity in counts:
            self.session.add(
                CashCount(
                    restaurant_id=self.scope.restaurant_id,
                    cash_session_id=till.id,
                    denomination=denomination,
                    quantity=quantity,
                )
            )
        till.status = CashSessionStatus.CLOSED
        till.closed_at = datetime.now(UTC)
        till.closed_by = actor.employee_id
        till.counted_cash = counted
        till.variance = variance
        await self.session.flush()
        record(
            self.session,
            actor,
            action="cash.close",
            entity="cash_session",
            entity_id=till.id,
            new={
                "expected": position.expected,
                "counted": counted,
                "variance": variance,
            },
        )
        await self.session.flush()
        logger.info("cash.closed", extra={"session_id": str(till.id), "variance": str(variance)})

    async def adjust(
        self, actor: Actor, till_id: uuid.UUID, *, amount: Decimal, reason: str
    ) -> None:
        till = await self._tills.get(till_id)
        if till is None:
            raise NotFoundError("cash_session.not_found", "That till session does not exist.")
        if till.status == CashSessionStatus.OPEN:
            raise ConflictError(
                "cash.session_still_open",
                "A till is adjusted after it is closed. While it is open, the count at close "
                "settles it.",
            )
        # Decision D16: the owner may correct a till they closed, and it is marked on the till
        # and in reports; anyone else needs a second person, as M05's count approval does.
        if till.closed_by == actor.employee_id and actor.rank != OWNER_RANK:
            raise ConflictError(
                "cash.adjustment_by_closer",
                "The person who closed a till cannot adjust it. Another manager, or the "
                "owner, has to.",
            )
        await self._movement(actor, till, CashMovementType.ADJUSTMENT, amount, reason)
        record(
            self.session,
            actor,
            action="cash.adjust",
            entity="cash_session",
            entity_id=till.id,
            new={"amount": amount, "variance_at_close": till.variance},
            reason=reason,
        )
        await self.session.flush()

    # ------------------------------------------------------------------ plumbing

    async def _position_of(self, till: CashSession) -> TillPosition:
        totals = await self._tills.totals_for([till.id])
        return TillPosition(till=till, totals=totals[till.id])

    async def _movement(
        self,
        actor: Actor,
        till: CashSession,
        kind: CashMovementType,
        amount: Decimal,
        reason: str,
    ) -> None:
        restaurant = await self._restaurant()
        now = datetime.now(UTC)
        self.session.add(
            CashMovement(
                restaurant_id=self.scope.restaurant_id,
                cash_session_id=till.id,
                type=kind,
                amount=amount,
                reason=reason,
                recorded_by=actor.employee_id,
                occurred_at=now,
                business_date=business_date_of(
                    now, restaurant.timezone, restaurant.business_day_start
                ),
            )
        )
        await self.session.flush()

    async def _locked(self, till_id: uuid.UUID) -> CashSession:
        till = await self._tills.get_for_update(till_id)
        if till is None:
            raise NotFoundError("cash_session.not_found", "That till session does not exist.")
        return till

    async def _my_shift(self, actor: Actor) -> uuid.UUID | None:
        """The shift the actor is rostered to right now, or `None`.

        M12 finally fills the column this module created as a bare `shift_id` with a comment saying
        it was waiting. Nothing is backfilled and it stays nullable: a restaurant may run without a
        roster, and a row written before one existed has no shift and must keep saying so.
        """
        for row in await ShiftService(self.session, self.scope).on_now():
            if row.assignment.employee_id == actor.employee_id:
                return row.assignment.shift_id
        return None

    async def _restaurant(self) -> Restaurant:
        restaurant = await RestaurantRepository(self.session, self.scope).get()
        if restaurant is None:
            raise NotFoundError("restaurant.not_found", "This restaurant no longer exists.")
        return restaurant
