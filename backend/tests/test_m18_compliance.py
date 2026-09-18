"""The catalogue, the state machine, and the one rule this module exists to keep.

`docs/compliance-rules.md` opens with a sentence that is the reason M18 was built and the reason
it is dangerous: *"never fill an Indian rate, threshold or commencement date from memory — research
returned stale-but-confident law three times in one session."* A product that warns a restaurant
about the law is a product that can be confidently wrong about the law, and a confidently wrong
warning is worse than no warning: it teaches an owner to ignore the next one.

So the first class here asserts the guarantee rather than any particular rule's wording:
**a rule that is not `in_force` cannot produce a `critical` finding**, over the whole catalogue,
including rules nobody has written yet. The four states are not a taxonomy for documentation —
`in_force`, `notified_not_in_force`, `unsettled` and `unverified` differ in exactly one way that
matters, which is whether the product may stop somebody.

The rest holds the state machine: evaluation happens on read, raising is idempotent, resolving is
the product's act and acknowledging is a person's, and nothing is ever deleted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import compliance as rules
from app.core.compliance import (
    CALORIE_OUTLET_THRESHOLD,
    CATALOGUE,
    EXPIRY_WARNING_DAYS,
    Facts,
    RuleStatus,
    Severity,
    codes,
    evaluate,
    rule_for,
)
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.tenancy import TenantScope
from app.models.compliance import ComplianceEvent, ComplianceFinding
from app.models.identity import Employee
from app.models.menu import MenuCategory, MenuItem
from app.models.setup import Station
from app.models.tenancy import Organization, Restaurant
from app.services.compliance import ComplianceService, catalogue

_NOW = datetime(2026, 9, 19, 11, 0, tzinfo=UTC)
# 11:00 UTC is 16:30 in Kolkata, which is comfortably inside the business day that began at 05:00.
_TODAY = date(2026, 9, 19)

# A **State** licence, which is what most tenants of this product hold. The default matters:
# digits 2-3 of `10012345678901` are `00`, which is a Central licence, and a Central licence
# is covered by the calorie declaration on its own. A default that quietly made every fixture
# a chain would have made the conditional rules look unconditional.
_GOOD_LICENCE = "11522998000123"
_CENTRAL_LICENCE = "10012345678901"
_REGISTRATION = "21522998000123"
_GOOD_GSTIN = "27AAPFU0939F1ZV"


def _facts(**overrides: object) -> Facts:
    """A restaurant with nothing wrong with it. Every test names only its own defect.

    Written as a helper rather than a fixture because it takes no I/O and the catalogue takes no
    session: the ten rules are pure functions of these fourteen numbers, which is what makes them
    testable at all.
    """
    base: dict[str, object] = {
        "today": _TODAY,
        "fssai_licence": _GOOD_LICENCE,
        "fssai_expires_on": _TODAY + timedelta(days=200),
        "gstin": _GOOD_GSTIN,
        "gst_scheme": "regular",
        "annual_turnover": Decimal("8000000"),
        "invoices_issued": 4000,
        "service_charge_rate": Decimal("0"),
        "live_menu_items": 40,
        "items_without_allergens": 0,
        "items_without_calories": 0,
        "outlets": 2,
        "tax_groups_without_a_current_rate": 0,
        "customers_without_consent": 0,
    }
    base.update(overrides)
    return Facts(**base)  # type: ignore[arg-type]


class TestTheRuleThatGovernsTheRules:
    """Asserted over the catalogue, not over ten hand-written cases.

    A test naming each rule would pass for the ten that exist and say nothing about the eleventh.
    """

    def test_only_a_rule_in_force_may_be_critical(self) -> None:
        for rule in CATALOGUE:
            if rule.severity is Severity.CRITICAL:
                assert rule.status is RuleStatus.IN_FORCE, (
                    f"{rule.code} would block an owner on the strength of {rule.status.value} law"
                )

    def test_the_constructor_refuses_the_combination_outright(self) -> None:
        """The guarantee above is a property of `Rule`, not a convention this file checks.

        Without this, the class above only says the ten rules happen to be fine today.
        """
        with pytest.raises(ValueError, match="only a rule in force may be critical"):
            rules.Rule(
                code="x.y",
                title="A rule about law that has not commenced",
                instrument="Something not yet in force",
                commencement=date(2030, 1, 1),
                checked_on=_TODAY,
                status=RuleStatus.NOTIFIED_NOT_IN_FORCE,
                severity=Severity.CRITICAL,
                evaluate=lambda _facts: None,
            )

    def test_every_rule_carries_an_instrument_a_commencement_and_a_checked_date(self) -> None:
        """*"Look it up, cite the instrument, and record the date checked."*

        The `checked_on` date is the one people forget, and it is the one that tells a future
        reader whether the citation is worth trusting.
        """
        for rule in CATALOGUE:
            assert rule.instrument.strip(), f"{rule.code} cites no instrument"
            assert isinstance(rule.commencement, date)
            assert isinstance(rule.checked_on, date)
            assert rule.checked_on >= rule.commencement or rule.commencement > _TODAY, (
                f"{rule.code} was checked before the instrument it cites commenced"
            )

    def test_a_rule_not_yet_commenced_is_never_in_force(self) -> None:
        """The distinction `docs/compliance-rules.md` names as the second standing rule."""
        for rule in CATALOGUE:
            if rule.commencement > _TODAY:
                assert rule.status is not RuleStatus.IN_FORCE, (
                    f"{rule.code} commences {rule.commencement} and is marked in force today"
                )

    def test_codes_are_unique_and_shaped_like_a_code(self) -> None:
        assert len(set(codes())) == len(CATALOGUE)
        for code in codes():
            assert "." in code, f"{code} is not scoped to an area"

    def test_a_clean_restaurant_produces_nothing_at_all(self) -> None:
        """The silence the owner's card depends on. If this ever fails, every card is noisy."""
        assert evaluate(_facts()) == []


