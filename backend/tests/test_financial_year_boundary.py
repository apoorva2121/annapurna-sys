"""The night of 31 March, which is the only place invoice numbering can actually be wrong.

`docs/checklist.md` P5 asks for *"GST invoice numbering verified across a financial-year
boundary"*, and M16's security-checklist run found it had never been done. Not for want of tests:
`financial_year_of` is unit-tested against a table of dates, and `next_sequence` is tested for
gaplessness and for races. **Both were tested inside one year.**

That leaves the claim the law actually makes untested. CGST Rules, Rule 46(b) requires a
consecutive serial number *for a financial year*, so the assertion is not "numbers go up" — it is
**"numbers go up and then start again at exactly the right moment"**, and the moment is midnight
local time on 1 April, in the restaurant's timezone, on the calendar date rather than the business
date.

Three tests, and the third is the one worth having.

1. The last bill of a year and the first of the next carry the year in the number.
2. The new year's series starts at 1 rather than continuing March's run.
3. **A bill at 01:30 on 1 April belongs to business day 31 March and to the *new* year's series.**
   `app/services/settlement.py` says so in a comment; nothing asserted it. This is where a business
   date and a calendar date disagree, and using the wrong one puts a 1 April bill into a year that
   has already been filed.

The clock is pinned rather than the dates faked, because settlement reads `datetime.now(UTC)` and a
test that manipulated the rows afterwards would be testing the rows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orders import Invoice
from tests.test_orders_endpoints import Menu, _added, _open, _setup
from tests.test_settlement import _registered, _settle

# `_world` already builds the restaurant in Asia/Kolkata, which is the timezone this boundary
# is about: the Indian financial year begins at midnight IST, not at midnight UTC.
_KOLKATA = "Asia/Kolkata"

# 18:30 UTC is midnight in Kolkata. So:
#   31 Mar 12:00 UTC  -> 31 Mar 17:30 IST   — last evening of 2025-26
#   31 Mar 20:00 UTC  ->  1 Apr 01:30 IST   — business day 31 Mar, calendar date 1 Apr
#   1  Apr 12:00 UTC  ->  1 Apr 17:30 IST   — first evening of 2026-27
_LAST_EVENING = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
_AFTER_MIDNIGHT = datetime(2026, 3, 31, 20, 0, tzinfo=UTC)
_FIRST_EVENING = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)


def _pin(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    """A stand-in rather than a `datetime` subclass, following `test_setup_endpoints.py`:
    subclassing makes mypy demand that `now` return the subclass, and the module only ever calls
    `datetime.now(...)`.

    **Both services, not only settlement.** The order is opened by `app.services.orders`, which
    stamps `placed_at` from its own clock, and settlement refuses a payment received *before the
    order was placed*. Pinning one and not the other opens an order in September and settles it in
    March, which the product is right to refuse:

        settlement.payment_time — A payment cannot be received before the order was placed or
        after now.
    """

    class _Clock:
        @staticmethod
        def now(tz: object = None) -> datetime:  # noqa: ARG004
            return moment

    monkeypatch.setattr("app.services.settlement.datetime", _Clock)
    monkeypatch.setattr("app.services.orders.datetime", _Clock)


async def _bill(
    api_client: AsyncClient,
    token: str,
    menu: Menu,
    monkeypatch: pytest.MonkeyPatch,
    moment: datetime,
) -> dict[str, Any]:
    """One order, opened and settled at a pinned moment.

    Takeaway, so each bill is independent: settling sends a table to `cleaning`, and three bills
    over one table would be testing the floor plan rather than the numbering.
    """
    _pin(monkeypatch, moment)
    opened = await _open(api_client, token, menu, type="takeaway", table_ids=[])
    order = await _added(api_client, token, opened, menu.dal)
    response = await _settle(api_client, token, order)
    assert response.status_code == 201, response.text
    return dict(response.json())


class TestTheYearInTheNumber:
    async def test_the_last_bill_of_one_year_and_the_first_of_the_next(
        self,
        db_session: AsyncSession,
        api_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)

        march = await _bill(api_client, token, menu, monkeypatch, _LAST_EVENING)
        april = await _bill(api_client, token, menu, monkeypatch, _FIRST_EVENING)

        assert march["invoice_number"] == "2025-26/000001"
        assert april["invoice_number"] == "2026-27/000001"

    async def test_the_new_years_series_starts_at_one(
        self,
        db_session: AsyncSession,
        api_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The assertion Rule 46(b) actually makes. Two bills in March, then one in April: the
        April bill is sequence 1, not sequence 3.

        A sequence that carried over would look perfectly healthy in every existing test, because
        every existing test settles inside one year.
        """
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)

        await _bill(api_client, token, menu, monkeypatch, _LAST_EVENING)
        await _bill(api_client, token, menu, monkeypatch, _LAST_EVENING)
        april = await _bill(api_client, token, menu, monkeypatch, _FIRST_EVENING)

        rows = (
            await db_session.scalars(
                select(Invoice).order_by(Invoice.financial_year, Invoice.sequence)
            )
        ).all()
        assert [(row.financial_year, row.sequence) for row in rows] == [
            ("2025-26", 1),
            ("2025-26", 2),
            ("2026-27", 1),
        ]
        assert april["invoice_number"] == "2026-27/000001"


class TestTheNightTheTwoDatesDisagree:
    async def test_a_bill_at_half_past_one_is_the_new_years_first(
        self,
        db_session: AsyncSession,
        api_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """01:30 on 1 April: business day 31 March, calendar date 1 April.

        `app/services/settlement.py` states the rule in a comment — *"the financial year follows
        the calendar date of issue, not the business date"* — and invariant 4 makes the business
        date the one everything else uses. This is the single night where using the familiar one
        would file a bill into a year that has closed.
        """
        world, menu, token = await _setup(db_session, api_client)
        await _registered(db_session, world)

        await _bill(api_client, token, menu, monkeypatch, _LAST_EVENING)
        late = await _bill(api_client, token, menu, monkeypatch, _AFTER_MIDNIGHT)

        row = (
            await db_session.scalars(
                select(Invoice).where(Invoice.invoice_number == late["invoice_number"])
            )
        ).one()

        assert late["invoice_number"] == "2026-27/000001"
        assert row.financial_year == "2026-27"
        # And the other half of the same row, which is what makes this worth asserting together:
        # the takings still belong to the night of the 31st.
        assert str(row.business_date) == "2026-03-31"
        assert str(row.invoice_date) == "2026-04-01"
