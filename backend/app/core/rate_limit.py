"""The guest surface's rate limit — declared on the route, the way a permission is.

Every staff route in this product sits behind a password. The guest routes are the first that do
not: they are printed on a table, opened by strangers, on a network nobody controls.
`docs/security.md` asks for "aggressive per-IP and per-token rate limits" and says why the write
side matters more than the read side — "feedback and order endpoints are write-limited to prevent
spam and rating manipulation".

**Why it is a declared dependency and not middleware.** The same reasoning as
`require_permission`: a check inside a handler enforces just as well and is invisible to a test
that walks the routing table. `RATE_LIMIT_MARKER` is what lets suite 5 prove that no guest route
was ever registered without one — which is the failure that actually happens, months later, when
somebody adds a fifth guest endpoint in a hurry.

**What this is not, said plainly so nobody discovers it during an incident.** The counter lives in
this process's memory. Two API containers behind a load balancer give an attacker twice the budget,
and a restart clears every counter. That is acceptable at pilot scale and stops being acceptable at
the second instance; `docs/backlog.md` carries the entry, the fix (a shared store, or the reverse
proxy doing it) and the trigger (the day a second instance is deployed).

It is a *floor*, not the defence. The defences that do not depend on it are structural: a table slug
is 128 bits and cannot be guessed, a bill token is hashed at rest and dies with the order, and a
unique index — not a counter — is what makes one feedback per order true.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

# What suite 5 looks for. Renaming it without updating that suite turns the guarantee off silently.
RATE_LIMIT_MARKER = "__rate_limit__"

_WINDOW_SECONDS = 60.0

# Above this many distinct keys the window is swept. A guest surface sees one key per client IP, so
# this is only ever reached by a distributed burst — which is exactly when unbounded growth would
# turn a rate limit into the outage it was meant to prevent.
_SWEEP_AT = 10_000


@dataclass
class _Window:
    started_at: float
    count: int


_counters: dict[str, _Window] = {}


def _client_ip(request: Request) -> str:
    """The client's address, trusting no header.

    `X-Forwarded-For` is written by whoever is in front of us — and, if nothing is, by the client.
    A limiter that trusts it is a limiter an attacker resets by changing one header. When this
    deploys behind a proxy, the proxy is configured to set the address and this reads it from the
    connection; until then, the connection is all there is.
    """
    client = request.client
    return "unknown" if client is None else client.host


def _sweep(now: float) -> None:
    stale = [key for key, window in _counters.items() if now - window.started_at > _WINDOW_SECONDS]
    for key in stale:
        del _counters[key]


def _consume(key: str, budget: int) -> int | None:
    """Count one request. Returns the seconds to wait when the budget is spent, else None."""
    now = time.monotonic()
    if len(_counters) > _SWEEP_AT:
        _sweep(now)

    window = _counters.get(key)
    if window is None or now - window.started_at > _WINDOW_SECONDS:
        _counters[key] = _Window(started_at=now, count=1)
        return None

    window.count += 1
    if window.count > budget:
        return max(1, int(_WINDOW_SECONDS - (now - window.started_at)) + 1)
    return None


def reset_rate_limits() -> None:
    """Clear every counter. For tests, and for nothing else.

    **`conftest.py` calls this from an autouse fixture, not individual tests.** Module-level state
    shared across a suite is the classic source of a test that passes alone and fails in company,
    and here it fails in a particularly confusing way: the twentieth guest request in a file gets a
    429 that has nothing to do with what that test was asserting. Every guest request in the suite
    comes from the same client address, so without the reset the whole file shares one budget.
    """
    _counters.clear()


def rate_limit(tier: str) -> Callable[..., Awaitable[None]]:
    """Declare and enforce the budget a guest route gets. `tier` is "read" or "write"."""

    async def dependency(request: Request) -> None:
        settings = get_settings()
        budget = (
            settings.guest_write_per_minute if tier == "write" else settings.guest_read_per_minute
        )
        key = f"{tier}:{_client_ip(request)}"
        retry_after = _consume(key, budget)
        if retry_after is None:
            return
        # Logged as a warning because `docs/observability.md` alerts on bursts against the public
        # surface; the address is not in the body, which says only what a person can act on.
        logger.warning("guest.rate_limited", extra={"tier": tier})
        raise AppError(
            "guest.too_many_requests",
            "Too many requests. Please wait a moment and try again.",
            {"retry_after_seconds": retry_after},
            status_code=429,
        )

    setattr(dependency, RATE_LIMIT_MARKER, tier)
    return dependency
