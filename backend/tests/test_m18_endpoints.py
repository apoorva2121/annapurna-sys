"""The compliance surface over HTTP, and the two things that are properties of the shape.

**Every finding on the wire carries a citation, and every citation carries `checked_on`.** Asserted
over whatever the route returns rather than against a fixed list, because the failure this guards
is a rule added later without one — and a rule with no citation is the product asserting Indian law
on its own authority, which `docs/compliance-rules.md` exists to forbid.

**A manager may read every finding and may not dismiss one.** That split is the whole of M18's
permission design: the person who runs the floor is the person most able to act on an expired
licence, and the least appropriate person to decide it does not matter.
"""

from __future__ import annotations

from datetime import date

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.staff.compliance import EXPORT_NOTE
from app.core.compliance import CATALOGUE, RuleStatus, Severity
from app.core.permissions import CATALOGUE as PERMISSIONS
from app.models.tenancy import Restaurant
from tests.test_setup_endpoints import World, _auth, _token
from tests.test_setup_endpoints import _world as _identity_world

STAFF = "/api/v1/staff"


async def _expire_the_licence(session: AsyncSession, world: World) -> date:
    """One defect, chosen because it is the only `critical` a restaurant can have on day one.

    Committed, because the API runs on its own session: the fixture and the request are two
    connections, and a flush the request cannot see is a fixture that silently does nothing.
    """
    place = (
        await session.scalars(select(Restaurant).where(Restaurant.id == world.restaurant.id))
    ).one()
    expired_on = date(2026, 1, 31)
    place.fssai_licence = "11522998000123"
    place.fssai_licence_expires_on = expired_on
    await session.commit()
    return expired_on


