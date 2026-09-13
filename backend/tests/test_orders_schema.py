"""The guarantees migration 0019 makes at the database, not in a service.

Every rule here has to hold when a future path forgets to ask: a migration, a seed script, psql,
or a bug in the settlement service. The two carrying the most weight are that a settled order
cannot be edited and that an invoice number survives, because a restaurant whose bills can be
changed after payment does not have bills.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Employee
from app.models.menu import MenuCategory, MenuItem, MenuItemVariant, Modifier, ModifierGroup
from app.models.orders import (
    CashCount,
    CashSession,
    CreditNote,
    IdempotencyKey,
    Invoice,
    Order,
    OrderCharge,
    OrderDiscount,
    OrderLine,
    OrderLineModifier,
    OrderTable,
    Payment,
)
from app.models.setup import DiningArea, RestaurantTable, Station, TaxGroup
from app.models.tenancy import Restaurant
from tests.test_procurement_schema import _restaurant

_NOW = datetime(2026, 9, 13, 14, 0, tzinfo=UTC)
_DAY = date(2026, 9, 13)
# The format example GSTN publishes, not anybody's registration.
_GSTIN = "27AAAAA0000A1Z5"


@dataclass(frozen=True)
class _World:
    restaurant: Restaurant
    employee: Employee
    tax_group: TaxGroup
    variant: MenuItemVariant
    modifier: Modifier
    table: RestaurantTable


async def _world(session: AsyncSession, slug: str) -> _World:
    """One restaurant with the least an order needs: a dish, a modifier, a table and a person."""
    restaurant = await _restaurant(session, slug)
    rid = restaurant.id
    employee = Employee(
        organization_id=restaurant.organization_id,
        employee_code="E1",
        full_name="Asha",
        joined_on=date(2026, 1, 1),
    )
    area = DiningArea(restaurant_id=rid, name="Hall", seq=0, is_active=True)
    station = Station(restaurant_id=rid, code="pass", name="Pass", seq=0, is_active=True)
    tax_group = TaxGroup(restaurant_id=rid, code="GST5", name="GST 5%", is_active=True)
    category = MenuCategory(restaurant_id=rid, code="MAINS", name="Mains", seq=0, is_active=True)
    group = ModifierGroup(
        restaurant_id=rid,
        code="EXTRA",
        name="Extras",
        min_select=0,
        max_select=1,
        is_required=False,
        is_active=True,
    )
    session.add_all([employee, area, station, tax_group, category, group])
    await session.flush()
    item = MenuItem(
        restaurant_id=rid,
        menu_category_id=category.id,
        code="BUTTER_CHICKEN",
        name="Butter Chicken",
        food_type="non_veg",
        station_id=station.id,
        seq=0,
        is_active=True,
    )
    modifier = Modifier(
        restaurant_id=rid,
        modifier_group_id=group.id,
        code="CHEESE",
        name="Extra cheese",
        price_delta=Decimal("40.00"),
        seq=0,
        is_active=True,
    )
    table = RestaurantTable(
        restaurant_id=rid, dining_area_id=area.id, code="T6", seats=4, status="free", is_active=True
    )
    session.add_all([item, modifier, table])
    await session.flush()
    variant = MenuItemVariant(
        restaurant_id=rid,
        menu_item_id=item.id,
        code="FULL",
        name="Full",
        price=Decimal("470.00"),
        tax_group_id=tax_group.id,
        prep_minutes=12,
        seq=0,
        is_active=True,
    )
    session.add(variant)
    await session.flush()
    return _World(restaurant, employee, tax_group, variant, modifier, table)


async def _order(
    session: AsyncSession, world: _World, *, number: str = "1", status: str = "open", **extra: Any
) -> Order:
    order = Order(
        restaurant_id=world.restaurant.id,
        order_number=number,
        type="dine_in",
        channel="pos",
        status=status,
        placed_at=_NOW,
        business_date=_DAY,
        **extra,
    )
    session.add(order)
    await session.flush()
    return order


async def _settled_order(session: AsyncSession, world: _World, *, number: str = "1") -> Order:
    return await _order(
        session,
        world,
        number=number,
        status="settled",
        settled_at=_NOW,
        subtotal=Decimal("940.00"),
        tax_total=Decimal("47.00"),
        grand_total=Decimal("987.00"),
    )


def _line(world: _World, order: Order, **overrides: Any) -> OrderLine:
    """Two butter chicken at ₹470 with 5% GST split evenly: ₹940 + ₹23.50 + ₹23.50 = ₹987."""
    values: dict[str, Any] = {
        "restaurant_id": world.restaurant.id,
        "order_id": order.id,
        "menu_item_variant_id": world.variant.id,
        "quantity": 2,
        "unit_price": Decimal("470.00"),
        "line_subtotal": Decimal("940.00"),
        "tax_group_id": world.tax_group.id,
        "tax_regime": "gst",
        "tax_rate": Decimal("0.0500"),
        "taxable_value": Decimal("940.00"),
        "cgst_amount": Decimal("23.50"),
        "sgst_amount": Decimal("23.50"),
        "tax_amount": Decimal("47.00"),
        "line_total": Decimal("987.00"),
        "status": "pending",
    }
    return OrderLine(**(values | overrides))


async def _saved_line(
    session: AsyncSession, world: _World, order: Order, **overrides: Any
) -> OrderLine:
    line = _line(world, order, **overrides)
    session.add(line)
    await session.flush()
    return line


def _invoice(world: _World, order: Order, **overrides: Any) -> Invoice:
    values: dict[str, Any] = {
        "restaurant_id": world.restaurant.id,
        "order_id": order.id,
        "document_type": "tax_invoice",
        "financial_year": "2026-27",
        "sequence": 1,
        "invoice_number": "2026-27/000001",
        "status": "issued",
        "issued_at": _NOW,
        "invoice_date": _DAY,
        "business_date": _DAY,
        "supplier_name": "Tandoor House",
        "supplier_gstin": _GSTIN,
        "taxable_total": Decimal("940.00"),
        "cgst_total": Decimal("23.50"),
        "sgst_total": Decimal("23.50"),
        "grand_total": Decimal("987.00"),
    }
    return Invoice(**(values | overrides))


async def _saved_invoice(
    session: AsyncSession, world: _World, order: Order, **overrides: Any
) -> Invoice:
    invoice = _invoice(world, order, **overrides)
    session.add(invoice)
    await session.flush()
    return invoice


def _payment(world: _World, order: Order, **overrides: Any) -> Payment:
    values: dict[str, Any] = {
        "restaurant_id": world.restaurant.id,
        "order_id": order.id,
        "method": "cash",
        "amount": Decimal("987.00"),
        "status": "success",
        "paid_at": _NOW,
        "business_date": _DAY,
    }
    return Payment(**(values | overrides))


async def _sql(session: AsyncSession, statement: str, **params: Any) -> None:
    await session.execute(text(statement), params)


async def _settle(session: AsyncSession, order: Order) -> None:
    await _sql(
        session,
        "UPDATE \"order\" SET status = 'settled', settled_at = now() WHERE id = :id",
        id=order.id,
    )


class TestASettledOrderDoesNotChange:
    """Invariant 6. The attack is one UPDATE: a ₹987 bill paid in cash, edited to ₹587 after the
    customer leaves, and ₹400 walks out of the till with every record agreeing."""

    async def test_changing_a_settled_orders_total_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "settled-total")
        order = await _settled_order(db_session, world)

        with pytest.raises(DBAPIError) as raised:
            await _sql(
                db_session, 'UPDATE "order" SET grand_total = 587 WHERE id = :id', id=order.id
            )
        assert "immutable" in str(raised.value)

    async def test_a_settled_order_can_be_voided(self, db_session: AsyncSession) -> None:
        """The one transition the law allows: an invoice cancelled on its day of issue."""
        world = await _world(db_session, "settled-void")
        order = await _settled_order(db_session, world)

        await _sql(
            db_session,
            "UPDATE \"order\" SET status = 'voided', cancel_reason = 'billed to the wrong table', "
            "cancelled_at = now(), voided_by = :by WHERE id = :id",
            id=order.id,
            by=world.employee.id,
        )
        status = await db_session.scalar(
            text('SELECT status FROM "order" WHERE id = :id'), {"id": order.id}
        )
        assert status == "voided"

    async def test_voiding_cannot_also_rewrite_the_money(self, db_session: AsyncSession) -> None:
        """Otherwise "void" is the door the total-edit walks back in through."""
        world = await _world(db_session, "settled-void-money")
        order = await _settled_order(db_session, world)

        with pytest.raises(DBAPIError) as raised:
            await _sql(
                db_session,
                "UPDATE \"order\" SET status = 'voided', cancel_reason = 'x', grand_total = 0 "
                "WHERE id = :id",
                id=order.id,
            )
        assert "immutable" in str(raised.value)

    async def test_a_settled_order_cannot_go_back_to_open(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "settled-reopen")
        order = await _settled_order(db_session, world)

        with pytest.raises(DBAPIError) as raised:
            await _sql(
                db_session, "UPDATE \"order\" SET status = 'open' WHERE id = :id", id=order.id
            )
        assert "immutable" in str(raised.value)

    async def test_a_void_reason_cannot_be_written_without_voiding(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "settled-reason")
        order = await _settled_order(db_session, world)

        with pytest.raises(DBAPIError) as raised:
            await _sql(
                db_session, "UPDATE \"order\" SET cancel_reason = 'x' WHERE id = :id", id=order.id
            )
        assert "only by voiding" in str(raised.value)

    async def test_a_paid_order_can_still_be_served(self, db_session: AsyncSession) -> None:
        """A counter-service restaurant takes the money before it cooks. Freezing every column
        would make the kitchen's own record of serving a paid order impossible."""
        world = await _world(db_session, "settled-served")
        order = await _settled_order(db_session, world)

        await _sql(db_session, 'UPDATE "order" SET served_at = now() WHERE id = :id', id=order.id)

    async def test_a_voided_order_cannot_change_at_all(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "voided-frozen")
        order = await _order(
            db_session, world, status="voided", cancel_reason="wrong table", cancelled_at=_NOW
        )

        with pytest.raises(DBAPIError) as raised:
            await _sql(
                db_session, "UPDATE \"order\" SET cancel_reason = 'y' WHERE id = :id", id=order.id
            )
        assert "cannot change" in str(raised.value)

    async def test_an_order_is_never_deleted(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "order-delete")
        order = await _order(db_session, world)

        with pytest.raises(DBAPIError) as raised:
            await _sql(db_session, 'DELETE FROM "order" WHERE id = :id', id=order.id)
        assert "never deleted" in str(raised.value)

    async def test_a_live_order_is_freely_editable(self, db_session: AsyncSession) -> None:
        """The trigger must not get in the way of an ordinary evening."""
        world = await _world(db_session, "open-edit")
        order = await _order(db_session, world)

        await _sql(
            db_session,
            'UPDATE "order" SET covers = 4, subtotal = 940 WHERE id = :id',
            id=order.id,
        )


