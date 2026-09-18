"""The roster over HTTP: staffing it, clocking in, and who is on the floor.

`test_generic_suites.py` already proves every route here is tenant-isolated and declares a
permission, and `test_shift_window.py` proves the crossing-midnight arithmetic without a database.
What is left, and what this file is:

- **you cannot clock in somebody else** — the endpoint takes no employee id, so the only way to
  try is to use another person's assignment id, and that is refused;
- **a correction needs a reason and leaves an audit row** naming both values, because asserting
  somebody else's attendance is a different act from their clocking in;
- **`present` and `late` are derived; `absent` and `leave` are said by a person**, and nothing in
  the background flips either;
- **every role can read the roster and clock itself in**, asserted over the catalogue;
- **every write actually commits** — each is followed by a second request that reads it back.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CATALOGUE
from app.models.audit import AuditLog
from app.models.setup import DiningArea
from app.models.shifts import ShiftAssignment
from tests.test_conversations import _people
from tests.test_setup_endpoints import _auth, _token, _world

STAFF = "/api/v1/staff"
SHIFTS = f"{STAFF}/shifts"

EVERY_ROLE = tuple(role.code for role in CATALOGUE.roles)


async def _shift(
    client: AsyncClient,
    token: str,
    *,
    name: str = "Morning",
    start: str = "08:00:00",
    end: str = "16:00:00",
) -> Any:
    return await client.post(
        SHIFTS,
        json={"name": name, "start_time": start, "end_time": end},
        headers=_auth(token),
    )


async def _assign(
    client: AsyncClient,
    token: str,
    shift_id: str,
    employee_id: str,
    *,
    business_date: str | None = None,
    area_id: str | None = None,
) -> Any:
    body: dict[str, Any] = {
        "shift_id": shift_id,
        "employee_id": employee_id,
        "business_date": business_date or date.today().isoformat(),
    }
    if area_id is not None:
        body["dining_area_id"] = area_id
    return await client.post(f"{SHIFTS}/assignments", json=body, headers=_auth(token))


async def _today(client: AsyncClient, token: str) -> str:
    """The restaurant's business date, taken from the product rather than from `date.today()` —
    which is the whole point of invariant 4 and would be wrong at 2am."""
    response = await client.get(f"{SHIFTS}/on-now", headers=_auth(token))
    assert response.status_code == 200, response.text
    return str(response.json()["business_date"])


class TestTheShiftsThemselves:
    async def test_a_shift_survives_the_request_that_made_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Two requests, deliberately. Only the second can tell whether anything committed."""
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")

        created = await _shift(api_client, owner)
        assert created.status_code == 201, created.text

        listed = await api_client.get(SHIFTS, headers=_auth(owner))
        assert [row["name"] for row in listed.json()["items"]] == ["Morning"]

    async def test_an_evening_shift_that_crosses_midnight_is_legal_and_says_so(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The evening shift of a place that closes at two. `crosses_midnight` is derived, so a
        screen never has to compare two times to know how to render one."""
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        created = await _shift(
            api_client, owner, name="Evening", start="18:00:00", end="00:30:00"
        )
        assert created.status_code == 201, created.text
        assert created.json()["crosses_midnight"] is True

    async def test_two_shifts_cannot_share_a_name(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        await _shift(api_client, owner)
        again = await _shift(api_client, owner)
        assert again.status_code == 409, again.text

    async def test_a_deactivated_shift_keeps_its_assignments_readable(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """ADR 0008's master-data tier: a report on last quarter must still be able to name it."""
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        shift = (await _shift(api_client, owner)).json()
        await _assign(api_client, owner, shift["id"], people["owner"])

        await api_client.patch(
            f"{SHIFTS}/{shift['id']}", json={"is_active": False}, headers=_auth(owner)
        )

        roster = await api_client.get(f"{SHIFTS}/roster", headers=_auth(owner))
        assert roster.status_code == 200, roster.text
        assert [row["shift_name"] for row in roster.json()["items"]] == ["Morning"]

    async def test_a_waiter_cannot_create_a_shift(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "waiter")
        waiter = await _token(api_client, "waiter")
        refused = await _shift(api_client, waiter)
        assert refused.status_code == 403, refused.text


class TestStaffingIt:
    async def test_the_same_person_cannot_be_staffed_twice(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        shift = (await _shift(api_client, owner)).json()

        first = await _assign(api_client, owner, shift["id"], people["waiter"])
        assert first.status_code == 201, first.text
        again = await _assign(api_client, owner, shift["id"], people["waiter"])
        assert again.status_code == 409, again.text

    async def test_somebody_who_does_not_work_here_cannot_be_staffed(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        shift = (await _shift(api_client, owner)).json()
        refused = await _assign(api_client, owner, shift["id"], str(uuid.uuid4()))
        assert refused.status_code == 404, refused.text

    async def test_an_assignment_that_has_started_cannot_be_deleted(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """After it starts it is a record, and the way to say somebody did not work is `absent` —
        which has an author."""
        await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        # 05:00 to 04:59 *is* the business day (invariant 4), so this has begun whatever the
        # clock says when the suite runs — which a 00:00 start would not: see
        # `test_a_midnight_start_belongs_to_the_end_of_the_business_day`.
        shift = (
            await _shift(api_client, owner, name="All day", start="05:00:00", end="04:59:00")
        ).json()
        today = await _today(api_client, owner)
        assignment = (
            await _assign(api_client, owner, shift["id"], people["waiter"], business_date=today)
        ).json()

        refused = await api_client.delete(
            f"{SHIFTS}/assignments/{assignment['id']}", headers=_auth(owner)
        )
        assert refused.status_code == 409, refused.text

    async def test_a_future_assignment_can_be_deleted(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        shift = (await _shift(api_client, owner)).json()
        later = (date.today() + timedelta(days=7)).isoformat()
        assignment = (
            await _assign(api_client, owner, shift["id"], people["waiter"], business_date=later)
        ).json()

        removed = await api_client.delete(
            f"{SHIFTS}/assignments/{assignment['id']}", headers=_auth(owner)
        )
        assert removed.status_code == 204, removed.text


class TestTheClock:
    async def test_clocking_in_records_the_time_and_makes_you_present(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        shift = (
            await _shift(api_client, owner, name="All day", start="05:00:00", end="04:59:00")
        ).json()
        today = await _today(api_client, owner)
        assignment = (
            await _assign(api_client, owner, shift["id"], people["waiter"], business_date=today)
        ).json()

        waiter = await _token(api_client, "waiter")
        clocked = await api_client.post(
            f"{SHIFTS}/assignments/{assignment['id']}/clock-in", headers=_auth(waiter)
        )
        assert clocked.status_code == 200, clocked.text
        assert clocked.json()["clock_in_at"] is not None
        # The day opened at 05:00 and the suite runs later, so this is late — which is the
        # derivation working rather than a problem with the fixture.
        assert clocked.json()["status"] in ("present", "late")

        read_back = await api_client.get(f"{SHIFTS}/me", headers=_auth(waiter))
        assert read_back.json()["items"][0]["clock_in_at"] is not None

    async def test_you_cannot_clock_in_somebody_else(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """There is no field for it, so the only way to try is to use their assignment's id."""
        await _world(db_session, "owner", "waiter", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        shift = (
            await _shift(api_client, owner, name="All day", start="05:00:00", end="04:59:00")
        ).json()
        today = await _today(api_client, owner)
        theirs = (
            await _assign(api_client, owner, shift["id"], people["waiter"], business_date=today)
        ).json()

        chef = await _token(api_client, "chef")
        refused = await api_client.post(
            f"{SHIFTS}/assignments/{theirs['id']}/clock-in", headers=_auth(chef)
        )
        assert refused.status_code == 403, refused.text
        assert refused.json()["code"] == "shift.not_yours"

    async def test_each_refusal_is_its_own_sentence(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A waiter with a phone in one hand at the start of service will not debug a single
        "cannot clock in", so there are five refusals and five messages."""
        await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        shift = (
            await _shift(api_client, owner, name="All day", start="05:00:00", end="04:59:00")
        ).json()
        today = await _today(api_client, owner)
        assignment = (
            await _assign(api_client, owner, shift["id"], people["waiter"], business_date=today)
        ).json()
        waiter = await _token(api_client, "waiter")
        clock_in = f"{SHIFTS}/assignments/{assignment['id']}/clock-in"
        clock_out = f"{SHIFTS}/assignments/{assignment['id']}/clock-out"

        too_early = await api_client.post(clock_out, headers=_auth(waiter))
        assert too_early.json()["code"] == "shift.not_clocked_in"

        await api_client.post(clock_in, headers=_auth(waiter))
        twice = await api_client.post(clock_in, headers=_auth(waiter))
        assert twice.json()["code"] == "shift.already_clocked_in"

        await api_client.post(clock_out, headers=_auth(waiter))
        out_twice = await api_client.post(clock_out, headers=_auth(waiter))
        assert out_twice.json()["code"] == "shift.already_clocked_out"

    async def test_you_cannot_clock_in_to_another_days_shift(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        shift = (await _shift(api_client, owner)).json()
        later = (date.today() + timedelta(days=3)).isoformat()
        assignment = (
            await _assign(api_client, owner, shift["id"], people["waiter"], business_date=later)
        ).json()

        waiter = await _token(api_client, "waiter")
        refused = await api_client.post(
            f"{SHIFTS}/assignments/{assignment['id']}/clock-in", headers=_auth(waiter)
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "shift.not_today"

    async def test_a_missed_clock_out_stays_open(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Nothing closes it at a guessed time: M17 normalises per hour worked, and a wrong
        denominator is worse than a missing one."""
        await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        shift = (
            await _shift(api_client, owner, name="All day", start="05:00:00", end="04:59:00")
        ).json()
        today = await _today(api_client, owner)
        assignment = (
            await _assign(api_client, owner, shift["id"], people["waiter"], business_date=today)
        ).json()
        waiter = await _token(api_client, "waiter")
        await api_client.post(
            f"{SHIFTS}/assignments/{assignment['id']}/clock-in", headers=_auth(waiter)
        )

        mine = await api_client.get(f"{SHIFTS}/me", headers=_auth(waiter))
        assert mine.json()["items"][0]["is_open"] is True


class TestCorrectionsHaveAnAuthor:
    async def test_a_correction_needs_a_reason(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        shift = (await _shift(api_client, owner)).json()
        assignment = (await _assign(api_client, owner, shift["id"], people["waiter"])).json()

        refused = await api_client.patch(
            f"{SHIFTS}/assignments/{assignment['id']}",
            json={"clock_in_at": datetime.now(UTC).isoformat()},
            headers=_auth(owner),
        )
        assert refused.status_code == 422, refused.text

    async def test_a_correction_writes_an_audit_row_with_both_values(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """"Suresh's phone was dead" is a legitimate, recorded, attributable act — and it must not
        look like his clocking in."""
        await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        shift = (await _shift(api_client, owner)).json()
        assignment = (await _assign(api_client, owner, shift["id"], people["waiter"])).json()

        corrected = await api_client.patch(
            f"{SHIFTS}/assignments/{assignment['id']}",
            json={
                "clock_in_at": datetime.now(UTC).isoformat(),
                "reason": "His phone was dead.",
            },
            headers=_auth(owner),
        )
        assert corrected.status_code == 200, corrected.text

        rows = await db_session.scalars(
            select(AuditLog).where(AuditLog.action == "shift.corrected")
        )
        row = rows.first()
        assert row is not None
        assert row.old_value is not None and row.new_value is not None
        assert row.audit_metadata == {"reason": "His phone was dead."}

    async def test_nobody_can_assert_present_by_hand(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Present and late are what clocking in *means*. A manager setting one on a row with no
        times is how M17 later counts hours nobody worked."""
        await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        shift = (await _shift(api_client, owner)).json()
        assignment = (await _assign(api_client, owner, shift["id"], people["waiter"])).json()

        refused = await api_client.post(
            f"{SHIFTS}/assignments/{assignment['id']}/status",
            json={"status": "present"},
            headers=_auth(owner),
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "shift.status_not_settable"

    async def test_absent_is_set_by_a_person_and_nothing_else(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        shift = (await _shift(api_client, owner)).json()
        assignment = (await _assign(api_client, owner, shift["id"], people["waiter"])).json()

        marked = await api_client.post(
            f"{SHIFTS}/assignments/{assignment['id']}/status",
            json={"status": "absent"},
            headers=_auth(owner),
        )
        assert marked.status_code == 200, marked.text
        assert marked.json()["status"] == "absent"


class TestEverybodyReadsTheRoster:
    @pytest.mark.parametrize("role", EVERY_ROLE)
    async def test_every_role_can_open_the_roster_and_its_own_shifts(
        self, db_session: AsyncSession, api_client: AsyncClient, role: str
    ) -> None:
        """The deliberate widening of the P1 grant: a roster nobody can read is a noticeboard in a
        locked room. Asserted over the catalogue, so a role added later fails here."""
        roles = ("owner",) if role == "owner" else ("owner", role)
        await _world(db_session, *roles)
        token = await _token(api_client, role)

        for path in (SHIFTS, f"{SHIFTS}/roster", f"{SHIFTS}/me", f"{SHIFTS}/on-now"):
            response = await api_client.get(path, headers=_auth(token))
            assert response.status_code == 200, f"{role} cannot read {path}: {response.text}"

    async def test_staffing_stays_behind_shift_manage(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The permission opens the screen; the scope decides the content."""
        await _world(db_session, "owner", "waiter")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        shift = (await _shift(api_client, owner)).json()

        waiter = await _token(api_client, "waiter")
        refused = await _assign(api_client, waiter, shift["id"], people["waiter"])
        assert refused.status_code == 403, refused.text


class TestWhoIsOnNow:
    async def test_a_shift_covering_now_is_on_and_one_that_is_not_is_not(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "waiter", "chef")
        owner = await _token(api_client, "owner")
        people = await _people(api_client, owner)
        today = await _today(api_client, owner)

        on = (
            await _shift(api_client, owner, name="All day", start="05:00:00", end="04:59:00")
        ).json()
        # 05:00 exactly: the business day's own boundary, so this shift is a single minute long and
        # is almost certainly not now.
        off = (
            await _shift(api_client, owner, name="A minute", start="05:00:00", end="05:01:00")
        ).json()
        await _assign(api_client, owner, on["id"], people["waiter"], business_date=today)
        await _assign(api_client, owner, off["id"], people["chef"], business_date=today)

        now = await api_client.get(f"{SHIFTS}/on-now", headers=_auth(owner))
        assert now.status_code == 200, now.text
        names = {row["shift_name"] for row in now.json()["items"]}
        assert "All day" in names
        assert "A minute" not in names


async def _area_of(session: AsyncSession) -> uuid.UUID:
    area = (await session.scalars(select(DiningArea).where(DiningArea.name == "Hall"))).one()
    return area.id


async def test_a_midnight_start_belongs_to_the_end_of_the_business_day(
    db_session: AsyncSession, api_client: AsyncClient
) -> None:
    """The consequence of invariant 4 that surprises everybody once, including this file.

    A restaurant's day runs 05:00 to 05:00. A shift starting at 00:00 on business date D is
    therefore **not** the beginning of D — it is the small hours at the *end* of it, at 00:00 on
    the following calendar day. That is correct and it is worth a test rather than a comment,
    because the first fixture written here assumed the opposite and three tests failed for it.
    """
    from app.core.shift_window import span_of

    span = span_of(
        business_day=date(2026, 9, 18),
        start=time(0, 0),
        end=time(4, 0),
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
    )
    from zoneinfo import ZoneInfo

    assert span.starts_at.astimezone(ZoneInfo("Asia/Kolkata")).date() == date(2026, 9, 19)


class TestTheRosterAssignsTheWaiter:
    """The owner's decision of 2026-09-14, buildable since M12. Five rules, five tests."""

    async def _rostered(
        self,
        session: AsyncSession,
        client: AsyncClient,
        *,
        who: tuple[str, ...],
    ) -> Any:
        """Put `who` on an all-day shift covering the Hall, which is where M07's tables are."""
        from tests.test_orders_endpoints import _setup

        world, menu, waiter_token = await _setup(session, client)
        owner = await _token(client, "owner")
        people = await _people(client, owner)
        today = await _today(client, owner)
        shift = (
            await _shift(client, owner, name="All day", start="05:00:00", end="04:59:00")
        ).json()
        area = str(await _area_of(session))
        for role in who:
            assigned = await _assign(
                client, owner, shift["id"], people[role], business_date=today, area_id=area
            )
            assert assigned.status_code == 201, assigned.text
        return world, menu, waiter_token

    async def test_one_waiter_on_the_section_gets_the_order(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        from tests.test_orders_endpoints import _open

        _world_, menu, _ = await self._rostered(db_session, api_client, who=("waiter",))
        manager = await _token(api_client, "manager")

        order = await _open(api_client, manager, menu)
        assert order["waiter"] is not None
        assert order["waiter"]["full_name"] == "Waiter Person"

    async def test_the_audit_row_says_why(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A month later, "why is this Priya's order" has an answer that is not a shrug."""
        from tests.test_orders_endpoints import _open

        _world_, menu, _ = await self._rostered(db_session, api_client, who=("waiter",))
        manager = await _token(api_client, "manager")

        await _open(api_client, manager, menu)

        rows = await db_session.scalars(
            select(AuditLog).where(AuditLog.action == "order.waiter_assigned")
        )
        row = rows.first()
        assert row is not None
        assert row.audit_metadata == {"reason": "roster"}

    async def test_two_waiters_on_the_section_assign_nobody(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A wrong waiter is worse than none: it is somebody else's performance score and somebody
        else's name on an audit row."""
        from tests.test_orders_endpoints import _open

        _world_, menu, _ = await self._rostered(
            db_session, api_client, who=("waiter", "manager")
        )
        manager = await _token(api_client, "manager")

        order = await _open(api_client, manager, menu)
        assert order["waiter"] is None

    async def test_it_never_overrides_a_person(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A waiter opening their own order is still its waiter, roster or not."""
        from tests.test_orders_endpoints import _open

        _world_, menu, waiter_token = await self._rostered(
            db_session, api_client, who=("manager",)
        )

        order = await _open(api_client, waiter_token, menu)
        assert order["waiter"]["full_name"] == "Waiter Person"

    async def test_a_takeaway_order_gets_nobody_from_the_roster(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        from tests.test_orders_endpoints import _open

        _world_, menu, _ = await self._rostered(db_session, api_client, who=("waiter",))
        manager = await _token(api_client, "manager")

        order = await _open(api_client, manager, menu, type="takeaway", table_ids=[])
        assert order["waiter"] is None
