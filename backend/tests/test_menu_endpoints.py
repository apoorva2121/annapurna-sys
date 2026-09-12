"""The menu surface, and the rules it exists to keep.

Four of these are worth reading before the rest, because they are the ones that would be expensive
to discover later:

- **`test_the_menu_tree_costs_the_same_for_12_dishes_and_400`** — `docs/modules.md` names this as
  M03's headline test. It runs against a *generated* 400-dish menu, not the seed: a test that only
  ever sees twelve dishes cannot tell a flat query count from a linear one, which is precisely how
  an N+1 ships.
- **`test_a_code_cannot_be_changed`** — `menu_item.code` is the join key to `library/dishes.yaml`
  and to every recipe M04 will attach. Renaming it breaks cost tracking while sales carry on.
- **`test_attaching_another_tenants_modifier_group_is_refused`** — `menu_item_modifier_group` has
  no `restaurant_id`, so the repository base class cannot filter it and the generic isolation suite
  cannot probe it as a row. This is the test that covers what the structure does not.
- **`test_a_manager_may_shape_the_menu_but_not_price_it`** — `seed/organization.yaml`'s P1 design
  draws that line by name, and a binary permission would have erased it.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.menu import (
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    MenuItemVariant,
    Modifier,
    ModifierGroup,
)
from app.models.setup import Station, TaxGroup, TaxRate
from tests.helpers.queries import count_queries
from tests.test_setup_endpoints import _auth, _token, _world

MENU = "/api/v1/staff/menu"


async def _scaffold(session: AsyncSession, restaurant_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """A station and a tax group, which every dish needs before it can exist.

    Written directly rather than through the API: this fixture must not depend on the endpoints the
    tests are about to probe.
    """
    station = Station(
        restaurant_id=restaurant_id, code="tandoor", name="Tandoor", seq=0, is_active=True
    )
    tax = TaxGroup(restaurant_id=restaurant_id, code="GST5", name="GST 5%", is_active=True)
    session.add_all([station, tax])
    await session.flush()
    session.add(
        TaxRate(
            restaurant_id=restaurant_id,
            tax_group_id=tax.id,
            rate=Decimal("0.0500"),
            is_inclusive=False,
            effective_from=date(2025, 4, 1),
        )
    )
    await session.flush()
    return {"station_id": station.id, "tax_group_id": tax.id}


async def _category(client: AsyncClient, token: str, *, code: str = "MAIN_VEG") -> str:
    response = await client.post(
        f"{MENU}/categories",
        json={"code": code, "name": code.title()},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    created: str = response.json()["id"]
    return created


async def _dish(
    client: AsyncClient,
    token: str,
    ids: dict[str, uuid.UUID],
    category_id: str,
    *,
    code: str = "BUTTER_CHICKEN",
    price: str = "470.00",
) -> dict[str, object]:
    response = await client.post(
        f"{MENU}/items",
        json={
            "menu_category_id": category_id,
            "code": code,
            "name": code.replace("_", " ").title(),
            "food_type": "non_veg",
            "station_id": str(ids["station_id"]),
            "variants": [
                {
                    "code": "FULL",
                    "name": "Full",
                    "price": price,
                    "tax_group_id": str(ids["tax_group_id"]),
                    "prep_minutes": 11,
                }
            ],
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


# --------------------------------------------------------------------------- the tree


class TestTheMenuTree:
    async def test_the_menu_tree_costs_the_same_for_12_dishes_and_400(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """**The headline test of this module** (`docs/modules.md`, M03).

        A three-level tree plus a many-to-many is the textbook N+1, and the obvious implementation —
        load categories, then each category's items, then each item's variants — passes every test
        written against a small fixture. So this compares twelve dishes with four hundred and
        asserts the *shape*: the same number of statements, not a number under a budget. A budget
        of six passes for twelve dishes while still hiding a query per dish.

        Rows are written directly rather than through the API: four hundred POSTs would make this
        test take minutes and would be measuring the wrong thing.
        """
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        engine = db_session.get_bind().engine

        await _bulk_menu(db_session, world.restaurant.id, ids, dishes=12, prefix="SMALL")
        await db_session.commit()
        with count_queries(engine) as small:
            small_response = await api_client.get(MENU, headers=_auth(token))
        assert small_response.status_code == 200, small_response.text

        await _bulk_menu(db_session, world.restaurant.id, ids, dishes=388, prefix="LARGE")
        await db_session.commit()
        with count_queries(engine) as large:
            large_response = await api_client.get(MENU, headers=_auth(token))
        assert large_response.status_code == 200

        small_count = sum(len(c["items"]) for c in small_response.json()["categories"])
        large_count = sum(len(c["items"]) for c in large_response.json()["categories"])
        # The generated dishes must really carry modifier groups. An empty parent set makes
        # SQLAlchemy skip a `selectinload` entirely, so without this the comparison below would be
        # blind to an N+1 in the modifier leg while looking exactly as green.
        assert all(
            item["modifier_groups"] and item["modifier_groups"][0]["modifiers"]
            for category in large_response.json()["categories"]
            for item in category["items"]
        )
        assert large_count >= 400 > small_count, (small_count, large_count)
        assert large.count == small.count, (
            f"the tree issued {small.count} queries for {small_count} dishes and "
            f"{large.count} for {large_count} — the cost is scaling with the menu"
        )

    async def test_the_tree_still_returns_variants_and_modifiers(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The cheapest way to make the test above pass is to stop returning the nested rows. This
        is what stops that being an option."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category_id = await _category(api_client, token)
        item = await _dish(api_client, token, ids, category_id)
        group = await api_client.post(
            f"{MENU}/modifier-groups",
            json={
                "code": "SPICE_LEVEL",
                "name": "Spice level",
                "modifiers": [{"code": "MILD", "name": "Mild", "price_delta": "0.00"}],
            },
            headers=_auth(token),
        )
        await api_client.put(
            f"{MENU}/items/{item['id']}/modifier-groups",
            json={"modifier_group_ids": [group.json()["id"]]},
            headers=_auth(token),
        )

        tree = (await api_client.get(MENU, headers=_auth(token))).json()

        dish = tree["categories"][0]["items"][0]
        assert dish["variants"][0]["price"] == "470.00"
        assert dish["modifier_groups"][0]["code"] == "SPICE_LEVEL"
        assert dish["modifier_groups"][0]["modifiers"][0]["name"] == "Mild"

    async def test_a_second_request_with_the_etag_returns_304(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The waiter PWA loads this on every app start, on a restaurant basement network."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        first = await api_client.get(MENU, headers=_auth(token))
        etag = first.headers["ETag"]
        second = await api_client.get(MENU, headers={**_auth(token), "If-None-Match": etag})

        assert second.status_code == 304
        assert second.content == b""

    async def test_a_menu_write_invalidates_the_etag(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A write that does not bump the version is a change no client ever sees — the cache has
        no expiry to save it."""
        world = await _world(db_session, "owner")
        await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        etag = (await api_client.get(MENU, headers=_auth(token))).headers["ETag"]

        await _category(api_client, token)

        after = await api_client.get(MENU, headers={**_auth(token), "If-None-Match": etag})
        assert after.status_code == 200, "the write did not invalidate the ETag"
        assert after.headers["ETag"] != etag

    async def test_the_tree_hides_deactivated_dishes_by_default(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A waiter must never see a dish that cannot be ordered; a manager must be able to find it
        again to bring it back."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category_id = await _category(api_client, token)
        item = await _dish(api_client, token, ids, category_id)
        await api_client.patch(
            f"{MENU}/items/{item['id']}", json={"is_active": False}, headers=_auth(token)
        )

        default = (await api_client.get(MENU, headers=_auth(token))).json()
        shown = (await api_client.get(f"{MENU}?include_inactive=true", headers=_auth(token))).json()

        assert [i for c in default["categories"] for i in c["items"]] == []
        assert len([i for c in shown["categories"] for i in c["items"]]) == 1


# --------------------------------------------------------------------------- codes


class TestCodesAreContracts:
    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("categories", {"code": "OTHER"}),
            ("items", {"code": "OTHER"}),
        ],
    )
    async def test_a_code_cannot_be_changed(
        self,
        db_session: AsyncSession,
        api_client: AsyncClient,
        path: str,
        body: dict[str, str],
    ) -> None:
        """`menu_item.code` joins this row to `library/dishes.yaml`, to `seed/menu.yaml` and to
        every recipe M04 attaches. Renaming it breaks cost tracking while sales carry on — a silent
        failure, which is why the schema offers no field rather than the service refusing one."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category_id = await _category(api_client, token)
        target = (
            category_id
            if path == "categories"
            else str((await _dish(api_client, token, ids, category_id))["id"])
        )

        response = await api_client.patch(
            f"{MENU}/{path}/{target}", json=body, headers=_auth(token)
        )

        assert response.status_code == 422, response.text

    async def test_a_dish_code_cannot_be_reused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category_id = await _category(api_client, token)
        await _dish(api_client, token, ids, category_id)

        response = await api_client.post(
            f"{MENU}/items",
            json={
                "menu_category_id": category_id,
                "code": "BUTTER_CHICKEN",
                "name": "Butter Chicken (new)",
                "food_type": "non_veg",
                "station_id": str(ids["station_id"]),
                "variants": [],
            },
            headers=_auth(token),
        )

        assert response.status_code == 409
        assert response.json()["code"] == "menu_item.code_taken"

    async def test_a_lowercase_code_is_accepted_and_stored_uppercase(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Refusing `butter_chicken` for its case would be a rule the person typing it has no way
        to know. Normalising gives the unique constraint exactly one spelling to police."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{MENU}/categories", json={"code": "main_veg", "name": "Mains"}, headers=_auth(token)
        )

        assert response.status_code == 201
        assert response.json()["code"] == "MAIN_VEG"


# --------------------------------------------------------------------------- money


class TestPrice:
    async def test_a_price_is_a_string_never_a_float(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """CLAUDE.md invariant 3 at the API boundary. A price that arrives as a JavaScript number
        has already lost the exactness that makes a bill reproducible."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category_id = await _category(api_client, token)

        item = await _dish(api_client, token, ids, category_id, price="470.50")

        variants = item["variants"]
        assert isinstance(variants, list)
        assert variants[0]["price"] == "470.50"

    async def test_a_third_decimal_place_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`NUMERIC(12,2)` would round it silently. Refusing at the boundary means the person who
        typed ₹470.555 finds out, rather than the bill quietly saying ₹470.56."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category_id = await _category(api_client, token)

        response = await api_client.post(
            f"{MENU}/items",
            json={
                "menu_category_id": category_id,
                "code": "ODD",
                "name": "Odd",
                "food_type": "veg",
                "station_id": str(ids["station_id"]),
                "variants": [
                    {
                        "code": "FULL",
                        "name": "Full",
                        "price": "470.555",
                        "tax_group_id": str(ids["tax_group_id"]),
                        "prep_minutes": 10,
                    }
                ],
            },
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_a_reprice_writes_an_audit_row_with_before_and_after(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Invariant 6, and the M03 threat table's first row: a manager raising a price and taking
        the difference on cash orders leaves no other trace."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category_id = await _category(api_client, token)
        item = await _dish(api_client, token, ids, category_id, price="470.00")
        variants = item["variants"]
        assert isinstance(variants, list)
        variant_id = variants[0]["id"]

        await api_client.patch(
            f"{MENU}/variants/{variant_id}", json={"price": "520.00"}, headers=_auth(token)
        )

        repriced = (
            await db_session.scalars(
                select(AuditLog).where(AuditLog.action == "menu_item_variant.repriced")
            )
        ).all()
        assert len(repriced) == 1
        assert repriced[0].old_value == {"price": "470.00"}
        assert repriced[0].new_value == {"price": "520.00"}


# --------------------------------------------------------------------------- permissions


class TestPermissions:
    async def test_a_manager_may_shape_the_menu_but_not_price_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`seed/organization.yaml` draws this line by name:

            - menu.view, menu.manage
            # deliberately NOT granted: menu.price ...  - these are the owner's.

        A manager fixing a dish name is an ordinary Tuesday. A manager raising a price is the threat
        table's first row. A binary permission cannot express both.
        """
        world = await _world(db_session, "owner", "manager")
        ids = await _scaffold(db_session, world.restaurant.id)
        owner = await _token(api_client, "owner")
        category_id = await _category(api_client, owner)
        item = await _dish(api_client, owner, ids, category_id)
        variants = item["variants"]
        assert isinstance(variants, list)
        manager = await _token(api_client, "manager")

        renamed = await api_client.patch(
            f"{MENU}/items/{item['id']}", json={"name": "Butter Chicken"}, headers=_auth(manager)
        )
        repriced = await api_client.patch(
            f"{MENU}/variants/{variants[0]['id']}",
            json={"price": "1.00"},
            headers=_auth(manager),
        )

        assert renamed.status_code == 200, renamed.text
        assert repriced.status_code == 403, repriced.text

    async def test_a_manager_cannot_create_a_dish_because_a_dish_carries_a_price(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`POST /menu/items` takes `menu.price` even though most of it is structure: the request
        may carry variants, and a variant carries a price. Otherwise a `menu.manage` holder creates
        the dish at ₹1 and the boundary was decoration."""
        world = await _world(db_session, "owner", "manager")
        ids = await _scaffold(db_session, world.restaurant.id)
        owner = await _token(api_client, "owner")
        category_id = await _category(api_client, owner)
        manager = await _token(api_client, "manager")

        response = await api_client.post(
            f"{MENU}/items",
            json={
                "menu_category_id": category_id,
                "code": "CHEAP",
                "name": "Cheap",
                "food_type": "veg",
                "station_id": str(ids["station_id"]),
                "variants": [],
            },
            headers=_auth(manager),
        )

        assert response.status_code == 403

    async def test_a_waiter_may_read_the_menu(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A waiter who cannot read the menu cannot take an order, which makes `menu.view` the one
        permission this module must not get wrong in the restrictive direction."""
        await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "waiter")

        response = await api_client.get(MENU, headers=_auth(token))

        assert response.status_code == 200


# --------------------------------------------------------------------------- attachment


class TestModifierAttachment:
    async def test_attaching_another_tenants_modifier_group_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """**The test that covers what the structure cannot.**

        `menu_item_modifier_group` has no `restaurant_id`: both parents carry one, and a third copy
        is a third thing that can disagree (M03 spec, schema checklist Q7). The cost of that choice
        is that `RestaurantScopedRepository` cannot filter this table and the generic isolation
        suite cannot probe it as a row — so the check lives in the service and this is what holds it
        there.
        """
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category_id = await _category(api_client, token)
        item = await _dish(api_client, token, ids, category_id)
        # A second organization entirely, with its own modifier group.
        other = await _world(db_session, "owner", slug="rival-kitchen")
        rival = ModifierGroup(
            restaurant_id=other.restaurant.id,
            code="RIVALSPICE",
            name="Rival spice level",
            min_select=0,
            max_select=1,
            is_required=False,
            is_active=True,
        )
        db_session.add(rival)
        await db_session.commit()

        response = await api_client.put(
            f"{MENU}/items/{item['id']}/modifier-groups",
            json={"modifier_group_ids": [str(rival.id)]},
            headers=_auth(token),
        )

        assert response.status_code == 404, response.text
        assert response.json()["code"] == "modifier_group.not_found"

    async def test_bulk_apply_reaches_every_dish_in_the_category(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """ "All main courses get a spice level" is how an owner describes a menu; the model is per
        dish so one of them can opt out. This is the bridge between those two."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category_id = await _category(api_client, token)
        for code in ("DISH_A", "DISH_B", "DISH_C"):
            await _dish(api_client, token, ids, category_id, code=code)
        group = await api_client.post(
            f"{MENU}/modifier-groups",
            json={"code": "SPICE_LEVEL", "name": "Spice level"},
            headers=_auth(token),
        )

        response = await api_client.post(
            f"{MENU}/categories/{category_id}/modifier-groups",
            json={"modifier_group_ids": [group.json()["id"]]},
            headers=_auth(token),
        )

        assert response.status_code == 200
        assert response.json()["items_updated"] == 3
        tree = (await api_client.get(MENU, headers=_auth(token))).json()
        for dish in tree["categories"][0]["items"]:
            assert [g["code"] for g in dish["modifier_groups"]] == ["SPICE_LEVEL"]


# --------------------------------------------------------------------------- sellability


class TestADishIsSellableOrDeactivated:
    async def test_the_last_active_variant_cannot_be_switched_off(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A dish on the menu with nothing orderable under it is a line a waiter taps to no
        effect. Deactivating the dish is the operation that was actually meant."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category_id = await _category(api_client, token)
        item = await _dish(api_client, token, ids, category_id)
        variants = item["variants"]
        assert isinstance(variants, list)

        response = await api_client.patch(
            f"{MENU}/variants/{variants[0]['id']}",
            json={"is_active": False},
            headers=_auth(token),
        )

        assert response.status_code == 409
        assert response.json()["code"] == "menu_item_variant.last_active"

    async def test_a_category_with_active_dishes_cannot_be_deactivated(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category_id = await _category(api_client, token)
        await _dish(api_client, token, ids, category_id)

        response = await api_client.patch(
            f"{MENU}/categories/{category_id}", json={"is_active": False}, headers=_auth(token)
        )

        assert response.status_code == 409
        assert response.json()["code"] == "menu_category.has_active_items"
        assert response.json()["details"]["active_items"] == 1

    async def test_a_required_group_must_ask_for_at_least_one_choice(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A mandatory question with no answer that satisfies it is a screen nobody can leave."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{MENU}/modifier-groups",
            json={
                "code": "SPICE_LEVEL",
                "name": "Spice level",
                "min_select": 0,
                "max_select": 1,
                "is_required": True,
            },
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "modifier_group.required_needs_one"


# --------------------------------------------------------------------------- helpers


async def _bulk_menu(
    session: AsyncSession,
    restaurant_id: uuid.UUID,
    ids: dict[str, uuid.UUID],
    *,
    dishes: int,
    prefix: str,
) -> None:
    """`dishes` dishes across four categories, each with two variants **and a modifier group**.

    Written straight to the session. Four hundred POSTs would turn the query-count test into a
    minutes-long test measuring the write path, which is not what it is about.

    **The modifier groups are not decoration.** SQLAlchemy skips a `selectinload` whose parent set
    is empty, so a generated menu with no attachments never issues the three statements that load
    `menu_item_modifier_group`, `modifier_group` and `modifier` — and the headline N+1 test was
    therefore measuring half the loader chain while claiming to measure all of it. An N+1 in the
    modifier leg would have passed it. Found by the M03/M04 review.
    """
    groups: list[ModifierGroup] = []
    for index in range(2):
        group_row = ModifierGroup(
            restaurant_id=restaurant_id,
            code=f"{prefix}_OPT_{index}",
            name=f"{prefix} Options {index}",
            min_select=0,
            max_select=2,
            is_required=False,
            is_active=True,
        )
        session.add(group_row)
        await session.flush()
        for choice in range(3):
            session.add(
                Modifier(
                    restaurant_id=restaurant_id,
                    modifier_group_id=group_row.id,
                    code=f"{prefix}_OPT_{index}_{choice}",
                    name=f"Choice {choice}",
                    price_delta=Decimal("0.00"),
                    seq=choice,
                    is_active=True,
                )
            )
        groups.append(group_row)
    await session.flush()

    for group in range(4):
        category = MenuCategory(
            restaurant_id=restaurant_id,
            code=f"{prefix}_CAT_{group}",
            name=f"{prefix} Section {group}",
            seq=group,
            is_active=True,
        )
        session.add(category)
        await session.flush()
        for index in range(group, dishes, 4):
            item = MenuItem(
                restaurant_id=restaurant_id,
                menu_category_id=category.id,
                code=f"{prefix}_DISH_{index}",
                name=f"{prefix} Dish {index}",
                food_type="veg",
                station_id=ids["station_id"],
                seq=index,
                is_active=True,
            )
            session.add(item)
            await session.flush()
            session.add(
                MenuItemModifierGroup(
                    menu_item_id=item.id,
                    modifier_group_id=groups[index % len(groups)].id,
                    seq=0,
                )
            )
            for variant_code, price in (("HALF", "260.00"), ("FULL", "380.00")):
                session.add(
                    MenuItemVariant(
                        restaurant_id=restaurant_id,
                        menu_item_id=item.id,
                        code=variant_code,
                        name=variant_code.title(),
                        price=Decimal(price),
                        tax_group_id=ids["tax_group_id"],
                        prep_minutes=10,
                        seq=0 if variant_code == "HALF" else 1,
                        is_active=True,
                    )
                )
    await session.flush()
