"""Application settings, validated once at startup.

A bad configuration fails the boot loudly here rather than surfacing as a mystery 500 in week
three. Every value the application needs is declared on this model; nothing reads os.environ
directly.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class StorageDriver(StrEnum):
    """Where uploaded files live. Two real adapters, not one and a stub (`app/storage/port.py`)."""

    FILESYSTEM = "filesystem"
    S3 = "s3"


class Settings(BaseSettings):
    """Runtime configuration. Immutable — nothing reconfigures the app after boot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # extra="forbid" everywhere (docs/engineering-standards.md §4). Here it also means a typo
        # in .env fails the boot instead of silently falling back to a default.
        extra="forbid",
        frozen=True,
    )

    env: Environment
    debug: bool = False
    log_level: str = "INFO"
    database_url: str
    cors_origins: str = ""
    # R4/ADR 0005 "one origin": the directory holding the built frontend, served by this app so the
    # SPA and the API share a scheme, host and port. Empty means "serve no static files", which is
    # what local development wants — Vite owns :5173 and proxies /api here, so a static mount would
    # shadow the dev server with a stale build. Set to /app/static in the image only.
    # Only ever set on staging, and only to seed the demo world there (R7 step 2). It must differ
    # from the password committed in `seed/organization.yaml`, which is the whole point: the
    # committed one is printed in a file's own header, so seeding with it outside local would hand
    # an owner account to anyone who can read the source.
    seed_password: str | None = None
    static_dir: str = ""
    sentry_dsn: str | None = None
    # Injected by the image build; "unknown" locally is honest rather than misleading.
    git_sha: str = "unknown"
    built_at: str = "unknown"

    # ------------------------------------------------------------------ auth (M01)
    # SecretStr so an accidental log line or repr prints '**********' rather than the key that
    # mints tokens for every account in the system.
    jwt_secret: SecretStr = SecretStr("local-development-secret-not-for-any-real-environment")
    # Short, because an access token cannot be revoked — only outlived. Everything that must take
    # effect immediately (deactivation, role change) is enforced against the session row on
    # refresh, so this value is the worst-case window, not the norm.
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    # Argon2id cost. Tunable rather than hardcoded because the pilot's hardware is not this
    # machine: the M01 spec requires login to stay under 400ms on the real container.
    argon2_time_cost: int = 3
    argon2_memory_cost_kib: int = 65536
    argon2_parallelism: int = 4

    # docs/security.md A07, backlog-issues B5 (decision D28). No automatic lock: a stranger who knew
    # a waiter's phone number could lock them out mid-service, and "locked" told the stranger the
    # login was real. Instead each wrong password for one login waits longer than the last — 1s, 2s,
    # 4s… from the third, never more than the cap — and one network that keeps failing is refused
    # for a while. A lock is set only by a person.
    login_delay_after_failures: int = 3
    login_delay_max_seconds: int = 30
    login_failure_window_minutes: int = 15
    login_ip_budget: int = 30
    login_ip_window_minutes: int = 10

    # M10, docs/security.md: "Aggressive per-IP and per-token rate limits" on the guest surface,
    # and the write side tighter than the read side because "feedback and order endpoints are
    # write-limited to prevent spam and rating manipulation".
    #
    # The numbers are per address per minute, chosen against what a *table* does rather than what a
    # server can serve. A party of six scanning the menu, browsing, opening a few dishes and asking
    # for the bill is a few dozen reads over an hour; sixty a minute is far above that and far below
    # what a scraper needs to be useful. Writes are a session, a rating and possibly a consent
    # withdrawal — six a minute is generous for a person and useless for a bot trying to move a
    # waiter's average.
    #
    # In-process, and therefore a floor rather than a defence (`app/core/rate_limit.py` says so at
    # length, and `docs/backlog.md` carries the shared-store follow-up with its trigger).
    guest_read_per_minute: int = 60
    guest_write_per_minute: int = 6

    # ------------------------------------------------------------- storage (M11)
    # ADR 0005: "S3-compatible object storage", with media URLs "pre-signed through a storage
    # abstraction, never constructed from a provider-specific host". Two drivers behind that
    # abstraction, chosen here (owner's decision, 2026-09-18).
    #
    # `filesystem` is not a development shortcut - it is what staging runs until a bucket exists,
    # and it is a real deployment's real driver. Its limitation is that Cloud Run's writable
    # filesystem is /tmp, which is memory: an upload does not survive the instance recycling. That
    # is stated at the top of the M11 manual script rather than discovered on the second day.
    #
    # `storage_root` empty means "somewhere sensible" - a directory under the system temp dir -
    # which is correct locally, in tests and on Cloud Run alike. Set it explicitly to keep files
    # on a mounted volume.
    storage_driver: StorageDriver = StorageDriver.FILESYSTEM
    storage_root: str = ""
    storage_bucket: str = ""
    # R2 wants an account endpoint, GCS wants storage.googleapis.com, MinIO wants a host and port.
    # Never constructed from a provider name - ADR 0005's actual words.
    storage_endpoint: str = ""
    # SigV4 needs *a* region string whether or not the provider has regions. R2 says `auto`.
    storage_region: str = "auto"
    storage_access_key: str = ""
    # SecretStr for the reason jwt_secret is: an accidental log line prints asterisks rather than
    # the key that can read every file in the bucket.
    storage_secret_key: SecretStr = SecretStr("")
    # Five minutes. Long enough for a phone on a bad connection to finish a 5 MB photograph, short
    # enough that a URL copied out of a browser's network tab is stale before it is useful.
    storage_url_ttl_seconds: int = 300
    # A phone photograph is 2-5 MB. Ten leaves room for a PDF invoice and refuses a video, which
    # is the thing that would quietly make storage the largest line on the bill.
    storage_max_bytes: int = 10 * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_local(self) -> bool:
        return self.env is Environment.LOCAL

    @model_validator(mode="after")
    def _debug_is_local_only(self) -> Settings:
        # Debug mode outside local leaks internals and disables safety rails. The M00 spec makes
        # this a startup assertion rather than a checklist item, because checklists get skipped.
        if self.debug and self.env is not Environment.LOCAL:
            raise ValueError(f"DEBUG=true is forbidden when ENV={self.env.value}")
        return self

    @model_validator(mode="after")
    def _s3_storage_needs_its_credentials(self) -> Settings:
        # The M00 rule, applied to the newest subsystem: a misconfiguration fails the boot rather
        # than the first upload. Without this, STORAGE_DRIVER=s3 with a missing secret starts
        # cleanly and then refuses every attachment with a signature error nobody can read.
        if self.storage_driver is not StorageDriver.S3:
            return self
        missing = [
            name
            for name, value in (
                ("STORAGE_BUCKET", self.storage_bucket),
                ("STORAGE_ENDPOINT", self.storage_endpoint),
                ("STORAGE_ACCESS_KEY", self.storage_access_key),
                ("STORAGE_SECRET_KEY", self.storage_secret_key.get_secret_value()),
            )
            if not value
        ]
        if missing:
            raise ValueError("STORAGE_DRIVER=s3 needs " + ", ".join(sorted(missing)))
        return self

    @model_validator(mode="after")
    def _database_url_must_be_async(self) -> Settings:
        # A sync driver here would block the event loop under load and only show up as latency.
        if not self.database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// driver")
        return self

    # Declared last deliberately: model_validator(mode="after") runs in definition order, and a
    # DEBUG or DATABASE_URL mistake is the more fundamental misconfiguration. Reporting the JWT
    # secret first would bury it.
    @model_validator(mode="after")
    def _real_environments_need_a_real_jwt_secret(self) -> Settings:
        # The default is in this repository: anyone who can read the source could otherwise mint
        # an owner token for any restaurant. Staging and production must set their own.
        secret = self.jwt_secret.get_secret_value()
        if self.env is not Environment.LOCAL and "local-development" in secret:
            raise ValueError(f"JWT_SECRET must be set explicitly when ENV={self.env.value}")
        # RFC 7518 §3.2: an HS256 key shorter than the hash output weakens the signature. PyJWT
        # only warns about this, and a warning in production is a thing nobody reads — so a short
        # secret fails the boot instead.
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes")
        return self


@lru_cache
def get_settings() -> Settings:
    """Settings are read once; the cache is what makes them a singleton."""
    return Settings()
