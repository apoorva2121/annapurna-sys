"""Serving the built frontend from the API, so the product has one origin (R4, ADR 0005).

Two applications are built, not one (ADR 0009): `index.html` is the staff bundle and `guest.html`
the guest one. They differ in how they are reached, and that difference is the whole design here:

* **Staff** uses React Router, so a refresh on `/orders/42` asks this server for a path no file
  matches. It has to answer with `index.html` and let the client route — the "SPA fallback".
* **Guest** carries its state in the query string (`?t=<table>`, `?b=<bill>`), so it is only ever
  reached at one path. It needs no fallback at all, which is why none is written for it.

The fallback is the dangerous half. A catch-all that answers `index.html` for everything breaks two
things that matter more than it does, so both are refused explicitly below:

1. **An unknown `/api/...` path must stay JSON.** The frontend switches on `code` from
   `{code, message, details, issue}` (D11, D12). A mistyped endpoint answering `200 text/html`
   turns a clear 404 into a JSON parse error three layers from the cause.
2. **A missing asset must 404, not fall back.** Hashed bundles are requested by exact name; a
   `<script src>` that receives `index.html` fails on MIME type, and the browser reports a syntax
   error in a file that was never JavaScript.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_spa(app: FastAPI, static_dir: str) -> None:
    """Mount the built frontend. Call *after* every router, so real routes match first."""
    root = Path(static_dir).resolve()
    index = root / "index.html"
    if not index.is_file():
        # Loud, not silent. A container built without the frontend would otherwise serve an API
        # that answers every page request with a 404 no log explains.
        raise RuntimeError(
            f"STATIC_DIR={static_dir} has no index.html; the image lacks a frontend build"
        )

    assets = root / "assets"
    if assets.is_dir():
        # StaticFiles, not the catch-all: it 404s a missing file, which is trap 2 above.
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    # GET and HEAD. Registered with `@app.get` alone, HEAD answered 405 — found by the first local
    # rehearsal rather than by any test here, because every test used GET. `curl -I` uses HEAD, and
    # so do uptime monitors, some load balancers and link checkers.
    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        # Trap 1. Registered API routes already matched; anything still starting with `api` is a
        # path that does not exist, and it must say so in the language the frontend parses.
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        # A real file wins — guest.html, favicon.ico, robots.txt, manifest.webmanifest. `resolve`
        # then the containment check, so `..%2f..%2fetc%2fpasswd` cannot escape the directory.
        if path:
            candidate = (root / path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)

        # Everything else is a client-side route: let the staff bundle decide what it means.
        return FileResponse(index)
