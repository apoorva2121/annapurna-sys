"""The restaurant's address is structured data, and the API contract said it was a string.

Found by external review, 2026-09-11, and it is the worst defect in M02: `GET /staff/restaurant`
raised a `ValidationError` — surfacing as a 500 — for **every seeded restaurant**, because
`seed/organization.yaml` writes a dict and `RestaurantResponse.address` was typed `str | None`.

`docs/schema.md` §1 specifies `address jsonb` and the model agrees (`Mapped[dict | None]`). The
schema was the outlier.

**Why the whole suite stayed green.** Every fixture in this project builds
`Restaurant(organization_id=…, name=…, code="R1")` with no address, so the column is NULL and
`None` satisfies `str | None`. The only thing that ever produced a dict was `make seed` — which is
exactly what the manual pass runs against, and step A1 of the manual script is "open Settings".

The lesson is the fixture, not the type: a test world that is uniformly simpler than the seeded
world cannot see a defect that only the seeded world has. Hence the populated address below.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EmploymentType, UserAccountStatus
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.audit import AuditLog
from app.models.identity import Employee, UserAccount
from app.models.tenancy import Organization, Restaurant

PASSWORD = "Staging#2026"  # noqa: S105

# Exactly what seed/organization.yaml writes for SG_KOREGAON.
SEEDED_ADDRESS = {
    "line1": "Lane 5, Koregaon Park",
    "city": "Pune",
    "state": "Maharashtra",
    "pincode": "411001",
}


async def _owner_at_a_restaurant_with_an_address(session: AsyncSession) -> Restaurant:
    organization = Organization(name="Spice Garden", slug="spice-garden")
    session.add(organization)
    await session.flush()
    restaurant = Restaurant(
        organization_id=organization.id,
        name="Spice Garden",
        code="R1",
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
        # The populated address is the entire point of this fixture.
        address=SEEDED_ADDRESS,
    )
    session.add(restaurant)
    await session.flush()

    role = (
        await session.scalars(
            select(Role).where(Role.code == "owner", Role.organization_id.is_(None))
        )
    ).first()
    assert role is not None
    account = UserAccount(
        organization_id=organization.id,
        email="owner@spice-garden.test",
        password_hash=hash_password(PASSWORD),
        status=UserAccountStatus.ACTIVE,
    )
    session.add(account)
    await session.flush()
    employee = Employee(
        organization_id=organization.id,
        user_account_id=account.id,
        employee_code="E001",
        full_name="Owner Person",
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
    await session.commit()
    return restaurant


async def _token(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "owner@spice-garden.test", "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestReadingARestaurantThatHasAnAddress:
    async def test_the_settings_endpoint_does_not_fall_over(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Step A1 of the manual script. This returned 500 on every seeded restaurant."""
        await _owner_at_a_restaurant_with_an_address(db_session)
        token = await _token(api_client)

        response = await api_client.get("/api/v1/staff/restaurant", headers=_auth(token))

        assert response.status_code == 200, response.text

    async def test_the_address_comes_back_with_its_parts_intact(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Structured, not flattened. M06's bill prints the lines separately and a GST filing needs
        the state on its own — a free-text blob would have to be re-parsed by every consumer."""
        await _owner_at_a_restaurant_with_an_address(db_session)
        token = await _token(api_client)

        response = await api_client.get("/api/v1/staff/restaurant", headers=_auth(token))

        # A superset, not an exact match: the response states every field of the contract, so an
        # absent `line2` comes back as an explicit null rather than being missing. Asserting on the
        # seeded keys is what this test is about — that the parts survived, not that the response
        # is byte-identical to the YAML.
        address = response.json()["address"]
        assert {key: address[key] for key in SEEDED_ADDRESS} == SEEDED_ADDRESS
        assert address["line2"] is None


class TestWritingAnAddress:
    async def test_an_address_can_be_changed(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _owner_at_a_restaurant_with_an_address(db_session)
        token = await _token(api_client)

        response = await api_client.patch(
            "/api/v1/staff/restaurant",
            json={
                "address": {
                    "line1": "Baner Road",
                    "city": "Pune",
                    "state": "Maharashtra",
                    "pincode": "411045",
                }
            },
            headers=_auth(token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["address"]["line1"] == "Baner Road"

    async def test_a_plain_string_address_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The half of this defect that would have destroyed data.

        With `address: str | None`, `PATCH {"address": "12 MG Road"}` stored the scalar JSON string
        into the JSONB column, replacing the structured value. The parts were then unrecoverable
        through the API — and the read path started working again, because a bare string validates
        against `str | None`. The failure concealed itself.
        """
        await _owner_at_a_restaurant_with_an_address(db_session)
        token = await _token(api_client)

        response = await api_client.patch(
            "/api/v1/staff/restaurant", json={"address": "12 MG Road"}, headers=_auth(token)
        )

        assert response.status_code == 422

    async def test_an_address_missing_its_city_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _owner_at_a_restaurant_with_an_address(db_session)
        token = await _token(api_client)

        response = await api_client.patch(
            "/api/v1/staff/restaurant",
            json={"address": {"line1": "Baner Road", "state": "Maharashtra", "pincode": "411045"}},
            headers=_auth(token),
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("pincode", ["41104", "4110455", "abcdef", "011045"])
    async def test_a_pincode_that_is_not_an_indian_pincode_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient, pincode: str
    ) -> None:
        """Six digits, never starting with zero. It prints on the bill and appears on a GST filing;
        a wrong one is not caught by anything downstream."""
        await _owner_at_a_restaurant_with_an_address(db_session)
        token = await _token(api_client)

        response = await api_client.patch(
            "/api/v1/staff/restaurant",
            json={
                "address": {
                    "line1": "Baner Road",
                    "city": "Pune",
                    "state": "Maharashtra",
                    "pincode": pincode,
                }
            },
            headers=_auth(token),
        )

        assert response.status_code == 422

    async def test_the_address_can_be_cleared(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Unlike timezone and currency, an address genuinely can be absent — a cloud kitchen with
        no shopfront is a real thing — so an explicit null clears it rather than being refused."""
        await _owner_at_a_restaurant_with_an_address(db_session)
        token = await _token(api_client)

        response = await api_client.patch(
            "/api/v1/staff/restaurant", json={"address": None}, headers=_auth(token)
        )

        assert response.status_code == 200, response.text
        assert response.json()["address"] is None


class TestSettingsThatCannotBeCleared:
    """`timezone`, `currency` and `business_day_start` are NOT NULL columns.

    An explicit `null` used to reach `setattr` and surface as an `IntegrityError` — a 500 for a
    request any client can construct, on the three columns that decide what a day and a rupee mean.
    The two validation guards skipped `None` and then the loop assigned it anyway: no validation
    *and* a constraint violation. Found by external review, 2026-09-11.
    """

    @pytest.mark.parametrize("field", ["timezone", "currency", "business_day_start"])
    async def test_clearing_it_is_refused_rather_than_violating_not_null(
        self, db_session: AsyncSession, api_client: AsyncClient, field: str
    ) -> None:
        await _owner_at_a_restaurant_with_an_address(db_session)
        token = await _token(api_client)

        response = await api_client.patch(
            "/api/v1/staff/restaurant", json={field: None}, headers=_auth(token)
        )

        # 422 and a code the client can act on — not a 500 with a reference number.
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "restaurant.setting_not_nullable"
        assert field in response.json()["details"]["fields"]

    async def test_the_fssai_licence_may_still_be_cleared(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The distinction is meaningful, not blanket. A restaurant can stop being GST-registered
        or lose a licence; it cannot stop having a timezone."""
        await _owner_at_a_restaurant_with_an_address(db_session)
        token = await _token(api_client)

        response = await api_client.patch(
            "/api/v1/staff/restaurant", json={"fssai_licence": None}, headers=_auth(token)
        )

        assert response.status_code == 200, response.text
        assert response.json()["fssai_licence"] is None


class TestTheNumbersThatPrintOnEveryBill:
    """The M02 threat table asks for GSTIN and FSSAI to be "format-validated, not merely
    non-empty", because the attack it describes is substituting a supplier's number so bills carry
    someone else's tax identity. Both carried only `max_length`. Found by external review."""

    @pytest.mark.parametrize("gstin", ["27AABCS1429B1Z", "nonsense", "27aabcs1429b1zx", ""])
    async def test_a_malformed_gstin_is_refused(
        self, db_session: AsyncSession, api_client: AsyncClient, gstin: str
    ) -> None:
        await _owner_at_a_restaurant_with_an_address(db_session)
        token = await _token(api_client)

        response = await api_client.patch(
            "/api/v1/staff/restaurant", json={"gstin": gstin}, headers=_auth(token)
        )

        assert response.status_code == 422

    async def test_the_seeded_gstin_is_accepted(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The pattern has to accept the real thing. A validator that refuses the seed is worse
        than none — it fails on the demo and gets loosened until it means nothing."""
        await _owner_at_a_restaurant_with_an_address(db_session)
        token = await _token(api_client)

        response = await api_client.patch(
            "/api/v1/staff/restaurant", json={"gstin": "27AABCS1429B1ZX"}, headers=_auth(token)
        )

        assert response.status_code == 200, response.text

    async def test_changing_the_fssai_licence_is_audited(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """It was absent from `_AUDITED_SETTINGS` while the threat table required it. It prints on
        every bill and is a legal requirement; a substitution left no trace at all."""
        await _owner_at_a_restaurant_with_an_address(db_session)
        token = await _token(api_client)

        await api_client.patch(
            "/api/v1/staff/restaurant",
            json={"fssai_licence": "11522998000123"},
            headers=_auth(token),
        )

        entry = (
            await db_session.scalars(
                select(AuditLog).where(AuditLog.action == "restaurant.settings_changed")
            )
        ).first()
        assert entry is not None
        assert entry.new_value == {"fssai_licence": "11522998000123"}

    async def test_an_fssai_licence_must_start_with_a_licence_or_registration_digit(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The first digit of an FSSAI number is its type: `1` licence, `2` basic registration.
        Nothing else is issued. The pattern accepted any 14 digits, so `00000000000000` passed
        format validation and printed on every bill.

        This is the cheap half of the check and all the cheap half can ever be. **An FSSAI number
        carries no check digit**, so no amount of pattern matching establishes that a well-formed
        number was ever issued — only a FoSCoS lookup does. Tightening the prefix removes the
        typos and the obvious fabrications; it does not make the number true.
        """
        await _owner_at_a_restaurant_with_an_address(db_session)
        token = await _token(api_client)

        for rejected in ("00000000000000", "31522998000123", "9152299800012"):
            response = await api_client.patch(
                "/api/v1/staff/restaurant",
                json={"fssai_licence": rejected},
                headers=_auth(token),
            )
            assert response.status_code == 422, f"{rejected} was accepted: {response.text}"

        for accepted in ("11522998000123", "21522998000123"):
            response = await api_client.patch(
                "/api/v1/staff/restaurant",
                json={"fssai_licence": accepted},
                headers=_auth(token),
            )
            assert response.status_code == 200, f"{accepted} was rejected: {response.text}"
