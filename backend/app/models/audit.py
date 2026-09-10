"""The audit trail. Append-only (ADR 0008, ledger tier): no update, no delete, no status.

M14 owns the service decorator, the query endpoint and the viewer screen. The table lands here in
M01 because M01 creates the actions worth auditing — granting a role, deactivating a person,
resetting someone else's password — and those are exactly what an insider would use. Waiting twelve
modules for the table would mean the highest-privilege actions in the product go unrecorded for the
whole build.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampedUUIDMixin


class AuditLog(TimestampedUUIDMixin, Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_restaurant_time", "restaurant_id", "occurred_at"),
        # "Who changed this record?" — the question an owner actually asks.
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_actor", "restaurant_id", "actor_employee_id", "occurred_at"),
    )

    # Nullable: organization-level actions (creating a restaurant, editing an org-wide role) have
    # no single restaurant to attribute them to.
    restaurant_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id")
    )
    # Nullable so a failed login or a system action is still recordable. An unattributed row is
    # worth more than no row.
    actor_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("employee.id")
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    # Before and after. Never contains a password hash or a token — the redaction happens at the
    # call site, because this table is readable by anyone holding the audit permission.
    old_value: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    new_value: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    audit_metadata: Mapped[dict[str, object] | None] = mapped_column("metadata", JSONB)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