class TestAnOrdersRowsFollowIt:
    async def test_a_line_cannot_be_added_to_a_settled_order(
        self, db_session: AsyncSession
    ) -> None:
        """The edit that matters most: a paid bill that quietly grows."""
        world = await _world(db_session, "line-add-settled")
        order = await _settled_order(db_session, world)

        db_session.add(_line(world, order))
        with pytest.raises(DBAPIError) as raised:
            await db_session.flush()
        assert "Cannot add a line" in str(raised.value)

    async def test_a_line_on_a_settled_order_cannot_change(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "line-edit-settled")
        order = await _order(db_session, world)
        line = await _saved_line(db_session, world, order)
        await _settle(db_session, order)

        with pytest.raises(DBAPIError) as raised:
            await _sql(db_session, "UPDATE order_line SET quantity = 1 WHERE id = :id", id=line.id)
        assert "only move through the kitchen" in str(raised.value)

    async def test_a_line_on_a_settled_order_can_still_move_through_the_kitchen(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "line-kitchen-settled")
        order = await _order(db_session, world)
        line = await _saved_line(db_session, world, order, status="sent", sent_at=_NOW)
        await _settle(db_session, order)

        await _sql(db_session, "UPDATE order_line SET status = 'ready' WHERE id = :id", id=line.id)

    async def test_a_line_on_a_settled_order_cannot_be_cancelled(
        self, db_session: AsyncSession
    ) -> None:
        """After payment, taking a dish off is a credit note, not a status."""
        world = await _world(db_session, "line-cancel-settled")
        order = await _order(db_session, world)
        line = await _saved_line(db_session, world, order)
        await _settle(db_session, order)

        with pytest.raises(DBAPIError) as raised:
            await _sql(
                db_session,
                "UPDATE order_line SET status = 'cancelled', cancel_reason = 'x' WHERE id = :id",
                id=line.id,
            )
        assert "only move through the kitchen" in str(raised.value)

    async def test_a_line_cannot_be_moved_into_a_settled_order(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "line-move-settled")
        live = await _order(db_session, world, number="1")
        paid = await _settled_order(db_session, world, number="2")
        line = await _saved_line(db_session, world, live)

        with pytest.raises(DBAPIError) as raised:
            await _sql(
                db_session,
                "UPDATE order_line SET order_id = :to WHERE id = :id",
                to=paid.id,
                id=line.id,
            )
        assert "Cannot add a line" in str(raised.value)

    async def test_a_line_can_move_between_live_orders(self, db_session: AsyncSession) -> None:
        """Split by items."""
        world = await _world(db_session, "line-move-live")
        first = await _order(db_session, world, number="1")
        second = await _order(db_session, world, number="2")
        line = await _saved_line(db_session, world, first)

        await _sql(
            db_session,
            "UPDATE order_line SET order_id = :to WHERE id = :id",
            to=second.id,
            id=line.id,
        )

    async def test_an_unsent_line_can_be_removed(self, db_session: AsyncSession) -> None:
        """A mis-tap the kitchen never saw is not worth an audit trail."""
        world = await _world(db_session, "line-delete-pending")
        order = await _order(db_session, world)
        line = await _saved_line(db_session, world, order)

        await _sql(db_session, "DELETE FROM order_line WHERE id = :id", id=line.id)

    async def test_a_sent_line_cannot_be_removed(self, db_session: AsyncSession) -> None:
        """Deleting a line the kitchen cooked is how a served dish disappears from a bill before
        the bill is printed. After sending, a line is cancelled with a reason."""
        world = await _world(db_session, "line-delete-sent")
        order = await _order(db_session, world)
        line = await _saved_line(db_session, world, order, status="sent", sent_at=_NOW)

        with pytest.raises(DBAPIError) as raised:
            await _sql(db_session, "DELETE FROM order_line WHERE id = :id", id=line.id)
        assert "Only an unsent line" in str(raised.value)

    async def test_a_discount_cannot_be_added_to_a_settled_order(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "discount-add-settled")
        order = await _settled_order(db_session, world)

        db_session.add(
            OrderDiscount(
                restaurant_id=world.restaurant.id,
                order_id=order.id,
                type="comp",
                rate=Decimal("1.0000"),
                amount=Decimal("940.00"),
                reason="regular",
                authorised_by=world.employee.id,
            )
        )
        with pytest.raises(DBAPIError) as raised:
            await db_session.flush()
        assert "Cannot add order_discount" in str(raised.value)

    async def test_a_charge_on_a_settled_order_cannot_be_removed(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "charge-delete-settled")
        order = await _order(db_session, world)
        charge = OrderCharge(
            restaurant_id=world.restaurant.id,
            order_id=order.id,
            type="packaging",
            amount=Decimal("20.00"),
        )
        db_session.add(charge)
        await db_session.flush()
        await _settle(db_session, order)

        with pytest.raises(DBAPIError) as raised:
            await _sql(db_session, "DELETE FROM order_charge WHERE id = :id", id=charge.id)
        assert "cannot change" in str(raised.value)

    async def test_a_modifier_cannot_be_added_to_a_settled_orders_line(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "modifier-add-settled")
        order = await _order(db_session, world)
        line = await _saved_line(db_session, world, order)
        await _settle(db_session, order)

        db_session.add(
            OrderLineModifier(
                restaurant_id=world.restaurant.id,
                order_line_id=line.id,
                modifier_id=world.modifier.id,
                price_delta=Decimal("40.00"),
            )
        )
        with pytest.raises(DBAPIError) as raised:
            await db_session.flush()
        assert "Cannot add a modifier" in str(raised.value)


