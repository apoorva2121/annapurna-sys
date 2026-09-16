"""The API contract for waste.

**There is no cost field on the way in, and that is the contract's main feature.**
`docs/waste-model.md`: never require the person logging waste to know the cost — the system knows —
and show the rupee value only *after*, because showing it before suppresses honest reporting. With
`extra="forbid"`, a client that sends a cost is refused with a 422 rather than having it silently
dropped, which is the stronger answer: a client that sends a price believes the price it sent.

**Money is a string in JSON, never a float** (CLAUDE.md invariant 3), and quantities are
`Decimal` in base units — grams, millilitres or pieces, converted at the boundary, never here
(invariant 5).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.core.enums import WastageStage


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WastageReasonResponse(_Schema):
    id: uuid.UUID
    code: str
    name: str
    stage: WastageStage
    # Stored, and not enforced until M11 owns `attachment`. The screen may nudge; nothing refuses
    # a log for want of a photograph, because a cook who cannot record the waste in front of them
    # stops recording waste.
    requires_photo: bool
    requires_approval: bool
    is_active: bool


class WastageReasonListResponse(_Schema):
    items: list[WastageReasonResponse]


class WastageReasonCreateRequest(_Schema):
    # Immutable once created, like every other code in this product: it is the join key a report
    # groups by, and renaming it would split one reason into two across a date boundary.
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    stage: WastageStage
    requires_photo: bool = False
    requires_approval: bool = False


class WastageReasonUpdateRequest(_Schema):
    """The code and the stage are absent on purpose.

    A reason's stage is what every report groups by; changing it would move last quarter's waste
    between stages retrospectively, which is the one thing a waste report must never do. Withdraw
    the reason and add another.
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    requires_photo: bool | None = None
    requires_approval: bool | None = None
    is_active: bool | None = None


class WastageLogRequest(_Schema):
    """What was thrown away. **Note what is not here: a cost.**"""

    stock_item_id: uuid.UUID
    wastage_reason_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    # **The screen never converts, and this is why** (backlog-issues B12e). A cook thinks in half a
    # kilo of paneer, not five hundred grams, so the presets are labelled in the item's purchase
    # unit and this flag says so — the server does the one conversion, exactly as the receiving
    # form does. A quantity divided by a thousand in a browser is the float round-trip invariant 3
    # forbids, and a unit mix-up on a form like this is what made a plate of cabbage cost more than
    # a car.
    #
    # False is the old meaning — base units — so a caller that knows grams keeps working.
    per_purchase_unit: bool = False
    station_id: uuid.UUID | None = None
    # Both optional and both a person's choice. The server never fills these in: M08 deliberately
    # does not book waste when a dish is remade, because it may be reheated rather than binned.
    menu_item_variant_id: uuid.UUID | None = None
    order_line_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class WastageEventResponse(_Schema):
    id: uuid.UUID
    stock_item_id: uuid.UUID
    stock_batch_id: uuid.UUID | None
    wastage_reason_id: uuid.UUID
    reason_code: str
    reason_name: str
    stage: WastageStage
    quantity: Decimal
    # **Shown after, never before.** This is the teaching half of the rule: a cook who learns that
    # the tray they binned was ₹340 throws less away next week.
    cost_value: Decimal
    occurred_at: AwareDatetime
    business_date: date
    reported_by: uuid.UUID
    approved_by: uuid.UUID | None
    approved_at: AwareDatetime | None
    # True when this event's reason wants a signature and has not had one. The screen surfaces it;
    # nothing is blocked by it, because the waste already happened.
    awaiting_approval: bool
    note: str | None


class WastageEventListResponse(_Schema):
    items: list[WastageEventResponse]
    next_cursor: str | None


class WastageSummaryLine(_Schema):
    stage: WastageStage
    reason_code: str
    reason_name: str
    events: int
    cost_value: Decimal
    # Of the whole range's cost, as a string with one decimal place. Computed on the server from
    # `Decimal` so the four stages add to a hundred — a share rounded per row in SQL does not.
    share_percent: str


class WastageSummaryResponse(_Schema):
    """The report `docs/waste-model.md` exists for, in its smallest honest form.

    Not a single total: "This week you lost ₹31,200" is a number nobody can act on until it is
    split by stage, because each stage has a different owner and a different fix.
    """

    since: date
    until: date
    total_cost: Decimal
    lines: list[WastageSummaryLine]
