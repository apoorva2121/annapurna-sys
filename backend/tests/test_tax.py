"""GST arithmetic, tested by ruling out families of inputs rather than confirming three examples.

A tax error on a bill is plausible rather than obviously broken. A paisa given to CGST and taken
from SGST prints perfectly well; it fails migration 0019's CHECK at settlement, mid-service, or
passes on a path nobody tested. So the golden cases are real bills and the spec's own examples,
and the properties are the invariants 0019 enforces, asserted over every price, quantity, rate
and discount hypothesis can construct.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.enums import DiscountType, DocumentType, GstScheme, TaxRegime
from app.core.tax import (
    PAISA,
    ZERO,
    ChargeInput,
    LineInput,
    apportion,
    collects_tax,
    credit_note_number,
    discount_amount,
    document_type_for,
    invoice_number,
    price_bill,
    rate_date,
    rounded_to_rupee,
    tax_line,
)

# The rates a restaurant bill actually carries (R1, R2), zero, and anything else between 0 and 1.
_KNOWN_RATES = [Decimal("0"), Decimal("0.05"), Decimal("0.12"), Decimal("0.18"), Decimal("0.28")]
rates = st.sampled_from(_KNOWN_RATES) | st.decimals(
    min_value=Decimal("0"), max_value=Decimal("1"), places=4
)
money = st.decimals(min_value=Decimal("0.00"), max_value=Decimal("99999.99"), places=2)


def _to_the_paisa(*figures: Decimal) -> bool:
    return all(figure == figure.quantize(PAISA) for figure in figures)


class TestTheBillsOnFile:
    """The owner's two real bills, and the spec's worked examples."""

    def test_the_jaipur_bill_reproduces(self) -> None:
        """Acceptance criterion 2: 19/04/2025, ₹1,580 at CGST 9% + SGST 9%, as printed."""
        line = tax_line(Decimal("1580.00"), Decimal("0.18"))

        assert (line.cgst, line.sgst) == (Decimal("142.20"), Decimal("142.20"))
        assert line.total == Decimal("1864.40")

    def test_the_jaipur_bill_was_not_rounded_and_need_not_be(self) -> None:
        """R12: rounding the payable to the rupee is practice, not law. Off unless asked for."""
        bill = price_bill([LineInput(subtotal=Decimal("1580.00"), rate=Decimal("0.18"))])

        assert bill.grand_total == Decimal("1864.40")
        assert bill.round_off == ZERO

    def test_an_odd_paisa_never_needs_a_home(self) -> None:
        """₹101 at 5% is ₹5.05 of tax, which halves to 2.525. Halving a total gives 2.53 and 2.52,
        which 0019 refuses. Computing each half on the line gives 2.53 twice: the bill carries a
        paisa more than the exact figure, and both halves agree."""
        line = tax_line(Decimal("101.00"), Decimal("0.05"))

        assert line.cgst == line.sgst == Decimal("2.53")
        assert line.tax == Decimal("5.06")


class TestOneLine:
    @given(amount=money, rate=rates, inclusive=st.booleans())
    def test_a_gst_line_splits_evenly_and_adds_up(
        self, amount: Decimal, rate: Decimal, inclusive: bool
    ) -> None:
        line = tax_line(amount, rate, inclusive=inclusive)

        assert line.cgst == line.sgst
        assert line.tax == line.cgst + line.sgst
        assert line.total == line.taxable_value + line.tax
        assert line.taxable_value >= 0
        assert _to_the_paisa(line.taxable_value, line.cgst, line.tax, line.total)
        if inclusive:
            assert line.total == amount
        else:
            assert line.taxable_value == amount

    @given(amount=money, rate=rates, inclusive=st.booleans())
    def test_a_non_gst_line_is_never_split(
        self, amount: Decimal, rate: Decimal, inclusive: bool
    ) -> None:
        line = tax_line(amount, rate, TaxRegime.NON_GST, inclusive=inclusive)

        assert line.cgst == line.sgst == ZERO
        assert line.total == line.taxable_value + line.tax
        assert line.taxable_value >= 0

    @given(amount=money, rate=rates)
    def test_inclusive_tax_is_within_a_paisa_of_the_exact_extraction(
        self, amount: Decimal, rate: Decimal
    ) -> None:
        line = tax_line(amount, rate, inclusive=True)

        assert abs(line.tax - amount * rate / (1 + rate)) <= PAISA

    @pytest.mark.parametrize("rate", [Decimal("-0.05"), Decimal("1.01")])
    def test_a_rate_outside_zero_to_one_is_refused(self, rate: Decimal) -> None:
        with pytest.raises(ValueError, match="fraction"):
            tax_line(Decimal("100.00"), rate)

    def test_a_fraction_of_a_paisa_is_refused_rather_than_rounded_away(self) -> None:
        with pytest.raises(ValueError, match="paise"):
            tax_line(Decimal("100.005"), Decimal("0.05"))

    def test_a_negative_value_is_refused(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            tax_line(Decimal("-1.00"), Decimal("0.05"))


class TestSection14:
    """Acceptance criterion 5. Midnight IST on 22 Sep 2025, the rate change the spec cites."""

    BOUNDARY = datetime(2025, 9, 21, 18, 30, tzinfo=UTC)

    @given(offsets=st.lists(st.integers(min_value=-600, max_value=600), min_size=3, max_size=3))
    def test_the_median_is_before_exactly_when_two_of_three_are(self, offsets: list[int]) -> None:
        """Every ordering and every side, including events exactly on the boundary, which belong
        to the new rate as a rate effective from midnight does."""
        served, invoiced, paid = (self.BOUNDARY + timedelta(minutes=m) for m in offsets)

        two_of_three_before = (
            sum(moment < self.BOUNDARY for moment in (served, invoiced, paid)) >= 2
        )
        assert (rate_date(served, invoiced, paid) < self.BOUNDARY) is two_of_three_before

    def test_the_spec_example_takes_the_old_rate(self) -> None:
        """Served 23:55, paid 23:58, billed 00:02: the invoice is dated after the change and the
        supply still takes the old rate. "Use the rate at settlement" gets this wrong."""
        served = self.BOUNDARY - timedelta(minutes=5)
        paid = self.BOUNDARY - timedelta(minutes=2)
        invoiced = self.BOUNDARY + timedelta(minutes=2)

        assert rate_date(served, invoiced, paid) < self.BOUNDARY

    def test_a_naive_datetime_is_refused(self) -> None:
        naive = datetime(2025, 9, 21, 23, 55)  # noqa: DTZ001 - naive on purpose
        with pytest.raises(ValueError, match="timezone-aware"):
            rate_date(naive, self.BOUNDARY, self.BOUNDARY)


class TestApportionment:
    """Acceptance criterion 12: a discount reaches the lines to the paisa."""

    @given(weights=st.lists(money, min_size=1, max_size=12), data=st.data())
    def test_shares_sum_exactly_and_never_exceed_their_line(
        self, weights: list[Decimal], data: st.DataObject
    ) -> None:
        base = sum(weights, ZERO)
        total = data.draw(st.decimals(min_value=Decimal("0"), max_value=base, places=2))

        shares = apportion(total, weights)

        assert sum(shares, ZERO) == total
        assert all(ZERO <= share <= weight for share, weight in zip(shares, weights, strict=True))
        if base > 0:
            assert all(
                abs(share - total * weight / base) < PAISA
                for share, weight in zip(shares, weights, strict=True)
            )

    def test_a_tie_goes_to_the_earlier_line_so_a_bill_always_divides_the_same_way(self) -> None:
        shares = apportion(Decimal("100.00"), [Decimal("300.00")] * 3)

        assert shares == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]

    def test_a_line_worth_nothing_takes_nothing(self) -> None:
        shares = apportion(Decimal("10.00"), [Decimal("0.00"), Decimal("40.00")])

        assert shares == [ZERO, Decimal("10.00")]

    def test_a_discount_larger_than_the_lines_is_refused(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed"):
            apportion(Decimal("100.01"), [Decimal("100.00")])

    def test_nothing_to_divide_divides_into_nothing(self) -> None:
        assert apportion(ZERO, []) == []


class TestDiscountAmounts:
    def test_a_percentage_rounds_half_up_to_the_paisa(self) -> None:
        assert discount_amount(
            DiscountType.PERCENTAGE, Decimal("333.35"), rate=Decimal("0.10")
        ) == Decimal("33.34")

    def test_a_full_comp_takes_everything(self) -> None:
        assert discount_amount(DiscountType.COMP, Decimal("940.00"), rate=Decimal("1")) == Decimal(
            "940.00"
        )

    def test_a_flat_discount_larger_than_the_bill_is_refused_not_clamped(self) -> None:
        """₹500 off a ₹300 bill is a mistake somebody should see, not a ₹300 discount nobody
        asked for."""
        with pytest.raises(ValueError, match="cannot exceed"):
            discount_amount(DiscountType.FLAT, Decimal("300.00"), flat_amount=Decimal("500.00"))

    @pytest.mark.parametrize(
        ("kind", "rate", "flat_amount"),
        [
            (DiscountType.FLAT, Decimal("0.10"), Decimal("50.00")),
            (DiscountType.FLAT, None, None),
            (DiscountType.PERCENTAGE, None, Decimal("50.00")),
            (DiscountType.PERCENTAGE, Decimal("0"), None),
            (DiscountType.COMP, Decimal("1.5"), None),
        ],
    )
    def test_a_discount_of_the_wrong_shape_is_refused(
        self, kind: DiscountType, rate: Decimal | None, flat_amount: Decimal | None
    ) -> None:
        with pytest.raises(ValueError):
            discount_amount(kind, Decimal("300.00"), rate=rate, flat_amount=flat_amount)


@st.composite
def _lines(draw: st.DrawFn) -> LineInput:
    subtotal = draw(money)
    return LineInput(
        subtotal=subtotal,
        rate=draw(rates),
        regime=draw(st.sampled_from(list(TaxRegime))),
        inclusive=draw(st.booleans()),
        line_discount=draw(st.decimals(min_value=Decimal("0"), max_value=subtotal, places=2)),
    )


_charges = st.builds(ChargeInput, amount=money, rate=st.none() | rates)


class TestTheWholeBill:
    """Acceptance criterion 1: the bill adds up exactly, whatever is on it."""

    @settings(max_examples=300)
    @given(
        lines=st.lists(_lines(), min_size=1, max_size=8),
        charges=st.lists(_charges, max_size=3),
        round_to_rupee=st.booleans(),
        data=st.data(),
    )
    def test_the_bill_adds_up_to_the_paisa(
        self,
        lines: list[LineInput],
        charges: list[ChargeInput],
        round_to_rupee: bool,
        data: st.DataObject,
    ) -> None:
        room = sum((line.subtotal - line.line_discount for line in lines), ZERO)
        order_discount = data.draw(st.decimals(min_value=Decimal("0"), max_value=room, places=2))

        bill = price_bill(
            lines, order_discount=order_discount, charges=charges, round_to_rupee=round_to_rupee
        )

        figures = [priced.tax for priced in bill.lines] + [priced.tax for priced in bill.charges]
        assert bill.grand_total == sum((figure.total for figure in figures), ZERO) + bill.round_off
        assert bill.grand_total == (
            bill.taxable_total
            + bill.cgst_total
            + bill.sgst_total
            + bill.non_gst_tax_total
            + bill.round_off
        )
        assert bill.tax_total == bill.cgst_total + bill.sgst_total + bill.non_gst_tax_total
        assert bill.discount_total == (
            sum((line.line_discount for line in lines), ZERO) + order_discount
        )
        assert bill.discount_total <= bill.subtotal
        assert all(priced.tax.cgst == priced.tax.sgst for priced in bill.lines)
        assert Decimal("-0.50") <= bill.round_off <= Decimal("0.50")
        if round_to_rupee:
            assert bill.grand_total == bill.grand_total.quantize(Decimal("1"))

    @given(lines=st.lists(_lines(), min_size=1, max_size=5), charges=st.lists(_charges, max_size=2))
    def test_a_restaurant_that_may_not_collect_tax_never_does(
        self, lines: list[LineInput], charges: list[ChargeInput]
    ) -> None:
        """Acceptance criterion 6, in the arithmetic: whatever tax group the menu names."""
        bill = price_bill(lines, charges=charges, collect_tax=False)

        assert bill.tax_total == ZERO
        assert bill.cgst_total == bill.sgst_total == ZERO

    def test_an_order_discount_comes_off_before_tax(self) -> None:
        """CGST Act s.15(3)(a): ₹1,000 of food, ₹100 off, 5% on the ₹900 that remains."""
        bill = price_bill(
            [LineInput(subtotal=Decimal("1000.00"), rate=Decimal("0.05"))],
            order_discount=Decimal("100.00"),
        )

        assert bill.taxable_total == Decimal("900.00")
        assert bill.tax_total == Decimal("45.00")
        assert bill.grand_total == Decimal("945.00")

    def test_an_untaxed_service_charge_carries_no_tax(self) -> None:
        bill = price_bill(
            [LineInput(subtotal=Decimal("1000.00"), rate=Decimal("0.05"))],
            charges=[ChargeInput(amount=Decimal("50.00"))],
        )

        assert bill.charges[0].tax.tax == ZERO
        assert bill.grand_total == Decimal("1100.00")

    def test_a_line_discount_larger_than_its_line_is_refused(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed the line"):
            price_bill(
                [
                    LineInput(
                        subtotal=Decimal("100.00"),
                        rate=Decimal("0.05"),
                        line_discount=Decimal("100.01"),
                    )
                ]
            )

    @pytest.mark.parametrize(
        ("amount", "payable", "round_off"),
        [
            (Decimal("1864.40"), Decimal("1864.00"), Decimal("-0.40")),
            (Decimal("1864.50"), Decimal("1865.00"), Decimal("0.50")),
            (Decimal("1864.49"), Decimal("1864.00"), Decimal("-0.49")),
            (Decimal("1864.00"), Decimal("1864.00"), Decimal("0.00")),
        ],
    )
    def test_rounding_to_the_rupee_takes_fifty_paise_up(
        self, amount: Decimal, payable: Decimal, round_off: Decimal
    ) -> None:
        """R12's convention for tax payable, applied only when a restaurant asks for it."""
        assert rounded_to_rupee(amount) == (payable, round_off)


