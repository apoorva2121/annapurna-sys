"""The permission catalogue is data, so its integrity is a test, not a review comment.

`app/core/permissions.json` is the editable source of truth for who can do what. A typo in a role's
grant list is invisible at runtime — the permission simply is not granted, and someone discovers it
mid-service. These tests make that typo fail the build instead.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from app.core.enums import RoleCode
from app.core.permissions import (
    CATALOGUE,
    Catalogue,
    PermissionCode,
    permissions_for_role,
)

_VALID_PERMISSION = {
    "code": "employee.view",
    "resource": "employee",
    "action": "view",
    "description": "See the staff list.",
}


def _catalogue(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "permissions": [_VALID_PERMISSION],
        "roles": [
            {
                "code": "owner",
                "name": "Owner",
                "description": "Holds everything.",
                "permissions": ["employee.view"],
            }
        ],
    }
    return base | overrides


def test_every_permission_code_matches_its_resource_and_action() -> None:
    # The code is the contract used in require_permission("employee.view"); resource and action
    # exist so the admin UI can group them. They must not be able to disagree.
    for permission in CATALOGUE.permissions:
        assert permission.code == f"{permission.resource}.{permission.action}"


def test_permission_codes_are_unique() -> None:
    codes = [permission.code for permission in CATALOGUE.permissions]
    assert len(codes) == len(set(codes))


def test_every_system_role_in_the_schema_is_present() -> None:
    # docs/schema.md §1 fixes the nine system roles. A role missing here cannot be assigned.
    assert {role.code for role in CATALOGUE.roles} == {member.value for member in RoleCode}


def test_no_role_grants_a_permission_that_does_not_exist() -> None:
    """The typo guard. This is the test that earns the file."""
    known = {permission.code for permission in CATALOGUE.permissions}
    for role in CATALOGUE.roles:
        dangling = set(role.permissions) - known
        assert not dangling, f"role {role.code} grants unknown permissions: {sorted(dangling)}"


def test_owner_holds_every_permission() -> None:
    # An owner who cannot do something in their own restaurant is a support call, and there is no
    # higher role to fix it from.
    assert permissions_for_role(RoleCode.OWNER) == {
        permission.code for permission in CATALOGUE.permissions
    }


def test_only_owner_and_admin_can_assign_roles() -> None:
    # The escalation path. No operational role may hold this (M01 spec, threat table).
    holders = {
        role.code
        for role in CATALOGUE.roles
        if PermissionCode.EMPLOYEE_ROLE_ASSIGN in role.permissions
    }
    assert holders == {RoleCode.OWNER.value, RoleCode.ADMIN.value}


@pytest.mark.parametrize(
    "role_code",
    [RoleCode.WAITER, RoleCode.KITCHEN_STAFF, RoleCode.CLEANER, RoleCode.STORE_MANAGER],
)
def test_operational_roles_cannot_read_the_staff_list(role_code: RoleCode) -> None:
    # Staff records carry phone numbers and dates of birth. Least privilege, and the reason the
    # M00 redaction filter was built before any PII existed.
    assert PermissionCode.EMPLOYEE_VIEW not in permissions_for_role(role_code)


def test_manager_can_staff_a_shift_but_not_promote_anyone() -> None:
    # The approved decision: a manager runs the floor at 7am when the owner is not there, but
    # cannot make themselves an owner.
    manager = permissions_for_role(RoleCode.MANAGER)
    assert PermissionCode.EMPLOYEE_CREATE in manager
    assert PermissionCode.EMPLOYEE_PASSWORD_RESET in manager
    assert PermissionCode.EMPLOYEE_ROLE_ASSIGN not in manager


class TestTheGuardsActuallyFire:
    """The tests above assert the shipped catalogue is clean, which they would do just as happily
    if the validators were deleted. These prove the validators reject a bad catalogue."""

    def test_a_role_granting_an_unknown_permission_is_rejected(self) -> None:
        broken = _catalogue(
            roles=[
                {
                    "code": "owner",
                    "name": "Owner",
                    "description": "Holds everything.",
                    # The realistic failure: a transposition nobody notices in review.
                    "permissions": ["employee.veiw"],
                }
            ]
        )
        with pytest.raises(ValidationError, match=re.escape("employee.veiw")):
            Catalogue.model_validate(broken)

    def test_a_permission_code_disagreeing_with_its_parts_is_rejected(self) -> None:
        broken = _catalogue(
            permissions=[_VALID_PERMISSION | {"code": "employee.read"}],
            roles=[],
        )
        with pytest.raises(ValidationError, match=re.escape("employee.view")):
            Catalogue.model_validate(broken)

    def test_duplicate_permission_codes_are_rejected(self) -> None:
        # Two rows with one code means the later edit silently wins, and which one is undefined.
        broken = _catalogue(permissions=[_VALID_PERMISSION, _VALID_PERMISSION])
        with pytest.raises(ValidationError, match="duplicate permission codes"):
            Catalogue.model_validate(broken)

    def test_duplicate_role_codes_are_rejected(self) -> None:
        role = {
            "code": "owner",
            "name": "Owner",
            "description": "Holds everything.",
            "permissions": ["employee.view"],
        }
        with pytest.raises(ValidationError, match="duplicate role codes"):
            Catalogue.model_validate(_catalogue(roles=[role, role]))

    def test_an_unknown_field_is_rejected(self) -> None:
        # extra="forbid": a renamed key must fail rather than fall back to a default.
        with pytest.raises(ValidationError):
            Catalogue.model_validate(_catalogue(rolez=[]))


def test_an_unknown_role_grants_nothing() -> None:
    # Fail closed. A role code that is not in the catalogue — a typo, or a custom role removed
    # from the file — must resolve to no permissions rather than raising, so a bad lookup denies
    # access instead of returning a 500 that someone retries until it works.
    assert permissions_for_role("sous_chef_de_partie") == frozenset()


def test_every_permission_code_constant_exists_in_the_catalogue() -> None:
    # PermissionCode is what the code references; the JSON is what the migration seeds. If they
    # drift, a route checks a permission no role can ever hold.
    known = {permission.code for permission in CATALOGUE.permissions}
    assert {member.value for member in PermissionCode} == known
