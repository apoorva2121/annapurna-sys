"""One envelope on every error path, including the ones nobody wrote deliberately."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import AppError, ConflictError, build_envelope
from app.core.logging import request_id_var

INTERNAL_DETAIL = "password authentication failed for host 10.0.0.5"


@pytest.fixture
async def error_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    @app.get("/api/v1/_boom")
    async def _boom() -> None:
        raise RuntimeError(INTERNAL_DETAIL)

    @app.get("/api/v1/_conflict")
    async def _conflict() -> None:
        raise ConflictError("order.already_settled", "Order #1042 was settled at 21:14.")

    @app.get("/api/v1/_echo")
    async def _echo(count: int) -> dict[str, int]:
        return {"count": count}

    # raise_app_exceptions=False so the handler's response is observed rather than the exception
    # being re-raised into the test, which is what a real server does.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_unhandled_exception_returns_the_envelope_and_leaks_nothing(
    error_client: AsyncClient,
) -> None:
    response = await error_client.get("/api/v1/_boom")
    body = response.json()

    assert response.status_code == 500
    assert body["code"] == "internal.error"
    assert body["message"] == "Something went wrong."
    assert "request_id" in body
    # The failure detail belongs in the log, never in the response.
    assert INTERNAL_DETAIL not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text


async def test_app_error_carries_its_own_code_and_status(error_client: AsyncClient) -> None:
    response = await error_client.get("/api/v1/_conflict")
    body = response.json()

    assert response.status_code == 409
    assert body["code"] == "order.already_settled"
    assert body["message"] == "Order #1042 was settled at 21:14."


async def test_validation_failure_uses_the_envelope(error_client: AsyncClient) -> None:
    response = await error_client.get("/api/v1/_echo", params={"count": "not-a-number"})
    body = response.json()

    assert response.status_code == 422
    assert body["code"] == "request.invalid"
    assert body["details"]["fields"][0]["field"] == "count"


async def test_unknown_route_uses_the_envelope(error_client: AsyncClient) -> None:
    response = await error_client.get("/api/v1/nothing-here")
    assert response.status_code == 404
    assert response.json()["code"] == "http.404"


def test_app_error_status_code_can_be_overridden_per_instance() -> None:
    error = AppError("stock.insufficient", "Not enough stock.", status_code=422)
    assert error.status_code == 422
    # The class default must not be mutated by an instance override.
    assert AppError.status_code == 400


def test_app_error_defaults_details_to_an_empty_dict() -> None:
    assert AppError("a.b", "message").details == {}


def test_envelope_falls_back_to_the_contextvar_when_no_id_is_passed() -> None:
    token = request_id_var.set("ctx-id")
    try:
        assert build_envelope("a.b", "message")["request_id"] == "ctx-id"
    finally:
        request_id_var.reset(token)


def test_envelope_omits_request_id_when_there_is_none() -> None:
    assert "request_id" not in build_envelope("a.b", "message")
