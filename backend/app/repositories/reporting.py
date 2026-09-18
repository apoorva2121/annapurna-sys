"""Every aggregate the dashboards and reports are built from. Business rules live in the service.

Five things here are load-bearing, and four of them are rules this codebase has already paid for
once somewhere else.

**These are queries, not tables.** `docs/schema.md`'s eliminated list settled it: the per-dish and
per-employee rollups "are queries, not tables. Storing them creates a second source of truth that
silently drifts." So every figure on every screen is computed from the rows that produced it, which
is also what makes drill-through free — the screen links to the same rows the number came from.

**Every aggregation groups on `business_date`, never on `date_trunc` of a timestamp.** CLAUDE.md
invariant 4: a restaurant closing at 2am has its takings on the right day only because of that
denormalised column, and a report that reached for `created_at` would be quietly wrong for exactly
the restaurants this product is for.

**Dish cost comes from `order_line.theoretical_unit_cost`, frozen at settlement.** Never
recomputed from today's recipes — `settlement.py`'s own words are "what did this bill cost in March
is answered from March's recipe rather than today's", and a report that recomputed would let a
recipe edit rewrite last month.

**Theoretical and actual consumption are returned separately, always.** `stock_movement.basis`
keeps them apart and invariant 7 forbids summing them into one consumption figure: the gap between
them is the number this product exists to produce.

**Nothing here rounds.** Every money value comes back as `Decimal` at full precision; the service
decides the one place a percentage is computed and the schema turns it into a string. Rounding in
two places is how a report's column stops adding up to its own total.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, and_, case, func, select

from app.core.enums import MovementBasis, OrderStatus
from app.models.customers import Feedback
from app.models.inventory import StockMovement
from app.models.kitchen import KotTicket
from app.models.menu import MenuItem, MenuItemVariant
from app.models.orders import Invoice, Order, OrderLine, Payment
from app.models.stock import StockItem
from app.models.tenancy import Organization, Restaurant
from app.models.waste import WastageEvent, WastageReason
from app.repositories.base import ScopedRepository

# Settled and not cancelled: an open order is not revenue, and a cancelled one never was.
_COUNTED = (OrderStatus.SETTLED.value,)


@dataclass(frozen=True, slots=True)
class SalesDay:
    """One business day's trading, as an owner reads a day."""

    business_date: date
    orders: int
    covers: int
    revenue: Decimal
    tax: Decimal
    discounts: Decimal


@dataclass(frozen=True, slots=True)
class PaymentSplit:
    method: str
    amount: Decimal
    count: int


@dataclass(frozen=True, slots=True)
class DishRow:
    """The acceptance query, per dish (`docs/domain-model.md`).

    Everything on this row is read from what was frozen at the time, not recomputed: `revenue` and
    `theoretical_cost` come off the settled order lines, so a price change or a recipe edit made
    today moves nothing here.
    """

    variant_id: uuid.UUID
    item_name: str
    variant_name: str
    units: int
    revenue: Decimal
    theoretical_cost: Decimal
    average_rating: Decimal | None
    average_prep_seconds: int | None


@dataclass(frozen=True, slots=True)
class ConsumptionRow:
    """One stock item's theoretical against its actual, and the waste that explains part of it.

    The four numbers are returned side by side and **never summed**: the report's whole subject is
    the distance between the first two (invariant 7), and `waste_value` is the part of that
    distance somebody wrote down a reason for.
    """

    stock_item_id: uuid.UUID
    item_name: str
    base_unit: str
    theoretical_quantity: Decimal
    actual_quantity: Decimal
    theoretical_value: Decimal
    actual_value: Decimal
    waste_quantity: Decimal
    waste_value: Decimal


@dataclass(frozen=True, slots=True)
class WasteRow:
    """One line of the waste report: a stage, a reason, what it cost and how often.

    Never one total. `docs/waste-model.md`: four stages, each with a different owner and a
    different fix, and lumping them produces a number nobody can act on.
    """

    stage: str
    reason_code: str
    reason_name: str
    events: int
    cost_value: Decimal


