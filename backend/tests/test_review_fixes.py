"""Regression tests for the defects the M03/M04 adversarial review found.

Every test here failed before its fix and passes after. They are grouped by defect rather than by
endpoint because that is how they will be read: someone who breaks one of these wants to know which
promise they broke, not which route they touched.

The four families:

1. **Cost visibility.** `seed/organization.yaml` says a chef sees grams, not rupees. The schemas
   carried the price on every read, so the whole ingredient price list was one `GET /stock-items`
   away from anyone who could open a recipe.
2. **Modifier pricing.** `price_delta` is money. It sat behind `menu.manage` and wrote no audit row,
   so "Extra paneer +Rs 150" was reachable by someone the P1 design denies pricing to, and left no
   trace afterwards.
3. **Tenancy in `recipe_line`.** The model docstring claimed a composite foreign key kept a line's
   component on the line's tenant. There was none — only a service check — and M04 hands a second
   write path to a later module.
4. **Unmapped `IntegrityError`s.** A duplicate id in an attachment list and an unvalidated
   `modifier_id` both reached the database and came back as 500s.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.stock import Recipe, RecipeLine, StockItem
from tests.test_menu_endpoints import _category, _dish, _scaffold
from tests.test_setup_endpoints import _auth, _token, _world

MENU = "/api/v1/staff/menu"
STAFF = "/api/v1/staff"


async def _ingredient(client: AsyncClient, token: str, *, code: str = "PANEER") -> str:
    response = await client.post(
        f"{STAFF}/stock-items",
        json={
            "kind": "ingredient",
            "code": code,
            "name": code.title(),
            "base_unit": "g",
            "category": "dairy",
            "current_unit_cost": "0.360000",
            "ingredient": {
                "purchase_unit": "kg",
                "purchase_to_base": "1000",
                "yield_factor": "0.98",
                "shelf_life_days": 4,
            },
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    created: str = response.json()["id"]
    return created


async def _group_body(client: AsyncClient, token: str, *, code: str = "SPICE") -> dict[str, Any]:
    response = await client.post(
        f"{MENU}/modifier-groups",
        json={
            "code": code,
            "name": code.title(),
            "is_required": False,
            "min_select": 0,
            "max_select": 1,
            "modifiers": [{"code": "MILD", "name": "Mild", "price_delta": "0.00"}],
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def _group(client: AsyncClient, token: str, *, code: str = "SPICE") -> str:
    return str((await _group_body(client, token, code=code))["id"])


# ------------------------------------------------------------------- 1 · a chef sees grams


class TestAChefSeesGramsNotRupees:
    """`cost.view` is held by the manager and the owner. The chef writes the recipe and is not
    told what it costs — which was true of the cost *endpoints* and not of anything else."""

    async def test_a_chef_reading_a_stock_item_is_not_told_its_price(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, owner)

        chef = await _token(api_client, "chef")
        body = (await api_client.get(f"{STAFF}/stock-items/{item_id}", headers=_auth(chef))).json()

        assert "current_unit_cost" not in body
        # The rest of the row is still the chef's job and still arrives.
        assert body["code"] == "PANEER"
        assert body["ingredient"]["yield_factor"] == "0.9800"

    async def test_an_owner_reading_the_same_item_is(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The other half. Stripping the field for everybody would also pass the test above."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, owner)

        body = (await api_client.get(f"{STAFF}/stock-items/{item_id}", headers=_auth(owner))).json()

        assert body["current_unit_cost"] == "0.360000"

    async def test_the_list_route_strips_the_price_too(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The list is the one that mattered: one request, the whole price list."""
        await _world(db_session, "owner", "chef")
        owner = await _token(api_client, "owner")
        await _ingredient(api_client, owner, code="PANEER")
        await _ingredient(api_client, owner, code="GHEE")

        chef = await _token(api_client, "chef")
        body = (await api_client.get(f"{STAFF}/stock-items", headers=_auth(chef))).json()

        assert len(body["items"]) == 2
        assert all("current_unit_cost" not in row for row in body["items"])

    async def test_a_chef_saving_a_recipe_is_not_told_what_it_costs(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`recipe.manage` is the chef's. The response used to hand back `unit_cost` anyway."""
        world = await _world(db_session, "owner", "chef")
        ids = await _scaffold(db_session, world.restaurant.id)
        owner = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, owner)
        category_id = await _category(api_client, owner)
        dish = await _dish(api_client, owner, ids, category_id)
        variant_id = dish["variants"][0]["id"]  # type: ignore[index]

        chef = await _token(api_client, "chef")
        response = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "menu_item_variant_id": variant_id,
                "lines": [{"component_id": item_id, "quantity": "200"}],
            },
            headers=_auth(chef),
        )

        assert response.status_code == 201, response.text
        assert "unit_cost" not in response.json()
        # The quantities are the chef's own work and must survive.
        assert response.json()["lines"][0]["quantity"] == "200.0000"


