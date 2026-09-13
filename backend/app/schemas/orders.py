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

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import (
    ChargeType,
    DiscountType,
    DocumentType,
    InvoiceStatus,
    OrderChannel,
    OrderLineStatus,
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentStatus,
    TableStatus,
    TaxRegime,
)
from app.schemas.gstin import GSTIN_PATTERN, capitalise_gstin


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
Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Rate = Annotated[Decimal, Field(gt=0, le=1, max_digits=6, decimal_places=4)]


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


class OrderRemoveRequest(_Schema):
    """Taking something off an order: a line, a discount or a charge.

    Only a line the kitchen has seen must say why, and the service is what knows that; a reason
    given anywhere else is recorded in the audit row rather than refused.
    """

    version: Version
    reason: Reason | None = None

    _clean = field_validator("reason", mode="before")(_strip)


class OrderVersionRequest(_Schema):
    version: Version


class OrderCancelRequest(_Schema):
    version: Version
    reason: Reason

    _clean = field_validator("reason", mode="before")(_strip)


class OrderDiscountRequest(_Schema):
    """A discount or a comp. **There is no `authorised_by` field**: the person holding
    `order.discount` who sends this is its authoriser, because "the manager said it was fine" is the
    sentence the row exists to replace."""

    version: Version
    type: DiscountType
    rate: Rate | None = None
    flat_amount: Money | None = None
    order_line_id: uuid.UUID | None = None
    reason: Reason

    _clean = field_validator("reason", mode="before")(_strip)

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.type == DiscountType.FLAT:
            if self.flat_amount is None or self.rate is not None:
                raise ValueError("A flat discount has an amount and no rate.")
        elif self.rate is None or self.flat_amount is not None:
            raise ValueError("A percentage discount or a comp has a rate and no amount.")
        return self


class OrderChargeRequest(_Schema):
    """Packaging or delivery carries the amount the restaurant charges. A service charge carries
    none: it is computed from the bill at the restaurant's own rate, never typed in."""

    version: Version
    type: ChargeType
    amount: Money | None = None
    tax_group_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.type == ChargeType.SERVICE_CHARGE and self.amount is not None:
            raise ValueError("A service charge is computed from the bill, never typed in.")
        if self.type != ChargeType.SERVICE_CHARGE and self.amount is None:
            raise ValueError("A packaging or delivery charge needs its amount.")
        return self


class OrderSplitRequest(_Schema):
    """The dishes to move to a new order at the same tables."""

    version: Version
    line_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _each_once(self) -> Self:
        if len(set(self.line_ids)) != len(self.line_ids):
            raise ValueError("Each line can be named once.")
        return self


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


class OrderDiscountResponse(_ReadSchema):
    id: uuid.UUID
    order_line_id: uuid.UUID | None
    type: DiscountType
    rate: Decimal | None
    flat_amount: Decimal | None
    amount: Decimal
    reason: str
    authorised_by: uuid.UUID


class OrderChargeResponse(_ReadSchema):
    id: uuid.UUID
    type: ChargeType
    amount: Decimal
    tax_rate: Decimal | None
    cgst_amount: Decimal
    sgst_amount: Decimal
    tax_amount: Decimal
    is_optional: bool


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
    discounts: list[OrderDiscountResponse]
    charges: list[OrderChargeResponse]
    # The invoice a settled or voided order was issued, so the screen that credits a bill can
    # reach it from the order. Filled when the order is read; a live order has none.
    invoice_id: uuid.UUID | None = None


class OrderListResponse(_Schema):
    items: list[OrderSummaryResponse]
    next_cursor: uuid.UUID | None = None


# --------------------------------------------------------------------------- settlement
#
# Appended to app/schemas/orders.py by chunk G's patch.

# Same structural pattern as `schemas/setup.py` and `schemas/procurement.py`. A well-formed GSTIN is
# not a verified one (`docs/compliance-rules.md` §A3).
_GSTIN = GSTIN_PATTERN


class PaymentRequest(_Schema):
    """One payment toward the bill. Several are how "we'll pay separately" works (decision 9).

    `paid_at` is when the money was actually received — a UPI payment confirmed before the bill was
    printed — because Section 14 counts it. The server refuses a time before the order was placed or
    after now, so it cannot be used to move a bill across a rate change.
    """

    method: PaymentMethod
    amount: Money
    tip_amount: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)] = Decimal("0.00")
    reference: str | None = Field(default=None, max_length=64)
    paid_at: AwareDatetime | None = None

    _clean = field_validator("reference", mode="before")(_strip)


