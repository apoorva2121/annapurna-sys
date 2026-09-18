"""The performance surface, and the one route every person in the restaurant can open.

**`GET /performance/me` is held by every role, always** (ADR 0011). Not by configuration, not by a
default somebody can change — by the catalogue, and `tests/test_m17_endpoints.py` asserts no role
is missing it. *"A score an employee cannot see is surveillance and lowers morale; the same score,
visible with its inputs shown, is feedback and raises it."*

**The distribution is behind `performance.view.team`** rather than the money permissions, because
it is about the roster rather than about pay. It is also the screen this module is really for: the
finding an owner needs is usually *the rota is unfair*, not *this person is bad*.

**No route here returns a bottom ranking.** That is a property of the response *schemas* — a team
line has no rank field at all — rather than of what each handler happens to sort. A screen can be
reimplemented; a schema that cannot express a ranking cannot be made to emit one.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import ActorDep, SessionDep, require_permission
from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.core.scoring import Metric
from app.schemas.performance import (
    AnswerRequest,
    AwardCreateRequest,
    AwardResponse,
    DistributionResponse,
    MetricResponse,
    MyScoreResponse,
    NoteCreateRequest,
    NoteResponse,
    PeriodCreateRequest,
    PeriodResponse,
    SchemeCreateRequest,
    SchemeResponse,
    ShareResponse,
    TeamLineResponse,
    TeamResponse,
)
from app.services.performance import Line, PerformanceService

router = APIRouter(tags=["performance"])

_TEAM = Annotated[Actor, Depends(require_permission(PermissionCode.PERFORMANCE_VIEW_TEAM))]
_PUBLISH = Annotated[Actor, Depends(require_permission(PermissionCode.PERFORMANCE_PUBLISH))]
_CONFIGURE = Annotated[Actor, Depends(require_permission(PermissionCode.INCENTIVE_CONFIGURE))]
_AWARD = Annotated[Actor, Depends(require_permission(PermissionCode.RECOGNITION_AWARD))]

# Said in the product rather than only in a document. `docs/workload-fairness.md`'s ethics review,
# question 2: nothing here consumes a score to punish, and the sentence a person is shown has to
# stay true.
PURPOSE = "These figures are used for rewards and for fairer rosters. Nothing else reads them."

_DEFAULT_WINDOW_DAYS = 28


def _service(session: SessionDep, actor: Actor) -> PerformanceService:
    return PerformanceService(session, actor.scope)


# --------------------------------------------------------------------------- my own


@router.get("/performance/me", response_model=MyScoreResponse | None)
async def my_performance(
    session: SessionDep, actor: ActorDep, period_id: Annotated[uuid.UUID, Query()]
) -> MyScoreResponse | None:
    """A person's own figures, with everything they are computed from.

    No permission dependency, because `performance.view.own` is held by every role and checking it
    here would imply it could be absent. What the route enforces is the thing that actually
    matters: it answers about **the caller**, and takes no employee id at all.
    """
    service = _service(session, actor)
    line = await service.mine(actor, period_id)
    if line is None:
        return None
    everyone = await service.team(period_id, actor.employee_id)
    return _mine(line, period_id, of=max(len(everyone), 1))


@router.get("/performance/team", response_model=TeamResponse)
async def team_performance(
    session: SessionDep, actor: _TEAM, period_id: Annotated[uuid.UUID, Query()]
) -> TeamResponse:
    """The top of the team and the viewer's own row. Below five scored people, the viewer alone."""
    lines = await _service(session, actor).team(period_id, actor.employee_id)
    return TeamResponse(
        period_id=period_id,
        shows_others=any(line.employee_id != actor.employee_id for line in lines),
        lines=[
            TeamLineResponse(
                employee_id=line.employee_id, points=str(line.points), hours=str(line.hours)
            )
            for line in lines
        ],
    )


@router.get("/performance/distribution", response_model=DistributionResponse)
async def distribution(
    session: SessionDep,
    actor: _TEAM,
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
) -> DistributionResponse:
    """**The primary screen.** Who handled what share of the work, against their share of the hours.

    Not a score and not a ranking: a person carrying 30% of the covers on 20% of the hours is a
    fact about the rota, and the fix is usually the rota.
    """
    finish = until or date.today()  # noqa: DTZ011 - a window, not a business date
    start = since or finish - timedelta(days=_DEFAULT_WINDOW_DAYS)
    shares = await _service(session, actor).distribution(since=start, until=finish)
    return DistributionResponse(
        since=start,
        until=finish,
        lines=[
            ShareResponse(
                employee_id=share.employee_id,
                hours=str(share.hours),
                covers=share.covers,
                orders=share.orders,
                assists=share.assists,
                covers_share=str(share.covers_share),
                hours_share=str(share.hours_share),
                carrying_more_than_their_hours=share.carrying_more_than_their_hours,
            )
            for share in shares
        ],
    )


# --------------------------------------------------------------------------- the scheme


