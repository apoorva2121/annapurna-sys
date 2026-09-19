"""`make seed` must produce a restaurant somebody can order from.

`seed/menu.yaml` has held 32 dishes since M00 and been validated by `seed/validate.py` ever since,
with nothing loading it — there was no table until M03. M02's review round found the same shape of
gap in the floor plan and called the module "not demonstrable"; this is that lesson applied before
the review rather than after it.

The tests below are mostly about **joins that cross files**. `menu.yaml` names a station by code
and a tax rate by percentage; `operations.yaml` defines both, and attaches modifier groups by
*category*. Every one of those is a place where a rename in one file silently drops data in the
other, which is exactly why the codes exist.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import FoodType
from app.models.menu import (
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    MenuItemVariant,
    Modifier,
    ModifierGroup,
)
from app.models.setup import Station, TaxGroup
from app.models.tenancy import Restaurant
from app.seed.identity import seed_identity
from app.seed.menu import MissingSeedReferenceError, seed_menu
from app.seed.setup import seed_setup


async def _seed(session: AsyncSession) -> None:
    await seed_identity(session)
    await seed_setup(session)
    await seed_menu(session)
    await session.flush()


async def _koregaon(session: AsyncSession) -> Restaurant:
    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == "SG_KOREGAON"))
    assert restaurant is not None
    return restaurant


async def _count(session: AsyncSession, model: Any, restaurant_id: object) -> int:
    total = await session.scalar(
        select(func.count()).select_from(model).where(model.restaurant_id == restaurant_id)
    )
    return int(total or 0)


class TestTheMenuLoads:
    async def test_every_dish_in_the_yaml_is_seeded(self, db_session: AsyncSession) -> None:
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        assert await _count(db_session, MenuCategory, restaurant.id) == 6
        assert await _count(db_session, MenuItem, restaurant.id) == 32
        assert await _count(db_session, MenuItemVariant, restaurant.id) == 36

    async def test_a_price_is_a_decimal_and_not_a_float(self, db_session: AsyncSession) -> None:
        """CLAUDE.md invariant 3, asserted on the seeder's own object rather than on a column read.

        **Not through `select(MenuItemVariant.price)`.** `NUMERIC(12,2)` rounds on insert, so
        `Decimal(470.5)` — float error and all — comes back as exactly `470.50`. A column select
        passes against the very bug it was written to catch. Selecting the entity returns the
        seeder's own object from the identity map, never round-tripped. M02's review round found
        this exact defect in the tax-rate version of this test.
        """
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        variants = (
            await db_session.scalars(
                select(MenuItemVariant).where(MenuItemVariant.restaurant_id == restaurant.id)
            )
        ).all()

        assert variants
        for variant in variants:
            assert isinstance(variant.price, Decimal), (
                f"{variant.code} stored a {type(variant.price)}"
            )
            assert variant.price == variant.price.quantize(Decimal("0.01"))

    async def test_butter_chicken_is_priced_and_taxed_as_the_yaml_says(
        self, db_session: AsyncSession
    ) -> None:
        """One dish end to end, including both cross-file joins: `gst: 5` resolves to the `GST5`
        group and `station: main_kitchen` to that station."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        item = await db_session.scalar(
            select(MenuItem).where(
                MenuItem.restaurant_id == restaurant.id, MenuItem.code == "BUTTER_CHICKEN"
            )
        )
        assert item is not None
        station = await db_session.scalar(select(Station).where(Station.id == item.station_id))
        variants = {
            variant.code: variant
            for variant in await db_session.scalars(
                select(MenuItemVariant).where(MenuItemVariant.menu_item_id == item.id)
            )
        }
        tax = await db_session.scalar(
            select(TaxGroup).where(TaxGroup.id == variants["FULL"].tax_group_id)
        )

        assert item.food_type == "non_veg"
        assert station is not None and station.code == "main_kitchen"
        assert variants["FULL"].price == Decimal("470.00")
        assert variants["HALF"].price == Decimal("320.00")
        assert tax is not None and tax.code == "GST5"

    async def test_seeding_twice_does_not_duplicate_the_menu(
        self, db_session: AsyncSession
    ) -> None:
        """`make seed` is run casually and repeatedly. The failure to design against is not "it
        crashed" but "it silently made a second Butter Chicken"."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)
        before = await _count(db_session, MenuItem, restaurant.id)

        second = await seed_menu(db_session)
        await db_session.flush()

        assert second.created_nothing
        assert await _count(db_session, MenuItem, restaurant.id) == before


class TestModifiersAreAttachedByCategory:
    async def test_every_main_course_gets_a_spice_level(self, db_session: AsyncSession) -> None:
        """`operations.yaml` attaches by category — `{categories: [MAIN_VEG, MAIN_NONVEG],
        groups: [SPICE_LEVEL, ...]}` — and the table stores one row per dish. This is the
        expansion."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)
        mains = (
            await db_session.scalars(
                select(MenuItem)
                .join(MenuCategory, MenuCategory.id == MenuItem.menu_category_id)
                .where(
                    MenuItem.restaurant_id == restaurant.id,
                    MenuCategory.code.in_(["MAIN_VEG", "MAIN_NONVEG"]),
                )
            )
        ).all()
        spice = await db_session.scalar(
            select(ModifierGroup).where(
                ModifierGroup.restaurant_id == restaurant.id,
                ModifierGroup.code == "SPICE_LEVEL",
            )
        )

        assert mains, "the seed has no main courses to attach anything to"
        assert spice is not None
        for item in mains:
            attached = (
                await db_session.scalars(
                    select(MenuItemModifierGroup.modifier_group_id).where(
                        MenuItemModifierGroup.menu_item_id == item.id
                    )
                )
            ).all()
            assert spice.id in attached, f"{item.code} has no spice level"

    async def test_jain_is_offered_on_veg_dishes_and_never_on_a_non_veg_one(
        self, db_session: AsyncSession
    ) -> None:
        """Found by the owner on 2026-09-19: a chicken curry offered "Jain (no onion/garlic)".

        Jain dietary practice is vegetarian by definition, so the option cannot be satisfied on a
        non-veg dish under any preparation. Worse than useless: a Jain customer shown it on chicken
        learns the restaurant does not know what the word means.

        **Category could not express this rule** — `CHINESE` holds veg and non-veg dishes side by
        side — so the attachment is filtered on the dish's own `food_type`, the field with a
        statutory basis (`docs/compliance-rules.md` §A1) and therefore the one that is never empty.
        """
        await _seed(db_session)
        restaurant = await _koregaon(db_session)
        jain = await db_session.scalar(
            select(ModifierGroup).where(
                ModifierGroup.restaurant_id == restaurant.id,
                ModifierGroup.code == "JAIN_PREF",
            )
        )
        assert jain is not None

        items = (
            await db_session.scalars(
                select(MenuItem).where(MenuItem.restaurant_id == restaurant.id)
            )
        ).all()
        attached_to = set(
            (
                await db_session.scalars(
                    select(MenuItemModifierGroup.menu_item_id).where(
                        MenuItemModifierGroup.modifier_group_id == jain.id
                    )
                )
            ).all()
        )

        offered = [item for item in items if item.id in attached_to]
        assert offered, "nothing offers Jain at all — this test would otherwise pass vacuously"

        wrong = [item.code for item in offered if item.food_type != FoodType.VEG.value]
        assert not wrong, f"Jain is offered on non-vegetarian dishes: {wrong}"

        # And it is still offered where it belongs, so the fix is not "detach it from everything".
        veg = [item for item in items if item.food_type == FoodType.VEG.value]
        assert any(item.id in attached_to for item in veg), "no veg dish offers Jain any more"

    async def test_a_category_with_no_attachment_rule_gets_nothing(
        self, db_session: AsyncSession
    ) -> None:
        """The expansion must not be a blanket apply. `operations.yaml` attaches nothing to
        RICE_BREAD beyond BREAD_OPTS, so a rice dish must not acquire a spice level."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)
        spice = await db_session.scalar(
            select(ModifierGroup).where(
                ModifierGroup.restaurant_id == restaurant.id,
                ModifierGroup.code == "SPICE_LEVEL",
            )
        )
        naan = await db_session.scalar(
            select(MenuItem).where(
                MenuItem.restaurant_id == restaurant.id, MenuItem.code == "BUTTER_NAAN"
            )
        )

        assert naan is not None and spice is not None
        attached = (
            await db_session.scalars(
                select(MenuItemModifierGroup.modifier_group_id).where(
                    MenuItemModifierGroup.menu_item_id == naan.id
                )
            )
        ).all()
        assert spice.id not in attached

    async def test_every_modifier_gets_a_stable_code(self, db_session: AsyncSession) -> None:
        """`operations.yaml` gives modifiers a name and no code, because a person writing "Mild"
        does not think in codes. One is derived — `uq_modifier_group_code` needs it, and so will
        M07's order lines, which must name the option a guest chose after the label changes."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        modifiers = (
            await db_session.scalars(
                select(Modifier).where(Modifier.restaurant_id == restaurant.id)
            )
        ).all()

        assert modifiers
        codes = [modifier.code for modifier in modifiers]
        assert all(code and code == code.upper() for code in codes), codes
        by_group: dict[object, list[str]] = {}
        for modifier in modifiers:
            by_group.setdefault(modifier.modifier_group_id, []).append(modifier.code)
        for group_id, group_codes in by_group.items():
            assert len(group_codes) == len(set(group_codes)), (group_id, group_codes)


