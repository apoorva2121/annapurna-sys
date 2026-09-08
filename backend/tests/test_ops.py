"""Health, readiness, version, and the request id that ties a bug report to a log line."""

from __future__ import annotations

import io
import json
import logging

from httpx import AsyncClient

from app.core.logging import REQUEST_ID_HEADER, JsonFormatter


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
