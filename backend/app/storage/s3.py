"""Any S3-compatible bucket: Cloudflare R2, GCS's HMAC interop, MinIO, AWS.

**boto3 rather than hand-rolled SigV4, and the reason is CLAUDE.md's.** Request signing is a
specification. Writing one from memory is the same mistake as filling in a tax rate from memory,
except that this one fails as a signature mismatch nobody can read. The reference implementation
encodes the spec; a recollection of it does not. `backend/pyproject.toml` records the cost — it is
the largest thing in the image — and the trigger to revisit it.

**Presigning does no I/O**, which is the thing people expect to be wrong here and is not:
`generate_presigned_url` is HMAC over a string the client never sees this process compute. The
three calls that *do* reach the network — head, ranged read, delete — run in a thread, so a slow
bucket cannot stall the event loop that is also serving the kitchen display.

**One client, built once.** botocore clients are thread-safe for the operations used here and
expensive to construct; building one per request would add a TLS handshake to every upload.

**`region_name` defaults to `auto`** because that is what R2 wants, and because SigV4 needs *a*
region string whether or not the provider has regions. GCS's interop endpoint and MinIO both accept
it. AWS itself does not, which is why it is configurable.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from functools import cached_property
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.storage.port import ObjectFacts, UploadInstruction

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mypy_boto3_s3.client import S3Client


class S3Storage:
    """Objects in one bucket, addressed by key."""

    driver = "s3"
    presigns_uploads = True

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        region: str,
        access_key: str,
        secret_key: str,
        url_ttl_seconds: int,
    ) -> None:
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._region = region
        self._access_key = access_key
        self._secret_key = secret_key
        self._ttl = url_ttl_seconds

    @cached_property
    def _client(self) -> S3Client:
        return boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            # Path addressing, because a virtual-host style URL needs DNS per bucket and MinIO,
            # R2's account endpoint and a local test container all speak path style.
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    async def presigned_put(
        self, key: str, *, content_type: str, size_bytes: int
    ) -> UploadInstruction:
        # `size_bytes` is not signed. S3 can bind a length only through a POST policy, which is a
        # different upload shape with a different client; the size is enforced at confirmation
        # instead, against what the store actually holds, which is the stronger check anyway.
        del size_bytes

        def _sign() -> str:
            return self._client.generate_presigned_url(
                "put_object",
                # `ContentType` is signed, so the client must echo it back exactly. That is why
                # `UploadInstruction` carries headers rather than only a URL.
                Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
                ExpiresIn=self._ttl,
                HttpMethod="PUT",
            )

        url = await asyncio.to_thread(_sign)
        return UploadInstruction(
            method="PUT",
            url=url,
            headers={"Content-Type": content_type},
            expires_at=datetime.now(UTC) + timedelta(seconds=self._ttl),
        )

    async def write(self, key: str, data: bytes, *, content_type: str) -> None:
        def _put() -> None:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )

        await asyncio.to_thread(_put)

    async def download_url(self, key: str, *, file_name: str) -> str | None:
        def _sign() -> str:
            return self._client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    # The separate-origin defence, asserted by the bucket rather than by us: the
                    # browser is told to save the file, never to render it, whatever it contains.
                    "ResponseContentDisposition": _disposition(file_name),
                },
                ExpiresIn=self._ttl,
                HttpMethod="GET",
            )

        return await asyncio.to_thread(_sign)

    async def read(self, key: str, count: int | None = None) -> bytes:
        def _get() -> bytes:
            extra: dict[str, Any] = {}
            if count is not None:
                # Ranged, so sniffing sixteen bytes does not pull down a five-megabyte photograph
                # on every confirmation.
                extra["Range"] = f"bytes=0-{count - 1}"
            response = self._client.get_object(Bucket=self._bucket, Key=key, **extra)
            body: bytes = response["Body"].read()
            return body

        return await asyncio.to_thread(_get)

    async def facts(self, key: str) -> ObjectFacts | None:
        def _head() -> ObjectFacts | None:
            try:
                response = self._client.head_object(Bucket=self._bucket, Key=key)
            except ClientError as error:
                # 404 and 403 both mean "not usable"; a bucket policy that hides a missing object
                # behind 403 must not become an exception a caller has to know about.
                status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if status in (403, 404):
                    return None
                raise
            return ObjectFacts(size_bytes=int(response["ContentLength"]))

        return await asyncio.to_thread(_head)

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            # S3 delete is already idempotent: deleting what is not there succeeds.
            self._client.delete_object(Bucket=self._bucket, Key=key)

        await asyncio.to_thread(_delete)


def _disposition(file_name: str) -> str:
    """`attachment`, with the filename encoded so a quote or a newline cannot break the header.

    RFC 6266's `filename*` form, which every current browser understands, and no bare `filename=`
    fallback: an unencoded fallback is precisely the injection this avoids.
    """
    from urllib.parse import quote

    return f"attachment; filename*=UTF-8''{quote(file_name, safe='')}"
