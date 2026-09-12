"""Suppliers, purchase orders and the delivery door. Every handler is authorise-call-shape.

Three permissions, and one of them is borrowed on purpose.

- `supplier.view` — read suppliers, orders, deliveries and the variance report. Commercially
  sensitive: it is who you buy from and what you pay.
- `supplier.manage` — add or change a supplier. Not the kitchen's: inventing a supplier is how
  purchases get laundered.
- `purchase.manage` — raise, send and cancel orders.
- **`stock.receive` — post a delivery**, and that is the interesting line. Receiving writes the
  stock ledger, so it keeps the ledger's permission rather than gaining a fourth of its own. The
  P1 design in `seed/organization.yaml` then gives separation of duties for free: the accountant
  holds `purchase.manage` and not `stock.receive`, so the person who reconciles invoices may raise
  an order and may never sign for one; the chef holds neither.

**There is no PATCH and no DELETE on a goods receipt.** It is append-only — the database refuses
both — so a route implying otherwise would advertise something the server rejects. A correction is
a `stock.adjust` movement referencing the receipt.

**Every write route commits; the service only flushes.** This codebase's convention, and the M05
build log records what happens when it is forgotten: every write returns `201` with a populated
body and then vanishes when the session closes. No unit test can see it — inside one transaction
the write is visible to the code that made it — which is why the endpoint tests exist.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.enums import PurchaseOrderStatus
from app.core.permissions import PermissionCode
from app.core.tenancy import TenantScope
from app.models.procurement import GoodsReceipt
from app.schemas.procurement import (
    AdHocReceiptRequest,
    OrderCancelRequest,
    OrderCreateRequest,
    OrderListResponse,
    OrderResponse,
    OrderUpdateRequest,
    PostedLineResponse,
    PostedReceiptResponse,
    ReceiptListResponse,
    ReceiptResponse,
    ReceiveAgainstOrderRequest,
    SupplierCreateRequest,
    SupplierListResponse,
    SupplierResponse,
    SupplierUpdateRequest,
    SupplierVarianceResponse,
    VarianceRowResponse,
)
from app.services.procurement import (
    OrderLineInput,
    ProcurementService,
    ReceiptLineInput,
    ReceiptResult,
    SupplierVariance,
)

router = APIRouter(tags=["procurement"])

_ViewDep = Annotated[Actor, Depends(require_permission(PermissionCode.SUPPLIER_VIEW))]
_SupplierDep = Annotated[Actor, Depends(require_permission(PermissionCode.SUPPLIER_MANAGE))]
_PurchaseDep = Annotated[Actor, Depends(require_permission(PermissionCode.PURCHASE_MANAGE))]
_ReceiveDep = Annotated[Actor, Depends(require_permission(PermissionCode.STOCK_RECEIVE))]

# A quarter, which is the window the report's headline sentence is about
# ("...across 31 deliveries this quarter").
_DEFAULT_VARIANCE_DAYS = 90


def _service(session: SessionDep, actor: Actor) -> ProcurementService:
    """The scope comes from the *actor*, never from the request body (`docs/security.md` A04)."""
    return ProcurementService(
        session,
        TenantScope(organization_id=actor.organization_id, restaurant_id=actor.restaurant_id),
    )


def _order_lines(payload: OrderCreateRequest | OrderUpdateRequest) -> list[OrderLineInput]:
    return [
        OrderLineInput(
            stock_item_id=line.stock_item_id,
            quantity_ordered=line.quantity_ordered,
            unit_price=line.unit_price,
        )
        for line in (payload.lines or [])
    ]


def _receipt_lines(payload: ReceiveAgainstOrderRequest) -> list[ReceiptLineInput]:
    return [
        ReceiptLineInput(
            stock_item_id=line.stock_item_id,
            quantity_invoiced=line.quantity_invoiced,
            quantity_received=line.quantity_received,
            quantity_rejected=line.quantity_rejected,
            unit_price=line.unit_price,
            rejection_reason=line.rejection_reason,
        )
        for line in payload.lines
    ]


def _posted(result: ReceiptResult, receipt: GoodsReceipt) -> PostedReceiptResponse:
    """Shape the confirmation panel. Every derived figure comes off the service's own dataclass —
    nothing is recomputed here, so the API and the ledger cannot disagree about a variance.

    The receipt is passed in, re-read with its lines eagerly loaded: the service returns an id
    rather than an instance, because `GoodsReceipt.lines` is `lazy="raise"` and the commit in
    between expires anything it did hand out.
    """
    return PostedReceiptResponse(
        receipt=ReceiptResponse.model_validate(receipt),
        lines=[
            PostedLineResponse(
                stock_item_id=line.stock_item_id,
                ordered=line.ordered,
                invoiced=line.invoiced,
                received=line.received,
                rejected=line.rejected,
                accepted=line.accepted,
                short_delivery=line.short_delivery,
                order_shortfall=line.order_shortfall,
                unit_price=line.unit_price,
                landed_unit_cost=line.landed_unit_cost,
                short_delivery_value=line.short_delivery_value,
                accepted_value=line.accepted_value,
            )
            for line in result.lines
        ],
        invoice_line_total=result.invoice_line_total,
        short_delivery_value=result.short_delivery_value,
        accepted_value=result.accepted_value,
    )


def _variance(report: SupplierVariance) -> SupplierVarianceResponse:
    return SupplierVarianceResponse(
        supplier_id=report.supplier_id,
        supplier_name=report.supplier_name,
        start=report.start,
        end=report.end,
        deliveries=report.deliveries,
        invoiced=report.invoiced,
        received=report.received,
        short_delivery_value=report.short_delivery_value,
        rows=[VarianceRowResponse.model_validate(row) for row in report.rows],
    )


# ---------------------------------------------------------------- suppliers


@router.get("/suppliers", response_model=SupplierListResponse)
async def list_suppliers(
    session: SessionDep,
    actor: _ViewDep,
    include_inactive: Annotated[bool, Query()] = True,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> SupplierListResponse:
    rows = await _service(session, actor).list_suppliers(
        include_inactive=include_inactive, limit=limit
    )
    return SupplierListResponse(suppliers=[SupplierResponse.model_validate(row) for row in rows])


@router.post("/suppliers", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    payload: SupplierCreateRequest, session: SessionDep, actor: _SupplierDep
) -> SupplierResponse:
    supplier = await _service(session, actor).create_supplier(
        actor, **payload.model_dump(exclude_unset=False)
    )
    await session.commit()
    return SupplierResponse.model_validate(supplier)


@router.get("/suppliers/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(
    supplier_id: uuid.UUID, session: SessionDep, actor: _ViewDep
) -> SupplierResponse:
    supplier = await _service(session, actor).get_supplier(supplier_id)
    return SupplierResponse.model_validate(supplier)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: uuid.UUID,
    payload: SupplierUpdateRequest,
    session: SessionDep,
    actor: _SupplierDep,
) -> SupplierResponse:
    supplier = await _service(session, actor).update_supplier(
        actor, supplier_id, payload.model_dump(exclude_unset=True)
    )
    await session.commit()
    return SupplierResponse.model_validate(supplier)


@router.get("/suppliers/{supplier_id}/variance", response_model=SupplierVarianceResponse)
async def supplier_variance(
    supplier_id: uuid.UUID,
    session: SessionDep,
    actor: _ViewDep,
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
) -> SupplierVarianceResponse:
    """*"Supplier A short-delivered 4.2% across 31 deliveries this quarter — ₹18,400."*

    The window defaults to the last 90 days in the **restaurant's** business days, not the
    server's calendar — a delivery booked at 01:30 belongs to the previous business day, and a
    report that disagreed with the ledger about which day that was would be quietly wrong at both
    ends of every window.
    """
    service = _service(session, actor)
    resolved_end = end or await service.inventory.business_date_now()
    resolved_start = start or resolved_end - timedelta(days=_DEFAULT_VARIANCE_DAYS)
    return _variance(
        await service.supplier_variance(supplier_id, start=resolved_start, end=resolved_end)
    )


# ---------------------------------------------------------------- purchase orders


@router.get("/purchase-orders", response_model=OrderListResponse)
async def list_orders(
    session: SessionDep,
    actor: _ViewDep,
    order_status: Annotated[PurchaseOrderStatus | None, Query(alias="status")] = None,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> OrderListResponse:
    rows = await _service(session, actor).list_orders(
        status=order_status, supplier_id=supplier_id, limit=limit
    )
    return OrderListResponse(orders=[OrderResponse.model_validate(row) for row in rows])


@router.post("/purchase-orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreateRequest, session: SessionDep, actor: _PurchaseDep
) -> OrderResponse:
    service = _service(session, actor)
    order = await service.create_order(
        actor,
        supplier_id=payload.supplier_id,
        lines=_order_lines(payload),
        expected_at=payload.expected_at,
    )
    await session.commit()
    return OrderResponse.model_validate(await service.get_order(order.id))


@router.get("/purchase-orders/{po_id}", response_model=OrderResponse)
async def get_order(po_id: uuid.UUID, session: SessionDep, actor: _ViewDep) -> OrderResponse:
    return OrderResponse.model_validate(await _service(session, actor).get_order(po_id))


@router.patch("/purchase-orders/{po_id}", response_model=OrderResponse)
async def update_order(
    po_id: uuid.UUID, payload: OrderUpdateRequest, session: SessionDep, actor: _PurchaseDep
) -> OrderResponse:
    service = _service(session, actor)
    await service.update_order(
        actor,
        po_id,
        lines=_order_lines(payload) if payload.lines is not None else None,
        expected_at=payload.expected_at,
        set_expected="expected_at" in payload.model_fields_set,
    )
    await session.commit()
    return OrderResponse.model_validate(await service.get_order(po_id))


@router.post("/purchase-orders/{po_id}/send", response_model=OrderResponse)
async def send_order(po_id: uuid.UUID, session: SessionDep, actor: _PurchaseDep) -> OrderResponse:
    service = _service(session, actor)
    await service.send_order(actor, po_id)
    await session.commit()
    return OrderResponse.model_validate(await service.get_order(po_id))


@router.post("/purchase-orders/{po_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    po_id: uuid.UUID, payload: OrderCancelRequest, session: SessionDep, actor: _PurchaseDep
) -> OrderResponse:
    service = _service(session, actor)
    await service.cancel_order(actor, po_id, reason=payload.reason)
    await session.commit()
    return OrderResponse.model_validate(await service.get_order(po_id))


# ---------------------------------------------------------------- receiving


@router.post(
    "/purchase-orders/{po_id}/receive",
    response_model=PostedReceiptResponse,
    status_code=status.HTTP_201_CREATED,
)
async def receive_against_order(
    po_id: uuid.UUID,
    payload: ReceiveAgainstOrderRequest,
    session: SessionDep,
    actor: _ReceiveDep,
) -> PostedReceiptResponse:
    """The money screen's endpoint. A partial delivery leaves the order partially open."""
    service = _service(session, actor)
    result = await service.receive(
        actor,
        purchase_order_id=po_id,
        lines=_receipt_lines(payload),
        invoice_number=payload.invoice_number,
        invoice_amount=payload.invoice_amount,
        tax_amount=payload.tax_amount,
        received_at=payload.received_at,
    )
    await session.commit()
    return _posted(result, await service.get_receipt(result.receipt_id))


