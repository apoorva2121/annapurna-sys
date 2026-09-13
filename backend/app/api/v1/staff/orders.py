"""Orders at the table. Every handler is authorise-call-shape.

Six permissions, from `seed/organization.yaml`'s P1 design:

- `order.view` — read orders and their provisional bills. The accountant holds this and nothing else
  on this path.
- `order.create` — open an order.
- `order.modify` — everything that changes a live order: its lines, sending, serving, asking for the
  bill, cancelling an order that never settled, charges, and splitting a bill by items.
- `order.discount` — apply or remove a discount or a comp. Not held by a waiter, and the person who
  sends it is recorded as its authoriser.
- `order.settle` — settle a bill: number its invoice, take its payments, post what it consumed.
  Held by a waiter, because the person at the table takes the money.
- `order.void` — cancel an invoice issued in error, or issue a credit note and refund. Not held by
  a waiter: cancelling a paid cash bill is how the cash disappears.

No route exists without its permission, and `tests/test_generic_suites.py` walks every one.

**Every write returns the whole order, re-read after the commit.** The waiter's screen replaces its
copy with what the server now believes, version included, so the next change is made against the
right version without another request.

**There is no DELETE.** Taking a dish off is `POST .../lines/{line_id}/remove`, because what it does
depends on the kitchen: an unsent line is deleted, a sent one is cancelled with a reason. A method
name that sometimes deletes and sometimes does not would be a lie, and a DELETE carrying a body is
one many clients will not send.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import SessionDep, require_permission
from app.api.idempotency import begin_idempotent
from app.core.actor import Actor
from app.core.enums import OrderStatus
from app.core.permissions import PermissionCode
from app.models.orders import CreditNote, Invoice, Order, Payment
from app.repositories.base import DEFAULT_PAGE_SIZE
from app.schemas.orders import (
    CreditNoteLineResponse,
    CreditNoteRequest,
    CreditNoteResponse,
    FloorArea,
    FloorBusyRequest,
    FloorBusyResponse,
    FloorOrder,
    FloorResponse,
    FloorTable,
    InvoiceCancelRequest,
    InvoiceResponse,
    OrderCancelRequest,
    OrderChargeRequest,
    OrderChargeResponse,
    OrderCreateRequest,
    OrderDiscountRequest,
    OrderDiscountResponse,
    OrderLineAddRequest,
    OrderLineResponse,
    OrderLineUpdateRequest,
    OrderListResponse,
    OrderRemoveRequest,
    OrderResponse,
    OrderSettleRequest,
    OrderSplitRequest,
    OrderSummaryResponse,
    OrderVersionRequest,
    PaymentResponse,
)
from app.services.orders import OrderService
from app.services.reversals import CreditLineInput, RefundInput, ReversalService
from app.services.settlement import PaymentInput, Recipient, SettlementService

router = APIRouter(tags=["orders"])

_ViewDep = Annotated[Actor, Depends(require_permission(PermissionCode.ORDER_VIEW))]
_CreateDep = Annotated[Actor, Depends(require_permission(PermissionCode.ORDER_CREATE))]
_ModifyDep = Annotated[Actor, Depends(require_permission(PermissionCode.ORDER_MODIFY))]
_DiscountDep = Annotated[Actor, Depends(require_permission(PermissionCode.ORDER_DISCOUNT))]
_SettleDep = Annotated[Actor, Depends(require_permission(PermissionCode.ORDER_SETTLE))]
_VoidDep = Annotated[Actor, Depends(require_permission(PermissionCode.ORDER_VOID))]
_FloorDep = Annotated[Actor, Depends(require_permission(PermissionCode.FLOOR_MANAGE))]
_LimitDep = Annotated[int | None, Query(ge=1, le=100)]
_CursorDep = Annotated[uuid.UUID | None, Query()]

_SUMMARY_FIELDS = tuple(name for name in OrderSummaryResponse.model_fields if name != "table_ids")


def _service(session: SessionDep, actor: Actor) -> OrderService:
    """The scope comes from the *actor*, never from the request (`docs/security.md` A04)."""
    return OrderService(session, actor.scope)


def _table_ids(order: Order) -> list[uuid.UUID]:
    primary_first = sorted(order.tables, key=lambda link: (not link.is_primary, link.id))
    return [link.restaurant_table_id for link in primary_first]


def _summary(order: Order) -> OrderSummaryResponse:
    fields = {name: getattr(order, name) for name in _SUMMARY_FIELDS}
    return OrderSummaryResponse.model_validate(fields | {"table_ids": _table_ids(order)})


def _detail(order: Order, *, invoice_id: uuid.UUID | None = None) -> OrderResponse:
    fields = {name: getattr(order, name) for name in _SUMMARY_FIELDS}
    return OrderResponse.model_validate(
        fields
        | {
            "table_ids": _table_ids(order),
            "lines": [OrderLineResponse.model_validate(line) for line in order.lines],
            "discounts": [
                OrderDiscountResponse.model_validate(row)
                for row in sorted(order.discounts, key=lambda row: row.id)
            ],
            "charges": [
                OrderChargeResponse.model_validate(row)
                for row in sorted(order.charges, key=lambda row: row.id)
            ],
            "invoice_id": invoice_id,
        }
    )


def _next_cursor(items: list[Order], limit: int | None) -> uuid.UUID | None:
    """Only offer a cursor when the page was full, for the reason `api/v1/staff/setup.py` gives."""
    if len(items) < (limit or DEFAULT_PAGE_SIZE):
        return None
    return items[-1].id


# --------------------------------------------------------------------------- reading


@router.get("/orders", response_model=OrderListResponse)
async def list_orders(
    actor: _ViewDep,
    session: SessionDep,
    statuses: Annotated[list[OrderStatus] | None, Query(alias="status")] = None,
    business_date: Annotated[date | None, Query()] = None,
    limit: _LimitDep = None,
    cursor: _CursorDep = None,
) -> OrderListResponse:
    orders = await _service(session, actor).list_orders(
        statuses=statuses, business_date=business_date, limit=limit, after=cursor
    )
    return OrderListResponse(
        items=[_summary(order) for order in orders],
        next_cursor=_next_cursor(list(orders), limit),
    )


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(actor: _ViewDep, session: SessionDep, order_id: uuid.UUID) -> OrderResponse:
    service = _service(session, actor)
    order = await service.get(order_id)
    return _detail(order, invoice_id=await service.invoice_id_for(order))


# --------------------------------------------------------------------------- opening


@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    actor: _CreateDep, session: SessionDep, request: OrderCreateRequest
) -> OrderResponse:
    service = _service(session, actor)
    order_id = await service.create(
        actor,
        order_type=request.type,
        table_ids=request.table_ids,
        covers=request.covers,
        channel=request.channel,
        external_order_id=request.external_order_id,
    )
    await session.commit()
    return _detail(await service.get(order_id))


# --------------------------------------------------------------------------- lines


@router.post(
    "/orders/{order_id}/lines", response_model=OrderResponse, status_code=status.HTTP_201_CREATED
)
async def add_line(
    actor: _ModifyDep, session: SessionDep, order_id: uuid.UUID, request: OrderLineAddRequest
) -> OrderResponse:
    service = _service(session, actor)
    await service.add_line(
        order_id,
        version=request.version,
        variant_id=request.menu_item_variant_id,
        quantity=request.quantity,
        modifier_ids=request.modifier_ids,
        special_instructions=request.special_instructions,
    )
    await session.commit()
    return _detail(await service.get(order_id))


@router.patch("/orders/{order_id}/lines/{line_id}", response_model=OrderResponse)
async def update_line(
    actor: _ModifyDep,
    session: SessionDep,
    order_id: uuid.UUID,
    line_id: uuid.UUID,
    request: OrderLineUpdateRequest,
) -> OrderResponse:
    service = _service(session, actor)
    await service.update_line(
        order_id,
        line_id,
        version=request.version,
        changes=request.model_dump(exclude_unset=True, exclude={"version"}),
    )
    await session.commit()
    return _detail(await service.get(order_id))


@router.post("/orders/{order_id}/lines/{line_id}/remove", response_model=OrderResponse)
async def remove_line(
    actor: _ModifyDep,
    session: SessionDep,
    order_id: uuid.UUID,
    line_id: uuid.UUID,
    request: OrderRemoveRequest,
) -> OrderResponse:
    service = _service(session, actor)
    await service.remove_line(
        actor, order_id, line_id, version=request.version, reason=request.reason
    )
    await session.commit()
    return _detail(await service.get(order_id))


# --------------------------------------------------------------------------- the evening


@router.post("/orders/{order_id}/send", response_model=OrderResponse)
async def send_order(
    actor: _ModifyDep, session: SessionDep, order_id: uuid.UUID, request: OrderVersionRequest
) -> OrderResponse:
    service = _service(session, actor)
    await service.send(order_id, version=request.version)
    await session.commit()
    return _detail(await service.get(order_id))


@router.post("/orders/{order_id}/served", response_model=OrderResponse)
async def mark_served(
    actor: _ModifyDep, session: SessionDep, order_id: uuid.UUID, request: OrderVersionRequest
) -> OrderResponse:
    service = _service(session, actor)
    await service.mark_served(order_id, version=request.version)
    await session.commit()
    return _detail(await service.get(order_id))


@router.post("/orders/{order_id}/bill", response_model=OrderResponse)
async def request_bill(
    actor: _ModifyDep, session: SessionDep, order_id: uuid.UUID, request: OrderVersionRequest
) -> OrderResponse:
    service = _service(session, actor)
    await service.request_bill(order_id, version=request.version)
    await session.commit()
    return _detail(await service.get(order_id))


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    actor: _ModifyDep, session: SessionDep, order_id: uuid.UUID, request: OrderCancelRequest
) -> OrderResponse:
    service = _service(session, actor)
    await service.cancel(actor, order_id, version=request.version, reason=request.reason)
    await session.commit()
    return _detail(await service.get(order_id))


# --------------------------------------------------------------------------- discounts and charges


@router.post(
    "/orders/{order_id}/discounts",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_discount(
    actor: _DiscountDep, session: SessionDep, order_id: uuid.UUID, request: OrderDiscountRequest
) -> OrderResponse:
    service = _service(session, actor)
    await service.add_discount(
        actor,
        order_id,
        version=request.version,
        kind=request.type,
        rate=request.rate,
        flat_amount=request.flat_amount,
        line_id=request.order_line_id,
        reason=request.reason,
    )
    await session.commit()
    return _detail(await service.get(order_id))


@router.post("/orders/{order_id}/discounts/{discount_id}/remove", response_model=OrderResponse)
async def remove_discount(
    actor: _DiscountDep,
    session: SessionDep,
    order_id: uuid.UUID,
    discount_id: uuid.UUID,
    request: OrderRemoveRequest,
) -> OrderResponse:
    service = _service(session, actor)
    await service.remove_discount(
        actor, order_id, discount_id, version=request.version, reason=request.reason
    )
    await session.commit()
    return _detail(await service.get(order_id))


@router.post(
    "/orders/{order_id}/charges", response_model=OrderResponse, status_code=status.HTTP_201_CREATED
)
async def add_charge(
    actor: _ModifyDep, session: SessionDep, order_id: uuid.UUID, request: OrderChargeRequest
) -> OrderResponse:
    service = _service(session, actor)
    await service.add_charge(
        order_id,
        version=request.version,
        kind=request.type,
        amount=request.amount,
        tax_group_id=request.tax_group_id,
    )
    await session.commit()
    return _detail(await service.get(order_id))


@router.post("/orders/{order_id}/charges/{charge_id}/remove", response_model=OrderResponse)
async def remove_charge(
    actor: _ModifyDep,
    session: SessionDep,
    order_id: uuid.UUID,
    charge_id: uuid.UUID,
    request: OrderRemoveRequest,
) -> OrderResponse:
    service = _service(session, actor)
    await service.remove_charge(order_id, charge_id, version=request.version)
    await session.commit()
    return _detail(await service.get(order_id))


# --------------------------------------------------------------------------- splitting


@router.post(
    "/orders/{order_id}/split", response_model=OrderResponse, status_code=status.HTTP_201_CREATED
)
async def split_order(
    actor: _ModifyDep, session: SessionDep, order_id: uuid.UUID, request: OrderSplitRequest
) -> OrderResponse:
    """Returns the new order. The original's version has moved, so the screen re-reads it."""
    service = _service(session, actor)
    new_order_id = await service.split(
        actor, order_id, version=request.version, line_ids=request.line_ids
    )
    await session.commit()
    return _detail(await service.get(new_order_id))


