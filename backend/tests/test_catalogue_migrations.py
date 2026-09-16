"""A catalogue migration applies the catalogue it was written against (backlog-issues B10).

Migrations 0002 and 0005 read `app/core/permissions.json` when they *ran*, so a database stopped at
an early revision and upgraded later applied a catalogue from the future, and 0005's wholesale
grant replacement reconciled against it. Each now reads a frozen copy under `alembic/catalogues/`,
which must hash to the fingerprint the migration declares. Migration 0028 brings every name and
description to today's catalogue, which is what makes freezing the earlier two safe: the seed tests
compare codes, grants and ranks, and nothing compared the words until the last test below.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_BACKEND = Path(__file__).resolve().parents[1]
_VERSIONS = _BACKEND / "alembic" / "versions"
_FROZEN = _BACKEND / "alembic" / "catalogues"
_LIVE = _BACKEND / "app" / "core" / "permissions.json"
_FROZEN_REVISIONS = [
    "0002_m01_identity",
    "0005_m02_restaurant_configure",
    "0028_catalogue_descriptions",
]


def _fingerprint(catalogue: dict[str, Any]) -> str:
    canonical = json.dumps(catalogue, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("revision", _FROZEN_REVISIONS)
def test_a_catalogue_migration_reads_its_own_frozen_copy(revision: str) -> None:
    source = (_VERSIONS / f"{revision}.py").read_text(encoding="utf-8")
    assert '"app" / "core" / "permissions.json"' not in source, (
        f"{revision} still reads today's catalogue"
    )

    frozen: dict[str, Any] = json.loads((_FROZEN / f"{revision}.json").read_text(encoding="utf-8"))
    declared = re.search(r'^CATALOGUE_FINGERPRINT = "([^"]+)"', source, re.MULTILINE)

    assert declared is not None, f"{revision} declares no fingerprint"
    assert _fingerprint(frozen) == declared.group(1)


async def test_every_name_and_description_in_the_file_reached_the_database(
    db_session: AsyncSession,
) -> None:
    live: dict[str, Any] = json.loads(_LIVE.read_text(encoding="utf-8"))

    permissions = dict(
        (await db_session.execute(text("SELECT code, description FROM permission"))).tuples().all()
    )
    roles = {
        str(code): (name, description)
        for code, name, description in (
            await db_session.execute(
                text("SELECT code, name, description FROM role WHERE organization_id IS NULL")
            )
        )
        .tuples()
        .all()
    }

    assert permissions == {row["code"]: row["description"] for row in live["permissions"]}
    assert roles == {row["code"]: (row["name"], row["description"]) for row in live["roles"]}
