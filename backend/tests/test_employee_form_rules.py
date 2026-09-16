"""Adding an employee (owner defect sheet rows 8, 9 and 11; decisions D15 and D19, B12).

- A name needs at least two letters. `12345` was accepted; "S. Patil" and "Ravi 2" are real names.
- The form fills in the next free employee code, which the organization's own codes decide.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.employee import next_employee_code
from tests.test_setup_endpoints import _auth, _token, _world

EMPLOYEES = "/api/v1/staff/employees"


def _new(name: str, code: str) -> dict[str, str]:
    return {"full_name": name, "employee_code": code, "joined_on": "2026-09-01"}


class TestAName:
    async def test_digits_alone_are_not_a_name(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        response = await api_client.post(
            EMPLOYEES, json=_new("12345", "EMP100"), headers=_auth(token)
        )

        assert response.status_code == 422, response.text
        assert response.json()["details"]["fields"][0]["field"] == "full_name"

    async def test_initials_and_digits_are_fine(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")

        first = await api_client.post(
            EMPLOYEES, json=_new("S. Patil", "EMP101"), headers=_auth(token)
        )
        second = await api_client.post(
            EMPLOYEES, json=_new("Ravi 2", "EMP102"), headers=_auth(token)
        )

        assert (first.status_code, second.status_code) == (201, 201), (first.text, second.text)

    async def test_a_rename_follows_the_same_rule(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner")
        token = await _token(api_client, "owner")
        created = await api_client.post(
            EMPLOYEES, json=_new("Ravi Sharma", "EMP103"), headers=_auth(token)
        )

        response = await api_client.patch(
            f"{EMPLOYEES}/{created.json()['id']}", json={"full_name": "99"}, headers=_auth(token)
        )

        assert response.status_code == 422, response.text


class TestTheNextCode:
    def test_it_follows_the_codes_already_in_use(self) -> None:
        assert next_employee_code(["EMP001", "EMP002", "EMP017"]) == "EMP018"
        assert next_employee_code(["E000", "E001"]) == "E002"
        assert next_employee_code([]) == "EMP001"

    def test_the_most_used_prefix_wins_and_the_width_is_kept(self) -> None:
        assert next_employee_code(["EMP009", "EMP010", "K7"]) == "EMP011"

    async def test_the_form_is_offered_the_next_free_code(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "manager")
        token = await _token(api_client, "owner")

        response = await api_client.get(f"{EMPLOYEES}/next-code", headers=_auth(token))

        assert response.status_code == 200, response.text
        assert response.json() == {"employee_code": "E002"}

    async def test_someone_who_cannot_add_employees_is_not_offered_one(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _world(db_session, "owner", "waiter")
        token = await _token(api_client, "waiter")

        response = await api_client.get(f"{EMPLOYEES}/next-code", headers=_auth(token))

        assert response.status_code == 403
