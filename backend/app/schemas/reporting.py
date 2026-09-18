"""The API contract for the dashboards and reports.

**Every money figure is a string, and every one of them carries its comparison.**
`docs/ui/conventions.md`: *"a number with no baseline is not information"*. A figure without its
`previous` is therefore not representable here — `Comparison` holds both, so a screen cannot render
one without the other by forgetting to fetch it.

**`change_percent` is nullable and that is deliberate.** `null` means *there is nothing to compare
against*, which is a different statement from zero. Zero would read as "unchanged", and a
restaurant's first Tuesday is not a Tuesday that did not move.

**No response here names an employee.** Variance belongs to a dish and a period; M17 is where
people are measured, and it has guardrails this module does not.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComparisonResponse(_Schema):
    """A figure and the same figure over the preceding period of equal length.

    Both are strings: money never becomes a float on the way to a browser (invariant 3), and a
    count is a string here too so a screen formats one thing one way.
    """

    value: str
    previous: str
    change: str
    # `null` when the previous period was zero — see the module docstring.
    change_percent: str | None


class SalesDayResponse(_Schema):
    business_date: date
    orders: int
    covers: int
    revenue: str
    tax: str
    discounts: str


class PaymentSplitResponse(_Schema):
    method: str
    amount: str
    count: int


class SalesReportResponse(_Schema):
    since: date
    until: date
    revenue: ComparisonResponse
    covers: ComparisonResponse
    average_bill: ComparisonResponse
    days: list[SalesDayResponse]
    payments: list[PaymentSplitResponse]


class VarianceLineResponse(_Schema):
    stock_item_id: uuid.UUID
    item_name: str
    base_unit: str
    theoretical_quantity: str
    actual_quantity: str
    # Actual minus theoretical, so positive means more was used than the recipes say — the
    # direction that costs money and the direction an owner is looking for.
    variance_quantity: str
    theoretical_value: str
    actual_value: str
    variance_value: str
    # The part of the gap somebody wrote a reason for.
    waste_value: str
    # And the part nobody did. This is the line the module exists to produce.
    unexplained_value: str


class VarianceReportResponse(_Schema):
    since: date
    until: date
    theoretical_total: str
    actual_total: str
    variance_total: str
    waste_total: str
    unexplained_total: str
    lines: list[VarianceLineResponse]


class DishLineResponse(_Schema):
    variant_id: uuid.UUID
    item_name: str
    variant_name: str
    units: int
    revenue: str
    theoretical_cost: str
    margin: str
    food_cost_percent: str | None
    average_rating: str | None
    average_prep_seconds: int | None
    # star | plough_horse | hidden_gem | dog, from vision doc §12.
    quadrant: str
    # A sentence, with the numbers beside it. The screen recommends; it never acts.
    advice: str


class DishReportResponse(_Schema):
    since: date
    until: date
    lines: list[DishLineResponse]


class TodayResponse(_Schema):
    business_date: date
    revenue: ComparisonResponse
    covers: ComparisonResponse
    open_orders: int
    average_rating: str | None
    # How many ratings the average is of. A 4.8 from two people is not a 4.8.
    ratings_counted: int
