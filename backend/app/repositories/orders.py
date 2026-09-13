"""Queries over orders and what they cost. Business rules live in the service, not here.

Four of these carry weight.

**`lock` takes the order row, and every change goes through it.** ADR 0010 chose optimistic
locking for *people*: a stale version is a 409. But two requests carrying the same, current
version still have to be serialised, or both pass the version check and the second reprice
overwrites the first. The lock is held only for one request, so a waiter who walks away blocks
nobody (the ADR's reason for rejecting pessimistic locking on orders).

**`next_order_number` takes a transaction-scoped advisory lock** per restaurant and business day —
the arrangement M06 proved for purchase-order numbers under five-way contention. Two waiters opening
tables in the same second must not both be "order 42".

**`live_order_on_table` is the question the table-status endpoint asks** before letting a table be
marked free: is anybody still eating here?

**`PricingRepository.rate_on` never locks.** `TaxRateRepository.live_on` takes `FOR UPDATE` because
its caller may be about to insert a successor rate; pricing a dish is not, and a lock there would
serialise every order in the restaurant behind whichever tab is adding a line.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Integer, Select, cast, func, literal, or_, select, update
from sqlalchemy.orm import selectinload

from app.core.enums import CashSessionStatus, OrderStatus
from app.models.menu import (
    MenuItem,
    MenuItemModifierGroup,
    MenuItemVariant,
    Modifier,
    ModifierGroup,
)
from app.models.orders import (
    CashSession,
    Invoice,
    Order,
    OrderDiscount,
    OrderLine,
    OrderTable,
    Payment,
)
from app.models.setup import TaxGroup, TaxRate
from app.repositories.base import RestaurantScopedRepository, ScopedRepository, page_size

# A namespace for the two-int advisory lock, distinct from M06's 60_001, so an order-number lock can
# never collide with a purchase-order-number lock on the same restaurant.
_ORDER_NUMBER_LOCK_NAMESPACE = 70_001

LIVE_ORDER_STATUSES = (OrderStatus.OPEN, OrderStatus.SENT, OrderStatus.SERVED)


class OrderRepository(RestaurantScopedRepository[Order]):
    model = Order

    def _detailed(self) -> Select[tuple[Order]]:
        return self.scoped().options(
            selectinload(Order.lines).selectinload(OrderLine.modifiers),
            selectinload(Order.discounts),
            selectinload(Order.charges),
            selectinload(Order.tables),
        )

    async def get_detail(self, order_id: uuid.UUID, *, refresh: bool = False) -> Order | None:
        """The order with everything a bill reads, in five statements whatever its size.

        `refresh` re-reads rows already in the session. A change flushes and then reprices from what
        the database now holds; without it, the identity map would hand back the collections as they
        were before the change, and a deleted line would still be on the bill.
        """
        query = self._detailed().where(Order.id == order_id)
        if refresh:
            query = query.execution_options(populate_existing=True)
        return (await self.session.scalars(query)).first()

    async def lock(self, order_id: uuid.UUID) -> bool:
        """Lock the order row for the rest of the transaction. False when there is no such order."""
        locked = await self.session.scalar(
            self.scoped().where(Order.id == order_id).with_for_update()
        )
        return locked is not None

    async def list_page(
        self,
        *,
        statuses: Sequence[str] | None = None,
        business_date: date | None = None,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[Order]:
        """Newest first. Ids are UUIDv7 and so time-ordered, which makes the id the cursor.

        Tables are loaded in one extra statement for the page, never one per order.
        """
        query = self.scoped().options(selectinload(Order.tables))
        if statuses:
            query = query.where(Order.status.in_(statuses))
        if business_date is not None:
            query = query.where(Order.business_date == business_date)
        if after is not None:
            query = query.where(Order.id < after)
        query = query.order_by(Order.id.desc()).limit(page_size(limit))
        return (await self.session.scalars(query)).all()

    async def next_order_number(self, business_date: date) -> str:
        """The next number for this business day, allocated under a lock held to commit.

        Counting restarts every business day because "table 6, order 42" is what a waiter calls
        out, and a number that never resets is not something anyone calls out.
        """
        key = f"{self.scope.restaurant_id}:{business_date.isoformat()}"
        await self.session.execute(
            select(
                func.pg_advisory_xact_lock(
                    literal(_ORDER_NUMBER_LOCK_NAMESPACE), func.hashtext(key)
                )
            )
        )
        highest = await self.session.scalar(
            self.scoped()
            .with_only_columns(func.max(cast(Order.order_number, Integer)))
            .where(Order.business_date == business_date)
        )
        return str((highest or 0) + 1)

    async def move_lines(self, line_ids: Sequence[uuid.UUID], to_order_id: uuid.UUID) -> None:
        """Move lines, and the discounts aimed at them, to another order of this restaurant.

        Both statements are scoped, and migration 0019 refuses the move if either order is final.
        """
        await self.session.execute(
            update(OrderLine)
            .where(
                OrderLine.id.in_(line_ids),
                OrderLine.restaurant_id == self.scope.restaurant_id,
            )
            .values(order_id=to_order_id)
        )
        await self.session.execute(
            update(OrderDiscount)
            .where(
                OrderDiscount.order_line_id.in_(line_ids),
                OrderDiscount.restaurant_id == self.scope.restaurant_id,
            )
            .values(order_id=to_order_id)
        )

    async def live_order_on_table(
        self, table_id: uuid.UUID, *, excluding: uuid.UUID | None = None
    ) -> Order | None:
        query = (
            self.scoped()
            .join(OrderTable, OrderTable.order_id == Order.id)
            .where(
                OrderTable.restaurant_table_id == table_id,
                Order.status.in_(LIVE_ORDER_STATUSES),
            )
        )
        if excluding is not None:
            query = query.where(Order.id != excluding)
        return (await self.session.scalars(query.limit(1))).first()


@dataclass(frozen=True, slots=True)
class SaleableVariant:
    variant: MenuItemVariant
    item: MenuItem


@dataclass(frozen=True, slots=True)
class RateOnDate:
    regime: str
    rate: Decimal
    inclusive: bool


class PricingRepository(ScopedRepository[MenuItemVariant]):
    """What the menu says a dish costs and how it is taxed. Read here; never taken from a client.

    Scoped by hand on every table it touches, because it joins across four of them and the base
    class's `scoped()` covers only one.
    """

    model = MenuItemVariant

    async def saleable_variant(self, variant_id: uuid.UUID) -> SaleableVariant | None:
        row = (
            await self.session.execute(
                select(MenuItemVariant, MenuItem)
                .join(MenuItem, MenuItem.id == MenuItemVariant.menu_item_id)
                .where(
                    MenuItemVariant.id == variant_id,
                    MenuItemVariant.restaurant_id == self.scope.restaurant_id,
                    MenuItem.restaurant_id == self.scope.restaurant_id,
                )
            )
        ).first()
        return None if row is None else SaleableVariant(variant=row[0], item=row[1])

    async def groups_for_item(self, item_id: uuid.UUID) -> Sequence[ModifierGroup]:
        """The active questions asked about this dish, with their selection limits."""
        result = await self.session.scalars(
            select(ModifierGroup)
            .join(
                MenuItemModifierGroup,
                MenuItemModifierGroup.modifier_group_id == ModifierGroup.id,
            )
            .where(
                MenuItemModifierGroup.menu_item_id == item_id,
                ModifierGroup.restaurant_id == self.scope.restaurant_id,
                ModifierGroup.is_active.is_(True),
            )
        )
        return result.all()

    async def modifiers_for_item(
        self, item_id: uuid.UUID
    ) -> Sequence[tuple[Modifier, ModifierGroup]]:
        """Every active answer those questions offer."""
        rows = await self.session.execute(
            select(Modifier, ModifierGroup)
            .join(ModifierGroup, ModifierGroup.id == Modifier.modifier_group_id)
            .join(
                MenuItemModifierGroup,
                MenuItemModifierGroup.modifier_group_id == ModifierGroup.id,
            )
            .where(
                MenuItemModifierGroup.menu_item_id == item_id,
                Modifier.restaurant_id == self.scope.restaurant_id,
                ModifierGroup.restaurant_id == self.scope.restaurant_id,
                Modifier.is_active.is_(True),
                ModifierGroup.is_active.is_(True),
            )
        )
        return [(modifier, group) for modifier, group in rows.tuples().all()]

    async def rate_on(self, tax_group_id: uuid.UUID, on: date) -> RateOnDate | None:
        """The group's regime and the rate whose period covers `on`. Never locks: see the module."""
        row = (
            await self.session.execute(
                select(TaxGroup.regime, TaxRate.rate, TaxRate.is_inclusive)
                .join(TaxRate, TaxRate.tax_group_id == TaxGroup.id)
                .where(
                    TaxGroup.id == tax_group_id,
                    TaxGroup.restaurant_id == self.scope.restaurant_id,
                    TaxRate.restaurant_id == self.scope.restaurant_id,
                    TaxRate.effective_from <= on,
                    or_(TaxRate.effective_to.is_(None), TaxRate.effective_to >= on),
                )
                .order_by(TaxRate.effective_from.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            return None
        regime, rate, inclusive = row
        rate_value = rate if isinstance(rate, Decimal) else Decimal(str(rate))
        return RateOnDate(regime=str(regime), rate=rate_value, inclusive=bool(inclusive))


# ----------------------------------------------------------------------------------------- invoices
#
# Appended to app/repositories/orders.py by chunk G's patch.

# Distinct from the order-number (70_001) and purchase-order (60_001) namespaces, so an invoice
# lock can never collide with either on the same restaurant.
_INVOICE_NUMBER_LOCK_NAMESPACE = 80_001


class InvoiceRepository(RestaurantScopedRepository[Invoice]):
    model = Invoice

    async def next_sequence(self, financial_year: str) -> int:
        """The next consecutive number in this restaurant's series for the year, under a lock held
        to commit (CGST Rules, Rule 46(b); spec decision 1).

        **Gapless because the lock and the insert share a transaction.** A settlement that fails
        after allocating a number rolls back its invoice row, and the next settlement — waiting on
        this lock — reads the same maximum and takes the same number. A sequence object would hand
        out the number and keep it, leaving exactly the gap an assessment asks about.
        """
        key = f"{self.scope.restaurant_id}:{financial_year}"
        await self.session.execute(
            select(
                func.pg_advisory_xact_lock(
                    literal(_INVOICE_NUMBER_LOCK_NAMESPACE), func.hashtext(key)
                )
            )
        )
        highest = await self.session.scalar(
            self.scoped()
            .with_only_columns(func.max(Invoice.sequence))
            .where(Invoice.financial_year == financial_year)
        )
        return int(highest or 0) + 1

    async def for_order(self, order_id: uuid.UUID) -> Invoice | None:
        return (
            await self.session.scalars(self.scoped().where(Invoice.order_id == order_id))
        ).first()


class CashSessionRepository(RestaurantScopedRepository[CashSession]):
    model = CashSession

    async def open_id(self) -> uuid.UUID | None:
        """The till open now, if any. At most one, by migration 0019's partial unique index."""
        found: uuid.UUID | None = await self.session.scalar(
            self.scoped()
            .with_only_columns(CashSession.id)
            .where(CashSession.status == CashSessionStatus.OPEN)
        )
        return found


class PaymentRepository(RestaurantScopedRepository[Payment]):
    model = Payment

    async def for_order(self, order_id: uuid.UUID) -> Sequence[Payment]:
        result = await self.session.scalars(
            self.scoped().where(Payment.order_id == order_id).order_by(Payment.id)
        )
        return result.all()
