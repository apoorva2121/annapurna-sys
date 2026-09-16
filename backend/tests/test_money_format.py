"""Money in a sentence reads the way it does on an Indian bill (backlog-issues B12).

The payout refusal said "₹4000.00"; the owner asked for "₹4,000.00", with Indian grouping.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.money import format_inr


@pytest.mark.parametrize(
    ("amount", "shown"),
    [
        ("0", "₹0.00"),
        ("0.5", "₹0.50"),
        ("470", "₹470.00"),
        ("4000", "₹4,000.00"),
        ("12000.00", "₹12,000.00"),
        ("123456.5", "₹1,23,456.50"),
        ("10000000", "₹1,00,00,000.00"),
        ("-20", "-₹20.00"),
        ("493.505", "₹493.51"),
    ],
)
def test_indian_grouping(amount: str, shown: str) -> None:
    assert format_inr(Decimal(amount)) == shown
