"""M19 chunk A over HTTP: who may open it, and what a widened tenant filter must never return.

**What the tenant tests here do and do not prove**, because the difference was measured rather
than assumed. Deleting the organization filter inside `_real_restaurants` leaves every test in this
file green. They cannot see it: the API gives no way to name a restaurant id, so
`AnalyticsService.branch_ids` has already narrowed the set to the caller's own branches before that
filter is ever reached.

So these ask *"does the endpoint leak another tenant's trading"* — which is the question a client
can actually pose — and the second lock is tested where it can fail, at the repository, by
`test_m19_analytics.py::test_across_cannot_reach_another_organizations_branch`. That one **does**
go red when the filter is removed; it was checked, not assumed.

Both are worth having. `across` is a list a service builds, and the day somebody adds an endpoint
that takes branch ids from a request, the repository test is the one still standing.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_reports_endpoints import _trading
from tests.test_setup_endpoints import _auth, _token

ANALYTICS = "/api/v1/staff/analytics"


class TestWhoMayOpenIt:
    async def test_a_manager_cannot_open_the_analytics(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Same line as M13's money screens, and for the same reason.

        Every figure here is revenue, covers or spend per guest. The P1 design gives
        `report.financial.view` to the owner and the accountant and not to the manager, so these
        are screens a manager does not have rather than screens with blanks in them — a disabled
        figure invites somebody to find the endpoint.
        """
        await _trading(db_session, api_client, "owner", "manager")
        manager = await _token(api_client, "manager")

        for path in (f"{ANALYTICS}/trend", f"{ANALYTICS}/branches"):
            refused = await api_client.get(path, headers=_auth(manager))
            assert refused.status_code == 403, f"{path}: {refused.text}"

    async def test_the_accountant_reads_them(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _trading(db_session, api_client, "owner", "accountant")
        accountant = await _token(api_client, "accountant")

        for path in (f"{ANALYTICS}/trend", f"{ANALYTICS}/branches"):
            allowed = await api_client.get(path, headers=_auth(accountant))
            assert allowed.status_code == 200, f"{path}: {allowed.text}"


class TestTheTenantBoundary:
    async def test_the_trend_never_carries_another_organizations_trading(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Two organizations, each with bills. Neither may see a rupee of the other's.

        `across_branches=true` is the widened path — the one that did not exist before chunk A —
        so it is the one worth pointing at another tenant.
        """
        ours_world, _ = await _trading(db_session, api_client, "owner")
        ours = await _token(api_client, "owner")
        # A second tenant with its own trading, built by the same helper.
        theirs_world, _ = await _trading(db_session, api_client, "owner", slug="tandoor-house")

        mine = await api_client.get(f"{ANALYTICS}/trend?across_branches=true", headers=_auth(ours))

        assert mine.status_code == 200, mine.text
        body = mine.json()
        # **Non-vacuous.** A second tenant that was never created would make the assertion below
        # true for the wrong reason, which is the shape of green test that proves nothing.
        assert theirs_world.restaurant.id != ours_world.restaurant.id
        assert [uuid.UUID(each) for each in body["restaurant_ids"]] == [ours_world.restaurant.id]

    async def test_the_comparison_never_carries_another_organizations_branch(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        ours_world, _ = await _trading(db_session, api_client, "owner")
        ours = await _token(api_client, "owner")
        theirs_world, _ = await _trading(db_session, api_client, "owner", slug="tandoor-house")

        mine = await api_client.get(f"{ANALYTICS}/branches", headers=_auth(ours))

        assert mine.status_code == 200, mine.text
        rows = mine.json()["branches"]
        # Again non-vacuous: the other tenant exists and has trading of its own.
        assert theirs_world.restaurant.id != ours_world.restaurant.id
        assert [uuid.UUID(row["restaurant_id"]) for row in rows] == [ours_world.restaurant.id]
        # And the comparison is not empty, so "no branches at all" cannot pass this either.
        assert rows[0]["revenue"] != "0.00"


class TestTheShapeOfTheAnswer:
    async def test_no_response_carries_a_tax_total(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The owner's decision of 2026-09-19, asserted against the wire.

        Nothing tax-shaped sums across branches: two restaurants under one organization can hold
        different GSTINs and different schemes, so a summed tax figure has no legal referent. The
        schema has no field for one — this is the test that says so from outside.
        """
        await _trading(db_session, api_client, "owner")
        owner = await _token(api_client, "owner")

        for path in (f"{ANALYTICS}/trend", f"{ANALYTICS}/branches"):
            body = (await api_client.get(path, headers=_auth(owner))).text.lower()
            assert "tax" not in body, f"{path} mentions tax"
            assert "gst" not in body, f"{path} mentions gst"

    async def test_a_bucket_with_no_trading_is_null_rather_than_zero(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A day the restaurant was shut has no average bill. Zero would draw a line through the
        floor of the chart and read as a catastrophic day rather than a closed one."""
        await _trading(db_session, api_client, "owner")
        owner = await _token(api_client, "owner")

        body = (
            await api_client.get(f"{ANALYTICS}/trend?metric=average_bill", headers=_auth(owner))
        ).json()

        empty = [point for point in body["points"] if point["days_traded"] == 0]
        assert empty, "every day traded — this test would otherwise pass vacuously"
        assert all(point["value"] is None for point in empty)

    async def test_money_crosses_the_wire_as_a_string(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Invariant 3. A float here is a rounding rule nobody chose."""
        await _trading(db_session, api_client, "owner")
        owner = await _token(api_client, "owner")

        body = (await api_client.get(f"{ANALYTICS}/branches", headers=_auth(owner))).json()

        assert isinstance(body["total_revenue"], str)
        for branch in body["branches"]:
            assert isinstance(branch["revenue"], str)
            assert isinstance(branch["dine_in_revenue"], str)
