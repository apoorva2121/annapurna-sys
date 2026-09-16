"""The rail under load — M08 acceptance criterion 14: **under 50 ms with 200 open tickets**.

`docs/ui/conventions.md` puts the kitchen display on a wall tablet read from two metres. A budget
that size is not about the chef's patience; it is about what the screen does while it waits. A rail
that takes half a second to answer flickers every time anything changes, and a flickering kitchen
display gets turned off.

**Where the 50 ms is actually checked, and why it is not checked here.**

The first version of this file asserted the budget as wall-clock time. It passed on its own and
failed inside `make check` at 63 ms — because a timing assertion in a test suite measures the
suite. The same query, on an idle machine, runs in a median of 28 ms (min 24.8, max 36.6 over
seven runs). Nothing was wrong with the query; the test was measuring a loaded laptop and calling
it a latency budget.

`docs/sdlc.md`'s Definition of Done already says where the number belongs — *"latency budgets met
**on staging** with seeded data"* — so asserting it here was putting the right number in the wrong
place. **The 50 ms is therefore NOT verified yet**, and M08's DoD line stays unticked until staging
exists (`docs/checklist.md` still lists cloud accounts as an open blocker).

What this file holds instead is the part that is load-independent and is the actual regression risk:

- **the query count**, flat between two tickets and sixty. A page of 200 that costs three statements
  stays fast when the restaurant gets busier; a page that costs 201 happens to be fast today on an
  empty database and is the defect worth catching;
- **a catastrophe bound** an order of magnitude above the measured median, which catches somebody
  adding a join that makes this ten times slower, and does not fail because CI was busy.
"""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import MAX_PAGE_SIZE
from app.services.kitchen import KitchenService
from tests.helpers.queries import count_queries
from tests.test_kitchen_send import _line, _order, _scope
from tests.test_orders_schema import _world as _order_world

# The product's budget, from `docs/modules.md` and the M08 spec. Recorded here because it is what
# the query is *for*; it is verified on staging, not by this file.
_BUDGET_MS = 50
# Measured on this machine, idle: median 28.4 ms over seven runs, worst 36.6. The bound below is
# roughly eight times the median — far enough above a busy CI box that a red here means the query
# changed, not that the machine was busy, and far enough below a pathological regression to catch
# one. A baseline is measured, never computed (`scripts/audit_guardrails.py` records the same
# lesson about ratchets).
_CATASTROPHE_MS = 250
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


async def test_the_rail_does_not_become_pathologically_slow_with_two_hundred_tickets(
    db_session: AsyncSession,
) -> None:
    """A catastrophe bound, not the product's budget — see the module docstring.

    The median of several runs rather than a single one: one sample on a machine running a test
    suite is a coin toss, and a flaky performance test gets deleted rather than investigated.
    """
    world = await _order_world(db_session, "latencyone")
    await _fill_the_rail(db_session, world, _OPEN_TICKETS)
    service = KitchenService(db_session, _scope(world))

    # Once to warm the connection and the query plan, so what is measured is the query rather than
    # the first statement of the session.
    await service.rail(station_id=None, statuses=None, limit=MAX_PAGE_SIZE)

    runs: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        tickets = await service.rail(station_id=None, statuses=None, limit=MAX_PAGE_SIZE)
        runs.append((time.perf_counter() - started) * 1000)
    runs.sort()
    median_ms = runs[len(runs) // 2]

    assert len(tickets) == MAX_PAGE_SIZE
    assert median_ms < _CATASTROPHE_MS, (
        f"the rail took a median {median_ms:.1f} ms with {_OPEN_TICKETS} open tickets. The "
        f"product's budget is {_BUDGET_MS} ms and is verified on staging; this bound only catches "
        f"a query that has become pathologically slow, so a failure here is a real regression."
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
