"""Application settings, validated once at startup.

A bad configuration fails the boot loudly here rather than surfacing as a mystery 500 in week
three. Every value the application needs is declared on this model; nothing reads os.environ
directly.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


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
    sentry_dsn: str | None = None
    # Injected by the image build; "unknown" locally is honest rather than misleading.
    git_sha: str = "unknown"
    built_at: str = "unknown"

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
    def _database_url_must_be_async(self) -> Settings:
        # A sync driver here would block the event loop under load and only show up as latency.
        if not self.database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// driver")
        return self


@lru_cache
def get_settings() -> Settings:
    """Settings are read once; the cache is what makes them a singleton."""
    return Settings()
