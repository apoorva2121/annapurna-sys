"""Response contracts for the operational endpoints.

SQLAlchemy models never cross the API boundary; a Pydantic schema is always the contract, even for
something as small as a health check.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


class ReadyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool
    database: bool
    migrations_at_head: bool


class VersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    git_sha: str
    built_at: str
    env: str
