"""The four generic suites (docs/testing-strategy.md).

These do not test M01. They enumerate the application and assert a property of *every* route, so a
route added in M07 is covered the moment it is registered and nobody has to remember. That is the
whole point: per-endpoint security tests protect the endpoints somebody thought about.

    1. Tenant isolation   — restaurant A cannot read, write or confirm restaurant B's resources
    2. Permission matrix  — every route x every role, against the declared catalogue
    3. Persona separation — no guest token reaches a staff route (ADR 0009)
    4. Route declaration  — every route declares a permission; default-deny is enforced

Suite 0 is the meta-test below, and it is not optional: all four suites assert "for every route
in ...", so an enumerator returning nothing makes every one of them pass while testing nothing.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import PUBLIC_ROUTES
from app.core.config import get_settings
from app.core.enums import EmploymentType, TableStatus, UserAccountStatus
from app.core.permissions import CATALOGUE, permissions_for_role
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee, UserAccount
from app.models.inventory import StockCount, StockCountLine
from app.models.menu import (
    MenuCategory,
    MenuItem,
    MenuItemVariant,
    Modifier,
    ModifierGroup,
)
from app.models.orders import Invoice, Order, OrderCharge, OrderDiscount, OrderLine
from app.models.procurement import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.setup import DiningArea, RestaurantTable, Station, TaxGroup, TaxRate
from app.models.stock import IngredientProfile, Recipe, RecipeLine, StockItem
from app.models.tenancy import Organization, Restaurant
from tests.helpers.routes import RouteInfo, all_routes, staff_routes

PASSWORD = "Staging#2026"  # noqa: S105

# Routes that legitimately take no permission, because they are what produces the identity a
# permission would be checked against. Kept small and explicit — an allow-list of four is
# auditable, whereas "skip routes without a marker" would hide every mistake.
_PUBLIC = PUBLIC_ROUTES | {
    "GET /api/v1/health",
    "GET /api/v1/ready",
    "GET /api/v1/version",
    # Authenticated, but every signed-in employee may read their own profile — there is no
    # permission that could gate it without gating the thing that reports permissions.
    "GET /api/v1/auth/me",
    "POST /api/v1/auth/password",
    # Authenticated, and authorises itself: whether someone may move to a branch depends on where
    # they are employed, which no single permission string can express. The refusal is tested
    # directly in tests/test_auth_switch.py against a two-organization, two-branch fixture (G-17).
    "POST /api/v1/auth/switch",
}


# --------------------------------------------------------------------------- suite 0


class TestTheEnumeratorItself:
    """Not one of the four. It is what stops the other four becoming decorative.

    Every suite below is a loop over routes. If the loop body never runs, the suite passes. This
    class asserts the loop has something to iterate, so a FastAPI upgrade that changes the routing
    internals fails here — loudly, in one place — rather than silently disarming the security
    tests for the rest of the project.
    """

    def test_the_enumerator_finds_routes(self, api: FastAPI) -> None:
        assert len(all_routes(api)) >= 15

    def test_the_enumerator_finds_the_staff_routes(self, api: FastAPI) -> None:
        assert len(staff_routes(api)) >= 8

    def test_the_enumerator_reads_a_declared_permission(self, api: FastAPI) -> None:
        # If permission extraction silently returned () for everything, suite 4 would pass by
        # treating every route as public and suite 2 would have nothing to check.
        listing = next(
            route
            for route in staff_routes(api)
            if route.path == "/api/v1/staff/employees" and route.method == "GET"
        )
        assert listing.permissions == ("employee.view",)

    def test_the_enumerator_finds_the_known_endpoints(self, api: FastAPI) -> None:
        keys = {route.key for route in all_routes(api)}
        for expected in (
            "POST /api/v1/auth/login",
            "POST /api/v1/auth/refresh",
            "GET /api/v1/auth/me",
            "GET /api/v1/staff/employees",
            "POST /api/v1/staff/employees",
            "POST /api/v1/staff/employees/{employee_id}/roles",
            "GET /api/v1/staff/roles",
        ):
            assert expected in keys, f"{expected} missing; enumerator or routing changed"


# --------------------------------------------------------------------------- suite 4


class TestEveryRouteDeclaresAPermission:
    """Suite 4. Default-deny, enforced by the build rather than by review."""

    def test_no_staff_route_is_missing_a_permission(self, api: FastAPI) -> None:
        undeclared = [
            route.key
            for route in staff_routes(api)
            if not route.permissions and route.key not in _PUBLIC
        ]
        assert not undeclared, (
            f"these routes declare no permission and are not on the public allow-list: {undeclared}"
        )

    def test_every_declared_permission_exists_in_the_catalogue(self, api: FastAPI) -> None:
        # A route requiring a permission no role can hold reads as "mysteriously denied" rather
        # than as an error, and would survive review indefinitely.
        known = {permission.code for permission in CATALOGUE.permissions}
        for route in all_routes(api):
            unknown = set(route.permissions) - known
            assert not unknown, f"{route.key} requires unknown permission(s) {sorted(unknown)}"

    def test_the_public_allow_list_has_no_stale_entries(self, api: FastAPI) -> None:
        # An entry left behind after a route is renamed silently exempts nothing — but the next
        # person reads it as "this path is intentionally public", which is worse than useless.
        keys = {route.key for route in all_routes(api)}
        assert not (_PUBLIC - keys), f"allow-list names routes that do not exist: {_PUBLIC - keys}"


# --------------------------------------------------------------------------- fixtures


class Tenant:
    def __init__(self, organization: Organization, restaurant: Restaurant) -> None:
        self.organization = organization
        self.restaurant = restaurant
        self.tokens: dict[str, str] = {}


async def _tenant(session: AsyncSession, slug: str, roles: tuple[str, ...]) -> Tenant:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(organization_id=organization.id, name=slug.title(), code="R1")
    session.add(restaurant)
    await session.flush()
    tenant = Tenant(organization, restaurant)

    for index, role_code in enumerate(roles):
        role = (
            await session.scalars(
                select(Role).where(Role.code == role_code, Role.organization_id.is_(None))
            )
        ).first()
        assert role is not None, f"system role {role_code} was not seeded"
        account = UserAccount(
            organization_id=organization.id,
            email=f"{role_code}@{slug}.test",
            password_hash=hash_password(PASSWORD),
            status=UserAccountStatus.ACTIVE,
        )
        session.add(account)
        await session.flush()
        employee = Employee(
            organization_id=organization.id,
            user_account_id=account.id,
            employee_code=f"E{index:03d}",
            full_name=f"{role_code.title()} Person",
            joined_on=date(2026, 1, 1),
            employment_type=EmploymentType.FULL_TIME,
        )
        session.add(employee)
        await session.flush()
        session.add(
            EmployeeRoleAssignment(
                employee_id=employee.id, restaurant_id=restaurant.id, role_id=role.id
            )
        )
        await session.flush()
    return tenant


def _guest_token() -> str:
    """A structurally valid token from the guest realm (ADR 0009).

    Signed with the real key on purpose: a token that failed signature verification would be
    rejected for the wrong reason and would prove nothing about persona separation.
    """
    settings = get_settings()
    return jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "typ": "guest",
            "table": "T4",
            "exp": datetime.now(UTC) + timedelta(minutes=15),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def _sample_body(route: RouteInfo) -> dict[str, Any]:
    """Enough of a body to get past validation and reach authorisation.

    A 422 would mean the request never reached the permission check, and the suite would be
    asserting nothing while looking green.
    """
    if route.path.endswith("/roles"):
        return {"role_ids": []}
    if route.path.endswith("/password"):
        return {"new_password": "SomeNewPassword#1"}
    if route.method == "POST" and route.path == "/api/v1/staff/employees":
        return {
            "full_name": "Probe Person",
            "employee_code": "PROBE1",
            "joined_on": "2026-01-01",
        }
    if route.path.endswith("/auth/switch"):
        return {"restaurant_id": str(_PROBE_UUID)}
    # M06. Each of these has to get *past validation* to reach the permission check; a 422 would
    # mean the suite asserted nothing while looking green.
    if route.path.endswith("/suppliers"):
        return {"name": "Probe Traders"}
    if route.path.endswith("/purchase-orders"):
        return {
            "supplier_id": str(_PROBE_UUID),
            "lines": [
                {
                    "stock_item_id": str(_PROBE_UUID),
                    "quantity_ordered": "1000.0000",
                    "unit_price": "0.042000",
                }
            ],
        }
    # M07. Every order change carries the version it read (ADR 0010), so each body needs one to
    # get past validation. The order-cancel branch sits above the generic `/cancel` for that.
    if route.path.endswith("/orders"):
        return {"type": "takeaway"}
    if route.path.endswith("/lines"):
        return {"version": 1, "menu_item_variant_id": str(_PROBE_UUID), "quantity": 1}
    if "/orders/" in route.path and route.path.endswith("/cancel"):
        return {"version": 1, "reason": "Probe cancellation"}
    if route.path.endswith("/discounts"):
        return {"version": 1, "type": "percentage", "rate": "0.1000", "reason": "Probe discount"}
    if route.path.endswith("/charges"):
        return {"version": 1, "type": "packaging", "amount": "20.00"}
    if route.path.endswith("/split"):
        return {"version": 1, "line_ids": [str(_PROBE_UUID)]}
    if route.path.endswith("/settle"):
        return {"version": 1, "payments": [{"method": "cash", "amount": "1.00"}]}
    if route.path.endswith("/credit-notes"):
        return {
            "reason": "Probe credit note",
            "lines": [{"order_line_id": str(_PROBE_UUID), "quantity": 1}],
        }
    if route.path.endswith("/remove"):
        return {"version": 1, "reason": "Probe removal"}
    if "/orders/" in route.path and route.method == "PATCH":
        return {"version": 1, "quantity": 2}
    if route.path.endswith(("/send", "/served", "/bill")) and "/orders/" in route.path:
        return {"version": 1}
    if route.path.endswith("/status"):
        return {"status": "reserved"}
    if route.path.endswith("/cancel"):
        return {"reason": "Probe cancellation"}
    if route.path.endswith("/receive"):
        return {"lines": [_PROBE_RECEIPT_LINE]}
    if route.path.endswith("/goods-receipts"):
        return {"supplier_id": str(_PROBE_UUID), "lines": [_PROBE_RECEIPT_LINE]}
    if "/suppliers/" in route.path and route.method == "PATCH":
        return {"contact_person": "Probe Person"}
    if "/purchase-orders/" in route.path and route.method == "PATCH":
        return {"expected_at": "2099-01-01T00:00:00Z"}
    if route.path.endswith("/setup/dining-areas"):
        return {"name": "Probe Area"}
    if route.path.endswith("/setup/tables"):
        return {"dining_area_id": str(_PROBE_UUID), "code": "P1", "seats": 2}
    if route.path.endswith("/setup/stations"):
        return {"code": "probe_station", "name": "Probe Station"}
    if route.path.endswith("/setup/tax-groups"):
        return {
            "code": "PROBETAX",
            "name": "Probe Tax",
            "rate": "0.0500",
            "effective_from": "2099-01-01",
        }
    if route.path.endswith("/rates"):
        return {"rate": "0.1200", "effective_from": "2099-06-01"}
    if "/setup/tax-groups/" in route.path or "/setup/dining-areas/" in route.path:
        return {"name": "Probe Rename"}
    if "/setup/stations/" in route.path:
        return {"name": "Probe Rename"}
    if "/setup/tables/" in route.path:
        return {"seats": 4}
    if route.method == "PATCH":
        return {"full_name": "Probe Person"}
    return {}


_PROBE_UUID = uuid.UUID("00000000-0000-0000-0000-0000000000ff")

# One delivered line, shaped to pass validation. `quantity_rejected` is absent rather than zero so
# the schema's own default is exercised by the probe as well.
_PROBE_RECEIPT_LINE = {
    "stock_item_id": str(_PROBE_UUID),
    "quantity_invoiced": "1000.0000",
    "quantity_received": "1000.0000",
    "unit_price": "0.042000",
}

# Every path parameter the staff surface uses, and the victim resource each one addresses.
#
# **A parameter missing from this map fails suite 1 rather than being skipped**, which is the whole
# point of the map existing. The previous version of the suite matched `{employee_id}` and
# `continue`d past everything else; when M02 added four PATCH routes taking `{area_id}`,
# `{table_id}`, `{station_id}` and `{tax_group_id}`, the suite went on passing while probing none of
# them — the four routes where a cross-tenant *write* would happen. A future module adding
# `{menu_item_id}` now gets a failing build telling it to seed a victim row here.
_VICTIM_PARAMETERS = frozenset(
    {
        "employee_id",
        "area_id",
        "table_id",
        "station_id",
        "tax_group_id",
        # M03. The suite refused the build the moment these routes were registered without victim
        # rows, which is exactly what the paragraph above predicted it would do.
        "category_id",
        "item_id",
        "variant_id",
        "group_id",
        "modifier_id",
        # M04. The suite refused the build the moment `/recipes/{recipe_id}/confirm` registered.
        "recipe_id",
        # M05. It refused again for these two, and the probe it then ran found a real leak:
        # `/stock/items/{stock_item_id}/movements` answered 200 for another tenant's item id.
        "stock_item_id",
        "count_id",
        # M06. A supplier list is who you buy from and what you pay, and a goods receipt is what
        # you were short of last Tuesday: reading another restaurant's is a direct commercial leak
        # as well as a tenant one.
        "supplier_id",
        "po_id",
        "receipt_id",
        # M07. An order and a line of another restaurant's: the bill somebody would most want
        # to read, and the one a cross-tenant write would most damage.
        "order_id",
        "line_id",
        "discount_id",
        "charge_id",
        "invoice_id",
    }
)


async def _victim_resources(
    session: AsyncSession,
    tenant: Tenant,
    *,
    prefix: str = "Victim",
    seq: int = 0,
    code: str = "V1",
    tax_code: str | None = None,
) -> dict[str, str]:
    """One row of every tenant-owned kind, belonging to the victim restaurant.

    These are the things another tenant must not be able to read, write or confirm the existence
    of. Created directly rather than through the API so the fixture does not depend on the
    endpoints it is about to probe.
    """
    restaurant_id = tenant.restaurant.id
    area = DiningArea(restaurant_id=restaurant_id, name=f"{prefix} Hall", seq=seq, is_active=True)
    station = Station(
        restaurant_id=restaurant_id,
        code=f"{prefix.lower()}_pass",
        name=f"{prefix} Pass",
        seq=seq,
        is_active=True,
    )
    tax = TaxGroup(
        restaurant_id=restaurant_id,
        # **Separate from `prefix`, and it has to be.** The tax list pages by `code`, so the
        # attacker's rows must sort *after* the victim's for a leaked cursor to be visible at all.
        # Derived from the prefix, "RIVALGST" sorted before "VICTIMGST" and the cursor leg of the
        # test was inert: both a leaked cursor and a correctly scoped one returned nothing.
        code=tax_code or f"{prefix.upper()}GST",
        name=f"{prefix} GST",
        is_active=True,
    )
    session.add_all([area, station, tax])
    await session.flush()
    # The rate hangs off the group, so the victim has something a probe could read through
    # `/rates` as well as through the group itself.
    session.add(
        TaxRate(
            restaurant_id=restaurant_id,
            tax_group_id=tax.id,
            rate=Decimal("0.0500"),
            is_inclusive=False,
            effective_from=date(2026, 1, 1),
        )
    )
    table = RestaurantTable(
        restaurant_id=restaurant_id,
        dining_area_id=area.id,
        code=code,
        seats=4,
        status=TableStatus.FREE,
        is_active=True,
    )
    session.add(table)
    await session.flush()

    # M03: a whole menu branch, so a probe has a category, a dish, a variant, a modifier group and
    # a modifier to try to reach. The variant points at the victim's own tax group and station,
    # which is what makes a cross-tenant read of it worth attempting in the first place.
    category = MenuCategory(
        restaurant_id=restaurant_id,
        code=f"{prefix.upper()}CAT",
        name=f"{prefix} Mains",
        seq=seq,
        is_active=True,
    )
    group = ModifierGroup(
        restaurant_id=restaurant_id,
        code=f"{prefix.upper()}SPICE",
        name=f"{prefix} Spice level",
        min_select=0,
        max_select=1,
        is_required=False,
        is_active=True,
    )
    session.add_all([category, group])
    await session.flush()
    item = MenuItem(
        restaurant_id=restaurant_id,
        menu_category_id=category.id,
        code=f"{prefix.upper()}_DISH",
        name=f"{prefix} Butter Chicken",
        food_type="non_veg",
        station_id=station.id,
        seq=seq,
        is_active=True,
    )
    modifier = Modifier(
        restaurant_id=restaurant_id,
        modifier_group_id=group.id,
        code="MILD",
        name="Mild",
        price_delta=Decimal("0.00"),
        seq=0,
        is_active=True,
    )
    session.add_all([item, modifier])
    await session.flush()
    variant = MenuItemVariant(
        restaurant_id=restaurant_id,
        menu_item_id=item.id,
        code="FULL",
        name="Full",
        price=Decimal("470.00"),
        tax_group_id=tax.id,
        prep_minutes=11,
        seq=0,
        is_active=True,
    )
    session.add(variant)
    await session.flush()

    employee = (
        await session.scalars(
            select(Employee.id).where(Employee.organization_id == tenant.organization.id)
        )
    ).first()
    assert employee is not None, "the victim tenant has no employee to probe"

    # M04: an ingredient, a preparation, and a recipe that ties them to the dish above. A probe can
    # then try to read another tenant's recipe — which is the row that says what a competitor's
    # dishes are made of, and how much of each.
    paneer = StockItem(
        restaurant_id=restaurant_id,
        kind="ingredient",
        code=f"{prefix.upper()}_PANEER",
        name=f"{prefix} Paneer",
        base_unit="g",
        category="dairy",
        storage_type="chilled",
        current_unit_cost=Decimal("0.360000"),
        is_active=True,
    )
    session.add(paneer)
    await session.flush()
    session.add(
        IngredientProfile(
            stock_item_id=paneer.id,
            purchase_unit="kg",
            purchase_to_base=Decimal("1000"),
            yield_factor=Decimal("0.98"),
            shelf_life_days=4,
        )
    )
    recipe = Recipe(
        restaurant_id=restaurant_id,
        menu_item_variant_id=variant.id,
        version=1,
        is_current=True,
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        unit_cost=Decimal("72.000000"),
        source="seeded",
    )
    session.add(recipe)
    await session.flush()
    session.add(
        RecipeLine(
            restaurant_id=recipe.restaurant_id,
            recipe_id=recipe.id,
            component_id=paneer.id,
            quantity=Decimal("200"),
            seq=0,
        )
    )
    # M05: a count belonging to the victim. A count is the document that says what a competitor
    # was short of and by how much, so reading somebody else's is a direct commercial leak as well
    # as a tenant one.
    count = StockCount(
        restaurant_id=restaurant_id,
        counted_at=datetime(2026, 1, 2, tzinfo=UTC),
        business_date=date(2026, 1, 2),
        scope="full",
        status="draft",
    )
    session.add(count)
    await session.flush()
    session.add(
        StockCountLine(
            restaurant_id=restaurant_id,
            stock_count_id=count.id,
            stock_item_id=paneer.id,
            system_quantity=Decimal("500"),
            counted_quantity=Decimal("480"),
            variance_value=Decimal("-7.20"),
        )
    )
    # M06: a supplier, an order against it, and a delivery booked against that order. The supplier
    # row is the one worth stealing on its own — it is who a competitor buys from and what they pay
    # — and the receipt is what they were short of, and by how much.
    supplier = Supplier(
        restaurant_id=restaurant_id,
        name=f"{prefix} Traders",
        contact_person=f"{prefix} Sharma",
        payment_terms_days=14,
    )
    session.add(supplier)
    await session.flush()
    order = PurchaseOrder(
        restaurant_id=restaurant_id,
        supplier_id=supplier.id,
        po_number=f"PO-{seq:06d}",
        # `sent`, so a cross-tenant receive is refused for being another tenant's order rather than
        # for being a draft — the suite must probe the tenant check, not a status check.
        status="sent",
        total_amount=Decimal("4200.00"),
    )
    session.add(order)
    await session.flush()
    session.add(
        PurchaseOrderLine(
            restaurant_id=restaurant_id,
            purchase_order_id=order.id,
            stock_item_id=paneer.id,
            quantity_ordered=Decimal("10000.0000"),
            unit_price=Decimal("0.420000"),
        )
    )
    receipt = GoodsReceipt(
        restaurant_id=restaurant_id,
        purchase_order_id=order.id,
        supplier_id=supplier.id,
        received_at=datetime(2026, 1, 3, tzinfo=UTC),
        business_date=date(2026, 1, 3),
        invoice_number=f"{prefix.upper()}-4471",
        invoice_amount=Decimal("3990.00"),
    )
    session.add(receipt)
    await session.flush()
    session.add(
        GoodsReceiptLine(
            restaurant_id=restaurant_id,
            goods_receipt_id=receipt.id,
            stock_item_id=paneer.id,
            quantity_invoiced=Decimal("10000.0000"),
            quantity_received=Decimal("9500.0000"),
            unit_price=Decimal("0.420000"),
        )
    )
    await session.flush()

    # M07: an order with one line, so a probe has another restaurant's bill to try to read,
    # change, send, serve, bill or cancel.
    victim_order = Order(
        restaurant_id=restaurant_id,
        order_number="1",
        type="takeaway",
        channel="pos",
        status="open",
        placed_at=datetime.now(UTC),
        business_date=date(2026, 9, 13),
    )
    session.add(victim_order)
    await session.flush()
    victim_line = OrderLine(
        restaurant_id=restaurant_id,
        order_id=victim_order.id,
        menu_item_variant_id=variant.id,
        quantity=1,
        unit_price=Decimal("470.00"),
        line_subtotal=Decimal("470.00"),
        tax_group_id=tax.id,
        tax_regime="gst",
        tax_rate=Decimal("0.0500"),
        taxable_value=Decimal("470.00"),
        cgst_amount=Decimal("11.75"),
        sgst_amount=Decimal("11.75"),
        tax_amount=Decimal("23.50"),
        line_total=Decimal("493.50"),
        status="pending",
    )
    session.add(victim_line)
    await session.flush()
    victim_discount = OrderDiscount(
        restaurant_id=restaurant_id,
        order_id=victim_order.id,
        type="comp",
        rate=Decimal("1.0000"),
        amount=Decimal("470.00"),
        reason="Victim comp",
        authorised_by=employee,
    )
    victim_charge = OrderCharge(
        restaurant_id=restaurant_id,
        order_id=victim_order.id,
        type="packaging",
        amount=Decimal("20.00"),
    )
    session.add_all([victim_discount, victim_charge])
    await session.flush()
    # A bill of supply, so the victim restaurant needs no GSTIN for the row to be valid.
    victim_invoice = Invoice(
        restaurant_id=restaurant_id,
        order_id=victim_order.id,
        document_type="bill_of_supply",
        financial_year="2026-27",
        sequence=1,
        invoice_number="2026-27/000001",
        status="issued",
        issued_at=datetime.now(UTC),
        invoice_date=date(2026, 9, 13),
        business_date=date(2026, 9, 13),
        supplier_name=f"{prefix} Restaurant",
        taxable_total=Decimal("470.00"),
        grand_total=Decimal("470.00"),
    )
    session.add(victim_invoice)
    await session.flush()

    return {
        "order_id": str(victim_order.id),
        "line_id": str(victim_line.id),
        "discount_id": str(victim_discount.id),
        "charge_id": str(victim_charge.id),
        "invoice_id": str(victim_invoice.id),
        "count_id": str(count.id),
        "supplier_id": str(supplier.id),
        "po_id": str(order.id),
        "receipt_id": str(receipt.id),
        "employee_id": str(employee),
        "area_id": str(area.id),
        "table_id": str(table.id),
        "station_id": str(station.id),
        "tax_group_id": str(tax.id),
        "category_id": str(category.id),
        "item_id": str(item.id),
        "variant_id": str(variant.id),
        "group_id": str(group.id),
        "modifier_id": str(modifier.id),
        "recipe_id": str(recipe.id),
        "stock_item_id": str(paneer.id),
    }


# --------------------------------------------------------------------------- suites 1-3


class TestTenantIsolationAcrossEveryStaffRoute:
    """Suite 1. The product's #1 bug class, asserted route by route rather than case by case."""

    async def test_every_path_parameter_has_a_victim_row(self, api: FastAPI) -> None:
        """The guard that stops this suite quietly shrinking.

        Suite 1 is a loop that substitutes a victim id into each route's path. A parameter it has
        no victim for cannot be probed — and the previous version simply skipped those, so adding a
        route with a new parameter name removed it from the product's most important security test
        without changing a single line of this file. M02 added four such routes.

        Now an unknown parameter fails here instead, naming the route and the parameter.
        """
        unknown: dict[str, str] = {}
        for route in staff_routes(api):
            for name in re.findall(r"\{([a-z_]+)\}", route.path):
                if name not in _VICTIM_PARAMETERS:
                    unknown[name] = route.key
        assert not unknown, (
            "these path parameters have no victim row, so suite 1 cannot probe their routes: "
            f"{unknown}. Add the parameter to _VICTIM_PARAMETERS and seed a row for it in "
            "_victim_resources, or the routes below are exempt from tenant-isolation testing."
        )

    async def test_no_staff_route_exposes_another_tenants_resource(
        self, db_session: AsyncSession, api: FastAPI, api_client: AsyncClient
    ) -> None:
        spice = await _tenant(db_session, "spice-garden", ("owner",))
        await _tenant(db_session, "tandoor-house", ("owner",))
        victims = await _victim_resources(db_session, spice)
        await db_session.commit()

        token = await _login(api_client, "owner@tandoor-house.test")
        failures: list[str] = []
        probed = 0
        for route in staff_routes(api):
            if "{" not in route.path:
                continue
            url = route.path
            for name, value in victims.items():
                url = url.replace(f"{{{name}}}", value)
            assert "{" not in url, f"no victim id for {route.key}"
            probed += 1
            response = await api_client.request(
                route.method,
                url,
                json=_sample_body(route),
                headers={
                    "Authorization": f"Bearer {token}",
                    # Fresh per probe, so an idempotent route reaches the check under test
                    # instead of refusing for a missing key (M07 chunk F).
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
            # 422 is acceptable only because a body may fail validation before authorisation;
            # 200 or 201 would mean one tenant reached another's row.
            if response.status_code not in (403, 404, 422):
                failures.append(f"{route.key} -> {response.status_code}")
        assert not failures, f"cross-tenant access succeeded on: {failures}"
        # The loop ran. Without this the suite passes when the enumerator returns nothing, which is
        # the failure mode suite 0 exists to prevent and this is its per-suite half.
        assert probed >= 10, f"suite 1 only probed {probed} routes; it should cover every id route"

    async def test_no_list_route_returns_another_tenants_rows(
        self, db_session: AsyncSession, api: FastAPI, api_client: AsyncClient
    ) -> None:
        """Suite 1's other half: the routes that take no id.

        The loop above substitutes a victim id into each path, so `if "{" not in route.path:
        continue` silently skipped every route without one — which is all four setup lists, the
        employee list and the restaurant settings. Those are where a dropped `restaurant_id`
        predicate leaks in *bulk* rather than one row at a time, so they were the more dangerous
        half and they were exempt. `test_setup_endpoints.py` meanwhile said isolation was "asserted
        for every route at once by suite 1", which is how nobody noticed. Found by external review.

        The victim tenant is furnished and the attacker tenant is bare, so any row at all in an
        attacker's response crossed the boundary.
        """
        spice = await _tenant(db_session, "spice-garden", ("owner",))
        await _tenant(db_session, "tandoor-house", ("owner",))
        victims = await _victim_resources(db_session, spice)
        await db_session.commit()

        token = await _login(api_client, "owner@tandoor-house.test")
        # **Ids, not names.** The first version looked for the substring "Victim", which every
        # seeded row carries in its *name* — and a table has no name, only the code "V1", while an
        # employee is called "Owner Person" like everybody else. Those two were exempt from the
        # suite that exists to catch exactly them. Every row serialises its id, so the ids are the
        # check that cannot be shaped around; the name check stays as a second net.
        needles = {value: key for key, value in victims.items()}
        needles["Victim"] = "a row named Victim"
        failures: list[str] = []
        probed = 0
        for route in staff_routes(api):
            if "{" in route.path or route.method != "GET":
                continue
            probed += 1
            response = await api_client.get(
                route.path, headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code != 200:
                continue
            leaked = [what for needle, what in needles.items() if needle in response.text]
            if leaked:
                failures.append(f"{route.key} leaked {leaked} -> {response.text[:160]}")
        assert not failures, f"a list route returned another tenant's rows: {failures}"
        assert probed >= 5, f"suite 1b only probed {probed} list routes"

        # **The positive control**, without which "no victim row was found" is also what a broken
        # probe returns. The victim's own token must find its own rows through these same routes,
        # so the loop above is known to be able to see a leak if one is there.
        owner = await _login(api_client, "owner@spice-garden.test")
        seen: set[str] = set()
        for route in staff_routes(api):
            if "{" in route.path or route.method != "GET":
                continue
            response = await api_client.get(
                route.path, headers={"Authorization": f"Bearer {owner}"}
            )
            if response.status_code != 200:
                continue
            seen.update(what for needle, what in needles.items() if needle in response.text)
        assert len(seen) >= 5, f"suite 1b's probe found only {seen} of the victim's own rows"

    async def test_a_cursor_naming_another_tenants_row_does_not_move_the_page(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The leak no row-level check can see.

        Every paged list resolves its cursor's sort key with a subquery. Those subqueries were not
        tenant-scoped, so passing another restaurant's row id returned *that* row's `seq` / `code` /
        `effective_from` and offset the page by it. No row crossed the boundary — the **ordering
        key** did, and feeding ids in and watching where the page starts reads it back out. The tax
        cursor leaked when a competitor last changed their GST rate.

        A foreign cursor must be indistinguishable from a meaningless one: an empty page.

        **The attacker tenant is given rows of its own, and that is the whole test.** The first
        version of this seeded nothing for the attacker, so its page was empty whether the cursor
        leaked or not, and the assertion held against the bug it was written to catch. With rows
        present the two outcomes finally differ: a leaked cursor resolves the victim's low sort key
        and returns the attacker's later rows, while correct scoping yields NULL and an empty page.
        """
        spice = await _tenant(db_session, "spice-garden", ("owner",))
        tandoor = await _tenant(db_session, "tandoor-house", ("owner",))
        victims = await _victim_resources(db_session, spice)
        # The attacker's own floor, deliberately sorting *after* the victim's rows, so a cursor that
        # resolved across the boundary would return these instead of nothing.
        await _victim_resources(
            db_session, tandoor, prefix="Rival", seq=5, code="Z9", tax_code="ZRIVALGST"
        )
        await db_session.commit()

        token = await _login(api_client, "owner@tandoor-house.test")
        for path, victim in (
            ("/api/v1/staff/setup/dining-areas", victims["area_id"]),
            ("/api/v1/staff/setup/tables", victims["table_id"]),
            ("/api/v1/staff/setup/stations", victims["station_id"]),
            ("/api/v1/staff/setup/tax-groups", victims["tax_group_id"]),
        ):
            response = await api_client.get(
                f"{path}?cursor={victim}", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200, response.text
            assert response.json()["items"] == [], (
                f"{path} honoured a cursor belonging to another tenant"
            )


class TestPersonaSeparation:
    """Suite 3. A guest token must not reach the employee surface (ADR 0009)."""

    async def test_no_guest_token_satisfies_any_staff_route(
        self, db_session: AsyncSession, api: FastAPI, api_client: AsyncClient
    ) -> None:
        await _tenant(db_session, "spice-garden", ("owner",))
        await db_session.commit()

        failures: list[str] = []
        for route in staff_routes(api):
            url = route.path.replace("{employee_id}", "00000000-0000-0000-0000-000000000002")
            response = await api_client.request(
                route.method,
                url,
                json=_sample_body(route),
                headers={"Authorization": f"Bearer {_guest_token()}"},
            )
            if response.status_code not in (401, 403):
                failures.append(f"{route.key} -> {response.status_code}")
        assert not failures, f"a guest token was accepted by: {failures}"

    async def test_no_token_at_all_is_refused_by_every_staff_route(
        self, api: FastAPI, api_client: AsyncClient
    ) -> None:
        failures: list[str] = []
        for route in staff_routes(api):
            url = route.path.replace("{employee_id}", "00000000-0000-0000-0000-000000000002")
            response = await api_client.request(route.method, url, json=_sample_body(route))
            if response.status_code != 401:
                failures.append(f"{route.key} -> {response.status_code}")
        assert not failures, f"these routes served an unauthenticated request: {failures}"


class TestThePermissionMatrix:
    """Suite 2. Every staff route against every role, checked against the declared catalogue.

    The assertion is not "a waiter gets 403 on the staff list" — it is that the *whole grid* agrees
    with permissions.json. A permission accidentally added to a role shows up here as a route that
    unexpectedly succeeded.
    """

    @pytest.mark.parametrize(
        "role_code", [role.code for role in CATALOGUE.roles if role.code != "owner"]
    )
    async def test_a_role_reaches_exactly_the_routes_its_permissions_allow(
        self, db_session: AsyncSession, api: FastAPI, api_client: AsyncClient, role_code: str
    ) -> None:
        await _tenant(db_session, f"org-{role_code}", (role_code,))
        await db_session.commit()
        granted = permissions_for_role(role_code)

        token = await _login(api_client, f"{role_code}@org-{role_code}.test")
        mismatches: list[str] = []
        for route in staff_routes(api):
            if not route.permissions:
                continue
            url = route.path.replace("{employee_id}", "00000000-0000-0000-0000-000000000002")
            response = await api_client.request(
                route.method,
                url,
                json=_sample_body(route),
                headers={
                    "Authorization": f"Bearer {token}",
                    # Fresh per probe, so an idempotent route reaches the check under test
                    # instead of refusing for a missing key (M07 chunk F).
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
            should_be_allowed = set(route.permissions) <= granted
            was_denied = response.status_code == 403
            if should_be_allowed and was_denied:
                mismatches.append(f"{route.key}: {role_code} holds it but was denied")
            if not should_be_allowed and not was_denied:
                mismatches.append(
                    f"{route.key}: {role_code} lacks {route.permissions} "
                    f"but got {response.status_code}"
                )
        assert not mismatches, "\n".join(mismatches)


async def _login(client: AsyncClient, identifier: str, *, expect_failure: bool = False) -> Any:
    response = await client.post(
        "/api/v1/auth/login", json={"identifier": identifier, "password": PASSWORD}
    )
    if response.status_code != 200:
        if expect_failure:
            return None
        raise AssertionError(
            f"login failed for {identifier}: {response.status_code} {response.text}"
        )
    return response.json()["access_token"]
