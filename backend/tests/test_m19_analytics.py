"""M19 chunk A, against data built to make each rule fail if it is wrong.

Same approach as `test_reporting.py`, and for the same reason: a report run over data that happens
to be fine proves nothing. Every fixture here is shaped so that a plausible wrong implementation
produces a visibly different number.

**The tenant tests are the ones that matter.** This chunk widened
`ReportingRepository._real_restaurants()` from one restaurant to several, and that method is what
every M13 aggregate filters through. Widening a tenant filter is invariant 1's blast radius, so the
question these tests answer is not "does the arithmetic work" but **"can a caller reach a branch it
should not by asking for it"** — because `across` is a list built by a service, and a service can
be wrong.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import OrderStatus, OrderType
from app.core.tenancy import TenantScope
from app.models.menu import MenuCategory, MenuItem, MenuItemVariant
from app.models.orders import Invoice, Order, OrderLine
from app.models.setup import Station, TaxGroup
from app.models.tenancy import Organization, Restaurant
from app.repositories.reporting import ReportingRepository
from app.services.analytics import (
    BranchRow,
    Bucket,
    Metric,
    _bucket_value,
    _weeks_back,
    comparison_basis,
)

_DAY = date(2026, 9, 16)


async def _org(session: AsyncSession, *, name: str, is_demo: bool = False) -> Organization:
    organization = Organization(
        name=name, slug=f"{name[:4].lower()}-{uuid.uuid4().hex[:8]}", is_demo=is_demo
    )
    session.add(organization)
    await session.flush()
    return organization


async def _restaurant(session: AsyncSession, organization: Organization, name: str) -> Restaurant:
    restaurant = Restaurant(
        organization_id=organization.id,
        name=name,
        code=f"R{uuid.uuid4().hex[:6]}",
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
    )
    session.add(restaurant)
    await session.flush()
    return restaurant


async def _variant(session: AsyncSession, restaurant: Restaurant) -> MenuItemVariant:
    rid = restaurant.id
    category = MenuCategory(
        restaurant_id=rid, code=f"C{uuid.uuid4().hex[:6]}", name="Mains", seq=0, is_active=True
    )
    tax = TaxGroup(
        restaurant_id=rid, code=f"T{uuid.uuid4().hex[:6]}", name="GST 5%", is_active=True
    )
    station = Station(
        restaurant_id=rid, code=f"ST{uuid.uuid4().hex[:5]}", name="Tandoor", seq=0, is_active=True
    )
    session.add_all([category, tax, station])
    await session.flush()
    item = MenuItem(
        restaurant_id=rid,
        menu_category_id=category.id,
        code=f"D{uuid.uuid4().hex[:6]}",
        name="Paneer Tikka",
        station_id=station.id,
        food_type="veg",
        is_active=True,
        seq=0,
    )
    session.add(item)
    await session.flush()
    variant = MenuItemVariant(
        restaurant_id=rid,
        menu_item_id=item.id,
        code="FULL",
        name="Full",
        price=Decimal("320.00"),
        prep_minutes=12,
        tax_group_id=tax.id,
        is_active=True,
        seq=0,
    )
    session.add(variant)
    await session.flush()
    return variant


async def _sold(
    session: AsyncSession,
    restaurant: Restaurant,
    variant: MenuItemVariant,
    *,
    revenue: str,
    business_date: date = _DAY,
    covers: int | None = 2,
    order_type: OrderType = OrderType.DINE_IN,
) -> None:
    """One settled order and its invoice, built in the order the product builds them.

    `covers=None` is how takeaway and delivery arrive — `ck_order_covers` permits NULL and forbids
    zero, so a takeaway order genuinely has no covers rather than nought of them. That distinction
    is the whole subject of `comparison_basis`.
    """
    rid = restaurant.id
    amount = Decimal(revenue)
    order = Order(
        restaurant_id=rid,
        order_number=f"O{uuid.uuid4().hex[:8]}",
        type=order_type.value,
        channel="pos",
        status=OrderStatus.OPEN.value,
        covers=covers,
        placed_at=datetime(2026, 9, 16, 13, 0, tzinfo=UTC),
        business_date=business_date,
    )
    session.add(order)
    await session.flush()
    session.add(
        OrderLine(
            restaurant_id=rid,
            order_id=order.id,
            menu_item_variant_id=variant.id,
            quantity=1,
            unit_price=amount,
            line_subtotal=amount,
            tax_group_id=variant.tax_group_id,
            tax_rate=Decimal("0.0500"),
            taxable_value=amount,
            tax_amount=Decimal("0.00"),
            line_total=amount,
            theoretical_unit_cost=Decimal("90.00"),
            status="served",
        )
    )
    await session.flush()
    order.status = OrderStatus.SETTLED.value
    order.settled_at = datetime(2026, 9, 16, 14, 0, tzinfo=UTC)
    await session.flush()
    sequence = (
        int(
            await session.scalar(select(func.count(Invoice.id)).where(Invoice.restaurant_id == rid))
            or 0
        )
        + 1
    )
    session.add(
        Invoice(
            restaurant_id=rid,
            order_id=order.id,
            document_type="tax_invoice",
            financial_year="2026-27",
            sequence=sequence,
            invoice_number=f"INV/{uuid.uuid4().hex[:8]}",
            status="issued",
            issued_at=order.settled_at,
            invoice_date=business_date,
            business_date=business_date,
            supplier_name="Spice Garden",
            supplier_gstin="27AAAPA1234A1Z5",
            taxable_total=amount,
            grand_total=amount,
        )
    )
    await session.flush()


# ------------------------------------------------------------------ the tenant boundary


async def test_across_cannot_reach_another_organizations_branch(db_session: AsyncSession) -> None:
    """The point of the chunk. `across` is a list a service builds, and a service can be wrong.

    Asking for another organization's restaurant by id must return **nothing from it** rather than
    its takings — the boundary is inside the query, not in the caller that built the list.
    """
    ours = await _org(db_session, name="Spice Garden Group")
    home = await _restaurant(db_session, ours, "Koregaon Park")
    theirs = await _org(db_session, name="Someone Else Entirely")
    not_ours = await _restaurant(db_session, theirs, "Their Branch")

    await _sold(db_session, home, await _variant(db_session, home), revenue="1000.00")
    await _sold(db_session, not_ours, await _variant(db_session, not_ours), revenue="9999.00")

    scope = TenantScope(organization_id=ours.id, restaurant_id=home.id)
    repository = ReportingRepository(db_session, scope, across=[home.id, not_ours.id])
    rows = await repository.sales_by_branch(since=_DAY, until=_DAY)

    assert [row.name for row in rows] == ["Koregaon Park"]
    assert sum(row.revenue for row in rows) == Decimal("1000.00")


async def test_across_none_is_exactly_the_old_behaviour(db_session: AsyncSession) -> None:
    """Every M13 caller passes nothing, and must keep seeing one restaurant."""
    organization = await _org(db_session, name="Spice Garden Group")
    home = await _restaurant(db_session, organization, "Koregaon Park")
    sibling = await _restaurant(db_session, organization, "Baner")
    await _sold(db_session, home, await _variant(db_session, home), revenue="1000.00")
    await _sold(db_session, sibling, await _variant(db_session, sibling), revenue="500.00")

    scope = TenantScope(organization_id=organization.id, restaurant_id=home.id)
    rows = await ReportingRepository(db_session, scope).sales_by_day(since=_DAY, until=_DAY)

    assert [row.revenue for row in rows] == [Decimal("1000.00")]


async def test_a_demo_organization_is_still_excluded_when_widened(db_session: AsyncSession) -> None:
    """Widening must not become a way round the demo filter."""
    demo = await _org(db_session, name="Demo Group", is_demo=True)
    one = await _restaurant(db_session, demo, "Demo One")
    two = await _restaurant(db_session, demo, "Demo Two")
    await _sold(db_session, one, await _variant(db_session, one), revenue="1000.00")

    scope = TenantScope(organization_id=demo.id, restaurant_id=one.id)
    repository = ReportingRepository(db_session, scope, across=[one.id, two.id])

    assert await repository.sales_by_branch(since=_DAY, until=_DAY) == []


# ------------------------------------------------------------------ the branch comparison


async def test_takeaway_revenue_never_lands_on_a_dine_in_guest(db_session: AsyncSession) -> None:
    """The defect the owner's chosen basis would have shipped with.

    One branch, ₹1,000 of dine-in across 2 covers and ₹5,000 of delivery with no covers at all.
    Spend per guest is ₹500. The obvious implementation — total revenue over covers — says ₹3,000,
    which is not a sum anybody at that table paid, and would rank this branch best in the group.
    """
    organization = await _org(db_session, name="Spice Garden Group")
    branch = await _restaurant(db_session, organization, "Koregaon Park")
    variant = await _variant(db_session, branch)
    await _sold(db_session, branch, variant, revenue="1000.00", covers=2)
    await _sold(
        db_session, branch, variant, revenue="5000.00", covers=None, order_type=OrderType.DELIVERY
    )

    scope = TenantScope(organization_id=organization.id, restaurant_id=branch.id)
    rows = await ReportingRepository(db_session, scope).sales_by_branch(since=_DAY, until=_DAY)
    row = rows[0]

    assert row.revenue == Decimal("6000.00")
    assert row.dine_in_revenue == Decimal("1000.00")
    assert row.covers == 2

    basis = comparison_basis(
        BranchRow(
            restaurant_id=row.restaurant_id,
            name=row.name,
            revenue=row.revenue,
            dine_in_revenue=row.dine_in_revenue,
            covers=row.covers,
            orders=row.orders,
            business_days_traded=row.business_days_traded,
            revenue_per_trading_day=None,
        )
    )
    assert basis == Decimal("500.00")
    assert basis != (row.revenue / row.covers).quantize(Decimal("0.01"))


async def test_business_days_traded_counts_days_not_the_window(db_session: AsyncSession) -> None:
    """Decision 1.3: a branch shut for most of the window must not look like a soft month."""
    organization = await _org(db_session, name="Spice Garden Group")
    branch = await _restaurant(db_session, organization, "Kalyani Nagar")
    variant = await _variant(db_session, branch)
    await _sold(db_session, branch, variant, revenue="1000.00", business_date=date(2026, 9, 14))
    await _sold(db_session, branch, variant, revenue="1000.00", business_date=date(2026, 9, 15))

    scope = TenantScope(organization_id=organization.id, restaurant_id=branch.id)
    rows = await ReportingRepository(db_session, scope).sales_by_branch(
        since=date(2026, 9, 1), until=date(2026, 9, 30)
    )

    # Two days traded out of a thirty-day window.
    assert rows[0].business_days_traded == 2


def test_branch_rows_carry_no_tax_at_all() -> None:
    """Decision 1.2, enforced structurally rather than by a comment asking nicely.

    The rule is that nothing tax-shaped sums across branches. The cheapest way to keep a total that
    must not exist from existing is to never select the column it would be summed from, so this
    test guards the *absence* of a field — which no arithmetic test would ever notice.
    """
    from app.repositories.reporting import BranchSales
    from app.services.analytics import BranchComparison

    for model in (BranchSales, BranchRow, BranchComparison):
        fields = set(model.__annotations__)
        assert not {name for name in fields if "tax" in name or "gst" in name}, model


# ------------------------------------------------------------------ the buckets


def test_weeks_are_anchored_to_the_end_so_the_newest_is_whole() -> None:
    """An owner comparing this week against a ragged week at the *start* of the window is being
    shown a fall that is not there. The ragged bucket belongs at the old end."""
    buckets = _weeks_back(date(2026, 9, 1), date(2026, 9, 20))

    assert buckets[-1] == (date(2026, 9, 14), date(2026, 9, 20))
    assert buckets[-2] == (date(2026, 9, 7), date(2026, 9, 13))
    # The oldest is the short one: five days, not seven.
    assert buckets[0] == (date(2026, 9, 1), date(2026, 9, 6))
    assert buckets == sorted(buckets)


def test_a_single_day_window_is_one_bucket() -> None:
    assert _weeks_back(_DAY, _DAY) == [(_DAY, _DAY)]


def test_average_bill_is_undefined_rather_than_zero_when_nothing_sold() -> None:
    """Rendering ₹0.00 draws a line through the floor on a day the restaurant was closed."""
    assert _bucket_value(Metric.AVERAGE_BILL, []) is None
    assert _bucket_value(Metric.REVENUE, []) is None


def test_the_series_metrics_are_the_ones_the_metric_table_names() -> None:
    """A member added to `Metric` without a row in the build log's metric table is exactly what
    that table exists to prevent. `tax` is absent deliberately — it does not sum."""
    assert {metric.value for metric in Metric} == {
        "revenue",
        "covers",
        "orders",
        "discounts",
        "average_bill",
    }
    assert {bucket.value for bucket in Bucket} == {"day", "week"}
