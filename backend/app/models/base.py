"""Declarative base and the columns every table carries. Conventions live in docs/schema.md."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import uuid7


class Base(DeclarativeBase):
    """All models inherit from this so Alembic autogenerate sees one metadata object."""


class TimestampedUUIDMixin:
    """`id`, `created_at`, `updated_at` — applied to every table, never repeated in schema.md.

    The id default is Python-side (ADR 0008) rather than a database default, so a service knows an
    entity's id before it is persisted. The audit decorator and event dispatch both depend on that.

    The timestamps carry a *server* default as well, so a row inserted by a migration, a seed
    script or psql is timestamped correctly rather than getting NULL.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
