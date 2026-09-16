"""Health, readiness, version, and the request id that ties a bug report to a log line."""

from __future__ import annotations

import io
import json
import logging

import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.logging import REQUEST_ID_HEADER, JsonFormatter
from app.main import configure_sentry, route_template

_DB_URL = "postgresql+asyncpg://user:pw@localhost:5432/db"


async def test_health_is_ok_without_touching_a_dependency(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_version_reports_the_build(client: AsyncClient) -> None:
    response = await client.get("/api/v1/version")
    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"git_sha", "built_at", "env"}
    assert body["env"] == "local"


async def test_ready_fails_when_the_database_is_unreachable(client: AsyncClient) -> None:
    # The test environment points at an unroutable database on purpose.
    response = await client.get("/api/v1/ready")
    body = response.json()
    assert response.status_code == 503
    assert body["ready"] is False
    assert body["database"] is False


async def test_request_id_is_echoed_and_reaches_the_log_line(client: AsyncClient) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        response = await client.get("/api/v1/health", headers={REQUEST_ID_HEADER: "abc123"})
    finally:
        root.removeHandler(handler)

    assert response.headers[REQUEST_ID_HEADER] == "abc123"
    lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    request_lines = [line for line in lines if line.get("msg") == "http.request"]
    assert request_lines, "the middleware did not log the request"
    assert request_lines[0]["request_id"] == "abc123"
    assert request_lines[0]["route"] == "GET /api/v1/health"
    assert isinstance(request_lines[0]["duration_ms"], float)


async def test_an_unsafe_client_request_id_is_replaced(client: AsyncClient) -> None:
    # An unbounded, attacker-chosen header value would otherwise be written straight into the logs.
    response = await client.get("/api/v1/health", headers={REQUEST_ID_HEADER: "x" * 200})
    assert response.headers[REQUEST_ID_HEADER] != "x" * 200
    assert len(response.headers[REQUEST_ID_HEADER]) == 32


def test_route_template_replaces_parameter_values_with_their_names() -> None:
    """Regression: the middleware logged scope["route"].path, which is router-relative and renders
    a staff route and a guest route identically (ADR 0009)."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/staff/orders/1042",
        "headers": [],
        "query_string": b"",
        "path_params": {"order_id": "1042"},
        "server": ("test", 80),
        "scheme": "http",
    }
    # The scope itself, not a `Request` wrapped around it: M08's middleware is pure ASGI and
    # never builds a Request, because the access line is written from the raw scope after the
    # response body has finished.
    assert route_template(scope) == "/api/v1/staff/orders/{order_id}"


def test_sentry_is_not_initialised_without_a_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _init(**_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("app.main.sentry_sdk.init", _init)
    configure_sentry(Settings(_env_file=None, env="local", database_url=_DB_URL))
    assert called is False


def test_sentry_is_initialised_with_pii_disabled_when_a_dsn_is_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _init(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("app.main.sentry_sdk.init", _init)
    configure_sentry(
        Settings(
            _env_file=None,
            env="local",
            database_url=_DB_URL,
            sentry_dsn="https://key@example.test/1",
        )
    )
    # PII scrubbing is configured before the first event is sent, not after.
    assert captured["send_default_pii"] is False
    assert captured["environment"] == "local"
