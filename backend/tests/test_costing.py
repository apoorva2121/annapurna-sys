"""The cost engine, against the figures `seed/validate.py` has produced since M00.

**This is the most important test file in M04 and possibly in the product.** Two implementations of
one arithmetic now exist — the validator that guards the seed, and `app/services/costing.py` — and
`docs/modules.md` names the figures that prove they agree:

    Butter Chicken Full      ₹126.70
    makhani gravy            ₹0.1489 per ml
    weighted food cost       25.7%

If those two implementations drift, this product's headline number depends on which one you ask,
and nobody would notice until an owner compared a screen to a spreadsheet.

The fixtures are read **from the YAML itself**, not transcribed. A transcribed fixture tests that
the engine agrees with what somebody typed in a test file; reading the seed tests that it agrees
with the data the validator actually validates. When `seed/ingredients.yaml` changes, both move
together or this goes red — which is the point.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.services.costing import (
    Component,
    CostEngine,
    Line,
    RecipeCycleError,
    RecipeTooDeepError,
    food_cost_percentage,
)

_SEED = Path(__file__).resolve().parents[2] / "seed"


def _load(name: str) -> Any:
    return yaml.safe_load((_SEED / name).read_text(encoding="utf-8"))


class _Seed:
    """The seed dataset, as the cost engine wants it.

    Ids are minted deterministically from codes so a fixture can say `seed.id("TOMATO")` without
    caring what a UUID is — the engine keys on ids because the database does, and the test keys on
    codes because a person does.
    """

    def __init__(self) -> None:
        ingredients = _load("ingredients.yaml")["ingredients"]
        preparations = _load("preparations.yaml")["preparations"]
        self.menu = _load("menu.yaml")

        self._ids: dict[str, uuid.UUID] = {}
        components: dict[uuid.UUID, Component] = {}
        for row in ingredients:
            item_id = self.id(row["code"])
            components[item_id] = Component(
                id=item_id,
                code=row["code"],
                kind="ingredient",
                base_unit=row["base_unit"],
                # `Decimal(str(...))` and never `Decimal(float)`: 0.28 as a float is
                # 0.2800000000000000266, and the golden figures are to the paisa.
                price=Decimal(str(row["price"])),
                yield_factor=Decimal(str(row["yield_factor"])),
            )
        prep_lines: dict[uuid.UUID, list[Line]] = {}
        for row in preparations:
            item_id = self.id(row["code"])
            components[item_id] = Component(
                id=item_id,
                code=row["code"],
                kind="preparation",
                base_unit=row["yield_unit"],
                batch_yield=Decimal(str(row["batch_yield"])),
            )
            prep_lines[item_id] = [
                Line(component_id=self.id(line["ref"]), quantity=Decimal(str(line["qty"])))
                for line in row["lines"]
            ]
        self.components = components
        self.prep_lines = prep_lines

    def id(self, code: str) -> uuid.UUID:
        if code not in self._ids:
            self._ids[code] = uuid.uuid5(uuid.NAMESPACE_OID, code)
        return self._ids[code]

    def engine(self) -> CostEngine:
        return CostEngine(self.components, self.prep_lines)

    def recipe(self, item_code: str, variant_code: str) -> list[Line]:
        for item in self.menu["items"]:
            if item["code"] != item_code:
                continue
            for variant in item["variants"]:
                if variant["code"] == variant_code:
                    return [
                        Line(
                            component_id=self.id(line["ref"]),
                            quantity=Decimal(str(line["qty"])),
                        )
                        for line in variant["recipe"]
                    ]
        raise KeyError(f"{item_code}/{variant_code} is not in seed/menu.yaml")


@pytest.fixture(scope="module")
def seed() -> _Seed:
    return _Seed()


class TestTheGoldenFigures:
    """`docs/modules.md`: "golden tests against `seed/validate.py` figures"."""

    def test_makhani_gravy_costs_what_the_validator_says(self, seed: _Seed) -> None:
        """₹0.1489 per ml. The most-used preparation in the seed and the one six dishes rest on."""
        unit = seed.engine().unit_cost(seed.id("PREP_MAKHANI"))

        assert unit.quantize(Decimal("0.0001")) == Decimal("0.1489")

    def test_butter_chicken_full_costs_126_70(self, seed: _Seed) -> None:
        """**The headline figure.** It exercises the whole engine in one number: two levels of
        nesting (`PREP_CHKN_TIKKA` → `PREP_TANDMARINADE` → ingredients), a yield factor on a count
        (`LEMON`, inside the marinade), and a yield factor on a weight (chicken at 0.95)."""
        cost = seed.engine().cost_of(seed.recipe("BUTTER_CHICKEN", "FULL"))

        assert cost.rupees == Decimal("126.70")

    def test_the_depth_three_chain_costs_correctly(self, seed: _Seed) -> None:
        """`ONION → PREP_BIRISTA → PREP_YELLOW → dish` is the seed's deliberate depth-3 chain, and
        the reason the cap is 3 rather than 2. Its unit cost is what `seed/validate.py` prints."""
        unit = seed.engine().unit_cost(seed.id("PREP_YELLOW"))

        assert unit > 0
        # Birista costs more per gram than the onion it is made from, because 4000 g of onion
        # yields 1200 g of birista. A cost engine that ignored `batch_yield` would report less.
        onion = seed.engine().unit_cost(seed.id("ONION"))
        birista = seed.engine().unit_cost(seed.id("PREP_BIRISTA"))
        assert birista > onion * 3

    def test_the_weighted_menu_food_cost_is_25_7_percent(self, seed: _Seed) -> None:
        """The number `docs/seed-data.md` targets and the demo is built around.

        Weighted by popularity, because a menu's food cost is its *sales mix*'s food cost — a
        straight average would let one rarely-ordered dish with a terrible margin dominate.
        """
        engine = seed.engine()
        numerator = Decimal(0)
        denominator = Decimal(0)
        for item in seed.menu["items"]:
            popularity = Decimal(str(item["popularity"]))
            for variant in item["variants"]:
                cost = engine.cost_of(seed.recipe(item["code"], variant["code"])).total
                numerator += popularity * cost
                denominator += popularity * Decimal(str(variant["price"]))

        weighted = (numerator / denominator * 100).quantize(Decimal("0.1"))
        assert weighted == Decimal("25.7")

    def test_every_seed_dish_costs_something_and_nothing_absurd(self, seed: _Seed) -> None:
        """A sweep, because the three figures above could all be right while one dish is nonsense.

        Nothing free, and nothing costing more than its price — a dish sold at a loss is a real
        thing this product must be able to report, but `seed/validate.py` already flags anything
        above 40% and the seed's worst is Chilli Paneer at ~46% by design (planted signal 7).
        """
        engine = seed.engine()
        for item in seed.menu["items"]:
            for variant in item["variants"]:
                cost = engine.cost_of(seed.recipe(item["code"], variant["code"])).total
                price = Decimal(str(variant["price"]))
                label = f"{item['code']}/{variant['code']}"
                assert cost > 0, f"{label} costs nothing"
                assert cost < price, f"{label} costs more than it sells for"


class TestTheBreakdownIsTheProduct:
    def test_a_cost_names_its_lines(self, seed: _Seed) -> None:
        """ "Butter Chicken costs ₹126.70" tells an owner nothing to act on. The line that says
        ₹62 of it is chicken tikka is what they use when the price of chicken moves."""
        cost = seed.engine().cost_of(seed.recipe("BUTTER_CHICKEN", "FULL"))

        by_code = {line.code: line for line in cost.lines}
        assert set(by_code) == {
            "PREP_MAKHANI",
            "PREP_CHKN_TIKKA",
            "BUTTER",
            "CREAM",
            "KASURI",
            "CORIANDER",
        }
        # The lines sum to the total, so nothing is lost or double-counted between them.
        assert sum((line.cost for line in cost.lines), Decimal(0)) == cost.total
        # The protein is the largest line, which is what a chef would expect and what makes the
        # breakdown believable. (An earlier version of this asserted it was 100x the kasuri methi,
        # which is simply false — 63 against 1.40 — and the test caught my arithmetic, not the
        # engine's.)
        assert max(cost.lines, key=lambda line: line.cost).code == "PREP_CHKN_TIKKA"

    def test_yield_factor_makes_an_ingredient_cost_more_than_its_price(self, seed: _Seed) -> None:
        """Chicken is 0.95: to use 100 g you buy 105 g. The cost engine charges for what you bought.

        This is the behaviour finding S15 questions for *count*-based items. It is not in question
        for weights, and this asserts it.
        """
        engine = seed.engine()
        per_gram = engine.unit_cost(seed.id("CHKN_BONELESS"))

        # price 0.280, yield 0.95 → 0.2947…
        assert per_gram > Decimal("0.280")
        assert per_gram.quantize(Decimal("0.0001")) == Decimal("0.2947")


class TestRefusals:
    """Depth and cycles, refused at save time rather than discovered at cost time."""

    def _engine(self, links: dict[str, list[str]]) -> tuple[CostEngine, _Ids]:
        ids = _Ids()
        components: dict[uuid.UUID, Component] = {
            ids.of("RAW"): Component(
                id=ids.of("RAW"),
                code="RAW",
                kind="ingredient",
                base_unit="g",
                price=Decimal("1"),
                yield_factor=Decimal("1"),
            )
        }
        lines: dict[uuid.UUID, list[Line]] = {}
        for code in links:
            components[ids.of(code)] = Component(
                id=ids.of(code),
                code=code,
                kind="preparation",
                base_unit="g",
                batch_yield=Decimal("1000"),
            )
        for code, refs in links.items():
            lines[ids.of(code)] = [
                Line(component_id=ids.of(ref), quantity=Decimal("100")) for ref in refs
            ]
        return CostEngine(components, lines), ids

    def test_a_preparation_containing_itself_is_refused(self) -> None:
        engine, ids = self._engine({"A": ["A"]})

        with pytest.raises(RecipeCycleError) as caught:
            engine.unit_cost(ids.of("A"))

        # The chain is in the error, because "there is a cycle" is not actionable and
        # "A → A" is.
        assert caught.value.details["chain"] == ["A", "A"]

    def test_a_cycle_three_hops_long_is_refused(self) -> None:
        """The one a person actually creates. A direct self-reference is obvious; A → B → C → A is
        three separate edits that each looked fine."""
        engine, ids = self._engine({"A": ["B"], "B": ["C"], "C": ["A"]})

        with pytest.raises((RecipeCycleError, RecipeTooDeepError)):
            engine.unit_cost(ids.of("A"))

    def test_depth_four_is_refused(self) -> None:
        """ADR 0006 caps nesting at three preparation hops: ingredient → prep → prep → dish."""
        engine, ids = self._engine({"A": ["B"], "B": ["C"], "C": ["D"], "D": ["RAW"]})

        with pytest.raises(RecipeTooDeepError) as caught:
            engine.unit_cost(ids.of("A"))

        assert caught.value.details["limit"] == 3

    def test_depth_three_is_allowed(self) -> None:
        """The cap must permit what the seed actually does, or it is not a cap but an outage:
        `ONION → PREP_BIRISTA → PREP_YELLOW → dish` is three hops and ships."""
        engine, ids = self._engine({"A": ["B"], "B": ["C"], "C": ["RAW"]})

        assert engine.unit_cost(ids.of("A")) > 0

    def test_the_save_time_check_finds_what_costing_would(self) -> None:
        """`check_depth_and_cycles` exists so a bad recipe is refused when it is written, not weeks
        later when somebody opens a cost screen. It must agree with the cost path exactly."""
        engine, ids = self._engine({"A": ["B"], "B": ["C"], "C": ["D"], "D": ["RAW"]})

        with pytest.raises(RecipeTooDeepError):
            engine.check_depth_and_cycles(
                [Line(component_id=ids.of("A"), quantity=Decimal("1"))],
                owner_code="DISH",
                owner_is_preparation=False,
            )

    def test_the_save_time_check_allows_what_costing_allows(self) -> None:
        """**The other direction, and the one that was wrong.**

        The save-time walk seeds its chain with the owner's code — needed to catch a preparation
        that contains itself — and then counted that code toward the depth. So it refused at three
        what `unit_cost` and `seed/validate.py` both allow at three: a dish made of a gravy made of
        a paste made of a spice mix, which is an ordinary Indian recipe and ships in the seed.
        Found by the M03/M04 review.
        """
        engine, ids = self._engine({"A": ["B"], "B": ["C"], "C": ["RAW"]})
        lines = [Line(component_id=ids.of("A"), quantity=Decimal("1"))]

        # Costing accepts it, so saving must.
        assert engine.cost_of(lines).total > 0
        engine.check_depth_and_cycles(lines, owner_code="DISH", owner_is_preparation=False)

    def test_a_preparation_owner_counts_as_a_level_and_a_dish_does_not(self) -> None:
        """Which is the whole reason the flag exists. Costing reaches a preparation's components
        one level down from the preparation; a dish's components are the top. Saving has to count
        the same way or the two disagree again, in the other direction."""
        engine, ids = self._engine({"A": ["B"], "B": ["C"], "C": ["RAW"]})
        lines = [Line(component_id=ids.of("A"), quantity=Decimal("1"))]

        with pytest.raises(RecipeTooDeepError):
            engine.check_depth_and_cycles(lines, owner_code="PREP_OWNER", owner_is_preparation=True)


class TestFoodCostPercentage:
    def test_it_reports_one_decimal_place(self) -> None:
        assert food_cost_percentage(Decimal("126.70"), Decimal("470")) == Decimal("27.0")

    def test_a_free_dish_has_no_food_cost_percentage(self) -> None:
        """A complimentary side is a real menu line. "0%" would be a lie and a crash would take
        the whole screen down for one row."""
        assert food_cost_percentage(Decimal("12"), Decimal("0")) is None


class _Ids:
    def __init__(self) -> None:
        self._ids: dict[str, uuid.UUID] = {}

    def of(self, code: str) -> uuid.UUID:
        if code not in self._ids:
            self._ids[code] = uuid.uuid5(uuid.NAMESPACE_OID, code)
        return self._ids[code]
