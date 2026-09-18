"""The reports over HTTP: who may open them, and whether the CSV tells the same story.

`test_reporting.py` proves the arithmetic against data built to break it. `test_generic_suites.py`
proves every route here is tenant-isolated and declares a permission. What is left, and what this
file is:

**A manager cannot open the money.** The P1 design gives `report.financial.view` to the owner and
the accountant and to neither the manager nor the store manager, and the route *refuses* rather
than returning a screen with blanks in it. A redacted figure invites somebody to go looking for the
endpoint; a 403 does not.

**The CSV and the screen agree, row for row.** This is the test the module would be worst without:
a CSV that disagrees with the screen is the worst defect a report can have, because both look
authoritative and nobody can tell which is lying.

**Every figure carries its baseline.** Asserted on the wire, not in the service — a screen reads
what the API sends, and a comparison the API omitted is a comparison the screen invents.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_reporting import _DAY, World, _sold, _variant
from tests.test_setup_endpoints import _auth, _token
from tests.test_setup_endpoints import _world as _identity_world

STAFF = "/api/v1/staff"
REPORTS = f"{STAFF}/reports"


async def _trading(session: AsyncSession, client: AsyncClient, *roles: str) -> tuple[World, str]:
    """A restaurant with people who can sign in, and one day's trading in it.

    `_identity_world` makes the organization, the restaurant and the logins; `test_reporting`'s
    helpers put bills in it. Two fixtures rather than one because the identity world is what every
    other endpoint test uses, and a second way of making a restaurant would be a second thing to
    keep in step.
    """
    identity = await _identity_world(session, *roles)
    world = World(
        identity.organization,
        identity.restaurant,
        __import__("app.core.tenancy", fromlist=["TenantScope"]).TenantScope(
            organization_id=identity.organization.id, restaurant_id=identity.restaurant.id
        ),
    )
    variant = await _variant(session, world, dish="Dal Makhani", price="470")
    await _sold(session, world, variant, quantity=2, unit_price="470", unit_cost="100")
    await session.commit()
    return world, await _token(client, roles[0])


class TestWhoMayOpenWhat:
    async def test_a_manager_cannot_open_the_money(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The P1 design's line, and the reason these are not manager screens with blanks."""
        await _trading(db_session, api_client, "owner", "manager")
        manager = await _token(api_client, "manager")

        for path in (f"{REPORTS}/sales", f"{REPORTS}/food-cost-variance"):
            refused = await api_client.get(path, headers=_auth(manager))
            assert refused.status_code == 403, f"{path}: {refused.text}"

    async def test_a_manager_can_open_the_operations(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _trading(db_session, api_client, "owner", "manager")
        manager = await _token(api_client, "manager")

        for path in (
            f"{REPORTS}/dish-performance",
            f"{REPORTS}/waste",
            f"{STAFF}/dashboard/today",
        ):
            allowed = await api_client.get(path, headers=_auth(manager))
            assert allowed.status_code == 200, f"{path}: {allowed.text}"

    async def test_the_accountant_reads_the_money(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The design gives the accountant the books and withholds them from the manager. This is
        the half of that rule that is easy to forget to build."""
        await _trading(db_session, api_client, "owner", "accountant")
        accountant = await _token(api_client, "accountant")

        allowed = await api_client.get(f"{REPORTS}/sales", headers=_auth(accountant))
        assert allowed.status_code == 200, allowed.text

    async def test_the_accountant_reads_the_waste_the_chefs_screen_withholds(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """**Why a second waste route exists at all.** M09's `/wastage/summary` sits behind
        `stock.view`, which the P1 design does not give an accountant; this one sits behind
        `report.operational.view`, which it does. Collapsing the two would take the report away
        from somebody, and this is the half of that argument a test can hold."""
        await _trading(db_session, api_client, "owner", "accountant")
        accountant = await _token(api_client, "accountant")

        allowed = await api_client.get(f"{REPORTS}/waste", headers=_auth(accountant))
        assert allowed.status_code == 200, allowed.text

        refused = await api_client.get(f"{STAFF}/wastage/summary", headers=_auth(accountant))
        assert refused.status_code == 403, refused.text

    async def test_a_waiter_reads_no_report_at_all(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _trading(db_session, api_client, "owner", "waiter")
        waiter = await _token(api_client, "waiter")

        for path in (
            f"{REPORTS}/sales",
            f"{REPORTS}/food-cost-variance",
            f"{REPORTS}/dish-performance",
            f"{REPORTS}/waste",
            f"{STAFF}/dashboard/today",
        ):
            refused = await api_client.get(path, headers=_auth(waiter))
            assert refused.status_code == 403, f"{path}: {refused.text}"


class TestTheNumbersOnTheWire:
    async def test_every_figure_carries_its_baseline(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A number with no baseline is not information (`docs/ui/conventions.md`), and the
        comparison comes from the server so two screens cannot compute it differently."""
        _, owner = await _trading(db_session, api_client, "owner")

        response = await api_client.get(
            f"{REPORTS}/sales?since={_DAY}&until={_DAY}", headers=_auth(owner)
        )
        assert response.status_code == 200, response.text
        body = response.json()

        for figure in ("revenue", "covers", "average_bill"):
            assert set(body[figure]) == {"value", "previous", "change", "change_percent"}

    async def test_money_crosses_the_wire_as_a_string(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Invariant 3. A float here is a float in front of money, and JSON has only floats."""
        _, owner = await _trading(db_session, api_client, "owner")

        body = (
            await api_client.get(f"{REPORTS}/sales?since={_DAY}&until={_DAY}", headers=_auth(owner))
        ).json()

        assert isinstance(body["revenue"]["value"], str)
        assert body["revenue"]["value"] == "940.00"
        assert isinstance(body["days"][0]["revenue"], str)

    async def test_nothing_to_compare_against_is_null_and_not_zero(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, owner = await _trading(db_session, api_client, "owner")

        body = (
            await api_client.get(f"{REPORTS}/sales?since={_DAY}&until={_DAY}", headers=_auth(owner))
        ).json()

        assert body["revenue"]["change_percent"] is None

    async def test_the_dashboard_answers_for_the_restaurants_own_day(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Not the server's date: a restaurant's day starts at 05:00, and a dashboard asked for at
        2am is asking about the day that is still running."""
        _, owner = await _trading(db_session, api_client, "owner")

        body = (await api_client.get(f"{STAFF}/dashboard/today", headers=_auth(owner))).json()

        assert date.fromisoformat(body["business_date"])
        assert set(body["revenue"]) == {"value", "previous", "change", "change_percent"}


class TestTheCsvTellsTheSameStory:
    async def test_the_sales_csv_matches_the_screen_row_for_row(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """**The test this module would be worst without.** Two authoritative-looking answers that
        disagree teach somebody to trust neither."""
        _, owner = await _trading(db_session, api_client, "owner")
        window = f"since={_DAY}&until={_DAY}"

        screen = (await api_client.get(f"{REPORTS}/sales?{window}", headers=_auth(owner))).json()
        exported = await api_client.get(
            f"{REPORTS}/sales?{window}&format=csv", headers=_auth(owner)
        )
        assert exported.status_code == 200, exported.text
        assert exported.headers["content-type"].startswith("text/csv")
        assert "attachment" in exported.headers["content-disposition"]

        rows = list(csv.DictReader(io.StringIO(exported.text)))
        assert len(rows) == len(screen["days"])
        for row, day in zip(rows, screen["days"], strict=True):
            assert row["business_date"] == day["business_date"]
            assert row["revenue"] == day["revenue"]
            assert int(row["covers"]) == day["covers"]
            assert int(row["orders"]) == day["orders"]

    async def test_the_variance_csv_matches_the_screen_row_for_row(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, owner = await _trading(db_session, api_client, "owner")
        window = f"since={_DAY}&until={_DAY}"

        screen = (
            await api_client.get(f"{REPORTS}/food-cost-variance?{window}", headers=_auth(owner))
        ).json()
        exported = await api_client.get(
            f"{REPORTS}/food-cost-variance?{window}&format=csv", headers=_auth(owner)
        )

        rows = list(csv.DictReader(io.StringIO(exported.text)))
        assert len(rows) == len(screen["lines"])
        for row, line in zip(rows, screen["lines"], strict=True):
            assert row["item"] == line["item_name"]
            assert row["unexplained_value"] == line["unexplained_value"]

    async def test_the_dish_csv_matches_the_screen_row_for_row(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, owner = await _trading(db_session, api_client, "owner")
        window = f"since={_DAY}&until={_DAY}"

        screen = (
            await api_client.get(f"{REPORTS}/dish-performance?{window}", headers=_auth(owner))
        ).json()
        exported = await api_client.get(
            f"{REPORTS}/dish-performance?{window}&format=csv", headers=_auth(owner)
        )

        rows = list(csv.DictReader(io.StringIO(exported.text)))
        assert len(rows) == len(screen["lines"])
        for row, line in zip(rows, screen["lines"], strict=True):
            assert row["dish"] == line["item_name"]
            assert row["revenue"] == line["revenue"]
            assert row["quadrant"] == line["quadrant"]

    async def test_the_waste_csv_matches_the_screen_row_for_row(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        _, owner = await _trading(db_session, api_client, "owner")
        window = f"since={_DAY}&until={_DAY}"

        screen = (await api_client.get(f"{REPORTS}/waste?{window}", headers=_auth(owner))).json()
        exported = await api_client.get(
            f"{REPORTS}/waste?{window}&format=csv", headers=_auth(owner)
        )

        rows = list(csv.DictReader(io.StringIO(exported.text)))
        assert len(rows) == len(screen["lines"])
        for row, line in zip(rows, screen["lines"], strict=True):
            assert row["stage"] == line["stage"]
            assert row["cost_value"] == line["cost_value"]
            assert row["share_percent"] == line["share_percent"]

    async def test_the_csv_has_no_blank_row_between_its_lines(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Windows Python plus `csv` writes `\\r\\r\\n` unless the buffer is opened with
        `newline=""`, and Excel reads that as a blank row between every line. Cheap to get wrong,
        invisible until somebody opens the file."""
        _, owner = await _trading(db_session, api_client, "owner")

        exported = await api_client.get(
            f"{REPORTS}/sales?since={_DAY}&until={_DAY}&format=csv", headers=_auth(owner)
        )

        assert "\r\r\n" not in exported.text
        assert "\n\n" not in exported.text.strip()
