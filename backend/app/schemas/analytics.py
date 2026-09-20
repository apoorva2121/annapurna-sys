"""M19's wire contract. Money crosses as a string, never a float (invariant 3).

**There is no tax field anywhere in this file, and that is the point.** The owner's decision of
2026-09-19 is that nothing tax-shaped sums across branches: two restaurants under one organization
can hold different GSTINs and even different schemes, so a summed tax figure has no legal referent.
Keeping the field out of the schema is what makes the forbidden total unrepresentable, rather than
a comment asking a client not to add two numbers up.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict

from app.services.analytics import Bucket, Metric


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SeriesPointResponse(_Schema):
    starts_on: date
    ends_on: date
    #: `None`, never `0`, when the bucket has nothing in it — a day the restaurant was shut has no
    #: average bill, and a zero would draw a line through the floor of the chart.
    value: str | None
    #: Business dates inside this bucket that issued an invoice. A week showing 2 of 7 is not a
    #: quiet week; it is a week the shop was shut, and the chart has to be able to say so.
    days_traded: int


class SeriesResponse(_Schema):
    metric: Metric
    bucket: Bucket
    since: date
    until: date
    #: Which branches the figures cover. Sent so a screen can say "three branches" without asking a
    #: second endpoint, and so a reader of a saved response knows what it was over.
    restaurant_ids: list[uuid.UUID]
    points: list[SeriesPointResponse]


class BranchRowResponse(_Schema):
    restaurant_id: uuid.UUID
    name: str
    revenue: str
    #: Dine-in only. `comparison_basis` divides by covers, and `order.covers` is NULL for takeaway
    #: and delivery — dividing *total* revenue by covers would charge a branch's whole delivery
    #: trade to the guests who sat down.
    dine_in_revenue: str
    covers: int
    orders: int
    #: Distinct business dates this branch issued an invoice on. Not the length of the window.
    business_days_traded: int
    revenue_per_trading_day: str | None
    #: Average spend per dine-in guest — the owner's chosen basis for comparing branches.
    #: `None` when nobody sat down, which is a different statement from zero.
    spend_per_cover: str | None


class BranchComparisonResponse(_Schema):
    since: date
    until: date
    branches: list[BranchRowResponse]
    #: The figures that may be summed, and only those.
    total_revenue: str
    total_covers: int
    total_orders: int
    average_bill: str | None
