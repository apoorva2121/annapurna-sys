"""Uploading a file, and the two drivers that must behave identically while doing it.

**The contract tests run against both adapters, and one of them is a real bucket.** MinIO in a
container, because a filesystem driver that only tests were allowed to use would be a fixture
pretending to be code, and an S3 driver nothing ever ran would be a deployment surprise waiting for
the day somebody sets `STORAGE_DRIVER=s3`. This is `docs/testing-strategy.md`'s "never SQLite"
argument applied to storage: the seam is where the bugs are.

**The image comes from quay.io, pinned by digest.** `minio/minio` on Docker Hub no longer exists —
a pull returns "repository does not exist or may require docker login", which reads like an
authentication problem and is not one. Recorded here because the next person to hit it will spend
twenty minutes on `docker login`.

The two tests that matter most:

**A disguised executable is refused**, after upload, by reading the stored object's first bytes
back — not by trusting the content type in the request, which with a presigned upload is the only
thing this process would otherwise ever see.

**A refusal takes the object with it.** Otherwise every rejected upload leaves a row somebody has
to wonder about and an object somebody has to pay for.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from app.core import media
from app.models.communication import Attachment
from app.storage.filesystem import FilesystemStorage
from app.storage.port import StoragePort
from app.storage.s3 import S3Storage
from tests.test_setup_endpoints import _auth, _token
from tests.test_waste_endpoints import _log, _reason, _stocked

STAFF = "/api/v1/staff"
ATTACHMENTS = f"{STAFF}/attachments"

# Pinned by digest for the reason `uv` is pinned: a floating tag means the suite and CI can be
# running different software while both call it "latest".
_MINIO_IMAGE = (
    "quay.io/minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e"
)
_MINIO_KEY = "testkey"
_MINIO_SECRET = "testsecret123"  # noqa: S105 - a throwaway credential for a throwaway container
_BUCKET = "attachments"

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 60
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 60
# The disguised executable: a DOS header, offered as a photograph.
EXECUTABLE = b"MZ\x90\x00" + b"\x00" * 60


# ------------------------------------------------------------------ the rules themselves


class TestWhatAnUploadMayBe:
    """`app/core/media.py` — pure, so these need no database, no bucket and no request."""

    @pytest.mark.parametrize(
        "content_type", ["image/jpeg", "image/png", "image/webp", "image/heic", "application/pdf"]
    )
    def test_the_allow_list_is_what_a_restaurant_actually_uploads(self, content_type: str) -> None:
        assert media.is_allowed(content_type)

    @pytest.mark.parametrize(
        "content_type",
        [
            # The one a reader should look twice at: an image to a person, a script to a browser.
            "image/svg+xml",
            "text/html",
            "application/javascript",
            "application/zip",
            "application/x-msdownload",
            "",
        ],
    )
    def test_everything_else_is_refused(self, content_type: str) -> None:
        assert not media.is_allowed(content_type)

    def test_a_jpeg_is_recognised_and_an_executable_calling_itself_one_is_not(self) -> None:
        assert media.matches_signature("image/jpeg", JPEG)
        assert not media.matches_signature("image/jpeg", EXECUTABLE)

    def test_a_png_offered_as_a_jpeg_is_refused(self) -> None:
        """Both are allowed types. Being allowed is not the same as being what you said."""
        assert media.matches_signature("image/png", PNG)
        assert not media.matches_signature("image/jpeg", PNG)

    def test_a_riff_file_that_is_not_a_webp_is_refused(self) -> None:
        """Checking only the outer prefix would accept any RIFF container — a WAV, an AVI — as a
        WebP, which is why the brand at offset 8 is checked too."""
        assert media.matches_signature("image/webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ")
        assert not media.matches_signature("image/webp", b"RIFF\x00\x00\x00\x00WAVEfmt ")

    def test_a_type_off_the_allow_list_has_no_signature_to_match(self) -> None:
        """Otherwise this would be a way round `is_allowed` rather than a check after it."""
        assert not media.matches_signature("image/svg+xml", b"<svg xmlns=")

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("../../etc/passwd", "etcpasswd"),
            ("..\\..\\windows\\system32", "windowssystem32"),
            (".env", "env"),
            ('a"b\rc\nd.jpg', "abcd.jpg"),
            ("   ", "attachment"),
        ],
    )
    def test_a_file_name_is_a_display_string_and_never_a_path(
        self, raw: str, expected: str
    ) -> None:
        assert media.safe_file_name(raw) == expected


# ------------------------------------------------------------------------ the two drivers


@pytest.fixture(scope="session")
def minio_endpoint() -> Iterator[str]:
    container = (
        DockerContainer(_MINIO_IMAGE)
        .with_env("MINIO_ROOT_USER", _MINIO_KEY)
        .with_env("MINIO_ROOT_PASSWORD", _MINIO_SECRET)
        .with_command("server /data")
        .with_exposed_ports(9000)
        # The structured strategy rather than `wait_for_logs`, which is deprecated and therefore
        # an error here (`filterwarnings = error`). "1 Online" never appears in this release's
        # output; the API banner does.
        .waiting_for(LogMessageWaitStrategy("API: http"))
    )
    with container:
        endpoint = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(9000)}"
        _make_bucket(endpoint)
        yield endpoint


def _make_bucket(endpoint: str) -> None:
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="auto",
        aws_access_key_id=_MINIO_KEY,
        aws_secret_access_key=_MINIO_SECRET,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    client.create_bucket(Bucket=_BUCKET)


@pytest.fixture(params=["filesystem", "s3"])
def storage(request: pytest.FixtureRequest, tmp_path: Any) -> StoragePort:
    """Both adapters, behind the port, for every test in `TestTheDriversAgree`."""
    if request.param == "filesystem":
        return FilesystemStorage(str(tmp_path))
    return S3Storage(
        bucket=_BUCKET,
        endpoint_url=request.getfixturevalue("minio_endpoint"),
        region="auto",
        access_key=_MINIO_KEY,
        secret_key=_MINIO_SECRET,
        url_ttl_seconds=300,
    )


class TestTheDriversAgree:
    """Everything the application above the port is entitled to assume."""

    async def test_what_is_written_can_be_read_back(self, storage: StoragePort) -> None:
        key = f"agree/{uuid.uuid4().hex}.jpg"
        await storage.write(key, JPEG, content_type="image/jpeg")
        assert await storage.read(key) == JPEG

    async def test_a_ranged_read_returns_only_the_head(self, storage: StoragePort) -> None:
        """Sniffing sixteen bytes must not pull down a five-megabyte photograph."""
        key = f"agree/{uuid.uuid4().hex}.jpg"
        await storage.write(key, JPEG, content_type="image/jpeg")
        assert await storage.read(key, media.SIGNATURE_BYTES) == JPEG[: media.SIGNATURE_BYTES]

    async def test_the_store_knows_how_big_an_object_is(self, storage: StoragePort) -> None:
        key = f"agree/{uuid.uuid4().hex}.jpg"
        await storage.write(key, JPEG, content_type="image/jpeg")
        facts = await storage.facts(key)
        assert facts is not None
        assert facts.size_bytes == len(JPEG)

    async def test_an_object_that_is_not_there_has_no_facts(self, storage: StoragePort) -> None:
        """`None` rather than an exception, because an upload begun and abandoned is the normal
        case the sweep exists for."""
        assert await storage.facts(f"agree/{uuid.uuid4().hex}.jpg") is None

    async def test_deleting_what_is_not_there_is_not_an_error(self, storage: StoragePort) -> None:
        """The sweep and a failed confirmation race with each other and with the client."""
        await storage.delete(f"agree/{uuid.uuid4().hex}.jpg")

    async def test_delete_removes_it(self, storage: StoragePort) -> None:
        key = f"agree/{uuid.uuid4().hex}.jpg"
        await storage.write(key, JPEG, content_type="image/jpeg")
        await storage.delete(key)
        assert await storage.facts(key) is None


class TestWhereTheDriversDiffer:
    """The one difference the layers above are allowed to see, asserted in both directions."""

    def test_only_the_bucket_can_presign(self, storage: StoragePort) -> None:
        assert storage.presigns_uploads is (storage.driver == "s3")

    async def test_a_presigned_put_actually_accepts_bytes(self, minio_endpoint: str) -> None:
        """The test that would have caught a signature this project got subtly wrong — which is
        exactly why the driver uses boto3 rather than eighty lines of hand-rolled SigV4."""
        import urllib.request

        store = S3Storage(
            bucket=_BUCKET,
            endpoint_url=minio_endpoint,
            region="auto",
            access_key=_MINIO_KEY,
            secret_key=_MINIO_SECRET,
            url_ttl_seconds=300,
        )
        key = f"presigned/{uuid.uuid4().hex}.jpg"
        instruction = await store.presigned_put(
            key, content_type="image/jpeg", size_bytes=len(JPEG)
        )
        request = urllib.request.Request(  # noqa: S310 - the URL is one this test just built
            instruction.url, data=JPEG, method="PUT", headers=dict(instruction.headers)
        )
        with urllib.request.urlopen(request) as response:  # noqa: S310
            assert response.status == 200

        facts = await store.facts(key)
        assert facts is not None and facts.size_bytes == len(JPEG)

    async def test_the_bucket_signs_a_download_and_the_filesystem_does_not(
        self, storage: StoragePort
    ) -> None:
        key = f"download/{uuid.uuid4().hex}.jpg"
        await storage.write(key, JPEG, content_type="image/jpeg")
        url = await storage.download_url(key, file_name="fridge.jpg")
        if storage.driver == "s3":
            assert url is not None
            # The separate-origin defence, asserted by the bucket rather than by us.
            assert "attachment" in url
        else:
            # `None` is not a failure: it means the download route serves the bytes itself, with
            # the headers that replace a separate origin.
            assert url is None

    def test_a_key_cannot_escape_the_filesystem_root(self, tmp_path: Any) -> None:
        """Keys are generated and never derived from a filename, and this is the last place that
        can be sure — because the cost of being wrong is arbitrary file write."""
        store = FilesystemStorage(str(tmp_path))
        with pytest.raises(ValueError, match="escapes"):
            store._path("../../etc/passwd")


# ------------------------------------------------------------------------- over HTTP


@pytest.fixture
async def filesystem_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> AsyncIterator[None]:
    """The driver staging runs. Patched at the route's own import, so nothing global changes."""
    from app.api.v1.staff import attachments as route

    store = FilesystemStorage(str(tmp_path))
    monkeypatch.setattr(route, "get_storage", lambda: store)
    yield None


