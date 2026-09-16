"""The guarantees migration 0030 makes at the database, not in a service.

The kitchen is the one module whose rows a service edits continuously for the whole time a dish is
being cooked, so it takes no append-only trigger. That makes these constraints the floor: whatever
`KitchenService` does or forgets, a ticket can never carry a `ready_at` with no `started_at`, a
remake can never exist without a reason, and a ticket can never point at another restaurant's order.

Every one of them is asserted against a real Postgres rather than against a repository's good
intentions. The timestamp ones matter longest: `ready_at - printed_at` is the entire
kitchen-performance story, and a ticket whose clock ran backwards is a question nobody can answer
in two years' time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import KotLineStatus, KotTicketStatus, OrderStatus, OrderType
from app.models.kitchen import KotStreamCursor, KotTicket, KotTicketLine
from app.models.orders import Order, OrderLine
from app.models.setup import Station
from app.models.tenancy import Organization, Restaurant
from tests.test_orders_schema import _saved_line as _saved_order_line
from tests.test_orders_schema import _World
from tests.test_orders_schema import _world as _order_world

_TODAY = date(2026, 9, 16)


async def _restaurant(session: AsyncSession, slug: str) -> Restaurant:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id, name=slug.title(), code=slug[:2].upper()
    )
    session.add(restaurant)
    await session.flush()
    return restaurant


async def _station(session: AsyncSession, restaurant: Restaurant, code: str = "TANDOOR") -> Station:
    station = Station(restaurant_id=restaurant.id, code=code, name=code.title(), seq=1)
    session.add(station)
    await session.flush()
    return station


async def _order(session: AsyncSession, restaurant: Restaurant, number: str = "1") -> Order:
    order = Order(
        restaurant_id=restaurant.id,
        order_number=number,
        type=OrderType.DINE_IN,
        status=OrderStatus.OPEN,
        business_date=_TODAY,
        placed_at=datetime.now(UTC),
    )
    session.add(order)
    await session.flush()
    return order


def _ticket(
    restaurant: Restaurant, order: Order, station: Station, **overrides: object
) -> KotTicket:
    fields: dict[str, object] = {
        "restaurant_id": restaurant.id,
        "order_id": order.id,
        "station_id": station.id,
        "ticket_number": "1",
        "sequence_in_order": 1,
        "status": KotTicketStatus.NEW,
        "target_minutes": 12,
        "business_date": _TODAY,
        "revision": 1,
        "printed_at": datetime.now(UTC),
    }
    fields.update(overrides)
    return KotTicket(**fields)


class TestTheClockOnlyRunsForwards:
    """A prep time is derived from these columns years after whoever wrote the bug has gone.

    A service can be fixed; a row that was written with `ready_at` and no `started_at` cannot be
    repaired from anything, because nothing else in the database knows when the dish went in a pan.
    """

    async def test_a_ticket_cannot_be_ready_without_having_started(
        self, db_session: AsyncSession
    ) -> None:
        restaurant = await _restaurant(db_session, "clockone")
        order = await _order(db_session, restaurant)
        station = await _station(db_session, restaurant)
        now = datetime.now(UTC)

        db_session.add(
            _ticket(
                restaurant,
                order,
                station,
                acknowledged_at=now,
                ready_at=now,
                status=KotTicketStatus.READY,
            )
        )
        with pytest.raises(IntegrityError, match="ck_kot_ticket_ready_order"):
            await db_session.flush()

    async def test_a_ticket_cannot_start_without_being_acknowledged(
        self, db_session: AsyncSession
    ) -> None:
        restaurant = await _restaurant(db_session, "clocktwo")
        order = await _order(db_session, restaurant)
        station = await _station(db_session, restaurant)

        db_session.add(
            _ticket(
                restaurant,
                order,
                station,
                started_at=datetime.now(UTC),
                status=KotTicketStatus.PREPARING,
            )
        )
        with pytest.raises(IntegrityError, match="ck_kot_ticket_started_order"):
            await db_session.flush()

    async def test_a_ticket_cannot_be_served_without_having_been_ready(
        self, db_session: AsyncSession
    ) -> None:
        """The one a counter-service restaurant would breach first: money is taken before the food
        is cooked, so `served` arrives on a ticket nobody moved through the kitchen."""
        restaurant = await _restaurant(db_session, "clockthree")
        order = await _order(db_session, restaurant)
        station = await _station(db_session, restaurant)
        now = datetime.now(UTC)

        db_session.add(
            _ticket(
                restaurant,
                order,
                station,
                acknowledged_at=now,
                started_at=now,
                served_at=now,
                status=KotTicketStatus.SERVED,
            )
        )
        with pytest.raises(IntegrityError, match="ck_kot_ticket_served_order"):
            await db_session.flush()

    async def test_a_cancelled_ticket_is_not_forced_through_the_sequence(
        self, db_session: AsyncSession
    ) -> None:
        """Cancellation is exempt by construction — the constraints say nothing about `status` —
        and that is deliberate: an order cancelled before anybody looked at the rail must still be
        cancellable."""
        restaurant = await _restaurant(db_session, "clockfour")
        order = await _order(db_session, restaurant)
        station = await _station(db_session, restaurant)

        db_session.add(
            _ticket(
                restaurant,
                order,
                station,
                status=KotTicketStatus.CANCELLED,
                cancelled_at=datetime.now(UTC),
            )
        )
        await db_session.flush()


class TestTenantScoping:
    """Invariant 1, held by composite foreign keys rather than by a repository remembering."""

    async def test_a_ticket_cannot_reference_another_restaurants_order(
        self, db_session: AsyncSession
    ) -> None:
        mine = await _restaurant(db_session, "tenantone")
        theirs = await _restaurant(db_session, "tenanttwo")
        their_order = await _order(db_session, theirs)
        my_station = await _station(db_session, mine)

        db_session.add(_ticket(mine, their_order, my_station))
        with pytest.raises(IntegrityError, match="fk_kot_ticket_order_tenant"):
            await db_session.flush()

    async def test_a_ticket_cannot_reference_another_restaurants_station(
        self, db_session: AsyncSession
    ) -> None:
        """The constraint migration 0030 had to add `UNIQUE (id, restaurant_id)` to `station` for.
        Without that target there is no composite key, and routing a dish to another restaurant's
        tandoor would be refused by nothing."""
        mine = await _restaurant(db_session, "tenantthree")
        theirs = await _restaurant(db_session, "tenantfour")
        my_order = await _order(db_session, mine)
        their_station = await _station(db_session, theirs)

        db_session.add(_ticket(mine, my_order, their_station))
        with pytest.raises(IntegrityError, match="fk_kot_ticket_station_tenant"):
            await db_session.flush()


class TestATicketIsARound:
    async def test_a_station_cannot_have_two_tickets_of_the_same_round_for_one_order(
        self, db_session: AsyncSession
    ) -> None:
        """A second send is round 2. Two rows both claiming to be round 1 would make
        `sequence_in_order` meaningless and the rail ambiguous about what was ordered when."""
        restaurant = await _restaurant(db_session, "roundone")
        order = await _order(db_session, restaurant)
        station = await _station(db_session, restaurant)

        db_session.add(_ticket(restaurant, order, station))
        await db_session.flush()
        db_session.add(_ticket(restaurant, order, station, ticket_number="2"))
        with pytest.raises(IntegrityError, match="uq_kot_ticket_round"):
            await db_session.flush()

    async def test_a_second_round_at_the_same_station_is_allowed(
        self, db_session: AsyncSession
    ) -> None:
        """The decision this module is built on: starters then mains is two tickets, not one
        ticket edited twice."""
        restaurant = await _restaurant(db_session, "roundtwo")
        order = await _order(db_session, restaurant)
        station = await _station(db_session, restaurant)

        db_session.add(_ticket(restaurant, order, station))
        await db_session.flush()
        db_session.add(_ticket(restaurant, order, station, ticket_number="2", sequence_in_order=2))
        await db_session.flush()

    async def test_a_ticket_number_is_unique_per_restaurant_per_business_day(
        self, db_session: AsyncSession
    ) -> None:
        restaurant = await _restaurant(db_session, "numberone")
        first = await _order(db_session, restaurant, "1")
        second = await _order(db_session, restaurant, "2")
        station = await _station(db_session, restaurant)

        db_session.add(_ticket(restaurant, first, station, ticket_number="7"))
        await db_session.flush()
        db_session.add(_ticket(restaurant, second, station, ticket_number="7"))
        with pytest.raises(IntegrityError, match="uq_kot_ticket_number_per_day"):
            await db_session.flush()

    async def test_yesterdays_ticket_number_comes_round_again_tomorrow(
        self, db_session: AsyncSession
    ) -> None:
        """Counting restarts each business day, like `order.order_number`, because "ticket seven"
        is something a person says out loud."""
        restaurant = await _restaurant(db_session, "numbertwo")
        first = await _order(db_session, restaurant, "1")
        second = await _order(db_session, restaurant, "2")
        station = await _station(db_session, restaurant)

        db_session.add(_ticket(restaurant, first, station, ticket_number="7"))
        await db_session.flush()
        db_session.add(
            _ticket(
                restaurant,
                second,
                station,
                ticket_number="7",
                business_date=date(2026, 9, 17),
                sequence_in_order=2,
            )
        )
        await db_session.flush()


class TestALineSaysWhatToCook:
    """These need a real `order_line`, so they borrow M07's world rather than building a second
    one — the same way `test_orders_schema` borrows its restaurant from
    `test_procurement_schema`."""

    async def _ticket_on_an_order(
        self, session: AsyncSession, slug: str
    ) -> tuple[_World, KotTicket, OrderLine]:
        world = await _order_world(session, slug)
        order = Order(
            restaurant_id=world.restaurant.id,
            order_number="1",
            type=OrderType.DINE_IN,
            status=OrderStatus.OPEN,
            business_date=_TODAY,
            placed_at=datetime.now(UTC),
        )
        session.add(order)
        await session.flush()
        line = await _saved_order_line(session, world, order)
        station = await _station(session, world.restaurant, code="TANDOOR2")
        ticket = _ticket(world.restaurant, order, station)
        session.add(ticket)
        await session.flush()
        return world, ticket, line

    async def test_a_remake_without_a_reason_is_refused(self, db_session: AsyncSession) -> None:
        """A remake is how a kitchen learns. One with no reason recorded teaches nobody anything,
        and the column would fill with nulls within a week of the first busy Saturday."""
        world, ticket, line = await self._ticket_on_an_order(db_session, "remakeone")

        db_session.add(
            KotTicketLine(
                restaurant_id=world.restaurant.id,
                kot_ticket_id=ticket.id,
                order_line_id=line.id,
                quantity=1,
                item_name="Butter Chicken",
                variant_name="Full",
                status=KotLineStatus.REMAKE,
            )
        )
        with pytest.raises(IntegrityError, match="ck_kot_ticket_line_remake_reason"):
            await db_session.flush()

    async def test_a_dish_appears_at_most_once_on_a_ticket(self, db_session: AsyncSession) -> None:
        """A second helping is a second order line, which is how M07 already models it. Two rows
        for one line would double the quantity the kitchen cooks."""
        world, ticket, line = await self._ticket_on_an_order(db_session, "onceone")
        for _ in range(2):
            db_session.add(
                KotTicketLine(
                    restaurant_id=world.restaurant.id,
                    kot_ticket_id=ticket.id,
                    order_line_id=line.id,
                    quantity=1,
                    item_name="Butter Chicken",
                    variant_name="Full",
                    status=KotLineStatus.PENDING,
                )
            )
        with pytest.raises(IntegrityError, match="uq_kot_ticket_line_once_per_ticket"):
            await db_session.flush()

    async def test_a_line_cannot_be_served_without_having_been_ready(
        self, db_session: AsyncSession
    ) -> None:
        """S2's timestamps carry the same rule as the ticket's. Per-dish prep time is the thing
        they exist for, and a dish served before it was ready has no prep time."""
        world, ticket, line = await self._ticket_on_an_order(db_session, "lineclock")

        db_session.add(
            KotTicketLine(
                restaurant_id=world.restaurant.id,
                kot_ticket_id=ticket.id,
                order_line_id=line.id,
                quantity=1,
                item_name="Butter Chicken",
                variant_name="Full",
                status=KotLineStatus.SERVED,
                served_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError, match="ck_kot_ticket_line_served_order"):
            await db_session.flush()

    async def test_a_line_cannot_reference_another_restaurants_order_line(
        self, db_session: AsyncSession
    ) -> None:
        _, ticket, _ = await self._ticket_on_an_order(db_session, "linetenantone")
        other, _, their_line = await self._ticket_on_an_order(db_session, "linetenanttwo")
        assert other is not None

        db_session.add(
            KotTicketLine(
                restaurant_id=ticket.restaurant_id,
                kot_ticket_id=ticket.id,
                order_line_id=their_line.id,
                quantity=1,
                item_name="Butter Chicken",
                variant_name="Full",
                status=KotLineStatus.PENDING,
            )
        )
        with pytest.raises(IntegrityError, match="fk_kot_ticket_line_order_line_tenant"):
            await db_session.flush()


class TestTheStreamCursor:
    async def test_a_restaurant_has_at_most_one_cursor(self, db_session: AsyncSession) -> None:
        """It is the restaurant's single kitchen revision. Two rows would be two answers to "what
        has happened since?", and a display would follow whichever it read first."""
        restaurant = await _restaurant(db_session, "cursorone")
        db_session.add(KotStreamCursor(restaurant_id=restaurant.id, last_revision=1))
        await db_session.flush()

        db_session.add(KotStreamCursor(restaurant_id=restaurant.id, last_revision=2))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_cursor_never_goes_negative(self, db_session: AsyncSession) -> None:
        restaurant = await _restaurant(db_session, "cursortwo")
        db_session.add(KotStreamCursor(restaurant_id=restaurant.id, last_revision=-1))
        with pytest.raises(IntegrityError, match="ck_kot_stream_cursor_revision"):
            await db_session.flush()


class TestTheKitchenNeverWritesMoney:
    async def test_no_kitchen_table_carries_a_money_column(self, db_session: AsyncSession) -> None:
        """Asserted rather than intended (spec, G-13 item 4).

        The control against a cook clearing a rail of food that never left the pass is that
        clearing it settles nothing. That holds only while the kitchen's tables have nothing
        money-shaped on them to settle *with*, so the absence is a test and not a habit.
        """
        rows = await db_session.execute(
            text(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_name IN ('kot_ticket', 'kot_ticket_line', 'kot_stream_cursor') "
                "AND data_type = 'numeric'"
            )
        )
        found = rows.all()
        assert found == [], f"the kitchen grew a money column: {found}"


async def test_the_models_and_the_migration_agree(db_session: AsyncSession) -> None:
    """A model column the migration never created is a query that fails in a restaurant rather
    than here. Every mapped column is selected once, which is the cheapest way to ask."""
    for model in (KotTicket, KotTicketLine, KotStreamCursor):
        await db_session.execute(select(model).limit(1))
