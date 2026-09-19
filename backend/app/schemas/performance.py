"""Performance on the wire, and the shapes that make a bottom ranking impossible to send.

**There is no `rank` on anything returned to a team.** `MyScoreResponse` carries one, because "you
were third of nine" is a thing to say to somebody about themselves; `TeamLineResponse` does not,
because a list of ranks *is* a ranking and the bottom of it is somebody.

**Every figure carries the count it came from.** `docs/workload-fairness.md` §5 names attribution as
the weakest link in the whole design — a captain entering orders for a section, a complaint filed
against the server rather than the kitchen — and the mitigation is that a wrong attribution shows up
as a wrong *number of things*, which a person can point at and argue with.

**Every figure carries its sentence.** The employee's own view is plain English rather than a
formula: *"You served 214 covers in 38 hours. That is 5.6 an hour."* Built on the server so the
screen, an export and any future translation say the same thing.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class MetricResponse(_Schema):
    key: str
    value: str
    # controllable | context. A context metric is shown and scores nothing (ADR 0011).
    kind: str
    # How many things the rate was computed from. The attribution mitigation.
    count: int
    # Whether it contributed to the points at all.
    weighted: bool
    # Plain English, from the server: "5.6 covers an hour, from 214 covers."
    sentence: str


class MyScoreResponse(_Schema):
    """What a person sees about themselves — the one view every role holds (ADR 0011)."""

    period_id: uuid.UUID
    employee_id: uuid.UUID
    hours: str
    points: str
    # Their own position, which is a thing to tell somebody about themselves. It is never part of
    # a list of other people.
    rank: int | None
    of: int
    metrics: list[MetricResponse]
    # What this is used for, said in the product rather than only in a document. If it stops being
    # true, the sentence is a lie somebody will notice.
    purpose: str


class TeamLineResponse(_Schema):
    """One row of the team view. **Deliberately has no rank.**"""

    employee_id: uuid.UUID
    points: str
    hours: str


class TeamResponse(_Schema):
    period_id: uuid.UUID
    # Whether the team is large enough for anybody to be shown anybody else at all.
    shows_others: bool
    lines: list[TeamLineResponse]


class ShareResponse(_Schema):
    """One row of the workload distribution — the module's primary screen."""

    employee_id: uuid.UUID
    hours: str
    covers: int
    orders: int
    assists: int
    covers_share: str
    hours_share: str
    # A share of the work above a share of the roster. A fact about the rota, not about the person.
    carrying_more_than_their_hours: bool


class DistributionResponse(_Schema):
    since: date
    until: date
    lines: list[ShareResponse]


class SchemeResponse(_Schema):
    id: uuid.UUID
    name: str
    period_type: str
    weights: dict[str, str]
    is_active: bool
    effective_from: date


class SchemeCreateRequest(_Schema):
    name: str
    period_type: str
    weights: dict[str, str]
    effective_from: date


class PeriodResponse(_Schema):
    id: uuid.UUID
    incentive_scheme_id: uuid.UUID
    period_start: date
    period_end: date
    status: str
    published_at: datetime | None
    # How many challenges are still unanswered. A period cannot be published while this is not zero.
    unanswered_disputes: int
    # People who worked this period and have **no way to sign in**, so no way to see their own
    # figures (ADR 0007 makes an employee without a login normal; ADR 0011 §3 promises everybody
    # can see their own score). They are left out of the freeze rather than scored blind, and
    # they are named here so the owner can decide what to do about it.
    unscored: tuple[str, ...] = ()


class PeriodSummaryResponse(_Schema):
    """Just enough to choose a period from a list, and **deliberately not `PeriodResponse`**.

    That one carries `unanswered_disputes` and `unscored` — how many people have challenged their
    figures, and the names of people who cannot see theirs. Both are a manager's business. This
    shape is what the screen every role can open needs to fill a dropdown, and nothing else: when
    it ran, whether it is frozen, and what to call it.
    """

    id: uuid.UUID
    period_start: date
    period_end: date
    status: str
    # "1-7 September", built on the server so a future translation changes one place.
    label: str


class PeriodCreateRequest(_Schema):
    incentive_scheme_id: uuid.UUID
    period_start: date
    period_end: date


class NoteResponse(_Schema):
    id: uuid.UUID
    employee_id: uuid.UUID
    author_employee_id: uuid.UUID
    kind: str
    note: str
    answer: str | None
    answered_at: datetime | None


class NoteCreateRequest(_Schema):
    employee_id: uuid.UUID
    note: str
    # context | dispute. A dispute is raised by the person whose figures they are.
    kind: str = "context"
    visible_to_employee: bool = True


class AnswerRequest(_Schema):
    answer: str


class AwardResponse(_Schema):
    id: uuid.UUID
    employee_id: uuid.UUID
    type: str
    amount: str | None
    # What it is for, in words. An award with a number and no sentence is a payment.
    citation: str
    granted_by: uuid.UUID
    granted_at: datetime


class AwardCreateRequest(_Schema):
    employee_id: uuid.UUID
    type: str
    citation: str
    amount: Decimal | None = None
    performance_period_id: uuid.UUID | None = None
