"""Reading the trail: three filters, and a sentence per row.

**Every row renders as a sentence, with the raw values beneath it.** A JSON blob on a screen is a
log, not a record. The person opening this is a manager asking *who changed this price* or an
accountant asking *what happened on Tuesday*, and neither of them should have to read
`{"price": "480.00"}` to find out.

**The sentence is built here, not in the browser.** One phrasing, so the screen, an export and a
future email cannot disagree about what a row means — the same reason M13 builds its comparisons on
the server.

**Three filters and no free-text search** (M14 decision 7). Entity, actor and date range are the
three ways somebody actually arrives. A search over `old_value` would be a second copy of
everything in the product, sitting outside every retention story — the refusal M11 already made
about message search, and DPDP is not improved by making old values searchable.

**Nothing here writes.** Reading the trail leaves no trace in it: *who looked at what* is a
different product with a different retention story, and M14's spec puts it out of scope by name.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantScope
from app.models.audit import AuditLog
from app.repositories.audit import AuditLogRepository
from app.repositories.employee import EmployeeRepository


@dataclass(frozen=True, slots=True)
class Entry:
    row: AuditLog
    actor_name: str | None
    sentence: str

    @property
    def reason(self) -> str | None:
        metadata = self.row.audit_metadata or {}
        value = metadata.get("reason")
        return value if isinstance(value, str) else None


class AuditTrailService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._trail = AuditLogRepository(session, scope)
        self._employees = EmployeeRepository(session, scope)

    async def page(
        self,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        actor_employee_id: uuid.UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> list[Entry]:
        rows = await self._trail.page(
            entity_type=entity_type,
            entity_id=entity_id,
            actor_employee_id=actor_employee_id,
            since=since,
            until=until,
            limit=limit,
            after=after,
        )
        names = await self._names(rows)
        return [
            Entry(
                row=row,
                actor_name=names.get(row.actor_employee_id),
                sentence=_sentence(row, names),
            )
            for row in rows
        ]

    async def _names(self, rows: Sequence[AuditLog]) -> dict[uuid.UUID | None, str]:
        """One lookup for the page, not one per row.

        A trail of fifty rows is usually a handful of people, and the alternative is fifty queries
        on the screen somebody opens when they are already suspicious about something.
        """
        ids = {row.actor_employee_id for row in rows if row.actor_employee_id is not None}
        if not ids:
            return {}
        people = await self._employees.by_ids(list(ids))
        return {person.id: person.full_name for person in people}


# ------------------------------------------------------------------- the sentence

# What each action *did*, in words somebody reads rather than in the code's own vocabulary. An
# action with no entry here still renders — `_humanise` turns `purchase_order.sent` into "sent a
# purchase order" — so a new action is never a blank row. The table exists for the ones where the
# plain reading would be wrong or clumsy.
_PHRASES: dict[str, str] = {
    "employee.role.assign": "changed who {subject} is",
    "employee.password.reset": "reset {subject}'s password",
    "employee.deactivate": "deactivated {subject}",
    "employee.reactivate": "brought {subject} back",
    "menu_item_variant.repriced": "repriced {subject}",
    "modifier.repriced": "repriced the option {subject}",
    "order.cancel": "voided {subject}",
    "order_line.cancel": "removed a dish from {subject}",
    "order_line.updated": "changed a dish on {subject}",
    "order.discount": "discounted {subject}",
    "order.discount_removed": "took a discount off {subject}",
    "order.charge_added": "added a charge to {subject}",
    "order.charge_removed": "took a charge off {subject}",
    "order.settle": "settled {subject}",
    "order.split": "split {subject}",
    "order.waiter_assigned": "changed who is serving {subject}",
    "invoice.cancel": "cancelled {subject}",
    "invoice.credit_note": "issued a credit note against {subject}",
    "stock.adjusted": "adjusted stock",
    "stock.received": "recorded a delivery",
    "stock.produced": "made a batch",
    "stock.count_approved": "approved a stock count",
    "stock_item.repriced": "repriced {subject}",
    "recipe.version_created": "saved a new version of {subject}",
    "recipe.confirmed": "confirmed {subject}",
    "cash.open": "opened the till",
    "cash.close": "closed the till",
    "cash.payout": "paid money out of the till",
    "cash.adjust": "adjusted a closed till",
    "shift.corrected": "corrected somebody's attendance",
    "shift.status_set": "set somebody's shift status",
    "wastage.logged": "logged waste",
    "wastage.approved": "approved a waste log",
    "customer.erase": "erased a customer's details",
    "organization.bootstrap": "set this restaurant up",
}

# The word for a table, when a sentence has to name one.
_ENTITIES: dict[str, str] = {
    "menu_item_variant": "a dish",
    "modifier": "an option",
    "order": "an order",
    "order_line": "a line",
    "order_discount": "a discount",
    "invoice": "an invoice",
    "credit_note": "a credit note",
    "stock_item": "an ingredient",
    "stock_batch": "a batch",
    "stock_movement": "a stock movement",
    "stock_count": "a stock count",
    "recipe": "a recipe",
    "cash_session": "the till",
    "employee": "somebody",
    "shift_assignment": "a shift",
    "wastage_event": "a waste log",
    "wastage_reason": "a waste reason",
    "supplier": "a supplier",
    "purchase_order": "a purchase order",
    "goods_receipt": "a delivery",
    "restaurant": "the restaurant",
    "tax_group": "a tax rate",
    "customer": "a customer",
    "organization": "the organization",
}


def _sentence(row: AuditLog, names: dict[uuid.UUID | None, str]) -> str:
    """*"Priya repriced a dish — price 480.00 → 520.00."*

    Three parts, and each has a fallback so no row can render as nothing: who, what they did, and
    what moved. A row whose actor is unknown says "Somebody", which is true and is better than a
    blank — `audit_log.actor_employee_id` is nullable for the bootstrap command, which by
    definition happens before anybody has a login.
    """
    who = names.get(row.actor_employee_id) or "Somebody"
    subject = _ENTITIES.get(row.entity_type, row.entity_type.replace("_", " "))
    phrase = _PHRASES.get(row.action, _humanise(row.action)).format(subject=subject)
    changes = _changes(row)
    return f"{who} {phrase}{changes}."


def _humanise(action: str) -> str:
    """`purchase_order.sent` → "sent a purchase order". Never a blank row for a new action."""
    entity, _, verb = action.rpartition(".")
    noun = _ENTITIES.get(entity, entity.replace("_", " ").replace(".", " "))
    return f"{verb.replace('_', ' ')} {noun}".strip()


def _changes(row: AuditLog) -> str:
    """What moved, as ` — price 480.00 → 520.00`, or nothing at all.

    Only the fields present on both sides get an arrow; a create or a delete lists its one side.
    Capped at three fields, because a sentence that names eleven columns is not a sentence — the
    raw values are rendered underneath it for that.
    """
    old = row.old_value or {}
    new = row.new_value or {}
    fields = [key for key in (new or old) if key not in ("id", "restaurant_id")][:3]
    if not fields:
        return ""
    parts = []
    for field in fields:
        label = field.replace("_", " ")
        if field in old and field in new:
            parts.append(f"{label} {old[field]} → {new[field]}")
        elif field in new:
            parts.append(f"{label} {new[field]}")
        else:
            parts.append(f"{label} was {old[field]}")
    return " — " + ", ".join(parts)
