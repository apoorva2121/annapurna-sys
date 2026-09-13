"""The rules for an order, from the first dish to the bill. Settlement is chunk G's, not this one's.

Five rules, and they are why this file exists rather than routes calling repositories.

**1 · The server prices everything.** A line names a dish, a quantity and its options. The unit
price comes from `menu_item_variant.price`, each option's delta from `modifier.price_delta`, and
the tax from the rate in force today — never from the client (`docs/security.md` A04).

**2 · Every figure on the order is recomputed after every change.** `_reprice` is the one place
totals are written, and it goes through `app/core/tax.py`, so the figure a waiter reads before
payment is the figure settlement starts from. Stored totals are a cache of that computation for the
list screens (G-13 item 6), never an input to it.

**3 · Every change carries the version it read, and holds the order row while it is made** (ADR
0010). The version check stops a stale screen; the lock stops two current ones racing.

**4 · What the kitchen has seen is cancelled, never deleted.** An unsent line is a mis-tap and
disappears. A sent one is food somebody may have cooked, so it is cancelled with a reason and an
audit row — and migration 0019 refuses the delete even if this service forgot.

**5 · The rate is snapshotted when a line is added.** Settlement re-freezes it from Section 14's
median date (chunk G). Until then the bill shows the rate in force today, which is right on every
night but a few a decade.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.business_day import business_date_of, calendar_date_of
from app.core.enums import (
    ChargeType,
    DiscountType,
    OrderChannel,
    OrderLineStatus,
    OrderStatus,
    OrderType,
    TableStatus,
    TaxRegime,
)
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.tax import (
    ZERO,
    ChargeInput,
    LineInput,
    collects_tax,
    discount_amount,
    price_bill,
    tax_line,
    to_paisa,
)
from app.core.tenancy import TenantScope
from app.models.audit import AuditLog
from app.models.menu import Modifier, ModifierGroup
from app.models.orders import (
    Order,
    OrderCharge,
    OrderDiscount,
    OrderLine,
    OrderLineModifier,
    OrderTable,
)
from app.models.setup import RestaurantTable
from app.models.tenancy import Restaurant
from app.repositories.orders import LIVE_ORDER_STATUSES, OrderRepository, PricingRepository
from app.repositories.setup import RestaurantRepository, RestaurantTableRepository

logger = logging.getLogger(__name__)

# Lines that are on the order but not on the bill.
_NOT_BILLED = frozenset({OrderLineStatus.CANCELLED, OrderLineStatus.RETURNED})
# Lines the kitchen has, and has not yet handed over.
_IN_THE_KITCHEN = frozenset(
    {OrderLineStatus.SENT, OrderLineStatus.PREPARING, OrderLineStatus.READY}
)


def _dec(value: object) -> Decimal:
    """Numeric columns are `Mapped[object]` across this codebase; always a Decimal at runtime."""
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _optional_dec(value: object) -> Decimal | None:
    return None if value is None else _dec(value)


class OrderService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._orders = OrderRepository(session, scope)
        self._pricing = PricingRepository(session, scope)
        self._tables = RestaurantTableRepository(session, scope)

    # ------------------------------------------------------------------ reads

    async def get(self, order_id: uuid.UUID) -> Order:
        order = await self._orders.get_detail(order_id, refresh=True)
        if order is None:
            raise NotFoundError("order.not_found", "That order does not exist.")
        return order

    async def list_orders(
        self,
        *,
        statuses: Sequence[str] | None = None,
        business_date: date | None = None,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[Order]:
        return await self._orders.list_page(
            statuses=statuses, business_date=business_date, limit=limit, after=after
        )

    # ------------------------------------------------------------------ opening

    async def create(
        self,
        actor: Actor,
        *,
        order_type: OrderType,
        table_ids: Sequence[uuid.UUID],
        covers: int | None,
        channel: OrderChannel,
        external_order_id: str | None,
    ) -> uuid.UUID:
        restaurant = await self._restaurant()
        now = datetime.now(UTC)
        business_date = business_date_of(now, restaurant.timezone, restaurant.business_day_start)

        tables = [await self._usable_table(table_id) for table_id in table_ids]
        order = Order(
            restaurant_id=self.scope.restaurant_id,
            order_number=await self._orders.next_order_number(business_date),
            type=order_type,
            channel=channel,
            external_order_id=external_order_id,
            status=OrderStatus.OPEN,
            waiter_employee_id=actor.employee_id,
            covers=covers,
            placed_at=now,
            business_date=business_date,
        )
        self.session.add(order)
        await self.session.flush()
        for index, table in enumerate(tables):
            self.session.add(
                OrderTable(
                    restaurant_id=self.scope.restaurant_id,
                    order_id=order.id,
                    restaurant_table_id=table.id,
                    is_primary=index == 0,
                )
            )
            table.status = TableStatus.OCCUPIED
        await self.session.flush()
        logger.info(
            "order.opened",
            extra={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "order_type": str(order_type),
                "tables": len(tables),
            },
        )
        return order.id

    async def _usable_table(self, table_id: uuid.UUID) -> RestaurantTable:
        table = await self._tables.get(table_id)
        if table is None:
            raise NotFoundError("table.not_found", "That table does not exist.")
        if not table.is_active:
            raise ConflictError("table.inactive", f"Table {table.code} is deactivated.")
        if table.status == TableStatus.OUT_OF_SERVICE:
            raise ConflictError("table.out_of_service", f"Table {table.code} is out of service.")
        return table

    # ------------------------------------------------------------------ lines

    async def add_line(
        self,
        order_id: uuid.UUID,
        *,
        version: int,
        variant_id: uuid.UUID,
        quantity: int,
        modifier_ids: Sequence[uuid.UUID],
        special_instructions: str | None,
    ) -> uuid.UUID:
        order = await self._locked(order_id, version)
        sale = await self._pricing.saleable_variant(variant_id)
        if sale is None:
            raise NotFoundError("menu_item_variant.not_found", "That dish is not on this menu.")
        dish = f"{sale.item.name} ({sale.variant.name})"
        if not (sale.variant.is_active and sale.item.is_active):
            raise ConflictError("menu_item_variant.unavailable", f"{dish} is not available.")
        chosen = await self._chosen_modifiers(sale.item.id, sale.item.name, modifier_ids)

        restaurant = await self._restaurant()
        today = calendar_date_of(datetime.now(UTC), restaurant.timezone)
        rate = await self._pricing.rate_on(sale.variant.tax_group_id, today)
        if rate is None:
            raise ConflictError(
                "tax.no_rate",
                f"{dish} has no tax rate in force on {today.isoformat()}. "
                "The owner needs to set one before it can be sold.",
            )
        charged_rate = rate.rate if collects_tax(restaurant.gst_scheme) else ZERO

        unit_price = _dec(sale.variant.price)
        each = unit_price + sum((_dec(modifier.price_delta) for modifier, _ in chosen), ZERO)
        if each < 0:
            raise AppError(
                "order_line.negative",
                f"Those options take {dish} below zero.",
                status_code=422,
            )
        subtotal = to_paisa(each * quantity)
        first = tax_line(subtotal, charged_rate, rate.regime, inclusive=rate.inclusive)

        line = OrderLine(
            restaurant_id=self.scope.restaurant_id,
            order_id=order.id,
            menu_item_variant_id=sale.variant.id,
            quantity=quantity,
            unit_price=unit_price,
            line_subtotal=subtotal,
            line_discount=ZERO,
            tax_group_id=sale.variant.tax_group_id,
            tax_regime=rate.regime,
            tax_rate=charged_rate,
            tax_inclusive=rate.inclusive,
            taxable_value=first.taxable_value,
            cgst_amount=first.cgst,
            sgst_amount=first.sgst,
            tax_amount=first.tax,
            line_total=first.total,
            status=OrderLineStatus.PENDING,
            special_instructions=special_instructions,
            seq=max((existing.seq for existing in order.lines), default=0) + 1,
        )
        self.session.add(line)
        await self.session.flush()
        for modifier, _ in chosen:
            self.session.add(
                OrderLineModifier(
                    restaurant_id=self.scope.restaurant_id,
                    order_line_id=line.id,
                    modifier_id=modifier.id,
                    price_delta=_dec(modifier.price_delta),
                )
            )
        await self._reprice(order.id)
        return line.id

    async def _chosen_modifiers(
        self, item_id: uuid.UUID, item_name: str, modifier_ids: Sequence[uuid.UUID]
    ) -> list[tuple[Modifier, ModifierGroup]]:
        """The options asked for, checked against what the dish offers and each question's limits.

        A modifier from another dish, another restaurant, or a deactivated group is "not offered",
        with one message for all three: saying which would confirm that another restaurant's id is
        real.
        """
        if len(set(modifier_ids)) != len(modifier_ids):
            raise AppError(
                "order_line.duplicate_modifier", "Each option can be chosen once.", status_code=422
            )
        offered = {
            modifier.id: (modifier, group)
            for modifier, group in await self._pricing.modifiers_for_item(item_id)
        }
        if any(modifier_id not in offered for modifier_id in modifier_ids):
            raise AppError(
                "order_line.modifier_not_offered",
                f"{item_name} does not offer that option.",
                status_code=422,
            )
        chosen = [offered[modifier_id] for modifier_id in modifier_ids]
        for group in await self._pricing.groups_for_item(item_id):
            count = sum(1 for _, owner in chosen if owner.id == group.id)
            if count < group.min_select or count > group.max_select:
                limits = (
                    f"exactly {group.min_select}"
                    if group.min_select == group.max_select
                    else f"between {group.min_select} and {group.max_select}"
                )
                raise AppError(
                    "order_line.modifier_selection",
                    f"{item_name}: {group.name} needs {limits}.",
                    details={"modifier_group_id": str(group.id)},
                    status_code=422,
                )
        return chosen

    async def update_line(
        self,
        order_id: uuid.UUID,
        line_id: uuid.UUID,
        *,
        version: int,
        changes: dict[str, Any],
    ) -> None:
        order = await self._locked(order_id, version)
        line = self._line(order, line_id)
        if line.status != OrderLineStatus.PENDING:
            raise ConflictError(
                "order_line.already_sent",
                "That dish has gone to the kitchen. Take it off and add it again instead.",
            )
        if changes.get("quantity") is not None:
            each = _dec(line.unit_price) + sum(
                (_dec(modifier.price_delta) for modifier in line.modifiers), ZERO
            )
            line.quantity = changes["quantity"]
            line.line_subtotal = to_paisa(each * changes["quantity"])
        if "special_instructions" in changes:
            line.special_instructions = changes["special_instructions"]
        await self._reprice(order.id)

    async def remove_line(
        self,
        actor: Actor,
        order_id: uuid.UUID,
        line_id: uuid.UUID,
        *,
        version: int,
        reason: str | None,
    ) -> None:
        order = await self._locked(order_id, version)
        line = self._line(order, line_id)
        if line.status in _NOT_BILLED:
            raise ConflictError("order_line.already_removed", "That dish is already off the bill.")
        if line.status == OrderLineStatus.PENDING:
            await self.session.delete(line)
        else:
            if reason is None:
                raise AppError(
                    "order_line.reason_required",
                    "That dish has gone to the kitchen, so taking it off needs a reason.",
                    status_code=422,
                )
            line.status = OrderLineStatus.CANCELLED
            line.cancel_reason = reason
            self._audit(
                actor,
                "order_line.cancel",
                "order_line",
                line.id,
                new={
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "quantity": line.quantity,
                    "line_subtotal": str(line.line_subtotal),
                    "status_when_cancelled": str(line.status),
                    "reason": reason,
                },
            )
        await self._reprice(order.id)

    @staticmethod
    def _line(order: Order, line_id: uuid.UUID) -> OrderLine:
        line = next((line for line in order.lines if line.id == line_id), None)
        if line is None:
            raise NotFoundError("order_line.not_found", "That dish is not on this order.")
        return line

    # ------------------------------------------------------------------ the evening

    async def send(self, order_id: uuid.UUID, *, version: int) -> None:
        order = await self._locked(order_id, version)
        pending = [line for line in order.lines if line.status == OrderLineStatus.PENDING]
        if not pending:
            raise ConflictError(
                "order.nothing_to_send",
                f"Order {order.order_number} has nothing new for the kitchen.",
            )
        now = datetime.now(UTC)
        for line in pending:
            line.status = OrderLineStatus.SENT
            line.sent_at = now
        order.status = OrderStatus.SENT
        if order.first_sent_at is None:
            order.first_sent_at = now
        order.updated_at = now
        await self.session.flush()
        logger.info("order.sent", extra={"order_id": str(order.id), "lines": len(pending)})

    async def mark_served(self, order_id: uuid.UUID, *, version: int) -> None:
        """Until M08's kitchen display exists, serving the order serves everything the kitchen has.

        `served_at` is overwritten on every serve, because Section 14's time of supply is when the
        supply completes — the last dish, not the first.
        """
        order = await self._locked(order_id, version)
        if order.first_sent_at is None:
            raise ConflictError(
                "order.not_sent", f"Nothing on order {order.order_number} has gone to the kitchen."
            )
        now = datetime.now(UTC)
        for line in order.lines:
            if line.status in _IN_THE_KITCHEN:
                line.status = OrderLineStatus.SERVED
        order.status = OrderStatus.SERVED
        order.served_at = now
        order.updated_at = now
        await self.session.flush()

    async def request_bill(self, order_id: uuid.UUID, *, version: int) -> None:
        """The first request is the one kept: bill-to-settle is measured from when the customer
        first asked, not from the third time they had to."""
        order = await self._locked(order_id, version)
        if not any(line.status not in _NOT_BILLED for line in order.lines):
            raise ConflictError("order.empty", f"Order {order.order_number} has nothing on it.")
        now = datetime.now(UTC)
        if order.bill_requested_at is None:
            order.bill_requested_at = now
        order.updated_at = now
        await self.session.flush()

    async def cancel(self, actor: Actor, order_id: uuid.UUID, *, version: int, reason: str) -> None:
        """An order that never settled. It never took an invoice number, so it leaves no gap.

        Cancelling after the kitchen has cooked is allowed — a table that walks out is a real
        evening — and is exactly what the audit row records: how much had gone to the kitchen.
        """
        order = await self._locked(order_id, version)
        cooked = [
            line
            for line in order.lines
            if line.status not in _NOT_BILLED and line.status != OrderLineStatus.PENDING
        ]
        now = datetime.now(UTC)
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = now
        order.cancel_reason = reason
        order.updated_at = now
        await self.session.flush()
        await self._release_tables(order)
        self._audit(
            actor,
            "order.cancel",
            "order",
            order.id,
            new={
                "order_number": order.order_number,
                "reason": reason,
                "lines_sent_to_kitchen": len(cooked),
                "value_sent_to_kitchen": str(sum((_dec(line.line_total) for line in cooked), ZERO)),
            },
        )
        await self.session.flush()
        logger.info(
            "order.cancelled",
            extra={"order_id": str(order.id), "lines_sent_to_kitchen": len(cooked)},
        )

    async def _release_tables(self, order: Order) -> None:
        """Free a table this order occupied, unless another live order still sits there."""
        for link in order.tables:
            if await self._orders.live_order_on_table(link.restaurant_table_id, excluding=order.id):
                continue
            table = await self._tables.get(link.restaurant_table_id)
            if table is not None and table.status == TableStatus.OCCUPIED:
                table.status = TableStatus.FREE
        await self.session.flush()

    # ------------------------------------------------------------------ discounts

    async def add_discount(
        self,
        actor: Actor,
        order_id: uuid.UUID,
        *,
        version: int,
        kind: DiscountType,
        rate: Decimal | None,
        flat_amount: Decimal | None,
        line_id: uuid.UUID | None,
        reason: str,
    ) -> None:
        """A discount or a comp: before tax (CGST Act s.15(3)(a)), with its authoriser's name.

        The actor is the authoriser. A discount on one dish takes from that dish; a discount on the
        order is shared across its dishes by largest remainder when the order is repriced. A
        discount that would exceed what it comes off is refused here rather than clamped.
        """
        order = await self._locked(order_id, version)
        billed = [line for line in order.lines if line.status not in _NOT_BILLED]
        if line_id is not None:
            line = self._line(order, line_id)
            if line.status in _NOT_BILLED:
                raise ConflictError(
                    "order_line.already_removed", "That dish is already off the bill."
                )
            already = sum(
                (
                    _dec(existing.amount)
                    for existing in order.discounts
                    if existing.order_line_id == line.id
                ),
                ZERO,
            )
            base = _dec(line.line_subtotal) - already
        else:
            if not billed:
                raise ConflictError("order.empty", f"Order {order.order_number} has nothing on it.")
            already = sum((_dec(existing.amount) for existing in order.discounts), ZERO)
            base = sum((_dec(line.line_subtotal) for line in billed), ZERO) - already
        try:
            amount = discount_amount(kind, base, rate=rate, flat_amount=flat_amount)
        except ValueError as error:
            raise AppError("order_discount.exceeds_base", str(error), status_code=422) from error

        discount = OrderDiscount(
            restaurant_id=self.scope.restaurant_id,
            order_id=order.id,
            order_line_id=line_id,
            type=kind,
            rate=rate,
            flat_amount=flat_amount,
            amount=amount,
            reason=reason,
            authorised_by=actor.employee_id,
        )
        self.session.add(discount)
        await self.session.flush()
        self._audit(
            actor,
            "order.discount",
            "order_discount",
            discount.id,
            new={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "type": str(kind),
                "rate": None if rate is None else str(rate),
                "flat_amount": None if flat_amount is None else str(flat_amount),
                "amount": str(amount),
                "order_line_id": None if line_id is None else str(line_id),
                "reason": reason,
            },
        )
        await self._reprice(order.id)
        logger.info(
            "order.discounted",
            extra={"order_id": str(order.id), "discount_type": str(kind), "amount": str(amount)},
        )

    async def remove_discount(
        self,
        actor: Actor,
        order_id: uuid.UUID,
        discount_id: uuid.UUID,
        *,
        version: int,
        reason: str | None,
    ) -> None:
        """Audited as well: a comp added and quietly removed after the bill was shown is the other
        half of the story the discount row tells."""
        order = await self._locked(order_id, version)
        discount = next((row for row in order.discounts if row.id == discount_id), None)
        if discount is None:
            raise NotFoundError("order_discount.not_found", "That discount is not on this order.")
        self._audit(
            actor,
            "order.discount_removed",
            "order_discount",
            discount.id,
            new={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "type": str(discount.type),
                "amount": str(discount.amount),
                "authorised_by": str(discount.authorised_by),
                "reason": reason,
            },
        )
        await self.session.delete(discount)
        await self._reprice(order.id)

    # ------------------------------------------------------------------ charges

    async def add_charge(
        self,
        order_id: uuid.UUID,
        *,
        version: int,
        kind: ChargeType,
        amount: Decimal | None,
        tax_group_id: uuid.UUID | None,
    ) -> None:
        """Packaging, delivery, or a service charge — and a service charge only ever on purpose.

        A service charge is refused while the restaurant has not enabled one, is never added by
        anything but this request, is computed from the bill rather than typed in, appears once, and
        is removable (CCPA guidelines, upheld 28 Mar 2025). Whether GST applies to it is unsettled
        (R17), so its tax group is whatever the restaurant names, including none.
        """
        order = await self._locked(order_id, version)
        restaurant = await self._restaurant()
        if kind == ChargeType.SERVICE_CHARGE:
            if restaurant.service_charge_rate is None:
                raise ConflictError(
                    "service_charge.disabled",
                    "This restaurant does not charge a service charge. The owner can enable one.",
                )
            if any(charge.type == ChargeType.SERVICE_CHARGE for charge in order.charges):
                raise ConflictError(
                    "service_charge.already_added", "This order already carries a service charge."
                )

        rate: Decimal | None = None
        if tax_group_id is not None:
            today = calendar_date_of(datetime.now(UTC), restaurant.timezone)
            found = await self._pricing.rate_on(tax_group_id, today)
            if found is None:
                raise NotFoundError(
                    "tax_group.not_found", "That tax group does not exist or has no rate today."
                )
            if found.regime != TaxRegime.GST:
                raise AppError(
                    "order_charge.not_gst",
                    "A charge is part of the meal and is taxed under GST, not a state tax.",
                    status_code=422,
                )
            rate = found.rate if collects_tax(restaurant.gst_scheme) else ZERO

        initial = amount if amount is not None else ZERO
        figures = tax_line(initial, rate if rate is not None else ZERO)
        self.session.add(
            OrderCharge(
                restaurant_id=self.scope.restaurant_id,
                order_id=order.id,
                type=kind,
                amount=initial,
                tax_group_id=tax_group_id,
                tax_rate=rate,
                cgst_amount=figures.cgst,
                sgst_amount=figures.sgst,
                tax_amount=figures.tax,
                is_optional=kind == ChargeType.SERVICE_CHARGE,
            )
        )
        await self._reprice(order.id)

    async def remove_charge(
        self, order_id: uuid.UUID, charge_id: uuid.UUID, *, version: int
    ) -> None:
        order = await self._locked(order_id, version)
        charge = next((row for row in order.charges if row.id == charge_id), None)
        if charge is None:
            raise NotFoundError("order_charge.not_found", "That charge is not on this order.")
        await self.session.delete(charge)
        await self._reprice(order.id)

    # ------------------------------------------------------------------ splitting

    async def split(
        self,
        actor: Actor,
        order_id: uuid.UUID,
        *,
        version: int,
        line_ids: Sequence[uuid.UUID],
    ) -> uuid.UUID:
        """Split by items: the chosen dishes move to a new order at the same tables (decision 9).

        Done before settlement, so every order still settles to exactly one invoice and "which
        invoice covers this dish" stays a single join. A discount aimed at a moved dish moves with
        it; discounts on the whole order, and its charges, stay where they were. Splitting by
        *payments* needs no endpoint — it is several payments against one order, chunk G's.
        """
        order = await self._locked(order_id, version)
        chosen = [self._line(order, line_id) for line_id in line_ids]
        if any(line.status in _NOT_BILLED for line in chosen):
            raise ConflictError(
                "order_line.already_removed", "A dish already off the bill cannot move to another."
            )
        billed = [line for line in order.lines if line.status not in _NOT_BILLED]
        if len(chosen) == len(billed):
            raise ConflictError(
                "order.split_everything",
                "That moves every dish, which would leave nothing on this order.",
            )

        if any(line.status in _IN_THE_KITCHEN for line in chosen):
            status = OrderStatus.SENT
        elif any(line.status == OrderLineStatus.SERVED for line in chosen):
            status = OrderStatus.SERVED
        else:
            status = OrderStatus.OPEN

        restaurant = await self._restaurant()
        now = datetime.now(UTC)
        business_date = business_date_of(now, restaurant.timezone, restaurant.business_day_start)
        child = Order(
            restaurant_id=self.scope.restaurant_id,
            order_number=await self._orders.next_order_number(business_date),
            type=order.type,
            channel=order.channel,
            status=status,
            waiter_employee_id=order.waiter_employee_id,
            parent_order_id=order.id,
            placed_at=now,
            first_sent_at=order.first_sent_at if status != OrderStatus.OPEN else None,
            served_at=order.served_at if status == OrderStatus.SERVED else None,
            business_date=business_date,
        )
        self.session.add(child)
        await self.session.flush()
        for link in order.tables:
            self.session.add(
                OrderTable(
                    restaurant_id=self.scope.restaurant_id,
                    order_id=child.id,
                    restaurant_table_id=link.restaurant_table_id,
                    is_primary=link.is_primary,
                )
            )
        moved = [line.id for line in chosen]
        await self.session.flush()
        await self._orders.move_lines(moved, child.id)
        self._audit(
            actor,
            "order.split",
            "order",
            order.id,
            new={
                "order_number": order.order_number,
                "new_order_id": str(child.id),
                "new_order_number": child.order_number,
                "line_ids": [str(line_id) for line_id in moved],
            },
        )
        await self._reprice(order.id)
        await self._reprice(child.id)
        logger.info(
            "order.split",
            extra={"order_id": str(order.id), "new_order_id": str(child.id), "lines": len(moved)},
        )
        return child.id

    # ------------------------------------------------------------------ the one place totals change

    async def _reprice(self, order_id: uuid.UUID) -> Order:
        """Recompute every figure on the order from its lines, discounts and charges.

        Flushes first and re-reads, so the bill is computed from what the database holds rather than
        from collections the identity map loaded before the change.
        """
        await self.session.flush()
        order = await self.get(order_id)
        restaurant = await self._restaurant()
        billed = [line for line in order.lines if line.status not in _NOT_BILLED]
        billed_ids = {line.id for line in billed}

        on_line: dict[uuid.UUID, list[OrderDiscount]] = defaultdict(list)
        on_order: list[OrderDiscount] = []
        for discount in sorted(order.discounts, key=lambda row: row.id):
            if discount.order_line_id is None:
                on_order.append(discount)
            elif discount.order_line_id in billed_ids:
                on_line[discount.order_line_id].append(discount)
            else:
                # The dish came off the bill; a discount on it takes nothing off.
                discount.amount = ZERO

        try:
            inputs: list[LineInput] = []
            for line in billed:
                subtotal = _dec(line.line_subtotal)
                taken = ZERO
                for discount in on_line.get(line.id, []):
                    discount.amount = self._discount_on(discount, subtotal - taken)
                    taken += _dec(discount.amount)
                inputs.append(
                    LineInput(
                        subtotal=subtotal,
                        rate=_dec(line.tax_rate),
                        regime=line.tax_regime,
                        inclusive=line.tax_inclusive,
                        line_discount=taken,
                    )
                )
            room = sum((entry.subtotal - entry.line_discount for entry in inputs), ZERO)
            order_discount = ZERO
            for discount in on_order:
                discount.amount = self._discount_on(discount, room - order_discount)
                order_discount += _dec(discount.amount)
        except ValueError as error:
            raise ConflictError(
                "order.discount_exceeds_bill",
                "A discount on this order is now larger than what it comes off. "
                "Remove the discount first.",
            ) from error

        service_rate = _optional_dec(restaurant.service_charge_rate)
        charges: list[ChargeInput] = []
        for charge in order.charges:
            if charge.type == ChargeType.SERVICE_CHARGE and service_rate is not None:
                charge.amount = to_paisa((room - order_discount) * service_rate)
            charges.append(
                ChargeInput(amount=_dec(charge.amount), rate=_optional_dec(charge.tax_rate))
            )

        bill = price_bill(
            inputs,
            order_discount=order_discount,
            charges=charges,
            collect_tax=collects_tax(restaurant.gst_scheme),
        )
        for line, priced in zip(billed, bill.lines, strict=True):
            line.line_discount = priced.discount
            line.taxable_value = priced.tax.taxable_value
            line.cgst_amount = priced.tax.cgst
            line.sgst_amount = priced.tax.sgst
            line.tax_amount = priced.tax.tax
            line.line_total = priced.tax.total
        for charge, priced_charge in zip(order.charges, bill.charges, strict=True):
            charge.cgst_amount = priced_charge.tax.cgst
            charge.sgst_amount = priced_charge.tax.sgst
            charge.tax_amount = priced_charge.tax.tax

        order.subtotal = bill.subtotal
        order.discount_total = bill.discount_total
        order.charge_total = bill.charge_total
        order.tax_total = bill.tax_total
        order.round_off = bill.round_off
        order.grand_total = bill.grand_total
        # Set even when no figure moved, so the version always advances: a change the version
        # does not record is a change the next stale screen would silently overwrite.
        order.updated_at = datetime.now(UTC)
        await self.session.flush()
        return order

    @staticmethod
    def _discount_on(discount: OrderDiscount, base: Decimal) -> Decimal:
        return discount_amount(
            discount.type,
            base,
            rate=_optional_dec(discount.rate),
            flat_amount=_optional_dec(discount.flat_amount),
        )

    # ------------------------------------------------------------------ plumbing

    async def _locked(self, order_id: uuid.UUID, version: int) -> Order:
        """Lock, re-read, and refuse a finished order or a stale version — in that order, because
        "this order is settled" is more useful to a waiter than "reload"."""
        if not await self._orders.lock(order_id):
            raise NotFoundError("order.not_found", "That order does not exist.")
        order = await self.get(order_id)
        if order.status not in LIVE_ORDER_STATUSES:
            raise ConflictError(
                "order.final",
                f"Order {order.order_number} is {order.status} and cannot change.",
            )
        if order.version != version:
            raise ConflictError(
                "order.stale",
                "Somebody changed this order after you opened it. Reload it and try again.",
                details={"current_version": order.version},
            )
        return order

    async def _restaurant(self) -> Restaurant:
        restaurant = await RestaurantRepository(self.session, self.scope).get()
        if restaurant is None:
            raise NotFoundError("restaurant.not_found", "This restaurant no longer exists.")
        return restaurant

    def _audit(
        self,
        actor: Actor,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        *,
        new: dict[str, Any],
    ) -> None:
        self.session.add(
            AuditLog(
                restaurant_id=actor.restaurant_id,
                actor_employee_id=actor.employee_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                new_value=new,
            )
        )
