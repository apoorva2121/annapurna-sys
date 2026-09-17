"""Smoke test against a deployed image (R7 step 7, guardrail G-14).

`scripts/smoke.py` checks the local compose stack. This checks a *deployed* one over the public
internet, and the difference is the point: every assertion here is something that passes on a laptop
and can still be wrong in the cloud — a container built without the frontend, an image whose
`/version` reports `unknown` because the build args were dropped, interactive docs exposed because
`ENV` was not set, or the one-origin fallback swallowing an API 404 into HTML.

Nothing here authenticates. CI has no credentials and should not have any; everything below is
observable from outside, which is also what an attacker sees first.

Usage:
    python scripts/smoke_prod.py --base https://restaurant-os-api-xxxx.run.app
    python scripts/smoke_prod.py --base https://... --expect-sha $(git rev-parse HEAD)
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

TIMEOUT = 20  # Generous: a scale-to-zero service answers its first request after a cold start.

failures: list[str] = []


def _lower(headers: object) -> dict[str, str]:
    """Header names are case-insensitive; uvicorn sends them lowercase. Looking up "Content-Type"
    in a plain dict of them finds nothing, which reads as a broken service rather than a broken
    lookup — it did exactly that during the first local rehearsal."""
    return {str(k).lower(): str(v) for k, v in dict(headers).items()}


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "ok  " if condition else "FAIL"
    print(f"  [{status}] {name}{'' if condition else f'  -> {detail[:300]}'}")
    if not condition:
        failures.append(name)


def get(url: str, accept: str = "application/json") -> tuple[int, str, dict[str, str]]:
    request = urllib.request.Request(url, headers={"Accept": accept})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return (
                response.status,
                response.read().decode(errors="replace"),
                _lower(response.headers),
            )
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace"), _lower(exc.headers)
    except Exception as exc:  # noqa: BLE001 - an unreachable service is a failed check, not a crash
        return 0, f"{type(exc).__name__}: {exc}", {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke test a deployed Restaurant OS image.")
    parser.add_argument("--base", required=True, help="Base URL, e.g. https://x.run.app")
    parser.add_argument(
        "--expect-sha",
        default=None,
        help="Fail unless /version reports this commit. Use in CI so the smoke test proves it "
        "tested the build that was just deployed, rather than a previous revision still serving.",
    )
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help="Permit a plain-http base URL. For the local rehearsal only — a real deployment "
        "reachable over http is a finding, not a configuration choice.",
    )
    args = parser.parse_args(argv)
    base = args.base.rstrip("/")

    if not base.startswith("https://") and not args.allow_http:
        # A deployed service reachable over plain HTTP is a finding in itself, so https is the
        # default and http has to be asked for by name. --allow-http exists for one purpose: the
        # local rehearsal, where the image runs on localhost with no certificate. Without it this
        # script could never be run against anything before a real deployment existed — a
        # verification tool that cannot itself be verified.
        check("base URL is https (pass --allow-http for a local rehearsal)", False, base)
        return 1

    print("Health")
    status, body, _ = get(f"{base}/api/v1/health")
    check("/api/v1/health is 200 ok", status == 200 and '"ok"' in body, f"{status} {body}")

    status, body, _ = get(f"{base}/api/v1/ready")
    # /ready touches the database. A 200 here is the only proof the connection string works.
    check("/api/v1/ready is 200 (database reachable)", status == 200, f"{status} {body}")

    print("Provenance")
    status, body, _ = get(f"{base}/api/v1/version")
    check("/api/v1/version is 200", status == 200, f"{status} {body}")
    payload: dict[str, object] = {}
    try:
        payload = json.loads(body or "{}")
    except ValueError:
        check("/api/v1/version returns JSON", False, body)
    sha = str(payload.get("git_sha", ""))
    # "unknown" is the Dockerfile's default. Seeing it means --build-arg GIT_SHA was not passed, so
    # nobody can tell later which commit is serving.
    check("version reports a real commit, not 'unknown'", sha not in ("", "unknown"), sha)
    if args.expect_sha:
        check(
            "version matches the commit just deployed",
            sha == args.expect_sha,
            f"serving {sha}, expected {args.expect_sha}",
        )

    print("One origin (R4)")
    status, body, headers = get(f"{base}/", accept="text/html")
    content_type = headers.get("content-type", "")
    check(
        "/ serves the staff bundle",
        status == 200 and "text/html" in content_type,
        f"{status} {content_type}",
    )

    status, body, headers = get(f"{base}/guest.html?t=smoke", accept="text/html")
    check(
        "/guest.html serves the guest bundle",
        status == 200 and "text/html" in headers.get("content-type", ""),
        f"{status} {headers.get('content-type', '')}",
    )

    status, body, _ = get(f"{base}/orders/42", accept="text/html")
    # React Router owns the URL space: a refresh deep in the app must not 404.
    check("a client-side route falls back to the SPA", status == 200, f"{status}")

    print("The fallback does not swallow the API")
    status, body, headers = get(f"{base}/api/v1/no-such-endpoint")
    check(
        "an unknown /api path stays JSON 404",
        status == 404 and "text/html" not in headers.get("content-type", ""),
        f"{status} {headers.get('content-type', '')}",
    )

    status, body, headers = get(f"{base}/assets/does-not-exist.js")
    check(
        "a missing asset 404s rather than returning HTML",
        status == 404,
        f"{status} {headers.get('content-type', '')}",
    )

    print("Exposure")
    status, _, _ = get(f"{base}/api/docs", accept="text/html")
    # docs_url is None unless ENV=local. A 200 here means the deployment thinks it is local, which
    # also means DEBUG could be on and the interactive docs are an inventory of every route.
    check("/api/docs is not exposed", status != 200, f"{status}")

    status, _, _ = get(f"{base}/api/openapi.json")
    check("/api/openapi.json is not exposed", status != 200, f"{status}")

    status, body, _ = get(f"{base}/api/v1/staff/customers")
    # Unauthenticated, so 401/403. A 500 means the dependency chain broke; a 200 is far worse.
    check(
        "a staff endpoint refuses an anonymous caller",
        status in (401, 403),
        f"{status} {body}",
    )

    print()
    if failures:
        print(f"smoke-prod: {len(failures)} FAILED -> {', '.join(failures)}")
        return 1
    print("smoke-prod: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
