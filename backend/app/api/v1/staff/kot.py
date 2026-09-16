"""The kitchen display's endpoints. Every handler is authorise-call-shape.

Two permissions, straight from `seed/organization.yaml`'s P1 design and not amended here:

- `kot.view` — read the rail, a ticket, and the stream. A **waiter holds this and nothing else** on
  this path, which is the design's own line: the floor watches the kitchen and does not drive it.
- `kot.update` — acknowledge, start, mark ready, and ask for a remake. Chef, kitchen staff, manager.

**`served` is not here.** It arrives from the order screen, behind the order permissions a waiter
already holds, because a dish is served when it reaches a table and the kitchen cannot see the table
(`docs/modules/M08-kitchen-spec.md` decision 5). Asking for it here is a 409 naming the other screen
rather than a 403, because the person is not unauthorised — they are on the wrong screen.

**The stream does not take a database session, and it is the only route that does not.** It holds a
connection open for a whole service; a session dependency would hold one pooled database connection
for exactly as long, so six kitchen screens would take six connections out of the pool and never
give them back. It takes the session *factory* and opens a short-lived session per tick instead.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import EventSourceResponse
from fastapi.sse import ServerSentEvent

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.db import SessionFactoryDep
from app.core.permissions import PermissionCode
from app.models.kitchen import KotTicket
from app.repositories.base import DEFAULT_PAGE_SIZE
from app.schemas.kitchen import (
    KotLineResponse,
    KotLineStatusRequest,
    KotRailResponse,
    KotRemakeRequest,
    KotStatusRequest,
    KotTicketResponse,
)
from app.services.kitchen import KitchenService
from app.services.kitchen_stream import RETRY_MS, kitchen_events

router = APIRouter(tags=["kitchen"])


def _service(session: SessionDep, actor: Actor) -> KitchenService:
    """The scope comes from the *actor*, never from the request (`docs/security.md` A04)."""
    return KitchenService(session, actor.scope)


def _ticket(ticket: KotTicket) -> KotTicketResponse:
    """A ticket as the rail renders it.

    The dish names come off the line rather than the menu — they were copied at the send, so a
    display resolves nothing and a withdrawn dish still reads correctly. The tables come off the
    order, live, because a party that moves mid-meal has to be found where they are now.
    """
    return KotTicketResponse(
        id=ticket.id,
        ticket_number=ticket.ticket_number,
        order_id=ticket.order_id,
        order_number=ticket.order.order_number,
        table_codes=[link.restaurant_table.code for link in ticket.order.tables],
        station_id=ticket.station_id,
        sequence_in_order=ticket.sequence_in_order,
        status=ticket.status,
        is_remake=ticket.is_remake,
        target_minutes=ticket.target_minutes,
        business_date=ticket.business_date,
        revision=ticket.revision,
        printed_at=ticket.printed_at,
        acknowledged_at=ticket.acknowledged_at,
        started_at=ticket.started_at,
        ready_at=ticket.ready_at,
        served_at=ticket.served_at,
        lines=[
            KotLineResponse(
                id=line.id,
                order_line_id=line.order_line_id,
                item_name=line.item_name,
                variant_name=line.variant_name,
                quantity=line.quantity,
                status=line.status,
                modifier_summary=line.modifier_summary,
                special_instructions=line.special_instructions,
                remake_reason=line.remake_reason,
                started_at=line.started_at,
                ready_at=line.ready_at,
                served_at=line.served_at,
            )
            for line in ticket.lines
        ],
    )


@router.get("/kot/tickets", response_model=KotRailResponse)
async def rail(
    session: SessionDep,
    actor: Annotated[Actor, Depends(require_permission(PermissionCode.KOT_VIEW))],
    station_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = DEFAULT_PAGE_SIZE,
) -> KotRailResponse:
    """What a station has to cook, oldest first.

    The revision is returned with it so a screen can open the stream exactly where this read
    finished, with no gap in between and nothing replayed twice.
    """
    service = _service(session, actor)
    tickets = await service.rail(station_id=station_id, statuses=status, limit=limit)
    return KotRailResponse(
        tickets=[_ticket(ticket) for ticket in tickets],
        revision=await service.current_revision(),
    )


@router.get("/kot/tickets/{ticket_id}", response_model=KotTicketResponse)
async def ticket_detail(
    ticket_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[Actor, Depends(require_permission(PermissionCode.KOT_VIEW))],
) -> KotTicketResponse:
    return _ticket(await _service(session, actor).get(ticket_id))


@router.patch("/kot/tickets/{ticket_id}/status", response_model=KotTicketResponse)
async def advance(
    ticket_id: uuid.UUID,
    body: KotStatusRequest,
    session: SessionDep,
    actor: Annotated[Actor, Depends(require_permission(PermissionCode.KOT_UPDATE))],
) -> KotTicketResponse:
    ticket = await _service(session, actor).advance(ticket_id, body.status, actor)
    await session.commit()
    return _ticket(ticket)


@router.patch("/kot/tickets/{ticket_id}/lines/{line_id}/status", response_model=KotTicketResponse)
async def advance_line(
    ticket_id: uuid.UUID,
    line_id: uuid.UUID,
    body: KotLineStatusRequest,
    session: SessionDep,
    actor: Annotated[Actor, Depends(require_permission(PermissionCode.KOT_UPDATE))],
) -> KotTicketResponse:
    """One dish ready before the rest of its ticket — the normal case at a busy pass."""
    ticket = await _service(session, actor).advance_line(ticket_id, line_id, body.status, actor)
    await session.commit()
    return _ticket(ticket)


@router.post("/kot/tickets/{ticket_id}/lines/{line_id}/remake", response_model=KotTicketResponse)
async def remake(
    ticket_id: uuid.UUID,
    line_id: uuid.UUID,
    body: KotRemakeRequest,
    session: SessionDep,
    actor: Annotated[Actor, Depends(require_permission(PermissionCode.KOT_UPDATE))],
) -> KotTicketResponse:
    """Returns the **new** ticket, because that is what the kitchen now has to cook."""
    ticket = await _service(session, actor).request_remake(ticket_id, line_id, body.reason, actor)
    await session.commit()
    return _ticket(ticket)


@router.get("/kot/stream", response_class=EventSourceResponse)
async def stream(
    request: Request,
    sessions: SessionFactoryDep,
    actor: Annotated[Actor, Depends(require_permission(PermissionCode.KOT_VIEW))],
    station_id: Annotated[uuid.UUID | None, Query()] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> AsyncIterator[ServerSentEvent]:
    """Every change to this restaurant's kitchen, as it happens.

    `retry` is sent first and once: the browser's backoff is the server's to choose, so it can be
    changed without shipping a frontend.

    A heartbeat is a *comment* rather than an event, which is the difference between "the connection
    is alive" and "something happened". A client that treated one as the other would redraw an
    unchanged rail every fifteen seconds all night.
    """
    # A comment rather than an event: it carries the retry interval and nothing a client has to
    # process. An opening event with an empty body would make every screen redraw on connect.
    yield ServerSentEvent(comment="stream open", retry=RETRY_MS)

    async for event in kitchen_events(
        sessions,
        actor,
        station_id=station_id,
        cursor=_cursor(last_event_id),
        is_disconnected=request.is_disconnected,
    ):
        if event is None:
            # A comment. `EventSourceResponse` writes a bare `: ` line for an event with no data.
            yield ServerSentEvent(comment="heartbeat")
        else:
            # `raw_data`, not `data`: the latter JSON-encodes whatever it is given, so a
            # pre-serialised model would arrive at the browser as a quoted string it has to parse
            # twice.
            yield ServerSentEvent(
                id=str(event.revision),
                event="ticket",
                raw_data=_ticket(event.ticket).model_dump_json(),
            )


def _cursor(last_event_id: str | None) -> int | None:
    """A client's `Last-Event-ID`, or None for a screen that has just read the rail.

    Client-supplied and therefore not trusted: anything that is not a non-negative integer is
    treated as "no cursor" rather than refused, because a browser that reconnects with a corrupted
    header should get tonight's kitchen rather than an error it cannot act on.
    """
    if last_event_id is None or not last_event_id.isdigit():
        return None
    return int(last_event_id)
