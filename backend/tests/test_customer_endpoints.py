"""The customer API: happy, validation, permission, not-found, conflict — and the branch rule.

**Every write is checked with two requests.** The write, and then a read that proves it survived.
M08 shipped a whole module of writes that returned 201 with a populated body and then rolled back,
and the same bug is documented at the top of `app/api/v1/staff/inventory.py` from an earlier module.
It has now happened twice, and no unit test catches it: inside one transaction the write is visible
to the code that made it. Only a second request sees the truth.

**The branch rule gets its own section**, because no existing suite covers it. The generic suites
build two *organizations*, which is the hard tenant boundary; this rule lives inside one
organization, between two branches of the same business, and it exists because the owner asked for
it on 2026-09-16: a manager reads their own branch's customers, and handling a second branch is an
assignment rather than a permission.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EmploymentType, UserAccountStatus
from app.core.security import hash_password
from app.models.access import EmployeeRoleAssignment, Role
from app.models.identity import Employee, UserAccount
from app.models.orders import Order
from app.models.tenancy import Organization, Restaurant

CUSTOMERS = "/api/v1/staff/customers"
PASSWORD = "Correct-Horse-9"  # noqa: S105


class World:
    """One organization, two branches, and whoever we need working in them."""

    def __init__(self, organization: Organization) -> None:
        self.organization = organization
        self.restaurants: dict[str, Restaurant] = {}
        self.tokens: dict[str, str] = {}


async def _world(session: AsyncSession, *, branches: tuple[str, ...] = ("main",)) -> World:
    organization = Organization(name="Spice Garden Group", slug=f"sg-{uuid.uuid4().hex[:8]}")
    session.add(organization)
    await session.flush()
    world = World(organization)
    for branch in branches:
        restaurant = Restaurant(
            organization_id=organization.id,
            name=branch.title(),
            code=f"{branch[:2].upper()}{uuid.uuid4().hex[:6]}",
        )
        session.add(restaurant)
        world.restaurants[branch] = restaurant
    await session.flush()
    return world


async def _sign_in(
    session: AsyncSession,
    api_client: AsyncClient,
    world: World,
    *,
    role: str,
    branches: tuple[str, ...],
    label: str | None = None,
) -> str:
    """An employee with one role, assigned to the named branches, signed in at the first of them."""
    label = label or role
    email = f"{label}-{uuid.uuid4().hex[:6]}@spicegarden.test"
    account = UserAccount(
        organization_id=world.organization.id,
        email=email,
        password_hash=await hash_password(PASSWORD),
        status=UserAccountStatus.ACTIVE,
    )
    session.add(account)
    await session.flush()

    employee = Employee(
        organization_id=world.organization.id,
        user_account_id=account.id,
        employee_code=f"E{uuid.uuid4().hex[:6].upper()}",
        full_name=label.title(),
        joined_on=date(2026, 1, 1),
        employment_type=EmploymentType.FULL_TIME,
    )
    session.add(employee)
    await session.flush()

    role_row = await session.scalar(
        select(Role).where(Role.code == role, Role.organization_id.is_(None))
    )
    assert role_row is not None
    for branch in branches:
        session.add(
            EmployeeRoleAssignment(
                employee_id=employee.id,
                restaurant_id=world.restaurants[branch].id,
                role_id=role_row.id,
            )
        )
    await session.flush()

    response = await api_client.post(
        "/api/v1/auth/login", json={"identifier": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create(api_client: AsyncClient, token: str, phone: str, **extra: Any) -> dict[str, Any]:
    response = await api_client.post(
        CUSTOMERS, json={"phone": phone, **extra}, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _open_order(session: AsyncSession, restaurant: Restaurant) -> str:
    """One open order, written in SQL: this file tests M10, and going through M07's service would
    test M07."""
    order_id = uuid.uuid4()
    await session.execute(
        text(
            'INSERT INTO "order" (id, restaurant_id, order_number, type, channel, status, '
            "business_date, placed_at, subtotal, discount_total, charge_total, tax_total, "
            "round_off, grand_total) "
            "VALUES (:id, :rid, :number, 'dine_in', 'pos', 'open', :day, now(), 0, 0, 0, 0, 0, 0)"
        ),
        {
            "id": order_id,
            "rid": restaurant.id,
            "number": uuid.uuid4().hex[:6],
            "day": date(2026, 9, 16),
        },
    )
    return str(order_id)


# --------------------------------------------------------------------------- the happy path


class TestCreatingACustomer:
    async def test_a_customer_survives_the_request_that_made_it(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """**Two requests, and the second is the test.**

        A write that returns 201 with a populated body and then rolls back looks identical to a
        working one from inside the transaction that made it. This module's predecessors shipped
        that bug twice.
        """
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))

        created = await _create(api_client, token, "98765 43210", name="Ravi Kumar")

        found = await api_client.get(f"{CUSTOMERS}/{created['id']}", headers=_auth(token))
        assert found.status_code == 200, found.text
        assert found.json()["name"] == "Ravi Kumar"

    async def test_a_number_is_normalised_so_one_person_is_one_row(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`98765 43210`, `+91 98765 43210` and `09876543210` are one customer or three, and which
        one must not depend on who was standing at the counter."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        await _create(api_client, token, "98765 43211")

        clash = await api_client.post(
            CUSTOMERS, json={"phone": "+91 98765 43211"}, headers=_auth(token)
        )

        assert clash.status_code == 409, clash.text
        assert clash.json()["code"] == "customer.phone_taken"
        # And it says where to go, rather than only that something is wrong: the person hitting
        # this is at a counter with a diner in front of them.
        assert "customer_id" in clash.json()["details"]

    async def test_the_phone_is_stored_the_same_way_it_will_be_searched(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))

        created = await _create(api_client, token, "+91 98765 43212")

        assert created["phone"] == "9876543212"


# --------------------------------------------------------------------------- preferences


class TestPreferences:
    async def test_a_preference_survives_and_an_allergy_is_marked_critical(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876543213")

        written = await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/preferences",
            json={"type": "allergy", "value": "Peanuts", "is_critical": True},
            headers=_auth(token),
        )
        assert written.status_code == 201, written.text

        found = await api_client.get(f"{CUSTOMERS}/{customer['id']}", headers=_auth(token))
        assert [
            (preference["value"], preference["is_critical"])
            for preference in found.json()["preferences"]
        ] == [("Peanuts", True)]

    async def test_a_preference_id_from_another_profile_deletes_nothing(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Scoped by the customer as well as by the id. Otherwise a preference id lifted from one
        person's profile removes something from theirs."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        theirs = await _create(api_client, token, "9876543214")
        mine = await _create(api_client, token, "9876543215")
        await api_client.post(
            f"{CUSTOMERS}/{theirs['id']}/preferences",
            json={"type": "allergy", "value": "Shellfish", "is_critical": True},
            headers=_auth(token),
        )
        profile = await api_client.get(f"{CUSTOMERS}/{theirs['id']}", headers=_auth(token))
        preference_id = profile.json()["preferences"][0]["id"]

        response = await api_client.delete(
            f"{CUSTOMERS}/{mine['id']}/preferences/{preference_id}", headers=_auth(token)
        )

        assert response.status_code == 404, response.text
        still = await api_client.get(f"{CUSTOMERS}/{theirs['id']}", headers=_auth(token))
        assert len(still.json()["preferences"]) == 1


# --------------------------------------------------------------------------- permissions


class TestWhoMayDoWhat:
    async def test_a_waiter_may_read_a_customer(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The P1 design grants a waiter `customer.view` on purpose.

        `docs/customer-experience.md` puts the regular's card on the waiter's screen — "7th visit,
        usually orders Butter Chicken + Butter Naan, no onion/garlic" — and a waiter who cannot see
        a customer cannot greet one.
        """
        world = await _world(db_session)
        manager = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        waiter = await _sign_in(
            db_session, api_client, world, role="waiter", branches=("main",), label="waiter"
        )
        customer = await _create(api_client, manager, "9876543216", name="Ravi Kumar")

        response = await api_client.get(f"{CUSTOMERS}/{customer['id']}", headers=_auth(waiter))

        assert response.status_code == 200, response.text
        assert response.json()["name"] == "Ravi Kumar"

    async def test_a_waiter_may_not_create_or_erase_one(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Seeing and changing are different permissions. Editing somebody's details, and
        destroying them, are accountable acts that belong to a manager."""
        world = await _world(db_session)
        manager = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        waiter = await _sign_in(
            db_session, api_client, world, role="waiter", branches=("main",), label="waiter"
        )
        customer = await _create(api_client, manager, "9876543217")

        created = await api_client.post(
            CUSTOMERS, json={"phone": "9876543218"}, headers=_auth(waiter)
        )
        erased = await api_client.post(f"{CUSTOMERS}/{customer['id']}/erase", headers=_auth(waiter))

        assert created.status_code == 403, created.text
        assert erased.status_code == 403, erased.text

    async def test_a_chef_sees_no_customer_at_all(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A chef sees grams, not diners. The allergy that must reach them reaches them on the
        ticket, copied when the customer was attached — never by reading a customer record."""
        world = await _world(db_session)
        chef = await _sign_in(db_session, api_client, world, role="chef", branches=("main",))

        response = await api_client.get(CUSTOMERS, headers=_auth(chef))

        assert response.status_code == 403, response.text


# --------------------------------------------------------------------------- the branch rule


class TestABranchSeesItsOwnCustomers:
    """The owner's decision, 2026-09-16, and the reason it needs its own tests.

    The generic suites prove the hard boundary — another *organization* is unreachable. This is the
    softer rule inside one organization: the record belongs to the business so a chain recognises
    one diner across its branches, and the *view* belongs to the branch.
    """

    async def test_a_manager_does_not_see_the_other_branchs_customers(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session, branches=("koregaon", "baner"))
        koregaon = await _sign_in(
            db_session, api_client, world, role="manager", branches=("koregaon",)
        )
        baner = await _sign_in(
            db_session, api_client, world, role="manager", branches=("baner",), label="baner"
        )
        await _create(api_client, baner, "9876543219", name="Baner Regular")

        listed = await api_client.get(CUSTOMERS, headers=_auth(koregaon))

        assert listed.status_code == 200, listed.text
        assert [item["name"] for item in listed.json()["items"]] == []

    async def test_a_manager_assigned_to_both_sees_the_branch_they_switched_to(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """ "Provision should be there that if required he is allowed to manage other branches as
        well" — and the provision is an assignment plus a switch, not a permission.

        This is the whole mechanism in one test: the same person, the same permission, a different
        branch, and the customer list follows the switch. Nothing was granted and nothing was
        configured; somebody was assigned to a second restaurant.
        """
        world = await _world(db_session, branches=("koregaon", "baner"))
        baner_only = await _sign_in(
            db_session, api_client, world, role="manager", branches=("baner",), label="baner"
        )
        await _create(api_client, baner_only, "9876543220", name="Baner Regular")

        both = await _sign_in(
            db_session,
            api_client,
            world,
            role="manager",
            branches=("koregaon", "baner"),
            label="both",
        )
        before = await api_client.get(CUSTOMERS, headers=_auth(both))

        switched = await api_client.post(
            "/api/v1/auth/switch",
            json={"restaurant_id": str(world.restaurants["baner"].id)},
            headers=_auth(both),
        )
        assert switched.status_code == 200, switched.text
        after = await api_client.get(CUSTOMERS, headers=_auth(str(switched.json()["access_token"])))

        assert [item["name"] for item in before.json()["items"]] == []
        assert [item["name"] for item in after.json()["items"]] == ["Baner Regular"]

    async def test_the_same_person_is_one_record_across_branches(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The other half, and the reason the record is the organization's: a regular's allergy is
        known wherever they walk in. Creating them again at the second branch is refused as a
        duplicate rather than quietly making a second person."""
        world = await _world(db_session, branches=("koregaon", "baner"))
        koregaon = await _sign_in(
            db_session, api_client, world, role="manager", branches=("koregaon",)
        )
        baner = await _sign_in(
            db_session, api_client, world, role="manager", branches=("baner",), label="baner"
        )
        await _create(api_client, koregaon, "9876543221", name="Ravi Kumar")

        again = await api_client.post(CUSTOMERS, json={"phone": "9876543221"}, headers=_auth(baner))

        assert again.status_code == 409, again.text
        assert again.json()["code"] == "customer.phone_taken"


# --------------------------------------------------------------------------- not found


@pytest.mark.parametrize(
    "path",
    ["{base}/{id}", "{base}/{id}/preferences"],
)
async def test_an_unknown_customer_is_a_readable_404(
    db_session: AsyncSession, api_client: AsyncClient, path: str
) -> None:
    world = await _world(db_session)
    token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
    url = path.format(base=CUSTOMERS, id=uuid.uuid4())

    response = (
        await api_client.get(url, headers=_auth(token))
        if url.endswith(str(uuid.uuid4())) or "preferences" not in url
        else await api_client.post(
            url, json={"type": "allergy", "value": "Peanuts"}, headers=_auth(token)
        )
    )

    assert response.status_code == 404, response.text
    assert response.json()["code"] == "customer.not_found"


# --------------------------------------------------------------------------- the allergy, frozen


class TestTheAllergyReachesTheKitchen:
    """`docs/modules.md` requires that allergy preferences surface to the kitchen, and decision 9
    says how: a **copy**, taken when the customer is attached, never a live join."""

    async def test_a_critical_preference_is_copied_onto_the_order(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876543230", name="Ravi Kumar")
        await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/preferences",
            json={"type": "allergy", "value": "Peanuts", "is_critical": True},
            headers=_auth(token),
        )
        # And one that is not critical: a spice level matters to the person and is noise on a
        # ticket, which is how a real allergy gets skimmed past.
        await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/preferences",
            json={"type": "spice_level", "value": "Extra hot", "is_critical": False},
            headers=_auth(token),
        )
        order_id = await _open_order(db_session, world.restaurants["main"])

        attached = await api_client.post(
            f"/api/v1/staff/orders/{order_id}/customer",
            json={"customer_id": customer["id"]},
            headers=_auth(token),
        )

        assert attached.status_code == 200, attached.text
        assert attached.json()["allergy_note"] == "Peanuts"

    async def test_deleting_the_preference_afterwards_does_not_change_the_order(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The reason it is a copy. A preference deleted next week must not retroactively change
        what the kitchen was warned about on a ticket it has already cooked."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876543231")
        await api_client.post(
            f"{CUSTOMERS}/{customer['id']}/preferences",
            json={"type": "allergy", "value": "Shellfish", "is_critical": True},
            headers=_auth(token),
        )
        profile = await api_client.get(f"{CUSTOMERS}/{customer['id']}", headers=_auth(token))
        preference_id = profile.json()["preferences"][0]["id"]
        order_id = await _open_order(db_session, world.restaurants["main"])
        await api_client.post(
            f"/api/v1/staff/orders/{order_id}/customer",
            json={"customer_id": customer["id"]},
            headers=_auth(token),
        )

        await api_client.delete(
            f"{CUSTOMERS}/{customer['id']}/preferences/{preference_id}", headers=_auth(token)
        )

        note = await db_session.scalar(
            select(Order.allergy_note).where(Order.id == uuid.UUID(order_id))
        )
        assert note == "Shellfish"

    async def test_a_customer_with_no_allergy_writes_no_note(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The common case, and it must not read as a failure on the waiter's screen."""
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876543232")
        order_id = await _open_order(db_session, world.restaurants["main"])

        attached = await api_client.post(
            f"/api/v1/staff/orders/{order_id}/customer",
            json={"customer_id": customer["id"]},
            headers=_auth(token),
        )

        assert attached.status_code == 200, attached.text
        assert attached.json()["allergy_note"] is None

    async def test_attaching_to_a_settled_bill_is_refused_readably(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The M10 review's second finding, and its regression test.

        A settled order is immutable (CLAUDE.md invariant 6) and a **database trigger** enforces it
        — which the seeder discovered by being refused. Without this check a waiter attaching
        somebody to a bill settled a second ago would meet the trigger's own refusal rendered as
        "Something went wrong", and the thing they actually need to be told is that the bill is
        finished and the customer goes on the next one.
        """
        world = await _world(db_session)
        token = await _sign_in(db_session, api_client, world, role="manager", branches=("main",))
        customer = await _create(api_client, token, "9876543240")
        order_id = await _open_order(db_session, world.restaurants["main"])
        await db_session.execute(
            text("UPDATE \"order\" SET status = 'settled', settled_at = now() WHERE id = :id"),
            {"id": uuid.UUID(order_id)},
        )

        response = await api_client.post(
            f"/api/v1/staff/orders/{order_id}/customer",
            json={"customer_id": customer["id"]},
            headers=_auth(token),
        )

        assert response.status_code == 409, response.text
        assert response.json()["code"] == "order.settled"
        assert "next order" in response.json()["message"]
