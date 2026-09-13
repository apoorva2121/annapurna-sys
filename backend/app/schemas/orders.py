"""The API contract for orders.

Same conventions as the rest of the API: money is a **string** in JSON, never a float, and
`extra="forbid"` refuses a field the contract does not name rather than ignoring it.

**The client sends what was ordered, never what it costs** (`docs/security.md` A04). A line names a
dish, a quantity and its options. There is no price field to tamper with, and a request that adds
one is refused with a 422 — stronger than ignoring it, because a client that sends a price believes
the price it sent, and should be told otherwise.

**Every change carries the `version` it read** (ADR 0010). Two waiters on one table holding stale
copies is the ordinary evening, not an edge case; a stale version is a 409 and the screen reloads
rather than overwriting.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import (
    OrderChannel,
    OrderLineStatus,
    OrderStatus,
    OrderType,
    TaxRegime,
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ReadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


def _strip(value: Any) -> Any:
    """Strip before the length constraint, for the reason `schemas/setup.py` documents: an "after"
    validator lets `"   "` satisfy `min_length` and then stores nothing."""
    return value.strip() if isinstance(value, str) else value


Version = Annotated[int, Field(ge=1)]
Reason = Annotated[str, Field(min_length=3, max_length=280)]


# --------------------------------------------------------------------------- requests


class OrderCreateRequest(_Schema):
    type: OrderType
    table_ids: list[uuid.UUID] = Field(default_factory=list, max_length=8)
    covers: int | None = Field(default=None, ge=1, le=200)
    channel: OrderChannel = OrderChannel.POS
    external_order_id: str | None = Field(default=None, min_length=1, max_length=64)

    _clean = field_validator("external_order_id", mode="before")(_strip)

    @model_validator(mode="after")
    def _tables_fit_the_type(self) -> Self:
        if self.type == OrderType.DINE_IN and not self.table_ids:
            raise ValueError("A dine-in order sits at a table.")
        if self.type != OrderType.DINE_IN and self.table_ids:
            raise ValueError("Only a dine-in order takes a table.")
        if len(set(self.table_ids)) != len(self.table_ids):
            raise ValueError("Each table can be named once.")
        if self.external_order_id is not None and self.channel != OrderChannel.AGGREGATOR:
            raise ValueError("Only an aggregator order carries an external order id.")
        return self


class OrderLineAddRequest(_Schema):
    version: Version
    menu_item_variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=99)
    modifier_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    special_instructions: str | None = Field(default=None, max_length=280)

    _clean = field_validator("special_instructions", mode="before")(_strip)


class OrderLineUpdateRequest(_Schema):
    """Only an unsent line changes. Once the kitchen has it, the line is removed and added again."""

    version: Version
    quantity: int | None = Field(default=None, ge=1, le=99)
    special_instructions: str | None = Field(default=None, max_length=280)

    _clean = field_validator("special_instructions", mode="before")(_strip)


class OrderLineRemoveRequest(_Schema):
    """An unsent line is deleted and needs no reason. A sent one is cancelled and must say why."""

    version: Version
    reason: Reason | None = None

    _clean = field_validator("reason", mode="before")(_strip)


class OrderVersionRequest(_Schema):
    version: Version


class OrderCancelRequest(_Schema):
    version: Version
    reason: Reason

    _clean = field_validator("reason", mode="before")(_strip)


# --------------------------------------------------------------------------- responses


class OrderLineModifierResponse(_ReadSchema):
    id: uuid.UUID
    modifier_id: uuid.UUID
    price_delta: Decimal


class OrderLineResponse(_ReadSchema):
    id: uuid.UUID
    menu_item_variant_id: uuid.UUID
    quantity: int
    unit_price: Decimal
    line_subtotal: Decimal
    line_discount: Decimal
    tax_regime: TaxRegime
    tax_rate: Decimal
    tax_inclusive: bool
    taxable_value: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    tax_amount: Decimal
    line_total: Decimal
    status: OrderLineStatus
    sent_at: datetime | None
    special_instructions: str | None
    cancel_reason: str | None
    seq: int
    modifiers: list[OrderLineModifierResponse]


class OrderSummaryResponse(_Schema):
    """What a list row needs. The primary table comes first in `table_ids`."""

    id: uuid.UUID
    order_number: str
    type: OrderType
    channel: OrderChannel
    external_order_id: str | None
    status: OrderStatus
    waiter_employee_id: uuid.UUID | None
    covers: int | None
    parent_order_id: uuid.UUID | None
    table_ids: list[uuid.UUID]
    placed_at: datetime
    first_sent_at: datetime | None
    served_at: datetime | None
    bill_requested_at: datetime | None
    settled_at: datetime | None
    cancelled_at: datetime | None
    business_date: date
    subtotal: Decimal
    discount_total: Decimal
    charge_total: Decimal
    tax_total: Decimal
    round_off: Decimal
    grand_total: Decimal
    cancel_reason: str | None
    version: int


class OrderResponse(OrderSummaryResponse):
    """The whole order: before settlement, this *is* the provisional bill."""

    lines: list[OrderLineResponse]


class OrderListResponse(_Schema):
    items: list[OrderSummaryResponse]
    next_cursor: uuid.UUID | None = None
