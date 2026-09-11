"""Loads and validates the access-control catalogue in permissions.json.

The JSON file is the editable source of truth; this module is the typed, validated view of it that
the rest of the application uses. Validation happens at import time, so a malformed catalogue fails
the boot in the same way a malformed Settings does — loudly, before anyone depends on it.

`PermissionCode` exists so route declarations are checked by mypy. A route asking for a permission
string that is not in the catalogue would otherwise be a permission no role can hold, which reads
as "mysteriously denied" rather than as an error.
"""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator

_CATALOGUE_PATH = Path(__file__).with_name("permissions.json")

# Fail closed: anything we cannot identify is treated as the least senior thing there is.
MOST_JUNIOR_RANK = 9_999

# The top of the ladder. Named rather than written as a bare 0 because `may_reset_password` turns
# on it, and "0" in a comparison there reads as an off-by-one rather than as "the owner".
OWNER_RANK = 0


class PermissionCode(StrEnum):
    """The permissions M01 declares. Mirrors permissions.json, asserted by a test."""

    EMPLOYEE_VIEW = "employee.view"
    EMPLOYEE_CREATE = "employee.create"
    EMPLOYEE_EDIT = "employee.edit"
    EMPLOYEE_DEACTIVATE = "employee.deactivate"
    EMPLOYEE_ROLE_ASSIGN = "employee.role.assign"
    # S105 reads any constant named *PASSWORD* as a hardcoded credential. This is a permission
    # code. Suppressed here rather than project-wide, because the rule is worth keeping.
    EMPLOYEE_PASSWORD_RESET = "employee.password.reset"  # noqa: S105
    ROLE_VIEW = "role.view"


class PermissionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    resource: str
    action: str
    description: str

    @model_validator(mode="after")
    def _code_matches_resource_and_action(self) -> PermissionSpec:
        expected = f"{self.resource}.{self.action}"
        if self.code != expected:
            raise ValueError(f"permission {self.code!r} should be {expected!r}")
        return self


class RoleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    name: str
    # Seniority. Lower is more senior; see `may_assign_rank`. This is what stops privilege
    # escalation, because permissions alone cannot: in M01 a manager and an owner hold the same
    # seven permissions, so a "you may not grant what you do not hold" rule would permit a manager
    # to make themselves an owner.
    rank: int
    description: str
    permissions: tuple[str, ...]


class Catalogue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    permissions: tuple[PermissionSpec, ...]
    roles: tuple[RoleSpec, ...]

    @model_validator(mode="after")
    def _roles_grant_only_known_permissions(self) -> Catalogue:
        # The typo guard. A role granting "employee.veiw" would otherwise be a permission nobody
        # holds, discovered by a person locked out of a screen mid-service.
        known = {permission.code for permission in self.permissions}
        for role in self.roles:
            unknown = sorted(set(role.permissions) - known)
            if unknown:
                raise ValueError(f"role {role.code!r} grants unknown permissions: {unknown}")
        return self

    @model_validator(mode="after")
    def _codes_are_unique(self) -> Catalogue:
        for label, codes in (
            ("permission", [permission.code for permission in self.permissions]),
            ("role", [role.code for role in self.roles]),
        ):
            duplicates = sorted({code for code in codes if codes.count(code) > 1})
            if duplicates:
                raise ValueError(f"duplicate {label} codes: {duplicates}")
        return self


@lru_cache
def load_catalogue() -> Catalogue:
    raw = json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    # Keys beginning with an underscore are documentation for whoever edits the file next.
    payload = {key: value for key, value in raw.items() if not key.startswith("_")}
    return Catalogue.model_validate(payload)


CATALOGUE = load_catalogue()


def permissions_for_role(role_code: str) -> frozenset[str]:
    """Every permission a role template grants. Empty for a role that has nothing to do yet."""
    for role in CATALOGUE.roles:
        if role.code == role_code:
            return frozenset(role.permissions)
    return frozenset()


def rank_for_role(role_code: str) -> int:
    """The seniority of a role. An unknown role is treated as the most junior possible, so a bad
    lookup can never accidentally confer authority."""
    for role in CATALOGUE.roles:
        if role.code == role_code:
            return role.rank
    return MOST_JUNIOR_RANK


def may_assign_rank(actor_rank: int, target_rank: int) -> bool:
    """May someone of `actor_rank` grant a role of `target_rank`?

    Sideways and downward, never upward. A manager may appoint another manager or any junior role
    — lateral appointment is not escalation — but may not create anyone more senior than
    themselves. Combined with the service's refusal to let anyone edit their own roles, this closes
    both the direct route (promote myself) and the indirect one (promote an ally, have them
    promote me).
    """
    return target_rank >= actor_rank


def may_reset_password(actor_rank: int, target_rank: int) -> bool:
    """May someone of `actor_rank` set a new password for someone of `target_rank`?

    **Stricter than `may_assign_rank`, and deliberately so.** Appointing a peer is not escalation —
    a manager may appoint another manager. *Acting as* a peer is, because a password is the ability
    to be that person: every order, void, discount and audit row afterwards names the victim, and
    nothing distinguishes it from them doing it themselves (P1-6).

    So this requires **strictly** more senior, with one exception: two owners. Rank 0 is the top of
    the ladder, and a rule of "strictly more senior" would leave co-owners unable to help each other
    and an owner locked out of their own restaurant with no recovery path at all — which in a
    business with no support desk means the product is gone.

    Note this is about *authority*, not visibility; the caller has already established that the
    actor may see the target, and `most_senior_rank_anywhere` is what it must pass as `target_rank`.
    """
    if actor_rank == OWNER_RANK and target_rank == OWNER_RANK:
        return True
    return actor_rank < target_rank
