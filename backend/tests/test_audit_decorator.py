"""The decorator, against the four things a hand-written audit call gets wrong.

`@audited` replaces ten near-copies of one idea. Ten copies is nine chances for the tenth to
differ, and the differences that matter are not stylistic:

**A row that records everything.** Two of the old helpers wrote a whole dictionary of current
values and no previous ones, so the trail could say what a thing *is* and not what *changed* —
which is the only question anybody asks of it.

**A row that records a credential.** The old helpers redacted at the call site, which worked for
exactly as long as nobody added a column.

**A row that stopped being written.** A hand-written call inside an `if` that later became an
`elif`; a parameter renamed under a helper that took it positionally. Both are silent, and silence
is indistinguishable from nothing having happened.

**A row with no reason on an act that had one.** M07's waiter handover and M12's attendance
correction both carry a why, and flattening them into a plain diff would lose the half a person
actually reads.

The services here are written for this file. Using a real one would test that service, and the
subject under test is the mechanism — the real services are migrated onto it in the next chunk,
where their own tests are the safety net.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.audit import audited
from app.core.tenancy import TenantScope
from app.models.audit import AuditLog
from app.models.identity import Employee, UserAccount
from app.models.setup import Station
from app.models.tenancy import Organization, Restaurant
from app.repositories.audit import AuditSubjectRepository


class World:
    def __init__(self, organization: Organization, restaurant: Restaurant, actor: Actor) -> None:
        self.organization = organization
        self.restaurant = restaurant
        self.actor = actor

    @property
    def scope(self) -> TenantScope:
        return self.actor.scope


async def _world(session: AsyncSession) -> World:
    organization = Organization(name="Spice Garden", slug=f"sg-{uuid.uuid4().hex[:8]}")
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name="Koregaon Park",
        code=f"KP{uuid.uuid4().hex[:6]}",
        timezone="Asia/Kolkata",
    )
    session.add(restaurant)
    await session.flush()
    employee = Employee(
        organization_id=organization.id,
        employee_code=f"E{uuid.uuid4().hex[:6]}",
        full_name="Priya",
        joined_on=date(2026, 1, 1),
    )
    session.add(employee)
    await session.flush()
    actor = Actor(
        employee_id=employee.id,
        organization_id=organization.id,
        restaurant_id=restaurant.id,
        full_name="Priya",
        permissions=frozenset(),
        rank=10,
    )
    return World(organization, restaurant, actor)


async def _station(session: AsyncSession, world: World, *, name: str = "Tandoor") -> Station:
    station = Station(
        restaurant_id=world.restaurant.id,
        code=f"ST{uuid.uuid4().hex[:5]}",
        name=name,
        seq=0,
        is_active=True,
    )
    session.add(station)
    await session.flush()
    return station


class Stations:
    """A service shaped like the real ones: a session, and methods that take an `Actor`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @audited("station.rename", entity="station", key="station_id")
    async def rename(self, actor: Actor, station_id: uuid.UUID, *, name: str) -> None:
        station = (
            await self.session.scalars(select(Station).where(Station.id == station_id))
        ).one()
        station.name = name

    @audited("station.create", entity="station")
    async def create(self, actor: Actor, *, name: str) -> Station:
        station = Station(
            restaurant_id=actor.restaurant_id,
            code=f"ST{uuid.uuid4().hex[:5]}",
            name=name,
            seq=1,
            is_active=True,
        )
        self.session.add(station)
        await self.session.flush()
        return station

    @audited("station.retire", entity="station", key="station_id")
    async def retire(self, actor: Actor, station_id: uuid.UUID) -> None:
        station = (
            await self.session.scalars(select(Station).where(Station.id == station_id))
        ).one()
        await self.session.delete(station)

    @audited("station.rename", entity="station", key="station_id", reason="because")
    async def rename_with_reason(
        self,
        actor: Actor,
        station_id: uuid.UUID,
        *,
        name: str,
        because: str | None,
    ) -> None:
        station = (
            await self.session.scalars(select(Station).where(Station.id == station_id))
        ).one()
        station.name = name

    @audited("user.rotate", entity="user_account", key="account_id")
    async def rotate(self, actor: Actor, account_id: uuid.UUID, *, password_hash: str) -> None:
        account = (
            await self.session.scalars(select(UserAccount).where(UserAccount.id == account_id))
        ).one()
        account.password_hash = password_hash


async def _rows(session: AsyncSession) -> list[AuditLog]:
    await session.flush()
    return list((await session.scalars(select(AuditLog).order_by(AuditLog.id))).all())


