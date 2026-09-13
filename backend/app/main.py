"""Application factory, request context middleware, and the global contracts.

Nothing here is a feature. Everything here is something every later module depends on.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

import sentry_sdk
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.v1 import auth
from app.api.v1.guest import router as guest_router
from app.api.v1.staff import router as staff_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import (
    REQUEST_ID_HEADER,
    actor_id_var,
    configure_logging,
    request_id_var,
    restaurant_id_var,
)

logger = logging.getLogger(__name__)

# A client-supplied request id is echoed into every log line, so it is validated rather than
# trusted — an unbounded header value is a log-injection vector.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _resolve_request_id(incoming: str | None) -> str:
    if incoming is not None and _SAFE_REQUEST_ID.match(incoming):
        return incoming
    return uuid4().hex


def route_template(request: Request) -> str:
    """The full path with parameter values replaced by their names.

    scope["route"].path is relative to the router it was registered on, so it renders a staff route
    and a guest route identically — the one distinction this product cannot afford to blur
    (ADR 0009). Rebuilding from the concrete path keeps the prefix and keeps cardinality low.
    """
    path = request.url.path
    for name, value in (request.scope.get("path_params") or {}).items():
        path = path.replace(str(value), "{" + name + "}", 1)
    return path


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Generate the request id at the edge, thread it through every log line, return it in the
    response header. When a bug is reported, this one value finds everything."""
    request_id = _resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
    # The contextvar is reset as this middleware unwinds, which is too early for the 500 handler
    # running above us in ServerErrorMiddleware. request.state lives in the ASGI scope and survives.
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        # **The handler's context does not reach this line.** `call_next` runs the application in a
        # child task, so the tenant `current_actor` set is gone by the time the access line is
        # written. `request.state` lives in the ASGI scope and survives, so it is read back here and
        # set for this one call only. Through the context variables rather than `extra`, so the ids
        # go through the formatter's own fields instead of the PII pattern scan.
        tenant = restaurant_id_var.set(getattr(request.state, "restaurant_id", None))
        actor = actor_id_var.set(getattr(request.state, "actor_employee_id", None))
        try:
            logger.info(
                "http.request",
                extra={
                    "route": f"{request.method} {route_template(request)}",
                    "duration_ms": duration_ms,
                },
            )
        finally:
            actor_id_var.reset(actor)
            restaurant_id_var.reset(tenant)
            request_id_var.reset(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def configure_sentry(settings: Settings) -> None:
    """PII scrubbing is configured before the first event is sent, not after."""
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env.value,
        release=settings.git_sha,
        send_default_pii=False,
    )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_sentry(settings)

    app = FastAPI(
        title="Restaurant OS",
        version="0.1.0",
        # Interactive docs enumerate every route and schema. Useful locally, an inventory for an
        # attacker anywhere else.
        docs_url="/api/docs" if settings.is_local else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.is_local else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.middleware("http")(request_context_middleware)
    register_error_handlers(app)

    app.include_router(health.router, prefix="/api/v1")
    # Auth sits outside /staff because it is what produces the identity /staff requires. Mounting
    # it inside would mean the login route lived behind the dependency it exists to satisfy.
    app.include_router(auth.router, prefix="/api/v1/auth")
    app.include_router(staff_router, prefix="/api/v1/staff")
    app.include_router(guest_router, prefix="/api/v1/guest")
    return app


app = create_app()
