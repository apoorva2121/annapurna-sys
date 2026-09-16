"""The event loop keeps running while a password is hashed (P1-9, guardrail G-6).

Argon2 at this configuration — `time_cost=3`, 64 MiB, `parallelism=4` — costs 150 to 300 ms, and
that is the whole point of it. Run on the event loop it is 150 to 300 ms in which the process
serves nobody: every other request waits, and from M08 every open kitchen display stops updating.

The audit found eight call sites on the loop and could not fix them without a module, so G-6 was
*ratcheted* instead — measured, written down, and not allowed to grow — with the note that the debt
would be paid at "measured load or M08". This is M08.

**Why a test and not just a code review.** The old arrangement was a synchronous function plus a
convention that callers wrap it in `asyncio.to_thread`. Exactly one of the five call sites in the
application remembered. A convention with a 20% hit rate is not a control, so the function itself
became the coroutine — and this test asserts the property that change was made for, rather than
asserting the shape of the code that currently delivers it.
"""

from __future__ import annotations

import asyncio

from app.core.security import hash_password, verify_password

# The heartbeat's period, and the floor — **both measured on this machine, never computed.**
#
# The arithmetic says a 90 ms hash divided by a 5 ms sleep is eighteen ticks. The measurement says
# seven, and asking for 1 ms sleeps also says seven: Windows' timer granularity is about 13 ms, so
# the tick rate is set by the platform rather than by the number written here. A floor derived from
# the arithmetic would have been a flaky test on the machine this project is built on.
#
# So the floor is three, which sits between the two things that actually have to be told apart: a
# free loop ticks about seven times during one argon2 run, and a blocked one cannot tick at all —
# the coroutine would run the hash to completion before ever yielding. Roughly a factor of two of
# headroom in both directions.
#
# (`scripts/audit_guardrails.py` records the same lesson in its own comment: a baseline is measured,
# never computed. This is that lesson, applied to a threshold.)
_TICK_SECONDS = 0.005
_MINIMUM_TICKS = 3


async def _count_ticks_during[T](work: asyncio.Future[T] | asyncio.Task[T]) -> int:
    """How many times a trivial coroutine gets to run while `work` is in flight."""
    ticks = 0
    while not work.done():
        ticks += 1
        await asyncio.sleep(_TICK_SECONDS)
    return ticks


async def test_hashing_a_password_leaves_the_event_loop_free() -> None:
    ticks = await _count_ticks_during(asyncio.ensure_future(hash_password("Staging#2026")))
    assert ticks >= _MINIMUM_TICKS, (
        f"the event loop ran {ticks} times during one argon2 hash. It is blocking again: "
        "hash_password must stay on a worker thread (G-6, P1-9)."
    )


async def test_verifying_a_password_leaves_the_event_loop_free() -> None:
    """The one that matters more. A restaurant hashes a password when somebody is hired and
    verifies one every time anybody signs in."""
    stored = await hash_password("Staging#2026")
    ticks = await _count_ticks_during(
        asyncio.ensure_future(verify_password("Staging#2026", stored))
    )
    assert ticks >= _MINIMUM_TICKS, (
        f"the event loop ran {ticks} times during one argon2 verification. It is blocking again."
    )


async def test_several_logins_verify_concurrently_rather_than_in_a_queue() -> None:
    """Four verifications together take appreciably less than four times one.

    The consequence a restaurant notices: a shift change is four people signing in at once, and on
    the event loop that was four sequential argon2 runs with every other request — and every
    kitchen display — waiting behind them.
    """
    stored = await hash_password("Staging#2026")

    loop = asyncio.get_running_loop()
    started = loop.time()
    await verify_password("Staging#2026", stored)
    one = loop.time() - started

    started = loop.time()
    await asyncio.gather(*(verify_password("Staging#2026", stored) for _ in range(4)))
    four = loop.time() - started

    # Not "four times faster": the pool is bounded and argon2 itself uses four lanes, so the gain
    # is real but not linear. Asserting anything sharper would be asserting the machine.
    assert four < one * 4, (
        f"four concurrent verifications took {four:.3f}s against {one:.3f}s for one"
    )