# --------------------------------------------------------------------------- settlement
#
# Appended to app/api/v1/staff/orders.py by chunk G's patch.

_INVOICE_FIELDS = tuple(name for name in InvoiceResponse.model_fields if name != "payments")


def _invoice_response(invoice: Invoice, payments: Sequence[Payment]) -> InvoiceResponse:
    fields = {name: getattr(invoice, name) for name in _INVOICE_FIELDS}
    return InvoiceResponse.model_validate(
        fields | {"payments": [PaymentResponse.model_validate(row) for row in payments]}
    )


@router.post(
    "/orders/{order_id}/settle",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def settle_order(
    actor: _SettleDep,
    session: SessionDep,
    order_id: uuid.UUID,
    payload: OrderSettleRequest,
    request: Request,
) -> InvoiceResponse | JSONResponse:
    """Number the invoice, take the payments, post consumption and freeze the cost — atomically.

    Idempotent (ADR 0010): a Settle tapped twice on a stalled connection replays the first invoice
    rather than charging the table twice. The response is built before the commit, so the ledger
    stores exactly what is returned.
    """
    call = await begin_idempotent(request, session, actor)
    if call.replay is not None:
        return call.replay
    service = SettlementService(session, actor.scope)
    invoice_id = await service.settle(
        actor,
        order_id,
        version=payload.version,
        payments=[
            PaymentInput(
                method=payment.method,
                amount=payment.amount,
                tip_amount=payment.tip_amount,
                reference=payment.reference,
                paid_at=payment.paid_at,
            )
            for payment in payload.payments
        ],
        recipient=(
            None
            if payload.recipient is None
            else Recipient(
                name=payload.recipient.name,
                gstin=payload.recipient.gstin,
                address=payload.recipient.address,
            )
        ),
    )
    response = _invoice_response(*await service.get_invoice(invoice_id))
    await call.complete(status.HTTP_201_CREATED, response)
    await session.commit()
    return response


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    actor: _ViewDep, session: SessionDep, invoice_id: uuid.UUID
) -> InvoiceResponse:
    return _invoice_response(*await SettlementService(session, actor.scope).get_invoice(invoice_id))


