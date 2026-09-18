"""The compliance surface, and the one route here that writes on a GET.

**`GET /compliance/findings` evaluates and commits.** That is unusual enough to say plainly: every
other read in this product is a read. ADR 0005 leaves no background job, so opening the screen *is*
the evaluation, and a finding the product noticed but did not record would make the export a
screenshot of the present rather than a record of what was known when. The alternative — a POST
somebody has to remember to send — puts the record's completeness in the hands of whoever last
touched the frontend.

**Two permissions, and the split matters.** `compliance.view` reaches the manager, because the
manager runs the floor and the floor is where an expired licence is discovered by an inspector.
`compliance.act` does not: acknowledging and, especially, suppressing are decisions, and a
suppression is the row an inspection reads.

**The export lists every rule, including the ones that found nothing.** *"We checked these ten
things"* is a different claim from *"here are three problems"*, and it is the one an inspection is
actually interested in.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.deps import SessionDep, require_permission
from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.schemas.compliance import (
    ActRequest,
    CatalogueResponse,
    CitationResponse,
    FindingResponse,
    ReviewResponse,
    RuleResponse,
)
from app.services.compliance import Citation, ComplianceService, Item, catalogue

router = APIRouter(tags=["compliance"])

_VIEW = Annotated[Actor, Depends(require_permission(PermissionCode.COMPLIANCE_VIEW))]
_ACT = Annotated[Actor, Depends(require_permission(PermissionCode.COMPLIANCE_ACT))]

# Printed on the export, above everything else. The sentence exists because the alternative is a
# reader assuming `raised_at` is when the condition began — which it is not, and which an
# inspection is the wrong place to find out.
EXPORT_NOTE = (
    "Each finding is dated when this system first detected it, which may be later than when the "
    "condition began. Every rule cites the instrument it comes from and the date that citation was "
    "last checked. Rules marked other than 'in_force' are shown for information and are not "
    "current obligations."
)


def _service(session: SessionDep, actor: Actor) -> ComplianceService:
    return ComplianceService(session, actor.scope)


@router.get("/compliance/findings", response_model=ReviewResponse)
async def findings(session: SessionDep, actor: _VIEW) -> ReviewResponse:
    """Evaluate the catalogue, reconcile the record, and answer.

    Commits, because the reconciliation is a write. See the module docstring for why a read does
    that here and nowhere else in this product.
    """
    review = await _service(session, actor).review(now=datetime.now(UTC))
    await session.commit()
    return ReviewResponse(
        as_of=review.as_of,
        business_date=review.business_date,
        outstanding=review.outstanding,
        findings=tuple(_finding(item) for item in review.items),
    )


@router.get("/compliance/history", response_model=tuple[FindingResponse, ...])
async def history(
    session: SessionDep, actor: _VIEW, limit: Annotated[int | None, Query(ge=1, le=100)] = None
) -> tuple[FindingResponse, ...]:
    """Everything ever raised, resolved rows included. Reads only — no evaluation here, because
    the history is about what *was* known rather than about what is true now."""
    return tuple(_finding(item) for item in await _service(session, actor).history(limit=limit))


@router.get("/compliance/rules", response_model=CatalogueResponse)
async def rules(_actor: _VIEW) -> CatalogueResponse:
    """The whole catalogue with its citations. Takes no session: a rule is code, not a row."""
    return CatalogueResponse(
        rules=tuple(
            RuleResponse(
                code=code, title=title, severity=severity.value, citation=_citation(citation)
            )
            for code, title, citation, severity in catalogue()
        )
    )


@router.post("/compliance/findings/{finding_id}/acknowledge", response_model=FindingResponse)
async def acknowledge(session: SessionDep, actor: _ACT, finding_id: uuid.UUID) -> FindingResponse:
    """*"I have seen this."* It does not make the finding go away — only the condition can."""
    service = _service(session, actor)
    row = await service.acknowledge(
        finding_id, actor_employee_id=actor.employee_id, at=datetime.now(UTC)
    )
    await session.commit()
    return _finding(service.item(row))


@router.post("/compliance/findings/{finding_id}/suppress", response_model=FindingResponse)
async def suppress(
    session: SessionDep, actor: _ACT, finding_id: uuid.UUID, body: ActRequest
) -> FindingResponse:
    """*"I have decided not to act on this, and here is why."*

    The reason is mandatory at three levels — the schema allows it, the service refuses a blank
    one, and the database's CHECK refuses a null. Three, because this is the row an inspection
    reads and a dismissal with nothing attached is indistinguishable afterwards from a misclick.
    """
    service = _service(session, actor)
    row = await service.suppress(
        finding_id,
        actor_employee_id=actor.employee_id,
        reason=body.reason or "",
        at=datetime.now(UTC),
    )
    await session.commit()
    return _finding(service.item(row))


@router.get("/compliance/export")
async def export(session: SessionDep, actor: _VIEW) -> StreamingResponse:
    """What an owner hands an inspector.

    Evaluates first, so the export is current rather than a view of whatever was last opened, and
    lists the quiet rules after the findings so the document says what was *checked* and not only
    what was *found*.
    """
    service = _service(session, actor)
    review = await service.review(now=datetime.now(UTC))
    await session.commit()
    raised = {item.finding.rule_code for item in review.items}
    return _csv(review.items, raised)


# --------------------------------------------------------------------------- shaping


def _citation(citation: Citation) -> CitationResponse:
    return CitationResponse(
        instrument=citation.instrument,
        commencement=citation.commencement,
        checked_on=citation.checked_on,
        status=citation.status,
    )


def _finding(item: Item) -> FindingResponse:
    row = item.finding
    return FindingResponse(
        id=row.id,
        rule_code=row.rule_code,
        severity=row.severity,
        state=row.state,
        title=row.title,
        risk=row.risk,
        action=row.action,
        evidence=row.evidence,
        raised_at=row.raised_at,
        resolved_at=row.resolved_at,
        citation=None if item.citation is None else _citation(item.citation),
    )


_HEADER = (
    "rule",
    "status",
    "severity",
    "state",
    "finding",
    "risk",
    "action",
    "instrument",
    "commenced",
    "citation_checked_on",
    "first_detected",
    "resolved",
)


def _csv(items: tuple[Item, ...], raised: set[str]) -> StreamingResponse:
    """Streamed, and shaped so the document reads top to bottom: the note, what was found, then
    every rule that was checked and found nothing.

    `newline=""` on the buffer, because csv writes its own line terminator and a Windows Python
    would otherwise emit `\\r\\r\\n` — which Excel reads as a blank row between every line.
    """

    def lines() -> Iterator[str]:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(("note", EXPORT_NOTE))
        writer.writerow(())
        writer.writerow(_HEADER)
        yield _drain(buffer)
        for item in items:
            writer.writerow(_finding_row(item))
            yield _drain(buffer)
        writer.writerow(())
        writer.writerow(("rules checked and found nothing",))
        yield _drain(buffer)
        for code, title, citation, _severity in catalogue():
            if code in raised:
                continue
            writer.writerow(
                (
                    code,
                    citation.status,
                    "",
                    "clear",
                    title,
                    "",
                    "",
                    citation.instrument,
                    citation.commencement,
                    citation.checked_on,
                    "",
                    "",
                )
            )
            yield _drain(buffer)

    return StreamingResponse(
        lines(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="compliance.csv"'},
    )


def _finding_row(item: Item) -> tuple[object, ...]:
    row = item.finding
    citation = item.citation
    return (
        row.rule_code,
        "" if citation is None else citation.status,
        row.severity,
        row.state,
        row.title,
        row.risk,
        row.action,
        "" if citation is None else citation.instrument,
        "" if citation is None else citation.commencement,
        "" if citation is None else citation.checked_on,
        row.raised_at,
        row.resolved_at or "",
    )


def _drain(buffer: io.StringIO) -> str:
    written = buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    return written