class TestTheLicenceRules:
    def test_an_expired_licence_is_critical(self) -> None:
        found = evaluate(_facts(fssai_expires_on=_TODAY - timedelta(days=1)))
        assert [finding.code for _, finding in found] == ["fssai.expired"]
        assert found[0][1].severity is Severity.CRITICAL

    def test_the_day_it_expires_is_not_yet_expired(self) -> None:
        """A licence valid *to* a date is valid on it. Off by one here is a false alarm on the
        busiest possible day to receive one."""
        found = {finding.code for _, finding in evaluate(_facts(fssai_expires_on=_TODAY))}
        assert "fssai.expired" not in found

    def test_expiry_inside_the_window_warns_and_outside_it_does_not(self) -> None:
        inside = _TODAY + timedelta(days=EXPIRY_WARNING_DAYS - 1)
        outside = _TODAY + timedelta(days=EXPIRY_WARNING_DAYS + 1)
        assert "fssai.expiring" in {c for c, _ in _codes(_facts(fssai_expires_on=inside))}
        assert "fssai.expiring" not in {c for c, _ in _codes(_facts(fssai_expires_on=outside))}

    def test_a_licence_that_is_not_fourteen_digits_is_malformed(self) -> None:
        assert "fssai.malformed" in _fired(_facts(fssai_licence="123"))

    def test_a_missing_licence_is_reported_once_not_three_times(self) -> None:
        """Three licence rules over one absent field would be three alarms about one thing, and an
        owner reading three would conclude the product is broken rather than that they are."""
        fired = _fired(_facts(fssai_licence=None, fssai_expires_on=None))
        assert len([code for code in fired if code.startswith("fssai.")]) == 1


class TestTheTierRule:
    def test_turnover_above_the_registration_ceiling_needs_a_licence_not_a_registration(
        self,
    ) -> None:
        over = rules.BASIC_REGISTRATION_CEILING + Decimal("1")
        assert "fssai.tier" in _fired(_facts(annual_turnover=over, fssai_licence=_REGISTRATION))

    def test_unknown_turnover_says_nothing_rather_than_says_you_are_fine(self) -> None:
        """`None` is not zero. A restaurant with nothing recorded is not a restaurant under the
        ceiling, and a rule that treated it as one would go quiet exactly where it is least
        informed."""
        assert "fssai.tier" not in _fired(_facts(annual_turnover=None))


class TestTheTaxRules:
    def test_a_registered_restaurant_issuing_invoices_without_a_gstin_is_critical(self) -> None:
        found = _fired(_facts(gstin=None))
        assert "gst.gstin_missing" in found

    def test_an_unregistered_restaurant_is_not_asked_for_a_gstin(self) -> None:
        assert "gst.gstin_missing" not in _fired(
            _facts(gstin=None, gst_scheme="unregistered", invoices_issued=0)
        )

    def test_a_tax_group_with_no_current_rate_is_critical(self) -> None:
        assert "gst.rate_missing" in _fired(_facts(tax_groups_without_a_current_rate=1))


