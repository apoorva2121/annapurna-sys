"""Evaluating the catalogue, and keeping the record of what it found.

**Evaluation runs when somebody opens the screen.** ADR 0005 leaves this product with no background
job, so there is no nightly sweep to raise a finding at midnight. That has one consequence worth
saying out loud rather than discovering during an inspection: **`raised_at` is when the product
first noticed, not when the condition began.** A licence that expired in March and is first opened
in June raises a finding dated June. The export says so in as many words.

**Raising and resolving are the product's acts; acknowledging and suppressing are a person's.**
The first two carry no actor because nobody did them. The last two always do, and suppression
additionally carries a reason — an owner may dismiss a finding, and what they said is the record of
the decision. Advice ignored is still advice given.

**Nothing here decides whether a rule may block.** That is settled structurally in
`app/core/compliance.py`: a `Rule` whose status is not `in_force` cannot be constructed with
`critical` severity. This module never re-checks it, because a second implementation of a rule is
a second place for it to be wrong.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.compliance import CATALOGUE, Finding, Rule, Severity, evaluate, rule_for
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.ids import uuid7
from app.core.shift_window import business_day_for
from app.core.tenancy import TenantScope
from app.models.compliance import ComplianceFinding
from app.models.tenancy import Restaurant
from app.repositories.compliance import ComplianceFactsRepository, ComplianceFindingRepository


@dataclass(frozen=True)
class Citation:
    """What a rule is, for somebody who wants to check the product's working.

    Carried beside every finding rather than looked up separately, because the whole point of the
    export is that a reader does not have to trust the product to follow it.
    """

    instrument: str
    commencement: date
    checked_on: date
    status: str


@dataclass(frozen=True)
class Item:
    """One finding as the API returns it: the row, plus the rule it came from."""

    finding: ComplianceFinding
    citation: Citation | None


@dataclass(frozen=True)
class Review:
    """The whole answer. `as_of` is the moment of evaluation, which is what `raised_at` means."""

    as_of: datetime
    business_date: date
    items: tuple[Item, ...]
    # Counted from the live findings a person has not already dealt with — the owner's card is
    # silent when this is zero, which is the module's one visible promise.
    outstanding: int


class ComplianceService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self.facts = ComplianceFactsRepository(session, scope)
        self.findings = ComplianceFindingRepository(session, scope)

    async def review(self, *, now: datetime) -> Review:
        """Evaluate, reconcile, and answer. The one entry point the screens use.

        Reconciliation is deliberately small: a rule that fires and has no live finding raises one;
        a live finding whose rule no longer fires is resolved. **A rule that fires and already has a
        live finding is left alone** — including its `state`, so acknowledging something does not
        un-acknowledge itself the next time somebody opens the screen.
        """
        today = await self._business_date(now)
        fired = {
            finding.code: (rule, finding)
            for rule, finding in evaluate(await self.facts.facts(today=today))
        }
        live = {row.rule_code: row for row in await self.findings.live()}

        for code, (_, finding) in fired.items():
            if code not in live:
                live[code] = await self._raise(finding, at=now)

        for code, row in list(live.items()):
            if code not in fired:
                self._resolve(row, at=now)
                del live[code]

        await self.session.flush()
        items = tuple(self._item(row) for row in await self.findings.live())
        outstanding = sum(1 for item in items if item.finding.state == "open")
        return Review(as_of=now, business_date=today, items=items, outstanding=outstanding)

    async def history(self, *, limit: int | None = None) -> tuple[Item, ...]:
        """Everything ever raised, resolved rows included. What the export is built from."""
        return tuple(self._item(row) for row in await self.findings.history(limit=limit))

    async def acknowledge(
        self, finding_id: uuid.UUID, *, actor_employee_id: uuid.UUID, at: datetime
    ) -> ComplianceFinding:
        """*"I have seen this."* It does not make the finding go away — only the condition can."""
        return await self._act(
            finding_id, state="acknowledged", actor_employee_id=actor_employee_id, at=at
        )

    async def suppress(
        self, finding_id: uuid.UUID, *, actor_employee_id: uuid.UUID, reason: str, at: datetime
    ) -> ComplianceFinding:
        """*"I have decided not to act on this, and here is why."*

        A reason is required, and the database requires it too. A dismissal with no reason
        attached is indistinguishable afterwards from a misclick, and this row is the one an
        inspection reads.
        """
        if not reason.strip():
            raise AppError(
                "compliance.reason_required",
                "Say why this is being set aside. The reason is part of the record.",
            )
        return await self._act(
            finding_id,
            state="suppressed",
            actor_employee_id=actor_employee_id,
            at=at,
            reason=reason.strip(),
        )

    # --- the three writes, in one place each -------------------------------------------------

    async def _raise(self, finding: Finding, *, at: datetime) -> ComplianceFinding:
        """The sentences are copied onto the row rather than referenced.

        The catalogue's wording will improve; what an owner was told must not change underneath
        them, and an export produced next year has to reproduce what the screen said this year.
        """
        row = ComplianceFinding(
            # Assigned here rather than at flush: the event below references it, and the two are
            # one act. ADR 0008 puts ids in Python precisely so this does not need a round trip.
            id=uuid7(),
            restaurant_id=self.scope.restaurant_id,
            rule_code=finding.code,
            severity=finding.severity.value,
            state="open",
            title=finding.title,
            risk=finding.risk,
            action=finding.action,
            evidence=finding.evidence,
            raised_at=at,
        )
        self.session.add(row)
        # Flushed before the event, not with it. The event's composite foreign key names the
        # finding's (id, restaurant_id), and these two mappers have no declared relationship
        # for the unit of work to order them by — which showed up as
        # `ForeignKeyViolationError: Key (compliance_finding_id, restaurant_id)=(...) is not
        # present in table "compliance_finding"` on the very first review.
        await self.session.flush()
        self.findings.add_event(row, kind="raised", at=at)
        return row

    def _resolve(self, row: ComplianceFinding, *, at: datetime) -> None:
        """The condition stopped being true. No actor, because nobody did this."""
        row.state = "resolved"
        row.resolved_at = at
        self.findings.add_event(row, kind="resolved", at=at)

    async def _act(
        self,
        finding_id: uuid.UUID,
        *,
        state: str,
        actor_employee_id: uuid.UUID,
        at: datetime,
        reason: str | None = None,
    ) -> ComplianceFinding:
        row = await self.findings.get(finding_id)
        if row is None:
            raise NotFoundError("compliance_finding.not_found", "That finding is not on this list.")
        if row.state == "resolved":
            # Not an error worth a special code: the condition has gone, and acting on it now
            # would attach a decision to something nobody has to decide about.
            raise ConflictError(
                "compliance_finding.already_resolved",
                "This has already been put right, so there is nothing to act on.",
            )
        row.state = state
        self.findings.add_event(
            row, kind=state, at=at, actor_employee_id=actor_employee_id, reason=reason
        )
        await self.session.flush()
        return row

    # --- helpers -----------------------------------------------------------------------------

    def _item(self, row: ComplianceFinding) -> Item:
        rule = rule_for(row.rule_code)
        return Item(finding=row, citation=None if rule is None else _cite(rule))

    async def _business_date(self, now: datetime) -> date:
        """Invariant 4. A finding raised at 01:00 belongs to the business day that is still open."""
        restaurant = await self.session.get(Restaurant, self.scope.restaurant_id)
        if restaurant is None:
            raise NotFoundError("restaurant.not_found", "Restaurant not found.")
        return business_day_for(now, restaurant.timezone, restaurant.business_day_start)


def _cite(rule: Rule) -> Citation:
    return Citation(
        instrument=rule.instrument,
        commencement=rule.commencement,
        checked_on=rule.checked_on,
        status=rule.status.value,
    )


def catalogue() -> tuple[tuple[str, str, Citation, Severity], ...]:
    """The whole catalogue, for the export's appendix and for the tests.

    Ten rules is a number a person can read, so the export lists every one of them — including the
    ones that did not fire. *"We checked these ten things"* is a different claim from *"here are
    three problems"*, and it is the one an inspection is actually interested in.
    """
    return tuple((rule.code, rule.title, _cite(rule), rule.severity) for rule in CATALOGUE)
