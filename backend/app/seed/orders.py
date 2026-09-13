"""Orders, a bill, a credit note and a till, so M07's screens open on a restaurant mid-service.

`docs/modules/M07-orders-spec.md` §Seed asks for enough to make the screens non-empty. Each thing
planted here is there for a screen:

- **An open order and a sent order** on two tables, so the waiter's first screen is a floor with
  something happening on it rather than a grid of "Free".
- **A settled order with its invoice, paid partly in cash and partly by UPI**, so today's bills list
  has a bill in it and a split payment is visible on the invoice.
- **One partial credit note** against that bill — a naan sent back, refunded by UPI — so the invoice
  screen shows the only way a settled bill ever changes.
- **A closed till with a small deliberate shortfall.** The same reasoning as the negative stock in
  the M05 seed and the short delivery in M06: a demo that makes the demonstrator create the problem
  is a demo of an empty product. The till is counted ₹50 under what it should hold, and the cash-up
  screen opens saying so.

Everything goes through the services, never around them, so the seeded bill is priced, taxed,
numbered and consumed exactly as a real one would be — a seed that wrote rows directly would demo
arithmetic the product never performed.

Runs **after** `seed_procurement`: settlement writes the stock ledger, and the inventory seeder
refuses to run once any movement exists. Idempotent: a restaurant that already has an order is left
alone, because an order in it is one somebody took. The volume — 120 days of history — is M15's.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import OrderChannel, OrderType, PaymentMethod
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.menu import MenuItem, MenuItemVariant
from app.models.orders import Order
from app.models.setup import RestaurantTable
from app.models.tenancy import Restaurant
from app.services.cash import CashService
from app.services.orders import OrderService
from app.services.reversals import CreditLineInput, RefundInput, ReversalService
from app.services.settlement import PaymentInput, SettlementService

logger = logging.getLogger(__name__)

# Dishes by code, all ones `seed/menu.yaml` really creates and none with a required choice. A code
# that is missing skips its line rather than failing the run.
_OPEN_DISHES = ("DAL_MAKHANI", "BUTTER_NAAN")
_SENT_DISHES = ("BUTTER_CHICKEN", "JEERA_RICE")
_SETTLED_DISHES = ("PANEER_TIKKA", "DAL_MAKHANI", "BUTTER_NAAN")

_OPENING_FLOAT = Decimal("2000.00")
_PAYOUT = Decimal("300.00")
# **The planted shortfall.** The till is counted this much under what it should hold.
_SHORTFALL = Decimal("50.00")
_DENOMINATIONS = tuple(Decimal(d) for d in ("500", "200", "100", "50", "20", "10", "5", "2", "1"))
_RUPEE = Decimal("1")


@dataclass(frozen=True, slots=True)
class OrdersSummary:
    orders_created: int = 0
    invoices_issued: int = 0
    credit_notes_issued: int = 0
    short_tills_planted: int = 0

    @property
    def created_nothing(self) -> bool:
        return not any(
            (
                self.orders_created,
                self.invoices_issued,
                self.credit_notes_issued,
                self.short_tills_planted,
            )
        )


async def seed_orders(session: AsyncSession) -> OrdersSummary:
    """Idempotent: a restaurant that already has an order is left alone."""
    restaurants = (await session.scalars(select(Restaurant))).all()
    totals = [0, 0, 0, 0]

    for restaurant in restaurants:
        existing = await session.scalar(
            select(func.count()).select_from(Order).where(Order.restaurant_id == restaurant.id)
        )
        if existing:
            continue
        actor = await _actor_for(session, restaurant)
        if actor is None:
            continue
        counts = await _seed_one(session, restaurant, actor)
        totals = [running + added for running, added in zip(totals, counts, strict=True)]

    return OrdersSummary(
        orders_created=totals[0],
        invoices_issued=totals[1],
        credit_notes_issued=totals[2],
        short_tills_planted=totals[3],
    )


async def _actor_for(session: AsyncSession, restaurant: Restaurant) -> Actor | None:
    """Somebody in the organization to record the work against, as the procurement seed does."""
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


async def _seed_one(
    session: AsyncSession, restaurant: Restaurant, actor: Actor
) -> tuple[int, int, int, int]:
    """One restaurant's orders, bill, credit note and till. Returns the four counts."""
    scope = TenantScope(organization_id=restaurant.organization_id, restaurant_id=restaurant.id)
    orders = OrderService(session, scope)
    tables = await _tables(session, restaurant)
    if len(tables) < 3:
        return 0, 0, 0, 0
    created = 0

    if await _order(orders, actor, tables[0], await _variants(session, restaurant, _OPEN_DISHES)):
        created += 1
    sent_id = await _order(
        orders, actor, tables[1], await _variants(session, restaurant, _SENT_DISHES)
    )
    if sent_id is not None:
        await orders.send(sent_id, version=await _version(orders, sent_id))
        created += 1

    if restaurant.gst_scheme == "regular" and not restaurant.gstin:
        # Settlement would be refused, and rightly (Rule 46). No bill, so no till to reconcile.
        return created, 0, 0, 0
    settled_id = await _order(
        orders, actor, tables[2], await _variants(session, restaurant, _SETTLED_DISHES)
    )
    if settled_id is None:
        return created, 0, 0, 0
    created += 1
    for step in (orders.send, orders.mark_served, orders.request_bill):
        await step(settled_id, version=await _version(orders, settled_id))

    cash = CashService(session, scope)
    till_id = await cash.open(actor, opening_float=_OPENING_FLOAT)

    # Whole rupees in cash and the paise by UPI: "we'll pay separately", and a till that can be
    # counted in notes.
    bill = await orders.get(settled_id)
    total = Decimal(str(bill.grand_total))
    in_cash = total.quantize(_RUPEE, rounding=ROUND_DOWN)
    payments = [PaymentInput(method=PaymentMethod.CASH, amount=in_cash)]
    if total > in_cash:
        payments.append(PaymentInput(method=PaymentMethod.UPI, amount=total - in_cash))
    invoice_id = await SettlementService(session, scope).settle(
        actor, settled_id, version=bill.version, payments=payments
    )

    # A naan sent back cold: credited whole and refunded by UPI, so the till is not touched.
    settled = await orders.get(settled_id)
    naan = max(settled.lines, key=lambda line: line.seq)
    await ReversalService(session, scope).issue_credit_note(
        actor,
        invoice_id,
        reason="Sent back: served cold",
        lines=[CreditLineInput(order_line_id=naan.id, quantity=naan.quantity)],
        refunds=[RefundInput(method=PaymentMethod.UPI, amount=Decimal(str(naan.line_total)))],
    )

    await cash.payout(actor, till_id, amount=_PAYOUT, reason="Ice and lemons from the market")
    position, _, _ = await cash.detail(till_id)
    await cash.close(actor, till_id, counts=_notes_for(position.expected - _SHORTFALL))
    return created, 1, 1, 1


