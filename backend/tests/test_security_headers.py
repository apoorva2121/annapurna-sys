"""The headers `docs/security.md` promises, asserted against what the application actually sends.

M16's security checklist found rows 7.2 and 7.3 failing, and the reason they went unnoticed for
sixteen modules is the thing this file exists to stop happening again: **the promise lived in a
document and nothing compared it to a response.**

So the first test here reads `docs/security.md` and asserts the headers it names are sent. If
somebody later removes the middleware, the document keeps promising and the test fails — which is
the correct direction for that disagreement to be discovered in.
"""

from __future__ import annotations

import pathlib

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.security_headers import CSP, HSTS

_SECURITY_DOC = pathlib.Path(__file__).resolve().parents[2] / "docs" / "security.md"


class TestTheDocumentAndTheResponseAgree:
    def test_the_document_still_promises_the_three_headers(self) -> None:
        """If this fails, somebody edited the promise rather than the code — which may be right,
        but should be a decision rather than a drift."""
        promise = _SECURITY_DOC.read_text(encoding="utf-8")

        assert "HSTS" in promise
        assert "X-Frame-Options: DENY" in promise
        assert "CSP" in promise

    async def test_the_application_sends_them(self, api_client: AsyncClient) -> None:
        response = await api_client.get("/api/v1/health")
        headers = {name.lower(): value for name, value in response.headers.items()}

        assert headers["x-frame-options"] == "DENY"
        assert headers["content-security-policy"] == CSP
        assert headers["x-content-type-options"] == "nosniff"


class TestWhatTheHeaderActuallySays:
    def test_scripts_may_not_be_inline(self) -> None:
        """The checklist's phrase, and the vector it is about."""
        assert "script-src 'self'" in CSP
        assert "script-src 'self' 'unsafe-inline'" not in CSP

    def test_styles_may_be_inline_and_that_is_deliberate(self) -> None:
        """Radix positions its popovers with `style=`. `style-src 'self'` alone would break every
        menu in the product, and removing the exception needs nonces threaded through the build —
        which is in `docs/backlog.md` rather than smuggled in here.

        Asserted rather than left implicit so the exception is a decision somebody made.
        """
        assert "style-src 'self' 'unsafe-inline'" in CSP

    def test_the_page_cannot_be_framed(self) -> None:
        """The clickjacking fix, said twice: modern browsers read `frame-ancestors`, older ones
        read `X-Frame-Options`, and this product's buttons void bills."""
        assert "frame-ancestors 'none'" in CSP

    def test_nothing_external_is_allowed(self) -> None:
        """The built SPA loads no font, no CDN and no analytics, so `'self'` is not a compromise
        here — it is the whole truth about the page. A future `https://` in this string is a
        supply-chain decision and should be argued for."""
        assert "https://" not in CSP
        assert "*" not in CSP


class TestHstsIsConditional:
    """A `max-age` set on `localhost` pins a developer's browser to HTTPS for a year."""

    async def test_it_is_absent_over_plain_http(self, api_client: AsyncClient) -> None:
        response = await api_client.get("/api/v1/health")

        assert "strict-transport-security" not in {name.lower() for name in response.headers}

    async def test_it_is_present_when_the_load_balancer_says_tls(self, api: FastAPI) -> None:
        """TLS terminates at the balancer, so the scope's scheme is `http` in production and
        `x-forwarded-proto` is the only evidence there is."""
        transport = ASGITransport(app=api)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health", headers={"x-forwarded-proto": "https"})

        assert response.headers["strict-transport-security"] == HSTS
        assert "includeSubDomains" in HSTS
        # Not `preload`: submitting to the preload list has no practical way back, and belongs to
        # whoever owns the domain rather than to a middleware.
        assert "preload" not in HSTS


class TestItDoesNotClobberAStricterOne:
    def test_the_attachment_route_still_declares_its_own(self) -> None:
        """`app/api/v1/staff/attachments.py` serves bytes somebody else uploaded, under
        `sandbox; default-src 'none'`. A middleware that overwrote that would quietly loosen the
        one response in this product that most needs the stricter policy.

        Read from the source rather than exercised through a download, because the assertion is
        about which policy wins and a download fixture would test the storage port instead.
        """
        source = (
            pathlib.Path(__file__).resolve().parents[1]
            / "app"
            / "api"
            / "v1"
            / "staff"
            / "attachments.py"
        ).read_text(encoding="utf-8")

        assert "sandbox; default-src 'none'" in source
