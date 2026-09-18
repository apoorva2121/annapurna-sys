"""Scoring, publishing, and the four refusals that decide what this feature is.

`docs/workload-fairness.md` opens by naming the risk in the same breath as the goal: *"a measurement
system aimed at morale can destroy morale if built carelessly."* Everything in this file is one of
those two things, and the refusals are the interesting half.

**A scheme that would pay people to rush is refused** (`app/core/scoring.py`).

**A period with an unanswered dispute cannot be published.** Visibility without recourse is the
shape of surveillance rather than of feedback, and a freeze is the moment the number stops being
arguable — so the argument has to happen first.

**A published period never moves.** ADR 0011, and the same reason `theoretical_food_cost` is frozen
at settlement: a later void must not rewrite the basis on which a bonus was already paid.

**Nothing here returns a bottom ranking.** `team()` gives the top and the viewer's own row, and
below five scored people it gives nobody else's at all — with three waiters, naming the top two
names the third.

And one thing that is not a refusal but is the module's actual purpose: **`distribution()` is the
primary screen**, because the finding an owner usually needs is *the roster is unfair*, not *this
person is bad*.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.audit import audited
from app.core.enums import (
    PerformanceMetricKind,
    PerformanceNoteKind,
    PerformancePeriodStatus,
)
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.scoring import (
    METRICS,
    Metric,
    SchemeError,
    points_for,
    validate_weights,
    visible_team,
)
from app.core.tenancy import TenantScope
from app.models.performance import (
    IncentiveScheme,
    PerformanceNote,
    PerformancePeriod,
    PerformanceScore,
    RecognitionAward,
)
from app.repositories.performance import PerformanceRepository, Quality, Served, Worked

_RATE = Decimal("0.0001")
_ZERO = Decimal("0")
# A rating is out of five; the score wants a fraction of the best possible.
_MAX_RATING = Decimal("5")
# Covers per hour that counts as a full mark. Chosen from `docs/seed-data.md`'s own figures — ~110
# covers over a service across the floor — and adjustable only by changing this constant, on
# purpose: a threshold in the configuration is a threshold somebody tunes until the answer flatters.
_COVERS_PER_HOUR_TARGET = Decimal("6")


@dataclass(frozen=True, slots=True)
class Line:
    """One person's figures for a period, live or frozen."""

    employee_id: uuid.UUID
    hours: Decimal
    metrics: dict[str, Metric]
    points: Decimal
    rank: int | None = None


@dataclass(frozen=True, slots=True)
class Share:
    """One person's share of the period's work — the distribution screen's row."""

    employee_id: uuid.UUID
    hours: Decimal
    covers: int
    orders: int
    assists: int
    covers_share: Decimal
    hours_share: Decimal

    @property
    def carrying_more_than_their_hours(self) -> bool:
        """The finding the screen exists for: a share of the work above a share of the roster."""
        return self.covers_share > self.hours_share


