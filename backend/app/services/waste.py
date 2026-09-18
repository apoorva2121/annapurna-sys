"""The rules for waste. `docs/modules/M09-waste-spec.md`, and `docs/waste-model.md` behind it.

Four rules, and they are why this file exists rather than routes calling repositories.

**1 · The event and its movement are one transaction, or neither happens.** `docs/schema.md` §8:
"Every `wastage_event` writes a paired `stock_movement` of type `wastage` in the same transaction.
Never one without the other." Both failures are bad and they are bad differently — an event with no
movement is waste everybody can see that never left the stock book, and the variance number is
silently wrong in the direction that hides theft; a movement with no event is stock gone with no
reason, no person and no stage, which is the mystery shrinkage this product exists to eliminate.

**2 · The cost is this service's answer and the client has no way to send one.** There is no field
for it in the request schema, so a client that tries gets a 422 from `extra="forbid"` rather than
having it dropped. It comes from the batches FEFO actually consumed at that moment — not today's
price, not an average — so a kilo wasted from Monday's expensive delivery costs what Monday cost.

**3 · Nothing here re-implements the ledger.** FEFO, per-batch cost, the negative-stock shortfall
and the append-only movement are M05's, reached through `InventoryService.consume`. This service
adds a reason, a person and a stage.

**4 · An approver is never the person who logged it.** Refused here and not merely discouraged:
approval is the control standing between an expensive reason code and somebody logging theft as
waste, and it is worth nothing if the same person can do both. Same shape as M05's rule that a
stock count's approver is never its counter.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.audit import audited, record
from app.core.enums import MovementBasis, MovementType
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.tenancy import TenantScope
from app.models.waste import WastageEvent, WastageReason
from app.repositories.waste import StageTotal, WastageEventRepository, WastageReasonRepository
from app.services.inventory import InventoryService
from app.services.shifts import ShiftService

logger = logging.getLogger(__name__)

# What a `wastage_event` names itself as in the stock ledger, so a movement can be traced back to
# the reason and the person behind it. `stock_movement.ref_type` has listed this value in
# `docs/schema.md` §5 since M05 — this module is what finally writes it.
REF_TYPE = "wastage_event"

# What `stock_movement.quantity_delta` and `wastage_event.quantity` hold: NUMERIC(14, 4).
_LEDGER_PLACES = Decimal("0.0001")


class WastageService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._reasons = WastageReasonRepository(session, scope)
        self._events = WastageEventRepository(session, scope)
        self._inventory = InventoryService(session, scope)

    # ------------------------------------------------------------------ reasons

    async def reasons(self, *, include_inactive: bool = False) -> Sequence[WastageReason]:
        return await self._reasons.list_all(include_inactive=include_inactive)

    @audited("wastage_reason.created", entity="wastage_reason")
    async def create_reason(
        self,
        actor: Actor,  # noqa: ARG002 - read by @audited
        *,
        code: str,
        name: str,
        stage: str,
        requires_photo: bool = False,
        requires_approval: bool = False,
    ) -> WastageReason:
        """A new reason. The code is normalised and permanent.

        Permanent because every report groups by it: renaming a code would split one reason into
        two across the date it changed, and a waste report that does that is worse than none. The
        uniqueness is a database constraint as well, because a check-then-insert is never the only
        guard (G-18).
        """
        normalised = code.strip().upper()
        if await self._reasons.by_code(normalised) is not None:
            raise ConflictError(
                "wastage.reason_code_taken",
                f"A reason with code {normalised} already exists. Codes are permanent, so pick "
                "another — or reactivate the existing one.",
            )
        reason = WastageReason(
            restaurant_id=self.scope.restaurant_id,
            code=normalised,
            name=name.strip(),
            stage=stage,
            requires_photo=requires_photo,
            requires_approval=requires_approval,
        )
        self.session.add(reason)
        await self.session.flush()
        return reason

    @audited("wastage_reason.updated", entity="wastage_reason", key="reason_id")
    async def update_reason(
        self,
        actor: Actor,  # noqa: ARG002 - read by @audited
        reason_id: uuid.UUID,
        *,
        name: str | None = None,
        requires_photo: bool | None = None,
        requires_approval: bool | None = None,
        is_active: bool | None = None,
    ) -> WastageReason:
        """Change what a reason is called and what it demands — never its code or its stage.

        The stage is what every report groups by. Changing it would move last quarter's waste
        between stages retrospectively, which is the one thing a waste report must never do; the
        request schema has no field for it, and this method has no parameter for it either.
        """
        reason = await self._reasons.get(reason_id)
        if reason is None:
            raise NotFoundError("wastage.reason_not_found", "That reason does not exist.")
        if name is not None:
            reason.name = name.strip()
        if requires_photo is not None:
            reason.requires_photo = requires_photo
        if requires_approval is not None:
            reason.requires_approval = requires_approval
        if is_active is not None:
            # Deactivated, never deleted (ADR 0008): historical events point here for ever.
            reason.is_active = is_active
        await self.session.flush()
        return reason

    # ------------------------------------------------------------------ the log

    async def log(
        self,
        actor: Actor,
        *,
        stock_item_id: uuid.UUID,
        wastage_reason_id: uuid.UUID,
        quantity: Decimal,
        per_purchase_unit: bool = False,
        station_id: uuid.UUID | None = None,
        menu_item_variant_id: uuid.UUID | None = None,
        order_line_id: uuid.UUID | None = None,
        note: str | None = None,
        occurred_at: datetime | None = None,
    ) -> WastageEvent:
        """Record something thrown away, and take it out of stock, together.

        The order of writes matters and is not arbitrary. The event is flushed **first** so it has
        an id for the movement to reference, then the consumption runs, then the cost it computed is
        written back. A failure anywhere in that sequence takes the whole transaction with it, which
        is the guarantee — not an ordering that happens to work.
        """
        if quantity <= 0:
            raise AppError(
                "wastage.quantity_invalid", "Say how much was thrown away.", status_code=422
            )
        reason = await self._reason(wastage_reason_id)
        if per_purchase_unit:
            # One conversion, on the server, through M05's own helper — so the ledger only ever
            # sees base units (invariant 5) and no screen does the arithmetic.
            quantity = await self._inventory.quantity_in_base_units(stock_item_id, quantity)
        # Quantised either way, so the response does not depend on which path the quantity took.
        # Without this, "500" and "500.0000" come back from the same endpoint for the same waste,
        # and a client comparing quantities across two records finds they differ when they do not.
        quantity = quantity.quantize(_LEDGER_PLACES)
        moment = occurred_at or datetime.now(UTC)
        business_date = await self._inventory.business_date_now(moment)

        event = WastageEvent(
            restaurant_id=self.scope.restaurant_id,
            stock_item_id=stock_item_id,
            wastage_reason_id=reason.id,
            quantity=quantity,
            # Replaced below with what the batches actually cost. Zero rather than None because the
            # column is NOT NULL by design — there is no moment at which this row exists without a
            # cost, and the flush that follows is inside the same transaction as the correction.
            cost_value=Decimal("0.00"),
            occurred_at=moment,
            business_date=business_date,
            reported_by=actor.employee_id,
            shift_id=await self._my_shift(actor),
            station_id=station_id,
            menu_item_variant_id=menu_item_variant_id,
            order_line_id=order_line_id,
            note=note,
        )
        self.session.add(event)
        await self.session.flush()

        consumed = await self._inventory.consume(
            actor,
            stock_item_id=stock_item_id,
            quantity=quantity,
            # **Actual, never theoretical** (invariant 7). Somebody physically threw this away; it
            # is not derived from a recipe, and summing the two together is what destroys the
            # leakage number this product exists to surface.
            basis=MovementBasis.ACTUAL,
            movement_type=MovementType.WASTAGE,
            ref_type=REF_TYPE,
            ref_id=event.id,
            occurred_at=moment,
            note=note,
        )
        event.cost_value = consumed.total_value.quantize(Decimal("0.01"))
        # The first batch FEFO took it from, when there was one. The movements hold the truth across
        # several; this is the human record's best single answer.
        if consumed.lines:
            event.stock_batch_id = consumed.lines[0].batch_id
        await self.session.flush()

        record(
            self.session,
            actor,
            action="wastage.logged",
            entity="wastage_event",
            entity_id=event.id,
            new={
                "reason": reason.code,
                "stage": reason.stage,
                "quantity": quantity,
                "cost_value": event.cost_value,
                "shortfall": consumed.shortfall,
            },
        )
        logger.info(
            "wastage.logged",
            extra={
                "wastage_event_id": str(event.id),
                "reason": reason.code,
                "stage": reason.stage,
                "cost_value": str(event.cost_value),
            },
        )
        return event

    @audited("wastage.approved", entity="wastage_event", key="event_id")
    async def approve(self, actor: Actor, event_id: uuid.UUID) -> WastageEvent:
        """Sign off an event logged against a reason that needs it.

        **The approver is never the person who logged it.** Refused rather than discouraged: the
        whole value of requiring approval on the expensive reasons is that a second person had to
        look, and one person being both people is not that. M05 draws the same line for a stock
        count's approver, and holds it with a CHECK constraint as well.
        """
        event = await self._events.with_reason(event_id)
        if event is None:
            raise NotFoundError("wastage.not_found", "That waste record does not exist.")
        if event.approved_at is not None:
            raise ConflictError("wastage.already_approved", "That has already been approved.")
        if event.reported_by == actor.employee_id:
            raise ConflictError(
                "wastage.approver_is_reporter",
                "Somebody else has to approve waste you logged yourself.",
            )
        event.approved_by = actor.employee_id
        event.approved_at = datetime.now(UTC)
        await self.session.flush()
        logger.info("wastage.approved", extra={"wastage_event_id": str(event.id)})
        return event

    # ------------------------------------------------------------------ reads

    async def get(self, event_id: uuid.UUID) -> WastageEvent:
        """One event with its reason loaded — what every route hands back.

        The reason is eager-loaded because the response carries its code, name and stage: the
        relationship is `lazy="raise"`, so a caller that wants them says so and an N+1 cannot
        appear by accident.
        """
        event = await self._events.with_reason(event_id)
        if event is None:
            raise NotFoundError("wastage.not_found", "That waste record does not exist.")
        return event

    async def business_date_now(self) -> date:
        """Today, in the restaurant's terms. A 01:30 entry belongs to the previous business day
        (invariant 4), and a summary defaulting to "the last seven days" has to agree with the
        rows it is summing."""
        return await self._inventory.business_date_now()

    async def list_events(
        self,
        *,
        business_date: date | None = None,
        stage: str | None = None,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[WastageEvent]:
        return await self._events.list_page(
            business_date=business_date, stage=stage, limit=limit, after=after
        )

    async def summary(self, *, since: date, until: date) -> list[StageTotal]:
        """What was lost, by stage and reason. The report `docs/waste-model.md` exists for.

        Shares are computed by the caller from these rows rather than here, and the totals are
        `Decimal` the whole way: a percentage of a rupee figure is presentation, and the moment it
        becomes a float somebody adds it to money.
        """
        if until < since:
            raise AppError(
                "wastage.range_invalid", "That date range runs backwards.", status_code=422
            )
        return await self._events.summary(since=since, until=until)

    # ------------------------------------------------------------------ internals

    async def _my_shift(self, actor: Actor) -> uuid.UUID | None:
        """The shift the actor is rostered to right now, or `None`.

        M12 finally fills the column this module created as a bare `shift_id` with a comment saying
        it was waiting. Nothing is backfilled and it stays nullable: a restaurant may run without a
        roster, and a row written before one existed has no shift and must keep saying so —
        attributing waste to a plausible shift nobody was on would manufacture exactly the kind of
        number this module exists to avoid.
        """
        for row in await ShiftService(self.session, self.scope).on_now():
            if row.assignment.employee_id == actor.employee_id:
                return row.assignment.shift_id
        return None

    async def _reason(self, reason_id: uuid.UUID) -> WastageReason:
        reason = await self._reasons.get(reason_id)
        if reason is None:
            raise NotFoundError("wastage.reason_not_found", "That reason does not exist.")
        if not reason.is_active:
            raise ConflictError(
                "wastage.reason_inactive",
                f"{reason.name} is no longer offered. Pick another reason.",
            )
        return reason
