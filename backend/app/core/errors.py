"""One error envelope, registered globally, applied before any endpoint exists.

`code` is a stable string the frontend switches on. `message` is human-readable English safe to
show a user and never contains internal detail — no stack traces, no SQL, no table names
(docs/engineering-standards.md §4).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import REQUEST_ID_HEADER, request_id_var
from app.core.validation_messages import describe, summary

logger = logging.getLogger(__name__)


class AppError(Exception):
    """An error the API deliberately exposes."""

    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, Any] = details or {}
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN


def request_id_for(request: Request) -> str | None:
    """The contextvar is reset as the exception unwinds the request middleware, which is too early
    for the 500 handler running above it in ServerErrorMiddleware. request.state lives in the ASGI
    scope and survives, so it is the primary source and the contextvar the fallback."""
    from_state = getattr(request.state, "request_id", None)
    if isinstance(from_state, str):
        return from_state
    return request_id_var.get()


def build_envelope(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message, "details": details or {}}
    resolved = request_id if request_id is not None else request_id_var.get()
    if resolved is not None:
        body["request_id"] = resolved
    return body


def _field_problem(error: Any) -> dict[str, str]:
    code, message = describe(error)
    # `loc` starts with where the value came from (`body`, `query`, `path`), which the person
    # filling the form does not need; the rest is the field.
    return {
        "field": ".".join(str(part) for part in error["loc"][1:]),
        "code": code,
        "message": message,
    }


def _respond(status_code: int, body: dict[str, Any]) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content=body)
    request_id = body.get("request_id")
    if isinstance(request_id, str):
        # The error path is where this header matters most; the middleware never gets to set it
        # when the request raised.
        response.headers[REQUEST_ID_HEADER] = request_id
    return response


def register_error_handlers(app: FastAPI) -> None:
    """Install the envelope on every error path, including the ones nobody wrote deliberately."""

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return _respond(
            exc.status_code,
            build_envelope(exc.code, exc.message, exc.details, request_id_for(request)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Field-level detail is safe: it describes the caller's own payload, not our internals. Each
        # problem is a stable code and a sentence a person can act on — never pydantic's wording,
        # which for a format rule is the regular expression itself.
        fields = [_field_problem(error) for error in exc.errors()]
        return _respond(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            build_envelope(
                "request.invalid",
                summary(len(fields)),
                {"fields": fields},
                request_id_for(request),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _respond(
            exc.status_code,
            build_envelope(
                f"http.{exc.status_code}", str(exc.detail), None, request_id_for(request)
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # The traceback goes to the log, where the request_id ties it to the user's report. The
        # caller gets a reference, never an internal detail.
        logger.exception("unhandled_exception", extra={"error_type": type(exc).__name__})
        return _respond(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            build_envelope(
                "internal.error", "Something went wrong.", None, request_id_for(request)
            ),
        )
