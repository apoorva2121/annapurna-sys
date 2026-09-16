"""issue catalogue - a number and plain words for every error a person can meet

Backlog-issues B12 (owner decisions D11, D12). Creates `issue` and copies the catalogue into it from a
frozen copy of app/core/issues.json, so this migration applies the catalogue it was written against.
A later change to the catalogue ships its own migration declaring the new ISSUES_FINGERPRINT.

Revision ID: 0029_issue_catalogue
Revises: 0028_catalogue_descriptions
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_issue_catalogue"
down_revision: str | None = "0028_catalogue_descriptions"
branch_labels: str | None = None
depends_on: str | None = None

ISSUES_FINGERPRINT = "sha256:830048a839a395386de70209ad52dde4f43490bac10b48828ae2d728702930bd"

_CATALOGUE_PATH = Path(__file__).resolve().parents[1] / "catalogues" / "0029_issue_catalogue.json"


def upgrade() -> None:
    op.create_table(
        "issue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("number", name="uq_issue_number"),
        sa.UniqueConstraint("code", name="uq_issue_code"),
    )
    catalogue: dict[str, Any] = json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    connection = op.get_bind()
    for issue in catalogue["issues"]:
        connection.execute(
            sa.text(
                "INSERT INTO issue (id, number, code, text) VALUES (:id, :number, :code, :text)"
            ),
            {"id": uuid.uuid4(), **issue},
        )


def downgrade() -> None:
    op.drop_table("issue")
