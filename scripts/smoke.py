"""Smoke test against a running stack (`make dev`), not against test doubles.

Unit tests use testcontainers and so never exercise the *composed* system. Three M00 defects were
invisible to a fully green suite: migrations were never applied, the make targets addressed a host
that does not resolve, and the Vite proxy pointed at localhost inside a container where localhost is
that container. Each was found by a person opening the app. This script is that person, automated.

Usage:  make smoke        (requires `make dev` to be up)
"""

import json
import sys
import urllib.error
import urllib.request

API = "http://localhost:8000"
WEB = "http://localhost:5173"
TIMEOUT = 5

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {name}{'' if condition else f'  -> {detail}'}")
    if not condition:
        failures.append(name)


def get(url: str, accept: str = "application/json") -> tuple[int, str, dict[str, str]]:
    request = urllib.request.Request(url, headers={"Accept": accept})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            return response.status, response.read().decode(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(), dict(exc.headers)
    except Exception as exc:  # noqa: BLE001 - a dead stack is a failed check, not a crash
        return 0, f"{type(exc).__name__}: {exc}", {}


print("API")
status, body, _ = get(f"{API}/api/v1/health")
check("/health is 200 ok", status == 200 and json.loads(body or "{}") == {"status": "ok"}, body)

status, body, _ = get(f"{API}/api/v1/ready")
ready = json.loads(body) if status in (200, 503) else {}
check(
    "/ready is 200 with database and migrations green",
    status == 200 and ready.get("ready") and ready.get("migrations_at_head"),
    body,
)

status, body, _ = get(f"{API}/api/v1/version")
check(
    "/version returns git_sha, built_at, env",
    status == 200 and set(json.loads(body or "{}")) == {"git_sha", "built_at", "env"},
    body,
)

print("Errors")
status, body, headers = get(f"{API}/api/v1/nothing-here")
envelope = json.loads(body) if body.startswith("{") else {}
check("unknown route returns the envelope", status == 404 and envelope.get("code") == "http.404", body)
check("envelope carries a request_id", "request_id" in envelope, body)
check("no traceback leaks to the caller", "Traceback" not in body and "File \"" not in body, body)
header_id = headers.get("X-Request-Id") or headers.get("x-request-id")
check(
    "request id in the header matches the body",
    header_id is not None and header_id == envelope.get("request_id"),
    f"header={header_id} body={envelope.get('request_id')}",
)

print("Web")
# text/html, not json: vite only applies its SPA fallback for a browser-shaped request.
status, body, _ = get(f"{WEB}/", accept="text/html")
check("the page is served", status == 200 and 'id="root"' in body, f"status={status}")

# The check that matters: the browser reaches the API *through* the dev server, which is the path a
# person actually uses. Hitting the API directly proves nothing about it.
status, body, _ = get(f"{WEB}/api/v1/version")
check("the API is reachable THROUGH the web server", status == 200, f"status={status} {body[:120]}")

print()
if failures:
    print(f"smoke: {len(failures)} FAILED -> {', '.join(failures)}")
    sys.exit(1)
print("smoke: all checks passed")
