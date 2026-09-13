"""GST arithmetic for a restaurant bill: pure functions, no database, no clock.

`docs/modules/M07-orders-spec.md` decisions 3 to 7 are the rules and this is their one
implementation. Every figure on a bill passes through here: the tax a waiter shows before payment,
the tax re-frozen at settlement, and a credit note's reversal. So the order service, the settlement
service and the credit-note service cannot each round a paisa differently.

Four rules carry the weight.

**1 · Tax is per line, and CGST and SGST are each computed on the line.** `cgst = round(v * r/2)`
and `sgst = round(v * r/2)`, so the halves are equal by construction. That is what the Jaipur bill
shows (₹142.20 each on ₹1,580 at 18%) and what migration 0019's CHECK requires. Computing a total
and halving it leaves an odd paisa that has to be given to one side.

**2 · A discount comes off before tax and reaches the lines by largest remainder.** CGST Act
s.15(3)(a) excludes a discount recorded on the invoice from taxable value. Tax is per line, so an
order-level discount has to be divided among the lines, and the shares must sum to it exactly.

**3 · The rate date is the median of served, invoiced and paid.** CGST Act s.14 puts a supply on
whichever side of a rate change two of those three events fall. For one boundary, "two of three
before" and "the median is before" are the same statement.

**4 · Rounding the payable total to the rupee is practice, not law** (R12: the 2015 bill rounded,
the 2025 bill did not). `price_bill` can do it; whether a restaurant does is the caller's decision.

Money is `Decimal`, to the paisa, rounded half-up. Division of a discount is done in whole paise, so
no share can drift through decimal precision.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from app.core.enums import DiscountType, DocumentType, GstScheme, TaxRegime

PAISA = Decimal("0.01")
ZERO = Decimal("0.00")
_RUPEE = Decimal("1")
_TWO = Decimal("2")
_PAISE_PER_RUPEE = 100

# CGST Rules, Rule 46(b): a serial number "not exceeding sixteen characters".
MAX_DOCUMENT_NUMBER_LENGTH = 16
_FINANCIAL_YEAR = re.compile(r"\d{4}-\d{2}")


def to_paisa(amount: Decimal) -> Decimal:
    """Round half-up to the paisa, the convention on Indian tax invoices."""
    return amount.quantize(PAISA, rounding=ROUND_HALF_UP)


def _paise(amount: Decimal, name: str) -> int:
    """`amount` as a whole number of paise, refusing anything finer rather than rounding it away."""
    if amount != to_paisa(amount):
        raise ValueError(f"{name} must be a whole number of paise, not {amount}.")
    return int(amount * _PAISE_PER_RUPEE)


def _rupees(paise: int) -> Decimal:
    return to_paisa(Decimal(paise) / _PAISE_PER_RUPEE)


# --------------------------------------------------------------------------- scheme


def collects_tax(scheme: GstScheme | str) -> bool:
    """Only a regular-scheme restaurant may put tax on a bill (CGST Act s.10; decision 3)."""
    return GstScheme(scheme) is GstScheme.REGULAR


def document_type_for(scheme: GstScheme | str) -> DocumentType:
    """A regular restaurant issues a tax invoice; every other restaurant a bill of supply.

    For a composition restaurant that is the law (Rule 49), under the heading Rule 5(1)(f) requires.
    An unregistered restaurant has no GSTIN to put on a tax invoice, so its bill is stored as a
    `bill_of_supply` row, which carries no tax and needs no GSTIN, and is printed without the
    composition heading.
    """
    return DocumentType.TAX_INVOICE if collects_tax(scheme) else DocumentType.BILL_OF_SUPPLY


# --------------------------------------------------------------------------- one line


@dataclass(frozen=True)
class LineTax:
    """One line's figures, exactly as `order_line` and `credit_note_line` store them."""

    taxable_value: Decimal
    cgst: Decimal
    sgst: Decimal
    tax: Decimal
    total: Decimal


def tax_line(
    amount: Decimal,
    rate: Decimal,
    regime: TaxRegime | str = TaxRegime.GST,
    *,
    inclusive: bool = False,
) -> LineTax:
    """The tax on one line, whose value after discount is `amount`.

    With an exclusive rate `amount` is the taxable value. With an inclusive one
    (`tax_rate.is_inclusive`, from M02) it is the price the customer pays, and tax is extracted as
    `amount * r / (1 + r)`, each half separately.

    A `non_gst` line (liquor, outside GST under Article 366(12A)) carries its state tax whole and is
    never split.
    """
    if _paise(amount, "A line's value") < 0:
        raise ValueError("A line's value cannot be negative.")
    if rate < 0 or rate > 1:
        raise ValueError(f"A tax rate is a fraction between 0 and 1, not {rate}.")

    if TaxRegime(regime) is TaxRegime.NON_GST:
        if inclusive:
            tax = to_paisa(amount * rate / (1 + rate))
            return LineTax(amount - tax, ZERO, ZERO, tax, amount)
        tax = to_paisa(amount * rate)
        return LineTax(amount, ZERO, ZERO, tax, amount + tax)

    if inclusive:
        half = to_paisa(amount * rate / _TWO / (1 + rate))
        taxable = amount - half - half
    else:
        half = to_paisa(amount * rate / _TWO)
        taxable = amount
    return LineTax(taxable, half, half, half + half, taxable + half + half)