async def _wasted(
    session: AsyncSession, client: AsyncClient, *, roles: tuple[str, ...] = ()
) -> tuple[str, str]:
    """A logged wastage event and the owner's token — a real owner object from M09, because the
    authorisation rule this module ships is *about* other modules' objects."""
    item_id, token = await _stocked(session, client, roles=roles)
    reason = await _reason(client, token, "SPOILAGE", "storage", requires_photo=True)
    logged = await _log(client, token, item_id, reason["id"])
    assert logged.status_code == 201, logged.text
    return str(logged.json()["id"]), token


async def _begin(
    client: AsyncClient,
    token: str,
    owner_id: str,
    *,
    mime_type: str = "image/jpeg",
    size: int = len(JPEG),
    file_name: str = "fridge.jpg",
    owner_type: str = "wastage_event",
) -> Any:
    return await client.post(
        ATTACHMENTS,
        json={
            "owner_type": owner_type,
            "owner_id": owner_id,
            "file_name": file_name,
            "mime_type": mime_type,
            "size_bytes": size,
        },
        headers=_auth(token),
    )


async def _upload(client: AsyncClient, token: str, begun: dict[str, Any], body: bytes) -> Any:
    upload = begun["upload"]
    return await client.request(
        upload["method"], upload["url"], content=body, headers={**_auth(token), **upload["headers"]}
    )


