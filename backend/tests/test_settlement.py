"""Settlement over HTTP: acceptance criteria 2, 3, 5, 6, 7, 8, 10 and 11 of the M07 spec.

Settling is the one transaction the module exists for: a numbered legal document, money, stock and a
frozen cost, all or nothing. Each class below takes one of those and tries to break it.

The concurrency tests at the bottom take `fresh_database` and their own connections, for the reason
`conftest.api` gives: inside the shared test transaction two "simultaneous" settlements never
contend, and a numbering test written there passes against code with no lock at all.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.business_day import calendar_date_of, financial_year_of
from app.core.db import get_session
from app.main import create_app
from app.models.audit import AuditLog
from app.models.inventory import StockMovement
from app.models.menu import MenuItemVariant
from app.models.orders import Invoice, Order, OrderLine, Payment
from app.models.setup import RestaurantTable, Station, TaxRate
from app.models.stock import IngredientProfile, PreparationProfile, Recipe, RecipeLine, StockItem
from app.services.settlement import SettlementService
from tests.test_orders_endpoints import ORDERS, Menu, _added, _menu, _open, _setup
from tests.test_setup_endpoints import World, _auth, _token, _world

# The format example GSTN publishes, not anybody's registration.
_GSTIN = "27AAAAA0000A1Z5"
_KOLKATA = "Asia/Kolkata"


async def _registered(session: AsyncSession, world: World) -> None:
    """A regular-scheme restaurant cannot issue a tax invoice without its GSTIN (Rule 46)."""
    world.restaurant.gstin = _GSTIN
    await session.commit()


async def _settle(
    client: AsyncClient,
    token: str,
    order: dict[str, Any],
    *,
    payments: list[dict[str, Any]] | None = None,
    key: str | None = None,
    version: int | None = None,
) -> Response:
    body = {
        "version": order["version"] if version is None else version,
        "payments": payments or [{"method": "upi", "amount": order["grand_total"]}],
    }
    return await client.post(
        f"{ORDERS}/{order['id']}/settle",
        json=body,
        headers=_auth(token) | {"Idempotency-Key": key or str(uuid.uuid4())},
    )


async def _count(session: AsyncSession, model: Any, *where: Any) -> int:
    return int(await session.scalar(select(func.count()).select_from(model).where(*where)) or 0)


# --------------------------------------------------------------------------- the kitchen


@dataclass(frozen=True)
class Kitchen:
    gravy: uuid.UUID
    onion: uuid.UUID
    butter: uuid.UUID
    cheese: uuid.UUID


async def _kitchen(session: AsyncSession, world: World, menu: Menu) -> Kitchen:
    """Dal is 150 g of house gravy and 20 g of butter; the gravy is onions; extra cheese is 40 g.

    Unit costs make the arithmetic readable: gravy is 1,250 g of onion at ₹0.04 into 1,000 g, so
    ₹0.05 a gram; a dal plate is 150 * 0.05 + 20 * 0.50 = ₹17.50; extra cheese is 40 * 0.60 = ₹24.
    """
    rid = world.restaurant.id
    station = Station(restaurant_id=rid, code="prep", name="Prep", seq=1, is_active=True)
    onion = StockItem(
        restaurant_id=rid,
        kind="ingredient",
        code="ONION",
        name="Onion",
        base_unit="g",
        category="veg",
        storage_type="ambient",
        current_unit_cost=Decimal("0.040000"),
        is_active=True,
    )
    butter = StockItem(
        restaurant_id=rid,
        kind="ingredient",
        code="BUTTER",
        name="Butter",
        base_unit="g",
        category="dairy",
        storage_type="chilled",
        current_unit_cost=Decimal("0.500000"),
        is_active=True,
    )
    cheese = StockItem(
        restaurant_id=rid,
        kind="ingredient",
        code="CHEESE",
        name="Cheese",
        base_unit="g",
        category="dairy",
        storage_type="chilled",
        current_unit_cost=Decimal("0.600000"),
        is_active=True,
    )
    gravy = StockItem(
        restaurant_id=rid,
        kind="preparation",
        code="GRAVY",
        name="House Gravy",
        base_unit="g",
        current_unit_cost=Decimal("0.050000"),
        is_active=True,
    )
    session.add_all([station, onion, butter, cheese, gravy])
    await session.flush()
    for item in (onion, butter, cheese):
        session.add(
            IngredientProfile(
                stock_item_id=item.id,
                purchase_unit="kg",
                purchase_to_base=Decimal("1000"),
                yield_factor=Decimal("1"),
                shelf_life_days=5,
            )
        )
    session.add(
        PreparationProfile(
            stock_item_id=gravy.id,
            batch_yield=Decimal("1000"),
            shelf_life_hours=48,
            station_id=station.id,
            prep_minutes=60,
        )
    )
    since = datetime(2026, 1, 1, tzinfo=UTC)
    gravy_recipe = Recipe(
        restaurant_id=rid,
        produces_stock_item_id=gravy.id,
        version=1,
        is_current=True,
        effective_from=since,
        unit_cost=Decimal("0.050000"),
        source="typed",
    )
    dal_recipe = Recipe(
        restaurant_id=rid,
        menu_item_variant_id=menu.dal,
        version=1,
        is_current=True,
        effective_from=since,
        unit_cost=Decimal("17.500000"),
        source="typed",
    )
    cheese_recipe = Recipe(
        restaurant_id=rid,
        modifier_id=menu.cheese,
        version=1,
        is_current=True,
        effective_from=since,
        unit_cost=Decimal("24.000000"),
        source="typed",
    )
    session.add_all([gravy_recipe, dal_recipe, cheese_recipe])
    await session.flush()
    session.add_all(
        [
            RecipeLine(
                restaurant_id=rid,
                recipe_id=gravy_recipe.id,
                component_id=onion.id,
                quantity=Decimal("1250"),
                seq=0,
            ),
            RecipeLine(
                restaurant_id=rid,
                recipe_id=dal_recipe.id,
                component_id=gravy.id,
                quantity=Decimal("150"),
                seq=0,
            ),
            RecipeLine(
                restaurant_id=rid,
                recipe_id=dal_recipe.id,
                component_id=butter.id,
                quantity=Decimal("20"),
                seq=1,
            ),
            RecipeLine(
                restaurant_id=rid,
                recipe_id=cheese_recipe.id,
                component_id=cheese.id,
                quantity=Decimal("40"),
                seq=0,
            ),
        ]
    )
    await session.flush()
    kitchen = Kitchen(gravy=gravy.id, onion=onion.id, butter=butter.id, cheese=cheese.id)
    await session.commit()
    return kitchen


# --------------------------------------------------------------------------- the bill


class TestASettledBill:
    async def test_it_is_a_numbered_tax_invoice_carrying_its_payments(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        order = await _added(
            api_client, token, await _open(api_client, token, menu), menu.dal, quantity=2
        )

        response = await _settle(api_client, token, order)

        assert response.status_code == 201, response.text
        invoice = response.json()
        year = financial_year_of(calendar_date_of(datetime.now(UTC), _KOLKATA))
        assert invoice["invoice_number"] == f"{year}/000001"
        assert invoice["document_type"] == "tax_invoice"
        assert invoice["supplier_gstin"] == _GSTIN
        assert invoice["supplier_name"] == world.restaurant.name
        assert (invoice["taxable_total"], invoice["cgst_total"], invoice["sgst_total"]) == (
            "940.00",
            "23.50",
            "23.50",
        )
        assert invoice["grand_total"] == "987.00"
        assert [(p["method"], p["amount"]) for p in invoice["payments"]] == [("upi", "987.00")]

        settled = (await api_client.get(f"{ORDERS}/{order['id']}", headers=_auth(token))).json()
        assert settled["status"] == "settled"
        assert settled["settled_at"] is not None
        table = await db_session.scalar(
            select(RestaurantTable.status).where(RestaurantTable.id == menu.table)
        )
        assert table == "cleaning"
        assert await _count(db_session, AuditLog, AuditLog.action == "order.settle") == 1

    async def test_the_jaipur_bill_settles_exactly_as_printed(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 2: ₹1,580 at 18% is CGST ₹142.20 + SGST ₹142.20 = ₹1,864.40, and
        no rounding, because the bill did not round."""
        world, menu, token = await _setup(db_session, api_client, rate="0.1800")
        await _registered(db_session, world)
        await db_session.execute(
            update(MenuItemVariant)
            .where(MenuItemVariant.id == menu.dal)
            .values(price=Decimal("1580.00"))
        )
        await db_session.commit()
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        invoice = (await _settle(api_client, token, order)).json()

        assert (invoice["cgst_total"], invoice["sgst_total"]) == ("142.20", "142.20")
        assert invoice["grand_total"] == "1864.40"
        assert invoice["round_off"] == "0.00"

    async def test_a_composition_restaurant_issues_a_bill_of_supply_with_no_tax(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 6. It needs no GSTIN to settle, and collects nothing."""
        world, menu, token = await _setup(db_session, api_client)
        world.restaurant.gst_scheme = "composition"
        await db_session.commit()
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        response = await _settle(api_client, token, order)

        assert response.status_code == 201, response.text
        invoice = response.json()
        assert invoice["document_type"] == "bill_of_supply"
        assert (invoice["cgst_total"], invoice["sgst_total"]) == ("0.00", "0.00")
        assert invoice["grand_total"] == "470.00"

    async def test_a_regular_restaurant_without_its_gstin_cannot_issue_a_tax_invoice(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        response = await _settle(api_client, token, order)

        assert response.status_code == 409
        assert response.json()["code"] == "restaurant.gstin_required"
        assert await _count(db_session, Invoice) == 0

    async def test_payments_that_do_not_cover_the_bill_are_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        response = await _settle(
            api_client, token, order, payments=[{"method": "cash", "amount": "400.00"}]
        )

        assert response.status_code == 422
        assert response.json()["code"] == "settlement.payments_do_not_match"
        assert await _count(db_session, Invoice) == 0
        assert await _count(db_session, Payment) == 0

    async def test_several_payments_settle_one_bill(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Decision 9: "we'll pay separately" is several UPI payments against one invoice."""
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        response = await _settle(
            api_client,
            token,
            order,
            payments=[
                {"method": "upi", "amount": "300.00", "reference": "UPI-1"},
                {"method": "upi", "amount": "193.50", "reference": "UPI-2"},
            ],
        )

        assert response.status_code == 201, response.text
        assert len(response.json()["payments"]) == 2

    async def test_a_stale_version_cannot_settle(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        response = await _settle(api_client, token, order, version=order["version"] - 1)

        assert response.status_code == 409
        assert response.json()["code"] == "order.stale"

    async def test_a_settled_order_cannot_be_settled_again(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        assert (await _settle(api_client, token, order)).status_code == 201
        current = (await api_client.get(f"{ORDERS}/{order['id']}", headers=_auth(token))).json()

        again = await _settle(api_client, token, current)

        assert again.status_code == 409
        assert again.json()["code"] == "order.final"
        assert await _count(db_session, Invoice) == 1

    async def test_a_double_tapped_settle_charges_the_table_once(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 7."""
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        key = str(uuid.uuid4())

        first = await _settle(api_client, token, order, key=key)
        again = await _settle(api_client, token, order, key=key)

        assert (first.status_code, again.status_code) == (201, 201), again.text
        assert again.json() == first.json()
        assert again.headers.get("Idempotent-Replayed") == "true"
        assert await _count(db_session, Payment) == 1


# --------------------------------------------------------------------------- stock and cost


class TestWhatTheKitchenUsed:
    """Decision 10 and acceptance criterion 11."""

    async def test_settling_consumes_the_gravy_and_not_the_onions_it_was_made_from(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        kitchen = await _kitchen(db_session, world, menu)
        order = await _added(
            api_client, token, await _open(api_client, token, menu), menu.dal, quantity=2
        )

        assert (await _settle(api_client, token, order)).status_code == 201

        rows = await db_session.execute(
            select(StockMovement.stock_item_id, func.sum(StockMovement.quantity_delta))
            .where(
                StockMovement.ref_type == "order", StockMovement.ref_id == uuid.UUID(order["id"])
            )
            .group_by(StockMovement.stock_item_id)
        )
        consumed = dict(rows.tuples().all())
        assert consumed == {kitchen.gravy: Decimal("-300"), kitchen.butter: Decimal("-40")}
        assert kitchen.onion not in consumed
        bases = await db_session.scalars(
            select(StockMovement.basis)
            .where(StockMovement.ref_id == uuid.UUID(order["id"]))
            .distinct()
        )
        assert bases.all() == ["theoretical"]

    async def test_the_plate_cost_is_frozen_on_the_order_and_its_lines(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        await _kitchen(db_session, world, menu)
        order = await _added(
            api_client, token, await _open(api_client, token, menu), menu.dal, quantity=2
        )

        assert (await _settle(api_client, token, order)).status_code == 201

        cost = await db_session.scalar(
            select(Order.theoretical_food_cost).where(Order.id == uuid.UUID(order["id"]))
        )
        line = (
            await db_session.execute(
                select(OrderLine.theoretical_unit_cost, OrderLine.recipe_id).where(
                    OrderLine.order_id == uuid.UUID(order["id"])
                )
            )
        ).one()
        assert cost == Decimal("35.00")
        assert line.theoretical_unit_cost == Decimal("17.500000")
        assert line.recipe_id is not None

    async def test_a_modifier_recipe_is_consumed_and_costed_too(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Extra cheese is 40 g no dish recipe accounts for. The paneer has no recipe at all, which
        costs nothing and is counted in the audit row rather than hidden."""
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        kitchen = await _kitchen(db_session, world, menu)
        order = await _added(
            api_client,
            token,
            await _open(api_client, token, menu),
            menu.paneer,
            modifiers=(menu.mild, menu.cheese),
        )

        assert (await _settle(api_client, token, order)).status_code == 201

        cheese = await db_session.scalar(
            select(func.sum(StockMovement.quantity_delta)).where(
                StockMovement.ref_id == uuid.UUID(order["id"]),
                StockMovement.stock_item_id == kitchen.cheese,
            )
        )
        cost = await db_session.scalar(
            select(Order.theoretical_food_cost).where(Order.id == uuid.UUID(order["id"]))
        )
        audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "order.settle"))
        assert cheese == Decimal("-40")
        assert cost == Decimal("24.00")
        assert audit is not None and audit.new_value is not None
        assert audit.new_value["lines_without_a_recipe"] == 1


# --------------------------------------------------------------------------- section 14


class TestSection14AtSettlement:
    """Acceptance criterion 5, through the whole stack rather than only the arithmetic."""

    async def test_a_bill_served_and_paid_before_a_rate_change_takes_the_old_rate(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """5% until yesterday, 18% from today. Served two days ago, paid yesterday, invoiced now:
        two of the three are before the change, so the bill takes 5% although it is issued today."""
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        now = datetime.now(UTC)
        today = calendar_date_of(now, _KOLKATA)
        await db_session.execute(
            update(TaxRate)
            .where(TaxRate.tax_group_id == menu.tax_group)
            .values(effective_to=today - timedelta(days=1))
        )
        db_session.add(
            TaxRate(
                restaurant_id=world.restaurant.id,
                tax_group_id=menu.tax_group,
                rate=Decimal("0.1800"),
                is_inclusive=False,
                effective_from=today,
            )
        )
        await db_session.commit()
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        assert order["lines"][0]["tax_rate"] == "0.1800"
        await db_session.execute(
            update(Order)
            .where(Order.id == uuid.UUID(order["id"]))
            .values(placed_at=now - timedelta(days=2), served_at=now - timedelta(days=2))
        )
        await db_session.commit()

        response = await _settle(
            api_client,
            token,
            order,
            payments=[
                {
                    "method": "upi",
                    "amount": "493.50",
                    "paid_at": (now - timedelta(days=1)).isoformat(),
                }
            ],
        )

        assert response.status_code == 201, response.text
        assert (response.json()["cgst_total"], response.json()["grand_total"]) == (
            "11.75",
            "493.50",
        )

    async def test_a_payment_before_the_order_existed_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Otherwise `paid_at` is a dial for moving a bill across a rate change."""
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        response = await _settle(
            api_client,
            token,
            order,
            payments=[
                {
                    "method": "upi",
                    "amount": order["grand_total"],
                    "paid_at": (datetime.now(UTC) - timedelta(days=30)).isoformat(),
                }
            ],
        )

        assert response.status_code == 422
        assert response.json()["code"] == "settlement.payment_time"


# --------------------------------------------------------------------------- atomicity


class TestAllOrNothing:
    async def test_a_failure_after_consumption_leaves_nothing_behind(
        self,
        db_session: AsyncSession,
        api_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Acceptance criterion 10. The failure is injected after the stock has been consumed and
        before the invoice exists — the most dangerous place, because a half-written settlement
        there is stock gone with no bill to say why."""
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)
        await _kitchen(db_session, world, menu)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        async def _printer_on_fire(*_: object, **__: object) -> Invoice:
            raise RuntimeError("the printer caught fire")

        monkeypatch.setattr(SettlementService, "_issue_invoice", _printer_on_fire)
        try:
            response = await _settle(api_client, token, order)
            assert response.status_code == 500
        except RuntimeError:
            pass

        order_id = uuid.UUID(order["id"])
        assert await _count(db_session, Invoice) == 0
        assert await _count(db_session, Payment) == 0
        assert await _count(db_session, StockMovement, StockMovement.ref_id == order_id) == 0
        assert await _count(db_session, AuditLog, AuditLog.action == "order.settle") == 0
        status = await db_session.scalar(select(Order.status).where(Order.id == order_id))
        assert status == "open"


# --------------------------------------------------------------------------- real concurrency


async def _fresh_app(url: str) -> tuple[Any, async_sessionmaker[AsyncSession], Any]:
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    application = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    application.dependency_overrides[get_session] = _session
    return application, factory, engine


async def test_five_bills_settling_at_once_take_five_consecutive_numbers(
    fresh_database: str,
) -> None:
    """Acceptance criterion 3, written to fail with the advisory lock removed.

    **To re-verify this test is not decorative:** delete the `pg_advisory_xact_lock` call from
    `InvoiceRepository.next_sequence` and run it again. Two or more settlements read the same
    maximum and one dies on `uq_invoice_sequence_per_fy`. Put it back.
    """
    application, factory, engine = await _fresh_app(fresh_database)
    try:
        async with factory() as setup:
            world = await _world(setup, "owner")
            menu = await _menu(setup, world)
            world.restaurant.gstin = _GSTIN
            await setup.commit()
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            token = await _token(client, "owner")
            orders = []
            for _ in range(5):
                opened = await _open(client, token, menu, type="takeaway", table_ids=[])
                orders.append(await _added(client, token, opened, menu.dal))

            responses = await asyncio.gather(*(_settle(client, token, order) for order in orders))

        assert [response.status_code for response in responses] == [201] * 5
        year = financial_year_of(calendar_date_of(datetime.now(UTC), _KOLKATA))
        assert sorted(response.json()["invoice_number"] for response in responses) == [
            f"{year}/{sequence:06d}" for sequence in range(1, 6)
        ]
    finally:
        application.dependency_overrides.clear()
        await engine.dispose()


async def test_two_devices_settling_one_order_charge_it_once(fresh_database: str) -> None:
    """Acceptance criterion 8. Two different keys, one order: the row lock serialises them, and the
    second finds a settled order rather than a second chance to charge."""
    application, factory, engine = await _fresh_app(fresh_database)
    try:
        async with factory() as setup:
            world = await _world(setup, "owner")
            menu = await _menu(setup, world)
            world.restaurant.gstin = _GSTIN
            await setup.commit()
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            token = await _token(client, "owner")
            order = await _added(client, token, await _open(client, token, menu), menu.dal)

            first, second = await asyncio.gather(
                _settle(client, token, order), _settle(client, token, order)
            )

        assert sorted([first.status_code, second.status_code]) == [201, 409]
        async with factory() as check:
            assert await _count(check, Payment) == 1
            assert await _count(check, Invoice) == 1
    finally:
        application.dependency_overrides.clear()
        await engine.dispose()
