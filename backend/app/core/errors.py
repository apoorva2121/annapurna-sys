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

from app.core.logging import request_id_var

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


def build_envelope(
    code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message, "details": details or {}}
    request_id = request_id_var.get()
    if request_id is not None:
        body["request_id"] = request_id
    return body


def register_error_handlers(app: FastAPI) -> None:
    """Install the envelope on every error path, including the ones nobody wrote deliberately."""

    # FastAPI fixes these handler signatures; the request argument is unused but required.
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:  # noqa: ARG001
        return JSONResponse(
            status_code=exc.status_code,
            content=build_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request,  # noqa: ARG001
        exc: RequestValidationError,
    ) -> JSONResponse:
        # Field-level detail is safe: it describes the caller's own payload, not our internals.
        fields = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "problem": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=build_envelope(
                "request.invalid", "The request was not valid.", {"fields": fields}
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(
        request: Request,  # noqa: ARG001
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=build_envelope(f"http.{exc.status_code}", str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        # The traceback goes to the log, where the request_id ties it to the user's report. The
        # caller gets a reference, never an internal detail.
        logger.exception("unhandled_exception", extra={"error_type": type(exc).__name__})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_envelope("internal.error", "Something went wrong."),
        )