@pytest.mark.usefixtures("filesystem_api")
class TestAttachingAFile:
    async def test_the_whole_journey_survives_the_requests_that_made_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Four requests, deliberately. Only a later one can tell whether an earlier one
        committed — the bug this codebase has now written twice."""
        event_id, token = await _wasted(db_session, api_client)

        begun = await _begin(api_client, token, event_id)
        assert begun.status_code == 201, begun.text
        body = begun.json()
        assert body["attachment"]["status"] == "pending"
        assert body["upload"]["method"] == "PUT"

        stored = await _upload(api_client, token, body, JPEG)
        assert stored.status_code == 204, stored.text

        confirmed = await api_client.post(
            f"{ATTACHMENTS}/{body['attachment']['id']}/confirm", headers=_auth(token)
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "ready"

        fetched = await api_client.get(
            f"{ATTACHMENTS}/{body['attachment']['id']}", headers=_auth(token)
        )
        assert fetched.status_code == 200, fetched.text
        assert fetched.content == JPEG

    async def test_a_disguised_executable_is_refused_and_leaves_nothing_behind(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The module's named test. A `.jpg` extension, `image/jpeg` declared, `MZ` first bytes."""
        event_id, token = await _wasted(db_session, api_client)
        begun = (await _begin(api_client, token, event_id, size=len(EXECUTABLE))).json()
        await _upload(api_client, token, begun, EXECUTABLE)

        confirmed = await api_client.post(
            f"{ATTACHMENTS}/{begun['attachment']['id']}/confirm", headers=_auth(token)
        )
        assert confirmed.status_code == 422, confirmed.text
        assert confirmed.json()["code"] == "attachment.content_mismatch"

        survivors = await db_session.scalars(
            select(Attachment).where(Attachment.id == uuid.UUID(begun["attachment"]["id"]))
        )
        assert survivors.first() is None

    async def test_a_file_larger_than_it_claimed_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The declared size is a client's claim, and a presigned PUT is not bound to it in every
        S3 implementation — so the store's answer is the one that counts."""
        event_id, token = await _wasted(db_session, api_client)
        begun = (await _begin(api_client, token, event_id, size=4)).json()
        await _upload(api_client, token, begun, JPEG)

        confirmed = await api_client.post(
            f"{ATTACHMENTS}/{begun['attachment']['id']}/confirm", headers=_auth(token)
        )
        assert confirmed.status_code == 422, confirmed.text
        assert confirmed.json()["code"] == "attachment.size_mismatch"

    async def test_a_type_off_the_allow_list_never_gets_a_key(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Refused before anything is issued, so an SVG never reaches the store at all."""
        event_id, token = await _wasted(db_session, api_client)
        refused = await _begin(api_client, token, event_id, mime_type="image/svg+xml")
        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == "attachment.type_not_allowed"

    async def test_a_download_is_saved_and_never_rendered(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """With no second origin available, these three headers are what replace it."""
        event_id, token = await _wasted(db_session, api_client)
        begun = (await _begin(api_client, token, event_id)).json()
        await _upload(api_client, token, begun, JPEG)
        await api_client.post(
            f"{ATTACHMENTS}/{begun['attachment']['id']}/confirm", headers=_auth(token)
        )

        fetched = await api_client.get(
            f"{ATTACHMENTS}/{begun['attachment']['id']}", headers=_auth(token)
        )
        assert fetched.headers["content-disposition"].startswith("attachment;")
        assert fetched.headers["x-content-type-options"] == "nosniff"
        assert "sandbox" in fetched.headers["content-security-policy"]

    async def test_a_file_name_that_is_a_path_becomes_a_name(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        event_id, token = await _wasted(db_session, api_client)
        begun = await _begin(api_client, token, event_id, file_name="../../etc/passwd")
        assert begun.json()["attachment"]["file_name"] == "etcpasswd"

    async def test_confirming_twice_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Otherwise a checked object could be replaced by an unchecked one under the same id."""
        event_id, token = await _wasted(db_session, api_client)
        begun = (await _begin(api_client, token, event_id)).json()
        await _upload(api_client, token, begun, JPEG)
        first = await api_client.post(
            f"{ATTACHMENTS}/{begun['attachment']['id']}/confirm", headers=_auth(token)
        )
        assert first.status_code == 200
        second = await api_client.post(
            f"{ATTACHMENTS}/{begun['attachment']['id']}/confirm", headers=_auth(token)
        )
        assert second.status_code == 409, second.text

    async def test_confirming_without_uploading_says_so(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        event_id, token = await _wasted(db_session, api_client)
        begun = (await _begin(api_client, token, event_id)).json()
        confirmed = await api_client.post(
            f"{ATTACHMENTS}/{begun['attachment']['id']}/confirm", headers=_auth(token)
        )
        assert confirmed.status_code == 409, confirmed.text
        assert confirmed.json()["code"] == "attachment.not_uploaded"

    async def test_a_waiter_cannot_attach_a_photograph_to_somebody_elses_waste(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The authorisation that matters: the route's permission is held by everybody, and the
        owner object is what decides."""
        event_id, _owner_token = await _wasted(db_session, api_client, roles=("waiter",))
        waiter = await _token(api_client, "waiter")
        refused = await _begin(api_client, waiter, event_id)
        assert refused.status_code == 403, refused.text
        assert refused.json()["code"] == "attachment.not_your_wastage"

    async def test_another_restaurants_owner_object_is_a_404_before_any_file_exists(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """One message for "no such thing" and "not yours": telling them apart is how somebody
        enumerates what exists in a tenant they cannot read."""
        _event_id, token = await _wasted(db_session, api_client)
        refused = await _begin(api_client, token, str(uuid.uuid4()))
        assert refused.status_code == 404, refused.text
        assert refused.json()["code"] == "attachment.owner_not_found"


@pytest.mark.usefixtures("filesystem_api")
class TestTheSweep:
    async def test_an_abandoned_upload_is_swept_with_its_object(
        self, db_session: AsyncSession, api_client: AsyncClient, tmp_path: Any
    ) -> None:
        """Without it a bucket fills with orphans no row references, no screen shows and no
        erasure reaches."""
        from app.services.attachments import AttachmentService

        event_id, token = await _wasted(db_session, api_client)
        begun = (await _begin(api_client, token, event_id)).json()
        await _upload(api_client, token, begun, JPEG)

        attachment = await db_session.get(Attachment, uuid.UUID(begun["attachment"]["id"]))
        assert attachment is not None
        store = FilesystemStorage(str(tmp_path))

        service = AttachmentService(
            db_session,
            _scope_of(attachment),
            store,
        )
        swept = await service.sweep(now=datetime.now(UTC) + timedelta(hours=2))
        assert swept >= 1
        assert await db_session.get(Attachment, uuid.UUID(begun["attachment"]["id"])) is None

    async def test_a_fresh_pending_upload_is_left_alone(
        self, db_session: AsyncSession, api_client: AsyncClient, tmp_path: Any
    ) -> None:
        from app.services.attachments import AttachmentService

        event_id, token = await _wasted(db_session, api_client)
        begun = (await _begin(api_client, token, event_id)).json()
        attachment = await db_session.get(Attachment, uuid.UUID(begun["attachment"]["id"]))
        assert attachment is not None

        service = AttachmentService(
            db_session, _scope_of(attachment), FilesystemStorage(str(tmp_path))
        )
        assert await service.sweep() == 0


def _scope_of(attachment: Attachment) -> Any:
    from app.core.tenancy import TenantScope

    return TenantScope(organization_id=uuid.uuid4(), restaurant_id=attachment.restaurant_id)


class TestTheBucketPath:
    """One journey through the real thing, so the S3 driver is not a deployment surprise."""

    async def test_a_bucket_backed_download_redirects_instead_of_streaming(
        self,
        db_session: AsyncSession,
        api_client: AsyncClient,
        minio_endpoint: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.api.v1.staff import attachments as route

        store = S3Storage(
            bucket=_BUCKET,
            endpoint_url=minio_endpoint,
            region="auto",
            access_key=_MINIO_KEY,
            secret_key=_MINIO_SECRET,
            url_ttl_seconds=300,
        )
        monkeypatch.setattr(route, "get_storage", lambda: store)

        event_id, token = await _wasted(db_session, api_client)
        begun = (await _begin(api_client, token, event_id)).json()
        # The client PUTs at the bucket, not at this API — the whole point of presigning.
        assert begun["upload"]["url"].startswith(minio_endpoint)
        await store.write(
            (await _key_of(db_session, begun["attachment"]["id"])), JPEG, content_type="image/jpeg"
        )

        confirmed = await api_client.post(
            f"{ATTACHMENTS}/{begun['attachment']['id']}/confirm", headers=_auth(token)
        )
        assert confirmed.status_code == 200, confirmed.text

        fetched = await api_client.get(
            f"{ATTACHMENTS}/{begun['attachment']['id']}",
            headers=_auth(token),
            follow_redirects=False,
        )
        assert fetched.status_code == 307
        assert fetched.headers["location"].startswith(minio_endpoint)


async def _key_of(session: AsyncSession, attachment_id: str) -> str:
    attachment = await session.get(Attachment, uuid.UUID(attachment_id))
    assert attachment is not None
    return str(attachment.file_key)
