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
    MOST_JUNIOR_RANK,
    Catalogue,
    PermissionCode,
    may_assign_rank,
    permissions_for_role,
    rank_for_role,
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
                "rank": 0,
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


def test_role_assignment_is_held_by_owner_admin_and_manager_only() -> None:
    """A manager appoints staff, because the owner is not on site at 7am. What stops that being an
    escalation path is `rank`, not this permission — see the ladder tests below."""
    holders = {
        role.code
        for role in CATALOGUE.roles
        if PermissionCode.EMPLOYEE_ROLE_ASSIGN in role.permissions
    }
    assert holders == {RoleCode.OWNER.value, RoleCode.ADMIN.value, RoleCode.MANAGER.value}


@pytest.mark.parametrize(
    "role_code",
    [RoleCode.WAITER, RoleCode.KITCHEN_STAFF, RoleCode.CLEANER, RoleCode.STORE_MANAGER],
)
def test_operational_roles_cannot_read_the_staff_list(role_code: RoleCode) -> None:
    # Staff records carry phone numbers and dates of birth. Least privilege, and the reason the
    # M00 redaction filter was built before any PII existed.
    assert PermissionCode.EMPLOYEE_VIEW not in permissions_for_role(role_code)


def test_manager_can_staff_a_shift_and_appoint_people() -> None:
    manager = permissions_for_role(RoleCode.MANAGER)
    assert PermissionCode.EMPLOYEE_CREATE in manager
    assert PermissionCode.EMPLOYEE_PASSWORD_RESET in manager
    assert PermissionCode.EMPLOYEE_ROLE_ASSIGN in manager


class TestTheSeniorityLadder:
    """`rank` is the control that makes granting employee.role.assign to a manager safe.

    Worth being explicit about why permissions alone cannot do this job: in M01 a manager and an
    owner hold the *same seven permissions*, so the usual "you may not grant a permission you do
    not hold" rule would happily let a manager make themselves an owner. The ladder is what
    distinguishes them.
    """

    def test_every_role_declares_a_rank(self) -> None:
        assert all(isinstance(role.rank, int) for role in CATALOGUE.roles)

    def test_the_owner_is_the_most_senior_role(self) -> None:
        assert rank_for_role(RoleCode.OWNER) == min(role.rank for role in CATALOGUE.roles)

    def test_a_manager_cannot_appoint_an_owner_or_an_admin(self) -> None:
        manager = rank_for_role(RoleCode.MANAGER)
        assert not may_assign_rank(manager, rank_for_role(RoleCode.OWNER))
        assert not may_assign_rank(manager, rank_for_role(RoleCode.ADMIN))

    def test_a_manager_can_appoint_junior_staff(self) -> None:
        manager = rank_for_role(RoleCode.MANAGER)
        for junior in (RoleCode.CHEF, RoleCode.WAITER, RoleCode.CLEANER, RoleCode.ACCOUNTANT):
            assert may_assign_rank(manager, rank_for_role(junior)), junior

    def test_a_manager_can_appoint_another_manager(self) -> None:
        # Lateral appointment is not escalation, and a head manager hiring a shift manager is a
        # normal Tuesday.
        manager = rank_for_role(RoleCode.MANAGER)
        assert may_assign_rank(manager, manager)

    def test_an_owner_can_appoint_anyone(self) -> None:
        owner = rank_for_role(RoleCode.OWNER)
        assert all(may_assign_rank(owner, role.rank) for role in CATALOGUE.roles)

    def test_an_unknown_role_is_treated_as_the_most_junior(self) -> None:
        # Fail closed: a role we cannot identify must never confer authority.
        assert rank_for_role("director_of_vibes") == MOST_JUNIOR_RANK
        assert not may_assign_rank(
            rank_for_role("director_of_vibes"), rank_for_role(RoleCode.OWNER)
        )


class TestTheGuardsActuallyFire:
    """The tests above assert the shipped catalogue is clean, which they would do just as happily
    if the validators were deleted. These prove the validators reject a bad catalogue."""

    def test_a_role_granting_an_unknown_permission_is_rejected(self) -> None:
        broken = _catalogue(
            roles=[
                {
                    "code": "owner",
                    "name": "Owner",
                    "rank": 0,
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
            "rank": 0,
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


def test_the_shipped_catalogue_is_a_subset_of_the_p1_design() -> None:
    """`seed/organization.yaml` carries the full permission design for M03-M17; this file
    carries the 7 that M01 actually implements.

    Finding M12 called the two a drift risk and proposed deleting the YAML block. Deleting it would
    throw away design work that later modules need, so both are kept and *this* is the guard: every
    permission the application enforces must already exist in the P1 design. A new code invented
    here without a place in the plan fails the build — which is the drift M12 was actually worried
    about. The reverse is expected and fine: the design deliberately contains permissions no module
    has built yet.
    """
    import yaml

    from app.seed.loader import find_seed_directory

    design = yaml.safe_load(
        (find_seed_directory() / "organization.yaml").read_text(encoding="utf-8")
    )
    designed = {entry["code"] for entry in design["permissions"]}
    shipped = {permission.code for permission in CATALOGUE.permissions}

    unplanned = shipped - designed
    assert not unplanned, (
        f"{sorted(unplanned)} are enforced by the application but appear nowhere in "
        "seed/organization.yaml's design. Either add them there or stop checking them."
    )


class TestTheBillAndTheTill:
    """M07. The grants that decide who can make money disappear, asserted by name because a
    permission quietly added to a waiter reads exactly like a permission correctly withheld."""

    def test_a_waiter_takes_and_settles_orders(self) -> None:
        held = permissions_for_role("waiter")
        assert {"order.view", "order.create", "order.modify", "order.settle"} <= held

    @pytest.mark.parametrize("code", ["order.void", "order.discount", "cash.manage"])
    def test_a_waiter_cannot_void_discount_or_close_the_till(self, code: str) -> None:
        """The P1 design's own phrase: "the classic leakage vectors"."""
        assert code not in permissions_for_role("waiter")

    def test_the_accountant_reads_orders_and_changes_none(self) -> None:
        held = {
            code
            for code in permissions_for_role("accountant")
            if code.startswith(("order.", "cash."))
        }
        assert held == {"order.view"}

    def test_the_manager_runs_the_floor_and_the_till(self) -> None:
        on_the_floor = {
            "order.view",
            "order.create",
            "order.modify",
            "order.settle",
            "order.void",
            "order.discount",
            "cash.manage",
        }
        assert on_the_floor <= permissions_for_role("manager")

    @pytest.mark.parametrize(
        "role_code", ["admin", "chef", "kitchen_staff", "store_manager", "cleaner"]
    )
    def test_roles_off_the_floor_hold_no_order_or_cash_permission(self, role_code: str) -> None:
        """Including `admin`, which configures the restaurant and is not in its commerce."""
        held = {
            code for code in permissions_for_role(role_code) if code.startswith(("order.", "cash."))
        }
        assert not held
