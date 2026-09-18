"""The audit trail and the notification centre.

**`audit.view` is the owner's, the admin's and the accountant's — not the manager's**, and that is
the P1 design's line rather than this module's. The person who runs the floor is frequently the
subject of the record, and a record its subject curates is not a record. The same design withholds
`report.financial.view` from a manager for a related reason, and M13 acted on it.

**The notification centre needs no permission of its own.** Every role holds it, because what it
*shows* is already decided by what each person can act on (`services/notifications.py`): a waiter
sees their own overdue tasks and nothing else, not because a check here refuses them the rest but
because a food-cost condition is not theirs to act on. A permission here would be a second, weaker
copy of that rule.

**Nothing in this file writes to `audit_log`.** Reading the trail leaves no trace in it — who
looked at what is a different product with a different retention story, and M14's spec puts it out
of scope by name.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import ActorDep, SessionDep, require_permission
from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.schemas.audit import (
    AuditEntryResponse,
    AuditPageResponse,
    MarkNoticeRequest,
    NoticeListResponse,
    NoticeResponse,
)
from app.services.audit_trail import AuditTrailService
from app.services.notifications import NotificationService

router = APIRouter(tags=["audit"])

_AUDIT = Annotated[Actor, Depends(require_permission(PermissionCode.AUDIT_VIEW))]


@router.get("/audit", response_model=AuditPageResponse)
async def audit_trail(
    session: SessionDep,
    actor: _AUDIT,
    entity_type: Annotated[str | None, Query()] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    actor_employee_id: Annotated[uuid.UUID | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    after: Annotated[uuid.UUID | None, Query()] = None,
) -> AuditPageResponse:
    """What happened, newest first. Three filters and a cursor.

    Keyset-paged on the id rather than offset, so a trail with a million rows costs what a trail
    with fifty costs — and so a row written while somebody is reading page two does not shift
    page three underneath them.
    """
    entries = await AuditTrailService(session, actor.scope).page(
        entity_type=entity_type,
        entity_id=entity_id,
        actor_employee_id=actor_employee_id,
        since=since,
        until=until,
        limit=limit,
        after=after,
    )
    return AuditPageResponse(
        items=[
            AuditEntryResponse(
                id=entry.row.id,
                action=entry.row.action,
                entity_type=entry.row.entity_type,
                entity_id=entry.row.entity_id,
                actor_employee_id=entry.row.actor_employee_id,
                actor_name=entry.actor_name,
                occurred_at=entry.row.occurred_at,
                sentence=entry.sentence,
                old_value=entry.row.old_value,
                new_value=entry.row.new_value,
                reason=entry.reason,
            )
            for entry in entries
        ],
        next_cursor=entries[-1].row.id if len(entries) == (limit or 50) else None,
    )


@router.get("/notifications", response_model=NoticeListResponse)
async def notifications(
    session: SessionDep,
    actor: ActorDep,
    include_dismissed: Annotated[bool, Query()] = False,
) -> NoticeListResponse:
    """Everything true right now that this person can act on.

    **Derived, never stored** (M14 decision 4). There is no background job in this product, and a
    notification table filled by a job that is not running is a centre that is silently empty —
    which looks exactly like nothing being wrong.
    """
    notices = await NotificationService(session, actor.scope).centre(
        actor, include_dismissed=include_dismissed
    )
    return NoticeListResponse(
        items=[
            NoticeResponse(
                key=notice.key,
                kind=notice.kind,
                severity=notice.severity,
                subject=notice.subject,
                detail=notice.detail,
                ref_type=notice.ref_type,
                ref_id=notice.ref_id,
                occurred_at=notice.occurred_at,
                read=notice.read,
                dismissed=notice.dismissed,
            )
            for notice in notices
        ],
        unread=sum(1 for notice in notices if not notice.read),
    )


@router.post("/notifications/read", status_code=204)
async def mark_notification(
    payload: MarkNoticeRequest,
    session: SessionDep,
    actor: ActorDep,
) -> None:
    """Read it, or put it away.

    **The key is in the body and not in the path**, which is the honest shape: it is a condition's
    identity — `stock.negative:<uuid>` — and not a resource id, so there is nothing here for
    somebody to address that belongs to anybody. The row written is always the actor's own state
    against a string, in the actor's own restaurant; there is no cross-tenant read to be had, and a
    path parameter would have implied one.
    """
    await NotificationService(session, actor.scope).mark(
        actor, payload.key, dismissed=payload.dismissed
    )
    await session.commit()