class ReportingRepository(ScopedRepository[Restaurant]):
    """Not a `RestaurantScopedRepository`: every query here starts from a different table, so there
    is no single `model.restaurant_id` for the base class to filter on. The scope is applied
    explicitly in each statement instead, and the generic suites probe every route that reaches
    here.

    **The demo organization is excluded once, here**, rather than in each query — one place to be
    right. A seeded demo restaurant's figures must never reach a real report.
    """

    model = Restaurant

    def _real_restaurants(self) -> Select[tuple[uuid.UUID]]:
        """This restaurant, unless it belongs to a demo organization."""
        return (
            select(Restaurant.id)
            .join(Organization, Organization.id == Restaurant.organization_id)
            .where(
                Restaurant.id == self.scope.restaurant_id,
                Restaurant.organization_id == self.scope.organization_id,
                Organization.is_demo.is_(False),
            )
        )

    # ------------------------------------------------------------------- sales

    async def sales_by_day(self, *, since: date, until: date) -> list[SalesDay]:
        """Revenue per business day, from the invoices that were actually issued.

        Cancelled invoices keep their number for GST (M07) and contribute nothing here — which is
        why the filter is on `cancelled_at`, not on absence from the table.
        """
        statement = (
            select(
                Invoice.business_date,
                func.count(func.distinct(Invoice.order_id)),
                func.coalesce(func.sum(Order.covers), 0),
                func.coalesce(func.sum(Invoice.grand_total), 0),
                func.coalesce(func.sum(Invoice.cgst_total + Invoice.sgst_total), 0),
                func.coalesce(func.sum(Invoice.discount_total), 0),
            )
            .join(Order, Order.id == Invoice.order_id)
            .where(
                Invoice.restaurant_id.in_(self._real_restaurants()),
                Invoice.business_date >= since,
                Invoice.business_date <= until,
                Invoice.cancelled_at.is_(None),
            )
            .group_by(Invoice.business_date)
            .order_by(Invoice.business_date)
        )
        rows = (await self.session.execute(statement)).all()
        return [
            SalesDay(
                business_date=row[0],
                orders=int(row[1]),
                covers=int(row[2]),
                revenue=Decimal(row[3]),
                tax=Decimal(row[4]),
                discounts=Decimal(row[5]),
            )
            for row in rows
        ]

    async def payments_by_method(self, *, since: date, until: date) -> list[PaymentSplit]:
        """What the money arrived as. A refund is a negative payment (`docs/schema.md`), so it
        reduces its own method's total rather than appearing as a separate line."""
        statement = (
            select(
                Payment.method,
                func.coalesce(func.sum(Payment.amount), 0),
                func.count(Payment.id),
            )
            .join(Order, Order.id == Payment.order_id)
            .where(
                Payment.restaurant_id.in_(self._real_restaurants()),
                Order.business_date >= since,
                Order.business_date <= until,
            )
            .group_by(Payment.method)
            .order_by(Payment.method)
        )
        rows = (await self.session.execute(statement)).all()
        return [
            PaymentSplit(method=str(row[0]), amount=Decimal(row[1]), count=int(row[2]))
            for row in rows
        ]

    # -------------------------------------------------------------- dish rows

    async def dish_performance(self, *, since: date, until: date) -> list[DishRow]:
        """`docs/domain-model.md`'s acceptance query, minus the two columns that come from other
        tables — consumption and waste are per *stock item*, not per dish, and joining them here
        would multiply the revenue by the number of ingredients.

        Ratings and prep time are correlated subqueries rather than joins for the same reason: an
        order with three ratings and four tickets would otherwise count its revenue twelve times.
        This is the single most common way a report of this shape is silently wrong.
        """
        rating = (
            select(func.avg(Feedback.food_rating))
            .where(
                Feedback.order_id == OrderLine.order_id,
                Feedback.restaurant_id == Order.restaurant_id,
            )
            .correlate(OrderLine, Order)
            .scalar_subquery()
        )
        prep = (
            select(func.avg(func.extract("epoch", KotTicket.ready_at - KotTicket.printed_at)))
            .where(
                KotTicket.order_id == OrderLine.order_id,
                KotTicket.ready_at.is_not(None),
            )
            .correlate(OrderLine)
            .scalar_subquery()
        )
        statement = (
            select(
                OrderLine.menu_item_variant_id,
                MenuItem.name,
                MenuItemVariant.name,
                func.coalesce(func.sum(OrderLine.quantity), 0),
                func.coalesce(func.sum(OrderLine.line_total), 0),
                # Frozen at settlement. Never recomputed from today's recipe.
                func.coalesce(func.sum(OrderLine.theoretical_unit_cost * OrderLine.quantity), 0),
                func.avg(rating),
                func.avg(prep),
            )
            .join(Order, Order.id == OrderLine.order_id)
            .join(MenuItemVariant, MenuItemVariant.id == OrderLine.menu_item_variant_id)
            .join(MenuItem, MenuItem.id == MenuItemVariant.menu_item_id)
            .where(
                Order.restaurant_id.in_(self._real_restaurants()),
                Order.business_date >= since,
                Order.business_date <= until,
                Order.status.in_(_COUNTED),
            )
            .group_by(OrderLine.menu_item_variant_id, MenuItem.name, MenuItemVariant.name)
            .order_by(func.sum(OrderLine.line_total).desc())
        )
        rows = (await self.session.execute(statement)).all()
        return [
            DishRow(
                variant_id=row[0],
                item_name=str(row[1]),
                variant_name=str(row[2]),
                units=int(row[3]),
                revenue=Decimal(row[4]),
                theoretical_cost=Decimal(row[5]),
                average_rating=None if row[6] is None else Decimal(row[6]),
                average_prep_seconds=None if row[7] is None else int(row[7]),
            )
            for row in rows
        ]

    # ------------------------------------------------------- the variance itself

    async def consumption(self, *, since: date, until: date) -> list[ConsumptionRow]:
        """Theoretical against actual, per stock item, with the waste that explains part of the gap.

        **The two bases are summed separately in one pass** — `SUM(CASE WHEN basis = …)` rather
        than two queries — so they cannot drift apart between round trips, and so nothing in the
        SQL is capable of adding them together.

        Consumption is negative in the ledger (stock going out), so the sums are negated here to
        give a report a positive quantity consumed. That is the one place the sign is flipped, and
        it is flipped for both bases identically.
        """
        consumed = StockMovement.quantity_delta < 0
        theoretical = and_(consumed, StockMovement.basis == MovementBasis.THEORETICAL.value)
        actual = and_(consumed, StockMovement.basis == MovementBasis.ACTUAL.value)

        waste = (
            select(
                WastageEvent.stock_item_id.label("stock_item_id"),
                func.coalesce(func.sum(WastageEvent.quantity), 0).label("quantity"),
                func.coalesce(func.sum(WastageEvent.cost_value), 0).label("value"),
            )
            .where(
                WastageEvent.restaurant_id.in_(self._real_restaurants()),
                WastageEvent.business_date >= since,
                WastageEvent.business_date <= until,
            )
            .group_by(WastageEvent.stock_item_id)
            .subquery()
        )

        statement = (
            select(
                StockMovement.stock_item_id,
                StockItem.name,
                StockItem.base_unit,
                -func.coalesce(
                    func.sum(case((theoretical, StockMovement.quantity_delta), else_=0)), 0
                ),
                -func.coalesce(func.sum(case((actual, StockMovement.quantity_delta), else_=0)), 0),
                -func.coalesce(
                    func.sum(
                        case(
                            (
                                theoretical,
                                StockMovement.quantity_delta * StockMovement.unit_cost,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                -func.coalesce(
                    func.sum(
                        case(
                            (actual, StockMovement.quantity_delta * StockMovement.unit_cost),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(waste.c.quantity, 0),
                func.coalesce(waste.c.value, 0),
            )
            .join(StockItem, StockItem.id == StockMovement.stock_item_id)
            .outerjoin(waste, waste.c.stock_item_id == StockMovement.stock_item_id)
            .where(
                StockMovement.restaurant_id.in_(self._real_restaurants()),
                StockMovement.business_date >= since,
                StockMovement.business_date <= until,
            )
            .group_by(
                StockMovement.stock_item_id,
                StockItem.name,
                StockItem.base_unit,
                waste.c.quantity,
                waste.c.value,
            )
            .order_by(StockItem.name)
        )
        rows = (await self.session.execute(statement)).all()
        return [
            ConsumptionRow(
                stock_item_id=row[0],
                item_name=str(row[1]),
                base_unit=str(row[2]),
                theoretical_quantity=Decimal(row[3]),
                actual_quantity=Decimal(row[4]),
                theoretical_value=Decimal(row[5]),
                actual_value=Decimal(row[6]),
                waste_quantity=Decimal(row[7]),
                waste_value=Decimal(row[8]),
            )
            for row in rows
        ]

    # --------------------------------------------------------------- the waste

    async def waste_by_reason(self, *, since: date, until: date) -> list[WasteRow]:
        """What was thrown away, by stage and then by reason.

        **This is M09's aggregation written a second time, and the duplication is deliberate.**
        `WastageEventRepository.summary()` answers the same question for the chef's screen and is
        scoped by `restaurant_id` alone; every query in this file goes through
        `_real_restaurants()`, which is decision 8 — the demo organization appears in no report,
        enforced in one place rather than in each query. Bending M09's repository to take a
        reporting concern would have put that rule in two places, which is the thing decision 8
        exists to prevent.

        `tests/test_reporting.py::test_the_waste_report_agrees_with_m09s_own_summary` runs both
        against one fixture and compares them line for line, so the two cannot drift apart
        unnoticed. That test is the price of the duplication and the reason it is safe.
        """
        statement = (
            select(
                WastageReason.stage,
                WastageReason.code,
                WastageReason.name,
                func.count(WastageEvent.id),
                func.coalesce(func.sum(WastageEvent.cost_value), 0),
            )
            .join(WastageReason, WastageReason.id == WastageEvent.wastage_reason_id)
            .where(
                WastageEvent.restaurant_id.in_(self._real_restaurants()),
                WastageEvent.business_date >= since,
                WastageEvent.business_date <= until,
            )
            .group_by(WastageReason.stage, WastageReason.code, WastageReason.name)
            .order_by(func.sum(WastageEvent.cost_value).desc())
        )
        return [
            WasteRow(
                stage=row[0],
                reason_code=row[1],
                reason_name=row[2],
                events=int(row[3]),
                cost_value=Decimal(row[4]),
            )
            for row in (await self.session.execute(statement)).all()
        ]

    # -------------------------------------------------------------- the glance

    async def open_orders(self) -> int:
        statement = select(func.count(Order.id)).where(
            Order.restaurant_id.in_(self._real_restaurants()),
            Order.status == OrderStatus.OPEN.value,
        )
        return int(await self.session.scalar(statement) or 0)

    async def ratings(self, *, since: date, until: date) -> tuple[Decimal | None, int]:
        """The average and how many it is an average of. A 4.8 from two people is not a 4.8."""
        statement = select(func.avg(Feedback.overall_rating), func.count(Feedback.id)).where(
            Feedback.restaurant_id.in_(self._real_restaurants()),
            Feedback.business_date >= since,
            Feedback.business_date <= until,
        )
        row = (await self.session.execute(statement)).one()
        return (None if row[0] is None else Decimal(row[0])), int(row[1])

    async def variant_ids_for(self, dish_names: Sequence[str]) -> list[uuid.UUID]:
        """Used only by tests and the drill-through; kept here so no service writes SQL."""
        statement = (
            select(MenuItemVariant.id)
            .join(MenuItem, MenuItem.id == MenuItemVariant.menu_item_id)
            .where(
                MenuItem.restaurant_id == self.scope.restaurant_id,
                MenuItem.name.in_(list(dish_names)),
            )
        )
        return list((await self.session.scalars(statement)).all())