# --------------------------------------------------------------------------- reversals
#
# Appended to app/api/v1/staff/orders.py by chunk H's patch, after chunk G's settlement routes.

_CREDIT_NOTE_FIELDS = tuple(
    name for name in CreditNoteResponse.model_fields if name not in {"lines", "refunds"}
)


def _credit_note_response(note: CreditNote, refunds: Sequence[Payment]) -> CreditNoteResponse:
    fields = {name: getattr(note, name) for name in _CREDIT_NOTE_FIELDS}
    return CreditNoteResponse.model_validate(
        fields
        | {
            "lines": [CreditNoteLineResponse.model_validate(line) for line in note.lines],
            "refunds": [PaymentResponse.model_validate(row) for row in refunds],
        }
    )


@router.post("/invoices/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    actor: _VoidDep,
    session: SessionDep,
    invoice_id: uuid.UUID,
    payload: InvoiceCancelRequest,
    request: Request,
) -> InvoiceResponse | JSONResponse:
    """Withdraw an invoice issued in error, on its business day. It keeps its number and moves no
    money; money going back is a credit note. Idempotent, like every void (ADR 0010)."""
    call = await begin_idempotent(request, session, actor)
    if call.replay is not None:
        return call.replay
    await ReversalService(session, actor.scope).cancel_invoice(
        actor, invoice_id, reason=payload.reason
    )
    response = _invoice_response(
        *await SettlementService(session, actor.scope).get_invoice(invoice_id)
    )
    await call.complete(status.HTTP_200_OK, response)
    await session.commit()
    return response