class TestTheLabellingRules:
    def test_items_without_an_allergen_statement_warn(self) -> None:
        assert "labelling.allergens" in _fired(_facts(items_without_allergens=3))

    def test_calories_are_asked_of_a_chain_and_not_of_a_single_restaurant(self) -> None:
        """The threshold is the rule. A single-outlet restaurant told to print calorie counts is
        the product inventing an obligation, which is the failure mode this module was built to
        avoid rather than to cause.

        This test was written asserting the wrong thing first: the default licence in this file was
        `10012345678901`, whose state code is `00` — a Central licence, covered on its own limb
        regardless of outlet count. The rule was right and the fixture was a chain by accident.
        """
        small = _facts(outlets=CALORIE_OUTLET_THRESHOLD - 1, items_without_calories=10)
        large = _facts(outlets=CALORIE_OUTLET_THRESHOLD, items_without_calories=10)
        assert "labelling.calories" not in _fired(small)
        assert "labelling.calories" in _fired(large)

    def test_a_central_licence_is_covered_on_its_own_however_few_outlets(self) -> None:
        """The other limb. One restaurant with a Central licence is covered; the outlet count is
        an alternative to it, not a condition on it."""
        alone = _facts(fssai_licence=_CENTRAL_LICENCE, outlets=1, items_without_calories=10)
        assert "labelling.calories" in _fired(alone)


class TestTheTwoThatMayNotBlock:
    def test_dpdp_is_advisory_and_says_it_has_not_commenced(self) -> None:
        rule = rule_for("dpdp.consent")
        assert rule is not None
        assert rule.status is RuleStatus.NOTIFIED_NOT_IN_FORCE
        assert rule.severity is Severity.ADVISORY
        assert rule.commencement > _TODAY

    def test_service_charge_is_advisory_and_says_the_position_is_unsettled(self) -> None:
        rule = rule_for("ccpa.service_charge")
        assert rule is not None
        assert rule.status is RuleStatus.UNSETTLED
        assert rule.severity is Severity.ADVISORY
        finding = rule.evaluate(_facts(service_charge_rate=Decimal("0.10")))
        assert finding is not None
        assert "appeal is pending" in finding.risk

    def test_worst_comes_first(self) -> None:
        """An owner reads the top of the list. If an advisory can outrank a critical, the one thing
        that could shut the restaurant is below the fold."""
        found = evaluate(
            _facts(fssai_expires_on=_TODAY - timedelta(days=1), service_charge_rate=Decimal("0.1"))
        )
        assert [finding.severity for _, finding in found] == [Severity.CRITICAL, Severity.ADVISORY]


# --- the service, against a database ----------------------------------------------------------


async def _world(session: AsyncSession, **restaurant: object) -> tuple[Restaurant, Employee]:
    """One restaurant with whatever defect the test is about, and somebody to act on it."""
    organization = Organization(name="Spice Garden", slug=f"sg-{uuid.uuid4().hex[:8]}")
    session.add(organization)
    await session.flush()
    fields: dict[str, object] = {
        "gstin": _GOOD_GSTIN,
        "fssai_licence": _GOOD_LICENCE,
        "fssai_licence_expires_on": _TODAY + timedelta(days=200),
        "gst_scheme": "regular",
    }
    fields.update(restaurant)
    place = Restaurant(
        organization_id=organization.id,
        name="Spice Garden",
        code="R1",
        timezone="Asia/Kolkata",
        business_day_start=time(5, 0),
        **fields,
    )
    session.add(place)
    await session.flush()
    person = Employee(
        organization_id=organization.id,
        employee_code=f"E{uuid.uuid4().hex[:6]}",
        full_name="Owner",
        employment_type="full_time",
        joined_on=_TODAY - timedelta(days=365),
    )
    session.add(person)
    await session.flush()
    return place, person


def _service(session: AsyncSession, place: Restaurant) -> ComplianceService:
    return ComplianceService(
        session,
        TenantScope(organization_id=place.organization_id, restaurant_id=place.id),
    )