class TestWhatTheRowSays:
    async def test_an_update_records_only_what_changed(self, db_session: AsyncSession) -> None:
        """Both sides, and only the columns that moved.

        A row carrying every column of both states would be a second copy of the table with no
        retention story, and the question somebody asks of the trail is *what changed*.
        """
        world = await _world(db_session)
        station = await _station(db_session, world, name="Tandoor")

        await Stations(db_session).rename(world.actor, station.id, name="Grill")

        row = (await _rows(db_session))[0]
        assert row.action == "station.rename"
        assert row.entity_type == "station"
        assert row.entity_id == station.id
        assert row.old_value == {"name": "Tandoor"}
        assert row.new_value == {"name": "Grill"}

    async def test_the_row_names_the_person_and_the_restaurant(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)
        station = await _station(db_session, world)

        await Stations(db_session).rename(world.actor, station.id, name="Grill")

        row = (await _rows(db_session))[0]
        assert row.actor_employee_id == world.actor.employee_id
        assert row.restaurant_id == world.restaurant.id

    async def test_a_timestamp_moving_is_not_a_change(self, db_session: AsyncSession) -> None:
        """`updated_at` moves on every write. In the diff it would be a line in every row that says
        only "something was written", which the row's existence already says."""
        world = await _world(db_session)
        station = await _station(db_session, world)

        await Stations(db_session).rename(world.actor, station.id, name="Grill")

        row = (await _rows(db_session))[0]
        assert set(row.new_value or {}) == {"name"}

    async def test_a_create_takes_its_id_from_what_the_method_returned(
        self, db_session: AsyncSession
    ) -> None:
        """Before the call there was nothing to have an id, so there is no parameter to name."""
        world = await _world(db_session)

        station = await Stations(db_session).create(world.actor, name="Chaat counter")

        row = (await _rows(db_session))[0]
        assert row.entity_id == station.id
        assert row.old_value is None
        assert (row.new_value or {})["name"] == "Chaat counter"

    async def test_a_delete_records_the_row_that_went(self, db_session: AsyncSession) -> None:
        """The one case where a whole side is the answer: what was deleted is what changed."""
        world = await _world(db_session)
        station = await _station(db_session, world, name="Tandoor")

        await Stations(db_session).retire(world.actor, station.id)

        row = (await _rows(db_session))[0]
        assert row.new_value is None
        assert (row.old_value or {})["name"] == "Tandoor"

    async def test_a_reason_goes_in_the_metadata_beside_the_values(
        self, db_session: AsyncSession
    ) -> None:
        """M07's waiter handover and M12's attendance correction both carry one, and
        `audit_log` has no `reason` column — the metadata block keeps the why in the same row as
        the values it explains."""
        world = await _world(db_session)
        station = await _station(db_session, world)

        await Stations(db_session).rename_with_reason(
            world.actor, station.id, name="Grill", because="the tandoor moved to the back"
        )

        row = (await _rows(db_session))[0]
        assert row.audit_metadata == {"reason": "the tandoor moved to the back"}

    async def test_no_reason_writes_no_metadata(self, db_session: AsyncSession) -> None:
        world = await _world(db_session)
        station = await _station(db_session, world)

        await Stations(db_session).rename_with_reason(
            world.actor, station.id, name="Grill", because=None
        )

        assert (await _rows(db_session))[0].audit_metadata is None


class TestWhatTheRowNeverSays:
    async def test_a_credential_never_reaches_the_trail(self, db_session: AsyncSession) -> None:
        """The table is readable by anyone holding `audit.view`, so a hash landing here is a leak
        with a long tail — and unlike a log line it is not rotated away.

        The old helpers redacted at the *call site*, which worked until somebody added a column.
        """
        world = await _world(db_session)
        account = UserAccount(
            organization_id=world.organization.id,
            email=f"{uuid.uuid4().hex[:8]}@spicegarden.test",
            password_hash="argon2-before",
        )
        db_session.add(account)
        await db_session.flush()

        await Stations(db_session).rotate(
            world.actor,
            account.id,
            password_hash="argon2-after",
        )

        row = (await _rows(db_session))[0]
        # The change is recorded; the secret is not. Both halves matter: a rotation nobody can see
        # is as bad as a hash anybody can read.
        assert row.action == "user.rotate"
        assert "argon2-after" not in str(row.new_value)
        assert "password_hash" not in (row.new_value or {})