class TestTheSeedRefusesRatherThanGuesses:
    async def test_a_menu_without_stations_refuses(self, db_session: AsyncSession) -> None:
        """Seeding the menu before setup would otherwise mean every dish looking for a station that
        is not there. It refuses with the order to run things in, rather than failing later on a
        foreign key nobody can read."""
        await seed_identity(db_session)
        await db_session.flush()

        with pytest.raises(MissingSeedReferenceError, match="Seed setup first"):
            await seed_menu(db_session)

    async def test_a_dish_naming_an_unknown_tax_rate_refuses(
        self, db_session: AsyncSession
    ) -> None:
        """`gst: 12` with no GST12 group is a typo in the YAML, and the only honest answer is to
        stop. Guessing the nearest rate would put a wrong number on every bill for that dish."""
        await seed_identity(db_session)
        await seed_setup(db_session)
        await db_session.flush()
        menu = {
            "categories": [{"code": "MAIN_VEG", "name": "Veg Main Course", "seq": 1}],
            "items": [
                {
                    "code": "ODD",
                    "name": "Odd",
                    "category": "MAIN_VEG",
                    "food_type": "veg",
                    "station": "main_kitchen",
                    "variants": [
                        {"code": "FULL", "name": "Full", "price": 100, "gst": 12, "prep_minutes": 5}
                    ],
                }
            ],
        }

        with pytest.raises(MissingSeedReferenceError, match="GST12"):
            await seed_menu(db_session, menu=menu, operations={})

    async def test_attaching_an_unknown_modifier_group_refuses(
        self, db_session: AsyncSession
    ) -> None:
        """A typo in `operations.yaml` used to be filtered out silently, and the seed reported
        success. The demo restaurant then came up with dishes that had no options at all — a
        failure nobody notices until somebody tries to take an order. Found by the M03/M04 review.
        """
        await seed_identity(db_session)
        await seed_setup(db_session)
        await db_session.flush()
        menu = {
            "categories": [{"code": "MAIN_VEG", "name": "Veg Main Course", "seq": 1}],
            "items": [
                {
                    "code": "ODD",
                    "name": "Odd",
                    "category": "MAIN_VEG",
                    "food_type": "veg",
                    "station": "main_kitchen",
                    "variants": [
                        {"code": "FULL", "name": "Full", "price": 100, "gst": 5, "prep_minutes": 5}
                    ],
                }
            ],
        }
        operations = {
            "modifier_groups": [{"code": "SPICE_LEVEL", "name": "Spice level", "options": []}],
            "modifier_attachments": [
                {"categories": ["MAIN_VEG"], "groups": ["SPICE_LEVEL", "SPYCE_LEVEL"]}
            ],
        }

        with pytest.raises(MissingSeedReferenceError, match="SPYCE_LEVEL"):
            await seed_menu(db_session, menu=menu, operations=operations)

    async def test_attaching_to_an_unknown_category_refuses(self, db_session: AsyncSession) -> None:
        """The other half of the same silence: an unknown category matched no dishes, expanded to
        nothing, and looked exactly like a rule that had been applied."""
        await seed_identity(db_session)
        await seed_setup(db_session)
        await db_session.flush()
        menu = {
            "categories": [{"code": "MAIN_VEG", "name": "Veg Main Course", "seq": 1}],
            "items": [
                {
                    "code": "ODD",
                    "name": "Odd",
                    "category": "MAIN_VEG",
                    "food_type": "veg",
                    "station": "main_kitchen",
                    "variants": [
                        {"code": "FULL", "name": "Full", "price": 100, "gst": 5, "prep_minutes": 5}
                    ],
                }
            ],
        }
        operations = {
            "modifier_groups": [{"code": "SPICE_LEVEL", "name": "Spice level", "options": []}],
            "modifier_attachments": [{"categories": ["MAIN_NONVEG"], "groups": ["SPICE_LEVEL"]}],
        }

        with pytest.raises(MissingSeedReferenceError, match="MAIN_NONVEG"):
            await seed_menu(db_session, menu=menu, operations=operations)
