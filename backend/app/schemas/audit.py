"""The audit trail and the notification centre, on the wire.

**Every audit row crosses as a sentence plus its raw values.** A JSON blob on a screen is a log,
not a record — a manager asking "who changed this price" should read *"Priya changed Butter
Chicken's price from ₹480 to ₹520"*, with the values underneath for the case where the sentence is
not enough. The sentence is built on the server so the CSV, the screen and a future email say the
same words.

**A notification carries no customer data.** M14's threat note: the centre is the easiest place to
leak a name into a surface nobody thought of, so a complaint notification says its *reference* —
the number M10 gave it precisely so a person could quote it — and never who complained.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AuditEntryResponse(_Schema):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    actor_employee_id: uuid.UUID | None
    # The name, resolved once for the page rather than looked up per row by the screen.
    actor_name: str | None
    occurred_at: datetime
    # "Priya changed Butter Chicken's price from ₹480 to ₹520." Built on the server.
    sentence: str
    old_value: dict[str, object] | None
    new_value: dict[str, object] | None
    # A why, when the act had one — a waiter handover, an attendance correction.
    reason: str | None


class AuditPageResponse(_Schema):
    items: list[AuditEntryResponse]
    next_cursor: uuid.UUID | None


class NoticeResponse(_Schema):
    # The condition's stable identity. What a dismissal is remembered against.
    key: str
    kind: str
    # critical | warning | caution | info, from the locked scale in docs/ui/conventions.md.
    severity: str
    subject: str
    detail: str
    ref_type: str
    ref_id: uuid.UUID
    occurred_at: datetime | None
    read: bool
    dismissed: bool


class NoticeListResponse(_Schema):
    items: list[NoticeResponse]
    unread: int


class MarkNoticeRequest(_Schema):
    # The condition's own identity, as the centre sent it. Not a row id: a person's state is kept
    # against the condition, so dismissing this batch's warning leaves the next batch's alone.
    key: str
    # Read means "I have seen it"; dismissed means "do not show me this one again while it lasts".
    dismissed: bool = False
