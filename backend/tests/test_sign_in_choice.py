"""Signing in when one login belongs to more than one organization (backlog-issues B4, D1, D1a).

**D1:** a login is unique inside an organization, not across the product — an accountant who works
for two restaurant groups uses one phone number for both. The global uniqueness check that used to
refuse that is gone.

**D1a:** the person types their login and password first. Only if the password is right for more
than one organization's account does the screen ask which one, with a single-use pass that lasts two
minutes, so the password is never sent again. Asking before the password would tell anyone holding a
phone number which businesses that person works at.

What made the global check necessary is also gone: a tenant creating a login with somebody else's
email can no longer lock them out, because their own password still matches only their own account.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EmploymentType, UserAccountStatus
from app.core.security import decode_access_token, hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee, UserAccount
from app.models.tenancy import Organization, Restaurant
from tests.test_employee_endpoints import PASSWORD, _auth, _token, _world

LOGIN = "/api/v1/auth/login"
CHOOSE = "/api/v1/auth/login/choose"
EMPLOYEES = "/api/v1/staff/employees"
CONSULTANT = "consultant@example.test"


async def _person_in(
    session: AsyncSession,
    name: str,
    *,
    email: str | None = CONSULTANT,
    phone: str | None = None,
    password: str = PASSWORD,
    active: bool = True,
) -> Organization:
    """An organization with one person in it, who can sign in there."""
    organization = Organization(name=name, slug=name.lower().replace(" ", "-"))
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(organization_id=organization.id, name=name, code="R1")
    account = UserAccount(
        organization_id=organization.id,
        email=email,
        phone=phone,
        password_hash=await hash_password(password),
        status=UserAccountStatus.ACTIVE,
    )
    session.add_all([restaurant, account])
    await session.flush()
    employee = Employee(
        organization_id=organization.id,
        user_account_id=account.id,
        employee_code="EMP001",
        full_name="Farhan Qureshi",
        joined_on=date(2026, 1, 1),
        employment_type=EmploymentType.FULL_TIME,
        is_active=active,
    )
    session.add(employee)
    await session.flush()
    role = (
        await session.scalars(
            select(Role).where(Role.code == "accountant", Role.organization_id.is_(None))
        )
    ).one()
    session.add(
        EmployeeRoleAssignment(
            employee_id=employee.id, restaurant_id=restaurant.id, role_id=role.id
        )
    )
    await session.commit()
    return organization


def _login_body(identifier: str = CONSULTANT, password: str = PASSWORD) -> dict[str, str]:
    return {"identifier": identifier, "password": password}


def _employee(code: str, login: str) -> dict[str, Any]:
    return {
        "full_name": "Ravi Sharma",
        "employee_code": code,
        "joined_on": "2026-01-01",
        "login_identifier": login,
        "initial_password": "a-long-password-1",
    }


# --------------------------------------------------------------------------- spellings


class TestOneLoginManySpellings:
    async def test_a_phone_saved_with_spaces_signs_in_typed_without_them(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        created = await api_client.post(
            EMPLOYEES, json=_employee("EMP050", "+91 98765 43210"), headers=_auth(owner)
        )
        assert created.status_code == 201, created.text

        response = await api_client.post(LOGIN, json=_login_body("9876543210", "a-long-password-1"))

        # Past the password: a person with no role yet is told why, which only happens once the
        # login and password have matched.
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "auth.no_restaurant"

    async def test_a_second_spelling_of_the_same_phone_is_the_same_login(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")
        first = await api_client.post(
            EMPLOYEES, json=_employee("EMP050", "+91 98765 43210"), headers=_auth(owner)
        )
        assert first.status_code == 201, first.text

        second = await api_client.post(
            EMPLOYEES, json=_employee("EMP051", "09876543210"), headers=_auth(owner)
        )

        assert second.status_code == 409, second.text
        assert second.json()["code"] == "employee.login_taken"

    async def test_a_login_that_is_neither_a_phone_nor_an_email_is_refused_in_words(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        owner = await _token(api_client, "owner")

        response = await api_client.post(
            EMPLOYEES, json=_employee("EMP050", "ravi"), headers=_auth(owner)
        )

        assert response.status_code == 422, response.text
        fields = [problem["field"] for problem in response.json()["details"]["fields"]]
        assert fields == ["login_identifier"]


# --------------------------------------------------------------------------- two organizations


class TestOneLoginTwoOrganizations:
    async def test_another_organization_may_use_the_same_email_and_takes_nothing_from_its_owner(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """What the global check existed to stop. Tandoor House's manager adds a login with the
        Spice Garden owner's email. It is allowed now — and the owner still signs straight in,
        because the owner's password matches only the owner's account."""
        await _world(db_session, "owner", slug="spice-garden")
        await _world(db_session, "manager", slug="tandoor-house")
        tandoor = await _token(api_client, "manager", slug="tandoor-house")

        created = await api_client.post(
            EMPLOYEES,
            json=_employee("SQUAT1", "owner@spice-garden.test"),
            headers=_auth(tandoor),
        )
        signed_in = await api_client.post(
            LOGIN, json=_login_body("owner@spice-garden.test", PASSWORD)
        )

        assert created.status_code == 201, created.text
        assert signed_in.status_code == 200, signed_in.text
        assert "access_token" in signed_in.json()

    async def test_one_password_for_both_asks_which_organization_and_signs_in_to_neither(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _person_in(db_session, "Spice Garden")
        await _person_in(db_session, "Tandoor House")

        response = await api_client.post(LOGIN, json=_login_body())

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["choose_organization"] is True
        assert [each["name"] for each in body["organizations"]] == ["Spice Garden", "Tandoor House"]
        assert body["expires_in_seconds"] == 120
        assert "access_token" not in body
        assert "set-cookie" not in response.headers

    async def test_choosing_signs_in_to_that_organization_only(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _person_in(db_session, "Spice Garden")
        tandoor = await _person_in(db_session, "Tandoor House")
        choice = (await api_client.post(LOGIN, json=_login_body())).json()

        response = await api_client.post(
            CHOOSE, json={"ticket": choice["ticket"], "organization_id": str(tandoor.id)}
        )

        assert response.status_code == 200, response.text
        claims = decode_access_token(response.json()["access_token"])
        assert claims.organization_id == str(tandoor.id)
        assert "restaurant_os_refresh" in response.headers.get("set-cookie", "")

    async def test_a_pass_works_once(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        spice = await _person_in(db_session, "Spice Garden")
        await _person_in(db_session, "Tandoor House")
        choice = (await api_client.post(LOGIN, json=_login_body())).json()
        body = {"ticket": choice["ticket"], "organization_id": str(spice.id)}

        first = await api_client.post(CHOOSE, json=body)
        second = await api_client.post(CHOOSE, json=body)

        assert first.status_code == 200, first.text
        assert second.status_code == 401, second.text
        assert second.json()["code"] == "auth.choice_expired"

    async def test_an_organization_that_was_not_offered_is_refused_the_same_way(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _person_in(db_session, "Spice Garden")
        await _person_in(db_session, "Tandoor House")
        choice = (await api_client.post(LOGIN, json=_login_body())).json()

        response = await api_client.post(
            CHOOSE, json={"ticket": choice["ticket"], "organization_id": str(uuid.uuid4())}
        )

        assert response.status_code == 401, response.text
        assert response.json()["code"] == "auth.choice_expired"

    async def test_a_pass_lasts_two_minutes(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        spice = await _person_in(db_session, "Spice Garden")
        await _person_in(db_session, "Tandoor House")
        choice = (await api_client.post(LOGIN, json=_login_body())).json()
        await db_session.execute(
            text("UPDATE sign_in_choice SET expires_at = now() - interval '1 second'")
        )
        await db_session.commit()

        response = await api_client.post(
            CHOOSE, json={"ticket": choice["ticket"], "organization_id": str(spice.id)}
        )

        assert response.status_code == 401, response.text
        assert response.json()["code"] == "auth.choice_expired"

    async def test_different_passwords_go_straight_in_with_no_question(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        spice = await _person_in(db_session, "Spice Garden")
        await _person_in(db_session, "Tandoor House", password="another-password-9")  # noqa: S106

        response = await api_client.post(LOGIN, json=_login_body())

        assert response.status_code == 200, response.text
        claims = decode_access_token(response.json()["access_token"])
        assert claims.organization_id == str(spice.id)

    async def test_a_wrong_password_is_the_usual_refusal_and_offers_nothing(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _person_in(db_session, "Spice Garden")
        await _person_in(db_session, "Tandoor House")

        response = await api_client.post(
            LOGIN,
            json=_login_body(password="not-the-password"),  # noqa: S106
        )

        assert response.status_code == 401, response.text
        assert response.json()["code"] == "auth.invalid_credentials"
        assert "ticket" not in response.text

    async def test_an_organization_that_no_longer_employs_them_is_not_offered(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        spice = await _person_in(db_session, "Spice Garden")
        await _person_in(db_session, "Tandoor House", active=False)

        response = await api_client.post(LOGIN, json=_login_body())

        assert response.status_code == 200, response.text
        claims = decode_access_token(response.json()["access_token"])
        assert claims.organization_id == str(spice.id)
