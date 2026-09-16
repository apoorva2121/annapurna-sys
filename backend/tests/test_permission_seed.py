"""What the migration seeded must equal what the catalogue file says.

Without this test, `permissions.json` is decorative: someone edits it, nothing happens, and the
discrepancy is found when a manager cannot open a screen they were told they could. With it,
editing the file without shipping a migration fails the build and says so.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RoleCode
from app.core.permissions import CATALOGUE

_BACKEND = Path(__file__).resolve().parents[1]
_CATALOGUE_PATH = _BACKEND / "app" / "core" / "permissions.json"
_VERSIONS = _BACKEND / "alembic" / "versions"


async def _seeded_grants(session: AsyncSession) -> dict[str, set[str]]:
    rows = await session.execute(
        text(
            """
            SELECT r.code AS role_code, p.code AS permission_code
            FROM role r
            LEFT JOIN role_permission rp ON rp.role_id = r.id
            LEFT JOIN permission p ON p.id = rp.permission_id
            WHERE r.organization_id IS NULL
            """
        )
    )
    grants: dict[str, set[str]] = {role.code: set() for role in CATALOGUE.roles}
    for role_code, permission_code in rows:
        if permission_code is not None:
            grants.setdefault(role_code, set()).add(permission_code)
    return grants


async def test_every_permission_in_the_file_exists_in_the_database(
    db_session: AsyncSession,
) -> None:
    seeded = set((await db_session.scalars(text("SELECT code FROM permission"))).all())
    assert seeded == {permission.code for permission in CATALOGUE.permissions}


async def test_every_system_role_in_the_file_exists_in_the_database(
    db_session: AsyncSession,
) -> None:
    seeded = set(
        (
            await db_session.scalars(text("SELECT code FROM role WHERE organization_id IS NULL"))
        ).all()
    )
    assert seeded == {role.code for role in CATALOGUE.roles}


async def test_the_seeded_grants_match_the_file_exactly(db_session: AsyncSession) -> None:
    """The one that matters. A drift in either direction — a grant in the file that never reached
    the database, or a grant in the database no longer in the file — is a live access-control bug.
    """
    expected = {role.code: set(role.permissions) for role in CATALOGUE.roles}
    assert await _seeded_grants(db_session) == expected


async def test_system_roles_are_marked_as_system(db_session: AsyncSession) -> None:
    # is_system = true is what stops an organization deleting the templates out from under itself.
    not_system = (
        await db_session.scalars(
            text("SELECT code FROM role WHERE organization_id IS NULL AND is_system IS NOT TRUE")
        )
    ).all()
    assert not list(not_system)


async def test_a_system_role_cannot_be_seeded_twice(db_session: AsyncSession) -> None:
    """Proves the partial unique index does its job. Without it, re-running the seed against a
    database that already had roles would quietly double them, and permission resolution would
    read whichever row it happened to join."""
    duplicates = (
        await db_session.execute(
            text(
                """
                SELECT code, count(*) FROM role
                WHERE organization_id IS NULL
                GROUP BY code HAVING count(*) > 1
                """
            )
        )
    ).all()
    assert not duplicates


async def test_the_owner_role_can_do_everything_the_catalogue_defines(
    db_session: AsyncSession,
) -> None:
    grants = await _seeded_grants(db_session)
    assert grants[RoleCode.OWNER.value] == {permission.code for permission in CATALOGUE.permissions}


async def test_the_seniority_ladder_reached_the_database(db_session: AsyncSession) -> None:
    """`rank` is only a security control if the value the service reads is the one in the file.

    The service compares the actor's stored rank against the target role's stored rank. If seeding
    dropped the column, every role would sit at the same default — and a manager could appoint an
    owner, silently, with every other test still green.
    """
    rows = await db_session.execute(
        text("SELECT code, rank FROM role WHERE organization_id IS NULL")
    )
    seeded = {str(code): int(rank) for code, rank in rows.all()}
    assert seeded == {role.code: role.rank for role in CATALOGUE.roles}


# --------------------------------------------------------------- the migration is not optional


def _catalogue_fingerprint() -> str:
    """A canonical hash of the catalogue's *content*.

    `_`-prefixed keys are excluded, so editing the readme does not demand a migration; keys are
    sorted and separators fixed, so reformatting the file does not either. Anything that changes
    who can do what does change this.
    """
    raw = json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    catalogue = {key: value for key, value in raw.items() if not key.startswith("_")}
    canonical = json.dumps(catalogue, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _declared_fingerprints() -> dict[str, str]:
    """Every `CATALOGUE_FINGERPRINT` declared by a migration, keyed by file name."""
    found: dict[str, str] = {}
    for path in _VERSIONS.glob("*.py"):
        match = re.search(
            r"^CATALOGUE_FINGERPRINT\s*=\s*[\"']([^\"']+)[\"']",
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if match is not None:
            found[path.name] = match.group(1)
    return found


def test_the_current_catalogue_has_a_migration_that_seeds_it() -> None:
    """Editing `permissions.json` without shipping a migration must fail the build.

    The three tests above cannot catch that, and it took M02 to notice. They compare the database
    against the file — but the database is built by running migrations, and migration 0002 *reads
    the file*, so a fresh database always agrees with whatever the file says. Adding a permission
    and shipping no migration left all of them green.

    The case they miss is the only one that matters: a database that has already run 0002. Alembic
    will not run it again, the new permission never arrives, and owner and admin quietly lack it in
    staging while every test passes locally.

    So this compares the file against the *migrations* instead. To fix a failure here, add a
    migration that reconciles the catalogue and declare the new fingerprint in it — copy
    `0005_m02_restaurant_configure.py`, which exists for exactly this reason.
    """
    current = _catalogue_fingerprint()
    declared = _declared_fingerprints()

    assert current in declared.values(), (
        f"permissions.json has changed and no migration seeds this version of it.\n"
        f"  current catalogue: {current}\n"
        f"  declared by migrations: {declared or 'none'}\n"
        f"Add a migration that reconciles the catalogue and set CATALOGUE_FINGERPRINT to the "
        f"current value. Without one, a database that already ran 0002 never receives the change."
    )
