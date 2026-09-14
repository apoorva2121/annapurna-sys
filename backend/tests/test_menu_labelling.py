"""What a menu must say about a dish, and the licence a bill prints (backlog-issues B8).

- `food_type` is the one enum with a statutory basis (`docs/compliance-rules.md` §A1) and lived in
  four places, none of them `app/core/enums.py`.
- Allergen information must appear on the menu, in text or clear symbols (§A2). The regulation's
  own list of allergens has not been verified from the instrument, so no list is written into code:
  a dish carries a statement in text, which §A2 accepts. NULL is "never asked".
- Calories and serving size (§B1) are representable, so a covered restaurant can declare them.
- The FSSAI licence number prints on every bill (§A3); its expiry date lets the screens warn.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from httpx import AsyncClient
from sqlalchemy import CheckConstraint, Table
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import FoodType
from app.models.menu import MenuItem
from app.services.menu_tree import guest_tree
from tests.test_menu_endpoints import MENU, _category, _scaffold
from tests.test_menu_tree_guest import _category as _guest_category
from tests.test_menu_tree_guest import _item
from tests.test_setup_endpoints import _auth, _token, _world

RESTAURANT = "/api/v1/staff/restaurant"


def _dish_body(category_id: str, ids: Mapping[str, object], **extra: object) -> dict[str, object]:
    return {
        "menu_category_id": category_id,
        "code": "DAL_MAKHANI",
        "name": "Dal Makhani",
        "food_type": "veg",
        "station_id": str(ids["station_id"]),
        "variants": [
            {
                "code": "FULL",
                "name": "Full",
                "price": "320.00",
                "tax_group_id": str(ids["tax_group_id"]),
                "prep_minutes": 12,
            }
        ],
    } | extra


class TestFoodTypeLivesInTheEnums:
    def test_the_enum_and_the_database_rule_name_the_same_three(self) -> None:
        constraint = next(
            c
            for c in cast(Table, MenuItem.__table__).constraints
            if isinstance(c, CheckConstraint) and c.name == "ck_menu_item_food_type"
        )
        listed = ", ".join(f"'{member.value}'" for member in FoodType)
        assert str(constraint.sqltext) == f"food_type IN ({listed})"


class TestADishSaysWhatIsInIt:
    async def test_allergens_calories_and_serving_size_are_kept(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category = await _category(api_client, token)

        response = await api_client.post(
            f"{MENU}/items",
            json=_dish_body(
                category,
                ids,
                allergen_statement="Milk, cashew",
                calories_kcal=480,
                serving_size="1 bowl (300 g)",
            ),
            headers=_auth(token),
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert (body["allergen_statement"], body["calories_kcal"], body["serving_size"]) == (
            "Milk, cashew",
            480,
            "1 bowl (300 g)",
        )

    async def test_a_dish_nobody_asked_about_says_so_rather_than_claiming_none(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category = await _category(api_client, token)

        response = await api_client.post(
            f"{MENU}/items", json=_dish_body(category, ids), headers=_auth(token)
        )

        assert response.status_code == 201, response.text
        assert response.json()["allergen_statement"] is None

    async def test_calories_cannot_be_negative(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner")
        ids = await _scaffold(db_session, world.restaurant.id)
        token = await _token(api_client, "owner")
        category = await _category(api_client, token)

        response = await api_client.post(
            f"{MENU}/items",
            json=_dish_body(category, ids, calories_kcal=-1),
            headers=_auth(token),
        )

        assert response.status_code == 422

    def test_a_guest_reads_them(self) -> None:
        item = _item()
        item.allergen_statement = "Milk, cashew"
        item.calories_kcal = 480
        item.serving_size = "1 bowl (300 g)"

        dish = guest_tree(1, [_guest_category(items=[item])]).categories[0].items[0]

        assert (dish.allergen_statement, dish.calories_kcal, dish.serving_size) == (
            "Milk, cashew",
            480,
            "1 bowl (300 g)",
        )


class TestTheLicenceExpiry:
    async def test_the_settings_keep_the_date_the_licence_is_valid_until(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        saved = await api_client.patch(
            RESTAURANT, json={"fssai_licence_expires_on": "2027-03-31"}, headers=_auth(token)
        )

        assert saved.status_code == 200, saved.text
        assert saved.json()["fssai_licence_expires_on"] == "2027-03-31"
