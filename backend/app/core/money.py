"""Money in a sentence, the way an Indian bill writes it: `₹1,23,456.50` (backlog-issues B12).

For messages only. Amounts on the wire stay strings of plain digits, and screens format them with
`formatINR` (frontend/src/shared/money.ts); this is the same grouping for the few sentences the
server writes itself.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def format_inr(amount: Decimal) -> str:
    """Two decimals, half-up to the paisa, grouped in threes then twos, a minus before the ₹."""
    quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, _, paise = f"{abs(quantized):.2f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    sign = "-" if quantized < 0 else ""
    return f"{sign}₹{whole}.{paise}"