@router.post(
    "/goods-receipts", response_model=PostedReceiptResponse, status_code=status.HTTP_201_CREATED
)
async def receive_ad_hoc(
    payload: AdHocReceiptRequest, session: SessionDep, actor: _ReceiveDep
) -> PostedReceiptResponse:
    """A market purchase with no order behind it, which is how a real vegetable run arrives.

    `docs/modules.md` M06 asks for this explicitly. The receipt's null `purchase_order_id` is the
    channel marker: bought at market prices rather than contracted ones, which is a different cost
    story and one M13 will want to split.
    """
    service = _service(session, actor)
    result = await service.receive(
        actor,
        supplier_id=payload.supplier_id,
        lines=_receipt_lines(payload),
        invoice_number=payload.invoice_number,
        invoice_amount=payload.invoice_amount,
        tax_amount=payload.tax_amount,
        received_at=payload.received_at,
    )
    await session.commit()
    return _posted(result, await service.get_receipt(result.receipt_id))


@router.get("/goods-receipts", response_model=ReceiptListResponse)
async def list_receipts(
    session: SessionDep,
    actor: _ViewDep,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> ReceiptListResponse:
    rows = await _service(session, actor).list_receipts(supplier_id=supplier_id, limit=limit)
    return ReceiptListResponse(receipts=[ReceiptResponse.model_validate(row) for row in rows])


@router.get("/goods-receipts/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    receipt_id: uuid.UUID, session: SessionDep, actor: _ViewDep
) -> ReceiptResponse:
    return ReceiptResponse.model_validate(await _service(session, actor).get_receipt(receipt_id))
