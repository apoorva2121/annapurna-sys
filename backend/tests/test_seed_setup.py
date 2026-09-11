"""`make seed` must produce a restaurant somebody can actually look at.

M02's master data has been in `seed/operations.yaml` since M00, validated by `seed/validate.py`
ever since, and loaded by nothing — there was no table to load it into until this module. The
result was a seeded restaurant with nineteen staff and an empty floor: every M02 screen opened
blank, and the manual pass would have begun by hand-building a floor plan before it could test
anything.

The second thing tested here is the dual posting. `POST /auth/switch` (finding S12) is unreachable
in a demo world where nobody works at two branches — the switcher renders nothing for someone with
one restaurant — so the feature would have shipped unverifiable by hand.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee
from app.models.setup import DiningArea, RestaurantTable, Station, TaxGroup
from app.models.tenancy import Restaurant
from app.seed.identity import seed_identity
from app.seed.setup import seed_setup


async def _seed(session: AsyncSession) -> None:
    await seed_identity(session)
    await seed_setup(session)
    await session.flush()


async def _koregaon(session: AsyncSession) -> Restaurant:
    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == "SG_KOREGAON"))
    assert restaurant is not None
    return restaurant


class TestTheFloorIsSeeded:
    async def test_the_dining_areas_arrive(self, db_session: AsyncSession) -> None:
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        areas = (
            await db_session.scalars(
                select(DiningArea)
                .where(DiningArea.restaurant_id == restaurant.id)
                .order_by(DiningArea.seq)
            )
        ).all()

        assert [area.name for area in areas] == ["AC Hall", "Terrace"]

    async def test_seeded_areas_start_at_zero_like_created_ones(
        self, db_session: AsyncSession
    ) -> None:
        """`operations.yaml` numbers from 1 and the column is 0-based, because `next_seq()` starts
        at 0. Mixing the two origins would put the first seeded area and the first area created
        through the API in the same slot, leaving the order to the id tiebreak."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        first = await db_session.scalar(
            select(DiningArea.seq)
            .where(DiningArea.restaurant_id == restaurant.id)
            .order_by(DiningArea.seq)
            .limit(1)
        )

        assert first == 0

    async def test_the_tables_arrive_and_are_all_free(self, db_session: AsyncSession) -> None:
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        tables = (
            await db_session.scalars(
                select(RestaurantTable).where(RestaurantTable.restaurant_id == restaurant.id)
            )
        ).all()

        assert len(tables) == 14
        # A seeded `occupied` would be an order that does not exist.
        assert {table.status for table in tables} == {"free"}

    async def test_the_stations_match_what_the_menu_routes_by(
        self, db_session: AsyncSession
    ) -> None:
        """`seed/menu.yaml` routes dishes to these codes and M08 will render a column per station.
        A station missing here is a dish that cannot be cooked."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        stations = (
            await db_session.scalars(
                select(Station.code).where(Station.restaurant_id == restaurant.id)
            )
        ).all()

        assert set(stations) == {"tandoor", "main_kitchen", "chinese"}

    async def test_the_tax_rate_is_a_decimal_and_not_a_float(
        self, db_session: AsyncSession
    ) -> None:
        """0.05 as a float is 0.05000000000000000277…, and that is what would have been stored.
        The YAML parses it as a float; the seeder converts through `str` (CLAUDE.md invariant 3)."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        rates = (
            await db_session.scalars(
                select(TaxGroup.rate).where(TaxGroup.restaurant_id == restaurant.id)
            )
        ).all()

        assert Decimal("0.0500") in set(rates)

    async def test_the_second_branch_is_deliberately_empty(self, db_session: AsyncSession) -> None:
        """A restaurant with no dining areas is a real state the product meets on day one of
        onboarding, and the seed is the only place it is easy to see."""
        await _seed(db_session)
        baner = await db_session.scalar(select(Restaurant).where(Restaurant.code == "SG_BANER"))
        assert baner is not None

        areas = await db_session.scalar(
            select(func.count()).select_from(DiningArea).where(DiningArea.restaurant_id == baner.id)
        )

        assert areas == 0


class TestSeedingTwiceChangesNothing:
    async def test_a_second_run_creates_no_duplicates(self, db_session: AsyncSession) -> None:
        """`make seed` is run casually and repeatedly. The failure to design against is not that it
        crashed — that is obvious and cheap — but that it silently made a second Terrace."""
        await _seed(db_session)
        restaurant = await _koregaon(db_session)

        second = await seed_setup(db_session)
        await db_session.flush()

        assert second.created_nothing
        areas = (
            await db_session.scalars(
                select(DiningArea.name).where(DiningArea.restaurant_id == restaurant.id)
            )
        ).all()
        tables = await db_session.scalar(
            select(func.count())
            .select_from(RestaurantTable)
            .where(RestaurantTable.restaurant_id == restaurant.id)
        )

        assert sorted(areas) == ["AC Hall", "Terrace"]
        assert tables == 14


class TestTheDualPosting:
    async def test_one_person_works_at_two_branches(self, db_session: AsyncSession) -> None:
        """Without this, `POST /auth/switch` cannot be exercised by hand at all: the switcher
        renders nothing for someone who works at one restaurant (finding S12)."""
        await _seed(db_session)
        vikram = await db_session.scalar(select(Employee).where(Employee.employee_code == "EMP003"))
        assert vikram is not None

        postings = (
            await db_session.scalars(
                select(Restaurant.code)
                .select_from(EmployeeRoleAssignment)
                .join(Restaurant, Restaurant.id == EmployeeRoleAssignment.restaurant_id)
                .where(EmployeeRoleAssignment.employee_id == vikram.id)
            )
        ).all()

        assert set(postings) == {"SG_KOREGAON", "SG_BANER"}

    async def test_he_is_junior_at_the_second_branch(self, db_session: AsyncSession) -> None:
        """Deliberately a lesser role there. Switching must visibly change what he can do — a
        fixture where he held the same role at both would hide exactly the bug P1-2 was."""
        await _seed(db_session)
        vikram = await db_session.scalar(select(Employee).where(Employee.employee_code == "EMP003"))
        assert vikram is not None

        rows = (
            await db_session.execute(
                select(Restaurant.code, Role.code)
                .select_from(EmployeeRoleAssignment)
                .join(Restaurant, Restaurant.id == EmployeeRoleAssignment.restaurant_id)
                .join(Role, Role.id == EmployeeRoleAssignment.role_id)
                .where(EmployeeRoleAssignment.employee_id == vikram.id)
            )
        ).all()

        # Built by hand rather than `dict(rows)` or a comprehension: mypy rejects the first
        # (SQLAlchemy `Row` is not a 2-tuple to it) and ruff rejects the second as redundant.
        by_branch: dict[str, str] = {}
        for branch, role in rows:
            by_branch[branch] = role

        assert by_branch == {"SG_KOREGAON": "manager", "SG_BANER": "waiter"}
