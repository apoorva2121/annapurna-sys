"""The suppliers, the orders, and the short delivery the seed plants on purpose.

`docs/seed-data.md`'s principle again: a demo requiring the demonstrator to first create the problem
is a demo of an empty product. Somebody opening this app for the first time should find the supplier
variance report already saying *"billed for 10 kg, 9 arrived"* — because that sentence is the whole
commercial argument for M06, and nobody believes it until they see it about their own paneer.

These tests are what stop that quietly disappearing.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PurchaseOrderStatus
from app.core.tenancy import TenantScope
from app.models.identity import Employee
from app.models.procurement import GoodsReceipt, PurchaseOrder, Supplier
from app.models.stock import StockItem
from app.models.tenancy import Organization, Restaurant
from app.repositories.inventory import StockMovementRepository
from app.repositories.procurement import GoodsReceiptRepository
from app.seed.procurement import seed_procurement

# Codes the M04 seed really creates. The seeder is keyed on these, so a test using invented ones
# would pass while the shipped seed planted nothing.
_ITEMS = (
    ("BASMATI", "0.110000"),
    ("ATTA", "0.042000"),
    ("OIL", "0.135000"),
    ("ONION", "0.038000"),
    ("TOMATO", "0.032000"),
    ("PANEER", "0.360000"),
)


async def _restaurant_with_items(session: AsyncSession, slug: str) -> Restaurant:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name=slug.title(),
        code=slug[:3].upper(),
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
    )
    session.add(restaurant)
    await session.flush()
    session.add(
        Employee(
            organization_id=organization.id,
            employee_code=f"{slug[:3].upper()}-1",
            full_name="Store Manager",
            joined_on=date(2026, 1, 1),
            employment_type="full_time",
            is_active=True,
        )
    )
    for code, cost in _ITEMS:
        session.add(
            StockItem(
                restaurant_id=restaurant.id,
                kind="ingredient",
                code=code,
                name=code.title(),
                base_unit="g",
                current_unit_cost=Decimal(cost),
                is_active=True,
            )
        )
    await session.flush()
    return restaurant


async def test_it_plants_a_short_delivery(db_session: AsyncSession) -> None:
    """The report opens with a number, not an empty table."""
    restaurant = await _restaurant_with_items(db_session, "seed-short")

    summary = await seed_procurement(db_session)

    assert summary.short_deliveries_planted == 1
    supplier = (
        await db_session.scalars(
            select(Supplier).where(
                Supplier.restaurant_id == restaurant.id, Supplier.name == "Konkan Fresh Produce"
            )
        )
    ).one()
    receipt = (
        await db_session.scalars(
            select(GoodsReceipt).where(GoodsReceipt.supplier_id == supplier.id)
        )
    ).first()
    assert receipt is not None
    # Two numbers on the record, and they disagree. That disagreement is the product.
    scope = TenantScope(organization_id=restaurant.organization_id, restaurant_id=restaurant.id)
    rows = await GoodsReceiptRepository(db_session, scope).supplier_variance(
        supplier.id, start=receipt.business_date - timedelta(days=1), end=date(2099, 1, 1)
    )
    assert rows, "the planted supplier has no variance rows"
    assert sum(row.short_delivery for row in rows) > 0


async def test_it_leaves_one_order_open_and_one_closed(db_session: AsyncSession) -> None:
    """`partial` is the status that earns the enum, and a demo where every order is closed shows
    none of the work a store manager actually does."""
    await _restaurant_with_items(db_session, "seed-orders")

    summary = await seed_procurement(db_session)

    assert summary.orders_created == 2
    statuses = {order.status for order in (await db_session.scalars(select(PurchaseOrder))).all()}
    assert statuses == {PurchaseOrderStatus.RECEIVED.value, PurchaseOrderStatus.PARTIAL.value}


async def test_it_books_one_delivery_with_no_order_behind_it(db_session: AsyncSession) -> None:
    """The market purchase. Its null `purchase_order_id` is the channel marker M13 will split
    contracted supply from spot buying on."""
    await _restaurant_with_items(db_session, "seed-market")

    await seed_procurement(db_session)

    receipts = (await db_session.scalars(select(GoodsReceipt))).all()
    ad_hoc = [receipt for receipt in receipts if receipt.purchase_order_id is None]
    assert len(ad_hoc) == 1


async def test_the_deliveries_reach_the_stock_ledger(db_session: AsyncSession) -> None:
    """A seeded receipt that wrote no movement would be paperwork with no stock behind it — the
    exact fiction invariant 2 exists to prevent, planted deliberately."""
    restaurant = await _restaurant_with_items(db_session, "seed-ledger")

    await seed_procurement(db_session)

    scope = TenantScope(organization_id=restaurant.organization_id, restaurant_id=restaurant.id)
    rows = await StockMovementRepository(db_session, scope).on_hand()
    assert rows, "the seeded deliveries put nothing on the shelf"
    # Everything that arrived is positive: nothing here consumes.
    assert all(row.quantity > 0 for row in rows)


async def test_it_is_idempotent(db_session: AsyncSession) -> None:
    """Re-running `make seed` must not book a second week of deliveries on top of the first.

    The check is for any supplier rather than a marker row, because a restaurant with suppliers in
    it is one somebody has started using, and re-seeding would write deliveries that never happened
    into a real ledger.
    """
    await _restaurant_with_items(db_session, "seed-twice")

    first = await seed_procurement(db_session)
    second = await seed_procurement(db_session)

    assert first.suppliers_created == 2
    assert second.created_nothing


async def test_a_restaurant_with_no_employee_is_skipped(db_session: AsyncSession) -> None:
    """Every write here is audited with an actor, and inventing one would put a name on the audit
    trail that belongs to nobody."""
    organization = Organization(name="Empty", slug="seed-empty")
    db_session.add(organization)
    await db_session.flush()
    db_session.add(
        Restaurant(
            organization_id=organization.id,
            name="Empty",
            code="EMP",
            timezone="Asia/Kolkata",
            business_day_start=time(5, 0),
        )
    )
    await db_session.flush()

    summary = await seed_procurement(db_session)

    assert summary.created_nothing


async def test_a_restaurant_with_no_stock_items_gets_suppliers_and_no_orders(
    db_session: AsyncSession,
) -> None:
    """The ingredients are M04's, and a branch that has not had its master data loaded yet should
    still end up with somebody to buy from rather than failing the whole seed run."""
    organization = Organization(name="Bare", slug="seed-bare")
    db_session.add(organization)
    await db_session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name="Bare",
        code="BAR",
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
    )
    db_session.add(restaurant)
    await db_session.flush()
    db_session.add(
        Employee(
            organization_id=organization.id,
            employee_code="BAR-1",
            full_name="Store Manager",
            joined_on=date(2026, 1, 1),
            employment_type="full_time",
            is_active=True,
        )
    )
    await db_session.flush()

    summary = await seed_procurement(db_session)

    assert summary.suppliers_created == 2
    assert summary.orders_created == 0