class TestTheTaxArithmeticIsHeldByTheDatabase:
    async def test_cgst_and_sgst_must_be_equal(self, db_session: AsyncSession) -> None:
        """Each half is computed on the taxable value, never one as the remainder of the other, so
        a paisa of difference is a bug and not a rounding choice."""
        world = await _world(db_session, "gst-unequal")
        order = await _order(db_session, world)

        db_session.add(
            _line(
                world,
                order,
                sgst_amount=Decimal("23.49"),
                tax_amount=Decimal("46.99"),
                line_total=Decimal("986.99"),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_non_gst_line_is_never_split(self, db_session: AsyncSession) -> None:
        """Liquor is outside GST (Article 366(12A)); a CGST figure on it is a wrong bill."""
        world = await _world(db_session, "gst-liquor-split")
        order = await _order(db_session, world)

        db_session.add(_line(world, order, tax_regime="non_gst"))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_non_gst_line_carries_its_state_tax_whole(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "gst-liquor-whole")
        order = await _order(db_session, world)

        await _saved_line(
            db_session,
            world,
            order,
            tax_regime="non_gst",
            cgst_amount=Decimal("0.00"),
            sgst_amount=Decimal("0.00"),
            tax_amount=Decimal("94.00"),
            line_total=Decimal("1034.00"),
        )

    async def test_a_line_total_must_add_up(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "line-total")
        order = await _order(db_session, world)

        db_session.add(_line(world, order, line_total=Decimal("990.00")))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_discount_names_who_authorised_it(self, db_session: AsyncSession) -> None:
        """A comp with no name on it is unanswerable (`docs/security.md` A04)."""
        world = await _world(db_session, "discount-unauthorised")
        order = await _order(db_session, world)

        db_session.add(
            OrderDiscount(
                restaurant_id=world.restaurant.id,
                order_id=order.id,
                type="percentage",
                rate=Decimal("0.1000"),
                amount=Decimal("94.00"),
                reason="regular",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_flat_discount_has_an_amount_and_no_rate(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "discount-shape")
        order = await _order(db_session, world)

        db_session.add(
            OrderDiscount(
                restaurant_id=world.restaurant.id,
                order_id=order.id,
                type="flat",
                rate=Decimal("0.1000"),
                amount=Decimal("94.00"),
                reason="regular",
                authorised_by=world.employee.id,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_service_charge_is_never_mandatory(self, db_session: AsyncSession) -> None:
        """CCPA guidelines of 4 Jul 2022, upheld by the Delhi High Court on 28 Mar 2025."""
        world = await _world(db_session, "service-charge")
        order = await _order(db_session, world)

        db_session.add(
            OrderCharge(
                restaurant_id=world.restaurant.id,
                order_id=order.id,
                type="service_charge",
                amount=Decimal("94.00"),
                is_optional=False,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestAnInvoiceIsALegalDocument:
    async def test_an_issued_invoices_total_cannot_change(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "invoice-edit")
        invoice = await _saved_invoice(db_session, world, await _settled_order(db_session, world))

        with pytest.raises(DBAPIError) as raised:
            await _sql(
                db_session, "UPDATE invoice SET grand_total = 587 WHERE id = :id", id=invoice.id
            )
        assert "immutable" in str(raised.value)

    async def test_an_invoice_can_be_cancelled(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "invoice-cancel")
        invoice = await _saved_invoice(db_session, world, await _settled_order(db_session, world))

        await _sql(
            db_session,
            "UPDATE invoice SET status = 'cancelled', cancelled_at = now(), "
            "cancel_reason = 'billed to the wrong table' WHERE id = :id",
            id=invoice.id,
        )

    async def test_an_invoice_can_be_registered_for_e_invoicing_after_issue(
        self, db_session: AsyncSession
    ) -> None:
        """The IRN arrives after the bill: out of scope in month 1, not blocked by the schema."""
        world = await _world(db_session, "invoice-irn")
        invoice = await _saved_invoice(db_session, world, await _settled_order(db_session, world))

        await _sql(db_session, "UPDATE invoice SET irn = 'a1b2c3' WHERE id = :id", id=invoice.id)

    async def test_a_cancelled_invoice_cannot_change(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "invoice-cancelled-frozen")
        invoice = await _saved_invoice(
            db_session,
            world,
            await _settled_order(db_session, world),
            status="cancelled",
            cancelled_at=_NOW,
            cancel_reason="wrong table",
        )

        with pytest.raises(DBAPIError) as raised:
            await _sql(
                db_session, "UPDATE invoice SET cancel_reason = 'y' WHERE id = :id", id=invoice.id
            )
        assert "cancelled and cannot change" in str(raised.value)

    async def test_an_invoice_is_never_deleted(self, db_session: AsyncSession) -> None:
        """A deleted invoice is a gap in the series, and a gap is what an assessment asks about."""
        world = await _world(db_session, "invoice-delete")
        invoice = await _saved_invoice(db_session, world, await _settled_order(db_session, world))

        with pytest.raises(DBAPIError) as raised:
            await _sql(db_session, "DELETE FROM invoice WHERE id = :id", id=invoice.id)
        assert "never deleted" in str(raised.value)

    async def test_a_tax_invoice_carries_the_suppliers_gstin(
        self, db_session: AsyncSession
    ) -> None:
        """Rule 46(a). A bill charging CGST and SGST with no GSTIN printed on it is a real and
        common defect on Indian restaurant bills; the product must be unable to produce one."""
        world = await _world(db_session, "invoice-gstin")
        order = await _settled_order(db_session, world)

        db_session.add(_invoice(world, order, supplier_gstin=None))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_bill_of_supply_collects_no_tax(self, db_session: AsyncSession) -> None:
        """A composition restaurant may not collect tax from its customers (CGST Act s.10)."""
        world = await _world(db_session, "invoice-bos-tax")
        order = await _settled_order(db_session, world)

        db_session.add(_invoice(world, order, document_type="bill_of_supply"))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_bill_of_supply_without_tax_is_accepted(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "invoice-bos-ok")
        order = await _settled_order(db_session, world)

        await _saved_invoice(
            db_session,
            world,
            order,
            document_type="bill_of_supply",
            cgst_total=Decimal("0.00"),
            sgst_total=Decimal("0.00"),
            grand_total=Decimal("940.00"),
        )

    async def test_an_invoice_number_is_at_most_sixteen_characters(
        self, db_session: AsyncSession
    ) -> None:
        """CGST Rules, Rule 46(b)."""
        world = await _world(db_session, "invoice-length")
        order = await _settled_order(db_session, world)

        db_session.add(_invoice(world, order, invoice_number="TANDOOR/2026-27/000001"))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_sequence_is_used_once_in_a_financial_year(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "invoice-sequence")
        await _saved_invoice(db_session, world, await _settled_order(db_session, world, number="1"))
        second = await _settled_order(db_session, world, number="2")

        db_session.add(_invoice(world, second, invoice_number="2026-27/000001B"))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_the_sequence_restarts_in_a_new_financial_year(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "invoice-new-fy")
        await _saved_invoice(db_session, world, await _settled_order(db_session, world, number="1"))
        second = await _settled_order(db_session, world, number="2")

        await _saved_invoice(
            db_session, world, second, financial_year="2027-28", invoice_number="2027-28/000001"
        )

    async def test_an_order_has_one_invoice(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "invoice-per-order")
        order = await _settled_order(db_session, world)
        await _saved_invoice(db_session, world, order)

        db_session.add(_invoice(world, order, sequence=2, invoice_number="2026-27/000002"))
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestMoneyThatMoved:
    async def test_a_refund_without_a_credit_note_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        """Cash going back with no tax document is a refund the GST return never hears about."""
        world = await _world(db_session, "refund-bare")
        order = await _settled_order(db_session, world)

        db_session.add(_payment(world, order, amount=Decimal("-100.00")))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_refund_against_a_credit_note_is_accepted(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session, "refund-noted")
        order = await _settled_order(db_session, world)
        invoice = await _saved_invoice(db_session, world, order)
        note = CreditNote(
            restaurant_id=world.restaurant.id,
            invoice_id=invoice.id,
            financial_year="2026-27",
            sequence=1,
            credit_note_number="CN/2026-27/0001",
            issued_at=_NOW,
            note_date=_DAY,
            business_date=_DAY,
            reason="the soup was cold",
            issued_by=world.employee.id,
            taxable_total=Decimal("95.24"),
            cgst_total=Decimal("2.38"),
            sgst_total=Decimal("2.38"),
            grand_total=Decimal("100.00"),
        )
        db_session.add(note)
        await db_session.flush()

        db_session.add(
            _payment(
                world,
                order,
                invoice_id=invoice.id,
                credit_note_id=note.id,
                amount=Decimal("-100.00"),
            )
        )
        await db_session.flush()

    async def test_a_payment_cannot_be_edited(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "payment-edit")
        payment = _payment(world, await _settled_order(db_session, world))
        db_session.add(payment)
        await db_session.flush()

        with pytest.raises(DBAPIError) as raised:
            await _sql(db_session, "UPDATE payment SET amount = 587 WHERE id = :id", id=payment.id)
        assert "append-only" in str(raised.value)

    async def test_a_zero_payment_is_refused(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "payment-zero")
        order = await _settled_order(db_session, world)

        db_session.add(_payment(world, order, amount=Decimal("0.00")))
        with pytest.raises(IntegrityError):
            await db_session.flush()


async def _till(session: AsyncSession, world: _World, **extra: Any) -> CashSession:
    till = CashSession(
        restaurant_id=world.restaurant.id,
        status="open",
        opened_at=_NOW,
        opened_by=world.employee.id,
        opening_float=Decimal("2000.00"),
        business_date=_DAY,
        **extra,
    )
    session.add(till)
    await session.flush()
    return till


class TestTheTill:
    async def test_one_open_till_per_restaurant(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "till-one-open")
        await _till(db_session, world)

        with pytest.raises(IntegrityError):
            await _till(db_session, world)

    async def test_a_till_cannot_close_without_its_count(self, db_session: AsyncSession) -> None:
        """A close with no counted cash and no variance is a close nobody can reconcile."""
        world = await _world(db_session, "till-close-incomplete")
        till = await _till(db_session, world)
        till.status = "closed"
        till.closed_at = _NOW

        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_closed_till_cannot_be_edited(self, db_session: AsyncSession) -> None:
        """Otherwise a ₹400 shortage is corrected by typing a different count."""
        world = await _world(db_session, "till-closed-frozen")
        till = await _till(db_session, world)
        await _sql(
            db_session,
            "UPDATE cash_session SET status = 'closed', closed_at = now(), closed_by = :by, "
            "counted_cash = 11600, variance = -400 WHERE id = :id",
            by=world.employee.id,
            id=till.id,
        )

        with pytest.raises(DBAPIError) as raised:
            await _sql(
                db_session, "UPDATE cash_session SET variance = 0 WHERE id = :id", id=till.id
            )
        assert "is closed" in str(raised.value)

    async def test_a_cash_count_cannot_be_edited(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "till-count-frozen")
        till = await _till(db_session, world)
        count = CashCount(
            restaurant_id=world.restaurant.id,
            cash_session_id=till.id,
            denomination=Decimal("500.00"),
            quantity=20,
        )
        db_session.add(count)
        await db_session.flush()

        with pytest.raises(DBAPIError) as raised:
            await _sql(
                db_session, "UPDATE cash_count SET quantity = 21 WHERE id = :id", id=count.id
            )
        assert "append-only" in str(raised.value)


class TestTenantSafetyIsStructural:
    """Composite foreign keys, so a path that never goes through a repository still cannot attach
    one restaurant's order to another restaurant's dish, tax group, modifier or table."""

    async def test_the_three_parent_constraints_exist(self, db_session: AsyncSession) -> None:
        rows = await db_session.execute(
            text("SELECT conname FROM pg_constraint WHERE contype = 'u'")
        )
        names = {row[0] for row in rows.all()}
        assert {
            "uq_menu_item_variant_id_restaurant",
            "uq_modifier_id_restaurant",
            "uq_restaurant_table_id_restaurant",
        } <= names

    async def test_a_line_cannot_order_another_restaurants_dish(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _world(db_session, "tenant-line-mine")
        theirs = await _world(db_session, "tenant-line-theirs")
        order = await _order(db_session, mine)

        db_session.add(_line(mine, order, menu_item_variant_id=theirs.variant.id))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_line_cannot_use_another_restaurants_tax_group(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _world(db_session, "tenant-tax-mine")
        theirs = await _world(db_session, "tenant-tax-theirs")
        order = await _order(db_session, mine)

        db_session.add(_line(mine, order, tax_group_id=theirs.tax_group.id))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_an_order_cannot_sit_at_another_restaurants_table(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _world(db_session, "tenant-table-mine")
        theirs = await _world(db_session, "tenant-table-theirs")
        order = await _order(db_session, mine)

        db_session.add(
            OrderTable(
                restaurant_id=mine.restaurant.id,
                order_id=order.id,
                restaurant_table_id=theirs.table.id,
                is_primary=True,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_line_cannot_take_another_restaurants_modifier(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _world(db_session, "tenant-modifier-mine")
        theirs = await _world(db_session, "tenant-modifier-theirs")
        line = await _saved_line(db_session, mine, await _order(db_session, mine))

        db_session.add(
            OrderLineModifier(
                restaurant_id=mine.restaurant.id,
                order_line_id=line.id,
                modifier_id=theirs.modifier.id,
                price_delta=Decimal("40.00"),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestTheRestaurantDeclaresItsScheme:
    async def test_an_unknown_gst_scheme_is_refused(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "scheme-unknown")
        world.restaurant.gst_scheme = "exempt"

        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_existing_rows_default_to_regular_and_gst(self, db_session: AsyncSession) -> None:
        """The server defaults are what existing restaurants and tax groups receive on upgrade, so
        they are asserted at the database rather than through the models' Python defaults."""
        world = await _world(db_session, "scheme-defaults")
        await _sql(
            db_session,
            "INSERT INTO tax_group (id, restaurant_id, code, name, is_active) "
            "VALUES (gen_random_uuid(), :rid, 'RAW', 'Raw', true)",
            rid=world.restaurant.id,
        )
        regime = await db_session.scalar(
            select(TaxGroup.regime).where(
                TaxGroup.restaurant_id == world.restaurant.id, TaxGroup.code == "RAW"
            )
        )
        column_default = await db_session.scalar(
            text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = 'restaurant' AND column_name = 'gst_scheme'"
            )
        )
        assert regime == "gst"
        assert "regular" in str(column_default)


def _idempotency_key(world: _World, key: str) -> IdempotencyKey:
    return IdempotencyKey(
        restaurant_id=world.restaurant.id,
        key=key,
        endpoint="POST /api/v1/staff/orders/{order_id}/settle",
        request_hash="h",
        state="in_progress",
        expires_at=_NOW,
    )


class TestIdempotencyKeys:
    async def test_a_key_is_used_once_per_restaurant(self, db_session: AsyncSession) -> None:
        """The unique index is the mechanism: a duplicate tap blocks on it, then replays."""
        world = await _world(db_session, "idem-dup")
        db_session.add(_idempotency_key(world, "tap-0001-aaaa-bbbb"))
        await db_session.flush()

        db_session.add(_idempotency_key(world, "tap-0001-aaaa-bbbb"))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_guessable_key_is_refused(self, db_session: AsyncSession) -> None:
        world = await _world(db_session, "idem-short")

        db_session.add(_idempotency_key(world, "1"))
        with pytest.raises(IntegrityError):
            await db_session.flush()
