"""Queries over customers, consent, feedback and complaints. Business rules live in the services.

Two things here carry weight.

**`CustomerRepository` is organization-scoped, and reads are branch-filtered on top of that.**
Those are two different questions and the owner answered them separately (spec decision 5): the
*record* belongs to the organization, so a chain recognises one diner across its branches; the
*view* belongs to the branch, so a manager reads their own book. `_at_this_branch()` is the second
half, and it is applied to every read that returns more than one customer.

A `TenantScope` already carries both ids, so the filter costs nothing extra — and switching branches
is M01's existing gesture, which is what "let this manager handle Baner as well" already means
everywhere else in this product. No permission was invented for it.

`OrgScopedRepository` and `RestaurantScopedRepository` are separate classes on purpose — "silently
applying whichever scope happened to be set" is the bug CLAUDE.md invariant 1 calls the #1 bug class
in this product. Feedback and complaints happen at a restaurant and are the restaurant's.

**`latest_per_purpose` is the only way anything reads consent.** `customer_consent` is append-only,
so "is marketing granted?" is not a column lookup — it is the newest row for that purpose. One
query with `DISTINCT ON`, so a screen showing four purposes does not make four round trips and,
more importantly, so nothing anywhere is tempted to keep a cached boolean beside the ledger.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, delete, exists, func, select
from sqlalchemy.orm import selectinload

from app.models.customers import (
    Complaint,
    Customer,
    CustomerConsent,
    CustomerPreference,
    Feedback,
)
from app.models.orders import Order
from app.repositories.base import (
    OrgScopedRepository,
    RestaurantScopedRepository,
    page_size,
)


class CustomerRepository(OrgScopedRepository[Customer]):
    model = Customer

    async def get_with_preferences(self, customer_id: uuid.UUID) -> Customer | None:
        result = await self.session.scalars(
            self.scoped()
            .where(Customer.id == customer_id)
            .options(selectinload(Customer.preferences))
        )
        return result.first()

    async def by_phone(self, phone: str) -> Customer | None:
        """The natural key. `phone` arrives normalised — `app/core/phone.py` is the only thing that
        decides whether two numbers are the same person, and this compares what it produced."""
        result = await self.session.scalars(self.scoped().where(Customer.phone == phone))
        return result.first()

    def _at_this_branch(self) -> ColumnElement[bool]:
        """Customers of the restaurant this actor is working in.

        Either they have eaten here, or here is where they were first written down. The second half
        matters on day one of a chain's second branch: a customer created at the counter has no
        orders yet and would otherwise be invisible to the person who just created them.

        **This is a view rule inside one organization, not the tenant boundary.** The boundary is
        `scoped()` above it, and no combination of arguments to this function can cross it.
        """
        eaten_here = exists(
            select(Order.id).where(
                Order.customer_id == Customer.id,
                Order.restaurant_id == self.scope.restaurant_id,
            )
        )
        return eaten_here | (Customer.home_restaurant_id == self.scope.restaurant_id)

    async def search(
        self, *, term: str | None = None, limit: int | None = None, after: uuid.UUID | None = None
    ) -> Sequence[Customer]:
        """The customers of this branch, most recent visit first: the person a manager is looking
        for is nearly always somebody who was here lately."""
        query = self.scoped().where(self._at_this_branch())
        if term:
            pattern = f"%{term}%"
            query = query.where(Customer.phone.ilike(pattern) | Customer.name.ilike(pattern))
        if after is not None:
            query = query.where(Customer.id > after)
        return (
            await self.session.scalars(
                query.order_by(Customer.last_visit_at.desc().nullslast(), Customer.id).limit(
                    page_size(limit)
                )
            )
        ).all()

    async def order_count(self, customer_id: uuid.UUID) -> int:
        """What erasure must not change. Counted before and asserted after."""
        return (
            await self.session.scalar(
                select(func.count(Order.id)).where(Order.customer_id == customer_id)
            )
        ) or 0

    async def critical_preferences(self, customer_id: uuid.UUID) -> Sequence[str]:
        """The allergies, and only the allergies. What the kitchen is told (spec decision 9)."""
        return (
            await self.session.scalars(
                select(CustomerPreference.value)
                .where(
                    CustomerPreference.customer_id == customer_id,
                    CustomerPreference.organization_id == self.scope.organization_id,
                    CustomerPreference.is_critical.is_(True),
                )
                .order_by(CustomerPreference.value)
            )
        ).all()


class CustomerPreferenceRepository(OrgScopedRepository[CustomerPreference]):
    model = CustomerPreference

    async def delete_all(self, customer_id: uuid.UUID) -> int:
        """Erasure. A real DELETE, not a flag: a preference is a statement about a person's body and
        their beliefs, and `docs/decisions/0008` reserves soft deletion for rows something else
        points at. Nothing points at these."""
        result = await self.session.execute(
            delete(CustomerPreference).where(
                CustomerPreference.customer_id == customer_id,
                CustomerPreference.organization_id == self.scope.organization_id,
            )
        )
        # `execute` is typed as returning `Result`, and a DELETE always returns a `CursorResult`.
        # The cast is narrowing a library's conservative annotation, not asserting something the
        # database does not guarantee.
        return cast("CursorResult[Any]", result).rowcount or 0


class ConsentRepository(OrgScopedRepository[CustomerConsent]):
    model = CustomerConsent

    async def latest_per_purpose(self, customer_id: uuid.UUID) -> Sequence[CustomerConsent]:
        """The standing answer for each purpose. A purpose never asked is absent, not false."""
        query = (
            self.scoped()
            .where(CustomerConsent.customer_id == customer_id)
            .order_by(CustomerConsent.purpose, CustomerConsent.occurred_at.desc())
            .distinct(CustomerConsent.purpose)
        )
        return (await self.session.scalars(query)).all()

    async def history(self, customer_id: uuid.UUID) -> Sequence[CustomerConsent]:
        """Every row, newest first.

        The DPDP access right, and the evidence an erasure was lawful.
        """
        return (
            await self.session.scalars(
                self.scoped()
                .where(CustomerConsent.customer_id == customer_id)
                .order_by(CustomerConsent.occurred_at.desc())
            )
        ).all()


class FeedbackRepository(RestaurantScopedRepository[Feedback]):
    model = Feedback

    async def for_order(self, order_id: uuid.UUID) -> Feedback | None:
        """ "Never ask twice in one visit." A second submission returns this rather than erroring —
        the guest tapped twice on a slow network, and an error screen for that is a rudeness."""
        result = await self.session.scalars(
            self.scoped().where(Feedback.order_id == order_id).options(selectinload(Feedback.lines))
        )
        return result.first()

    async def list_day(
        self, *, business_date: date, waiter_employee_id: uuid.UUID | None = None
    ) -> Sequence[Feedback]:
        query = self.scoped().where(Feedback.business_date == business_date)
        if waiter_employee_id is not None:
            query = query.where(Feedback.waiter_employee_id == waiter_employee_id)
        return (
            await self.session.scalars(
                query.order_by(Feedback.submitted_at.desc()).options(selectinload(Feedback.lines))
            )
        ).all()


class ComplaintRepository(RestaurantScopedRepository[Complaint]):
    model = Complaint

    async def list_open(self) -> Sequence[Complaint]:
        return (
            await self.session.scalars(
                self.scoped()
                .where(Complaint.status.in_(("open", "investigating")))
                .order_by(Complaint.severity, Complaint.created_at)
            )
        ).all()

    async def returned_after(self, customer_id: uuid.UUID, resolved_at: object) -> bool:
        """The only honest measure of recovery, derived rather than stored (spec decision 8).

        Did this person order again after we said the complaint was settled? One query, always
        current, and impossible to flatter.
        """
        found = await self.session.scalar(
            select(Order.id)
            .where(
                Order.restaurant_id == self.scope.restaurant_id,
                Order.customer_id == customer_id,
                # `placed_at`, not `created_at`: when the customer actually ordered, which is the
                # event the question is about.
                Order.placed_at > resolved_at,
            )
            .limit(1)
        )
        return found is not None