@router.post(
    "/invoices/{invoice_id}/credit-notes",
    response_model=CreditNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_credit_note(
    actor: _VoidDep,
    session: SessionDep,
    invoice_id: uuid.UUID,
    payload: CreditNoteRequest,
    request: Request,
) -> CreditNoteResponse | JSONResponse:
    """Reduce a settled bill by whole dishes, with any refund against it (CGST Act s.34)."""
    call = await begin_idempotent(request, session, actor)
    if call.replay is not None:
        return call.replay
    service = ReversalService(session, actor.scope)
    note_id = await service.issue_credit_note(
        actor,
        invoice_id,
        reason=payload.reason,
        lines=[
            CreditLineInput(order_line_id=line.order_line_id, quantity=line.quantity)
            for line in payload.lines
        ],
        refunds=[
            RefundInput(method=refund.method, amount=refund.amount, reference=refund.reference)
            for refund in payload.refunds
        ],
    )
    response = _credit_note_response(*await service.get_credit_note(note_id))
    await call.complete(status.HTTP_201_CREATED, response)
    await session.commit()
    return response


# --------------------------------------------------------------------------- the floor

_FLOOR_ORDER_FIELDS = tuple(FloorOrder.model_fields)


@router.get("/floor", response_model=FloorResponse)
async def get_floor(actor: _ViewDep, session: SessionDep) -> FloorResponse:
    """`/floor`, not `/orders/floor`: under `/orders` the word would be read as an order id."""
    floor = await _service(session, actor).floor()
    return FloorResponse(
        areas=[
            FloorArea(
                id=view.area.id,
                name=view.area.name,
                tables=[
                    FloorTable(
                        id=cell.table.id,
                        code=cell.table.code,
                        seats=cell.table.seats,
                        status=cell.status,
                        ready_at=cell.ready_at,
                        orders=[
                            FloorOrder.model_validate(
                                {name: getattr(order, name) for name in _FLOOR_ORDER_FIELDS}
                            )
                            for order in cell.orders
                        ],
                    )
                    for cell in view.tables
                ],
            )
            for view in floor.areas
        ],
        busy=floor.busy,
    )


@router.post("/floor/tables/{table_id}/ready", response_model=FloorTable)
async def mark_table_ready(
    actor: _CreateDep, session: SessionDep, table_id: uuid.UUID
) -> FloorTable:
    """Mark ready: a table being cleared is free for the next party (backlog-issues B2).

    Behind `order.create`, because whoever seats a table is whoever clears it. Refused while an
    order sits there, with the same code and words as the setup route.
    """
    table = await _service(session, actor).mark_ready(table_id)
    await session.commit()
    return FloorTable(
        id=table.id, code=table.code, seats=table.seats, status=table.status, orders=[]
    )


@router.post("/floor/busy", response_model=FloorBusyResponse)
async def set_busy_mode(
    actor: _FloorDep, session: SessionDep, request: FloorBusyRequest
) -> FloorBusyResponse:
    """Busy mode from the floor: a settled table is free at once instead of being cleared first.
    Owner and manager only; it switches itself off at the next business day."""
    busy = await _service(session, actor).set_busy(request.on)
    await session.commit()
    return FloorBusyResponse(busy=busy)