class TestWhoMaySeeAndWhoMayDecide:
    def test_the_shipped_roles_split_seeing_from_deciding(self) -> None:
        """Asserted against the catalogue rather than by calling routes, because this is a claim
        about the design and not about one handler."""
        by_code = {role.code: set(role.permissions) for role in PERMISSIONS.roles}

        assert "compliance.view" in by_code["manager"]
        assert "compliance.act" not in by_code["manager"]
        for role in ("owner", "admin"):
            assert {"compliance.view", "compliance.act"} <= by_code[role]
        # The accountant reads the record and does not curate it, for the same reason they hold
        # `audit.view` and not the ability to alter what it says.
        assert "compliance.view" in by_code["accountant"]
        assert "compliance.act" not in by_code["accountant"]
        # Nobody on the floor holds either. A compliance finding names what is wrong with the
        # business, and it is not a thing a waiter is given to read.
        for role in ("waiter", "kitchen_staff", "cleaner"):
            assert not {"compliance.view", "compliance.act"} & by_code[role]

    async def test_a_waiter_is_refused(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _identity_world(db_session, "owner", "waiter")
        response = await api_client.get(
            f"{STAFF}/compliance/findings",
            headers=_auth(await _token(api_client, "waiter")),
        )

        assert response.status_code == 403


class TestOpeningTheScreen:
    async def test_a_clean_restaurant_answers_with_nothing_outstanding(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """The silence the owner's card depends on."""
        await _identity_world(db_session, "owner")
        response = await api_client.get(
            f"{STAFF}/compliance/findings", headers=_auth(await _token(api_client, "owner"))
        )

        assert response.status_code == 200, response.text
        assert response.json()["outstanding"] == 0, response.json()["findings"]

    async def test_every_finding_carries_a_citation_with_a_checked_date(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        world = await _identity_world(db_session, "owner")
        await _expire_the_licence(db_session, world)
        token = await _token(api_client, "owner")

        body = (await api_client.get(f"{STAFF}/compliance/findings", headers=_auth(token))).json()

        assert body["findings"], "the fixture was meant to have an expired licence"
        for finding in body["findings"]:
            citation = finding["citation"]
            assert citation is not None, f"{finding['rule_code']} cites nothing"
            assert citation["instrument"]
            assert citation["checked_on"]
            assert citation["status"] in {status.value for status in RuleStatus}
            # The guarantee, on the wire: only a rule in force may be critical.
            if finding["severity"] == Severity.CRITICAL.value:
                assert citation["status"] == RuleStatus.IN_FORCE.value

    async def test_the_rules_route_lists_the_whole_catalogue(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _identity_world(db_session, "owner")
        body = (
            await api_client.get(
                f"{STAFF}/compliance/rules",
                headers=_auth(await _token(api_client, "owner")),
            )
        ).json()

        assert len(body["rules"]) == len(CATALOGUE)
        assert {rule["code"] for rule in body["rules"]} == {rule.code for rule in CATALOGUE}


class TestActingOnOne:
    async def test_a_manager_may_read_and_may_not_suppress(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        world = await _identity_world(db_session, "owner", "manager")
        await _expire_the_licence(db_session, world)
        manager = await _token(api_client, "manager")

        listed = await api_client.get(f"{STAFF}/compliance/findings", headers=_auth(manager))
        assert listed.status_code == 200
        finding_id = listed.json()["findings"][0]["id"]

        refused = await api_client.post(
            f"{STAFF}/compliance/findings/{finding_id}/suppress",
            headers=_auth(manager),
            json={"reason": "Not my problem."},
        )
        assert refused.status_code == 403

    async def test_suppressing_without_a_reason_is_refused(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        world = await _identity_world(db_session, "owner")
        await _expire_the_licence(db_session, world)
        token = await _token(api_client, "owner")
        listed = await api_client.get(f"{STAFF}/compliance/findings", headers=_auth(token))
        finding_id = listed.json()["findings"][0]["id"]

        response = await api_client.post(
            f"{STAFF}/compliance/findings/{finding_id}/suppress",
            headers=_auth(token),
            json={},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "compliance.reason_required"

    async def test_acknowledging_clears_it_from_outstanding_and_not_from_the_list(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        world = await _identity_world(db_session, "owner")
        await _expire_the_licence(db_session, world)
        token = await _token(api_client, "owner")
        listed = await api_client.get(f"{STAFF}/compliance/findings", headers=_auth(token))
        finding_id = listed.json()["findings"][0]["id"]

        acknowledged = await api_client.post(
            f"{STAFF}/compliance/findings/{finding_id}/acknowledge", headers=_auth(token)
        )
        assert acknowledged.status_code == 200, acknowledged.text
        assert acknowledged.json()["state"] == "acknowledged"

        again = (await api_client.get(f"{STAFF}/compliance/findings", headers=_auth(token))).json()
        assert again["outstanding"] == 0
        assert [f["id"] for f in again["findings"]] == [finding_id]


class TestTheExport:
    async def test_it_says_what_raised_at_means_and_lists_the_quiet_rules(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """*"We checked these ten things"* is the claim an inspection is interested in, and the
        note is there because the alternative is a reader assuming `first_detected` is when the
        condition began."""
        world = await _identity_world(db_session, "owner")
        await _expire_the_licence(db_session, world)
        response = await api_client.get(
            f"{STAFF}/compliance/export", headers=_auth(await _token(api_client, "owner"))
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        text = response.text
        assert EXPORT_NOTE.split(".")[0] in text
        assert "fssai.expired" in text
        # A rule that found nothing is still named, with its instrument.
        assert "ccpa.service_charge" in text
        assert "rules checked and found nothing" in text

    async def test_the_history_survives_the_condition_being_fixed(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        world = await _identity_world(db_session, "owner")
        await _expire_the_licence(db_session, world)
        token = await _token(api_client, "owner")
        await api_client.get(f"{STAFF}/compliance/findings", headers=_auth(token))

        place = (
            await db_session.scalars(select(Restaurant).where(Restaurant.id == world.restaurant.id))
        ).one()
        place.fssai_licence_expires_on = date(2030, 1, 31)
        await db_session.commit()

        live = (await api_client.get(f"{STAFF}/compliance/findings", headers=_auth(token))).json()
        history = (await api_client.get(f"{STAFF}/compliance/history", headers=_auth(token))).json()

        assert live["findings"] == []
        assert [row["rule_code"] for row in history] == ["fssai.expired"]
        assert history[0]["state"] == "resolved"
        assert history[0]["resolved_at"] is not None