class RecipientRequest(_Schema):
    """A registered customer's details, printed on their tax invoice when they ask (Rule 46(d))."""

    name: str | None = Field(default=None, max_length=160)
    gstin: str | None = Field(default=None, pattern=_GSTIN)
    address: str | None = Field(default=None, max_length=400)

    _clean = field_validator("name", "address", mode="before")(_strip)
    _gstin = field_validator("gstin", mode="before")(capitalise_gstin)


class OrderSettleRequest(_Schema):
    version: Version
    payments: list[PaymentRequest] = Field(min_length=1, max_length=10)
    recipient: RecipientRequest | None = None


class PaymentResponse(_ReadSchema):
    id: uuid.UUID
    method: PaymentMethod
    amount: Decimal
    tip_amount: Decimal
    reference: str | None
    status: PaymentStatus
    paid_at: datetime
    credit_note_id: uuid.UUID | None


class InvoiceResponse(_Schema):
    """The legal document as issued, with the payments made against it."""

    id: uuid.UUID
    order_id: uuid.UUID
    document_type: DocumentType
    invoice_number: str
    financial_year: str
    status: InvoiceStatus
    issued_at: datetime
    invoice_date: date
    business_date: date
    supplier_name: str
    supplier_address: dict[str, Any] | None
    supplier_gstin: str | None
    fssai_licence: str | None
    recipient_name: str | None
    recipient_gstin: str | None
    recipient_address: str | None
    sac_code: str
    taxable_total: Decimal
    cgst_total: Decimal
    sgst_total: Decimal
    non_gst_tax_total: Decimal
    discount_total: Decimal
    charge_total: Decimal
    round_off: Decimal
    grand_total: Decimal
    cancelled_at: datetime | None
    cancel_reason: str | None
    payments: list[PaymentResponse]


# --------------------------------------------------------------------------- reversals
#
# Appended to app/schemas/orders.py by chunk H's patch, after chunk G's settlement schemas.


class InvoiceCancelRequest(_Schema):
    """Only for an invoice issued in error, on its own business day. The reason is required."""

    reason: Reason

    _clean = field_validator("reason", mode="before")(_strip)


class CreditLineRequest(_Schema):
    order_line_id: uuid.UUID
    quantity: int = Field(ge=1, le=99)


class RefundRequest(_Schema):
    """Money going back. Sent positive; stored as a negative payment naming the credit note."""

    method: PaymentMethod
    amount: Money
    reference: str | None = Field(default=None, max_length=64)

    _clean = field_validator("reference", mode="before")(_strip)

    @model_validator(mode="after")
    def _real_money(self) -> Self:
        if self.method == PaymentMethod.DUE:
            raise ValueError("A refund is money going back, so it cannot be on account.")
        return self


class CreditNoteRequest(_Schema):
    reason: Reason
    lines: list[CreditLineRequest] = Field(min_length=1, max_length=50)
    refunds: list[RefundRequest] = Field(default_factory=list, max_length=5)

    _clean = field_validator("reason", mode="before")(_strip)

    @model_validator(mode="after")
    def _each_dish_once(self) -> Self:
        ids = [line.order_line_id for line in self.lines]
        if len(set(ids)) != len(ids):
            raise ValueError("Each dish can be named once on a credit note.")
        return self


class CreditNoteLineResponse(_ReadSchema):
    id: uuid.UUID
    order_line_id: uuid.UUID
    quantity: int
    taxable_value: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    tax_amount: Decimal
    line_total: Decimal


class CreditNoteResponse(_Schema):
    id: uuid.UUID
    invoice_id: uuid.UUID
    credit_note_number: str
    financial_year: str
    issued_at: datetime
    note_date: date
    business_date: date
    reason: str
    issued_by: uuid.UUID
    taxable_total: Decimal
    cgst_total: Decimal
    sgst_total: Decimal
    non_gst_tax_total: Decimal
    grand_total: Decimal
    lines: list[CreditNoteLineResponse]
    refunds: list[PaymentResponse]


# --------------------------------------------------------------------------- the floor


class FloorOrder(_Schema):
    """What a table cell shows about the order sitting there: enough to tap into it, no more."""

    id: uuid.UUID
    order_number: str
    status: OrderStatus
    grand_total: Decimal
    first_sent_at: datetime | None
    bill_requested_at: datetime | None
    version: int


class FloorTable(_Schema):
    id: uuid.UUID
    code: str
    seats: int
    status: TableStatus
    orders: list[FloorOrder]


class FloorArea(_Schema):
    id: uuid.UUID
    name: str
    tables: list[FloorTable]


class FloorResponse(_Schema):
    """The table map. Behind `order.view`, because a waiter needs it and does not hold
    `restaurant.configure`, which guards the setup table list."""

    areas: list[FloorArea]
