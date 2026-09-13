"""Every log line knows which restaurant it belongs to — and no identifier is mistaken for a phone.

Two defects, found while writing the M07 spec, and both invisible to every test that existed.

**1 · The tenant was never on a log line.** `docs/observability.md` promises that every line
carries `request_id`, `restaurant_id` and `actor_id` *"automatically, via middleware"*.
`app/core/logging.py` declares a context variable for each and the formatter reads all three — but
nothing anywhere ever **set** `restaurant_id_var` or `actor_id_var`. So every business event, every
security warning and every access line has been written with no tenant on it, while the document
describing the system said otherwise. Per-tenant debugging, which the doc calls "a filter, not an
investigation", was an investigation.

**2 · The phone redactor ate UUIDs.** The Indian-mobile pattern is bounded by `(?<!\\d)` and
`(?!\\d)`, which exclude digits and nothing else. A UUID's final twelve-character group containing a
ten-digit run that starts 6-9 and sits between a dash and a hex letter matches `[6-9]\\d{9}` — so
`…-b137-9876543210ab` was logged as `…-b137-[redacted]ab`. Roughly one identifier in two hundred.
Anything passed through `extra={...}` is pattern-scanned by `RedactingFilter`, and
`auth.account_locked` passes `account_id` exactly that way: a fraction of locked-account ids in the
*security* log were already corrupted.

The redaction is a PII control, so the fix for the second must not weaken it: a real phone number
beside a UUID is still redacted, and a test says so.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ActorDep
from app.core.logging import JsonFormatter, RedactingFilter, redact_text, redact_value
from app.models.identity import Employee
from tests.test_setup_endpoints import _auth, _token, _world

# A UUIDv7-shaped identifier whose last group holds a bounded ten-digit run starting with 9 — the
# exact shape the phone pattern used to match.
_UNLUCKY_UUID = "01a0975a-bdb5-7534-b137-9876543210ab"
_PROBE_EVENT = "probe.business_event"


@contextmanager
def _captured_lines() -> Iterator[list[dict[str, Any]]]:
    """Every JSON line the application writes while the block runs, parsed.

    Installed on the root logger with the production formatter and filter, so what is asserted is
    what production would emit — not pytest's own record format, which never sees the context vars.
    """
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    lines: list[dict[str, Any]] = []
    try:
        yield lines
    finally:
        root.removeHandler(handler)
        lines.extend(json.loads(raw) for raw in stream.getvalue().splitlines() if raw.strip())


def _add_probe_route(app: FastAPI) -> None:
    """A throwaway authenticated route that logs one business event, on this test's app only.

    Every test gets a fresh `create_app()`, so the generic suites never see this route and its
    missing permission declaration cannot fail suite 4.
    """
    probe_logger = logging.getLogger("app.probe")

    # Named for its side effect: requiring the actor is what sets the tenant under test.
    async def probe(_actor: ActorDep) -> dict[str, str]:
        probe_logger.info(_PROBE_EVENT)
        return {"ok": "yes"}

    app.add_api_route("/api/v1/staff/_probe", probe, methods=["GET"])


# --------------------------------------------------------------------------- redaction


def test_a_uuid_in_free_text_is_not_mistaken_for_a_phone_number() -> None:
    assert redact_text(f"restaurant {_UNLUCKY_UUID}") == f"restaurant {_UNLUCKY_UUID}"


def test_a_uuid_passed_as_a_structured_field_survives_redaction() -> None:
    """The path `auth.account_locked` uses, and every business event M07 will add."""
    assert redact_value("account_id", _UNLUCKY_UUID) == _UNLUCKY_UUID


def test_a_real_phone_beside_a_uuid_is_still_redacted() -> None:
    """The fix is a carve-out from a PII control, so it has to be exactly as wide as a UUID.

    Anything wider — relaxing the phone pattern's boundaries to exclude hex letters, say — would
    stop redacting a number glued to a word, and a missed phone number is worse than a mangled id.
    """
    out = redact_text(f"account {_UNLUCKY_UUID} called 9876543210 twice")
    assert _UNLUCKY_UUID in out
    assert out.endswith("called [redacted] twice")


# --------------------------------------------------------------------------- tenant context


async def test_a_log_line_written_during_a_request_carries_the_tenant(
    db_session: AsyncSession, api: FastAPI, api_client: AsyncClient
) -> None:
    world = await _world(db_session, "owner")
    token = await _token(api_client, "owner")
    employee_id = (
        await db_session.scalars(
            select(Employee.id).where(Employee.organization_id == world.organization.id)
        )
    ).one()
    _add_probe_route(api)

    with _captured_lines() as lines:
        response = await api_client.get("/api/v1/staff/_probe", headers=_auth(token))
    assert response.status_code == 200, response.text

    events = [line for line in lines if line.get("msg") == _PROBE_EVENT]
    assert events, "the probe route logged nothing the handler could capture"
    assert events[0].get("restaurant_id") == str(world.restaurant.id)
    assert events[0].get("actor_id") == str(employee_id)


async def test_the_access_line_carries_the_tenant(
    db_session: AsyncSession, api_client: AsyncClient
) -> None:
    """`http.request` is written by the middleware *after* the handler returns, in a context the
    handler's variables do not reach — so it needs the tenant from somewhere that does survive."""
    world = await _world(db_session, "owner")
    token = await _token(api_client, "owner")

    with _captured_lines() as lines:
        response = await api_client.get("/api/v1/staff/suppliers", headers=_auth(token))
    assert response.status_code == 200, response.text

    access = [
        line
        for line in lines
        if line.get("msg") == "http.request" and "/suppliers" in str(line.get("route"))
    ]
    assert access, "no access line was written for the request"
    assert access[0].get("restaurant_id") == str(world.restaurant.id)


async def test_the_tenant_does_not_leak_into_the_next_request(
    db_session: AsyncSession, api_client: AsyncClient
) -> None:
    """Tenant context is request-scoped. If it outlived its request, the next line — possibly
    another restaurant's — would be filed under the wrong tenant, which is worse than no tenant."""
    await _world(db_session, "owner")
    token = await _token(api_client, "owner")
    await api_client.get("/api/v1/staff/suppliers", headers=_auth(token))

    with _captured_lines() as lines:
        response = await api_client.get("/api/v1/health")
    assert response.status_code == 200, response.text

    health = [line for line in lines if "/health" in str(line.get("route"))]
    assert health, "no access line was written for the health check"
    assert "restaurant_id" not in health[0]
    assert "actor_id" not in health[0]
