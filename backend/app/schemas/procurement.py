"""The API contract for procurement.

Same conventions as the rest of the API: quantities and money are **strings** in JSON, never
floats, and `extra="forbid"` refuses a misspelled field rather than ignoring it.

**Three quantities on a receipt line, and none of them is called `quantity`.** `quantity_invoiced`
is what the bill says, `quantity_received` is what the scale says, `quantity_rejected` is what
arrived and was refused. A field named `quantity` would eventually be filled in with whichever
number the caller had to hand, and `docs/waste-model.md` §1's report would be unanswerable for
ever. The derived figures — accepted, short delivery, order shortfall, and every rupee value — are
**response** fields only: the server computes them, the client never does (invariant 3).

**There is no update or delete request for a goods receipt.** It is append-only and the database
refuses both, so an API shape implying otherwise would be lying about what the server can do. The
correction path is a stock adjustment referencing the receipt.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import PurchaseOrderStatus


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ReadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


def _strip(value: Any) -> Any:
    """Strip before the length constraint, for the reason `schemas/setup.py` documents: an "after"
    validator lets `"   "` satisfy `min_length=1` and then stores nothing."""
    return value.strip() if isinstance(value, str) else value


# Same pattern as `RestaurantUpdateRequest.gstin` (M02): 2-digit state code, 10-character PAN,
# entity digit, 'Z', checksum. Structure rather than length, because the attack the M02 threat
# table describes is substituting somebody else's tax identity — and a typo is only found at return
# time. **A well-formed GSTIN is not a verified one**; there is no check digit
# (`docs/compliance-rules.md` §A3), and nothing downstream may treat this as verification.
_GSTIN = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"


# --------------------------------------------------------------------------- suppliers


class SupplierCreateRequest(_Schema):
    name: str = Field(min_length=1, max_length=160)
    contact_person: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=254)
    gstin: str | None = Field(default=None, pattern=_GSTIN)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)

    _clean = field_validator("name", "contact_person", "phone", "email", mode="before")(_strip)


class SupplierUpdateRequest(_Schema):
    """Every field optional; only what is sent changes.

    `is_active=false` is how a supplier is retired. There is no delete: master-data tier, and every
    historical receipt points at this row for ever.
    """

    name: str | None = Field(default=None, min_length=1, max_length=160)
    contact_person: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=254)
    gstin: str | None = Field(default=None, pattern=_GSTIN)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    is_active: bool | None = None

    _clean = field_validator("name", "contact_person", "phone", "email", mode="before")(_strip)


class SupplierResponse(_ReadSchema):
    id: uuid.UUID
    name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    gstin: str | None
    payment_terms_days: int | None
    is_active: bool
    deactivated_at: datetime | None


class SupplierListResponse(_ReadSchema):
    suppliers: list[SupplierResponse]


# --------------------------------------------------------------------------- orders


class OrderLineRequest(_Schema):
    stock_item_id: uuid.UUID
    # Base units (invariant 5). The supplier's sack is converted at the boundary, so nothing
    # downstream has to know what a "bag" was.
    quantity_ordered: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=6)


class OrderCreateRequest(_Schema):
    supplier_id: uuid.UUID
    lines: list[OrderLineRequest] = Field(min_length=1)
    expected_at: datetime | None = None
    # `total_amount` is absent on purpose. The server computes it from the lines; a client that
    # could send a total would be choosing what its own order cost (`docs/security.md` A04).


class OrderUpdateRequest(_Schema):
    """Draft orders only. Once sent, a supplier has seen it and it is a commitment."""

    lines: list[OrderLineRequest] | None = Field(default=None, min_length=1)
    expected_at: datetime | None = None


class OrderCancelRequest(_Schema):
    reason: str = Field(min_length=1, max_length=500)

    _clean = field_validator("reason", mode="before")(_strip)


class OrderLineResponse(_ReadSchema):
    stock_item_id: uuid.UUID
    quantity_ordered: Decimal
    unit_price: Decimal


class OrderResponse(_ReadSchema):
    id: uuid.UUID
    po_number: str
    supplier_id: uuid.UUID
    status: PurchaseOrderStatus
    expected_at: datetime | None
    total_amount: Decimal
    created_by: uuid.UUID | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    lines: list[OrderLineResponse]


class OrderListResponse(_ReadSchema):
    orders: list[OrderResponse]


# --------------------------------------------------------------------------- receiving


class ReceiptLineRequest(_Schema):
    """One line of a delivery, as the person at the gate reports it.

    Zero is allowed for all three quantities: *"they billed 50 kg and delivered nothing for this
    line"* is a real and important row. `quantity_rejected` may not exceed `quantity_received` — a
    CHECK constraint says so too — and a rejection carries a reason.

    `unit_price` is optional against an order: the quoted price is the default, so the person
    weighing types weights rather than retyping the one figure the variance report multiplies by.
    """

    stock_item_id: uuid.UUID
    quantity_invoiced: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    quantity_received: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    quantity_rejected: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=4)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=6)
    rejection_reason: str | None = Field(default=None, max_length=500)

    _clean = field_validator("rejection_reason", mode="before")(_strip)


class ReceiveAgainstOrderRequest(_Schema):
    """`supplier_id` is absent deliberately: it comes from the order.

    A delivery cannot be attributed to a different supplier than the one it was ordered from, and
    letting a client send both is inviting exactly that.
    """

    lines: list[ReceiptLineRequest] = Field(min_length=1)
    invoice_number: str | None = Field(default=None, max_length=64)
    # What the supplier billed, tax included — a fact being reported, not a figure the server could
    # derive, which is why this one number does come from the client.
    invoice_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    # How much of it was tax. Borne, not reclaimable (`docs/compliance-rules.md` §A6), so it lands
    # in the cost of the stock.
    tax_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    received_at: datetime | None = None

    _clean = field_validator("invoice_number", mode="before")(_strip)


class AdHocReceiptRequest(ReceiveAgainstOrderRequest):
    """A market purchase: no order behind it, so it says who it came from and what things cost."""

    supplier_id: uuid.UUID


class ReceiptLineResponse(_ReadSchema):
    stock_item_id: uuid.UUID
    quantity_invoiced: Decimal
    quantity_received: Decimal
    quantity_rejected: Decimal
    unit_price: Decimal
    rejection_reason: str | None


class ReceiptResponse(_ReadSchema):
    id: uuid.UUID
    purchase_order_id: uuid.UUID | None
    supplier_id: uuid.UUID
    received_at: datetime
    business_date: date
    invoice_number: str | None
    invoice_amount: Decimal | None
    tax_amount: Decimal | None
    received_by: uuid.UUID | None
    lines: list[ReceiptLineResponse]


class ReceiptListResponse(_ReadSchema):
    receipts: list[ReceiptResponse]


class PostedLineResponse(_ReadSchema):
    """One line's three numbers with every derivation the server computed from them.

    `ordered` and `order_shortfall` are `null` for a market purchase, and null rather than zero on
    purpose: nothing was ordered, so nothing was under-supplied, and "no order" and "delivered in
    full" are different claims.
    """

    stock_item_id: uuid.UUID
    ordered: Decimal | None
    invoiced: Decimal
    received: Decimal
    rejected: Decimal
    accepted: Decimal
    short_delivery: Decimal
    order_shortfall: Decimal | None
    unit_price: Decimal
    landed_unit_cost: Decimal
    short_delivery_value: Decimal
    accepted_value: Decimal


class PostedReceiptResponse(_ReadSchema):
    """The confirmation panel, returned **after** the weight can no longer be edited.

    `docs/waste-model.md` is explicit that showing the rupee value of a loss before it is recorded
    suppresses honest reporting. A screen announcing *"this weight will flag your supplier for
    ₹4,200"* while somebody holds the scale is asking them to choose between an accurate number and
    an awkward conversation, and some of them will move the number.
    """

    receipt: ReceiptResponse
    lines: list[PostedLineResponse]
    # What the invoice's own lines add up to, before tax. When this and `invoice_amount` disagree by
    # more than the tax, the supplier's arithmetic does not match their own line items — a
    # different and more interesting problem than a short delivery.
    invoice_line_total: Decimal
    short_delivery_value: Decimal
    accepted_value: Decimal


# --------------------------------------------------------------------------- the report


class VarianceRowResponse(_ReadSchema):
    stock_item_id: uuid.UUID
    code: str
    name: str
    base_unit: str
    deliveries: int
    invoiced: Decimal
    received: Decimal
    rejected: Decimal
    short_delivery: Decimal
    short_delivery_value: Decimal


class SupplierVarianceResponse(_ReadSchema):
    supplier_id: uuid.UUID
    supplier_name: str
    start: date
    end: date
    deliveries: int
    invoiced: Decimal
    received: Decimal
    short_delivery_value: Decimal
    rows: list[VarianceRowResponse]
