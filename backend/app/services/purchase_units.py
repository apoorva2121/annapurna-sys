"""Purchase units at the boundary (backlog-issues B12e).

A supplier sells cabbage by the kilo and the ledger holds it in grams (CLAUDE.md invariant 5). The
form asks for what is on the invoice - 12 kg at ₹28 a kilo - and this module is the one place that
turns it into base units, so no screen and no service does the arithmetic twice.

The second function is the sanity guard the owner's defect sheet asked for. The ₹40-a-gram cabbage
that made a plate of cabbage cost more than a car came from a price per unit typed against the
wrong unit, and nothing said anything: 40 was a plausible number, it was the unit that was wrong. A
price that is ten times the item's current cost - or a tenth of it - is not refused, because a
price really can move that far; it is put back to the person as a sentence, and they confirm.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.money import format_inr

_QUANTITY = Decimal("0.0001")
_UNIT_COST = Decimal("0.000001")

# Ten times or a tenth. Wide enough that a season's price rise never trips it, narrow enough that a
# kilo typed as a gram (a factor of a thousand) always does.
UNUSUAL_RATIO = Decimal("10")


def to_base_units(
    quantity: Decimal, price: Decimal, purchase_to_base: Decimal
) -> tuple[Decimal, Decimal]:
    """`quantity` purchase units at `price` per purchase unit, as base units and a base-unit price.

    Quantity is multiplied and quantised to the ledger's four places; price is divided and kept to
    six, which is what `stock_batch.unit_cost` and `stock_item.current_unit_cost` hold. Decimal all
    the way (invariant 3).
    """
    if purchase_to_base <= 0:
        raise ValueError("purchase_to_base must be positive")
    base_quantity = (quantity * purchase_to_base).quantize(_QUANTITY)
    base_price = (price / purchase_to_base).quantize(_UNIT_COST)
    return base_quantity, base_price


def unusual_price_problem(
    *,
    item_name: str,
    purchase_unit: str,
    purchase_to_base: Decimal,
    base_price: Decimal,
    current_unit_cost: Decimal | None,
) -> str | None:
    """The sentence to put back to the person when `base_price` is far from what the item costs
    now, or `None` when it is not. Both prices are said per purchase unit, because that is the unit
    the person typed in and the one on the supplier's invoice.

    Nothing to compare against - a new item with no cost yet, or a cost of zero - is not unusual.
    """
    if current_unit_cost is None or current_unit_cost <= 0:
        return None
    ratio = base_price / current_unit_cost
    if ratio < UNUSUAL_RATIO and ratio > 1 / UNUSUAL_RATIO:
        return None
    now = format_inr(current_unit_cost * purchase_to_base)
    typed = format_inr(base_price * purchase_to_base)
    return (
        f"{item_name} has been costing {now} per {purchase_unit}; this price works out at "
        f"{typed} per {purchase_unit}. Check the price and the unit."
    )
