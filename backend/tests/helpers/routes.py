"""One enumerator over the application's real routing table, shared by all four generic suites.

Why this file is more careful than it looks: every generic suite asserts something about *every*
route. If the enumerator ever returns an empty list, all four suites pass — instantly, silently, and
for the rest of the project's life. The security guarantee would be gone and the build would stay
green. That is a worse outcome than any single missing test, so `all_routes()` is paired with a
test that asserts it found the routes we know exist.

FastAPI 0.141 stopped flattening included routers into `app.routes` and wraps them instead, so the
traversal below handles both shapes: a plain `APIRoute`, and a wrapper exposing
`effective_route_contexts()`. Both are tried, because relying on one would break silently on an
upgrade — which is the failure this file exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from app.api.deps import PERMISSION_MARKER
from app.core.rate_limit import RATE_LIMIT_MARKER


@dataclass(frozen=True)
class RouteInfo:
    method: str
    path: str
    permissions: tuple[str, ...]
    name: str
    # What the route answers with. Suite 5 walks this to prove a guest route cannot answer with a
    # staff schema, and cannot reach one three levels down either.
    response_model: Any = None
    # The guest surface's analogue of a declared permission: a staff route declares what a person
    # must hold, a guest route declares what an address may spend. Both are declared on the route
    # rather than checked in a handler, for the reason `require_permission`'s docstring gives.
    rate_limits: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"

    @property
    def is_staff(self) -> bool:
        return self.path.startswith("/api/v1/staff")

    @property
    def is_guest(self) -> bool:
        return self.path.startswith("/api/v1/guest")

    @property
    def is_stream(self) -> bool:
        """A route that holds its connection open instead of answering and closing.

        **A suite that walks every route must skip these, or it hangs on them.** M08's
        `GET /kot/stream` is the first: it keeps a kitchen display updated for a whole service, so
        a plain GET does not return until its deadline — fifty-five minutes later. Suite 1b, which
        probes every id-less GET for another tenant's rows, stopped the entire build dead on it.
        That is not the suite being wrong; it is a route whose contract is "never returns" meeting
        a loop whose contract is "call everything".

        A streaming route still needs every guarantee the suites give the others, so skipping one
        here is a debt, not an exemption: it is paid in `tests/test_kitchen_endpoints.py` (the
        permission, and the headers) and `tests/test_kitchen_stream.py` (tenant isolation, including
        a cursor lifted from another restaurant's stream). Anything added to this list without that
        cover is a route with no tenant test at all.
        """
        return self.path.endswith("/stream")

    def __str__(self) -> str:
        return self.key


def _declared_permissions(dependant: Any) -> tuple[str, ...]:
    """Walk the whole dependency tree, not just the top level.

    `require_permission()` is nested under the route's own dependant, and a future refactor could
    nest it deeper still. Checking only direct dependencies would quietly report "no permission
    declared" for a route that has one.
    """
    found: list[str] = []

    def walk(node: Any) -> None:
        for sub in getattr(node, "dependencies", []):
            code = getattr(getattr(sub, "call", None), PERMISSION_MARKER, None)
            if code:
                found.append(str(code))
            walk(sub)

    walk(dependant)
    return tuple(found)


def _declared_rate_limits(dependant: Any) -> tuple[str, ...]:
    """Walk the whole dependency tree, the same way `_declared_permissions` does and for the same
    reason: a limit nested one level deeper would otherwise read as absent."""
    found: list[str] = []

    def walk(node: Any) -> None:
        for sub in getattr(node, "dependencies", []):
            tier = getattr(getattr(sub, "call", None), RATE_LIMIT_MARKER, None)
            if tier:
                found.append(str(tier))
            walk(sub)

    walk(dependant)
    return tuple(found)


def _from_context(context: Any) -> list[RouteInfo]:
    methods = getattr(context, "methods", None) or set()
    path = getattr(context, "path", None) or getattr(context, "path_format", None)
    dependant = getattr(context, "dependant", None)
    if not path or dependant is None:
        return []
    permissions = _declared_permissions(dependant)
    rate_limits = _declared_rate_limits(dependant)
    name = str(getattr(context, "name", "") or "")
    response_model = getattr(context, "response_model", None)
    return [
        RouteInfo(
            method=method,
            path=str(path),
            permissions=permissions,
            name=name,
            response_model=response_model,
            rate_limits=rate_limits,
        )
        for method in sorted(set(methods) - {"HEAD", "OPTIONS"})
    ]


def all_routes(app: FastAPI) -> list[RouteInfo]:
    """Every API route the application actually serves, with the permission each declares."""
    collected: list[RouteInfo] = []
    for route in app.routes:
        # Shape 1: a plain APIRoute sitting directly on the app.
        if getattr(route, "dependant", None) is not None:
            collected.extend(_from_context(route))
            continue
        # Shape 2: an included router. FastAPI 0.141 wraps these rather than flattening them.
        contexts = getattr(route, "effective_route_contexts", None)
        if callable(contexts):
            for context in contexts():
                collected.extend(_from_context(context))
    return [route for route in collected if route.path.startswith("/api/v1")]


def staff_routes(app: FastAPI) -> list[RouteInfo]:
    return [route for route in all_routes(app) if route.is_staff]


def guest_routes(app: FastAPI) -> list[RouteInfo]:
    """The mirror of `staff_routes`.

    Suite 5 asserts it finds at least five, for the reason this file's own docstring was written
    about: an enumerator that silently returns nothing turns every guarantee below it off at once.
    """
    return [route for route in all_routes(app) if route.is_guest]
