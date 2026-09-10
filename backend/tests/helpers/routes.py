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


@dataclass(frozen=True)
class RouteInfo:
    method: str
    path: str
    permissions: tuple[str, ...]
    name: str

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"

    @property
    def is_staff(self) -> bool:
        return self.path.startswith("/api/v1/staff")

    @property
    def is_guest(self) -> bool:
        return self.path.startswith("/api/v1/guest")

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


def _from_context(context: Any) -> list[RouteInfo]:
    methods = getattr(context, "methods", None) or set()
    path = getattr(context, "path", None) or getattr(context, "path_format", None)
    dependant = getattr(context, "dependant", None)
    if not path or dependant is None:
        return []
    permissions = _declared_permissions(dependant)
    name = str(getattr(context, "name", "") or "")
    return [
        RouteInfo(method=method, path=str(path), permissions=permissions, name=name)
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
