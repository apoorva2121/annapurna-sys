"""The guarantees migration 0033 makes at the database, not in a service.

Two of these are worth more than the rest.

**`cost_value` is NOT NULL**, which is the schema's half of a rule from `docs/waste-model.md`:
never require the person logging waste to know the cost — the system knows — and show the rupee
value only afterwards, because showing it before suppresses honest reporting. NOT NULL means there
is no shape of this table a "we'll fill the cost in later" code path could use, so the rule cannot
be quietly dropped by a future service method.

**An approval is a person and a time together, or neither.** A row claiming to be approved by
nobody, or at no time, is a row nobody can audit — and approval is the control standing between an
expensive reason code and somebody logging theft as waste.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import WastageStage
from app.models.identity import Employee
from app.models.waste import WastageEvent, WastageReason
from tests.test_inventory_schema import _item, _restaurant

_TODAY = date(2026, 9, 16)


async def _reason(
    session: AsyncSession, restaurant_id: object, code: str = "EXPIRED", **overrides: object
) -> WastageReason:
    fields: dict[str, object] = {
        "restaurant_id": restaurant_id,
        "code": code,
        "name": code.title(),
        "stage": WastageStage.STORAGE,
    }
    fields.update(overrides)
    reason = WastageReason(**fields)
    session.add(reason)
    await session.flush()
    return reason


async def _reporter(session: AsyncSession, organization_id: object) -> Employee:
    """Somebody to have thrown it away.

    Created here rather than looked up: the first version of this file did
    `SELECT id FROM employee LIMIT 1` against a world that has no employees, so `reported_by` was
    null and the NOT NULL fired **first** — masking every constraint these tests exist to check.
    Four of them passed for the wrong reason before the regex in `pytest.raises` gave it away.
    """
    employee = Employee(
        organization_id=organization_id,
        employee_code=f"W{uuid.uuid4().hex[:6].upper()}",
        full_name="Waste Reporter",
        joined_on=date(2026, 1, 1),
    )
    session.add(employee)
    await session.flush()
    return employee


async def _event(
    session: AsyncSession, restaurant_id: object, item_id: object, reason_id: object, **over: object
) -> WastageEvent:
    organization_id = await session.scalar(
        text("SELECT organization_id FROM restaurant WHERE id = :rid"), {"rid": restaurant_id}
    )
    employee_id = (await _reporter(session, organization_id)).id
    fields: dict[str, object] = {
        "restaurant_id": restaurant_id,
        "stock_item_id": item_id,
        "wastage_reason_id": reason_id,
        "quantity": Decimal("250.0000"),
        "cost_value": Decimal("90.00"),
        "occurred_at": datetime.now(UTC),
        "business_date": _TODAY,
        "reported_by": employee_id,
    }
    fields.update(over)
    event = WastageEvent(**fields)
    session.add(event)
    await session.flush()
    return event


class TestAReasonCarriesPolicy:
    async def test_a_stage_outside_the_four_is_refused(self, db_session: AsyncSession) -> None:
        """The four stages are the module. A fifth invented at a call site would produce a report
        that silently does not add up."""
        restaurant = await _restaurant(db_session, "wastestage")

        db_session.add(
            WastageReason(
                restaurant_id=restaurant.id, code="MYSTERY", name="Mystery", stage="somewhere"
            )
        )
        with pytest.raises(IntegrityError, match="ck_wastage_reason_stage"):
            await db_session.flush()

    async def test_a_code_is_unique_per_restaurant_but_not_across_them(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _restaurant(db_session, "wastecodeone")
        theirs = await _restaurant(db_session, "wastecodetwo")

        await _reason(db_session, mine.id, "EXPIRED")
        # The same code at another restaurant is a different reason and must be allowed.
        await _reason(db_session, theirs.id, "EXPIRED")

        db_session.add(
            WastageReason(
                restaurant_id=mine.id,
                code="EXPIRED",
                name="Expired again",
                stage=WastageStage.STORAGE,
            )
        )
        with pytest.raises(IntegrityError, match="uq_wastage_reason_code"):
            await db_session.flush()


class TestTheCostIsNeverOptional:
    async def test_an_event_cannot_be_written_without_a_cost(
        self, db_session: AsyncSession
    ) -> None:
        """The schema's half of "never ask the person logging what it cost".

        A nullable column would let a future path write the event now and the cost later, and
        "later" is where a waste report quietly becomes a count of incidents rather than a number
        of rupees.
        """
        restaurant = await _restaurant(db_session, "wastecost")
        item = await _item(db_session, restaurant, "PANEER")
        reason = await _reason(db_session, restaurant.id)
        employee_id = (await _reporter(db_session, restaurant.organization_id)).id

        db_session.add(
            WastageEvent(
                restaurant_id=restaurant.id,
                stock_item_id=item.id,
                wastage_reason_id=reason.id,
                quantity=Decimal("250.0000"),
                cost_value=None,
                occurred_at=datetime.now(UTC),
                business_date=_TODAY,
                reported_by=employee_id,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_negative_cost_is_refused(self, db_session: AsyncSession) -> None:
        restaurant = await _restaurant(db_session, "wastenegcost")
        item = await _item(db_session, restaurant, "PANEER")
        reason = await _reason(db_session, restaurant.id)

        with pytest.raises(IntegrityError, match="ck_wastage_event_cost_not_negative"):
            await _event(db_session, restaurant.id, item.id, reason.id, cost_value=Decimal("-1.00"))

    async def test_wasting_nothing_is_refused(self, db_session: AsyncSession) -> None:
        """A zero-quantity event is a tap somebody did not mean, and it would sit in the report
        as a reason with no weight behind it."""
        restaurant = await _restaurant(db_session, "wastezero")
        item = await _item(db_session, restaurant, "PANEER")
        reason = await _reason(db_session, restaurant.id)

        with pytest.raises(IntegrityError, match="ck_wastage_event_quantity"):
            await _event(db_session, restaurant.id, item.id, reason.id, quantity=Decimal("0"))


class TestAnApprovalIsAPersonAndATime:
    async def test_an_approver_without_a_time_is_refused(self, db_session: AsyncSession) -> None:
        restaurant = await _restaurant(db_session, "wasteapprove")
        item = await _item(db_session, restaurant, "PANEER")
        reason = await _reason(db_session, restaurant.id, requires_approval=True)
        employee_id = (await _reporter(db_session, restaurant.organization_id)).id

        with pytest.raises(IntegrityError, match="ck_wastage_event_approval_pair"):
            await _event(db_session, restaurant.id, item.id, reason.id, approved_by=employee_id)

    async def test_a_time_without_an_approver_is_refused(self, db_session: AsyncSession) -> None:
        restaurant = await _restaurant(db_session, "wasteapprovetwo")
        item = await _item(db_session, restaurant, "PANEER")
        reason = await _reason(db_session, restaurant.id, requires_approval=True)

        with pytest.raises(IntegrityError, match="ck_wastage_event_approval_pair"):
            await _event(
                db_session, restaurant.id, item.id, reason.id, approved_at=datetime.now(UTC)
            )


class TestTenantScoping:
    async def test_an_event_cannot_reference_another_restaurants_reason(
        self, db_session: AsyncSession
    ) -> None:
        """Invariant 1, held by a composite foreign key rather than by a repository remembering.

        It matters more here than it looks: a reason carries the *stage*, so borrowing another
        restaurant's reason would file this restaurant's waste under a stage its own reports never
        configured.
        """
        mine = await _restaurant(db_session, "wastetenantone")
        theirs = await _restaurant(db_session, "wastetenanttwo")
        my_item = await _item(db_session, mine, "PANEER")
        their_reason = await _reason(db_session, theirs.id)

        with pytest.raises(IntegrityError, match="fk_wastage_event_reason_tenant"):
            await _event(db_session, mine.id, my_item.id, their_reason.id)

    async def test_an_event_cannot_reference_another_restaurants_stock_item(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _restaurant(db_session, "wasteitemone")
        theirs = await _restaurant(db_session, "wasteitemtwo")
        their_item = await _item(db_session, theirs, "PANEER")
        my_reason = await _reason(db_session, mine.id)

        with pytest.raises(IntegrityError, match="fk_wastage_event_item_tenant"):
            await _event(db_session, mine.id, their_item.id, my_reason.id)


async def test_the_models_and_the_migration_agree(db_session: AsyncSession) -> None:
    """Every mapped column selected once — the cheapest way to ask whether a model column exists
    in the table the migration actually created."""
    for model in (WastageReason, WastageEvent):
        await db_session.execute(select(model).limit(1))


async def test_the_shift_reference_is_a_bare_column(db_session: AsyncSession) -> None:
    """`shift` is M12's table, so `shift_id` carries no foreign key yet — the same shape
    `cash_session.shift_id` has had since M07.

    Asserted rather than assumed, because the day M12 lands somebody has to remember to add the
    constraint, and a test naming the gap is how they find out.
    """
    constraints = await db_session.execute(
        text(
            "SELECT 1 FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "WHERE tc.table_name = 'wastage_event' AND tc.constraint_type = 'FOREIGN KEY' "
            "  AND kcu.column_name = 'shift_id'"
        )
    )
    assert constraints.first() is None, (
        "wastage_event.shift_id has a foreign key now — if M12 has landed, delete this test and "
        "keep the constraint; if it has not, something added a reference to a table that does not "
        "exist yet."
    )