# --------------------------------------------------------------------------- the rate date


def rate_date(served_at: datetime, invoiced_at: datetime, paid_at: datetime) -> datetime:
    """The instant whose rate a supply takes (CGST Act s.14): the median of the three events.

    Food served at 23:55, paid by UPI at 23:58 and billed at 00:02 on the night a rate changes has
    two events before the change, so it takes the old rate although the invoice is dated after.
    "Use the rate at settlement" gets that wrong. The caller turns the result into the restaurant's
    calendar date and looks up the rate effective on it.
    """
    moments = (served_at, invoiced_at, paid_at)
    if any(moment.tzinfo is None or moment.utcoffset() is None for moment in moments):
        raise ValueError("rate_date needs timezone-aware datetimes.")
    return sorted(moments)[1]


# --------------------------------------------------------------------------- discounts


def apportion(total: Decimal, weights: Sequence[Decimal]) -> list[Decimal]:
    """Divide `total` among `weights` pro rata, to the paisa, summing to `total` exactly.

    Largest remainder: every share starts at its pro-rata value rounded down, and the paise that
    rounding dropped go one each to the shares it cut most. Ties go to the earlier weight, so the
    same bill always divides the same way.

    No share exceeds its weight while `total` does not exceed their sum: a share gains a paisa only
    when rounding cut something from it, and a weight is a whole number of paise. That is what keeps
    migration 0019's `line_discount <= line_subtotal` true without a clamp.
    """
    total_paise = _paise(total, "The amount to divide")
    weight_paise = [_paise(weight, "A line value") for weight in weights]
    if total_paise < 0 or any(weight < 0 for weight in weight_paise):
        raise ValueError("Neither a discount nor a line value can be negative.")
    base = sum(weight_paise)
    if total_paise > base:
        raise ValueError(
            f"A discount of {total} cannot come off lines worth {_rupees(base)}: "
            "a discount cannot exceed what it is taken from."
        )
    if total_paise == 0:
        return [ZERO for _ in weights]

    shares = [total_paise * weight // base for weight in weight_paise]
    remainders = [total_paise * weight % base for weight in weight_paise]
    leftover = total_paise - sum(shares)
    for index in sorted(range(len(shares)), key=lambda i: (-remainders[i], i))[:leftover]:
        shares[index] += 1
    return [_rupees(share) for share in shares]


def discount_amount(
    kind: DiscountType | str,
    base: Decimal,
    *,
    rate: Decimal | None = None,
    flat_amount: Decimal | None = None,
) -> Decimal:
    """The rupees a discount takes off `base`, frozen onto `order_discount.amount`.

    A percentage or a comp is a `rate` of the base; a flat discount is its `flat_amount`, and is
    refused rather than clamped when it exceeds the base, because a ₹500 discount on a ₹300 bill is
    a mistake somebody should see, not a ₹300 discount somebody did not ask for.
    """
    if _paise(base, "A discount base") < 0:
        raise ValueError("A discount base cannot be negative.")
    if DiscountType(kind) is DiscountType.FLAT:
        if flat_amount is None or rate is not None:
            raise ValueError("A flat discount has an amount and no rate.")
        if _paise(flat_amount, "A flat discount") <= 0:
            raise ValueError("A flat discount must be more than zero.")
        if flat_amount > base:
            raise ValueError(
                f"A discount of {flat_amount} cannot come off {base}: "
                "a discount cannot exceed what it is taken from."
            )
        return flat_amount
    if rate is None or flat_amount is not None:
        raise ValueError("A percentage discount or a comp has a rate and no flat amount.")
    if rate <= 0 or rate > 1:
        raise ValueError(f"A discount rate is a fraction above 0 and at most 1, not {rate}.")
    return to_paisa(base * rate)


# --------------------------------------------------------------------------- the bill


@dataclass(frozen=True)
class LineInput:
    """What the bill needs to know about one line.

    `subtotal` is `(unit_price + modifier deltas) * quantity`; `line_discount` is the rupees already
    decided for discounts aimed at this line alone.
    """

    subtotal: Decimal
    rate: Decimal
    regime: TaxRegime | str = TaxRegime.GST
    inclusive: bool = False
    line_discount: Decimal = ZERO


@dataclass(frozen=True)
class ChargeInput:
    """Packaging, delivery or an optional service charge. `rate` is None when the restaurant has not
    put the charge under a tax group, which R17 leaves open for a service charge."""

    amount: Decimal
    rate: Decimal | None = None


@dataclass(frozen=True)
class PricedLine:
    discount: Decimal
    tax: LineTax


@dataclass(frozen=True)
class PricedCharge:
    amount: Decimal
    tax: LineTax


@dataclass(frozen=True)
class Bill:
    """Every figure `order` and `invoice` store, in the order they are computed."""

    lines: tuple[PricedLine, ...]
    charges: tuple[PricedCharge, ...]
    subtotal: Decimal
    discount_total: Decimal
    charge_total: Decimal
    taxable_total: Decimal
    cgst_total: Decimal
    sgst_total: Decimal
    non_gst_tax_total: Decimal
    tax_total: Decimal
    round_off: Decimal
    grand_total: Decimal


def rounded_to_rupee(amount: Decimal) -> tuple[Decimal, Decimal]:
    """`(payable, round_off)`: the amount to the nearest rupee, 50 paise up, and the difference."""
    payable = amount.quantize(_RUPEE, rounding=ROUND_HALF_UP).quantize(PAISA)
    return payable, payable - amount


def price_bill(
    lines: Sequence[LineInput],
    *,
    order_discount: Decimal = ZERO,
    charges: Sequence[ChargeInput] = (),
    collect_tax: bool = True,
    round_to_rupee: bool = False,
) -> Bill:
    """Price a whole bill: line discounts, the order discount shared out, tax per line, charges.

    `collect_tax=False` is a composition or unregistered restaurant (decision 3): every rate is
    treated as zero, whatever tax group the menu names, so such a bill cannot carry tax by accident.
    Charges are not discounted, and tips are not here at all: they sit outside taxable value.
    """
    remaining: list[Decimal] = []
    for line in lines:
        if _paise(line.subtotal, "A line subtotal") < 0:
            raise ValueError("A line subtotal cannot be negative.")
        if _paise(line.line_discount, "A line discount") < 0:
            raise ValueError("A line discount cannot be negative.")
        if line.line_discount > line.subtotal:
            raise ValueError("A line's own discount cannot exceed the line.")
        remaining.append(line.subtotal - line.line_discount)

    shares = apportion(order_discount, remaining)
    priced_lines = tuple(
        PricedLine(
            discount=line.line_discount + share,
            tax=tax_line(
                left - share,
                line.rate if collect_tax else ZERO,
                line.regime,
                inclusive=line.inclusive,
            ),
        )
        for line, left, share in zip(lines, remaining, shares, strict=True)
    )
    priced_charges = tuple(
        PricedCharge(
            amount=charge.amount,
            tax=tax_line(
                charge.amount,
                charge.rate if collect_tax and charge.rate is not None else ZERO,
            ),
        )
        for charge in charges
    )

    figures = [priced.tax for priced in priced_lines] + [priced.tax for priced in priced_charges]
    payable = sum((figure.total for figure in figures), ZERO)
    round_off = ZERO
    if round_to_rupee:
        payable, round_off = rounded_to_rupee(payable)

    return Bill(
        lines=priced_lines,
        charges=priced_charges,
        subtotal=sum((line.subtotal for line in lines), ZERO),
        discount_total=sum((priced.discount for priced in priced_lines), ZERO),
        charge_total=sum((charge.amount for charge in charges), ZERO),
        taxable_total=sum((figure.taxable_value for figure in figures), ZERO),
        cgst_total=sum((figure.cgst for figure in figures), ZERO),
        sgst_total=sum((figure.sgst for figure in figures), ZERO),
        non_gst_tax_total=sum(
            (
                priced.tax.tax
                for priced, line in zip(priced_lines, lines, strict=True)
                if TaxRegime(line.regime) is TaxRegime.NON_GST
            ),
            ZERO,
        ),
        tax_total=sum((figure.tax for figure in figures), ZERO),
        round_off=round_off,
        grand_total=payable,
    )


# --------------------------------------------------------------------------- document numbers


def _document_number(prefix: str, financial_year: str, sequence: int, width: int) -> str:
    if not _FINANCIAL_YEAR.fullmatch(financial_year):
        raise ValueError(f"A financial year looks like 2026-27, not {financial_year!r}.")
    if sequence < 1:
        raise ValueError("A document sequence starts at 1.")
    number = f"{prefix}{financial_year}/{sequence:0{width}d}"
    if len(number) > MAX_DOCUMENT_NUMBER_LENGTH:
        raise ValueError(
            f"{number} is longer than the sixteen characters CGST Rules, Rule 46(b) allows."
        )
    return number


def invoice_number(financial_year: str, sequence: int) -> str:
    """`2026-27/000123`: the year in the number, so a new year starts a new series with no lookup.

    Fourteen characters, and room for a hundred million bills a year before Rule 46(b)'s sixteen.
    """
    return _document_number("", financial_year, sequence, width=6)


def credit_note_number(financial_year: str, sequence: int) -> str:
    """`CN/2026-27/00001`: its own series (Rule 53), sixteen characters exactly.

    A restaurant issuing a hundred thousand credit notes in a year is refused rather than issued a
    seventeen-character number the law does not allow.
    """
    return _document_number("CN/", financial_year, sequence, width=5)