class TestEvaluationHappensOnRead:
    async def test_a_clean_restaurant_raises_nothing_and_the_card_stays_silent(
        self, db_session: AsyncSession
    ) -> None:
        place, _ = await _world(db_session)
        review = await _service(db_session, place).review(now=_NOW)

        assert review.items == ()
        assert review.outstanding == 0

    async def test_opening_the_screen_raises_the_finding_and_records_the_event(
        self, db_session: AsyncSession
    ) -> None:
        place, _ = await _world(db_session, fssai_licence_expires_on=_TODAY - timedelta(days=1))
        review = await _service(db_session, place).review(now=_NOW)

        assert [item.finding.rule_code for item in review.items] == ["fssai.expired"]
        assert review.outstanding == 1
        events = (
            await db_session.scalars(
                select(ComplianceEvent).where(
                    ComplianceEvent.compliance_finding_id == review.items[0].finding.id
                )
            )
        ).all()
        assert [event.type for event in events] == ["raised"]
        # Nobody did this, so nobody is named.
        assert events[0].actor_employee_id is None

    async def test_raised_at_is_when_the_product_noticed_not_when_the_condition_began(
        self, db_session: AsyncSession
    ) -> None:
        """The consequence of having no background job, asserted rather than assumed.

        The licence expired six months ago; the finding is dated today, because today is when
        somebody opened the screen. The export says this in words for the same reason.
        """
        expired_long_ago = _TODAY - timedelta(days=180)
        place, _ = await _world(db_session, fssai_licence_expires_on=expired_long_ago)
        review = await _service(db_session, place).review(now=_NOW)

        assert review.items[0].finding.raised_at == _NOW

    async def test_opening_it_twice_does_not_raise_it_twice(self, db_session: AsyncSession) -> None:
        """A licence does not expire twice. Without this the list becomes a log within a week."""
        place, _ = await _world(db_session, fssai_licence_expires_on=_TODAY - timedelta(days=1))
        service = _service(db_session, place)
        await service.review(now=_NOW)
        second = await service.review(now=_NOW + timedelta(hours=1))

        assert len(second.items) == 1
        assert second.items[0].finding.raised_at == _NOW

    async def test_fixing_the_condition_resolves_the_finding_without_deleting_it(
        self, db_session: AsyncSession
    ) -> None:
        place, _ = await _world(db_session, fssai_licence_expires_on=_TODAY - timedelta(days=1))
        service = _service(db_session, place)
        await service.review(now=_NOW)

        place.fssai_licence_expires_on = _TODAY + timedelta(days=365)
        await db_session.flush()
        later = _NOW + timedelta(days=1)
        review = await service.review(now=later)

        assert review.items == ()
        history = await service.history()
        assert len(history) == 1
        assert history[0].finding.state == "resolved"
        assert history[0].finding.resolved_at == later

    async def test_the_same_rule_may_fire_again_after_it_was_resolved(
        self, db_session: AsyncSession
    ) -> None:
        """Why the uniqueness index is partial. A full one would make next year's expiry
        unrecordable, which is the opposite of keeping a record."""
        place, _ = await _world(db_session, fssai_licence_expires_on=_TODAY - timedelta(days=1))
        service = _service(db_session, place)
        await service.review(now=_NOW)
        place.fssai_licence_expires_on = _TODAY + timedelta(days=365)
        await db_session.flush()
        await service.review(now=_NOW + timedelta(days=1))

        place.fssai_licence_expires_on = _TODAY - timedelta(days=1)
        await db_session.flush()
        again = await service.review(now=_NOW + timedelta(days=2))

        assert len(again.items) == 1
        assert len(await service.history()) == 2


