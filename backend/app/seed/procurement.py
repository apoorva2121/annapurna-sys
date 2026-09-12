"""Suppliers, orders and deliveries, so the variance report has something to say on day one.

Four things are planted here and each is deliberate.

**Two suppliers, not one.** A variance report with a single supplier in it cannot be compared
against anything, and comparison is the whole point: "this one short-delivers and that one does
not" is the sentence an owner acts on.

**One order fully delivered, one part-delivered.** `partial` is the status that earns the enum — a
supplier delivering 30 of 50 sacks is the ordinary case — and a demo where every order is closed
shows none of the work a store manager actually does.

**One market purchase with no order behind it.** That is how a vegetable run really arrives, and
its null `purchase_order_id` is the channel marker M13 will split contracted supply from spot
buying on.

**One deliberate short delivery.** The same reasoning that put a deliberate negative in the M05
seed (`docs/seed-data.md`): a demo that requires the demonstrator to first create the problem is a
demo of an empty product. Somebody opening this app for the first time should find the report
already saying *"billed for 10 kg, 9 arrived"* — because that sentence is the product, and nobody
believes it until they see it about their own paneer.

Runs **after** `seed_inventory`, which is the one ordering constraint: both write the stock ledger,
and the inventory seeder refuses to run at all if any movement already exists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.procurement import Supplier
from app.models.stock import StockItem
from app.models.tenancy import Restaurant
from app.services.procurement import OrderLineInput, ProcurementService, ReceiptLineInput

logger = logging.getLogger(__name__)

_SUPPLIERS = (
    {
        "name": "Sharma Provisions",
        "contact_person": "Anil Sharma",
        "phone": "9820044001",
        "payment_terms_days": 15,
    },
    {
        "name": "Konkan Fresh Produce",
        "contact_person": "Meera Patil",
        "phone": "9820044002",
        "payment_terms_days": 7,
    },
)

# What each planted order is for, by stock item code. Kept to codes the M04 seed is known to
# create, so a missing item skips its line rather than failing the whole run.
_DRY_GOODS = ("BASMATI", "ATTA", "OIL")
_FRESH = ("ONION", "TOMATO", "PANEER")

# 20 kg, 10 kg, and the short delivery: 10 kg billed, 9 arrived.
_ORDERED = Decimal("20000")
_FRESH_ORDERED = Decimal("10000")
_FRESH_DELIVERED = Decimal("9000")


@dataclass(frozen=True, slots=True)
class ProcurementSummary:
    suppliers_created: int = 0
    orders_created: int = 0
    receipts_created: int = 0
    short_deliveries_planted: int = 0

    @property
    def created_nothing(self) -> bool:
        return not any(
            (
                self.suppliers_created,
                self.orders_created,
                self.receipts_created,
                self.short_deliveries_planted,
            )
        )


async def seed_procurement(session: AsyncSession) -> ProcurementSummary:
    """Idempotent: a restaurant that already has a supplier is left alone.

    The check is for any supplier rather than for a marker row, because a restaurant with suppliers
    in it is one somebody has started using, and re-seeding it would book deliveries that never
    happened into a real ledger.
    """
    restaurants = (await session.scalars(select(Restaurant))).all()
    totals = [0, 0, 0, 0]

    for restaurant in restaurants:
        existing = await session.scalar(
            select(func.count())
            .select_from(Supplier)
            .where(Supplier.restaurant_id == restaurant.id)
        )
        if existing:
            continue
        actor = await _actor_for(session, restaurant)
        if actor is None:
            continue
        counts = await _seed_one(session, restaurant, actor)
        totals = [running + added for running, added in zip(totals, counts, strict=True)]

    return ProcurementSummary(
        suppliers_created=totals[0],
        orders_created=totals[1],
        receipts_created=totals[2],
        short_deliveries_planted=totals[3],
    )


async def _actor_for(session: AsyncSession, restaurant: Restaurant) -> Actor | None:
    employee = (
        await session.scalars(
            select(Employee).where(Employee.organization_id == restaurant.organization_id)
        )
    ).first()
    if employee is None:
        return None
    return Actor(
        employee_id=employee.id,
        organization_id=restaurant.organization_id,
        restaurant_id=restaurant.id,
        full_name=employee.full_name,
        permissions=frozenset(),
        rank=100,
    )


async def _items_by_code(
    session: AsyncSession, restaurant: Restaurant, codes: tuple[str, ...]
) -> list[StockItem]:
    rows = await session.scalars(
        select(StockItem).where(
            StockItem.restaurant_id == restaurant.id,
            StockItem.code.in_(codes),
            StockItem.is_active.is_(True),
        )
    )
    return list(rows.all())


async def _seed_one(
    session: AsyncSession, restaurant: Restaurant, actor: Actor
) -> tuple[int, int, int, int]:
    """One restaurant's suppliers, orders and deliveries. Returns the four counts."""
    service = ProcurementService(
        session,
        TenantScope(organization_id=restaurant.organization_id, restaurant_id=restaurant.id),
    )
    suppliers = [
        await service.create_supplier(actor, **fields)  # type: ignore[arg-type]
        for fields in _SUPPLIERS
    ]
    now = datetime.now(UTC)

    dry = await _items_by_code(session, restaurant, _DRY_GOODS)
    fresh = await _items_by_code(session, restaurant, _FRESH)
    orders = 0
    receipts = 0
    short = 0

    if dry:
        # Fully delivered, so the demo has a closed order beside the open one.
        await _order_and_receive(
            service,
            actor,
            supplier_id=suppliers[0].id,
            items=dry,
            ordered=_ORDERED,
            delivered=_ORDERED,
            invoice="SP-1180",
            moment=now - timedelta(days=6),
        )
        orders += 1
        receipts += 1

    if fresh:
        # **The planted short delivery.** Billed for 10 kg of each, 9 arrived. The order stays
        # `partial`, and the variance report opens with a number instead of an empty table.
        await _order_and_receive(
            service,
            actor,
            supplier_id=suppliers[1].id,
            items=fresh,
            ordered=_FRESH_ORDERED,
            delivered=_FRESH_DELIVERED,
            invoice="KF-4471",
            moment=now - timedelta(days=2),
        )
        orders += 1
        receipts += 1
        short += 1

        # A market purchase with no order behind it — how a real vegetable run arrives.
        await service.receive(
            actor,
            supplier_id=suppliers[1].id,
            lines=[
                ReceiptLineInput(
                    stock_item_id=item.id,
                    quantity_invoiced=Decimal("3000"),
                    quantity_received=Decimal("3000"),
                    unit_price=Decimal(str(item.current_unit_cost)),
                )
                for item in fresh[:1]
            ],
            received_at=now - timedelta(days=1),
        )
        receipts += 1

    return len(suppliers), orders, receipts, short


async def _order_and_receive(
    service: ProcurementService,
    actor: Actor,
    *,
    supplier_id: object,
    items: list[StockItem],
    ordered: Decimal,
    delivered: Decimal,
    invoice: str,
    moment: datetime,
) -> None:
    """Raise it, send it, and book in what turned up. The three steps a store manager does."""
    order = await service.create_order(
        actor,
        supplier_id=supplier_id,  # type: ignore[arg-type]
        lines=[
            OrderLineInput(
                stock_item_id=item.id,
                quantity_ordered=ordered,
                unit_price=Decimal(str(item.current_unit_cost)),
            )
            for item in items
        ],
        expected_at=moment,
    )
    await service.send_order(actor, order.id)
    await service.receive(
        actor,
        purchase_order_id=order.id,
        invoice_number=invoice,
        lines=[
            ReceiptLineInput(
                stock_item_id=item.id,
                # Billed for what was ordered; delivered whatever actually turned up. Two columns,
                # which is the entire point of the module.
                quantity_invoiced=ordered,
                quantity_received=delivered,
            )
            for item in items
        ],
        received_at=moment,
    )
