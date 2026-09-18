"""The storage port: what this application asks of a place to keep files, and nothing more.

ADR 0005 commits to "a Docker container, PostgreSQL, and S3-compatible object storage", with media
URLs "pre-signed through a storage abstraction, never constructed from a provider-specific host".
This is that abstraction, and it is deliberately six methods wide.

**Two adapters, and neither is a test double.** `filesystem` runs local development, every test and
staging until a bucket exists; `s3` runs against Cloudflare R2, GCS's HMAC interop, MinIO or AWS.
The behaviour tests in `tests/test_attachments.py` are parameterised over both, because a
filesystem driver that only tests were allowed to use would be a fixture pretending to be code.

**The one difference the application above is allowed to see** is `presigns_uploads`. With S3 the
bytes never pass through this process: the client PUTs them straight at the bucket. With a
filesystem there is nothing to sign, so the client PUTs them at this API instead. Everything
downstream of that — validation especially — is identical, because it asks the *store* rather than
the request (`AttachmentService.confirm`).

**`read` and `facts` exist so that validation is honest.** A `pending` attachment's declared size
and content type are a client's claims; with a presigned upload nothing in this process ever saw
the bytes to check them. So confirmation asks how big the object actually is, reads its first bytes
back, and refuses on either mismatch. That is the whole reason the port has a read at all — the
application never otherwise reads a file it just told somebody to write.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class UploadInstruction:
    """Where to PUT the bytes, and what to send with them.

    A shape rather than a bare URL, because the S3 driver needs `Content-Type` echoed back exactly
    as it was signed — a client that sends a different one gets a signature mismatch from the
    bucket rather than anything this application could explain.
    """

    method: str
    url: str
    headers: Mapping[str, str]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ObjectFacts:
    """What the *store* says about an object, as opposed to what a client claimed."""

    size_bytes: int


@runtime_checkable
class StoragePort(Protocol):
    """Six methods. Adding a seventh is a decision, not a convenience."""

    #: Names the adapter in logs and in `/version`-style diagnostics.
    driver: str
    #: False means "the client cannot PUT at the store; route the bytes through this API".
    presigns_uploads: bool

    async def presigned_put(
        self, key: str, *, content_type: str, size_bytes: int
    ) -> UploadInstruction:
        """Only called when `presigns_uploads` is true."""
        ...

    async def write(self, key: str, data: bytes, *, content_type: str) -> None: ...

    async def download_url(self, key: str, *, file_name: str) -> str | None:
        """A short-lived signed URL, or `None` when the store cannot sign one.

        `None` is not a failure: it means the download route must serve the bytes itself, with the
        hardening headers that replace the separate-origin defence (`AttachmentService`).
        """
        ...

    async def read(self, key: str, count: int | None = None) -> bytes: ...

    async def facts(self, key: str) -> ObjectFacts | None:
        """`None` when the object is not there — which is the normal answer for an upload that was
        begun and abandoned, and the reason the sweep can run without special-casing."""
        ...

    async def delete(self, key: str) -> None:
        """Idempotent. Deleting an object that is not there is not an error, because the sweep and
        a failed confirmation both race with each other and with the client."""
        ...