class TestWhatAPersonCanDoAboutIt:
    async def test_acknowledging_is_an_event_and_survives_the_next_evaluation(
        self, db_session: AsyncSession
    ) -> None:
        place, person = await _world(
            db_session, fssai_licence_expires_on=_TODAY - timedelta(days=1)
        )
        service = _service(db_session, place)
        review = await service.review(now=_NOW)
        await service.acknowledge(
            review.items[0].finding.id, actor_employee_id=person.id, at=_NOW + timedelta(minutes=5)
        )

        again = await service.review(now=_NOW + timedelta(hours=2))
        assert again.items[0].finding.state == "acknowledged"
        # Acknowledged is not outstanding: the card is for things nobody has looked at.
        assert again.outstanding == 0

    async def test_suppressing_requires_a_reason_and_keeps_it(
        self, db_session: AsyncSession
    ) -> None:
        place, person = await _world(db_session)
        await _menu_item_without_allergens(db_session, place)
        service = _service(db_session, place)
        review = await service.review(now=_NOW)
        finding = next(
            item.finding for item in review.items if item.finding.rule_code == "labelling.allergens"
        )

        with pytest.raises(AppError, match="part of the record"):
            await service.suppress(finding.id, actor_employee_id=person.id, reason="   ", at=_NOW)

        await service.suppress(
            finding.id,
            actor_employee_id=person.id,
            reason="The printed menu carries the statement; the screen copy is being updated.",
            at=_NOW,
        )
        events = (
            await db_session.scalars(
                select(ComplianceEvent).where(
                    ComplianceEvent.compliance_finding_id == finding.id,
                    ComplianceEvent.type == "suppressed",
                )
            )
        ).all()
        assert len(events) == 1
        assert events[0].actor_employee_id == person.id
        assert "printed menu" in (events[0].reason or "")

    async def test_a_suppressed_finding_is_still_in_the_record(
        self, db_session: AsyncSession
    ) -> None:
        """*"Advice ignored is still advice given."* Suppression is a decision, not a delete."""
        place, person = await _world(db_session)
        await _menu_item_without_allergens(db_session, place)
        service = _service(db_session, place)
        review = await service.review(now=_NOW)
        finding = next(
            item.finding for item in review.items if item.finding.rule_code == "labelling.allergens"
        )
        await service.suppress(
            finding.id, actor_employee_id=person.id, reason="Handled on the printed menu.", at=_NOW
        )

        history = await service.history()
        assert [item.finding.state for item in history] == ["suppressed"]

    async def test_acting_on_something_already_put_right_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        place, person = await _world(
            db_session, fssai_licence_expires_on=_TODAY - timedelta(days=1)
        )
        service = _service(db_session, place)
        review = await service.review(now=_NOW)
        finding_id = review.items[0].finding.id
        place.fssai_licence_expires_on = _TODAY + timedelta(days=365)
        await db_session.flush()
        await service.review(now=_NOW + timedelta(days=1))

        with pytest.raises(ConflictError, match="already been put right"):
            await service.acknowledge(finding_id, actor_employee_id=person.id, at=_NOW)

    async def test_another_restaurants_finding_is_not_found(self, db_session: AsyncSession) -> None:
        """Invariant 1, at the one place in this module that takes an id from a caller."""
        mine, person = await _world(db_session)
        theirs, _ = await _world(db_session, fssai_licence_expires_on=_TODAY - timedelta(days=1))
        theirs_review = await _service(db_session, theirs).review(now=_NOW)

        with pytest.raises(NotFoundError):
            await _service(db_session, mine).acknowledge(
                theirs_review.items[0].finding.id, actor_employee_id=person.id, at=_NOW
            )


class TestTheWordsAreFrozen:
    async def test_the_sentences_are_copied_onto_the_row(self, db_session: AsyncSession) -> None:
        """The catalogue's wording will improve. What an owner was told must not change under them,
        and an export produced next year has to reproduce what the screen said this year."""
        place, _ = await _world(db_session, fssai_licence_expires_on=_TODAY - timedelta(days=1))
        review = await _service(db_session, place).review(now=_NOW)
        row = (await db_session.scalars(select(ComplianceFinding))).one()

        assert row.title == review.items[0].finding.title
        assert row.risk.strip() != ""
        assert row.action.strip() != ""
        assert row.evidence != {}

    def test_the_export_appendix_lists_every_rule_including_the_quiet_ones(self) -> None:
        """*"We checked these ten things"* is a different claim from *"here are three problems"*,
        and it is the one an inspection is interested in."""
        appendix = catalogue()

        assert len(appendix) == len(CATALOGUE)
        for _, title, citation, _severity in appendix:
            assert title.strip()
            assert citation.instrument.strip()
            assert citation.status in {status.value for status in RuleStatus}


async def _menu_item_without_allergens(session: AsyncSession, place: Restaurant) -> None:
    category = MenuCategory(restaurant_id=place.id, code="MAIN", name="Mains", seq=1)
    station = Station(restaurant_id=place.id, code="TAND", name="Tandoor", seq=1)
    session.add_all([category, station])
    await session.flush()
    session.add(
        MenuItem(
            restaurant_id=place.id,
            menu_category_id=category.id,
            code="P1",
            name="Paneer Tikka",
            food_type="veg",
            station_id=station.id,
            seq=1,
        )
    )
    await session.flush()


def _codes(facts: Facts) -> list[tuple[str, Severity]]:
    return [(finding.code, finding.severity) for _, finding in evaluate(facts)]


def _fired(facts: Facts) -> set[str]:
    return {code for code, _ in _codes(facts)}
