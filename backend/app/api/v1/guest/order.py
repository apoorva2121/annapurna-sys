"""The bill for the order this token names, and no other.

**Order scope only.** A table sticker does not open a bill, which is the whole point of there being
two codes: a photographed sticker is worth the menu, and reading what table four is eating tonight
needs the QR printed on table four's bill.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.guest_deps import GuestSessionDep, OrderScopeDep
from app.core.rate_limit import rate_limit
from app.schemas.guest import GuestBillLine, GuestBillResponse
from app.services.guest_bill import GuestBillService

router = APIRouter()


@router.get("/order", response_model=GuestBillResponse, dependencies=[Depends(rate_limit("read"))])
async def guest_bill(session: GuestSessionDep, scope: OrderScopeDep) -> GuestBillResponse:
    """Every figure here is the server's, rendered.

    A guest total that disagreed with the printed one by a paisa is an argument at a table, so
    nothing on this path adds two numbers together (CLAUDE.md invariant 3).
    """
    order, lines = await GuestBillService(session, scope).bill(scope.subject_id)
    return GuestBillResponse(
        lines=[
            GuestBillLine(name=line.name, quantity=line.quantity, amount=line.amount)
            for line in lines
        ],
        subtotal=order.subtotal,
        discount_total=order.discount_total,
        charge_total=order.charge_total,
        tax_total=order.tax_total,
        round_off=order.round_off,
        grand_total=order.grand_total,
        is_settled=order.settled_at is not None,
    )
