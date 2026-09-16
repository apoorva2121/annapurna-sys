"""Purchase units at the boundary (backlog-issues B12e).

The ₹40-a-gram cabbage: a price typed per kilo against a form that meant per gram, and nothing
said anything. These tests pin the conversion and the sentence that now catches it.
"""

from decimal import Decimal

from app.services.purchase_units import to_base_units, unusual_price_problem


class TestToBaseUnits:
    def test_a_kilo_price_becomes_a_gram_price(self) -> None:
        quantity, price = to_base_units(Decimal("12"), Decimal("28.00"), Decimal("1000"))

        assert quantity == Decimal("12000.0000")
        assert price == Decimal("0.028000")

    def test_a_crate_of_thirty_becomes_thirty_units(self) -> None:
        quantity, price = to_base_units(Decimal("2"), Decimal("210"), Decimal("30"))

        assert quantity == Decimal("60.0000")
        assert price == Decimal("7.000000")

    def test_keeps_six_places_on_the_price_and_four_on_the_quantity(self) -> None:
        quantity, price = to_base_units(Decimal("1.5"), Decimal("100"), Decimal("3"))

        assert quantity == Decimal("4.5000")
        # 33.333333..., cut at the six places the ledger holds.
        assert price == Decimal("33.333333")

    def test_the_identity_factor_changes_nothing(self) -> None:
        assert to_base_units(Decimal("5"), Decimal("12.5"), Decimal("1")) == (
            Decimal("5.0000"),
            Decimal("12.500000"),
        )


class TestUnusualPrice:
    def test_the_forty_rupee_gram_of_cabbage_is_named(self) -> None:
        problem = unusual_price_problem(
            item_name="Cabbage",
            purchase_unit="kg",
            purchase_to_base=Decimal("1000"),
            base_price=Decimal("40"),
            current_unit_cost=Decimal("0.028"),
        )

        assert problem == (
            "Cabbage has been costing ₹28.00 per kg; this price works out at ₹40,000.00 per kg. "
            "Check the price and the unit."
        )

    def test_a_tenth_of_the_current_price_is_unusual_too(self) -> None:
        problem = unusual_price_problem(
            item_name="Paneer",
            purchase_unit="kg",
            purchase_to_base=Decimal("1000"),
            base_price=Decimal("0.03"),
            current_unit_cost=Decimal("0.41"),
        )

        assert problem is not None
        assert "₹410.00 per kg" in problem
        assert "₹30.00 per kg" in problem

    def test_a_season_price_rise_is_not_unusual(self) -> None:
        assert (
            unusual_price_problem(
                item_name="Tomato",
                purchase_unit="kg",
                purchase_to_base=Decimal("1000"),
                base_price=Decimal("0.09"),
                current_unit_cost=Decimal("0.03"),
            )
            is None
        )

    def test_exactly_ten_times_is_unusual(self) -> None:
        assert (
            unusual_price_problem(
                item_name="Tomato",
                purchase_unit="kg",
                purchase_to_base=Decimal("1000"),
                base_price=Decimal("0.30"),
                current_unit_cost=Decimal("0.03"),
            )
            is not None
        )

    def test_an_item_with_no_cost_yet_has_nothing_to_compare(self) -> None:
        for current in (None, Decimal("0")):
            assert (
                unusual_price_problem(
                    item_name="New",
                    purchase_unit="kg",
                    purchase_to_base=Decimal("1000"),
                    base_price=Decimal("40"),
                    current_unit_cost=current,
                )
                is None
            )
