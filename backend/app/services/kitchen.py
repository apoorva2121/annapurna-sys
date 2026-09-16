"""The rules for a ticket, from the send to the pass. `docs/modules/M08-kitchen-spec.md`.

Five rules, and they are why this file exists rather than routes calling repositories.

**1 · A ticket is a round.** `raise_tickets` makes one ticket per station represented in *this*
send, never one per order per station. A ticket's membership never changes afterwards: a second
send is a second ticket, because that is what a second piece of paper is.

**2 · The clock only runs forwards.** `new → acknowledged → preparing → ready` and nothing else.
There is no way back from `ready`, no edit, and no delete — correcting a mistake is a remake with
a reason, which is a row. Migration 0030's CHECK constraints hold the timestamp half of this even
if this service is wrong.

**3 · The kitchen owns `ready`; the floor owns `served`.** Every method here refuses `served`,
which arrives instead from `OrderService.mark_served` through `serve_order_lines`. A cook who
clears a rail of food that never left the pass settles nothing and hides nothing — it makes the gap
between `ready_at` and `served_at` visible, which is the whole control (spec threat question).

**4 · Every kitchen write bumps the restaurant's revision, once per transaction.** That is what
lets `GET /kot/stream` replay from a dropped client's cursor instead of from a queue nobody kept.
A send that raises three tickets is one kitchen event and gives all three one revision.

**5 · The kitchen never writes money.** Nothing in this file touches a `Decimal`. Deliberate, and
asserted by a test rather than left to intention.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import KotLineStatus, KotTicketStatus, OrderLineStatus
from app.core.errors import ConflictError, NotFoundError
from app.core.tenancy import TenantScope
from app.models.kitchen import KotTicket, KotTicketLine
from app.models.orders import Order, OrderLine
from app.repositories.kitchen import OPEN_STATUSES, KitchenRepository, LineRouting

logger = logging.getLogger(__name__)

# The only path through the kitchen. A status may move to the one after it and to nothing else;
# `served` is absent because it is the floor's, and `cancelled` because it arrives from a
# cancelled order line rather than from a button on the rail.
_NEXT: dict[str, str] = {
    KotTicketStatus.NEW: KotTicketStatus.ACKNOWLEDGED,
    KotTicketStatus.ACKNOWLEDGED: KotTicketStatus.PREPARING,
    KotTicketStatus.PREPARING: KotTicketStatus.READY,
}
# The timestamp each arrival stamps, and the actor column that goes with it where there is one.
_STAMP: dict[str, str] = {
    KotTicketStatus.ACKNOWLEDGED: "acknowledged_at",
    KotTicketStatus.PREPARING: "started_at",
    KotTicketStatus.READY: "ready_at",
}
_ACTOR_COLUMN: dict[str, str] = {
    KotTicketStatus.ACKNOWLEDGED: "acknowledged_by",
    KotTicketStatus.READY: "ready_by",
}
# A ticket that has left the rail for good.
_FINAL = frozenset({KotTicketStatus.SERVED, KotTicketStatus.CANCELLED})
# What a ticket's arrival means for the lines on it. `acknowledged` means nothing to a dish — it
# says the kitchen has seen the paper, not that anything is in a pan.
_TICKET_TO_LINE: dict[str, str] = {
    KotTicketStatus.PREPARING: KotLineStatus.PREPARING,
    KotTicketStatus.READY: KotLineStatus.READY,
}
# A line that is still work. Everything else has left the rail.
_LINE_OPEN = frozenset({KotLineStatus.PENDING, KotLineStatus.PREPARING, KotLineStatus.READY})
# What the order line reads while the kitchen has it, so the waiter's screen says the same thing
# the rail does.
_ORDER_LINE_ECHO: dict[str, str] = {
    KotLineStatus.PREPARING: OrderLineStatus.PREPARING,
    KotLineStatus.READY: OrderLineStatus.READY,
}


class KitchenService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._kitchen = KitchenRepository(session, scope)

    # ------------------------------------------------------------------ the send

    async def raise_tickets(
        self, order: Order, lines: Sequence[OrderLine], *, now: datetime | None = None
    ) -> list[KotTicket]:
        """One ticket per station represented in this send. Called by `OrderService.send`.

        Takes the lines rather than re-reading them, because the caller has just decided which of
        them are new and that decision must not be made twice with a different answer.
        """
        if not lines:
            return []
        now = now or datetime.now(UTC)
        routing = await self._kitchen.routing_for([line.id for line in lines])
        if len(routing) != len(lines):
            # A line whose variant or item vanished between the send and this query. Refused rather
            # than dropped: a dish silently missing from the rail is a dish nobody cooks.
            raise ConflictError(
                "kot.unroutable",
                "One of these dishes has no kitchen station any more. "
                "Reload the menu and try again.",
            )

        by_station: dict[uuid.UUID, list[LineRouting]] = defaultdict(list)
        for route in routing:
            by_station[route.station_id].append(route)

        rounds = await self._kitchen.rounds_so_far(order.id)
        revision = await self._kitchen.bump_revision()

        tickets: list[KotTicket] = []
        for station_id, routes in sorted(by_station.items(), key=lambda item: str(item[0])):
            ticket = KotTicket(
                restaurant_id=self.scope.restaurant_id,
                order_id=order.id,
                station_id=station_id,
                ticket_number=await self._kitchen.next_ticket_number(order.business_date),
                sequence_in_order=rounds.get(station_id, 0) + 1,
                status=KotTicketStatus.NEW,
                is_remake=False,
                # The standard for the *slowest* dish, not the sum: a station cooks a round in
                # parallel, and summing would declare every four-dish ticket late on arrival.
                target_minutes=max(route.prep_minutes for route in routes),
                business_date=order.business_date,
                revision=revision,
                printed_at=now,
            )
            ticket.lines = [
                KotTicketLine(
                    restaurant_id=self.scope.restaurant_id,
                    order_line_id=route.order_line_id,
                    quantity=route.quantity,
                    item_name=route.item_name,
                    variant_name=route.variant_name,
                    modifier_summary=route.modifier_summary,
                    special_instructions=route.special_instructions,
                    status=KotLineStatus.PENDING,
                    seq=route.seq,
                )
                for route in routes
            ]
            self.session.add(ticket)
            tickets.append(ticket)

        await self.session.flush()
        logger.info(
            "kot.raised",
            extra={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "tickets": len(tickets),
                "revision": revision,
            },
        )
        return tickets

    # ------------------------------------------------------------------ the rail

    async def rail(
        self, *, station_id: uuid.UUID | None, statuses: Sequence[str] | None, limit: int | None
    ) -> Sequence[KotTicket]:
        return await self._kitchen.rail(
            station_id=station_id, statuses=statuses or OPEN_STATUSES, limit=limit
        )

    async def get(self, ticket_id: uuid.UUID) -> KotTicket:
        ticket = await self._kitchen.with_lines(ticket_id)
        if ticket is None:
            raise NotFoundError("kot.not_found", "That ticket does not exist.")
        return ticket

    # ------------------------------------------------------------------ transitions

    async def advance(self, ticket_id: uuid.UUID, to_status: str, actor: Actor) -> KotTicket:
        """Move a ticket one step along, stamping the time and who did it."""
        ticket = await self.get(ticket_id)
        self._refuse_served(to_status)
        if ticket.status in _FINAL:
            raise ConflictError(
                "kot.finished",
                f"Ticket {ticket.ticket_number} is {ticket.status} and cannot change.",
            )
        expected = _NEXT.get(ticket.status)
        if to_status != expected:
            raise ConflictError(
                "kot.out_of_order",
                f"Ticket {ticket.ticket_number} is {ticket.status}. "
                + (f"The next step is {expected}." if expected else "It is finished."),
            )

        now = datetime.now(UTC)
        ticket.status = to_status
        setattr(ticket, _STAMP[to_status], now)
        actor_column = _ACTOR_COLUMN.get(to_status)
        if actor_column is not None:
            setattr(ticket, actor_column, actor.employee_id)
        # The lines follow the ticket, so a chef who works the whole ticket never touches a line.
        line_status = _TICKET_TO_LINE.get(to_status)
        if line_status is not None:
            for line in ticket.lines:
                if line.status in _LINE_OPEN:
                    self._set_line_status(line, line_status, now)
        await self._touch(ticket)
        await self._echo_to_order(ticket)
        logger.info(
            "kot.advanced",
            extra={"ticket": ticket.ticket_number, "status": to_status},
        )
        return ticket

    async def advance_line(
        self, ticket_id: uuid.UUID, line_id: uuid.UUID, to_status: str, actor: Actor
    ) -> KotTicket:
        """One dish ready before the rest of its ticket.

        When the last open line arrives, the ticket arrives with it — and not before, which is the
        difference between "the table's food is ready" and "some of it is".
        """
        ticket = await self.get(ticket_id)
        self._refuse_served(to_status)
        line = self._line(ticket, line_id)
        if line.status not in _LINE_OPEN:
            raise ConflictError(
                "kot.line_finished", "That dish is no longer on the rail and cannot change."
            )
        if to_status not in (KotLineStatus.PREPARING, KotLineStatus.READY):
            raise ConflictError("kot.line_status", "A dish goes to preparing, then to ready.")
        if to_status == KotLineStatus.PREPARING and line.status != KotLineStatus.PENDING:
            raise ConflictError("kot.line_out_of_order", "That dish is already being cooked.")

        now = datetime.now(UTC)
        self._set_line_status(line, to_status, now)
        # A ticket nobody acknowledged, whose first dish is now being cooked, is acknowledged: the
        # work started, and a rail that still said `new` would be lying about it.
        if ticket.status == KotTicketStatus.NEW:
            ticket.status = KotTicketStatus.ACKNOWLEDGED
            ticket.acknowledged_at = now
            ticket.acknowledged_by = actor.employee_id
        if ticket.status == KotTicketStatus.ACKNOWLEDGED:
            ticket.status = KotTicketStatus.PREPARING
            ticket.started_at = now
        open_lines = [line for line in ticket.lines if line.status in _LINE_OPEN]
        if not open_lines and ticket.status == KotTicketStatus.PREPARING:
            ticket.status = KotTicketStatus.READY
            ticket.ready_at = now
            ticket.ready_by = actor.employee_id
        await self._touch(ticket)
        await self._echo_to_order(ticket)
        return ticket

    async def request_remake(
        self, ticket_id: uuid.UUID, line_id: uuid.UUID, reason: str, actor: Actor
    ) -> KotTicket:
        """The original line keeps its history; the remade dish is a new ticket.

        Not a wastage event. The dish may be going back to be reheated rather than binned, and a
        system that books waste on the kitchen's behalf teaches people to stop remaking food —
        M09 offers the link and a person decides (spec decision 8).
        """
        ticket = await self.get(ticket_id)
        line = self._line(ticket, line_id)
        if line.status in (KotLineStatus.CANCELLED, KotLineStatus.REMAKE):
            raise ConflictError(
                "kot.line_finished", "That dish has already been cancelled or remade."
            )
        reason = reason.strip()
        if not reason:
            raise ConflictError("kot.remake_reason", "Say why it is being remade.")

        now = datetime.now(UTC)
        line.status = KotLineStatus.REMAKE
        line.remake_reason = reason
        revision = await self._kitchen.bump_revision()
        routing = await self._kitchen.routing_for([line.order_line_id])
        if not routing:
            raise ConflictError("kot.unroutable", "That dish has no kitchen station any more.")
        route = routing[0]
        rounds = await self._kitchen.rounds_so_far(ticket.order_id)
        remake = KotTicket(
            restaurant_id=self.scope.restaurant_id,
            order_id=ticket.order_id,
            station_id=route.station_id,
            ticket_number=await self._kitchen.next_ticket_number(ticket.business_date),
            sequence_in_order=rounds.get(route.station_id, 0) + 1,
            status=KotTicketStatus.NEW,
            is_remake=True,
            target_minutes=route.prep_minutes,
            business_date=ticket.business_date,
            revision=revision,
            printed_at=now,
        )
        remake.lines = [
            KotTicketLine(
                restaurant_id=self.scope.restaurant_id,
                order_line_id=route.order_line_id,
                quantity=line.quantity,
                item_name=route.item_name,
                variant_name=route.variant_name,
                modifier_summary=route.modifier_summary,
                special_instructions=route.special_instructions,
                status=KotLineStatus.PENDING,
                seq=0,
            )
        ]
        self.session.add(remake)
        ticket.revision = revision
        await self.session.flush()
        # The dish is back in the kitchen, so the order line says so rather than staying `ready`.
        await self._set_order_line(line.order_line_id, OrderLineStatus.SENT)
        logger.warning(
            "kot.remake",
            extra={
                "ticket": ticket.ticket_number,
                "remake_ticket": remake.ticket_number,
                "actor_employee_id": str(actor.employee_id),
            },
        )
        return remake

    # ------------------------------------------------------------------ what the floor does

    async def serve_order_lines(self, order_line_ids: Sequence[uuid.UUID]) -> None:
        """Stamp `served` down onto the kitchen, from `OrderService.mark_served`.

        The one place `served` is written. A dish is served when it reaches the table, and the
        kitchen cannot see the table.
        """
        lines = await self._kitchen.lines_for_order_lines(order_line_ids)
        touched = [line for line in lines if line.status in _LINE_OPEN]
        if not touched:
            return
        now = datetime.now(UTC)
        for line in touched:
            # A dish served straight off the pass never passed through `ready`, and the CHECK
            # refuses a `served_at` without one — so the pass is recorded too, at the same instant.
            if line.ready_at is None:
                line.ready_at = now
            line.status = KotLineStatus.SERVED
            line.served_at = now
        await self._finish_tickets(
            {line.kot_ticket_id for line in touched}, KotTicketStatus.SERVED, now
        )

    async def cancel_order_lines(self, order_line_ids: Sequence[uuid.UUID]) -> None:
        """A dish taken off the bill is a dish the kitchen stops cooking, in this transaction.

        The reverse never holds: a ticket going `ready` cannot cancel an order line. The kitchen
        never writes money.
        """
        lines = await self._kitchen.lines_for_order_lines(order_line_ids)
        touched = [line for line in lines if line.status in _LINE_OPEN]
        if not touched:
            return
        now = datetime.now(UTC)
        for line in touched:
            line.status = KotLineStatus.CANCELLED
        await self._finish_tickets(
            {line.kot_ticket_id for line in touched}, KotTicketStatus.CANCELLED, now
        )

    # ------------------------------------------------------------------ internals

    async def _finish_tickets(self, ticket_ids: set[uuid.UUID], status: str, now: datetime) -> None:
        """A ticket leaves the rail when its last open line does, and not before."""
        revision = await self._kitchen.bump_revision()
        for ticket in await self._kitchen.tickets_by_id(sorted(ticket_ids, key=str)):
            ticket.revision = revision
            if any(line.status in _LINE_OPEN for line in ticket.lines):
                continue
            if ticket.status in _FINAL:
                continue
            if status == KotTicketStatus.SERVED:
                if ticket.ready_at is None:
                    ticket.acknowledged_at = ticket.acknowledged_at or now
                    ticket.started_at = ticket.started_at or now
                    ticket.ready_at = now
                ticket.served_at = now
            else:
                ticket.cancelled_at = now
            ticket.status = status
        await self.session.flush()

    def _set_line_status(self, line: KotTicketLine, status: str, now: datetime) -> None:
        line.status = status
        if status == KotLineStatus.PREPARING and line.started_at is None:
            line.started_at = now
        if status == KotLineStatus.READY and line.ready_at is None:
            line.ready_at = now

    async def _touch(self, ticket: KotTicket) -> None:
        ticket.revision = await self._kitchen.bump_revision()
        await self.session.flush()

    async def _echo_to_order(self, ticket: KotTicket) -> None:
        """Say the same thing on the waiter's screen that the rail says.

        The order line is the floor's copy of where a dish has got to. Without this, a waiter
        watching the order screen sees `sent` until the food arrives, and the one question the
        kitchen display exists to answer — *is it ready?* — is answerable only in the kitchen.
        """
        wanted = {
            line.order_line_id: _ORDER_LINE_ECHO[line.status]
            for line in ticket.lines
            if line.status in _ORDER_LINE_ECHO
        }
        if not wanted:
            return
        for order_line in await self._kitchen.order_lines_by_id(sorted(wanted, key=str)):
            order_line.status = wanted[order_line.id]
        await self.session.flush()

    async def _set_order_line(self, order_line_id: uuid.UUID, status: str) -> None:
        for order_line in await self._kitchen.order_lines_by_id([order_line_id]):
            order_line.status = status
        await self.session.flush()

    @staticmethod
    def _line(ticket: KotTicket, line_id: uuid.UUID) -> KotTicketLine:
        line = next((line for line in ticket.lines if line.id == line_id), None)
        if line is None:
            raise NotFoundError("kot.line_not_found", "That dish is not on this ticket.")
        return line

    @staticmethod
    def _refuse_served(status: str) -> None:
        if status == KotTicketStatus.SERVED or status == KotLineStatus.SERVED:
            raise ConflictError(
                "kot.served_is_the_floors",
                "A dish is served from the order screen, by whoever carried it to the table.",
            )
