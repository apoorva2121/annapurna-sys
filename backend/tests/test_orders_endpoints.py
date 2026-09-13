"""Orders over HTTP: the acceptance criteria in `docs/modules/M07-orders-spec.md` that live before
settlement.

`test_generic_suites.py` already proves every route here is tenant-isolated and declares a
permission. What it cannot express is the money, and three things about the money are this file:

- **the server prices everything** — a price sent by the client is refused, and every figure on the
  order comes from the menu and the rate in force;
- **two waiters on one table cannot overwrite each other** — a stale version is a 409 that names the
  current one (ADR 0010);
- **what the kitchen has seen is never deleted** — a sent dish is cancelled with a reason and an
  audit row, and the table it sat at is freed only when nobody is left eating there.

The menu is built directly in the database rather than through the menu API, so a defect in M03's
endpoints cannot make these tests fail for a reason that has nothing to do with orders.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.models.audit import AuditLog
from app.models.menu import (
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    MenuItemVariant,
    Modifier,
    ModifierGroup,
)
from app.models.setup import DiningArea, RestaurantTable, Station, TaxGroup, TaxRate
from tests.test_setup_endpoints import World, _auth, _token, _world

ORDERS = "/api/v1/staff/orders"
SETUP = "/api/v1/staff/setup"


@dataclass(frozen=True)
class Menu:
    table: uuid.UUID
    second_table: uuid.UUID
    # ₹470, no questions asked.
    dal: uuid.UUID
    # ₹350; a spice level must be chosen, and up to two extras may be.
    paneer: uuid.UUID
    mild: uuid.UUID
    hot: uuid.UUID
    # +₹40.
    cheese: uuid.UUID
    tax_group: uuid.UUID


async def _menu(
    session: AsyncSession,
    world: World,
    *,
    rate: str = "0.0500",
    inclusive: bool = False,
    effective_from: date = date(2026, 1, 1),
) -> Menu:
    rid = world.restaurant.id
    area = DiningArea(restaurant_id=rid, name="Hall", seq=0, is_active=True)
    station = Station(restaurant_id=rid, code="tandoor", name="Tandoor", seq=0, is_active=True)
    tax = TaxGroup(restaurant_id=rid, code="GST5", name="GST 5%", is_active=True)
    category = MenuCategory(restaurant_id=rid, code="MAINS", name="Mains", seq=0, is_active=True)
    spice = ModifierGroup(
        restaurant_id=rid,
        code="SPICE",
        name="Spice level",
        min_select=1,
        max_select=1,
        is_required=True,
        is_active=True,
    )
    extras = ModifierGroup(
        restaurant_id=rid,
        code="EXTRAS",
        name="Extras",
        min_select=0,
        max_select=2,
        is_required=False,
        is_active=True,
    )
    session.add_all([area, station, tax, category, spice, extras])
    await session.flush()

    tables = [
        RestaurantTable(
            restaurant_id=rid,
            dining_area_id=area.id,
            code=code,
            seats=4,
            status="free",
            is_active=True,
        )
        for code in ("T6", "T7")
    ]
    dal_item = MenuItem(
        restaurant_id=rid,
        menu_category_id=category.id,
        code="DAL_MAKHANI",
        name="Dal Makhani",
        food_type="veg",
        station_id=station.id,
        seq=0,
        is_active=True,
    )
    paneer_item = MenuItem(
        restaurant_id=rid,
        menu_category_id=category.id,
        code="PANEER_TIKKA",
        name="Paneer Tikka",
        food_type="veg",
        station_id=station.id,
        seq=1,
        is_active=True,
    )
    mild = Modifier(
        restaurant_id=rid,
        modifier_group_id=spice.id,
        code="MILD",
        name="Mild",
        price_delta=Decimal("0.00"),
        seq=0,
        is_active=True,
    )
    hot = Modifier(
        restaurant_id=rid,
        modifier_group_id=spice.id,
        code="HOT",
        name="Hot",
        price_delta=Decimal("0.00"),
        seq=1,
        is_active=True,
    )
    cheese = Modifier(
        restaurant_id=rid,
        modifier_group_id=extras.id,
        code="CHEESE",
        name="Extra cheese",
        price_delta=Decimal("40.00"),
        seq=0,
        is_active=True,
    )
    session.add(
        TaxRate(
            restaurant_id=rid,
            tax_group_id=tax.id,
            rate=Decimal(rate),
            is_inclusive=inclusive,
            effective_from=effective_from,
        )
    )
    session.add_all([*tables, dal_item, paneer_item, mild, hot, cheese])
    await session.flush()

    dal = MenuItemVariant(
        restaurant_id=rid,
        menu_item_id=dal_item.id,
        code="FULL",
        name="Full",
        price=Decimal("470.00"),
        tax_group_id=tax.id,
        prep_minutes=12,
        seq=0,
        is_active=True,
    )
    paneer = MenuItemVariant(
        restaurant_id=rid,
        menu_item_id=paneer_item.id,
        code="FULL",
        name="Full",
        price=Decimal("350.00"),
        tax_group_id=tax.id,
        prep_minutes=15,
        seq=0,
        is_active=True,
    )
    session.add_all(
        [
            dal,
            paneer,
            MenuItemModifierGroup(menu_item_id=paneer_item.id, modifier_group_id=spice.id, seq=0),
            MenuItemModifierGroup(menu_item_id=paneer_item.id, modifier_group_id=extras.id, seq=1),
        ]
    )
    await session.flush()
    menu = Menu(
        table=tables[0].id,
        second_table=tables[1].id,
        dal=dal.id,
        paneer=paneer.id,
        mild=mild.id,
        hot=hot.id,
        cheese=cheese.id,
        tax_group=tax.id,
    )
    await session.commit()
    return menu


async def _setup(
    session: AsyncSession, client: AsyncClient, **menu_options: Any
) -> tuple[World, Menu, str]:
    world = await _world(session, "owner", "waiter", "accountant", "manager")
    menu = await _menu(session, world, **menu_options)
    return world, menu, await _token(client, "waiter")


async def _open(client: AsyncClient, token: str, menu: Menu, **overrides: Any) -> dict[str, Any]:
    body = {"type": "dine_in", "table_ids": [str(menu.table)], "covers": 2} | overrides
    response = await client.post(ORDERS, json=body, headers=_auth(token))
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _add(
    client: AsyncClient,
    token: str,
    order: dict[str, Any],
    variant: uuid.UUID,
    *,
    quantity: int = 1,
    modifiers: tuple[uuid.UUID, ...] = (),
) -> Response:
    return await client.post(
        f"{ORDERS}/{order['id']}/lines",
        json={
            "version": order["version"],
            "menu_item_variant_id": str(variant),
            "quantity": quantity,
            "modifier_ids": [str(modifier) for modifier in modifiers],
        },
        headers=_auth(token),
    )


async def _added(
    client: AsyncClient,
    token: str,
    order: dict[str, Any],
    variant: uuid.UUID,
    **options: Any,
) -> dict[str, Any]:
    response = await _add(client, token, order, variant, **options)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _step(
    client: AsyncClient, token: str, order: dict[str, Any], action: str, **extra: Any
) -> Response:
    return await client.post(
        f"{ORDERS}/{order['id']}/{action}",
        json={"version": order["version"]} | extra,
        headers=_auth(token),
    )


async def _stepped(
    client: AsyncClient, token: str, order: dict[str, Any], action: str, **extra: Any
) -> dict[str, Any]:
    response = await _step(client, token, order, action, **extra)
    assert response.status_code == 200, response.text
    return dict(response.json())


# --------------------------------------------------------------------------- opening


class TestOpeningAnOrder:
    async def test_a_waiter_opens_a_table_and_the_floor_shows_it_occupied(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)

        order = await _open(api_client, token, menu)

        assert order["status"] == "open"
        assert order["version"] == 1
        assert order["order_number"] == "1"
        assert order["table_ids"] == [str(menu.table)]
        assert order["waiter_employee_id"] is not None
        assert order["lines"] == []
        assert order["grand_total"] == "0.00"
        status = await db_session.scalar(
            select(RestaurantTable.status).where(RestaurantTable.id == menu.table)
        )
        assert status == "occupied"

    async def test_order_numbers_count_up_within_a_business_day(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """ "Table 6, order 42" is what a waiter calls out, so the number is short and per day."""
        _, menu, token = await _setup(db_session, api_client)

        first = await _open(api_client, token, menu)
        second = await _open(api_client, token, menu, table_ids=[str(menu.second_table)])

        assert (first["order_number"], second["order_number"]) == ("1", "2")

    async def test_the_accountant_reads_orders_and_cannot_open_one(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        await _open(api_client, token, menu)
        accountant = await _token(api_client, "accountant")

        opened = await api_client.post(ORDERS, json={"type": "takeaway"}, headers=_auth(accountant))
        listed = await api_client.get(ORDERS, headers=_auth(accountant))

        assert opened.status_code == 403
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 1

    async def test_a_dine_in_order_sits_at_a_table(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, _, token = await _setup(db_session, api_client)

        response = await api_client.post(ORDERS, json={"type": "dine_in"}, headers=_auth(token))

        assert response.status_code == 422

    async def test_a_table_out_of_service_takes_no_order(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        owner = await _token(api_client, "owner")
        marked = await api_client.post(
            f"{SETUP}/tables/{menu.table}/status",
            json={"status": "out_of_service"},
            headers=_auth(owner),
        )
        assert marked.status_code == 200, marked.text

        response = await api_client.post(
            ORDERS,
            json={"type": "dine_in", "table_ids": [str(menu.table)]},
            headers=_auth(token),
        )

        assert response.status_code == 409
        assert response.json()["code"] == "table.out_of_service"


# --------------------------------------------------------------------------- prices


class TestTheServerPricesEverything:
    async def test_a_line_is_priced_from_the_menu_with_its_tax_split_evenly(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Two dal at ₹470 with 5% GST: ₹940 + ₹23.50 + ₹23.50 = ₹987."""
        _, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)

        order = await _added(api_client, token, order, menu.dal, quantity=2)

        (line,) = order["lines"]
        assert line["unit_price"] == "470.00"
        assert line["line_subtotal"] == "940.00"
        assert (line["cgst_amount"], line["sgst_amount"]) == ("23.50", "23.50")
        assert line["line_total"] == "987.00"
        assert line["status"] == "pending"
        assert (order["subtotal"], order["tax_total"], order["grand_total"]) == (
            "940.00",
            "47.00",
            "987.00",
        )
        assert order["version"] == 2

    async def test_a_price_sent_by_the_client_is_refused_and_changes_nothing(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 9, made stronger than the spec's "ignored": a client that sends a
        price believes it, and is told otherwise rather than silently overruled."""
        _, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)

        response = await api_client.post(
            f"{ORDERS}/{order['id']}/lines",
            json={
                "version": 1,
                "menu_item_variant_id": str(menu.dal),
                "quantity": 1,
                "unit_price": "1.00",
            },
            headers=_auth(token),
        )
        after = await api_client.get(f"{ORDERS}/{order['id']}", headers=_auth(token))

        assert response.status_code == 422
        assert after.json()["lines"] == []
        assert after.json()["version"] == 1

    async def test_options_are_priced_from_the_menu_too(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)

        order = await _added(
            api_client, token, order, menu.paneer, modifiers=(menu.mild, menu.cheese)
        )

        (line,) = order["lines"]
        assert line["unit_price"] == "350.00"
        assert line["line_subtotal"] == "390.00"
        assert sorted(modifier["price_delta"] for modifier in line["modifiers"]) == [
            "0.00",
            "40.00",
        ]

    async def test_a_required_question_has_to_be_answered(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)

        response = await _add(api_client, token, order, menu.paneer)

        assert response.status_code == 422
        assert response.json()["code"] == "order_line.modifier_selection"

    async def test_an_option_the_dish_does_not_offer_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Extra cheese on dal: a real id, from this restaurant, attached to a different dish."""
        _, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)

        response = await _add(api_client, token, order, menu.dal, modifiers=(menu.cheese,))

        assert response.status_code == 422
        assert response.json()["code"] == "order_line.modifier_not_offered"

    async def test_a_composition_restaurant_puts_no_tax_on_the_bill(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 6, in the service: whatever tax group the menu names."""
        world, menu, token = await _setup(db_session, api_client)
        world.restaurant.gst_scheme = "composition"
        await db_session.commit()
        order = await _open(api_client, token, menu)

        order = await _added(api_client, token, order, menu.dal)

        (line,) = order["lines"]
        assert line["tax_amount"] == "0.00"
        assert order["grand_total"] == "470.00"

    async def test_an_inclusive_rate_takes_the_tax_out_of_the_menu_price(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """₹470 including 5%: each half is round(470 * 0.025 / 1.05) = ₹11.19, and the customer
        still pays ₹470."""
        _, menu, token = await _setup(db_session, api_client, inclusive=True)
        order = await _open(api_client, token, menu)

        order = await _added(api_client, token, order, menu.dal)

        (line,) = order["lines"]
        assert line["tax_inclusive"] is True
        assert (line["cgst_amount"], line["sgst_amount"]) == ("11.19", "11.19")
        assert line["taxable_value"] == "447.62"
        assert line["line_total"] == "470.00"

    async def test_a_dish_with_no_rate_in_force_cannot_be_sold(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client, effective_from=date(2099, 1, 1))
        order = await _open(api_client, token, menu)

        response = await _add(api_client, token, order, menu.dal)

        assert response.status_code == 409
        assert response.json()["code"] == "tax.no_rate"


# --------------------------------------------------------------------------- two waiters


class TestTwoWaitersOneTable:
    """ADR 0010. The dessert that vanishes because a stale copy was saved over it."""

    async def test_a_stale_version_is_refused_and_told_the_current_one(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        opened = await _open(api_client, token, menu)
        await _added(api_client, token, opened, menu.dal)

        response = await _add(api_client, token, opened, menu.dal)

        assert response.status_code == 409
        assert response.json()["code"] == "order.stale"
        assert response.json()["details"]["current_version"] == 2

    async def test_every_change_moves_the_version_even_when_no_figure_does(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A change the version does not record is one the next stale screen overwrites."""
        _, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        (line,) = order["lines"]

        response = await api_client.patch(
            f"{ORDERS}/{order['id']}/lines/{line['id']}",
            json={"version": order["version"], "special_instructions": "less oil"},
            headers=_auth(token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["version"] == order["version"] + 1
        assert response.json()["grand_total"] == order["grand_total"]


# --------------------------------------------------------------------------- the kitchen


class TestWhatTheKitchenHasSeen:
    async def test_sending_stamps_the_lines_and_the_order(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        sent = await _stepped(api_client, token, order, "send")

        assert sent["status"] == "sent"
        assert sent["first_sent_at"] is not None
        assert [line["status"] for line in sent["lines"]] == ["sent"]
        assert sent["lines"][0]["sent_at"] is not None

    async def test_an_empty_send_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)

        response = await _step(api_client, token, order, "send")

        assert response.status_code == 409
        assert response.json()["code"] == "order.nothing_to_send"

    async def test_an_unsent_line_is_simply_removed(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A mis-tap the kitchen never saw is not worth a reason or an audit row."""
        _, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        (line,) = order["lines"]

        removed = await _stepped(api_client, token, order, f"lines/{line['id']}/remove")

        assert removed["lines"] == []
        assert removed["grand_total"] == "0.00"

    async def test_a_sent_line_needs_a_reason_and_leaves_an_audit_row(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        order = await _stepped(api_client, token, order, "send")
        (line,) = order["lines"]

        unexplained = await _step(api_client, token, order, f"lines/{line['id']}/remove")
        explained = await _stepped(
            api_client, token, order, f"lines/{line['id']}/remove", reason="guest changed mind"
        )

        assert unexplained.status_code == 422
        assert unexplained.json()["code"] == "order_line.reason_required"
        assert explained["lines"][0]["status"] == "cancelled"
        assert explained["lines"][0]["cancel_reason"] == "guest changed mind"
        assert explained["grand_total"] == "0.00"
        audit = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.restaurant_id == world.restaurant.id,
                AuditLog.action == "order_line.cancel",
            )
        )
        assert audit is not None
        assert audit.new_value is not None
        assert audit.new_value["reason"] == "guest changed mind"

    async def test_a_sent_line_cannot_be_edited(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        order = await _stepped(api_client, token, order, "send")

        response = await api_client.patch(
            f"{ORDERS}/{order['id']}/lines/{order['lines'][0]['id']}",
            json={"version": order["version"], "quantity": 3},
            headers=_auth(token),
        )

        assert response.status_code == 409
        assert response.json()["code"] == "order_line.already_sent"

    async def test_serving_and_the_first_bill_request_are_both_kept(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Bill-to-settle is measured from when the customer first asked (G-13 item 1)."""
        _, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        order = await _stepped(api_client, token, order, "send")

        served = await _stepped(api_client, token, order, "served")
        first_bill = await _stepped(api_client, token, served, "bill")
        second_bill = await _stepped(api_client, token, first_bill, "bill")

        assert served["status"] == "served"
        assert served["served_at"] is not None
        assert served["lines"][0]["status"] == "served"
        assert first_bill["bill_requested_at"] is not None
        assert second_bill["bill_requested_at"] == first_bill["bill_requested_at"]

    async def test_an_empty_bill_cannot_be_asked_for(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)

        response = await _step(api_client, token, order, "bill")

        assert response.status_code == 409
        assert response.json()["code"] == "order.empty"


# --------------------------------------------------------------------------- cancelling


class TestCancelling:
    async def test_cancelling_frees_the_table_and_records_what_the_kitchen_had(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A table that walks out is a real evening, and the audit row is what makes it visible."""
        world, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        order = await _stepped(api_client, token, order, "send")

        cancelled = await _stepped(api_client, token, order, "cancel", reason="table walked out")

        assert cancelled["status"] == "cancelled"
        assert cancelled["cancel_reason"] == "table walked out"
        status = await db_session.scalar(
            select(RestaurantTable.status).where(RestaurantTable.id == menu.table)
        )
        assert status == "free"
        audit = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.restaurant_id == world.restaurant.id, AuditLog.action == "order.cancel"
            )
        )
        assert audit is not None
        assert audit.new_value is not None
        assert audit.new_value["lines_sent_to_kitchen"] == 1

    async def test_a_cancelled_order_cannot_change(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)
        cancelled = await _stepped(api_client, token, order, "cancel", reason="opened by mistake")

        response = await _add(api_client, token, cancelled, menu.dal)

        assert response.status_code == 409
        assert response.json()["code"] == "order.final"

    async def test_a_table_stays_occupied_while_another_order_sits_there(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        first = await _open(api_client, token, menu)
        await _open(api_client, token, menu)

        await _stepped(api_client, token, first, "cancel", reason="duplicate order")

        status = await db_session.scalar(
            select(RestaurantTable.status).where(RestaurantTable.id == menu.table)
        )
        assert status == "occupied"


# --------------------------------------------------------------------------- table status


class TestTheTableUnderAnOpenOrder:
    """Acceptance criterion 18: a table with a bill still open on it is not free."""

    async def test_a_table_with_an_open_order_cannot_be_marked_free(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)
        owner = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/tables/{menu.table}/status", json={"status": "free"}, headers=_auth(owner)
        )

        assert response.status_code == 409
        assert response.json()["code"] == "table.order_open"
        assert response.json()["details"]["order_id"] == order["id"]

    async def test_nor_taken_out_of_service(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        await _open(api_client, token, menu)
        owner = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/tables/{menu.table}/status",
            json={"status": "out_of_service"},
            headers=_auth(owner),
        )

        assert response.status_code == 409

    async def test_once_the_order_is_gone_the_table_can_be_freed(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu)
        await _stepped(api_client, token, order, "cancel", reason="opened by mistake")
        owner = await _token(api_client, "owner")

        response = await api_client.post(
            f"{SETUP}/tables/{menu.table}/status",
            json={"status": "cleaning"},
            headers=_auth(owner),
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "cleaning"


# --------------------------------------------------------------------------- listing


class TestTheOrderList:
    async def test_the_list_filters_by_status(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        live = await _open(api_client, token, menu)
        gone = await _open(api_client, token, menu, table_ids=[str(menu.second_table)])
        await _stepped(api_client, token, gone, "cancel", reason="opened by mistake")

        open_orders = await api_client.get(f"{ORDERS}?status=open", headers=_auth(token))
        cancelled = await api_client.get(f"{ORDERS}?status=cancelled", headers=_auth(token))

        assert [item["id"] for item in open_orders.json()["items"]] == [live["id"]]
        assert [item["id"] for item in cancelled.json()["items"]] == [gone["id"]]


# --------------------------------------------------------------------------- discounts


async def _discount(
    client: AsyncClient, token: str, order: dict[str, Any], **body: Any
) -> Response:
    return await client.post(
        f"{ORDERS}/{order['id']}/discounts",
        json={"version": order["version"]} | body,
        headers=_auth(token),
    )


async def _discounted(
    client: AsyncClient, token: str, order: dict[str, Any], **body: Any
) -> dict[str, Any]:
    response = await _discount(client, token, order, **body)
    assert response.status_code == 201, response.text
    return dict(response.json())


def _line_of(order: dict[str, Any], variant: uuid.UUID) -> dict[str, Any]:
    return next(line for line in order["lines"] if line["menu_item_variant_id"] == str(variant))


class TestDiscounts:
    """Decision 6 and acceptance criterion 12: before tax, to the paisa, and with a name on it."""

    async def test_a_waiter_cannot_discount(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The P1 design calls discounts one of the classic leakage vectors."""
        _, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        response = await _discount(
            api_client, token, order, type="percentage", rate="0.1000", reason="regular guest"
        )

        assert response.status_code == 403

    async def test_a_percentage_comes_off_before_tax_and_names_its_authoriser(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """₹940 less 10% is ₹846 taxable; 5% of that is ₹42.30, split ₹21.15 + ₹21.15."""
        world, menu, token = await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        order = await _added(
            api_client, token, await _open(api_client, token, menu), menu.dal, quantity=2
        )

        discounted = await _discounted(
            api_client, manager, order, type="percentage", rate="0.1000", reason="regular guest"
        )

        (line,) = discounted["lines"]
        assert line["line_discount"] == "94.00"
        assert line["taxable_value"] == "846.00"
        assert (line["cgst_amount"], line["sgst_amount"]) == ("21.15", "21.15")
        assert discounted["discount_total"] == "94.00"
        assert discounted["grand_total"] == "888.30"
        (discount,) = discounted["discounts"]
        assert discount["authorised_by"] == decode_access_token(manager).employee_id
        audit = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.restaurant_id == world.restaurant.id, AuditLog.action == "order.discount"
            )
        )
        assert audit is not None

    async def test_an_order_discount_reaches_the_lines_to_the_paisa(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """₹100 off ₹470 + ₹350. Pro rata is ₹57.317… and ₹42.682…; rounding both down loses a
        paisa, which goes to the share rounding cut most — the dal's — so ₹57.32 and ₹42.68."""
        _, menu, token = await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        order = await _added(api_client, token, order, menu.paneer, modifiers=(menu.mild,))

        discounted = await _discounted(
            api_client, manager, order, type="flat", flat_amount="100.00", reason="birthday"
        )

        assert _line_of(discounted, menu.dal)["line_discount"] == "57.32"
        assert _line_of(discounted, menu.paneer)["line_discount"] == "42.68"
        assert discounted["discount_total"] == "100.00"

    async def test_a_comp_on_one_dish_takes_the_dish_and_its_tax_off_the_bill(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        order = await _added(api_client, token, order, menu.paneer, modifiers=(menu.mild,))

        discounted = await _discounted(
            api_client,
            manager,
            order,
            type="comp",
            rate="1.0000",
            order_line_id=_line_of(order, menu.dal)["id"],
            reason="dish was late",
        )

        dal = _line_of(discounted, menu.dal)
        assert (dal["taxable_value"], dal["tax_amount"]) == ("0.00", "0.00")
        # The paneer alone: ₹350 + ₹8.75 + ₹8.75.
        assert discounted["grand_total"] == "367.50"

    async def test_a_discount_larger_than_what_it_comes_off_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        response = await _discount(
            api_client, manager, order, type="flat", flat_amount="1000.00", reason="mistake"
        )

        assert response.status_code == 422
        assert response.json()["code"] == "order_discount.exceeds_base"

    async def test_a_discount_without_a_reason_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        response = await _discount(api_client, manager, order, type="percentage", rate="0.1000")

        assert response.status_code == 422

    async def test_removing_a_discount_restores_the_bill_and_is_audited(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        discounted = await _discounted(
            api_client, manager, order, type="percentage", rate="0.1000", reason="regular guest"
        )

        removed = await _stepped(
            api_client, manager, discounted, f"discounts/{discounted['discounts'][0]['id']}/remove"
        )

        assert removed["discounts"] == []
        assert removed["grand_total"] == "493.50"
        audit = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.restaurant_id == world.restaurant.id,
                AuditLog.action == "order.discount_removed",
            )
        )
        assert audit is not None

    async def test_a_dish_taken_off_takes_its_discount_with_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        order = await _added(api_client, token, order, menu.paneer, modifiers=(menu.mild,))
        order = await _stepped(api_client, token, order, "send")
        order = await _discounted(
            api_client,
            manager,
            order,
            type="comp",
            rate="1.0000",
            order_line_id=_line_of(order, menu.dal)["id"],
            reason="dish was late",
        )

        removed = await _stepped(
            api_client,
            token,
            order,
            f"lines/{_line_of(order, menu.dal)['id']}/remove",
            reason="guest left it",
        )

        assert removed["discounts"][0]["amount"] == "0.00"
        assert removed["grand_total"] == "367.50"

    async def test_a_dish_cannot_come_off_under_a_discount_it_would_no_longer_cover(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """₹400 off a ₹820 bill is fine; the same ₹400 off the ₹350 left after the dal goes is not,
        and the whole change is refused rather than half made."""
        _, menu, token = await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        order = await _added(api_client, token, order, menu.paneer, modifiers=(menu.mild,))
        order = await _stepped(api_client, token, order, "send")
        order = await _discounted(
            api_client, manager, order, type="flat", flat_amount="400.00", reason="event booking"
        )

        response = await _step(
            api_client,
            token,
            order,
            f"lines/{_line_of(order, menu.dal)['id']}/remove",
            reason="guest left it",
        )
        after = await api_client.get(f"{ORDERS}/{order['id']}", headers=_auth(token))

        assert response.status_code == 409
        assert response.json()["code"] == "order.discount_exceeds_bill"
        assert _line_of(after.json(), menu.dal)["status"] == "sent"


# --------------------------------------------------------------------------- charges


async def _charge(client: AsyncClient, token: str, order: dict[str, Any], **body: Any) -> Response:
    return await client.post(
        f"{ORDERS}/{order['id']}/charges",
        json={"version": order["version"]} | body,
        headers=_auth(token),
    )


class TestCharges:
    """Decision 7: packaging taxed with the meal, a service charge only ever on purpose."""

    async def test_packaging_is_taxed_at_the_meals_rate(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _open(api_client, token, menu, type="takeaway", table_ids=[])
        order = await _added(api_client, token, order, menu.dal)

        response = await _charge(
            api_client,
            token,
            order,
            type="packaging",
            amount="20.00",
            tax_group_id=str(menu.tax_group),
        )

        assert response.status_code == 201, response.text
        charged = response.json()
        (charge,) = charged["charges"]
        assert (charge["amount"], charge["tax_amount"]) == ("20.00", "1.00")
        assert charge["is_optional"] is False
        assert charged["charge_total"] == "20.00"
        # ₹470 + ₹23.50 of dal, ₹20 + ₹1.00 of packaging.
        assert charged["grand_total"] == "514.50"

    async def test_no_order_carries_a_service_charge_it_was_not_given(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 15: never default-applied, even where one is enabled."""
        world, menu, token = await _setup(db_session, api_client)
        world.restaurant.service_charge_rate = Decimal("0.1000")
        await db_session.commit()

        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        assert order["charges"] == []
        assert order["charge_total"] == "0.00"

    async def test_a_service_charge_is_refused_where_the_restaurant_has_none(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        response = await _charge(api_client, token, order, type="service_charge")

        assert response.status_code == 409
        assert response.json()["code"] == "service_charge.disabled"

    async def test_an_enabled_service_charge_is_computed_optional_and_removable(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        world.restaurant.service_charge_rate = Decimal("0.1000")
        await db_session.commit()
        order = await _added(
            api_client, token, await _open(api_client, token, menu), menu.dal, quantity=2
        )

        response = await _charge(api_client, token, order, type="service_charge")
        assert response.status_code == 201, response.text
        charged = response.json()
        removed = await _stepped(
            api_client, token, charged, f"charges/{charged['charges'][0]['id']}/remove"
        )

        (charge,) = charged["charges"]
        assert charge["amount"] == "94.00"
        assert charge["is_optional"] is True
        assert charge["tax_amount"] == "0.00"
        assert charged["grand_total"] == "1081.00"
        assert removed["charges"] == []
        assert removed["grand_total"] == "987.00"

    async def test_a_service_charge_typed_in_by_hand_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        response = await _charge(api_client, token, order, type="service_charge", amount="50.00")

        assert response.status_code == 422


# --------------------------------------------------------------------------- splitting


class TestSplittingByItems:
    """Decision 9: split before settlement, so one order still settles to one invoice."""

    async def test_the_chosen_dishes_move_to_a_new_order_at_the_same_table(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        order = await _added(api_client, token, order, menu.paneer, modifiers=(menu.mild,))
        order = await _stepped(api_client, token, order, "send")

        response = await api_client.post(
            f"{ORDERS}/{order['id']}/split",
            json={"version": order["version"], "line_ids": [_line_of(order, menu.paneer)["id"]]},
            headers=_auth(token),
        )
        original = await api_client.get(f"{ORDERS}/{order['id']}", headers=_auth(token))

        assert response.status_code == 201, response.text
        child = response.json()
        assert child["parent_order_id"] == order["id"]
        assert child["table_ids"] == [str(menu.table)]
        assert child["status"] == "sent"
        assert [line["menu_item_variant_id"] for line in child["lines"]] == [str(menu.paneer)]
        assert child["grand_total"] == "367.50"
        remaining = original.json()
        assert [line["menu_item_variant_id"] for line in remaining["lines"]] == [str(menu.dal)]
        assert remaining["grand_total"] == "493.50"
        assert remaining["version"] > order["version"]

    async def test_a_discount_on_a_moved_dish_moves_with_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)
        order = await _added(api_client, token, order, menu.paneer, modifiers=(menu.mild,))
        order = await _discounted(
            api_client,
            manager,
            order,
            type="comp",
            rate="1.0000",
            order_line_id=_line_of(order, menu.paneer)["id"],
            reason="birthday dish",
        )

        response = await api_client.post(
            f"{ORDERS}/{order['id']}/split",
            json={"version": order["version"], "line_ids": [_line_of(order, menu.paneer)["id"]]},
            headers=_auth(token),
        )
        original = await api_client.get(f"{ORDERS}/{order['id']}", headers=_auth(token))

        assert response.status_code == 201, response.text
        assert len(response.json()["discounts"]) == 1
        assert response.json()["grand_total"] == "0.00"
        assert original.json()["discounts"] == []
        assert original.json()["grand_total"] == "493.50"

    async def test_splitting_off_every_dish_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, menu, token = await _setup(db_session, api_client)
        order = await _added(api_client, token, await _open(api_client, token, menu), menu.dal)

        response = await api_client.post(
            f"{ORDERS}/{order['id']}/split",
            json={"version": order["version"], "line_ids": [order["lines"][0]["id"]]},
            headers=_auth(token),
        )

        assert response.status_code == 409
        assert response.json()["code"] == "order.split_everything"


# --------------------------------------------------------------------------- the second reader


class TestADiscountNeverGrowsPastItsAuthorisation:
    async def test_a_comp_does_not_grow_when_a_waiter_orders_more_of_the_dish(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Second reader, finding 4. A manager comps one dal. The waiter, who holds no discount
        permission, raises the unsent dal to three. The comp covers what the manager authorised,
        ₹470, and the other two dals are billed."""
        _, menu, waiter = await _setup(db_session, api_client)
        manager = await _token(api_client, "manager")
        order = await _added(api_client, waiter, await _open(api_client, waiter, menu), menu.dal)
        comped = await _discounted(
            api_client,
            manager,
            order,
            type="comp",
            rate="1.0000",
            order_line_id=_line_of(order, menu.dal)["id"],
            reason="dish was late",
        )
        dal = _line_of(comped, menu.dal)

        changed = await api_client.patch(
            f"{ORDERS}/{comped['id']}/lines/{dal['id']}",
            json={"version": comped["version"], "quantity": 3},
            headers=_auth(waiter),
        )

        assert changed.status_code == 200, changed.text
        assert _line_of(changed.json(), menu.dal)["line_discount"] == "470.00"
        assert changed.json()["discount_total"] == "470.00"
