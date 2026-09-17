"""The one-origin static mount (R4): what it serves, and the two things it must refuse.

No database and no shared fixtures — `mount_spa` is wired onto a bare app with one stand-in API
route, because what is under test is route precedence and the fallback rule, not the product.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.spa import mount_spa


@asynccontextmanager
async def _client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """A static directory shaped like a real `npm run build`, plus a real API route."""
    (tmp_path / "index.html").write_text("<title>Staff</title>", encoding="utf-8")
    (tmp_path / "guest.html").write_text("<title>Menu</title>", encoding="utf-8")
    (tmp_path / "favicon.ico").write_bytes(b"\x00")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "staff-abc123.js").write_text("console.log(1)", encoding="utf-8")

    app = FastAPI()

    @app.get("/api/v1/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "yes"}

    mount_spa(app, str(tmp_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_a_real_api_route_still_answers_with_the_mount_in_place(tmp_path: Path) -> None:
    """Registration order is the guard: routers first, catch-all last."""
    async with _client(tmp_path) as client:
        response = await client.get("/api/v1/ping")
    assert response.status_code == 200
    assert response.json() == {"pong": "yes"}


async def test_an_unknown_api_path_stays_json_and_never_becomes_html(tmp_path: Path) -> None:
    """Trap 1. The frontend switches on `code`; HTML here is a parse error far from its cause."""
    async with _client(tmp_path) as client:
        response = await client.get("/api/v1/customerz")
    assert response.status_code == 404
    assert "text/html" not in response.headers["content-type"]


async def test_a_client_side_route_falls_back_to_the_staff_bundle(tmp_path: Path) -> None:
    """A refresh on /orders/42 is a path no file matches, and React Router owns it."""
    async with _client(tmp_path) as client:
        response = await client.get("/orders/42")
    assert response.status_code == 200
    assert "Staff" in response.text


async def test_the_guest_bundle_is_served_as_itself_not_the_staff_fallback(tmp_path: Path) -> None:
    """ADR 0009's two applications stay two. A guest must never receive the staff bundle."""
    async with _client(tmp_path) as client:
        response = await client.get("/guest.html?t=table-slug")
    assert response.status_code == 200
    assert "Menu" in response.text
    assert "Staff" not in response.text


async def test_a_missing_asset_404s_rather_than_returning_html(tmp_path: Path) -> None:
    """Trap 2. index.html under a <script src> fails on MIME type, blaming the wrong file."""
    async with _client(tmp_path) as client:
        response = await client.get("/assets/staff-deadbeef.js")
    assert response.status_code == 404
    assert "Staff" not in response.text


async def test_a_present_asset_is_served(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        response = await client.get("/assets/staff-abc123.js")
    assert response.status_code == 200
    assert response.text == "console.log(1)"


async def test_a_root_file_wins_over_the_fallback(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        response = await client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.content == b"\x00"


async def test_a_traversal_attempt_cannot_escape_the_static_directory(tmp_path: Path) -> None:
    """`is_relative_to` after `resolve`, not string prefixing."""
    secret = tmp_path.parent / "spa-secret.txt"
    secret.write_text("do not serve me", encoding="utf-8")
    async with _client(tmp_path) as client:
        for path in ("/../spa-secret.txt", "/..%2fspa-secret.txt", "/%2e%2e/spa-secret.txt"):
            response = await client.get(path)
            assert "do not serve me" not in response.text, path


def test_an_image_without_a_frontend_build_refuses_to_start(tmp_path: Path) -> None:
    """Loud, not an API that 404s every page with nothing in the log to explain it."""
    with pytest.raises(RuntimeError, match=r"no index\.html"):
        mount_spa(FastAPI(), str(tmp_path))


async def test_head_is_answered_as_well_as_get(tmp_path: Path) -> None:
    """Found by the first local rehearsal, not by any unit test here.

    The catch-all was registered with `@app.get`, so HEAD returned 405 Method Not Allowed. Every
    check in this file used GET and passed. `curl -I` uses HEAD, and so do uptime monitors, some
    load balancers, and link checkers — a 405 from the page route reads as a broken deployment.
    """
    async with _client(tmp_path) as client:
        for path in ("/", "/guest.html", "/orders/42"):
            response = await client.head(path)
            assert response.status_code == 200, f"HEAD {path} -> {response.status_code}"
