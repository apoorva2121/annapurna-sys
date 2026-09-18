"""Compliance on the wire, and the field that stops this product from being confidently wrong.

**Every finding carries its citation, and the citation carries `checked_on`.** `status` is one of
four — `in_force`, `notified_not_in_force`, `unsettled`, `unverified` — and it is on the wire rather
than folded into severity because the screen has to be able to say *"this is not law today"* in the
words an owner reads. `docs/compliance-rules.md`: *"never conflate in force with notified but not in
force with unsettled with unverified. Only the first is safe to build on, and only the first may
block a user."*

**`raised_at` means when the product first noticed.** There is no background job (ADR 0005), so a
condition that began in March and was first opened in June is dated June. The export says so in a
sentence rather than leaving a reader to infer it, because an inspection is exactly the wrong place
to discover a date meant something else.

**The evidence is on the wire too.** A warning a person cannot check is a warning they must either
take on faith or ignore, and the second is what actually happens.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CitationResponse(_Schema):
    """What the rule is, so a reader can verify rather than trust."""

    instrument: str
    commencement: date
    # The date somebody last confirmed this citation against the instrument. The field people
    # forget, and the one that tells a future reader whether the rest is worth believing.
    checked_on: date
    # in_force | notified_not_in_force | unsettled | unverified
    status: str


class FindingResponse(_Schema):
    id: uuid.UUID
    rule_code: str
    # critical | warning | advisory. Only a rule in force can be critical, enforced in
    # `app/core/compliance.py` rather than here.
    severity: str
    # open | acknowledged | suppressed | resolved
    state: str
    title: str
    risk: str
    action: str
    evidence: dict[str, object]
    raised_at: datetime
    resolved_at: datetime | None
    citation: CitationResponse | None


class ReviewResponse(_Schema):
    """The list, and the two dates that say what it means."""

    as_of: datetime
    business_date: date
    # Open findings only — acknowledged and suppressed ones are dealt with. The owner's card is
    # silent when this is zero, which is the module's one visible promise.
    outstanding: int
    findings: tuple[FindingResponse, ...]


class RuleResponse(_Schema):
    """One entry in the appendix: a rule that was checked, whether or not it found anything."""

    code: str
    title: str
    severity: str
    citation: CitationResponse


class CatalogueResponse(_Schema):
    """*"We checked these ten things"* is a different claim from *"here are three problems"*, and
    it is the one an inspection is interested in."""

    rules: tuple[RuleResponse, ...]


class ActRequest(_Schema):
    """Acknowledging takes no reason; suppressing requires one, and the database agrees."""

    reason: str | None = None
