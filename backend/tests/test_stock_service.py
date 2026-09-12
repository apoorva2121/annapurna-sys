"""Stock item and recipe paths the endpoint tests do not reach.

`test_stock_endpoints.py` covers the journey an owner takes; this covers the refusals and the
corners — the branches that only fire when somebody does something slightly wrong, which is most of
what a service is for.

They are worth having rather than worth hitting a coverage number: every one of these is a sentence
somebody will read at the moment they are confused, and an untested error message is an error
message nobody has read.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setup import Station
from app.models.stock import Recipe, StockItem
from tests.test_setup_endpoints import _auth, _token, _world

STAFF = "/api/v1/staff"


async def _station(session: AsyncSession, restaurant_id: uuid.UUID) -> uuid.UUID:
    station = Station(
        restaurant_id=restaurant_id, code="tandoor", name="Tandoor", seq=0, is_active=True
    )
    session.add(station)
    await session.flush()
    return station.id


async def _ingredient(
    client: AsyncClient, token: str, *, code: str = "PANEER", cost: str = "0.360000"
) -> str:
    response = await client.post(
        f"{STAFF}/stock-items",
        json={
            "kind": "ingredient",
            "code": code,
            "name": code.title(),
            "base_unit": "g",
            "category": "dairy",
            "storage_type": "chilled",
            "current_unit_cost": cost,
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


class TestCreatingAStockItem:
    async def test_an_ingredient_carries_its_profile_back(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        item_id = await _ingredient(api_client, token)

        body = (await api_client.get(f"{STAFF}/stock-items/{item_id}", headers=_auth(token))).json()
        assert body["ingredient"]["yield_factor"] == "0.9800"
        assert body["preparation"] is None
        # A string on the wire, never a float — this number multiplies into every dish's cost.
        assert isinstance(body["current_unit_cost"], str)

    async def test_a_preparation_needs_a_batch_yield_and_a_station(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner")
        station_id = await _station(db_session, world.restaurant.id)
        await db_session.commit()
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{STAFF}/stock-items",
            json={
                "kind": "preparation",
                "code": "PREP_MAKHANI",
                "name": "Makhani gravy",
                "base_unit": "ml",
                "preparation": {
                    "batch_yield": "8000",
                    "shelf_life_hours": 36,
                    "station_id": str(station_id),
                    "prep_minutes": 90,
                },
            },
            headers=_auth(token),
        )

        assert response.status_code == 201, response.text
        assert response.json()["preparation"]["shelf_life_hours"] == 36

    async def test_a_preparation_without_its_profile_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A preparation with no `batch_yield` has no unit cost, and inventing one would put a
        wrong number on every dish that uses it."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{STAFF}/stock-items",
            json={
                "kind": "preparation",
                "code": "PREP_X",
                "name": "Something",
                "base_unit": "ml",
            },
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "stock_item.profile_required"

    async def test_an_ingredient_given_a_preparation_profile_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner")
        station_id = await _station(db_session, world.restaurant.id)
        await db_session.commit()
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"{STAFF}/stock-items",
            json={
                "kind": "ingredient",
                "code": "CONFUSED",
                "name": "Confused",
                "base_unit": "g",
                "preparation": {
                    "batch_yield": "100",
                    "shelf_life_hours": 24,
                    "station_id": str(station_id),
                    "prep_minutes": 10,
                },
            },
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "stock_item.wrong_profile"

    async def test_a_code_cannot_be_reused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        await _ingredient(api_client, token)

        response = await api_client.post(
            f"{STAFF}/stock-items",
            json={
                "kind": "ingredient",
                "code": "PANEER",
                "name": "Paneer again",
                "base_unit": "g",
                "ingredient": {
                    "purchase_unit": "kg",
                    "purchase_to_base": "1000",
                    "shelf_life_days": 4,
                },
            },
            headers=_auth(token),
        )

        assert response.status_code == 409
        assert response.json()["code"] == "stock_item.code_taken"


class TestUpdatingAStockItem:
    async def test_a_price_change_writes_an_audit_row(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """It moves every dish that uses this and leaves no other trace (invariant 6)."""
        from app.models.audit import AuditLog

        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token, cost="0.360000")

        await api_client.patch(
            f"{STAFF}/stock-items/{item_id}",
            json={"current_unit_cost": "0.420000"},
            headers=_auth(token),
        )

        rows = (
            await db_session.scalars(
                select(AuditLog).where(AuditLog.action == "stock_item.repriced")
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].old_value == {"current_unit_cost": "0.360000"}
        assert rows[0].new_value == {"current_unit_cost": "0.420000"}

    async def test_renaming_does_not_write_an_audit_row(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A label correction is not a money event, and auditing everything is how an audit log
        becomes unreadable."""
        from app.models.audit import AuditLog

        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)

        await api_client.patch(
            f"{STAFF}/stock-items/{item_id}",
            json={"name": "Paneer (malai)"},
            headers=_auth(token),
        )

        rows = (
            await db_session.scalars(
                select(AuditLog).where(AuditLog.action == "stock_item.repriced")
            )
        ).all()
        assert rows == []

    async def test_the_profile_can_be_corrected(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`purchase_to_base` is an assumption the seeder makes — a gram-based ingredient bought by
        the kilo — and a restaurant buying paneer in 200 g packets corrects it here."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)

        response = await api_client.patch(
            f"{STAFF}/stock-items/{item_id}",
            json={
                "ingredient": {
                    "purchase_unit": "packet",
                    "purchase_to_base": "200",
                    "yield_factor": "1.0",
                    "shelf_life_days": 4,
                }
            },
            headers=_auth(token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["ingredient"]["purchase_unit"] == "packet"

    async def test_giving_an_ingredient_a_preparation_profile_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner")
        station_id = await _station(db_session, world.restaurant.id)
        await db_session.commit()
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)

        response = await api_client.patch(
            f"{STAFF}/stock-items/{item_id}",
            json={
                "preparation": {
                    "batch_yield": "100",
                    "shelf_life_hours": 24,
                    "station_id": str(station_id),
                    "prep_minutes": 10,
                }
            },
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "stock_item.wrong_profile"

    async def test_an_unknown_item_is_a_404(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.get(f"{STAFF}/stock-items/{uuid.uuid4()}", headers=_auth(token))

        assert response.status_code == 404


class TestRecipeRefusals:
    async def test_a_recipe_with_no_owner_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        item_id = await _ingredient(api_client, token)

        response = await api_client.post(
            f"{STAFF}/recipes",
            json={"lines": [{"component_id": item_id, "quantity": "100"}]},
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "recipe.owner_required"

    async def test_the_same_ingredient_twice_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`recipe_line`'s primary key is `(recipe_id, component_id)`, so a duplicate would be an
        IntegrityError and a 500. This is the sentence in front of it."""
        world = await _world(db_session, "owner")
        station_id = await _station(db_session, world.restaurant.id)
        await db_session.commit()
        token = await _token(api_client, "owner")
        paneer = await _ingredient(api_client, token)
        prep = await api_client.post(
            f"{STAFF}/stock-items",
            json={
                "kind": "preparation",
                "code": "PREP_X",
                "name": "Something",
                "base_unit": "g",
                "preparation": {
                    "batch_yield": "1000",
                    "shelf_life_hours": 24,
                    "station_id": str(station_id),
                    "prep_minutes": 10,
                },
            },
            headers=_auth(token),
        )

        response = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "produces_stock_item_id": prep.json()["id"],
                "lines": [
                    {"component_id": paneer, "quantity": "100"},
                    {"component_id": paneer, "quantity": "50"},
                ],
            },
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "recipe.duplicate_component"

    async def test_a_recipe_producing_an_ingredient_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Only a preparation is *made*. An ingredient is bought, and a recipe that claimed to
        produce one would give it two competing costs."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        paneer = await _ingredient(api_client, token)
        cream = await _ingredient(api_client, token, code="CREAM")

        response = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "produces_stock_item_id": paneer,
                "lines": [{"component_id": cream, "quantity": "100"}],
            },
            headers=_auth(token),
        )

        assert response.status_code == 422
        assert response.json()["code"] == "recipe.not_a_preparation"

    async def test_a_recipe_for_a_variant_that_does_not_exist_is_a_404(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        paneer = await _ingredient(api_client, token)

        response = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "menu_item_variant_id": str(uuid.uuid4()),
                "lines": [{"component_id": paneer, "quantity": "100"}],
            },
            headers=_auth(token),
        )

        assert response.status_code == 404

    async def test_an_unknown_recipe_is_a_404(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.get(f"{STAFF}/recipes/{uuid.uuid4()}", headers=_auth(token))

        assert response.status_code == 404


class TestConfirmation:
    async def test_confirming_marks_the_recipe_and_is_idempotent(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A chef saying "yes, this is what we actually make".

        Idempotent because the button will be pressed twice, and a second confirmation that moved
        the timestamp would quietly claim the chef checked it again today.
        """
        world = await _world(db_session, "owner")
        station_id = await _station(db_session, world.restaurant.id)
        await db_session.commit()
        token = await _token(api_client, "owner")
        paneer = await _ingredient(api_client, token)
        prep = await api_client.post(
            f"{STAFF}/stock-items",
            json={
                "kind": "preparation",
                "code": "PREP_X",
                "name": "Something",
                "base_unit": "g",
                "preparation": {
                    "batch_yield": "1000",
                    "shelf_life_hours": 24,
                    "station_id": str(station_id),
                    "prep_minutes": 10,
                },
            },
            headers=_auth(token),
        )
        recipe = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "produces_stock_item_id": prep.json()["id"],
                "lines": [{"component_id": paneer, "quantity": "100"}],
                "source": "library",
            },
            headers=_auth(token),
        )
        recipe_id = recipe.json()["id"]
        assert recipe.json()["confirmed_at"] is None, "a library recipe arrives unconfirmed"

        first = await api_client.post(f"{STAFF}/recipes/{recipe_id}/confirm", headers=_auth(token))
        second = await api_client.post(f"{STAFF}/recipes/{recipe_id}/confirm", headers=_auth(token))

        assert first.json()["confirmed_at"] is not None
        assert second.json()["confirmed_at"] == first.json()["confirmed_at"]

    async def test_a_preparations_unit_cost_is_per_base_unit_not_per_batch(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The number every consuming recipe multiplies by. Storing the batch total instead would
        overstate every dish using it by the size of a batch."""
        world = await _world(db_session, "owner")
        station_id = await _station(db_session, world.restaurant.id)
        await db_session.commit()
        token = await _token(api_client, "owner")
        # 1000 g of something costing ₹1/g, yielding a 500 g batch → ₹2 per gram of yield.
        paneer = await _ingredient(api_client, token, cost="1.000000")
        prep = await api_client.post(
            f"{STAFF}/stock-items",
            json={
                "kind": "preparation",
                "code": "PREP_X",
                "name": "Something",
                "base_unit": "g",
                "preparation": {
                    "batch_yield": "500",
                    "shelf_life_hours": 24,
                    "station_id": str(station_id),
                    "prep_minutes": 10,
                },
            },
            headers=_auth(token),
        )

        response = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "produces_stock_item_id": prep.json()["id"],
                "lines": [{"component_id": paneer, "quantity": "1000"}],
            },
            headers=_auth(token),
        )

        # 1000 g at 0.98 yield, at Rs 1/g, is Rs 1020.41 a batch. Over 500 g of yield
        # that is Rs 2.04 per gram — which is the number a consuming recipe multiplies by.
        unit_cost = Decimal(response.json()["unit_cost"])
        assert unit_cost.quantize(Decimal("0.01")) == Decimal("2.04"), unit_cost


class TestCostOfAnUncostedDish:
    async def test_a_dish_with_no_recipe_reports_no_recipe_rather_than_zero(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """ "₹0.00" reads as a dish that is free to make, which is the opposite of the truth: an
        uncosted dish is the one nobody can make a decision about."""
        from tests.test_menu_endpoints import _category, _dish, _scaffold

        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        await db_session.commit()
        token = await _token(api_client, "owner")
        category_id = await _category(api_client, token)
        item = await _dish(api_client, token, ids, category_id)
        variants = item["variants"]
        assert isinstance(variants, list)

        body = (
            await api_client.get(
                f"{STAFF}/menu-variants/{variants[0]['id']}/cost", headers=_auth(token)
            )
        ).json()

        assert body["has_recipe"] is False
        assert body["food_cost_percent"] is None
        assert body["lines"] == []


class TestRecipeVersionsAreVisible:
    async def test_the_stored_recipe_reports_its_source(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`library/PROVENANCE.md` says most of the starter library is `estimated`. A recipe that
        came from it must be distinguishable from one a chef wrote, or the cost screen states a
        number with confidence nobody has earned."""
        world = await _world(db_session, "owner")
        station_id = await _station(db_session, world.restaurant.id)
        await db_session.commit()
        token = await _token(api_client, "owner")
        paneer = await _ingredient(api_client, token)
        prep = await api_client.post(
            f"{STAFF}/stock-items",
            json={
                "kind": "preparation",
                "code": "PREP_X",
                "name": "Something",
                "base_unit": "g",
                "preparation": {
                    "batch_yield": "1000",
                    "shelf_life_hours": 24,
                    "station_id": str(station_id),
                    "prep_minutes": 10,
                },
            },
            headers=_auth(token),
        )

        created = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "produces_stock_item_id": prep.json()["id"],
                "lines": [{"component_id": paneer, "quantity": "100"}],
                "source": "library",
                "notes": "Matched from the starter library",
            },
            headers=_auth(token),
        )

        stored = (
            await api_client.get(f"{STAFF}/recipes/{created.json()['id']}", headers=_auth(token))
        ).json()
        assert stored["source"] == "library"
        assert stored["notes"] == "Matched from the starter library"
        assert stored["version"] == 1
        assert stored["is_current"] is True

    async def test_the_previous_version_is_still_readable(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """M07 will cite a version by id. Every version must resolve forever, which is why `recipe`
        is the one table here that is neither deactivated nor deleted."""
        world = await _world(db_session, "owner")
        station_id = await _station(db_session, world.restaurant.id)
        await db_session.commit()
        token = await _token(api_client, "owner")
        paneer = await _ingredient(api_client, token)
        prep = await api_client.post(
            f"{STAFF}/stock-items",
            json={
                "kind": "preparation",
                "code": "PREP_X",
                "name": "Something",
                "base_unit": "g",
                "preparation": {
                    "batch_yield": "1000",
                    "shelf_life_hours": 24,
                    "station_id": str(station_id),
                    "prep_minutes": 10,
                },
            },
            headers=_auth(token),
        )
        first = await api_client.post(
            f"{STAFF}/recipes",
            json={
                "produces_stock_item_id": prep.json()["id"],
                "lines": [{"component_id": paneer, "quantity": "100"}],
            },
            headers=_auth(token),
        )

        await api_client.post(
            f"{STAFF}/recipes",
            json={
                "produces_stock_item_id": prep.json()["id"],
                "lines": [{"component_id": paneer, "quantity": "200"}],
            },
            headers=_auth(token),
        )

        old = (
            await api_client.get(f"{STAFF}/recipes/{first.json()['id']}", headers=_auth(token))
        ).json()
        assert old["version"] == 1
        assert old["is_current"] is False
        assert old["lines"][0]["quantity"] == "100.0000"
        # Two versions, one current — the partial unique index, observed from outside.
        rows = (await db_session.scalars(select(Recipe).where(Recipe.is_current.is_(True)))).all()
        assert len(rows) == 1
        assert (
            await db_session.scalar(select(StockItem).where(StockItem.code == "PREP_X"))
        ) is not None
