"""The API contract for the kitchen.

Two things here are shaped by the screen rather than by the table.

**The rail carries what it needs to be read at two metres**, and nothing else. The order number and
the table are what a chef looks for; the dish name and its options are what they cook from. A
ticket response therefore carries denormalised names rather than ids the display would have to
resolve — a KDS that fetched a menu to render a ticket would be one round trip from being blank
during a service.

**Elapsed time is not sent.** `printed_at` and `target_minutes` are, and the client counts. A
server-sent "seven minutes ago" is stale the instant it arrives and would have to be re-fetched
every second to stay true, which is exactly the polling the stream exists to avoid.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.core.enums import KotLineStatus, KotTicketStatus


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KotLineResponse(_Schema):
    id: uuid.UUID
    order_line_id: uuid.UUID
    # What is cooked, spelled out. The KDS never joins to a menu.
    item_name: str
    variant_name: str
    quantity: int
    status: KotLineStatus
    # "No onion, Extra spicy" — the half of a ticket that gets a dish sent back when it is missed,
    # which is why it is a first-class field and not a footnote. One string rather than a list,
    # because it is copied off the ticket line exactly as the kitchen will read it.
    modifier_summary: str | None = None
    special_instructions: str | None = None
    remake_reason: str | None = None
    started_at: AwareDatetime | None = None
    ready_at: AwareDatetime | None = None
    served_at: AwareDatetime | None = None


class KotTicketResponse(_Schema):
    id: uuid.UUID
    ticket_number: str
    order_id: uuid.UUID
    order_number: str
    # Where the food goes. Empty for a takeaway, which the display says in words rather than by
    # leaving a gap.
    table_codes: list[str] = Field(default_factory=list)
    station_id: uuid.UUID
    sequence_in_order: int
    status: KotTicketStatus
    is_remake: bool
    target_minutes: int
    business_date: date
    # The cursor. A client that reconnects sends the highest it has seen.
    revision: int
    printed_at: AwareDatetime
    acknowledged_at: AwareDatetime | None = None
    started_at: AwareDatetime | None = None
    ready_at: AwareDatetime | None = None
    served_at: AwareDatetime | None = None
    lines: list[KotLineResponse]


class KotRailResponse(_Schema):
    tickets: list[KotTicketResponse]
    # Where the stream should resume from if the client opens one after this read. Sent even when
    # the rail is empty, because "nothing to cook" is a valid place to start watching from.
    revision: int


class KotStatusRequest(_Schema):
    # `served` is deliberately absent from what a client may ask for here, and the service refuses
    # it with a message naming the order screen: a dish is served by whoever carried it to a table.
    status: KotTicketStatus


class KotLineStatusRequest(_Schema):
    status: KotLineStatus


class KotRemakeRequest(_Schema):
    # Required, and not from a fixed list. A remake reason is how a kitchen learns; a dropdown of
    # five options is how it stops writing them down.
    reason: str = Field(min_length=1, max_length=280)
