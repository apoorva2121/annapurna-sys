"""Application factory, request context middleware, and the global contracts.

Nothing here is a feature. Everything here is something every later module depends on.
"""

from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.spa import mount_spa

logger = logging.getLogger(__name__)

# A client-supplied request id is echoed into every log line, so it is validated rather than
# trusted — an unbounded header value is a log-injection vector.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _resolve_request_id(incoming: str | None) -> str:
    if incoming is not None and _SAFE_REQUEST_ID.match(incoming):
        return incoming
    return uuid4().hex


def route_template(scope: Scope) -> str:
    """The full path with parameter values replaced by their names.

    scope["route"].path is relative to the router it was registered on, so it renders a staff route
    and a guest route identically — the one distinction this product cannot afford to blur
    (ADR 0009). Rebuilding from the concrete path keeps the prefix and keeps cardinality low.
    """
    path = str(scope.get("path", ""))
    for name, value in (scope.get("path_params") or {}).items():
        path = path.replace(str(value), "{" + name + "}", 1)
    return path


class RequestContextMiddleware:
    """Generate the request id at the edge, thread it through every log line, return it in the
    response header. When a bug is reported, this one value finds everything.

    **Pure ASGI, not `BaseHTTPMiddleware`** (external review M4, done for M08). The class-based
    helper runs the application in a child task and returns from `call_next` when the response
    *starts*. For every module up to M07 that was a distinction without a difference. M08 holds a
    connection open for a whole service, and under the old shape its access line was written at
    second zero, reporting a duration that excluded the entire response, with the handler's context
    variables already gone — the tenant had to be smuggled back through `request.state`.

    Here there is no child task. `send` is wrapped, the status is remembered from
    `http.response.start`, and the access line is written when the last body message goes out. A
    context variable set inside the handler is therefore still set when the line is written, which
    is why `current_actor` no longer copies the tenant anywhere.

    The cost of one shared context is that a `set()` inside the handler would outlive the request,
    so all three variables are set here with tokens and reset in `finally`. `tests/
    test_request_context.py` holds both halves: the line carries the tenant, and the next request
    does not.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _resolve_request_id(_header(scope, REQUEST_ID_HEADER))
        # The context variables are reset as this middleware unwinds, which is too early for the
        # 500 handler running above us in ServerErrorMiddleware. The ASGI scope's state survives.
        scope.setdefault("state", {})["request_id"] = request_id

        started = time.perf_counter()
        status_code = 500
        written = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, written
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                # The last byte of the body. Logged here rather than after `self.app` returns so a
                # stream is measured to its end, and logged before the message is forwarded so an
                # abandoned connection still leaves a line.
                written = True
                _access_line(scope, status_code, started)
            await send(message)

        tokens = (
            request_id_var.set(request_id),
            restaurant_id_var.set(None),
            actor_id_var.set(None),
        )
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # An unhandled error, a client that hung up mid-stream, a cancelled task: every one of
            # them is a request that happened and must appear in the log exactly once.
            if not written:
                written = True
                _access_line(scope, status_code, started)
            raise
        finally:
            if not written:
                _access_line(scope, status_code, started)
            actor_id_var.reset(tokens[2])
            restaurant_id_var.reset(tokens[1])
            request_id_var.reset(tokens[0])


def _header(scope: Scope, name: str) -> str | None:
    """`scope["headers"]` is untyped in the ASGI spec, so the bytes are narrowed here rather than
    trusted — this value is echoed into every log line of the request."""
    wanted = name.lower().encode()
    for key, value in scope.get("headers", ()):
        if key == wanted:
            decoded: str = bytes(value).decode("latin-1")
            return decoded
    return None


def _access_line(scope: Scope, status_code: int, started: float) -> None:
    """The one line per request. Ids travel on the context variables rather than in `extra`, so
    they go through the formatter's own fields instead of the PII pattern scan."""
    logger.info(
        "http.request",
        extra={
            "route": f"{scope.get('method', '')} {route_template(scope)}",
            "status_code": status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )


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
    # M16. Added before the request context so the context wraps it too: a response that never
    # reached a handler still leaves with its headers on.
    app.add_middleware(SecurityHeadersMiddleware)
    # Added after CORS, so it wraps it: a rejected pre-flight is still a request that happened.
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    app.include_router(health.router, prefix="/api/v1")
    # Auth sits outside /staff because it is what produces the identity /staff requires. Mounting
    # it inside would mean the login route lived behind the dependency it exists to satisfy.
    app.include_router(auth.router, prefix="/api/v1/auth")
    app.include_router(staff_router, prefix="/api/v1/staff")
    app.include_router(guest_router, prefix="/api/v1/guest")

    # Last, deliberately. The catch-all in mount_spa would shadow any route registered after it,
    # and the guard that keeps unknown /api paths answering JSON depends on the real routes having
    # had their chance first. Empty STATIC_DIR (local development) mounts nothing at all.
    if settings.static_dir:
        mount_spa(app, settings.static_dir)
    return app


app = create_app()
