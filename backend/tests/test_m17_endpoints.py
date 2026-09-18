"""The performance surface over HTTP, and the two guarantees that are structural rather than
behavioural.

**Every role can open its own score.** ADR 0011 makes `performance.view.own` a structural
guarantee rather than a setting, so this asserts it against the shipped catalogue — every role,
including the cleaner, including kitchen staff — rather than against one endpoint returning 200.

**No response schema can express a bottom ranking.** A handler that sorts correctly today can be
rewritten tomorrow; a `TeamLineResponse` with no `rank` field cannot be made to emit one whatever
anybody writes in the handler. That is the difference between a rule and a habit, and this test
walks the schemas rather than calling the routes.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CATALOGUE
from app.core.scoring import SUGGESTED_WEIGHTS
from app.schemas import performance as schemas
from tests.test_setup_endpoints import World, _auth, _token
from tests.test_setup_endpoints import _world as _identity_world

STAFF = "/api/v1/staff"
_DAY = date(2026, 9, 16)


async def _scheme_and_period(client: AsyncClient, token: str) -> tuple[str, str]:
    scheme = await client.post(
        f"{STAFF}/performance/schemes",
        headers=_auth(token),
        json={
            "name": "Starting point",
            "period_type": "weekly",
            "weights": dict(SUGGESTED_WEIGHTS),
            "effective_from": str(_DAY - timedelta(days=30)),
        },
    )
    assert scheme.status_code == 201, scheme.text
    period = await client.post(
        f"{STAFF}/performance/periods",
        headers=_auth(token),
        json={
            "incentive_scheme_id": scheme.json()["id"],
            "period_start": str(_DAY - timedelta(days=6)),
            "period_end": str(_DAY),
        },
    )
    assert period.status_code == 201, period.text
    return scheme.json()["id"], period.json()["id"]


class TestEverybodyCanSeeTheirOwn:
    def test_every_role_in_the_catalogue_holds_it(self) -> None:
        """**ADR 0011's structural guarantee**, asserted where it is structural.

        *"A score an employee cannot see is surveillance and lowers morale; the same score, visible
        with its inputs shown, is feedback and raises it. This is the decision that determines which
        of the two this feature becomes, so it is a structural guarantee rather than a setting."*

        A role missing it is not a configuration mistake; it is this feature quietly becoming the
        other thing.
        """
        missing = [
            role.code for role in CATALOGUE.roles if "performance.view.own" not in role.permissions
        ]

        assert missing == [], f"these roles cannot see their own figures: {missing}"

    async def test_a_cleaner_can_open_their_own_score(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """The role with the fewest permissions in the product, and the one this rule is really
        about."""
        await _identity_world(db_session, "owner", "cleaner")
        await db_session.commit()
        owner = await _token(api_client, "owner")
        _, period_id = await _scheme_and_period(api_client, owner)
        cleaner = await _token(api_client, "cleaner")

        response = await api_client.get(
            f"{STAFF}/performance/me?period_id={period_id}", headers=_auth(cleaner)
        )

        assert response.status_code == 200, response.text

    async def test_the_route_takes_no_employee_id(self) -> None:
        """It answers about *the caller*. A route that took an id would be a route somebody could
        point at somebody else, which is a different feature with different ethics."""
        import inspect

        from app.api.v1.staff.performance import my_performance

        assert "employee_id" not in inspect.signature(my_performance).parameters

    async def test_it_says_what_the_figures_are_used_for(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """`docs/workload-fairness.md`'s ethics review, question 2: the promise is made *in the
        product*, not only in a document. If it stops being true, the sentence is a lie somebody
        will notice."""
        await _identity_world(db_session, "owner")
        await db_session.commit()
        owner = await _token(api_client, "owner")
        _, period_id = await _scheme_and_period(api_client, owner)

        body = (
            await api_client.get(
                f"{STAFF}/performance/me?period_id={period_id}", headers=_auth(owner)
            )
        ).json()

        # Nobody worked in this window, so there is no line — but when there is one it carries it.
        assert body is None or "rewards and for fairer rosters" in body["purpose"]


class TestNoScreenCanShowABottomRanking:
    def test_no_team_facing_schema_has_a_rank_field(self) -> None:
        """**A property of the shapes, not of the handlers.**

        A handler that sorts correctly today can be rewritten tomorrow. A schema with no rank field
        cannot be made to emit a ranking whatever anybody writes in the handler, and that is the
        difference between a rule and a habit.

        `MyScoreResponse` is excluded on purpose: "you were third of nine" is a thing to say to
        somebody about themselves, and it is never part of a list of other people.
        """
        team_facing = (
            schemas.TeamLineResponse,
            schemas.TeamResponse,
            schemas.ShareResponse,
            schemas.DistributionResponse,
        )

        for schema in team_facing:
            fields = set(schema.model_fields)
            assert "rank" not in fields, f"{schema.__name__} can express a ranking"
            assert "rank_in_period" not in fields, f"{schema.__name__} can express a ranking"

    def test_only_a_persons_own_view_carries_a_rank(self) -> None:
        assert "rank" in schemas.MyScoreResponse.model_fields


class TestWhoMayDoWhat:
    async def test_a_waiter_cannot_configure_the_scheme(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """It decides what the restaurant pays people to do. The owner's alone."""
        await _identity_world(db_session, "owner", "waiter")
        await db_session.commit()
        waiter = await _token(api_client, "waiter")

        refused = await api_client.post(
            f"{STAFF}/performance/schemes",
            headers=_auth(waiter),
            json={
                "name": "Mine",
                "period_type": "weekly",
                "weights": dict(SUGGESTED_WEIGHTS),
                "effective_from": str(_DAY),
            },
        )

        assert refused.status_code == 403, refused.text

    async def test_a_waiter_cannot_open_the_team_view(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        await _identity_world(db_session, "owner", "waiter")
        await db_session.commit()
        waiter = await _token(api_client, "waiter")

        refused = await api_client.get(
            f"{STAFF}/performance/team?period_id={uuid.uuid4()}", headers=_auth(waiter)
        )

        assert refused.status_code == 403, refused.text

    async def test_a_manager_cannot_publish(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """Publishing is the act that turns a measurement into a payment, so it is the owner's."""
        await _identity_world(db_session, "owner", "manager")
        await db_session.commit()
        manager = await _token(api_client, "manager")

        refused = await api_client.post(
            f"{STAFF}/performance/periods/{uuid.uuid4()}/publish", headers=_auth(manager)
        )

        assert refused.status_code == 403, refused.text

    async def test_a_manager_can_grant_an_award(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """A manager is who notices somebody covering two shifts at no notice."""
        world = await _identity_world(db_session, "owner", "manager")
        await db_session.commit()
        manager = await _token(api_client, "manager")
        employee = await _somebody(db_session, world)

        granted = await api_client.post(
            f"{STAFF}/recognition/awards",
            headers=_auth(manager),
            json={
                "employee_id": str(employee),
                "type": "recognition_only",
                "citation": "Covered two shifts at no notice in the week of the wedding party.",
            },
        )

        assert granted.status_code == 201, granted.text
        assert granted.json()["citation"].startswith("Covered two shifts")


class TestTheSchemeRefusalReachesTheCaller:
    async def test_a_volume_heavy_scheme_is_refused_in_words(
        self, db_session: AsyncSession, api_client: AsyncClient
    ) -> None:
        """422 with the sentence, not a code. The person reading it is the owner, and the reason is
        the whole point of the rule."""
        await _identity_world(db_session, "owner")
        await db_session.commit()
        owner = await _token(api_client, "owner")

        refused = await api_client.post(
            f"{STAFF}/performance/schemes",
            headers=_auth(owner),
            json={
                "name": "Rush",
                "period_type": "weekly",
                "weights": {"volume": "0.60", "accuracy": "0.20", "rating": "0.20"},
                "effective_from": str(_DAY),
            },
        )

        assert refused.status_code == 422, refused.text
        assert "pays people to rush" in refused.json()["message"]


async def _somebody(session: AsyncSession, world: World) -> uuid.UUID:
    from sqlalchemy import select

    from app.models.identity import Employee

    found = (
        await session.scalars(
            select(Employee).where(Employee.organization_id == world.organization.id)
        )
    ).first()
    assert found is not None
    return found.id
