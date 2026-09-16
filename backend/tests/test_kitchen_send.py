"""Sending an order puts paper on the right rails — `OrderService.send` meeting M08.

The behaviour these assert is spec decision 1, which is the decision the whole module rests on: a
KOT is a **round**, not an order. Everything else here follows from it. A second send is a second
ticket; the first ticket does not move; and each ticket carries the standard for its own slowest
dish, frozen, so a menu edited next month cannot make last night's kitchen look late.

They go through the service rather than the HTTP layer because what is under test is the
transaction — tickets and order lines change together or not at all, and a route test would pass
just as well against two commits.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import OrderLineStatus, OrderStatus, OrderType
from app.core.errors import ConflictError
from app.core.tenancy import TenantScope
from app.models.kitchen import KotTicket
from app.models.menu import MenuCategory, MenuItem, MenuItemVariant
from app.models.orders import Order, OrderLine
from app.models.setup import Station
from app.repositories.kitchen import KitchenRepository
from app.services.kitchen import KitchenService
from tests.helpers.queries import count_queries
from tests.test_orders_schema import _World
from tests.test_orders_schema import _world as _order_world

_TODAY = date(2026, 9, 16)


def _scope(world: _World) -> TenantScope:
    return TenantScope(
        organization_id=world.restaurant.organization_id, restaurant_id=world.restaurant.id
    )


async def _order(session: AsyncSession, world: _World, number: str = "1") -> Order:
    order = Order(
        restaurant_id=world.restaurant.id,
        order_number=number,
        type=OrderType.DINE_IN,
        status=OrderStatus.OPEN,
        business_date=_TODAY,
        placed_at=datetime.now(UTC),
    )
    session.add(order)
    await session.flush()
    return order


async def _second_dish(
    session: AsyncSession, world: _World, *, station_code: str, prep_minutes: int
) -> MenuItemVariant:
    """A dish at its own station, so a send has two rails to split across."""
    station = Station(
        restaurant_id=world.restaurant.id, code=station_code, name=station_code.title(), seq=1
    )
    category_id = await session.scalar(
        select(MenuCategory.id).where(MenuCategory.restaurant_id == world.restaurant.id)
    )
    session.add(station)
    await session.flush()
    item = MenuItem(
        restaurant_id=world.restaurant.id,
        menu_category_id=category_id,
        code=f"DISH_{station_code}",
        name=f"{station_code.title()} Special",
        food_type="veg",
        station_id=station.id,
        seq=1,
        is_active=True,
    )
    session.add(item)
    await session.flush()
    variant = MenuItemVariant(
        restaurant_id=world.restaurant.id,
        menu_item_id=item.id,
        code="FULL",
        name="Full",
        price=Decimal("250.00"),
        tax_group_id=world.tax_group.id,
        prep_minutes=prep_minutes,
        seq=0,
        is_active=True,
    )
    session.add(variant)
    await session.flush()
    return variant


async def _line(
    session: AsyncSession,
    world: _World,
    order: Order,
    variant: MenuItemVariant | None = None,
    **overrides: Any,
) -> OrderLine:
    values: dict[str, Any] = {
        "restaurant_id": world.restaurant.id,
        "order_id": order.id,
        "menu_item_variant_id": (variant or world.variant).id,
        "quantity": 1,
        "unit_price": Decimal("470.00"),
        "line_subtotal": Decimal("470.00"),
        "tax_group_id": world.tax_group.id,
        "tax_regime": "gst",
        "tax_rate": Decimal("0.0500"),
        "taxable_value": Decimal("470.00"),
        "cgst_amount": Decimal("11.75"),
        "sgst_amount": Decimal("11.75"),
        "tax_amount": Decimal("23.50"),
        "line_total": Decimal("493.50"),
        "status": OrderLineStatus.PENDING,
    }
    line = OrderLine(**(values | overrides))
    session.add(line)
    await session.flush()
    return line


async def _tickets(session: AsyncSession, order: Order) -> list[KotTicket]:
    """Lines eager-loaded: the relationship is `lazy="raise"` on purpose, so a caller that wants
    them says so and an N+1 cannot appear by accident."""
    result = await session.scalars(
        select(KotTicket)
        .options(selectinload(KotTicket.lines))
        .where(KotTicket.order_id == order.id)
        .order_by(KotTicket.ticket_number)
    )
    return list(result.all())


class TestOneTicketPerStation:
    async def test_a_send_raises_one_ticket_for_each_station_it_touches(
        self, db_session: AsyncSession
    ) -> None:
        world = await _order_world(db_session, "sendone")
        order = await _order(db_session, world)
        tandoor = await _second_dish(db_session, world, station_code="TANDOOR", prep_minutes=9)
        first = await _line(db_session, world, order)
        second = await _line(db_session, world, order, tandoor, seq=1)

        service = KitchenService(db_session, _scope(world))
        raised = await service.raise_tickets(order, [first, second])

        assert len(raised) == 2
        # Two different rails, and each carries only its own dish. A ticket at the wrong station is
        # food nobody cooks, which is the whole failure this routing exists to avoid.
        assert len({ticket.station_id for ticket in raised}) == 2
        assert sorted(len(ticket.lines) for ticket in raised) == [1, 1]
        assert {ticket.station_id for ticket in raised} == {
            await _station_of(db_session, first),
            await _station_of(db_session, second),
        }

    async def test_dishes_for_one_station_share_a_ticket(self, db_session: AsyncSession) -> None:
        """Two dishes off the same pass are one piece of paper, not two."""
        world = await _order_world(db_session, "sendtwo")
        order = await _order(db_session, world)
        first = await _line(db_session, world, order)
        second = await _line(db_session, world, order, seq=1)

        service = KitchenService(db_session, _scope(world))
        raised = await service.raise_tickets(order, [first, second])

        assert len(raised) == 1
        assert len(raised[0].lines) == 2


class TestASecondSendIsASecondTicket:
    async def test_the_second_round_gets_its_own_ticket(self, db_session: AsyncSession) -> None:
        world = await _order_world(db_session, "roundsone")
        order = await _order(db_session, world)
        starters = await _line(db_session, world, order)

        service = KitchenService(db_session, _scope(world))
        await service.raise_tickets(order, [starters])
        mains = await _line(db_session, world, order, seq=1)
        await service.raise_tickets(order, [mains])

        raised = await _tickets(db_session, order)
        assert [ticket.sequence_in_order for ticket in raised] == [1, 2]
        assert [len(ticket.lines) for ticket in raised] == [1, 1]

    async def test_the_first_ticket_does_not_move_when_the_second_is_raised(
        self, db_session: AsyncSession
    ) -> None:
        """The reason the sketch's "one per order per station" had to go.

        Appending to the first ticket would have to drag a `ready` one back to `new`, and the
        `ready_at` it destroys is what M13's prep times and M17's fairness scores are built from.
        """
        world = await _order_world(db_session, "roundstwo")
        order = await _order(db_session, world)
        starters = await _line(db_session, world, order)

        service = KitchenService(db_session, _scope(world))
        [first] = await service.raise_tickets(order, [starters])
        printed_at, number, lines = first.printed_at, first.ticket_number, len(first.lines)

        mains = await _line(db_session, world, order, seq=1)
        await service.raise_tickets(order, [mains])
        await db_session.refresh(first, ["lines"])

        assert first.printed_at == printed_at
        assert first.ticket_number == number
        assert len(first.lines) == lines


class TestTheTicketSaysWhatToCook:
    async def test_the_dish_name_is_copied_rather_than_joined(
        self, db_session: AsyncSession
    ) -> None:
        """A KOT is a printed instruction. Renaming the dish next week must not rewrite it, and a
        withdrawn dish must still read correctly on last night's ticket."""
        world = await _order_world(db_session, "namesone")
        order = await _order(db_session, world)
        line = await _line(db_session, world, order)

        service = KitchenService(db_session, _scope(world))
        [ticket] = await service.raise_tickets(order, [line])
        assert ticket.lines[0].item_name == "Butter Chicken"
        assert ticket.lines[0].variant_name == "Full"

        variant = await db_session.get(MenuItemVariant, line.menu_item_variant_id)
        assert variant is not None
        item = await db_session.get(MenuItem, variant.menu_item_id)
        assert item is not None
        item.name = "Murgh Makhani"
        await db_session.flush()
        await db_session.refresh(ticket, ["lines"])

        assert ticket.lines[0].item_name == "Butter Chicken"

    async def test_special_instructions_travel_to_the_kitchen(
        self, db_session: AsyncSession
    ) -> None:
        """The field most likely to send a dish back if it is dropped on the way."""
        world = await _order_world(db_session, "namestwo")
        order = await _order(db_session, world)
        line = await _line(db_session, world, order, special_instructions="No chilli, allergy")

        service = KitchenService(db_session, _scope(world))
        [ticket] = await service.raise_tickets(order, [line])

        assert ticket.lines[0].special_instructions == "No chilli, allergy"