async def _tables(session: AsyncSession, restaurant: Restaurant) -> list[RestaurantTable]:
    rows = await session.scalars(
        select(RestaurantTable)
        .where(
            RestaurantTable.restaurant_id == restaurant.id,
            RestaurantTable.is_active.is_(True),
        )
        .order_by(RestaurantTable.code)
    )
    return list(rows.all())


async def _variants(
    session: AsyncSession, restaurant: Restaurant, codes: tuple[str, ...]
) -> list[uuid.UUID]:
    """The first active variant of each dish, in the order given. A missing dish is skipped."""
    rows = await session.execute(
        select(MenuItem.code, MenuItemVariant.id)
        .join(MenuItemVariant, MenuItemVariant.menu_item_id == MenuItem.id)
        .where(
            MenuItem.restaurant_id == restaurant.id,
            MenuItem.code.in_(codes),
            MenuItem.is_active.is_(True),
            MenuItemVariant.is_active.is_(True),
        )
        .order_by(MenuItemVariant.seq)
    )
    first: dict[str, uuid.UUID] = {}
    for code, variant_id in rows.tuples().all():
        first.setdefault(code, variant_id)
    return [first[code] for code in codes if code in first]


async def _order(
    service: OrderService, actor: Actor, table: RestaurantTable, variants: list[uuid.UUID]
) -> uuid.UUID | None:
    """A dine-in order on one table with one of each dish. None when no dish could be found."""
    if not variants:
        return None
    order_id = await service.create(
        actor,
        order_type=OrderType.DINE_IN,
        table_ids=[table.id],
        covers=2,
        channel=OrderChannel.POS,
        external_order_id=None,
    )
    for variant_id in variants:
        await service.add_line(
            order_id,
            version=await _version(service, order_id),
            variant_id=variant_id,
            quantity=1,
            modifier_ids=[],
            special_instructions=None,
        )
    return order_id


async def _version(service: OrderService, order_id: uuid.UUID) -> int:
    return (await service.get(order_id)).version


def _notes_for(amount: Decimal) -> list[tuple[Decimal, int]]:
    """Whole rupees as the fewest notes and coins, largest first."""
    counts: list[tuple[Decimal, int]] = []
    remaining = amount
    for denomination in _DENOMINATIONS:
        quantity = int(remaining // denomination)
        if quantity:
            counts.append((denomination, quantity))
            remaining -= denomination * quantity
    return counts
