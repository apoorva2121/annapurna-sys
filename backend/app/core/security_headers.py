"""The three headers `docs/security.md` promised and nothing sent.

M16's security checklist found rows 7.2 and 7.3 failing, and the interesting part is *why*:

> `docs/security.md:62` — *"TLS 1.2+ everywhere, HSTS, no mixed content."*
> `docs/security.md:91` — *"Strict CORS allow-list. CSP with no `unsafe-inline`.
> `X-Frame-Options: DENY`."*

The CORS allow-list beside them was real. These three were implemented nowhere, and **no reverse
proxy could have been adding them**: ADR 0005 serves the built SPA from this API (`app/core/
spa.py`), so there is one origin and one process, and headers are this application's job.

The consequence was concrete rather than theoretical. The staff application could be framed — a
clickjacking surface on a product whose buttons void bills, reset passwords and grant roles.

**Three decisions worth stating, because each will look wrong to somebody.**

**1 · `style-src` keeps `'unsafe-inline'` and `script-src` does not.** The checklist's phrase is
"CSP with no `unsafe-inline`", and the vector it is about is script execution. Style attributes are
a different thing: Radix positions its popovers with `style=`, so `style-src 'self'` alone would
break every menu in the product. Removing it needs nonces threaded through the build, which is a
piece of work rather than a line — `docs/backlog.md` carries it. What matters is that the
distinction is deliberate and written down, not that it was missed.

**2 · HSTS is only sent when the request arrived over TLS.** A `max-age` set on `localhost` pins a
developer's browser to HTTPS for that host until it expires, which is a genuinely unpleasant
afternoon. Browsers ignore the header over plain HTTP anyway, so sending it there buys nothing and
costs that.

**3 · An existing header is never overwritten.** `app/api/v1/staff/attachments.py` sets its own,
much stricter, `Content-Security-Policy: sandbox; default-src 'none'` on a downloaded file. A
middleware that clobbered it would quietly loosen the one response in this product that serves
bytes somebody else uploaded.

`X-Frame-Options` ships alongside `frame-ancestors 'none'` although the latter supersedes it. The
checklist asks for the header by name, and it is the only one of the two that an older browser
obeys.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# One year, and `includeSubDomains`. Not `preload`: submitting to the preload list is a decision
# with no practical way back, and it belongs to whoever owns the domain rather than to this file.
HSTS = "max-age=31536000; includeSubDomains"

# Everything is same-origin (ADR 0005), and the built SPA loads nothing external — no fonts, no
# CDN, no analytics. So `'self'` is not a compromise here; it is the whole truth about this page.
CSP = "; ".join(
    (
        "default-src 'self'",
        # The line the checklist is actually about.
        "script-src 'self'",
        # See decision 1 in the module docstring.
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        "connect-src 'self'",
        # The clickjacking fix. `X-Frame-Options` below says the same thing to older browsers.
        "frame-ancestors 'none'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
    )
)

_HEADERS = {
    "content-security-policy": CSP,
    "x-frame-options": "DENY",
    # Not named by the checklist, and one line. This API serves both JSON and, through the SPA
    # mount, files from disk; a response whose type a browser is willing to guess at is the same
    # defect class as the two above.
    "x-content-type-options": "nosniff",
}


class SecurityHeadersMiddleware:
    """Pure ASGI, for the same reason `RequestContextMiddleware` is (external review M4).

    `BaseHTTPMiddleware` runs the application in a child task and returns when the response
    *starts*, which M08's open-for-a-whole-service stream made visible. Nothing here needs the
    body, so wrapping `send` and touching only `http.response.start` is both correct and the
    cheapest thing that can work.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        secure = _is_https(scope)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _HEADERS.items():
                    # Never overwrite. See decision 3.
                    if name not in headers:
                        headers[name] = value
                if secure and "strict-transport-security" not in headers:
                    headers["strict-transport-security"] = HSTS
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _is_https(scope: Scope) -> bool:
    """TLS terminates at the load balancer, so the scheme in the scope is `http` in production.

    `x-forwarded-proto` is what Cloud Run sets, and it is trusted here for exactly one purpose:
    deciding whether to send a header that a browser on plain HTTP would ignore anyway. Nothing
    about authorisation or tenancy reads it.
    """
    if scope.get("scheme") == "https":
        return True
    for key, value in scope.get("headers") or ():
        if key == b"x-forwarded-proto":
            return bool(value.split(b",")[0].strip().lower() == b"https")
    return False