class TestTheStandardIsFrozen:
    async def test_the_target_is_the_slowest_dish_not_the_sum(
        self, db_session: AsyncSession
    ) -> None:
        """A station cooks a round in parallel. Summing would declare every four-dish ticket late
        on arrival, and a display that is always red is a display nobody reads."""
        world = await _order_world(db_session, "targetone")
        order = await _order(db_session, world)
        first = await _line(db_session, world, order)
        second = await _line(db_session, world, order, seq=1)

        service = KitchenService(db_session, _scope(world))
        [ticket] = await service.raise_tickets(order, [first, second])

        variant = await db_session.get(MenuItemVariant, first.menu_item_variant_id)
        assert variant is not None
        assert ticket.target_minutes == variant.prep_minutes

    async def test_repricing_the_menus_prep_time_does_not_move_a_printed_ticket(
        self, db_session: AsyncSession
    ) -> None:
        world = await _order_world(db_session, "targettwo")
        order = await _order(db_session, world)
        line = await _line(db_session, world, order)

        service = KitchenService(db_session, _scope(world))
        [ticket] = await service.raise_tickets(order, [line])
        before = ticket.target_minutes

        variant = await db_session.get(MenuItemVariant, line.menu_item_variant_id)
        assert variant is not None
        variant.prep_minutes = before + 30
        await db_session.flush()
        await db_session.refresh(ticket)

        assert ticket.target_minutes == before


