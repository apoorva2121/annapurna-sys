"""Roles, permissions and their bindings — the tables `require_permission()` reads.

Code never compares a role name (ADR 0007). It asks whether the actor holds `employee.view` at the
restaurant they are acting in, and the answer is computed from these four tables. The contents are
seeded by migration from `app/core/permissions.json`, so access control is version-controlled and
diffable rather than clicked into a production database.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampedUUIDMixin


class Role(TimestampedUUIDMixin, Base):
    """A named bundle of permissions.

    `organization_id IS NULL` marks a system template — the nine roles every organization starts
    from. An organization may later customise its own copy without touching the template.
    """

    __tablename__ = "role"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_role_org_code"),
        # A NULLable column in a UNIQUE constraint does not constrain the NULL rows, and system
        # roles are exactly the NULL rows — without this, "owner" could be seeded twice.
        Index(
            "uq_role_system_code",
            "code",
            unique=True,
            postgresql_where=text("organization_id IS NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("organization.id")
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Permission(TimestampedUUIDMixin, Base):
    """A static `resource.action` string. Global, not per tenant — the vocabulary is the same
    everywhere; only who holds which one differs."""

    __tablename__ = "permission"

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class RolePermission(Base):
    """The binding table. A composite primary key, so a duplicate grant is impossible rather than
    merely unlikely."""

    __tablename__ = "role_permission"

    role_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        ForeignKey("permission.id", ondelete="CASCADE"),
        primary_key=True,
    )


class EmployeeRoleAssignment(TimestampedUUIDMixin, Base):
    """One person, one restaurant, one role — per restaurant, so a manager at one branch can be a
    waiter at another (ADR 0007)."""

    __tablename__ = "employee_role_assignment"
    __table_args__ = (
        UniqueConstraint(
            "employee_id", "restaurant_id", "role_id", name="uq_assignment_employee_restaurant_role"
        ),
        Index("ix_assignment_restaurant_role", "restaurant_id", "role_id"),
        # The hot path: "what may this person do at this restaurant?", asked on every request.
        Index("ix_assignment_employee_restaurant", "employee_id", "restaurant_id"),
    )

    employee_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("employee.id"), nullable=False
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("role.id"), nullable=False
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("employee.id")
    )
