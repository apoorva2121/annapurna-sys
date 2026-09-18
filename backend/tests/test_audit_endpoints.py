"""The trail and the centre over HTTP: who may read what, and what each row says.

Three things this file is for, and each is a rule that would be invisible in a unit test.

**A manager cannot open the trail.** The P1 design gives `audit.view` to the owner, the
administrator and the accountant. The person who runs the floor is frequently the *subject* of the
record, and a record its subject curates is not a record. The route refuses; it does not redact.

**Every row is a sentence.** A JSON blob on a screen is a log, and the person who opens this is
already suspicious about something — they should read *"Priya repriced a dish — price 480.00 →
520.00"*, not `{"price": "520.00"}`.

**The centre shows a person what they can act on** (`docs/product/vision.md` §25). A waiter sees
their own overdue task and not the food-cost conditions they cannot change; an owner does not see
one waiter's overdue task as though it were their problem. The vision's own sentence is *"this
will prevent notification overload"*, and this is where that survives contact with a real week.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.audit import record
from app.core.enums import MovementType, TaskPriority, TaskStatus
from app.models.communication import Task
from app.models.identity import Employee
from app.models.inventory import StockBatch, StockMovement
from app.models.stock import StockItem
from tests.test_setup_endpoints import World, _auth, _token
from tests.test_setup_endpoints import _world as _identity_world

STAFF = "/api/v1/staff"


async def _employee(session: AsyncSession, world: World, role: str) -> Employee:
    """The person `_world` seeded for a role. It names them "<Role> Person"."""
    found = (
        await session.scalars(
            select(Employee).where(
                Employee.organization_id == world.organization.id,
                Employee.full_name == f"{role.title()} Person",
            )
        )
    ).first()
    assert found is not None, f"no seeded employee for {role}"
    return found


async def _actor(session: AsyncSession, world: World, role: str = "owner") -> Actor:
    """An actor for a seeded login, built the way the API builds one."""
    employee = await _employee(session, world, role)
    return Actor(
        employee_id=employee.id,
        organization_id=world.organization.id,
        restaurant_id=world.restaurant.id,
        full_name=employee.full_name,
        permissions=frozenset(),
        rank=0,
    )


async def _stock_item(session: AsyncSession, world: World, *, name: str) -> StockItem:
    item = StockItem(
        restaurant_id=world.restaurant.id,
        code=f"S{uuid.uuid4().hex[:6]}",
        name=name,
        kind="ingredient",
        base_unit="g",
        is_active=True,
    )
    session.add(item)
    await session.flush()
    return item


async def _consumed_without_receiving(
    session: AsyncSession, world: World, item: StockItem, quantity: str
) -> None:
    """A negative position: stock used that nobody recorded receiving.

    `docs/onboarding-cold-start.md` calls this week one for a real restaurant rather than an edge
    case, which is why the centre calls it `critical`.
    """
    rid = world.restaurant.id
    batch = StockBatch(
        restaurant_id=rid,
        stock_item_id=item.id,
        batch_code=f"B{uuid.uuid4().hex[:8]}",
        quantity_received=Decimal("0"),
        unit_cost=Decimal("0.36"),
        received_at=datetime(2026, 9, 10, 6, 0, tzinfo=UTC),
        source="opening",
    )
    session.add(batch)
    await session.flush()
    session.add(
        StockMovement(
            restaurant_id=rid,
            stock_batch_id=batch.id,
            stock_item_id=item.id,
            type=MovementType.CONSUMPTION.value,
            quantity_delta=-Decimal(quantity),
            unit_cost=Decimal("0.36"),
            basis="actual",
            occurred_at=datetime(2026, 9, 16, 15, 0, tzinfo=UTC),
            business_date=datetime(2026, 9, 16, tzinfo=UTC).date(),
        )
    )
    await session.flush()


async def _overdue_task(session: AsyncSession, world: World, *, assigned_to: uuid.UUID) -> Task:
    task = Task(
        restaurant_id=world.restaurant.id,
        title="Clean the fryer",
        assigned_to=assigned_to,
        priority=TaskPriority.NORMAL.value,
        status=TaskStatus.ASSIGNED.value,
        due_at=datetime.now(UTC) - timedelta(hours=3),
        revision=1,
    )
    session.add(task)
    await session.flush()
    return task


class TestWhoMayReadTheTrail:
    async def test_a_manager_cannot_open_the_audit_trail(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The P1 design's line: the person who runs the floor is frequently the subject."""
        await _identity_world(db_session, "owner", "manager")
        await db_session.commit()
        manager = await _token(api_client, "manager")

        refused = await api_client.get(f"{STAFF}/audit", headers=_auth(manager))

        assert refused.status_code == 403, refused.text

    async def test_the_owner_and_the_accountant_can(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _identity_world(db_session, "owner", "accountant")
        await db_session.commit()

        for role in ("owner", "accountant"):
            token = await _token(api_client, role)
            allowed = await api_client.get(f"{STAFF}/audit", headers=_auth(token))
            assert allowed.status_code == 200, f"{role}: {allowed.text}"

    async def test_a_waiter_cannot(self, db_session: AsyncSession, api_client: AsyncClient) -> None:
        await _identity_world(db_session, "owner", "waiter")
        await db_session.commit()
        waiter = await _token(api_client, "waiter")

        refused = await api_client.get(f"{STAFF}/audit", headers=_auth(waiter))

        assert refused.status_code == 403, refused.text


class TestWhatARowSays:
    async def test_every_row_renders_as_a_sentence(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """*"Priya repriced a dish — price 480.00 → 520.00."* A blob is a log, not a record."""
        world = await _identity_world(db_session, "owner")
        actor = await _actor(db_session, world)
        item = await _stock_item(db_session, world, name="Paneer")
        record(
            db_session,
            actor,
            action="stock_item.repriced",
            entity="stock_item",
            entity_id=item.id,
            old={"current_unit_cost": Decimal("0.36")},
            new={"current_unit_cost": Decimal("0.42")},
        )
        await db_session.commit()
        owner = await _token(api_client, "owner")

        body = (await api_client.get(f"{STAFF}/audit", headers=_auth(owner))).json()

        row = next(item for item in body["items"] if item["action"] == "stock_item.repriced")
        assert row["sentence"].endswith("current unit cost 0.36 → 0.42.")
        assert row["actor_name"] is not None
        # And the raw values are there beneath it, for when the sentence is not enough.
        assert row["old_value"] == {"current_unit_cost": "0.36"}

    async def test_a_reason_reaches_the_wire(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """M07's waiter handover and M12's attendance correction both carry one, and it is the
        half a person actually reads."""
        world = await _identity_world(db_session, "owner")
        actor = await _actor(db_session, world)
        record(
            db_session,
            actor,
            action="shift.corrected",
            entity="shift_assignment",
            entity_id=uuid.uuid4(),
            new={"clock_in_at": "2026-09-18T12:00:00+00:00"},
            reason="His phone was dead.",
        )
        await db_session.commit()
        owner = await _token(api_client, "owner")

        body = (await api_client.get(f"{STAFF}/audit", headers=_auth(owner))).json()

        assert body["items"][0]["reason"] == "His phone was dead."

    async def test_the_trail_filters_by_entity_and_by_actor(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The two questions somebody actually arrives with: *what happened to this*, and *what
        did this person do*."""
        world = await _identity_world(db_session, "owner")
        actor = await _actor(db_session, world)
        item = await _stock_item(db_session, world, name="Paneer")
        record(
            db_session,
            actor,
            action="stock_item.repriced",
            entity="stock_item",
            entity_id=item.id,
            new={"current_unit_cost": Decimal("0.42")},
        )
        record(
            db_session,
            actor,
            action="order.cancel",
            entity="order",
            entity_id=uuid.uuid4(),
            new={"reason": "guest left"},
        )
        await db_session.commit()
        owner = await _token(api_client, "owner")

        by_entity = (
            await api_client.get(
                f"{STAFF}/audit?entity_type=stock_item&entity_id={item.id}", headers=_auth(owner)
            )
        ).json()
        by_actor = (
            await api_client.get(
                f"{STAFF}/audit?actor_employee_id={actor.employee_id}", headers=_auth(owner)
            )
        ).json()

        assert [row["action"] for row in by_entity["items"]] == ["stock_item.repriced"]
        assert len(by_actor["items"]) == 2

    async def test_reading_the_trail_writes_nothing_to_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 5. *Who looked at what* is a different product with a different
        retention story, and recording more is not how DPDP is satisfied."""
        world = await _identity_world(db_session, "owner")
        record(
            db_session,
            await _actor(db_session, world),
            action="order.cancel",
            entity="order",
            entity_id=uuid.uuid4(),
            new={"reason": "guest left"},
        )
        await db_session.commit()
        owner = await _token(api_client, "owner")

        before = (await api_client.get(f"{STAFF}/audit", headers=_auth(owner))).json()
        after = (await api_client.get(f"{STAFF}/audit", headers=_auth(owner))).json()

        assert len(before["items"]) == len(after["items"]) == 1


class TestTheCentreShowsWhatAPersonCanActOn:
    async def test_an_owner_sees_stock_that_has_gone_negative(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _identity_world(db_session, "owner")
        item = await _stock_item(db_session, world, name="Paneer")
        await _consumed_without_receiving(db_session, world, item, "1400")
        await db_session.commit()
        owner = await _token(api_client, "owner")

        body = (await api_client.get(f"{STAFF}/notifications", headers=_auth(owner))).json()

        negative = next(row for row in body["items"] if row["kind"] == "stock.negative")
        assert negative["severity"] == "critical"
        assert negative["subject"] == "Paneer"
        assert body["unread"] >= 1

    async def test_a_waiter_sees_their_own_task_and_not_the_stock(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Vision §25's rule, and the reason a notification centre survives its first week."""
        world = await _identity_world(db_session, "owner", "waiter")
        item = await _stock_item(db_session, world, name="Paneer")
        await _consumed_without_receiving(db_session, world, item, "1400")
        waiter = await _employee(db_session, world, "waiter")
        await _overdue_task(db_session, world, assigned_to=waiter.id)
        await db_session.commit()
        token = await _token(api_client, "waiter")

        body = (await api_client.get(f"{STAFF}/notifications", headers=_auth(token))).json()

        kinds = {row["kind"] for row in body["items"]}
        assert kinds == {"task.overdue"}

    async def test_nothing_true_is_an_empty_centre(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 6. An empty centre is the *right* answer when nothing is wrong,
        which is exactly why it must be derived: a table filled by a job that is not running looks
        identical to this and means the opposite."""
        await _identity_world(db_session, "owner")
        await db_session.commit()
        owner = await _token(api_client, "owner")

        body = (await api_client.get(f"{STAFF}/notifications", headers=_auth(owner))).json()

        assert body["items"] == []
        assert body["unread"] == 0


class TestReadingAndDismissing:
    async def test_dismissing_one_condition_does_not_dismiss_another_of_the_same_kind(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 7, and the reason `condition_key` names *this* condition rather
        than its kind."""
        world = await _identity_world(db_session, "owner")
        paneer = await _stock_item(db_session, world, name="Paneer")
        ghee = await _stock_item(db_session, world, name="Ghee")
        await _consumed_without_receiving(db_session, world, paneer, "1400")
        await _consumed_without_receiving(db_session, world, ghee, "500")
        await db_session.commit()
        owner = await _token(api_client, "owner")

        marked = await api_client.post(
            f"{STAFF}/notifications/read",
            headers=_auth(owner),
            json={"key": f"stock.negative:{paneer.id}", "dismissed": True},
        )
        assert marked.status_code == 204, marked.text

        body = (await api_client.get(f"{STAFF}/notifications", headers=_auth(owner))).json()

        subjects = {row["subject"] for row in body["items"]}
        assert subjects == {"Ghee"}

    async def test_reading_something_twice_is_one_act(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Two taps on a phone in a basement. Without the upsert the second writes a second row
        and the unread count never reaches zero."""
        world = await _identity_world(db_session, "owner")
        item = await _stock_item(db_session, world, name="Paneer")
        await _consumed_without_receiving(db_session, world, item, "1400")
        await db_session.commit()
        owner = await _token(api_client, "owner")
        payload = {"key": f"stock.negative:{item.id}", "dismissed": False}

        await api_client.post(f"{STAFF}/notifications/read", headers=_auth(owner), json=payload)
        await api_client.post(f"{STAFF}/notifications/read", headers=_auth(owner), json=payload)

        body = (await api_client.get(f"{STAFF}/notifications", headers=_auth(owner))).json()

        assert len(body["items"]) == 1
        assert body["items"][0]["read"] is True
        assert body["unread"] == 0

    async def test_a_key_for_a_condition_that_has_gone_is_accepted(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Deliberate. A condition that resolved between the screen rendering and the tap is
        exactly when somebody taps, and refusing then would make the centre argue with people
        about things that have stopped being true."""
        await _identity_world(db_session, "owner")
        await db_session.commit()
        owner = await _token(api_client, "owner")

        accepted = await api_client.post(
            f"{STAFF}/notifications/read",
            headers=_auth(owner),
            json={"key": f"stock.negative:{uuid.uuid4()}", "dismissed": True},
        )

        assert accepted.status_code == 204, accepted.text
