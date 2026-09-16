"""Customers. Every handler is authorise-call-shape and nothing else.

Two permissions, and the P1 design's own line between them (`seed/organization.yaml`):

- `customer.view` — read a profile, a history, the list. **A waiter holds this**, because
  `docs/customer-experience.md` puts the regular's card on the waiter's screen: "7th visit, usually
  orders Butter Chicken + Butter Naan, no onion/garlic, last visit rated 5". Asking a regular for
  the fourth time whether they eat onion is a small insult; remembering is a small delight, and in
  this market that matters more than almost any feature we could build.
- `customer.manage` — create, edit, record a preference, capture or withdraw a consent, export,
  erase. Manager and owner.

**What `customer.view` does not grant is the whole organization.** The record belongs to the
business, so a chain recognises one diner across its branches; the *view* belongs to the branch, and
a person reads the customers of the restaurant they are working in. Handling a second branch is an
assignment — M01's own gesture — not a permission. Owner's decision, 2026-09-16.

**Erasure sits under `customer.manage`, beside editing a name, and arguably should not.** The P1
design has no finer code and the shipped catalogue must be a subset of it, so inventing one here
would be changing the design from inside a migration. It is in `docs/backlog.md` as a question for
the owner.

**The export is per customer and there is no bulk one, in any role.** A customer list is a
competitor's most valuable asset and the design hands `customer.view` to waiters on purpose, so the
control is the shape of the surface rather than the permission: the list is thin, the export is one
person at a time, and every export and erasure writes an `audit_log` row. None of that stops a
determined person with a phone camera; it makes the fast version not exist.

**Every write route commits; the service only flushes.** This codebase's convention, broken twice
already — every write returning 201 with a populated body and then vanishing. No unit test catches
it, because inside one transaction the write is visible to the code that made it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep, require_permission
from app.api.v1.staff.complaints import _complaint_response, _feedback_response
from app.core.actor import Actor
from app.core.permissions import PermissionCode
from app.core.tenancy import TenantScope
from app.models.customers import Customer, CustomerConsent
from app.repositories.customers import Visits
from app.schemas.customers import (
    AttachCustomerRequest,
    ConsentStateResponse,
    ConsentWriteRequest,
    CustomerCreateRequest,
    CustomerExportResponse,
    CustomerHistoryResponse,
    CustomerListItem,
    CustomerListResponse,
    CustomerPreferenceResponse,
    CustomerResponse,
    CustomerUpdateRequest,
    CustomerVisitLine,
    ErasureResponse,
    OrderCustomerResponse,
    PreferenceCreateRequest,
)
from app.services.customers import CustomerHistory, CustomerService

router = APIRouter()

# Somebody who has never settled a bill here. Counted as nothing rather than absent, so a brand-new
# customer's screen reads "First visit not recorded yet" instead of breaking.
_NO_VISITS = Visits(count=0, spent=Decimal("0.00"), first_at=None, last_at=None)

_ViewDep = Annotated[Actor, Depends(require_permission(PermissionCode.CUSTOMER_VIEW))]
_ManageDep = Annotated[Actor, Depends(require_permission(PermissionCode.CUSTOMER_MANAGE))]
_LimitDep = Annotated[int | None, Query(ge=1, le=200)]
_CursorDep = Annotated[uuid.UUID | None, Query()]


def _service(session: SessionDep, actor: Actor) -> CustomerService:
    return CustomerService(
        session,
        TenantScope(organization_id=actor.organization_id, restaurant_id=actor.restaurant_id),
    )


def _consent_state(rows: list[CustomerConsent]) -> list[ConsentStateResponse]:
    return [
        ConsentStateResponse(
            purpose=row.purpose,
            granted=row.granted,
            occurred_at=row.occurred_at,
            notice_version=row.notice_version,
            notice_language=row.notice_language,
            source=row.source,
        )
        for row in rows
    ]


def _history_response(history: CustomerHistory) -> CustomerHistoryResponse:
    return CustomerHistoryResponse(
        visits=[
            CustomerVisitLine(
                order_id=visit.order_id,
                business_date=visit.business_date,
                total=visit.total,
                items=visit.items,
            )
            for visit in history.visits
        ],
        feedback=[_feedback_response(row) for row in history.feedback],
        complaints=[_complaint_response(row, returned=None) for row in history.complaints],
    )


def _detail(
    customer: Customer, consents: list[CustomerConsent], visits: Visits | None
) -> CustomerResponse:
    """The profile.

    `visit_count` and `lifetime_value` come from `visits` — counted from the order ledger — and not
    from the columns of the same name, which nothing maintains. A number that cannot go stale is
    worth more than one that is cheaper to read.
    """
    return CustomerResponse(
        id=customer.id,
        phone=customer.phone,
        name=customer.name,
        email=customer.email,
        first_visit_at=None if visits is None else visits.first_at,
        last_visit_at=None if visits is None else visits.last_at,
        visit_count=0 if visits is None else visits.count,
        lifetime_value=Decimal("0.00") if visits is None else visits.spent,
        birthday=customer.birthday,
        anniversary=customer.anniversary,
        is_erased=customer.is_erased,
        is_active=customer.is_active,
        preferences=[
            CustomerPreferenceResponse(
                id=preference.id,
                type=preference.type,
                value=preference.value,
                is_critical=preference.is_critical,
            )
            for preference in customer.preferences
        ],
        consents=_consent_state(consents),
    )


# --------------------------------------------------------------------------- reading


@router.get("/customers", response_model=CustomerListResponse)
async def list_customers(
    actor: _ViewDep,
    session: SessionDep,
    search: Annotated[str | None, Query(max_length=40)] = None,
    limit: _LimitDep = None,
    cursor: _CursorDep = None,
) -> CustomerListResponse:
    """The customers of **this branch**, most recent visit first.

    Deliberately thinner than the profile: phone, name, visit count, last visit. Not birthdays, not
    preferences, not lifetime value. A screen showing every customer's birthday is a screen somebody
    photographs.
    """
    service = _service(session, actor)
    rows = await service.search(term=search, limit=limit, after=cursor)
    # One grouped query for the whole page, not one per row.
    counts = await service.relationship([row.id for row in rows])
    items = [
        CustomerListItem(
            id=row.id,
            phone=row.phone,
            name=row.name,
            visit_count=counts.get(row.id, _NO_VISITS).count,
            last_visit_at=counts.get(row.id, _NO_VISITS).last_at,
            is_erased=row.is_erased,
        )
        for row in rows
    ]
    next_cursor = items[-1].id if limit is not None and len(items) == limit else None
    return CustomerListResponse(items=items, next_cursor=next_cursor)


@router.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    actor: _ViewDep, session: SessionDep, customer_id: uuid.UUID
) -> CustomerResponse:
    service = _service(session, actor)
    customer = await service.get(customer_id)
    return _detail(
        customer,
        list(await service.consent_state(customer_id)),
        (await service.relationship([customer.id])).get(customer.id),
    )


@router.get("/customers/{customer_id}/history", response_model=CustomerHistoryResponse)
async def customer_history(
    actor: _ViewDep, session: SessionDep, customer_id: uuid.UUID
) -> CustomerHistoryResponse:
    """Every visit, rating and complaint — **at this branch**.

    The record is the organization's so the same person is recognised wherever they walk in; what
    each branch shows is its own.
    """
    history = await _service(session, actor).history(customer_id)
    return _history_response(history)


@router.get("/customers/{customer_id}/export", response_model=CustomerExportResponse)
async def export_customer(
    actor: _ManageDep, session: SessionDep, customer_id: uuid.UUID
) -> CustomerExportResponse:
    """The DPDP access right: everything this product holds about one person, in one response.

    **Per customer, and there is no bulk version in any role.** Audited, because reading out
    everything held about somebody is an event worth being able to ask about afterwards.
    """
    service = _service(session, actor)
    export = await service.export(customer_id)
    await session.commit()
    return CustomerExportResponse(
        exported_at=datetime.now(UTC),
        customer=_detail(
            export.customer,
            list(await service.consent_state(customer_id)),
            (await service.relationship([export.customer.id])).get(export.customer.id),
        ),
        consent_history=_consent_state(export.consents),
        history=_history_response(export.history),
    )


# --------------------------------------------------------------------------- writing


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    actor: _ManageDep, session: SessionDep, request: CustomerCreateRequest
) -> CustomerResponse:
    service = _service(session, actor)
    customer = await service.create(
        phone=request.phone,
        name=request.name,
        email=request.email,
        birthday=request.birthday,
        anniversary=request.anniversary,
    )
    await session.commit()
    # A customer created a moment ago has settled nothing, so there is no relationship yet.
    return _detail(await service.get(customer.id), [], None)


@router.patch("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    actor: _ManageDep,
    session: SessionDep,
    customer_id: uuid.UUID,
    request: CustomerUpdateRequest,
) -> CustomerResponse:
    service = _service(session, actor)
    await service.update(customer_id, **request.model_dump(exclude_unset=True))
    await session.commit()
    customer = await service.get(customer_id)
    return _detail(
        customer,
        list(await service.consent_state(customer_id)),
        (await service.relationship([customer.id])).get(customer.id),
    )


@router.post(
    "/customers/{customer_id}/preferences",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_preference(
    actor: _ManageDep,
    session: SessionDep,
    customer_id: uuid.UUID,
    request: PreferenceCreateRequest,
) -> CustomerResponse:
    service = _service(session, actor)
    await service.add_preference(
        customer_id, type=request.type, value=request.value, is_critical=request.is_critical
    )
    await session.commit()
    customer = await service.get(customer_id)
    return _detail(
        customer,
        list(await service.consent_state(customer_id)),
        (await service.relationship([customer.id])).get(customer.id),
    )


@router.delete(
    "/customers/{customer_id}/preferences/{preference_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_preference(
    actor: _ManageDep, session: SessionDep, customer_id: uuid.UUID, preference_id: uuid.UUID
) -> None:
    await _service(session, actor).remove_preference(customer_id, preference_id)
    await session.commit()


@router.post("/customers/{customer_id}/consent", response_model=ConsentStateResponse)
async def record_consent(
    actor: _ManageDep,
    session: SessionDep,
    customer_id: uuid.UUID,
    request: ConsentWriteRequest,
) -> ConsentStateResponse:
    """One purpose per call, and there is no way to express "all of them".

    `docs/compliance-rules.md` §B2's purpose limitation, in the shape of the API: a phone number
    collected for a bill is not marketing consent, so granting one grants nothing else.
    """
    service = _service(session, actor)
    consent = await service.record_consent(
        actor,
        customer_id,
        purpose=request.purpose,
        granted=request.granted,
        notice_version=request.notice_version,
        notice_language=request.notice_language,
        source="staff",  # type: ignore[arg-type]
    )
    await session.commit()
    return _consent_state([consent])[0]


@router.post("/customers/{customer_id}/erase", response_model=ErasureResponse)
async def erase_customer(
    actor: _ManageDep, session: SessionDep, customer_id: uuid.UUID
) -> ErasureResponse:
    """The DPDP erasure right. Irreversible, and the screen says so before it is pressed.

    Everything that names a person is destroyed; every order stays, because a bill is a financial
    record. The response carries what was retained as well as what was destroyed, so the screen can
    show both and nobody has to take the second half on trust.
    """
    result = await _service(session, actor).erase(actor, customer_id)
    await session.commit()
    return ErasureResponse(
        customer_id=result.customer_id,
        erased_at=result.erased_at,
        preferences_deleted=result.preferences_deleted,
        orders_retained=result.orders_retained,
        lifetime_value_retained=result.lifetime_value_retained,
    )


# --------------------------------------------------------------------------- the order attach
#
# The path lives under `/orders`, and the handler lives here, with the rest of M10. The routing
# table is what the suites walk, not the file layout, and keeping this module's code together is
# worth more than matching a URL prefix to a filename.


@router.post("/orders/{order_id}/customer", response_model=OrderCustomerResponse)
async def attach_customer(
    actor: _ManageDep,
    session: SessionDep,
    order_id: uuid.UUID,
    request: AttachCustomerRequest,
) -> OrderCustomerResponse:
    """Put a customer on an order, and freeze their allergies onto it.

    The note is a **copy**, taken now (`docs/modules/M10-customers-spec.md` decision 9). A live join
    would mean deleting a preference next week retroactively changes what the kitchen was told about
    a ticket it has already cooked; the kitchen's record of what it was warned about has to be the
    warning it actually received.

    Non-critical preferences are not copied and never reach the kitchen. A ticket carrying a
    regular's seating preference is noise, and noise on a ticket is how a real allergy gets skimmed
    past.
    """
    note = await _service(session, actor).attach_to_order(order_id, request.customer_id)
    await session.commit()
    return OrderCustomerResponse(
        order_id=order_id, customer_id=request.customer_id, allergy_note=note
    )
