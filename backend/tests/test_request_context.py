"""The request-context middleware, rewritten as pure ASGI because M08 streams (external review M4).

`request_context_middleware` was a `BaseHTTPMiddleware`. That class runs the application in a child
task and hands the response back through a memory stream, which has three consequences this module
cannot live with:

1. **`call_next` returns when the response *starts*, not when it finishes.** For a request/response
   route the difference is microseconds. For M08's `GET /kot/stream`, which stays open for a whole
   service, the access line is written at second zero claiming a duration of nothing, and the real
   end of the request is never logged at all.
2. **The handler's context variables do not reach the access line.** They are set in the child task
   and are gone by the time the middleware writes. The old code worked around this by copying the
   tenant onto `request.state` and reading it back — a workaround that exists only because of the
   middleware class, and that the pure-ASGI version does not need.
3. **The access line had no status code.** A log of every request that cannot say which ones failed
   is an access log with the interesting half missing.

The generic shape of the fix: wrap `send`, remember the status from `http.response.start`, and
write the access line when the last body message goes out. Same task throughout, so a context
variable set inside the handler is still set when the line is written — and is *reset* afterwards
by this middleware, so it cannot leak into the next request.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ActorDep
from tests.helpers.logs import captured_lines
from tests.test_setup_endpoints import _auth, _token, _world

_CHUNK_EVENT = "probe.chunk"
_STARTED_EVENT = "probe.started"
_STREAM_PATH = "/api/v1/staff/_stream_probe"

probe_logger = logging.getLogger("app.probe")


def _add_streaming_probe(app: FastAPI) -> None:
    """A throwaway authenticated route that streams three chunks, logging each as it goes.

    Shaped like `GET /kot/stream` on purpose: authenticated, so it sets the tenant context; slow,
    so the difference between "logged when the response started" and "logged when it finished" is
    visible; and chunked, so the ordering assertion has something to order.
    """

    async def stream(_actor: ActorDep) -> StreamingResponse:
        probe_logger.info(_STARTED_EVENT)

        async def body() -> AsyncIterator[bytes]:
            for index in range(3):
                await asyncio.sleep(0.02)
                probe_logger.info(_CHUNK_EVENT, extra={"index": index})
                yield f"chunk {index}\n".encode()

        return StreamingResponse(body(), media_type="text/plain")

    app.add_api_route(_STREAM_PATH, stream, methods=["GET"])


def _access_lines(lines: list[dict[str, object]], fragment: str) -> list[dict[str, object]]:
    return [
        line
        for line in lines
        if line.get("msg") == "http.request" and fragment in str(line.get("route"))
    ]


def access_line(lines: list[dict[str, object]]) -> dict[str, object]:
    """The stream's own access line, of which there is exactly one."""
    found = _access_lines(lines, "_stream_probe")
    assert len(found) == 1, f"expected one access line for the stream, got {len(found)}"
    return found[0]


# --------------------------------------------------------------------------- status code


async def test_the_access_line_names_the_status_code(api_client: AsyncClient) -> None:
    with captured_lines() as lines:
        response = await api_client.get("/api/v1/health")
    assert response.status_code == 200, response.text

    access = _access_lines(lines, "/health")
    assert access, "no access line was written for the health check"
    assert access[0].get("status_code") == 200


async def test_a_refused_request_is_logged_with_its_status(api_client: AsyncClient) -> None:
    """The half of an access log that matters. An unauthenticated staff call is a 401, and a log
    that records only that a request happened cannot tell it from a success."""
    with captured_lines() as lines:
        response = await api_client.get("/api/v1/staff/suppliers")
    assert response.status_code == 401, response.text

    access = _access_lines(lines, "/suppliers")
    assert access, "no access line was written for the refused request"
    assert access[0].get("status_code") == 401


# --------------------------------------------------------------------------- streaming


async def test_a_streaming_response_is_logged_after_its_body_finishes(
    db_session: AsyncSession, api: FastAPI, api_client: AsyncClient
) -> None:
    """The M08 requirement, stated as an ordering: every chunk, then the access line.

    Under `BaseHTTPMiddleware` this fails — the access line is written the moment the response
    starts, so it lands *before* all three chunks and reports a duration that excludes the body.
    """
    await _world(db_session, "owner")
    token = await _token(api_client, "owner")
    _add_streaming_probe(api)

    with captured_lines() as lines:
        response = await api_client.get(_STREAM_PATH, headers=_auth(token))
    assert response.status_code == 200, response.text
    assert response.text.count("chunk") == 3

    order = [line.get("msg") for line in lines]
    assert order.count(_CHUNK_EVENT) == 3, order
    assert order.index("http.request") > _last_index(order, _CHUNK_EVENT), (
        f"the access line was written before the body finished: {order}"
    )

    # And the duration is measured to that point, not to the response's first byte. Asserted here
    # rather than in a test of its own: a standalone "duration ≥ some number" test passes under the
    # broken middleware for the wrong reason, because argon2 on the login costs more than the
    # body's three sleeps. It is only meaningful once the ordering above holds.
    body_span_ms = (_stamp(lines, _CHUNK_EVENT, last=True) - _stamp(lines, _STARTED_EVENT)) * 1000
    assert body_span_ms > 0
    assert float(str(access_line(lines)["duration_ms"])) >= body_span_ms


async def test_a_streaming_response_carries_the_tenant_on_its_access_line(
    db_session: AsyncSession, api: FastAPI, api_client: AsyncClient
) -> None:
    """The context variable is set by `current_actor`, deep inside the handler. Pure ASGI keeps the
    middleware in the same context, so it is still set when the line is written — no `request.state`
    round trip, which is the workaround that only ever existed to escape the child task."""
    world = await _world(db_session, "owner")
    token = await _token(api_client, "owner")
    _add_streaming_probe(api)

    with captured_lines() as lines:
        await api_client.get(_STREAM_PATH, headers=_auth(token))

    access = _access_lines(lines, "_stream_probe")
    assert access, "no access line was written for the stream"
    assert access[0].get("restaurant_id") == str(world.restaurant.id)


async def test_the_tenant_does_not_leak_out_of_a_streaming_request(
    db_session: AsyncSession, api: FastAPI, api_client: AsyncClient
) -> None:
    """The risk the pure-ASGI version introduces and has to close.

    A child task's context died on its own. One shared context does not: a `set()` inside the
    handler outlives the request unless the middleware resets it. An unauthenticated health check
    after a tenant's stream must carry no tenant — the alternative is one restaurant's identifier
    on another's log line.
    """
    await _world(db_session, "owner")
    token = await _token(api_client, "owner")
    _add_streaming_probe(api)
    await api_client.get(_STREAM_PATH, headers=_auth(token))

    with captured_lines() as lines:
        await api_client.get("/api/v1/health")

    health = _access_lines(lines, "/health")
    assert health, "no access line was written for the health check"
    assert "restaurant_id" not in health[0]
    assert "actor_id" not in health[0]


def _last_index(values: list[object], needle: object) -> int:
    return len(values) - 1 - values[::-1].index(needle)


def _stamp(lines: list[dict[str, object]], event: str, *, last: bool = False) -> float:
    """The `ts` of the first (or last) line with this message, as epoch seconds."""
    stamps = [
        datetime.fromisoformat(str(line["ts"])).timestamp()
        for line in lines
        if line.get("msg") == event
    ]
    assert stamps, f"no {event} line was written"
    return stamps[-1] if last else stamps[0]
