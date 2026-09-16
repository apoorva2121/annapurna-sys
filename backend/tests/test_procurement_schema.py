"""The guarantees migration 0017 makes at the database, not in a service.

Every rule here must hold when a future path forgets to ask — a migration, a seed script, psql —
so every one is asserted against a real Postgres rather than against a repository's good
intentions. If a receipt can be edited after it posted, the supplier variance report is a story
rather than a record.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.stock import StockItem
from app.models.tenancy import Organization, Restaurant


async def _restaurant(session: AsyncSession, slug: str) -> Restaurant:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id, name=slug.title(), code=slug[:2].upper()
    )
    session.add(restaurant)
    await session.flush()
    return restaurant


async def _supplier(
    session: AsyncSession, restaurant: Restaurant, name: str = "Sharma"
) -> Supplier:
    supplier = Supplier(restaurant_id=restaurant.id, name=name)
    session.add(supplier)
    await session.flush()
    return supplier


async def _item(session: AsyncSession, restaurant: Restaurant, code: str = "PANEER") -> StockItem:
    item = StockItem(
        restaurant_id=restaurant.id,
        kind="ingredient",
        code=code,
        name=code.title(),
        base_unit="g",
        current_unit_cost=Decimal("0.360000"),
        is_active=True,
    )
    session.add(item)
    await session.flush()
    return item


async def _order(
    session: AsyncSession, restaurant: Restaurant, supplier: Supplier, *, number: str = "PO-000001"
) -> PurchaseOrder:
    order = PurchaseOrder(
        restaurant_id=restaurant.id,
        supplier_id=supplier.id,
        po_number=number,
        status="draft",
        total_amount=Decimal("0.00"),
    )
    session.add(order)
    await session.flush()
    return order


async def _receipt(
    session: AsyncSession,
    restaurant: Restaurant,
    supplier: Supplier,
    *,
    invoice_number: str | None = None,
) -> GoodsReceipt:
    receipt = GoodsReceipt(
        restaurant_id=restaurant.id,
        supplier_id=supplier.id,
        received_at=datetime.now(UTC),
        business_date=date(2026, 9, 13),
        invoice_number=invoice_number,
    )
    session.add(receipt)
    await session.flush()
    return receipt


class TestAReceiptIsAppendOnly:
    """The threat, not the taxonomy.

    A receipt writes stock movements that 0015's trigger already refuses to change. If the receipt
    stayed editable, the attack is one `UPDATE`: weigh 47, take 3 home, edit the receipt to say 50
    so the invoice reconciles. Two records would then disagree with nothing able to say which had
    been altered.
    """

    async def test_updating_a_receipt_is_refused(self, db_session: AsyncSession) -> None:
        restaurant = await _restaurant(db_session, "gr-append-one")
        receipt = await _receipt(db_session, restaurant, await _supplier(db_session, restaurant))

        with pytest.raises(DBAPIError) as raised:
            await db_session.execute(
                text("UPDATE goods_receipt SET invoice_number = 'X' WHERE id = :id"),
                {"id": receipt.id},
            )
        assert "append-only" in str(raised.value)
        # The message names the remedy, because whoever hits this is mid-change and needs to know
        # what to do instead of merely that they may not.
        assert "stock adjustment" in str(raised.value)

    async def test_deleting_a_receipt_is_refused(self, db_session: AsyncSession) -> None:
        restaurant = await _restaurant(db_session, "gr-append-two")
        receipt = await _receipt(db_session, restaurant, await _supplier(db_session, restaurant))

        with pytest.raises(DBAPIError) as raised:
            await db_session.execute(
                text("DELETE FROM goods_receipt WHERE id = :id"), {"id": receipt.id}
            )
        assert "append-only" in str(raised.value)

    async def test_updating_a_receipt_line_is_refused(self, db_session: AsyncSession) -> None:
        """The line is where the quantities live, so the line is what an insider would edit."""
        restaurant = await _restaurant(db_session, "gr-append-three")
        supplier = await _supplier(db_session, restaurant)
        item = await _item(db_session, restaurant)
        receipt = await _receipt(db_session, restaurant, supplier)
        line = GoodsReceiptLine(
            restaurant_id=restaurant.id,
            goods_receipt_id=receipt.id,
            stock_item_id=item.id,
            quantity_invoiced=Decimal("50000.0000"),
            quantity_received=Decimal("47000.0000"),
            unit_price=Decimal("0.042000"),
        )
        db_session.add(line)
        await db_session.flush()

        with pytest.raises(DBAPIError) as raised:
            await db_session.execute(
                text("UPDATE goods_receipt_line SET quantity_received = 50000 WHERE id = :id"),
                {"id": line.id},
            )
        assert "append-only" in str(raised.value)


class TestTenantSafetyIsStructural:
    """Everywhere else cross-tenant leakage is prevented by a repository taking the scope. Here it
    is prevented by a composite foreign key, so it holds for a path that never goes through one."""

    async def test_an_order_cannot_reference_another_restaurants_supplier(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _restaurant(db_session, "po-mine")
        theirs = await _restaurant(db_session, "po-theirs")
        their_supplier = await _supplier(db_session, theirs, name="Rival Traders")

        db_session.add(
            PurchaseOrder(
                restaurant_id=mine.id,
                supplier_id=their_supplier.id,
                po_number="PO-000001",
                status="draft",
                total_amount=Decimal("0.00"),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_an_order_line_cannot_reference_another_restaurants_item(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _restaurant(db_session, "pol-mine")
        theirs = await _restaurant(db_session, "pol-theirs")
        order = await _order(db_session, mine, await _supplier(db_session, mine))
        their_item = await _item(db_session, theirs, code="RIVAL")

        db_session.add(
            PurchaseOrderLine(
                restaurant_id=mine.id,
                purchase_order_id=order.id,
                stock_item_id=their_item.id,
                quantity_ordered=Decimal("1000.0000"),
                unit_price=Decimal("0.042000"),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_receipt_line_cannot_reference_another_restaurants_item(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _restaurant(db_session, "grl-mine")
        theirs = await _restaurant(db_session, "grl-theirs")
        receipt = await _receipt(db_session, mine, await _supplier(db_session, mine))
        their_item = await _item(db_session, theirs, code="RIVAL")

        db_session.add(
            GoodsReceiptLine(
                restaurant_id=mine.id,
                goods_receipt_id=receipt.id,
                stock_item_id=their_item.id,
                quantity_invoiced=Decimal("1000.0000"),
                quantity_received=Decimal("1000.0000"),
                unit_price=Decimal("0.042000"),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestTheConstraintsThatCatchNonsense:
    async def test_one_supplier_invoice_cannot_be_booked_twice(
        self, db_session: AsyncSession
    ) -> None:
        """The most ordinary error in accounts payable and the most ordinary small fraud.

        It also silently doubles the stock the invoice brought in, which makes every food-cost
        figure built on it wrong by considerably more than the money.
        """
        restaurant = await _restaurant(db_session, "inv-dup")
        supplier = await _supplier(db_session, restaurant)
        await _receipt(db_session, restaurant, supplier, invoice_number="4471")

        # Added without the helper's flush, so the violation happens inside `raises` rather than
        # on the way in.
        db_session.add(
            GoodsReceipt(
                restaurant_id=restaurant.id,
                supplier_id=supplier.id,
                received_at=datetime.now(UTC),
                business_date=date(2026, 9, 14),
                invoice_number="4471",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_two_receipts_with_no_invoice_number_are_both_allowed(
        self, db_session: AsyncSession
    ) -> None:
        """The index is partial because a market purchase arrives with no paperwork at all, and
        two vegetable runs in one week must not collide on a shared NULL."""
        restaurant = await _restaurant(db_session, "inv-null")
        supplier = await _supplier(db_session, restaurant)
        await _receipt(db_session, restaurant, supplier)
        await _receipt(db_session, restaurant, supplier)
        await db_session.flush()

    async def test_more_cannot_be_rejected_than_arrived(self, db_session: AsyncSession) -> None:
        """Reject 50 of 50 and keep the "rejected" stock is a real theft route. Refusing *more*
        than arrived is the arithmetic half of closing it."""
        restaurant = await _restaurant(db_session, "reject-over")
        supplier = await _supplier(db_session, restaurant)
        item = await _item(db_session, restaurant)
        receipt = await _receipt(db_session, restaurant, supplier)

        db_session.add(
            GoodsReceiptLine(
                restaurant_id=restaurant.id,
                goods_receipt_id=receipt.id,
                stock_item_id=item.id,
                quantity_invoiced=Decimal("1000.0000"),
                quantity_received=Decimal("900.0000"),
                quantity_rejected=Decimal("950.0000"),
                rejection_reason="mouldy",
                unit_price=Decimal("0.042000"),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_rejection_needs_a_reason(self, db_session: AsyncSession) -> None:
        restaurant = await _restaurant(db_session, "reject-reason")
        supplier = await _supplier(db_session, restaurant)
        item = await _item(db_session, restaurant)
        receipt = await _receipt(db_session, restaurant, supplier)

        db_session.add(
            GoodsReceiptLine(
                restaurant_id=restaurant.id,
                goods_receipt_id=receipt.id,
                stock_item_id=item.id,
                quantity_invoiced=Decimal("1000.0000"),
                quantity_received=Decimal("1000.0000"),
                quantity_rejected=Decimal("100.0000"),
                unit_price=Decimal("0.042000"),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_line_delivering_nothing_is_allowed(self, db_session: AsyncSession) -> None:
        """*"They billed 50 kg and delivered nothing for this line"* is a real and important row,
        and it is the whole point of storing invoiced separately from received."""
        restaurant = await _restaurant(db_session, "gr-zero")
        supplier = await _supplier(db_session, restaurant)
        item = await _item(db_session, restaurant)
        receipt = await _receipt(db_session, restaurant, supplier)

        db_session.add(
            GoodsReceiptLine(
                restaurant_id=restaurant.id,
                goods_receipt_id=receipt.id,
                stock_item_id=item.id,
                quantity_invoiced=Decimal("50000.0000"),
                quantity_received=Decimal("0.0000"),
                unit_price=Decimal("0.042000"),
            )
        )
        await db_session.flush()

    async def test_a_cancellation_cannot_be_left_unexplained(
        self, db_session: AsyncSession
    ) -> None:
        """A cancellation nobody has to explain is exactly the one somebody would use to make an
        over-order disappear."""
        restaurant = await _restaurant(db_session, "po-cancel")
        order = await _order(db_session, restaurant, await _supplier(db_session, restaurant))
        order.status = "cancelled"
        order.cancelled_at = datetime.now(UTC)

        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_one_supplier_name_per_restaurant(self, db_session: AsyncSession) -> None:
        """Two spellings of one business are two rows whose deliveries cannot be summed, and a
        variance report split across them understates the leak."""
        restaurant = await _restaurant(db_session, "supplier-dup")
        await _supplier(db_session, restaurant, name="Sharma Traders")

        db_session.add(Supplier(restaurant_id=restaurant.id, name="Sharma Traders"))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_an_item_appears_once_on_an_order(self, db_session: AsyncSession) -> None:
        """Also what makes the receipt-to-order-line match exact without a second foreign key."""
        restaurant = await _restaurant(db_session, "pol-dup")
        order = await _order(db_session, restaurant, await _supplier(db_session, restaurant))
        item = await _item(db_session, restaurant)
        for _ in range(2):
            db_session.add(
                PurchaseOrderLine(
                    restaurant_id=restaurant.id,
                    purchase_order_id=order.id,
                    stock_item_id=item.id,
                    quantity_ordered=Decimal("1000.0000"),
                    unit_price=Decimal("0.042000"),
                )
            )
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestTheForeignKeysM05CouldNotCreate:
    """`stock_batch.supplier_id` and `goods_receipt_line_id` were bare uuid columns from 0015 until
    the tables they point at existed. `docs/schema.md` §5 asked for the constraints here."""

    async def test_both_constraints_exist(self, db_session: AsyncSession) -> None:
        rows = await db_session.execute(
            text(
                "SELECT conname FROM pg_constraint "
                " WHERE conrelid = 'stock_batch'::regclass AND contype = 'f'"
            )
        )
        names = {row[0] for row in rows.all()}
        assert "fk_stock_batch_supplier_tenant" in names
        assert "fk_stock_batch_gr_line_tenant" in names

    async def test_a_batch_cannot_claim_another_restaurants_supplier(
        self, db_session: AsyncSession
    ) -> None:
        """The composite form is what matters. A plain `supplier_id` foreign key would have been
        satisfied by any supplier anywhere, including a competitor's."""
        from app.models.inventory import StockBatch

        mine = await _restaurant(db_session, "batch-mine")
        theirs = await _restaurant(db_session, "batch-theirs")
        item = await _item(db_session, mine)
        their_supplier = await _supplier(db_session, theirs, name="Rival Traders")

        db_session.add(
            StockBatch(
                restaurant_id=mine.id,
                stock_item_id=item.id,
                batch_code="B1",
                quantity_received=Decimal("1000.0000"),
                unit_cost=Decimal("0.042000"),
                received_at=datetime.now(UTC),
                source="purchase",
                supplier_id=their_supplier.id,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()