class TestTheSubjectIsReadWithinTheTenant:
    async def test_another_restaurants_row_is_not_readable(self, db_session: AsyncSession) -> None:
        """Invariant 1, at the one place it would be most tempting to skip: a decorator that called
        `session.get()` would be the single unscoped read in this codebase, inside the mechanism
        that records who did what."""
        mine = await _world(db_session)
        theirs = await _world(db_session)
        station = await _station(db_session, theirs, name="Their tandoor")

        snapshot = await AuditSubjectRepository(db_session, mine.scope).snapshot(
            "station", station.id
        )

        assert snapshot is None

    async def test_an_organization_owned_subject_is_scoped_to_the_organization(
        self, db_session: AsyncSession
    ) -> None:
        """An employee is employed by the company, not by a branch (`repositories/base.py`), so the
        loader picks the tenant column the model actually carries."""
        mine = await _world(db_session)
        theirs = await _world(db_session)

        assert (
            await AuditSubjectRepository(db_session, mine.scope).snapshot(
                "employee", theirs.actor.employee_id
            )
            is None
        )
        assert (
            await AuditSubjectRepository(db_session, mine.scope).snapshot(
                "employee", mine.actor.employee_id
            )
            is not None
        )

    async def test_a_table_owned_by_nobody_cannot_be_audited(
        self, db_session: AsyncSession
    ) -> None:
        """`issue` is reference data with no tenant column. Silently skipping the filter for such a
        table is how that becomes the precedent for skipping it elsewhere."""
        world = await _world(db_session)

        with pytest.raises(LookupError, match="neither restaurant_id nor organization_id"):
            await AuditSubjectRepository(db_session, world.scope).snapshot("issue", uuid.uuid4())


class TestTheDeclarationIsCheckedWhenItIsWritten:
    def test_a_key_that_names_no_parameter_fails_at_import(self) -> None:
        """The quiet failure this prevents: rename `order_id` to `bill_id`, and a decorator looking
        up the old name writes rows with no subject — or none at all — for a year."""
        with pytest.raises(TypeError, match="names a parameter 'bill_id'"):

            class Broken:
                @audited("order.void", entity="order", key="bill_id")
                async def void(self, actor: Actor, order_id: uuid.UUID) -> None: ...

    def test_a_method_without_an_actor_fails_at_import(self) -> None:
        with pytest.raises(TypeError, match="names a parameter 'actor'"):

            class Anonymous:
                @audited("order.void", entity="order", key="order_id")
                async def void(self, order_id: uuid.UUID) -> None: ...

    async def test_an_entity_that_is_no_table_fails_at_the_first_call(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)

        class Invented:
            def __init__(self, session: AsyncSession) -> None:
                self.session = session

            @audited("thing.change", entity="not_a_table", key="thing_id")
            async def change(self, actor: Actor, thing_id: uuid.UUID) -> None: ...

        with pytest.raises(LookupError, match="no mapped table is called 'not_a_table'"):
            await Invented(db_session).change(world.actor, uuid.uuid4())

    async def test_a_create_that_returns_nothing_useful_says_so(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)

        class Careless:
            def __init__(self, session: AsyncSession) -> None:
                self.session = session

            @audited("station.create", entity="station")
            async def create(self, actor: Actor) -> Any:
                return None

        with pytest.raises(TypeError, match="takes the entity id from what the method returns"):
            await Careless(db_session).create(world.actor)


class TestTheDecoratorDisturbsNothing:
    """The regression that cost 34 tests, and the rule it leaves behind.

    The first version of the snapshot loaded the mapped object and called `session.expire()` on it
    to read the after-state. It worked, and it also expired *the caller's* object: the route that
    had just created a stock item then serialised it, found its eagerly-loaded `ingredient` gone,
    and died on `lazy="raise"` with a 500.

        FAILED tests/test_waste_endpoints.py::TestReasons::test_the_stage_cannot_be_changed
        ValidationError: 2 validation errors for PricedStockItemResponse
        ingredient
          Error extracting attribute: InvalidRequestError: 'StockItem.ingredient' is not
          available due to lazy='raise'
        ... 34 failed, 262 passed

    **An audit decorator that changes what the method it wraps returns is worse than no
    decorator**, because it turns a recording mechanism into a source of bugs in the paths it
    records. The snapshot now reads columns, which touches no identity map.
    """

    async def test_what_the_method_returned_is_still_usable_afterwards(
        self, db_session: AsyncSession
    ) -> None:
        world = await _world(db_session)

        station = await Stations(db_session).create(world.actor, name="Chaat counter")

        assert sqlalchemy_inspect(station).expired is False
        # Readable without a query, which is what a caller about to serialise it needs.
        assert station.name == "Chaat counter"

    async def test_an_update_leaves_the_subject_loaded(self, db_session: AsyncSession) -> None:
        world = await _world(db_session)
        station = await _station(db_session, world, name="Tandoor")

        await Stations(db_session).rename(world.actor, station.id, name="Grill")

        assert sqlalchemy_inspect(station).expired is False
        assert station.name == "Grill"