class PerformanceService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._repository = PerformanceRepository(session, scope)

    # ------------------------------------------------------------------ the scheme

    @audited("incentive_scheme.created", entity="incentive_scheme")
    async def create_scheme(
        self,
        actor: Actor,  # noqa: ARG002 - read by @audited
        *,
        name: str,
        period_type: str,
        weights: dict[str, object],
        effective_from: date,
    ) -> IncentiveScheme:
        """Save a weighting, or refuse it with the sentence that says why.

        The refusal is the point: `validate_weights` is where "volume never stands alone" stops
        being a principle in a document and becomes something the product will not do.
        """
        scheme = IncentiveScheme(
            restaurant_id=self.scope.restaurant_id,
            name=name.strip(),
            period_type=period_type,
            weights={key: str(value) for key, value in _checked(weights).items()},
            is_active=True,
            effective_from=effective_from,
        )
        self.session.add(scheme)
        await self.session.flush()
        return scheme

    # ------------------------------------------------------------------ the period

    async def open_period(
        self,
        actor: Actor,  # noqa: ARG002 - opening a draft records nothing; publishing it does
        *,
        scheme_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> PerformancePeriod:
        scheme = await self._repository.scheme(scheme_id)
        if scheme is None:
            raise NotFoundError("incentive_scheme.not_found", "That scheme does not exist here.")
        if period_end < period_start:
            raise AppError(
                "performance.period_backwards",
                "That period ends before it starts.",
                status_code=422,
            )
        period = PerformancePeriod(
            restaurant_id=self.scope.restaurant_id,
            incentive_scheme_id=scheme.id,
            period_start=period_start,
            period_end=period_end,
            status=PerformancePeriodStatus.DRAFT.value,
        )
        self.session.add(period)
        await self.session.flush()
        return period

    async def draft(self, period_id: uuid.UUID) -> list[Line]:
        """The live figures for a period. Computed now, stored nowhere.

        While a period is draft this is the whole of it — `docs/schema.md`'s elimination of
        `waiter_performance` still holding, because nothing here has been used to pay anybody yet.
        """
        period = await self._require_period(period_id)
        scheme = await self._repository.scheme(period.incentive_scheme_id)
        weights = (
            {}
            if scheme is None
            else {key: Decimal(str(value)) for key, value in scheme.weights.items()}
        )
        return await self._compute(period.period_start, period.period_end, weights)

    @audited("performance_period.published", entity="performance_period", key="period_id")
    async def publish(self, actor: Actor, period_id: uuid.UUID) -> PerformancePeriod:
        """**The freeze.** After this, the numbers do not move again.

        Two refusals before it, and the second is the one the ethics review asked for:

        - a period already published is not published twice, because the second freeze would
          silently overwrite the first with figures computed from data that has since changed;
        - **a period with an unanswered dispute is refused**, because freezing a number somebody
          has challenged, before answering them, is the exact move that turns feedback into
          surveillance.
        """
        period = await self._require_period(period_id)
        if period.status != PerformancePeriodStatus.DRAFT.value:
            raise ConflictError(
                "performance.already_published",
                "That period is already published. Its figures are frozen and do not move.",
            )
        unanswered = await self._repository.unanswered_disputes(period_id)
        if unanswered:
            raise ConflictError(
                "performance.dispute_open",
                f"{unanswered} person has challenged these figures and has not had an answer. "
                "Answer the challenge - accept it, or decline it with a reason - and then publish.",
                details={"unanswered": unanswered},
            )

        lines = await self.draft(period_id)
        ranked = sorted(lines, key=lambda line: line.points, reverse=True)
        now = datetime.now(UTC)
        for position, line in enumerate(ranked, start=1):
            self.session.add(
                PerformanceScore(
                    restaurant_id=self.scope.restaurant_id,
                    performance_period_id=period.id,
                    employee_id=line.employee_id,
                    hours_worked=line.hours,
                    metrics=_frozen(line.metrics),
                    points=line.points,
                    rank_in_period=position,
                )
            )
        period.status = PerformancePeriodStatus.PUBLISHED.value
        period.published_at = now
        period.published_by = actor.employee_id
        await self.session.flush()
        return period

    # ------------------------------------------------------------------ reading it

    async def mine(self, actor: Actor, period_id: uuid.UUID) -> Line | None:
        """A person's own figures — the one view every role holds, always (ADR 0011)."""
        return await self._line_for(period_id, actor.employee_id)

    async def team(self, period_id: uuid.UUID, viewer: uuid.UUID) -> list[Line]:
        """The top of the team, plus the viewer's own row. **Never a bottom ranking.**

        Below five scored people this returns the viewer alone: with three waiters, naming the top
        two names the third, which defeats the rule by arithmetic rather than by intent.
        """
        lines = await self._lines(period_id)
        if not visible_team(len(lines)):
            return [line for line in lines if line.employee_id == viewer]
        ranked = sorted(lines, key=lambda line: line.points, reverse=True)
        top = ranked[: max(1, len(ranked) // 3)]
        own = [line for line in ranked if line.employee_id == viewer]
        shown = {line.employee_id: line for line in top + own}
        return sorted(shown.values(), key=lambda line: line.points, reverse=True)

    async def distribution(self, *, since: date, until: date) -> list[Share]:
        """**The primary screen.** Who handled what share of the work, against their share of the
        hours.

        Not a ranking and not a score: a person carrying 30% of the covers on 20% of the hours is a
        fact about the *roster*, and the fix is usually the rota rather than the person.
        """
        worked = {
            row.employee_id: row for row in await self._repository.worked(since=since, until=until)
        }
        served = {
            row.employee_id: row for row in await self._repository.served(since=since, until=until)
        }
        total_hours = sum((row.hours for row in worked.values()), _ZERO)
        total_covers = sum(row.covers for row in served.values())

        shares = []
        for employee_id, work in worked.items():
            service = served.get(employee_id)
            covers = service.covers if service else 0
            shares.append(
                Share(
                    employee_id=employee_id,
                    hours=work.hours,
                    covers=covers,
                    orders=service.orders if service else 0,
                    assists=service.assists if service else 0,
                    covers_share=_share(Decimal(covers), Decimal(total_covers)),
                    hours_share=_share(work.hours, total_hours),
                )
            )
        return sorted(shares, key=lambda share: share.covers_share, reverse=True)

    # ------------------------------------------------------------------ notes and awards

    async def add_note(
        self,
        actor: Actor,
        *,
        period_id: uuid.UUID,
        employee_id: uuid.UUID,
        note: str,
        kind: str = PerformanceNoteKind.CONTEXT.value,
        visible_to_employee: bool = True,
    ) -> PerformanceNote:
        """Context from a manager, or a dispute from the person being measured.

        A dispute is **always** visible to the person who raised it, whatever the caller asks for:
        a challenge somebody cannot see the state of is not a challenge.
        """
        await self._require_period(period_id)
        if kind == PerformanceNoteKind.DISPUTE.value and employee_id != actor.employee_id:
            raise AppError(
                "performance.dispute_not_yours",
                "A challenge is raised by the person whose figures they are.",
                status_code=422,
            )
        row = PerformanceNote(
            restaurant_id=self.scope.restaurant_id,
            performance_period_id=period_id,
            employee_id=employee_id,
            author_employee_id=actor.employee_id,
            kind=kind,
            note=note.strip(),
            visible_to_employee=(
                True if kind == PerformanceNoteKind.DISPUTE.value else visible_to_employee
            ),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    @audited("performance_note.answered", entity="performance_note", key="note_id")
    async def answer_dispute(
        self, actor: Actor, note_id: uuid.UUID, *, answer: str
    ) -> PerformanceNote:
        """Accept it, or decline it with a reason. Either way, in writing and by a named person."""
        row = await self.session.get(PerformanceNote, note_id) if note_id else None
        if row is None or row.restaurant_id != self.scope.restaurant_id:
            raise NotFoundError("performance_note.not_found", "That note does not exist here.")
        if row.kind != PerformanceNoteKind.DISPUTE.value:
            raise AppError(
                "performance.not_a_dispute",
                "That note is context, not a challenge. There is nothing to answer.",
                status_code=422,
            )
        row.answer = answer.strip()
        row.answered_at = datetime.now(UTC)
        row.answered_by = actor.employee_id
        await self.session.flush()
        return row

    @audited("recognition_award.granted", entity="recognition_award")
    async def grant_award(
        self,
        actor: Actor,
        *,
        employee_id: uuid.UUID,
        award_type: str,
        citation: str,
        amount: Decimal | None = None,
        period_id: uuid.UUID | None = None,
    ) -> RecognitionAward:
        """**Granted by a person, never by a score** (ADR 0011).

        The citation is mandatory and is what the employee is shown. An award with a number and no
        sentence is a payment; an award with a sentence is recognition, and the difference is the
        whole of what this module is for.
        """
        if not citation.strip():
            raise AppError(
                "recognition.citation_required",
                "Say what it is for. The words are what the person is actually given.",
                status_code=422,
            )
        award = RecognitionAward(
            restaurant_id=self.scope.restaurant_id,
            performance_period_id=period_id,
            employee_id=employee_id,
            type=award_type,
            amount=amount,
            citation=citation.strip(),
            granted_by=actor.employee_id,
            granted_at=datetime.now(UTC),
        )
        self.session.add(award)
        await self.session.flush()
        return award

    # ------------------------------------------------------------------ internals

    async def _require_period(self, period_id: uuid.UUID) -> PerformancePeriod:
        period = await self._repository.period(period_id)
        if period is None:
            raise NotFoundError("performance_period.not_found", "That period does not exist here.")
        return period

    async def _lines(self, period_id: uuid.UUID) -> list[Line]:
        """Frozen if published, live if draft — and the caller cannot tell, which is the point."""
        period = await self._require_period(period_id)
        if period.status == PerformancePeriodStatus.DRAFT.value:
            return await self.draft(period_id)
        return [
            Line(
                employee_id=row.employee_id,
                hours=Decimal(str(row.hours_worked)),
                metrics=_thawed(row.metrics),
                points=Decimal(str(row.points)),
                rank=row.rank_in_period,
            )
            for row in await self._repository.scores(period_id)
        ]

    async def _line_for(self, period_id: uuid.UUID, employee_id: uuid.UUID) -> Line | None:
        return next(
            (line for line in await self._lines(period_id) if line.employee_id == employee_id), None
        )

    async def _compute(self, since: date, until: date, weights: dict[str, Decimal]) -> list[Line]:
        worked = {
            row.employee_id: row for row in await self._repository.worked(since=since, until=until)
        }
        served = {
            row.employee_id: row for row in await self._repository.served(since=since, until=until)
        }
        quality = {
            row.employee_id: row for row in await self._repository.quality(since=since, until=until)
        }
        delay = await self._repository.kitchen_delay_minutes(since=since, until=until)

        lines = []
        for employee_id, work in worked.items():
            metrics = _metrics_for(work, served.get(employee_id), quality.get(employee_id), delay)
            lines.append(
                Line(
                    employee_id=employee_id,
                    hours=work.hours,
                    metrics=metrics,
                    points=points_for(metrics, weights),
                )
            )
        return lines


# --------------------------------------------------------------------------- helpers


def _checked(weights: dict[str, object]) -> dict[str, Decimal]:
    try:
        return validate_weights(weights)
    except SchemeError as error:
        raise AppError("incentive.weights_invalid", str(error), status_code=422) from error


def _share(part: Decimal, whole: Decimal) -> Decimal:
    if whole <= 0:
        return _ZERO
    return (part / whole).quantize(_RATE, ROUND_HALF_UP)


def _metrics_for(
    work: Worked, served: Served | None, quality: Quality | None, kitchen_delay: Decimal
) -> dict[str, Metric]:
    """Every figure as a **rate**, with the count it came from.

    A four-hour shift and an eight-hour shift are not comparable, so nothing here is a total. And
    every rate carries the number of things behind it, because that is what makes a wrong
    attribution visible as a wrong *count* rather than as an unexplained score.
    """
    covers = served.covers if served else 0
    orders = served.orders if served else 0
    assists = served.assists if served else 0
    lines = quality.lines if quality else 0
    cancelled = quality.cancelled_lines if quality else 0
    ratings = quality.ratings if quality else 0
    rating_total = quality.rating_total if quality else 0

    per_hour = _share(Decimal(covers), work.hours) if work.hours else _ZERO
    return {
        "volume": Metric(
            key="volume",
            value=min(per_hour * _COVERS_PER_HOUR_TARGET, Decimal(1)) if work.hours else _ZERO,
            kind=METRICS["volume"],
            count=covers,
        ),
        "accuracy": Metric(
            key="accuracy",
            value=(
                (Decimal(lines - cancelled) / Decimal(lines)).quantize(_RATE)
                if lines
                else Decimal(1)
            ),
            kind=METRICS["accuracy"],
            count=lines,
        ),
        "rating": Metric(
            key="rating",
            # No ratings is **not** a zero. Somebody nobody rated is not somebody rated badly, and
            # scoring them as though they were is how a quiet week becomes a bad review.
            value=(
                (Decimal(rating_total) / Decimal(ratings) / _MAX_RATING).quantize(_RATE)
                if ratings
                else _ZERO
            ),
            kind=METRICS["rating"],
            count=ratings,
        ),
        "attendance": Metric(
            key="attendance",
            # The denominator excludes approved leave. `docs/workload-fairness.md` §4: counting it
            # against somebody looks neutral and quietly disadvantages the people employment law
            # protects.
            value=_attendance(work),
            kind=METRICS["attendance"],
            count=work.shifts,
        ),
        "assists": Metric(
            key="assists",
            value=(Decimal(assists) / Decimal(orders)).quantize(_RATE) if orders else _ZERO,
            kind=METRICS["assists"],
            count=assists,
        ),
        "kitchen_delay": Metric(
            key="kitchen_delay",
            value=kitchen_delay,
            kind=METRICS["kitchen_delay"],
            count=0,
        ),
    }


def _attendance(work: Worked) -> Decimal:
    expected = work.rostered - work.excused
    if expected <= 0:
        # Somebody whose every rostered day was approved leave has a perfect record, not an empty
        # one. Scoring them zero would be the exact failure the exclusion list exists to prevent.
        return Decimal(1)
    return min(Decimal(work.shifts) / Decimal(expected), Decimal(1)).quantize(_RATE)


def _frozen(metrics: dict[str, Metric]) -> dict[str, object]:
    """What goes into `performance_score.metrics`, once, at publication."""
    return {
        key: {"value": str(metric.value), "kind": metric.kind.value, "count": metric.count}
        for key, metric in metrics.items()
    }


def _thawed(stored: dict[str, object]) -> dict[str, Metric]:
    thawed = {}
    for key, raw in stored.items():
        if not isinstance(raw, dict):  # pragma: no cover - written by `_frozen` only
            continue
        thawed[key] = Metric(
            key=key,
            value=Decimal(str(raw.get("value", "0"))),
            kind=PerformanceMetricKind(str(raw.get("kind", "context"))),
            count=int(raw.get("count", 0) or 0),
        )
    return thawed
