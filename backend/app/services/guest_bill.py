"""What a guest may see of their own order, and the shape of what they may not.

One method, and it still earns a service rather than a route calling a repository. The layering rule
(G-8) exists so that "just this once" does not accumulate — and on this surface in particular, the
place where somebody will one day add "and also show them X" should be a service with a name, not a
handler that already knows how to query.

**Never cost, never margin, never a waiter's name, never another guest's anything.** That is
enforced structurally by `app/schemas/guest.py` and suite 5; this file simply has no access to those
fields, because `GuestOrderRepository` does not return them.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.guest_token import GuestScope
from app.models.orders import Order
from app.repositories.guest import BillLine, GuestOrderRepository


class GuestBillService:
    def __init__(self, session: AsyncSession, scope: GuestScope) -> None:
        self.session = session
        self.scope = scope
        self._orders = GuestOrderRepository(session, scope)

    async def bill(self, order_id: uuid.UUID) -> tuple[Order, list[BillLine]]:
        """The order's totals and its lines, in two queries and no N+1.

        A guest bill is read once per table per meal, on a phone, on a bad network: eleven round
        trips for eleven dishes is the difference between a screen that opens and one that does not.
        """
        found = await self._orders.bill(order_id)
        if found is None:
            # The dependency already proved this order is in scope, so this is a race rather than an
            # attack — the order was voided between opening the session and asking for the bill.
            raise NotFoundError("guest.order_not_found", "This bill is no longer available.")
        order, lines = found
        return order, list(lines)
