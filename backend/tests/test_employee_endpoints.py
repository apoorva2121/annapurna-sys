"""Endpoint tests for staff management: happy path, validation, permission, not-found, conflict.

The Definition of Done asks for those five per endpoint. The ones that earn the most attention here
are the escalation guards, because granting `employee.role.assign` to managers is what makes them
necessary — a manager who can appoint people is one bug away from being able to appoint themselves.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EmploymentType, UserAccountStatus
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.audit import AuditLog
from app.models.identity import Employee, UserAccount, UserSession
from app.models.tenancy import Organization, Restaurant

PASSWORD = "Staging#2026"  # noqa: S105


class World:
    """One organization, one restaurant, and a person per role that the tests need."""

    def __init__(self, organization: Organization, restaurant: Restaurant) -> None:
        self.organization = organization
        self.restaurant = restaurant
        self.employees: dict[str, Employee] = {}


async def _role(session: AsyncSession, code: str) -> Role:
    role = (
        await session.scalars(select(Role).where(Role.code == code, Role.organization_id.is_(None)))
    ).first()
    assert role is not None
    return role


async def _world(session: AsyncSession, *roles: str, slug: str = "spice-garden") -> World:
    organization = Organization(name=slug.title(), slug=slug)
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(organization_id=organization.id, name=slug.title(), code="R1")
    session.add(restaurant)
    await session.flush()
    world = World(organization, restaurant)

    for index, role_code in enumerate(roles):
        role = await _role(session, role_code)
        account = UserAccount(
            organization_id=organization.id,
            email=f"{role_code}@{slug}.test",
            password_hash=hash_password(PASSWORD),
            status=UserAccountStatus.ACTIVE,
        )
        session.add(account)
        await session.flush()
        employee = Employee(
            organization_id=organization.id,
            user_account_id=account.id,
            employee_code=f"E{index:03d}",
            full_name=f"{role_code.replace('_', ' ').title()}",
            joined_on=date(2026, 1, 1),
            employment_type=EmploymentType.FULL_TIME,
        )
        session.add(employee)
        await session.flush()
        session.add(
            EmployeeRoleAssignment(
                employee_id=employee.id, restaurant_id=restaurant.id, role_id=role.id
            )
        )
        await session.flush()
        world.employees[role_code] = employee
    await session.commit()
    return world


async def _token(client: AsyncClient, role_code: str, slug: str = "spice-garden") -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"identifier": f"{role_code}@{slug}.test", "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _audit_actions(session: AsyncSession) -> list[str]:
    return list((await session.scalars(select(AuditLog.action))).all())


class TestListing:
    async def test_an_owner_sees_the_staff_list(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "owner")

        response = await api_client.get("/api/v1/staff/employees", headers=_auth(token))

        assert response.status_code == 200
        assert {item["full_name"] for item in response.json()["items"]} == {"Owner", "Waiter"}

    async def test_the_list_reports_each_person_s_roles(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        # The screen shows a role per row; without this the client would have to guess.
        await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "owner")

        response = await api_client.get("/api/v1/staff/employees", headers=_auth(token))

        by_name = {item["full_name"]: item for item in response.json()["items"]}
        assert by_name["Waiter"]["roles"] == ["waiter"]

    async def test_a_waiter_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "waiter")

        response = await api_client.get("/api/v1/staff/employees", headers=_auth(token))

        assert response.status_code == 403

    async def test_the_denial_does_not_name_the_missing_permission(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        # Telling a waiter the exact string that unlocks a screen is a map of the permission model.
        await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "waiter")

        response = await api_client.get("/api/v1/staff/employees", headers=_auth(token))

        assert "employee.view" not in response.text

    async def test_deactivated_staff_are_hidden_by_default_and_findable_on_request(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "owner")
        await api_client.post(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}/deactivate",
            headers=_auth(token),
        )

        active = await api_client.get("/api/v1/staff/employees", headers=_auth(token))
        everyone = await api_client.get(
            "/api/v1/staff/employees?include_inactive=true", headers=_auth(token)
        )

        assert {item["full_name"] for item in active.json()["items"]} == {"Owner"}
        assert {item["full_name"] for item in everyone.json()["items"]} == {"Owner", "Waiter"}


class TestCreate:
    async def test_a_manager_can_add_an_employee(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "manager")
        token = await _token(api_client, "manager")

        response = await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(token),
            json={
                "full_name": "Test Waiter",
                "employee_code": "W100",
                "joined_on": "2026-09-10",
                "phone": "9000000001",
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["full_name"] == "Test Waiter"
        assert response.json()["has_login"] is False

    async def test_an_employee_can_be_created_with_no_login(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 10 / ADR 0007. A cleaner referenced by tasks and shifts who never
        signs in must be a normal thing to create, not a workaround."""
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(token),
            json={"full_name": "Night Cleaner", "employee_code": "C1", "joined_on": "2026-09-10"},
        )

        assert response.status_code == 201
        assert response.json()["has_login"] is False

    async def test_creating_with_a_login_makes_that_person_able_to_sign_in(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(token),
            json={
                "full_name": "New Manager",
                "employee_code": "M9",
                "joined_on": "2026-09-10",
                "login_identifier": "9000000002",
                "initial_password": "TheirPassword#1",
            },
        )

        # No role yet, so login is refused for that reason and not for a credential reason —
        # which is the manager-creates-staff window working as designed.
        response = await api_client.post(
            "/api/v1/auth/login",
            json={"identifier": "9000000002", "password": "TheirPassword#1"},
        )
        assert response.json()["code"] == "auth.no_restaurant"

    @pytest.mark.parametrize(
        ("field", "value"),
        [("full_name", ""), ("phone", "12345"), ("employee_code", "")],
    )
    async def test_invalid_input_is_rejected_with_a_field_error(
        self, db_session: AsyncSession, api_client: AsyncClient, field: str, value: str
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        payload: dict[str, Any] = {
            "full_name": "Someone",
            "employee_code": "X1",
            "joined_on": "2026-09-10",
        }
        payload[field] = value

        response = await api_client.post(
            "/api/v1/staff/employees", headers=_auth(token), json=payload
        )

        assert response.status_code == 422
        assert response.json()["code"] == "request.invalid"

    async def test_an_unknown_field_is_rejected(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        # extra="forbid": mass assignment must be impossible, so `is_active` cannot be smuggled in.
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(token),
            json={
                "full_name": "Someone",
                "employee_code": "X1",
                "joined_on": "2026-09-10",
                "is_active": False,
                "organization_id": "00000000-0000-0000-0000-000000000009",
            },
        )

        assert response.status_code == 422

    async def test_a_duplicate_employee_code_is_a_clear_conflict(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        payload = {"full_name": "First", "employee_code": "DUP", "joined_on": "2026-09-10"}
        await api_client.post("/api/v1/staff/employees", headers=_auth(token), json=payload)

        response = await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(token),
            json=payload | {"full_name": "Second"},
        )

        assert response.status_code == 409
        assert response.json()["code"] == "employee.code_taken"

    async def test_a_phone_already_in_use_is_a_clear_conflict(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        # Manual test B6.
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        first = {
            "full_name": "First",
            "employee_code": "P1",
            "joined_on": "2026-09-10",
            "login_identifier": "9000000003",
            "initial_password": "SomePassword#1",
        }
        await api_client.post("/api/v1/staff/employees", headers=_auth(token), json=first)

        response = await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(token),
            json=first | {"employee_code": "P2", "full_name": "Second"},
        )

        assert response.status_code == 409
        assert response.json()["code"] == "employee.login_taken"

    async def test_creating_writes_an_audit_row(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(token),
            json={"full_name": "Audited", "employee_code": "A1", "joined_on": "2026-09-10"},
        )

        assert "employee.create" in await _audit_actions(db_session)


class TestDeactivation:
    async def test_deactivating_revokes_every_session_immediately(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Acceptance criterion 4 and manual probe D3. The dismissed person's open tab must stop
        working on their next request, not at their next login."""
        world = await _world(db_session, "owner", "waiter")
        waiter_token = await _token(api_client, "waiter")
        owner_token = await _token(api_client, "owner")
        # Prove the waiter's session was live before the deactivation.
        assert (
            await api_client.get("/api/v1/auth/me", headers=_auth(waiter_token))
        ).status_code == 200

        await api_client.post(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}/deactivate",
            headers=_auth(owner_token),
        )

        after = await api_client.get("/api/v1/auth/me", headers=_auth(waiter_token))
        assert after.status_code == 401

    async def test_the_refresh_token_dies_too(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        # Otherwise the access token expires and the browser quietly gets a new one.
        world = await _world(db_session, "owner", "waiter")
        await _token(api_client, "waiter")
        owner_token = await _token(api_client, "owner")

        await api_client.post(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}/deactivate",
            headers=_auth(owner_token),
        )

        live = (
            await db_session.scalars(select(UserSession).where(UserSession.revoked_at.is_(None)))
        ).all()
        revoked_account = world.employees["waiter"].user_account_id
        assert all(row.user_account_id != revoked_account for row in live)

    async def test_the_row_is_kept_not_deleted(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        # ADR 0008 master-data tier. Manual test A7.
        world = await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}/deactivate",
            headers=_auth(token),
        )

        assert response.status_code == 200
        assert response.json()["is_active"] is False
        assert response.json()["deactivated_at"] is not None

    async def test_you_cannot_deactivate_yourself(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        # Locking yourself out mid-service is never the intent, and can leave nobody able to sign
        # in at all.
        world = await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['owner'].id}/deactivate",
            headers=_auth(token),
        )

        assert response.status_code == 400
        assert response.json()["code"] == "employee.cannot_deactivate_self"

    async def test_a_manager_cannot_deactivate_an_owner(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The seniority ladder applied to dismissal. Without it, a manager could remove the owner
        from their own restaurant."""
        world = await _world(db_session, "owner", "manager")
        token = await _token(api_client, "manager")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['owner'].id}/deactivate",
            headers=_auth(token),
        )

        assert response.status_code == 403
        assert response.json()["code"] == "employee.more_senior"

    async def test_reactivating_restores_access(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "owner")
        waiter_id = world.employees["waiter"].id
        await api_client.post(
            f"/api/v1/staff/employees/{waiter_id}/deactivate", headers=_auth(token)
        )

        response = await api_client.post(
            f"/api/v1/staff/employees/{waiter_id}/reactivate", headers=_auth(token)
        )

        assert response.json()["is_active"] is True
        assert (await _token(api_client, "waiter")) is not None


