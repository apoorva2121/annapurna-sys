"""Declarative base for every model. Table and column conventions live in docs/schema.md."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All models inherit from this so Alembic autogenerate sees one metadata object."""