@router.post("/performance/schemes", response_model=SchemeResponse, status_code=201)
async def create_scheme(
    payload: SchemeCreateRequest, session: SessionDep, actor: _CONFIGURE
) -> SchemeResponse:
    """The owner's alone: it decides what the restaurant pays people to do."""
    scheme = await _service(session, actor).create_scheme(
        actor,
        name=payload.name,
        period_type=payload.period_type,
        weights=dict(payload.weights),
        effective_from=payload.effective_from,
    )
    await session.commit()
    return SchemeResponse.model_validate(scheme)


@router.post("/performance/periods", response_model=PeriodResponse, status_code=201)
async def open_period(
    payload: PeriodCreateRequest, session: SessionDep, actor: _PUBLISH
) -> PeriodResponse:
    service = _service(session, actor)
    period = await service.open_period(
        actor,
        scheme_id=payload.incentive_scheme_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
    )
    await session.commit()
    return await _period(service, period.id)


@router.post("/performance/periods/{period_id}/publish", response_model=PeriodResponse)
async def publish_period(
    period_id: uuid.UUID, session: SessionDep, actor: _PUBLISH
) -> PeriodResponse:
    """**The freeze.** Refused while somebody's challenge to these figures is unanswered."""
    service = _service(session, actor)
    await service.publish(actor, period_id)
    await session.commit()
    return await _period(service, period_id)


# --------------------------------------------------------------------------- notes


@router.post("/performance/periods/{period_id}/notes", response_model=NoteResponse, status_code=201)
async def add_note(
    period_id: uuid.UUID, payload: NoteCreateRequest, session: SessionDep, actor: ActorDep
) -> NoteResponse:
    """Context from a manager, or a challenge from the person being measured.

    No permission dependency: raising a dispute about your own figures is part of being measured,
    and gating it behind something a role might not hold would be the thing the ethics review
    refused. The service enforces the rule that matters — a dispute is raised by the person whose
    figures they are.
    """
    note = await _service(session, actor).add_note(
        actor,
        period_id=period_id,
        employee_id=payload.employee_id,
        note=payload.note,
        kind=payload.kind,
        visible_to_employee=payload.visible_to_employee,
    )
    await session.commit()
    return NoteResponse.model_validate(note)


@router.post("/performance/notes/{note_id}/answer", response_model=NoteResponse)
async def answer_dispute(
    note_id: uuid.UUID, payload: AnswerRequest, session: SessionDep, actor: _TEAM
) -> NoteResponse:
    """Accept it, or decline it with a reason. In writing, by a named person."""
    note = await _service(session, actor).answer_dispute(actor, note_id, answer=payload.answer)
    await session.commit()
    return NoteResponse.model_validate(note)


# --------------------------------------------------------------------------- awards


@router.post("/recognition/awards", response_model=AwardResponse, status_code=201)
async def grant_award(
    payload: AwardCreateRequest, session: SessionDep, actor: _AWARD
) -> AwardResponse:
    """Granted by a person, never by a score (ADR 0011). Data informs it; it never makes it."""
    award = await _service(session, actor).grant_award(
        actor,
        employee_id=payload.employee_id,
        award_type=payload.type,
        citation=payload.citation,
        amount=payload.amount,
        period_id=payload.performance_period_id,
    )
    await session.commit()
    return AwardResponse(
        id=award.id,
        employee_id=award.employee_id,
        type=award.type,
        amount=None if award.amount is None else str(award.amount),
        citation=award.citation,
        granted_by=award.granted_by,
        granted_at=award.granted_at,
    )


# --------------------------------------------------------------------------- shaping


def _mine(line: Line, period_id: uuid.UUID, *, of: int) -> MyScoreResponse:
    return MyScoreResponse(
        period_id=period_id,
        employee_id=line.employee_id,
        hours=str(line.hours),
        points=str(line.points),
        rank=line.rank,
        of=of,
        metrics=[_metric(metric) for metric in line.metrics.values()],
        purpose=PURPOSE,
    )


# The sentence each metric is said in. `docs/workload-fairness.md`'s ethics review, question 6:
# visible is not the same as understandable, and a points breakdown is not an explanation.
_SENTENCES: dict[str, str] = {
    "volume": "You served {count} covers.",
    "accuracy": "{count} dishes went out; the ones sent back are counted against this.",
    "rating": "{count} people rated their visit.",
    "attendance": "You worked {count} of the shifts you were rostered for.",
    "assists": "{count} of your tables were somebody else's section.",
    "kitchen_delay": "The kitchen ran this far past its own targets. Not yours to fix.",
}


def _metric(metric: Metric) -> MetricResponse:
    return MetricResponse(
        key=metric.key,
        value=str(metric.value),
        kind=metric.kind.value,
        count=metric.count,
        weighted=metric.weighted,
        sentence=_SENTENCES.get(metric.key, "{count} counted.").format(count=metric.count),
    )


async def _period(service: PerformanceService, period_id: uuid.UUID) -> PeriodResponse:
    period = await service._require_period(period_id)
    unanswered = await service._repository.unanswered_disputes(period_id)
    return PeriodResponse(
        id=period.id,
        incentive_scheme_id=period.incentive_scheme_id,
        period_start=period.period_start,
        period_end=period.period_end,
        status=period.status,
        published_at=period.published_at,
        unanswered_disputes=unanswered,
    )