class TestTheEscalationGuards:
    """The reason granting managers `employee.role.assign` is safe.

    Each test here is one of the two routes to becoming more powerful than you should be. They are
    the highest-value tests in this file: everything else fails visibly, whereas an escalation hole
    works perfectly and is discovered by its consequences.
    """

    async def test_a_manager_cannot_appoint_an_owner(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner", "manager", "waiter")
        token = await _token(api_client, "manager")
        owner_role = await _role(db_session, "owner")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}/roles",
            headers=_auth(token),
            json={"role_ids": [str(owner_role.id)]},
        )

        assert response.status_code == 403
        assert response.json()["code"] == "employee.role_too_senior"

    async def test_a_manager_cannot_change_their_own_roles(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        # Closes the direct route, and is checked before anything else so it holds even for a
        # role the actor would otherwise be allowed to grant.
        world = await _world(db_session, "owner", "manager")
        token = await _token(api_client, "manager")
        waiter_role = await _role(db_session, "waiter")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['manager'].id}/roles",
            headers=_auth(token),
            json={"role_ids": [str(waiter_role.id)]},
        )

        assert response.status_code == 403
        assert response.json()["code"] == "employee.cannot_change_own_roles"

    async def test_a_manager_cannot_strip_an_owner_s_roles(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The denial-of-service direction. Demoting the owner is not escalation, but it would let
        a manager take over a restaurant by removing everyone above them."""
        world = await _world(db_session, "owner", "manager")
        token = await _token(api_client, "manager")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['owner'].id}/roles",
            headers=_auth(token),
            json={"role_ids": []},
        )

        assert response.status_code == 403

    async def test_a_manager_can_appoint_a_waiter(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        # The whole point of the change: a manager staffs their own shift.
        world = await _world(db_session, "owner", "manager", "chef")
        token = await _token(api_client, "manager")
        waiter_role = await _role(db_session, "waiter")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['chef'].id}/roles",
            headers=_auth(token),
            json={"role_ids": [str(waiter_role.id)]},
        )

        assert response.status_code == 200, response.text
        assert response.json()["roles"] == ["waiter"]

    async def test_a_manager_can_appoint_another_manager(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        # Lateral appointment is not escalation.
        world = await _world(db_session, "owner", "manager", "waiter")
        token = await _token(api_client, "manager")
        manager_role = await _role(db_session, "manager")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}/roles",
            headers=_auth(token),
            json={"role_ids": [str(manager_role.id)]},
        )

        assert response.status_code == 200

    async def test_an_owner_can_appoint_anyone(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "owner")
        admin_role = await _role(db_session, "admin")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}/roles",
            headers=_auth(token),
            json={"role_ids": [str(admin_role.id)]},
        )

        assert response.status_code == 200

    async def test_a_role_change_revokes_the_affected_person_s_sessions(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A demotion must not wait for a token to expire, or the demoted person keeps their old
        permissions for up to the access-token lifetime."""
        world = await _world(db_session, "owner", "chef")
        chef_token = await _token(api_client, "chef")
        owner_token = await _token(api_client, "owner")
        waiter_role = await _role(db_session, "waiter")

        await api_client.post(
            f"/api/v1/staff/employees/{world.employees['chef'].id}/roles",
            headers=_auth(owner_token),
            json={"role_ids": [str(waiter_role.id)]},
        )

        after = await api_client.get("/api/v1/staff/employees", headers=_auth(chef_token))
        assert after.status_code == 403

    async def test_assigning_writes_an_audit_row_with_before_and_after(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """What makes the owner-visibility promise real. M14 turns these rows into notifications;
        the event has to exist from the moment it happens or there is nothing to notify about."""
        world = await _world(db_session, "owner", "chef")
        token = await _token(api_client, "owner")
        waiter_role = await _role(db_session, "waiter")

        await api_client.post(
            f"/api/v1/staff/employees/{world.employees['chef'].id}/roles",
            headers=_auth(token),
            json={"role_ids": [str(waiter_role.id)]},
        )

        row = (
            await db_session.scalars(
                select(AuditLog).where(AuditLog.action == "employee.role.assign")
            )
        ).first()
        assert row is not None
        assert row.old_value == {"roles": ["chef"]}
        assert row.new_value == {"roles": ["waiter"]}
        assert row.actor_employee_id == world.employees["owner"].id

    async def test_a_role_from_another_organization_cannot_be_assigned(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner", "waiter")
        other = await _world(db_session, "owner", slug="tandoor-house")
        foreign_role = Role(
            organization_id=other.organization.id, code="custom", name="Custom", rank=5
        )
        db_session.add(foreign_role)
        await db_session.commit()
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}/roles",
            headers=_auth(token),
            json={"role_ids": [str(foreign_role.id)]},
        )

        assert response.status_code == 404


class TestPasswordReset:
    async def test_an_owner_can_reset_a_staff_password(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}/password",
            headers=_auth(token),
            json={"new_password": "BrandNewPass#1"},
        )

        assert response.status_code == 204
        login = await api_client.post(
            "/api/v1/auth/login",
            json={"identifier": "waiter@spice-garden.test", "password": "BrandNewPass#1"},
        )
        assert login.status_code == 200

    async def test_a_manager_cannot_reset_an_owner_s_password(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Without the seniority check this is a complete account takeover: reset the owner's
        password, then sign in as them."""
        world = await _world(db_session, "owner", "manager")
        token = await _token(api_client, "manager")

        response = await api_client.post(
            f"/api/v1/staff/employees/{world.employees['owner'].id}/password",
            headers=_auth(token),
            json={"new_password": "TakenOver#1"},
        )

        assert response.status_code == 403

    async def test_a_reset_clears_a_lockout(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        # Otherwise the fix for "I am locked out" does not actually fix it.
        world = await _world(db_session, "owner", "waiter")
        for _ in range(5):
            await api_client.post(
                "/api/v1/auth/login",
                json={"identifier": "waiter@spice-garden.test", "password": "wrong"},
            )
        token = await _token(api_client, "owner")

        await api_client.post(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}/password",
            headers=_auth(token),
            json={"new_password": "BrandNewPass#1"},
        )

        login = await api_client.post(
            "/api/v1/auth/login",
            json={"identifier": "waiter@spice-garden.test", "password": "BrandNewPass#1"},
        )
        assert login.status_code == 200

    async def test_resetting_an_employee_with_no_login_is_a_clear_error(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        created = await api_client.post(
            "/api/v1/staff/employees",
            headers=_auth(token),
            json={"full_name": "No Login", "employee_code": "N1", "joined_on": "2026-09-10"},
        )

        response = await api_client.post(
            f"/api/v1/staff/employees/{created.json()['id']}/password",
            headers=_auth(token),
            json={"new_password": "BrandNewPass#1"},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "employee.no_login"


class TestUpdateAndFetch:
    async def test_an_owner_can_edit_a_name(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "owner")

        response = await api_client.patch(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}",
            headers=_auth(token),
            json={"full_name": "Renamed Person"},
        )

        assert response.status_code == 200
        assert response.json()["full_name"] == "Renamed Person"

    async def test_a_missing_employee_is_a_404(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.get(
            "/api/v1/staff/employees/00000000-0000-0000-0000-0000000000ff",
            headers=_auth(token),
        )

        assert response.status_code == 404

    async def test_an_update_writes_an_audit_row(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "owner")

        await api_client.patch(
            f"/api/v1/staff/employees/{world.employees['waiter'].id}",
            headers=_auth(token),
            json={"full_name": "Renamed"},
        )

        assert "employee.update" in await _audit_actions(db_session)


class TestNoSecretsInAnyResponse:
    """Acceptance criterion 11, asserted on real response bodies rather than on the schema."""

    async def test_no_response_contains_a_hash_or_a_token_field(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "owner")

        bodies = [
            (await api_client.get("/api/v1/staff/employees", headers=_auth(token))).text,
            (
                await api_client.get(
                    f"/api/v1/staff/employees/{world.employees['waiter'].id}",
                    headers=_auth(token),
                )
            ).text,
            (await api_client.get("/api/v1/auth/me", headers=_auth(token))).text,
            (
                await api_client.post(
                    "/api/v1/auth/login",
                    json={"identifier": "owner@spice-garden.test", "password": PASSWORD},
                )
            ).text,
        ]

        for body in bodies:
            for forbidden in (
                "password_hash",
                "refresh_token_hash",
                "mfa_secret",
                "$argon2",
                PASSWORD,
            ):
                assert forbidden not in body, f"{forbidden} appeared in a response body"


class TestRolesCatalogue:
    async def test_the_role_list_is_ordered_by_seniority(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.get("/api/v1/staff/roles", headers=_auth(token))

        ranks = [role["rank"] for role in response.json()]
        assert ranks == sorted(ranks)
        assert response.json()[0]["code"] == "owner"

    async def test_the_permission_catalogue_explains_each_permission(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        # The assignment screen shows what a grant actually does, rather than an opaque string.
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.get("/api/v1/staff/permissions", headers=_auth(token))

        assert response.status_code == 200
        assert all(item["description"] for item in response.json())

    async def test_a_waiter_cannot_read_the_catalogue(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "waiter")

        response = await api_client.get("/api/v1/staff/roles", headers=_auth(token))

        assert response.status_code == 403
