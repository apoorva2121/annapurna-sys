"""Stock items, recipes and cost, end to end.

**The test that matters is `test_butter_chicken_costs_126_70_through_the_api`.** `test_costing.py`
proves the arithmetic against the YAML; this proves the whole path — seeder, database, repository,
engine, endpoint — produces the same number. Those are different claims, and only the second one is
what an owner actually sees.

The rest is about the two rules a recipe table exists to keep: a version is never edited, and a
recipe cannot reach another tenant's ingredients.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.menu import MenuItem, MenuItemVariant
from app.models.stock import Recipe, StockItem
from app.seed.identity import seed_identity
from app.seed.menu import seed_menu
from app.seed.setup import seed_setup
from app.seed.stock import seed_stock
from tests.helpers.queries import count_queries
from tests.test_setup_endpoints import PASSWORD, _auth, _token, _world

STAFF = "/api/v1/staff"


async def _seed_token(client: AsyncClient, role: str) -> str:
    """Sign in as one of the *seeded* people.

    `_token` from the M02 suite builds `role@slug.test` for a world it created itself;
    `seed/organization.yaml` uses `role@spicegarden.test`. Two different worlds, two different
    identifier shapes, and conflating them produces a 401 that reads like a permission bug.
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={"identifier": f"{role}@spicegarden.test", "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


async def _seeded(session: AsyncSession) -> None:
    """The whole demo world: people, floor, menu, recipes."""
    await seed_identity(session)
    await seed_setup(session)
    await seed_menu(session)
    await seed_stock(session)
    await session.commit()


async def _variant_id(session: AsyncSession, item_code: str, variant_code: str) -> uuid.UUID:
    item = await session.scalar(select(MenuItem).where(MenuItem.code == item_code))
    assert item is not None
    variant = await session.scalar(
        select(MenuItemVariant).where(
            MenuItemVariant.menu_item_id == item.id, MenuItemVariant.code == variant_code
        )
    )
    assert variant is not None
    return variant.id


async def _item_id(session: AsyncSession, code: str) -> uuid.UUID:
    item = await session.scalar(select(StockItem).where(StockItem.code == code))
    assert item is not None
    return item.id


class TestTheGoldenFigureSurvivesTheWholeStack:
    async def test_butter_chicken_costs_126_70_through_the_api(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """**The claim this module is for.**

        `test_costing.py` asserts the engine agrees with `seed/validate.py` against the YAML. This
        asserts the *product* does: seeded into Postgres, read back through a repository, costed and
        serialised. A `numeric(14,6)` round trip, a `Decimal`-to-string boundary and a recursive
        walk over real rows all sit between the two, and any of them could lose a paisa.
        """
        await _seeded(db_session)
        token = await _seed_token(api_client, "owner")
        variant_id = await _variant_id(db_session, "BUTTER_CHICKEN", "FULL")

        response = await api_client.get(
            f"{STAFF}/menu-variants/{variant_id}/cost", headers=_auth(token)
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["cost"] == "126.70"
        assert body["price"] == "470.00"
        assert body["food_cost_percent"] == "27.0"
        assert body["has_recipe"] is True

    async def test_the_breakdown_names_where_the_money_went(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A total is not actionable. The line saying ₹63 of it is chicken tikka is."""
        await _seeded(db_session)
        token = await _seed_token(api_client, "owner")
        variant_id = await _variant_id(db_session, "BUTTER_CHICKEN", "FULL")

        body = (
            await api_client.get(f"{STAFF}/menu-variants/{variant_id}/cost", headers=_auth(token))
        ).json()

        by_code = {line["code"]: line for line in body["lines"]}
        assert "PREP_CHKN_TIKKA" in by_code
        assert "PREP_MAKHANI" in by_code
        # Every amount is a string on the wire. A float here is how ₹126.70 becomes ₹126.7000000001.
        assert all(isinstance(line["cost"], str) for line in body["lines"])

    async def test_the_menu_cost_screen_sorts_the_worst_dish_first(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The day-1 screen. An owner opening it is looking for the dish that is losing money, not
        reading an alphabetical list — and `seed/menu.yaml` plants Chilli Paneer at ~46% food cost
        for exactly this reason (planted signal 7)."""
        await _seeded(db_session)
        token = await _seed_token(api_client, "owner")

        body = (await api_client.get(f"{STAFF}/menu/costs", headers=_auth(token))).json()

        rows = body["rows"]
        assert len(rows) == 36, "every seeded variant should appear"
        assert body["uncosted"] == 0, "every seeded dish has a recipe"
        percentages = [Decimal(row["food_cost_percent"]) for row in rows]
        assert percentages == sorted(percentages, reverse=True)
        assert rows[0]["menu_item_name"] == "Chilli Paneer", rows[0]

    async def test_the_cost_screen_costs_the_same_queries_however_many_dishes(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The recursive walk is the N+1 risk in this module, and memoisation is the answer.

        Asserted as a *shape*: the seeded menu against a single dish. A budget would pass for both
        while still hiding a walk per dish.
        """
        await _seeded(db_session)
        token = await _seed_token(api_client, "owner")
        engine = db_session.get_bind().engine

        with count_queries(engine) as full:
            response = await api_client.get(f"{STAFF}/menu/costs", headers=_auth(token))
        assert response.status_code == 200

        # Deactivate all but one dish, so the sweep has one row to cost instead of thirty-six.
        items = (await db_session.scalars(select(MenuItem))).all()
        for item in items[1:]:
            item.is_active = False
        await db_session.commit()

        with count_queries(engine) as single:
            await api_client.get(f"{STAFF}/menu/costs", headers=_auth(token))

        assert full.count == single.count, (
            f"costing 36 dishes issued {full.count} queries and costing 1 issued "
            f"{single.count} — the cost is scaling with the menu"
        )


class TestWhatUsesThis:
    async def test_paneer_reaches_the_dishes_and_not_only_the_gravy(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The question an owner asks first when a price moves, and the reason
        `recipe_line.component_id` is indexed.

        Cashew is in makhani gravy, white gravy and several dishes directly. A single query over
        `recipe_line` finds the gravies and misses every dish made from them — the answer nobody
        wanted.
        """
        await _seeded(db_session)
        token = await _seed_token(api_client, "owner")
        cashew = await _item_id(db_session, "CASHEW")

        body = (
            await api_client.get(f"{STAFF}/stock-items/{cashew}/used-by", headers=_auth(token))
        ).json()

        assert "PREP_MAKHANI" in [prep["code"] for prep in body["preparations"]]
        # Butter Chicken contains no cashew directly — it is in the makhani gravy. Finding it here
        # is the whole point of walking rather than selecting.
        assert "Butter Chicken" in body["dish_names"]


class TestARecipeIsNeverEdited:
    async def test_a_change_creates_a_version_and_leaves_the_old_one_alone(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`order_line` (M07) cites the version live when the line was added. A version whose lines
        moved would restate what every past order cost."""
        await _seeded(db_session)
        token = await _seed_token(api_client, "owner")
        variant_id = await _variant_id(db_session, "JEERA_RICE", "FULL")
        original = await db_session.scalar(
            select(Recipe).where(
                Recipe.menu_item_variant_id == variant_id, Recipe.is_current.is_(True)
            )
        )
        assert original is not None
        original_cost = Decimal(str(original.unit_cost))
        ghee = await _item_id(db_session, "GHEE")

        response = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "menu_item_variant_id": str(variant_id),
                "lines": [{"component_id": str(ghee), "quantity": "40"}],
            },
            headers=_auth(token),
        )

        assert response.status_code == 201, response.text
        assert response.json()["version"] == 2
        await db_session.refresh(original)
        assert original.is_current is False
        # The frozen cost of version 1 is untouched — which is what M13 reads for a March order.
        assert Decimal(str(original.unit_cost)) == original_cost

    async def test_the_cost_endpoint_follows_the_current_version(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _seeded(db_session)
        token = await _seed_token(api_client, "owner")
        variant_id = await _variant_id(db_session, "JEERA_RICE", "FULL")
        before = (
            await api_client.get(f"{STAFF}/menu-variants/{variant_id}/cost", headers=_auth(token))
        ).json()["cost"]
        ghee = await _item_id(db_session, "GHEE")

        await api_client.post(
            f"{STAFF}/recipes",
            json={
                "menu_item_variant_id": str(variant_id),
                "lines": [{"component_id": str(ghee), "quantity": "400"}],
            },
            headers=_auth(token),
        )

        after = (
            await api_client.get(f"{STAFF}/menu-variants/{variant_id}/cost", headers=_auth(token))
        ).json()["cost"]
        assert Decimal(after) > Decimal(before)

    async def test_a_recipe_naming_two_owners_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A recipe owned by two things has no defined cost. The CHECK refuses it at the database;
        this is the readable refusal in front of it."""
        await _seeded(db_session)
        token = await _seed_token(api_client, "owner")
        variant_id = await _variant_id(db_session, "JEERA_RICE", "FULL")
        gravy = await _item_id(db_session, "PREP_MAKHANI")
        ghee = await _item_id(db_session, "GHEE")

        response = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "menu_item_variant_id": str(variant_id),
                "produces_stock_item_id": str(gravy),
                "lines": [{"component_id": str(ghee), "quantity": "10"}],
            },
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "recipe.owner_required"

    async def test_a_cycle_is_refused_at_save_time(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """ADR 0006, and the refusal names the chain — "there is a cycle" is not actionable."""
        await _seeded(db_session)
        token = await _seed_token(api_client, "owner")
        birista = await _item_id(db_session, "PREP_BIRISTA")
        yellow = await _item_id(db_session, "PREP_YELLOW")

        # Birista already feeds yellow gravy. Making birista consume yellow gravy closes the loop.
        response = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "produces_stock_item_id": str(birista),
                "lines": [{"component_id": str(yellow), "quantity": "100"}],
            },
            headers=_auth(token),
        )

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "recipe.cycle"
        assert "PREP_BIRISTA" in response.json()["details"]["chain"]

    async def test_a_recipe_cannot_reference_another_tenants_ingredient(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`recipe_line` has no `restaurant_id` — its parent carries one — so the repository base
        class cannot filter it and the generic isolation suite cannot probe it as a row. This is the
        test that holds the boundary, exactly as M03's modifier attachment has one."""
        await _seeded(db_session)
        token = await _seed_token(api_client, "owner")
        variant_id = await _variant_id(db_session, "JEERA_RICE", "FULL")
        rival = await _world(db_session, "owner", slug="rival-kitchen")
        rival_item = StockItem(
            restaurant_id=rival.restaurant.id,
            kind="ingredient",
            code="RIVAL_SAFFRON",
            name="Rival saffron",
            base_unit="g",
            current_unit_cost=Decimal("320"),
            is_active=True,
        )
        db_session.add(rival_item)
        await db_session.commit()

        response = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "menu_item_variant_id": str(variant_id),
                "lines": [{"component_id": str(rival_item.id), "quantity": "1"}],
            },
            headers=_auth(token),
        )

        assert response.status_code == 404, response.text
        assert response.json()["code"] == "stock_item.not_found"


class TestAChefSeesGramsNotRupees:
    async def test_a_chef_may_write_a_recipe(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _seeded(db_session)
        token = await _seed_token(api_client, "chef")
        variant_id = await _variant_id(db_session, "JEERA_RICE", "FULL")
        ghee = await _item_id(db_session, "GHEE")

        response = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "menu_item_variant_id": str(variant_id),
                "lines": [{"component_id": str(ghee), "quantity": "20"}],
            },
            headers=_auth(token),
        )

        assert response.status_code == 201, response.text

    async def test_a_chef_may_not_see_what_it_costs(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`seed/organization.yaml`, on the chef role: "NOT granted: any price, cost or financial
        permission. A chef sees grams, not rupees."

        The separation is deliberate in both directions — the chef writes the recipe and cannot see
        the margin; the manager sees the margin and cannot change the recipe.
        """
        await _seeded(db_session)
        token = await _seed_token(api_client, "chef")
        variant_id = await _variant_id(db_session, "BUTTER_CHICKEN", "FULL")

        cost = await api_client.get(
            f"{STAFF}/menu-variants/{variant_id}/cost", headers=_auth(token)
        )
        screen = await api_client.get(f"{STAFF}/menu/costs", headers=_auth(token))

        assert cost.status_code == 403
        assert screen.status_code == 403

    async def test_a_manager_may_see_the_cost_and_not_change_the_recipe(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _seeded(db_session)
        token = await _seed_token(api_client, "manager")
        variant_id = await _variant_id(db_session, "JEERA_RICE", "FULL")
        ghee = await _item_id(db_session, "GHEE")

        cost = await api_client.get(
            f"{STAFF}/menu-variants/{variant_id}/cost", headers=_auth(token)
        )
        write = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "menu_item_variant_id": str(variant_id),
                "lines": [{"component_id": str(ghee), "quantity": "20"}],
            },
            headers=_auth(token),
        )

        assert cost.status_code == 200
        assert write.status_code == 403


class TestStockItems:
    async def test_an_ingredient_without_a_profile_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A preparation with no `batch_yield` has no unit cost, and inventing one would put a wrong
        number on every dish that uses it."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{STAFF}/stock-items",
            json={
                "kind": "ingredient",
                "code": "NEW_THING",
                "name": "New thing",
                "base_unit": "g",
            },
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "stock_item.profile_required"

    async def test_the_seed_loads_every_ingredient_and_preparation(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _seeded(db_session)
        token = await _seed_token(api_client, "owner")

        ingredients = (
            await api_client.get(
                f"{STAFF}/stock-items?kind=ingredient&limit=100", headers=_auth(token)
            )
        ).json()
        preparations = (
            await api_client.get(
                f"{STAFF}/stock-items?kind=preparation&limit=100", headers=_auth(token)
            )
        ).json()

        assert len(ingredients["items"]) == 61
        assert len(preparations["items"]) == 11
        # Every preparation was costed by the freezing pass. A zero here means the pass ran before
        # the graph was complete — which is exactly what a per-row pass would have done.
        assert all(Decimal(row["current_unit_cost"]) > 0 for row in preparations["items"]), [
            row["code"] for row in preparations["items"] if Decimal(row["current_unit_cost"]) == 0
        ]

    async def test_seeding_twice_does_not_duplicate_anything(
        self, db_session: AsyncSession
    ) -> None:
        await _seeded(db_session)
        before = len((await db_session.scalars(select(StockItem))).all())

        second = await seed_stock(db_session)

        assert second.created_nothing
        assert len((await db_session.scalars(select(StockItem))).all()) == before