class TestNumberingAndTheCursor:
    async def test_ticket_numbers_count_from_one_each_business_day(
        self, db_session: AsyncSession
    ) -> None:
        world = await _order_world(db_session, "numberone")
        order = await _order(db_session, world)
        tandoor = await _second_dish(db_session, world, station_code="TANDOOR", prep_minutes=9)
        first = await _line(db_session, world, order)
        second = await _line(db_session, world, order, tandoor, seq=1)

        service = KitchenService(db_session, _scope(world))
        raised = await service.raise_tickets(order, [first, second])

        assert sorted(ticket.ticket_number for ticket in raised) == ["1", "2"]

    async def test_one_send_is_one_revision_however_many_rails_it_reaches(
        self, db_session: AsyncSession
    ) -> None:
        """A send is one kitchen event. Giving each ticket its own revision would make a client
        that reconnects mid-batch replay half of it, which is the failure the inclusive cursor
        exists to prevent — cheaper to make the batch atomic in the first place."""
        world = await _order_world(db_session, "revisionone")
        order = await _order(db_session, world)
        tandoor = await _second_dish(db_session, world, station_code="TANDOOR", prep_minutes=9)
        first = await _line(db_session, world, order)
        second = await _line(db_session, world, order, tandoor, seq=1)

        service = KitchenService(db_session, _scope(world))
        raised = await service.raise_tickets(order, [first, second])

        assert len({ticket.revision for ticket in raised}) == 1

    async def test_a_later_send_has_a_higher_revision(self, db_session: AsyncSession) -> None:
        world = await _order_world(db_session, "revisiontwo")
        order = await _order(db_session, world)
        starters = await _line(db_session, world, order)

        service = KitchenService(db_session, _scope(world))
        [first] = await service.raise_tickets(order, [starters])
        mains = await _line(db_session, world, order, seq=1)
        [second] = await service.raise_tickets(order, [mains])

        assert second.revision > first.revision


class TestTheSendCostsTheSameWhateverWasOrdered:
    async def test_routing_does_not_grow_with_the_number_of_dishes(
        self, db_session: AsyncSession
    ) -> None:
        """The shape an N+1 cannot satisfy, on the hot path of the busiest screen in the restaurant.

        A dish's station and standard prep time live two joins away on `menu_item` and
        `menu_item_variant`, and its options a third. Asked per line, a six-dish order would be
        eighteen statements at the exact moment a waiter is standing at a table waiting.

        Counted against `routing_for` rather than the whole send: ticket numbering takes an
        advisory lock per ticket by design, so the send's total legitimately grows with the number
        of *stations*. What must not grow with the number of dishes is this.
        """
        world = await _order_world(db_session, "countone")
        order = await _order(db_session, world)
        one = await _line(db_session, world, order)
        engine = db_session.get_bind().engine
        repository = KitchenRepository(db_session, _scope(world))

        with count_queries(engine) as few:
            await repository.routing_for([one.id])

        many = [one]
        for index in range(1, 6):
            many.append(await _line(db_session, world, order, seq=index))
        with count_queries(engine) as lots:
            await repository.routing_for([line.id for line in many])

        assert lots.count == few.count
        # And the number itself is the two the repository's docstring claims: the lines, then
        # their options.
        assert few.count == 2


class TestTenantIsolation:
    async def test_a_line_from_another_restaurant_routes_nowhere(
        self, db_session: AsyncSession
    ) -> None:
        """`routing_for` is scoped, so another restaurant's line resolves to nothing and the send
        is refused rather than silently dropping a dish onto this restaurant's rail."""
        mine = await _order_world(db_session, "isolationone")
        theirs = await _order_world(db_session, "isolationtwo")
        my_order = await _order(db_session, mine)
        their_order = await _order(db_session, theirs)
        their_line = await _line(db_session, theirs, their_order)

        service = KitchenService(db_session, _scope(mine))
        with pytest.raises(ConflictError) as raised:
            await service.raise_tickets(my_order, [their_line])
        assert raised.value.code == "kot.unroutable"


async def _station_of(session: AsyncSession, line: OrderLine) -> uuid.UUID:
    """Where the menu says this line's dish is cooked — the answer a ticket snapshots."""
    station_id = await session.scalar(
        select(MenuItem.station_id)
        .join(MenuItemVariant, MenuItemVariant.menu_item_id == MenuItem.id)
        .where(MenuItemVariant.id == line.menu_item_variant_id)
    )
    assert station_id is not None
    return station_id
