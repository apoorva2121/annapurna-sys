"""Object storage: the port, its two adapters, and the one place that chooses between them.

`get_storage()` is cached, so the S3 client is built once per process rather than once per upload,
and so a test can clear it the way it clears `get_settings`.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import StorageDriver, get_settings
from app.storage.filesystem import FilesystemStorage
from app.storage.port import ObjectFacts, StoragePort, UploadInstruction
from app.storage.s3 import S3Storage

__all__ = [
    "FilesystemStorage",
    "ObjectFacts",
    "S3Storage",
    "StoragePort",
    "UploadInstruction",
    "get_storage",
]


@lru_cache
def get_storage() -> StoragePort:
    """The driver this deployment is configured for.

    `Settings` has already refused to boot if `s3` is selected without its credentials, so nothing
    here has to handle a half-configured bucket.
    """
    settings = get_settings()
    if settings.storage_driver is StorageDriver.S3:
        return S3Storage(
            bucket=settings.storage_bucket,
            endpoint_url=settings.storage_endpoint,
            region=settings.storage_region,
            access_key=settings.storage_access_key,
            secret_key=settings.storage_secret_key.get_secret_value(),
            url_ttl_seconds=settings.storage_url_ttl_seconds,
        )
    return FilesystemStorage(settings.storage_root)
