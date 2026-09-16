"""The rail under load — M08 acceptance criterion 14: **under 50 ms with 200 open tickets**.

`docs/ui/conventions.md` puts the kitchen display on a wall tablet read from two metres. A budget
that size is not about the chef's patience; it is about what the screen does while it waits. A rail
that takes half a second to answer is a rail that flickers every time anything changes, and a
flickering kitchen display gets turned off.

Two assertions, and the second is the one that will still be true in a year:

- **the wall-clock number**, which proves the budget is met on the machine this was built on;
- **the query count**, which proves it is met for the right reason. A page of 200 tickets that
  costs three statements stays fast when the restaurant gets busier. A page that costs 201 happens
  to be fast today on an empty database and is the defect this whole assertion exists to catch.

The timing one is deliberately generous about the machine and strict about the shape: it seeds two
hundred tickets, which is a genuinely bad Saturday, and still expects the answer inside the budget.
"""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import MAX_PAGE_SIZE
from app.services.kitchen import KitchenService
from tests.helpers.queries import count_queries
from tests.test_kitchen_send import _line, _order, _scope
from tests.test_orders_schema import _world as _order_world

# The budget, from `docs/modules.md` and the M08 spec.
_BUDGET_MS = 50
# A genuinely bad Saturday night, and the number the spec names.
_OPEN_TICKETS = 200


async def _fill_the_rail(
    session: AsyncSession, world: object, tickets: int, *, order_number: str = "1"
) -> None:
    """`tickets` open tickets, each its own round, exactly as a service would produce them."""
    service = KitchenService(session, _scope(world))  # type: ignore[arg-type]
    order = await _order(session, world, order_number)  # type: ignore[arg-type]
    for index in range(tickets):
        line = await _line(session, world, order, seq=index)  # type: ignore[arg-type]
        await service.raise_tickets(order, [line])


async def test_the_rail_answers_inside_its_budget_with_two_hundred_tickets(
    db_session: AsyncSession,
) -> None:
    world = await _order_world(db_session, "latencyone")
    await _fill_the_rail(db_session, world, _OPEN_TICKETS)
    service = KitchenService(db_session, _scope(world))

    # Once to warm the connection and the query plan, so what is measured is the query rather than
    # the first statement of the session.
    await service.rail(station_id=None, statuses=None, limit=MAX_PAGE_SIZE)

    started = time.perf_counter()
    tickets = await service.rail(station_id=None, statuses=None, limit=MAX_PAGE_SIZE)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert len(tickets) == MAX_PAGE_SIZE
    assert elapsed_ms < _BUDGET_MS, (
        f"the rail took {elapsed_ms:.1f} ms with {_OPEN_TICKETS} open tickets, "
        f"against a {_BUDGET_MS} ms budget"
    )


async def test_the_rail_costs_the_same_however_busy_the_kitchen(
    db_session: AsyncSession,
) -> None:
    """The assertion that keeps the one above true.

    A budget met by an empty database and an N+1 is a budget that fails on the first busy night in
    a real restaurant, on the screen where it is most visible. This asserts the *shape* — a page of
    two hundred costs what a page of two costs — which no amount of per-ticket querying can satisfy.
    """
    world = await _order_world(db_session, "latencytwo")
    await _fill_the_rail(db_session, world, 2)
    service = KitchenService(db_session, _scope(world))
    engine = db_session.get_bind().engine

    with count_queries(engine) as quiet:
        await service.rail(station_id=None, statuses=None, limit=MAX_PAGE_SIZE)

    await _fill_the_rail(db_session, world, 60, order_number="2")

    with count_queries(engine) as busy:
        tickets = await service.rail(station_id=None, statuses=None, limit=MAX_PAGE_SIZE)

    assert len(tickets) > 50
    assert busy.count == quiet.count