class TestTheScheme:
    """Decision 3: only a regular restaurant collects tax, and it decides the document."""

    @pytest.mark.parametrize(
        ("scheme", "collects", "document"),
        [
            (GstScheme.REGULAR, True, DocumentType.TAX_INVOICE),
            (GstScheme.COMPOSITION, False, DocumentType.BILL_OF_SUPPLY),
            (GstScheme.UNREGISTERED, False, DocumentType.BILL_OF_SUPPLY),
        ],
    )
    def test_the_scheme_decides_tax_and_document(
        self, scheme: GstScheme, collects: bool, document: DocumentType
    ) -> None:
        assert collects_tax(scheme) is collects
        assert document_type_for(scheme) is document


class TestDocumentNumbers:
    """CGST Rules, Rule 46(b): consecutive, at most sixteen characters, unique per year."""

    def test_an_invoice_number_carries_its_year(self) -> None:
        assert invoice_number("2026-27", 123) == "2026-27/000123"

    def test_a_credit_note_has_its_own_series_and_fills_sixteen_characters(self) -> None:
        number = credit_note_number("2026-27", 1)

        assert number == "CN/2026-27/00001"
        assert len(number) == 16

    @given(sequence=st.integers(min_value=1, max_value=99_999_999))
    def test_every_invoice_number_a_year_can_reach_fits_the_rule(self, sequence: int) -> None:
        assert len(invoice_number("2026-27", sequence)) <= 16

    def test_a_number_the_rule_forbids_is_refused_rather_than_issued(self) -> None:
        with pytest.raises(ValueError, match="sixteen"):
            credit_note_number("2026-27", 100_000)

    @pytest.mark.parametrize(("year", "sequence"), [("2026-2027", 1), ("FY27", 1), ("2026-27", 0)])
    def test_a_malformed_year_or_sequence_is_refused(self, year: str, sequence: int) -> None:
        with pytest.raises(ValueError):
            invoice_number(year, sequence)