# ------------------------------------------------------------------- 2 · a price is a price


class TestAModifierPriceIsAPrice:
    async def test_a_manager_cannot_price_an_option(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The manager holds `menu.manage` and is denied `menu.price` by name. Adding "Extra
        paneer +Rs 150" was a price change reachable without the pricing permission."""
        await _world(db_session, "owner", "manager")
        owner = await _token(api_client, "owner")
        group_id = await _group(api_client, owner)

        manager = await _token(api_client, "manager")
        response = await api_client.post(
            f"{MENU}/modifier-groups/{group_id}/modifiers",
            json={"code": "EXTRA_PANEER", "name": "Extra paneer", "price_delta": "150.00"},
            headers=_auth(manager),
        )

        assert response.status_code == 403, response.text

    async def test_repricing_an_option_writes_an_audit_row(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Invariant 6. A move from +Rs 30 to +Rs 150 leaves no other trace: the menu still reads
        "Extra paneer" and the bill is simply larger."""
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        group_id = await _group(api_client, owner)

        created = await api_client.post(
            f"{MENU}/modifier-groups/{group_id}/modifiers",
            json={"code": "EXTRA_PANEER", "name": "Extra paneer", "price_delta": "30.00"},
            headers=_auth(owner),
        )
        assert created.status_code == 201, created.text
        modifier_id = next(
            row["id"] for row in created.json()["modifiers"] if row["code"] == "EXTRA_PANEER"
        )

        response = await api_client.patch(
            f"{MENU}/modifiers/{modifier_id}",
            json={"price_delta": "150.00"},
            headers=_auth(owner),
        )
        assert response.status_code == 200, response.text

        rows = list(
            await db_session.scalars(select(AuditLog).where(AuditLog.action == "modifier.repriced"))
        )
        assert len(rows) == 1
        assert rows[0].old_value == {"price_delta": "30.00"}
        assert rows[0].new_value == {"price_delta": "150.00"}

    async def test_a_rename_alone_writes_no_audit_row(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The other side of the same guard. An audit log that records everything records
        nothing — the rows that matter stop being findable."""
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        group_id = await _group(api_client, owner)
        created = await api_client.post(
            f"{MENU}/modifier-groups/{group_id}/modifiers",
            json={"code": "EXTRA_PANEER", "name": "Extra paneer", "price_delta": "30.00"},
            headers=_auth(owner),
        )
        modifier_id = next(
            row["id"] for row in created.json()["modifiers"] if row["code"] == "EXTRA_PANEER"
        )

        response = await api_client.patch(
            f"{MENU}/modifiers/{modifier_id}",
            json={"name": "Extra paneer (large)"},
            headers=_auth(owner),
        )
        assert response.status_code == 200, response.text

        rows = list(
            await db_session.scalars(select(AuditLog).where(AuditLog.action == "modifier.repriced"))
        )
        assert rows == []


# ------------------------------------------------------------------- 3 · the tenant boundary


class TestARecipeLineCannotCrossATenant:
    async def test_the_database_refuses_a_component_from_another_restaurant(
        self, db_session: AsyncSession
    ) -> None:
        """**Written against the database, not the service, and deliberately so.**

        `StockService.save_version` already refused this. The claim the review falsified was that
        the *schema* refused it — which matters because M04 hands a second write path to the
        `library/` matching flow, and a guard living in one service does not cover a second writer.
        """
        mine = await _world(db_session, "owner", slug="spice-garden")
        theirs = await _world(db_session, "owner", slug="rival-kitchen")

        theirs_paneer = StockItem(
            restaurant_id=theirs.restaurant.id,
            kind="ingredient",
            code="PANEER",
            name="Paneer",
            base_unit="g",
            current_unit_cost=Decimal("0.360000"),
            is_active=True,
        )
        db_session.add(theirs_paneer)
        await db_session.flush()

        recipe = Recipe(
            restaurant_id=mine.restaurant.id,
            produces_stock_item_id=None,
            modifier_id=None,
            menu_item_variant_id=None,
            version=1,
            is_current=True,
            effective_from=datetime.now(UTC),
            source="typed",
        )
        # A recipe needs exactly one owner, so give it one of its own making.
        mine_prep = StockItem(
            restaurant_id=mine.restaurant.id,
            kind="preparation",
            code="MAKHANI",
            name="Makhani gravy",
            base_unit="ml",
            current_unit_cost=Decimal("0"),
            is_active=True,
        )
        db_session.add(mine_prep)
        await db_session.flush()
        recipe.produces_stock_item_id = mine_prep.id
        db_session.add(recipe)
        await db_session.flush()

        db_session.add(
            RecipeLine(
                restaurant_id=mine.restaurant.id,
                recipe_id=recipe.id,
                component_id=theirs_paneer.id,
                quantity=Decimal("200"),
                seq=0,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()


# ------------------------------------------------------------------- 4 · not a 500


class TestWhatUsedToBeA500:
    async def test_the_same_modifier_group_twice_is_accepted_once(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`menu_item_modifier_group`'s primary key is the pair, so a repeated id was an
        `IntegrityError` and — the exception being unmapped — a 500. A UI that lets somebody tick
        "Spice level" twice before saving produced it."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        owner = await _token(api_client, "owner")
        category_id = await _category(api_client, owner)
        dish = await _dish(api_client, owner, ids, category_id)
        group_id = await _group(api_client, owner)

        response = await api_client.put(
            f"{MENU}/items/{dish['id']}/modifier-groups",
            json={"modifier_group_ids": [group_id, group_id]},
            headers=_auth(owner),
        )

        assert response.status_code == 200, response.text

    async def test_a_recipe_for_a_modifier_that_does_not_exist_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Nothing validated `recipe.modifier_id` at all — not existence, not tenancy. Combined
        with the then-global `uq_recipe_current_modifier`, one tenant could take another's slot."""
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, owner)

        response = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "modifier_id": str(uuid.uuid4()),
                "lines": [{"component_id": item_id, "quantity": "40"}],
            },
            headers=_auth(owner),
        )

        assert response.status_code == 404, response.text
        assert response.json()["code"] == "modifier.not_found"

    async def test_a_recipe_for_another_tenants_modifier_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The same check, doing the work it exists for."""
        await _world(db_session, "owner", slug="spice-garden")
        theirs = await _world(db_session, "owner", slug="rival-kitchen")
        ids = await _scaffold(db_session, theirs.restaurant.id)
        assert ids  # the rival's scaffold; the group below is theirs

        rival = await _token(api_client, "owner", slug="rival-kitchen")
        rival_modifier = (await _group_body(api_client, rival))["modifiers"][0]["id"]

        owner = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, owner)
        response = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "modifier_id": rival_modifier,
                "lines": [{"component_id": item_id, "quantity": "40"}],
            },
            headers=_auth(owner),
        )

        assert response.status_code == 404, response.text


# ------------------------------------------------------------------- 5 · one depth rule


class TestNestingDepthAgreesEverywhere:
    """ADR 0006 allows a recipe to nest three levels. Three places count those levels and they
    must agree: `check_depth_and_cycles` at save time, `cost_of` when a screen asks, and
    `seed/validate.py` over the YAML the product ships.

    They did not. The save-time walk seeded its chain with the owner's code — needed to catch a
    preparation that contains itself — and then counted that code toward the depth, so it refused
    at three what the other two allowed at three. A chef building a gravy from a paste from a spice
    mix was told the recipe was too deep, while the seed shipping exactly that shape validated.
    """

    async def _preparation(
        self,
        client: AsyncClient,
        token: str,
        station_id: uuid.UUID,
        code: str,
    ) -> str:
        response = await client.post(
            f"{STAFF}/stock-items",
            json={
                "kind": "preparation",
                "code": code,
                "name": code.title(),
                "base_unit": "ml",
                "preparation": {
                    "batch_yield": "1000",
                    "shelf_life_hours": 36,
                    "station_id": str(station_id),
                    "prep_minutes": 30,
                },
            },
            headers=_auth(token),
        )
        assert response.status_code == 201, response.text
        return str(response.json()["id"])

    async def _recipe_for_preparation(
        self, client: AsyncClient, token: str, produces: str, component: str
    ) -> int:
        response = await client.post(
            f"{STAFF}/recipes",
            json={
                "produces_stock_item_id": produces,
                "lines": [{"component_id": component, "quantity": "500"}],
            },
            headers=_auth(token),
        )
        return response.status_code

    async def test_a_dish_three_preparations_deep_is_accepted(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Dish -> spice mix -> paste -> gravy is three levels, which ADR 0006 allows and
        `seed/validate.py` accepts. Save time refused it."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        owner = await _token(api_client, "owner")
        station_id = ids["station_id"]
        cumin = await _ingredient(api_client, owner, code="CUMIN")

        mix = await self._preparation(api_client, owner, station_id, "PREP_MIX")
        paste = await self._preparation(api_client, owner, station_id, "PREP_PASTE")
        gravy = await self._preparation(api_client, owner, station_id, "PREP_GRAVY")
        assert await self._recipe_for_preparation(api_client, owner, mix, cumin) == 201
        assert await self._recipe_for_preparation(api_client, owner, paste, mix) == 201
        assert await self._recipe_for_preparation(api_client, owner, gravy, paste) == 201

        category_id = await _category(api_client, owner)
        dish = await _dish(api_client, owner, ids, category_id)
        response = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "menu_item_variant_id": dish["variants"][0]["id"],  # type: ignore[index]
                "lines": [{"component_id": gravy, "quantity": "250"}],
            },
            headers=_auth(owner),
        )

        assert response.status_code == 201, response.text

    async def test_the_cost_screen_agrees_that_it_is_allowed(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The other half of "the two checks agree": the same recipe must also cost, rather than
        saving and then raising on every screen that reads it."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        owner = await _token(api_client, "owner")
        station_id = ids["station_id"]
        cumin = await _ingredient(api_client, owner, code="CUMIN")
        mix = await self._preparation(api_client, owner, station_id, "PREP_MIX")
        paste = await self._preparation(api_client, owner, station_id, "PREP_PASTE")
        gravy = await self._preparation(api_client, owner, station_id, "PREP_GRAVY")
        await self._recipe_for_preparation(api_client, owner, mix, cumin)
        await self._recipe_for_preparation(api_client, owner, paste, mix)
        await self._recipe_for_preparation(api_client, owner, gravy, paste)
        category_id = await _category(api_client, owner)
        dish = await _dish(api_client, owner, ids, category_id)
        variant_id = dish["variants"][0]["id"]  # type: ignore[index]
        await api_client.post(
            f"{STAFF}/recipes",
            json={
                "menu_item_variant_id": variant_id,
                "lines": [{"component_id": gravy, "quantity": "250"}],
            },
            headers=_auth(owner),
        )

        response = await api_client.get(
            f"{STAFF}/menu-variants/{variant_id}/cost", headers=_auth(owner)
        )

        assert response.status_code == 200, response.text
        assert Decimal(response.json()["cost"]) > 0

    async def test_a_fourth_level_is_still_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The limit is still a limit. Relaxing the off-by-one must not relax the rule."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        owner = await _token(api_client, "owner")
        station_id = ids["station_id"]
        cumin = await _ingredient(api_client, owner, code="CUMIN")
        mix = await self._preparation(api_client, owner, station_id, "PREP_MIX")
        paste = await self._preparation(api_client, owner, station_id, "PREP_PASTE")
        gravy = await self._preparation(api_client, owner, station_id, "PREP_GRAVY")
        sauce = await self._preparation(api_client, owner, station_id, "PREP_SAUCE")
        await self._recipe_for_preparation(api_client, owner, mix, cumin)
        await self._recipe_for_preparation(api_client, owner, paste, mix)
        await self._recipe_for_preparation(api_client, owner, gravy, paste)

        status = await self._recipe_for_preparation(api_client, owner, sauce, gravy)

        assert status == 422


# ------------------------------------------------------------------- 6 · the editor can read back


class TestADishReportsItsOwnOptions:
    async def test_a_dish_carries_the_groups_attached_to_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Attachment is a `PUT` of the whole set, and nothing in the API said what the set was.

        So the options editor started from nothing ticked, and saving anything at all detached
        every group the dish already had — silently, with a 200. The screen could not have got this
        right; the response had to carry it.
        """
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        owner = await _token(api_client, "owner")
        category_id = await _category(api_client, owner)
        dish = await _dish(api_client, owner, ids, category_id)
        spice = await _group(api_client, owner, code="SPICE")
        addons = await _group(api_client, owner, code="ADDONS")

        attached = await api_client.put(
            f"{MENU}/items/{dish['id']}/modifier-groups",
            json={"modifier_group_ids": [spice, addons]},
            headers=_auth(owner),
        )
        assert attached.status_code == 200, attached.text
        assert attached.json()["modifier_group_ids"] == [spice, addons]

        # And on a plain read, which is where the editor gets it.
        body = (await api_client.get(f"{MENU}/items/{dish['id']}", headers=_auth(owner))).json()
        assert body["modifier_group_ids"] == [spice, addons]

    async def test_the_order_is_the_attachment_order_not_the_id_order(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`seq` is what the waiter's screen asks questions in. Sorting by id would shuffle it."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        owner = await _token(api_client, "owner")
        category_id = await _category(api_client, owner)
        dish = await _dish(api_client, owner, ids, category_id)
        spice = await _group(api_client, owner, code="SPICE")
        addons = await _group(api_client, owner, code="ADDONS")

        await api_client.put(
            f"{MENU}/items/{dish['id']}/modifier-groups",
            json={"modifier_group_ids": [addons, spice]},
            headers=_auth(owner),
        )

        body = (await api_client.get(f"{MENU}/items/{dish['id']}", headers=_auth(owner))).json()
        assert body["modifier_group_ids"] == [addons, spice]


# ------------------------------------------------------------------- 7 · the chef's own screen


class TestTheRecipeAChefIsAboutToEdit:
    """`StockService.current_recipe_for_variant` existed and no route reached it, so the editor
    had no way to load what it was editing — and M04 shipped without an editor at all."""

    async def test_a_dish_hands_back_its_current_recipe(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        owner = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, owner)
        category_id = await _category(api_client, owner)
        dish = await _dish(api_client, owner, ids, category_id)
        variant_id = dish["variants"][0]["id"]  # type: ignore[index]
        await api_client.post(
            f"{STAFF}/recipes",
            json={
                "menu_item_variant_id": variant_id,
                "lines": [{"component_id": item_id, "quantity": "200"}],
            },
            headers=_auth(owner),
        )

        response = await api_client.get(
            f"{STAFF}/menu-variants/{variant_id}/recipe", headers=_auth(owner)
        )

        assert response.status_code == 200, response.text
        assert response.json()["is_current"] is True
        assert response.json()["lines"] == [
            {"component_id": item_id, "quantity": "200.0000", "seq": 0}
        ]

    async def test_a_dish_with_no_recipe_says_so_rather_than_returning_an_empty_one(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """An empty recipe and no recipe are different things: the first costs zero and the second
        is uncosted. The dish-cost screen depends on never confusing them."""
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        owner = await _token(api_client, "owner")
        category_id = await _category(api_client, owner)
        dish = await _dish(api_client, owner, ids, category_id)

        response = await api_client.get(
            f"{STAFF}/menu-variants/{dish['variants'][0]['id']}/recipe",  # type: ignore[index]
            headers=_auth(owner),
        )

        assert response.status_code == 404, response.text
        assert response.json()["code"] == "recipe.not_found"

    async def test_another_tenants_variant_is_not_readable(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", slug="spice-garden")
        rival_world = await _world(db_session, "owner", slug="rival-kitchen")
        rival_ids = await _scaffold(db_session, rival_world.restaurant.id)
        rival = await _token(api_client, "owner", slug="rival-kitchen")
        rival_category = await _category(api_client, rival)
        rival_dish = await _dish(api_client, rival, rival_ids, rival_category)

        owner = await _token(api_client, "owner")
        response = await api_client.get(
            f"{STAFF}/menu-variants/{rival_dish['variants'][0]['id']}/recipe",  # type: ignore[index]
            headers=_auth(owner),
        )

        assert response.status_code == 404, response.text
