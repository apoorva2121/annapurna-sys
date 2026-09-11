"""Demo data. `make seed` runs this; the full 120-day generator arrives in M15.

M01 seeds identity only — organizations, restaurants, logins and staff — because that is what
exists to be seeded. Menu, recipes, stock and orders have no tables yet.
"""

from __future__ import annotations

from app.seed.identity import MissingSystemRoleError, SeedSummary, seed_identity
from app.seed.loader import SeedData, SeedDataNotFoundError, load_seed_data

__all__ = [
    "MissingSystemRoleError",
    "SeedData",
    "SeedDataNotFoundError",
    "SeedSummary",
    "load_seed_data",
    "seed_identity",
    "seed_password",
]


def seed_password() -> str:
    """The password every seeded login shares.

    A function rather than a module constant, because a constant would read the YAML at import
    time — making this package unimportable wherever the data is not mounted, and putting file IO
    on the path of any tool that merely wants the routing table. The same mistake, in the same
    shape, as the decoy hash this module's build log records as defect 7.

    Read from the YAML rather than duplicated here, so `docs/manual-tests/M01-identity.md`,
    `seed/organization.yaml` and the tests cannot drift into naming three different passwords.
    """
    return load_seed_data().password
