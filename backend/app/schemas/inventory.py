"""The API contract for the stock ledger.

Same conventions as the rest of the API: quantities and money are **strings** in JSON, never
floats, and `extra="forbid"` refuses a misspelled field rather than ignoring it.

The string rule matters more here than almost anywhere else in the product. A stock movement can be
`0.05` g of saffron; a `float` round-trip through JavaScript makes that `0.05000000000000000277`,
and the ledger is a table whose whole purpose is that it adds up exactly.

**There is no update or delete request in this file, for anything.** The ledger is append-only
(invariant 2) and the database refuses both, so an API shape that implied otherwise would be
lying about what the server can do. A correction is `AdjustmentRequest`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import MovementBasis, MovementType, StockCountScope, StockCountStatus


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ReadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


# ---------------------------------------------------------------- requests


class ReceiptRequest(_Schema):
    stock_item_id: uuid.UUID
    # `gt=0` rather than `ge=0`: a receipt of nothing is not a receipt, and the service says so in
    # words, pointing at the adjustment endpoint instead.
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    unit_cost: Decimal = Field(ge=0, max_digits=14, decimal_places=6)
    batch_code: str | None = Field(default=None, max_length=64)
    expiry_date: date | None = None
    storage_location: str | None = Field(default=None, max_length=120)


class ProductionRequest(_Schema):
    stock_item_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=4)


class AdjustmentRequest(_Schema):
    stock_item_id: uuid.UUID
    # Signed, and explicitly allowed to be negative — that is the whole point of an adjustment.
    # Zero is refused by the service, because an adjustment of nothing is either a mistake or an
    # attempt to write an audit row that says nothing.
    quantity_delta: Decimal = Field(max_digits=14, decimal_places=4)
    reason: str = Field(min_length=1, max_length=500)


class CountOpenRequest(_Schema):
    stock_item_ids: list[uuid.UUID] = Field(min_length=1)
    scope: StockCountScope = StockCountScope.FULL


class CountLineInput(_Schema):
    stock_item_id: uuid.UUID
    counted_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=4)


class CountRecordRequest(_Schema):
    lines: list[CountLineInput] = Field(min_length=1)


# ---------------------------------------------------------------- responses


class BatchResponse(_ReadSchema):
    id: uuid.UUID
    stock_item_id: uuid.UUID
    batch_code: str
    quantity_received: Decimal
    unit_cost: Decimal
    received_at: datetime
    expiry_date: date | None
    storage_location: str | None
    source: str


class OnHandResponse(_ReadSchema):
    """One item's derived position. Nothing here is stored — every field is a sum."""

    stock_item_id: uuid.UUID
    code: str
    name: str
    base_unit: str
    quantity: Decimal
    value: Decimal
    # Computed rather than stored, and surfaced explicitly so a screen does not have to know that
    # `quantity < 0` is meaningful. A negative position means stock was consumed that nobody
    # recorded receiving (M05 spec decision 2) — the alert is the product, not an error state.
    is_negative: bool


class OnHandListResponse(_ReadSchema):
    items: list[OnHandResponse]
    # So a screen can lead with the problem rather than making someone scan for it.
    negative_count: int


class ExpiringBatchResponse(_ReadSchema):
    batch_id: uuid.UUID
    unit_cost: Decimal
    remaining: Decimal
    expiry_date: date | None


class ExpiringListResponse(_ReadSchema):
    batches: list[ExpiringBatchResponse]


class MovementResponse(_ReadSchema):
    id: uuid.UUID
    stock_item_id: uuid.UUID
    stock_batch_id: uuid.UUID
    type: MovementType
    quantity_delta: Decimal
    unit_cost: Decimal
    basis: MovementBasis
    occurred_at: datetime
    business_date: date
    ref_type: str | None
    ref_id: uuid.UUID | None
    note: str | None


class ConsumptionLineResponse(_ReadSchema):
    batch_id: uuid.UUID
    quantity: Decimal
    unit_cost: Decimal


class ConsumptionResponse(_ReadSchema):
    lines: list[ConsumptionLineResponse]
    # Returned rather than raised. A caller is told what it could not cover and carries on, because
    # refusing would stop a restaurant taking money over a bookkeeping gap.
    shortfall: Decimal
    total_value: Decimal


class CountLineResponse(_ReadSchema):
    stock_item_id: uuid.UUID
    system_quantity: Decimal
    counted_quantity: Decimal
    variance_value: Decimal
    reason: str | None


class CountResponse(_ReadSchema):
    id: uuid.UUID
    counted_at: datetime
    business_date: date
    scope: StockCountScope
    status: StockCountStatus
    counted_by: uuid.UUID | None
    approved_by: uuid.UUID | None
    lines: list[CountLineResponse]


class CountListResponse(_ReadSchema):
    counts: list[CountResponse]
