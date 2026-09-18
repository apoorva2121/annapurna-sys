"""Gathering the facts a rule is evaluated against, and storing what it found.

**One query per fact, not one query per rule.** Ten rules over one restaurant would be ten round
trips for figures most of them share, and the shared figures would be free to disagree — two rules
disagreeing about how many menu items are live is the kind of defect nobody finds until an
inspection. `facts()` builds one `Facts` and the whole catalogue reads it.

**`annual_turnover` is the trailing 365 days of issued invoices, and is `None` when nothing has
been issued.** The distinction matters: a restaurant with no turnover *recorded* is not a
restaurant under the registration ceiling, and the tier rule must be able to say "I cannot tell"
rather than "you are fine". Cancelled invoices are excluded — they keep their number for GSTR-1
Table 13, but they are not turnover.

**`consent_rows` counts the organization, not the restaurant.** Consent is given to the company;
`customer_consent` is organization-scoped, and scoping it to a branch would report a gap the data
does not show.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.compliance import Facts
from app.core.tenancy import TenantScope
from app.models.compliance import ComplianceEvent, ComplianceFinding
from app.models.customers import Customer, CustomerConsent
from app.models.menu import MenuItem
from app.models.orders import Invoice
from app.models.setup import TaxGroup, TaxRate
from app.models.tenancy import Restaurant
from app.repositories.base import RestaurantScopedRepository, page_size

TURNOVER_WINDOW_DAYS = 365


def _rate(value: object | None) -> Decimal:
    return Decimal(0) if value is None else Decimal(str(value))


class ComplianceFactsRepository:
    """Reads. Writes nothing, and holds no rules — a rule's words live in `app/core/compliance.py`.

    Not a `RestaurantScopedRepository` because it reads six tables rather than one, but every query
    it issues carries the scope explicitly, which is what invariant 1 actually asks for.
    """

    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope

    async def facts(self, *, today: date) -> Facts:
        restaurant = await self.session.get(Restaurant, self.scope.restaurant_id)
        if restaurant is None or restaurant.organization_id != self.scope.organization_id:
            # Reached only if a scope is built for a restaurant of another organization, which the
            # auth layer prevents. Raised rather than returning empty facts, because empty facts
            # read as "nothing is wrong".
            raise LookupError("restaurant not in scope")

        return Facts(
            today=today,
            fssai_licence=restaurant.fssai_licence,
            fssai_expires_on=restaurant.fssai_licence_expires_on,
            gstin=restaurant.gstin,
            gst_scheme=restaurant.gst_scheme,
            annual_turnover=await self._turnover(today),
            invoices_issued=await self._invoices_issued(),
            # Null means none is levied, which for this rule is exactly zero. The column is
            # nullable because M02 distinguishes "not configured" from "configured at nil";
            # the CCPA rule asks only whether one is added, and both answers are no.
            service_charge_rate=_rate(restaurant.service_charge_rate),
            live_menu_items=await self._menu_items(),
            items_without_allergens=await self._menu_items(missing="allergens"),
            items_without_calories=await self._menu_items(missing="calories"),
            outlets=await self._outlets(),
            tax_groups_without_a_current_rate=await self._tax_groups_without_a_rate(today),
            customers_without_consent=await self._customers_without_consent(),
        )

    async def _turnover(self, today: date) -> Decimal | None:
        since = today - timedelta(days=TURNOVER_WINDOW_DAYS)
        total = await self.session.scalar(
            select(func.sum(Invoice.grand_total)).where(
                Invoice.restaurant_id == self.scope.restaurant_id,
                Invoice.status == "issued",
                Invoice.business_date >= since,
            )
        )
        # None rather than zero: "nothing recorded" is not "under the ceiling".
        return None if total is None else Decimal(str(total))

    async def _invoices_issued(self) -> int:
        return await self._count(
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.restaurant_id == self.scope.restaurant_id, Invoice.status == "issued")
        )

    async def _menu_items(self, *, missing: str | None = None) -> int:
        query = (
            select(func.count())
            .select_from(MenuItem)
            .where(MenuItem.restaurant_id == self.scope.restaurant_id, MenuItem.is_active.is_(True))
        )
        if missing == "allergens":
            # An empty string counts as absent. A blank statement is not a declaration, and a rule
            # that accepted one would be satisfiable by typing a space.
            query = query.where(
                or_(
                    MenuItem.allergen_statement.is_(None),
                    func.btrim(MenuItem.allergen_statement) == "",
                )
            )
        elif missing == "calories":
            query = query.where(MenuItem.calories_kcal.is_(None))
        return await self._count(query)

    async def _outlets(self) -> int:
        """Active restaurants in the organization — the number the calorie rule turns on."""
        return await self._count(
            select(func.count())
            .select_from(Restaurant)
            .where(
                Restaurant.organization_id == self.scope.organization_id,
                Restaurant.is_active.is_(True),
            )
        )

    async def _tax_groups_without_a_rate(self, today: date) -> int:
        current = (
            select(TaxRate.tax_group_id)
            .where(
                TaxRate.restaurant_id == self.scope.restaurant_id,
                TaxRate.effective_from <= today,
                or_(TaxRate.effective_to.is_(None), TaxRate.effective_to >= today),
            )
            .subquery()
        )
        return await self._count(
            select(func.count())
            .select_from(TaxGroup)
            .outerjoin(current, current.c.tax_group_id == TaxGroup.id)
            .where(
                TaxGroup.restaurant_id == self.scope.restaurant_id,
                TaxGroup.is_active.is_(True),
                current.c.tax_group_id.is_(None),
            )
        )

    async def _customers_without_consent(self) -> int:
        consented = (
            select(CustomerConsent.customer_id)
            .where(CustomerConsent.organization_id == self.scope.organization_id)
            .subquery()
        )
        return await self._count(
            select(func.count())
            .select_from(Customer)
            .outerjoin(consented, consented.c.customer_id == Customer.id)
            .where(
                Customer.organization_id == self.scope.organization_id,
                Customer.is_active.is_(True),
                # An erased customer is one whose data has already been dealt with.
                Customer.erased_at.is_(None),
                consented.c.customer_id.is_(None),
            )
        )

    async def _count(self, query: Select[Any]) -> int:
        return await self.session.scalar(query) or 0


# Worst first. Written as a CASE rather than an ORDER BY on the column, because alphabetically
# `advisory` sorts before `critical`, which is exactly backwards for the two that matter.
_SEVERITY_ORDER = case(
    (ComplianceFinding.severity == "critical", 0),
    (ComplianceFinding.severity == "warning", 1),
    else_=2,
)


class ComplianceFindingRepository(RestaurantScopedRepository[ComplianceFinding]):
    """The findings, and the append-only events that happened to them."""

    model = ComplianceFinding

    async def live(self) -> Sequence[ComplianceFinding]:
        """Everything not resolved, worst first, then oldest first."""
        result = await self.session.scalars(
            self.scoped()
            .where(ComplianceFinding.state != "resolved")
            .order_by(_SEVERITY_ORDER, ComplianceFinding.raised_at)
        )
        return result.all()

    async def by_code(self, code: str) -> ComplianceFinding | None:
        """The live finding for a rule, if there is one. The partial unique index makes it at most
        one, so `first()` here is a fact about the schema rather than a hope."""
        result = await self.session.scalars(
            self.scoped().where(
                ComplianceFinding.rule_code == code, ComplianceFinding.state != "resolved"
            )
        )
        return result.first()

    async def history(self, *, limit: int | None = None) -> Sequence[ComplianceFinding]:
        """Everything ever raised, newest first. What the export is built from."""
        result = await self.session.scalars(
            self.scoped().order_by(ComplianceFinding.raised_at.desc()).limit(page_size(limit))
        )
        return result.all()

    async def events(self, finding_ids: Sequence[uuid.UUID]) -> Sequence[ComplianceEvent]:
        if not finding_ids:
            return []
        result = await self.session.scalars(
            select(ComplianceEvent)
            .where(
                ComplianceEvent.restaurant_id == self.scope.restaurant_id,
                ComplianceEvent.compliance_finding_id.in_(finding_ids),
            )
            .order_by(ComplianceEvent.occurred_at)
        )
        return result.all()

    def add_event(
        self,
        finding: ComplianceFinding,
        *,
        kind: str,
        at: datetime,
        actor_employee_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> ComplianceEvent:
        """Append-only. Nothing in this module updates or deletes one of these."""
        event = ComplianceEvent(
            restaurant_id=self.scope.restaurant_id,
            compliance_finding_id=finding.id,
            type=kind,
            actor_employee_id=actor_employee_id,
            reason=reason,
            occurred_at=at,
        )
        self.session.add(event)
        return event
