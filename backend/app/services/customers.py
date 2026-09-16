"""The rules for customers, consent and the two DPDP rights. `docs/modules/M10-customers-spec.md`.

Four rules, and they are why this file exists rather than routes calling repositories.

**1 · Consent is written, never updated.** Every grant and every withdrawal is a new row in
`customer_consent`, and the current state of a purpose is the latest row for it. Nothing in this
service updates a consent row, and nothing deletes one — including erasure, which keeps the ledger
and destroys the person. `docs/compliance-rules.md` §B2 wants proof, and a record that can be
rewritten is not proof.

**2 · Erasure anonymises and keeps the money.** `docs/security.md`: "Erasure anonymises the customer
row and keeps the order (financial records must be retained); it does not cascade-delete revenue
history." So the row survives with a placeholder phone, the preferences go, the consent ledger stays
with nobody's name on it, and not one rupee moves. The service returns what it retained as well as
what it destroyed, so the screen can show both and the test can assert the second half.

**3 · A phone number is normalised once, on the way in.** The same person typed as `98765 43210`,
`+91 98765 43210` and `09876543210` is one customer or three, and which one it is must not depend on
who was standing at the counter. `app/core/phone.py` decides; nothing else compares a raw string.

**4 · Critical preferences are copied onto the order, not joined to it.** Attaching a customer
freezes their allergies onto the order at that moment. A preference deleted next week must not
change what the kitchen was warned about on a ticket it has already cooked — the same reasoning as
M05's frozen batch costs and ADR 0011's frozen published metrics.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.enums import ConsentPurpose, ContactSource, PreferenceType
from app.core.errors import ConflictError, NotFoundError
from app.core.phone import normalise_phone
from app.core.tenancy import TenantScope
from app.models.audit import AuditLog
from app.models.customers import (
    Complaint,
    Customer,
    CustomerConsent,
    CustomerPreference,
    Feedback,
)
from app.repositories.customers import (
    ComplaintRepository,
    ConsentRepository,
    CustomerPreferenceRepository,
    CustomerRepository,
    FeedbackRepository,
    Visit,
)
from app.repositories.orders import OrderRepository

logger = logging.getLogger(__name__)

# What an erased customer's phone becomes. Not NULL — the column is the natural key and is NOT NULL
# — and not blank, because two erased customers would then collide on the unique constraint. It is
# deliberately not a number: nothing should ever be able to dial it.
_ERASED_PHONE = "erased:{customer_id}"


@dataclass(frozen=True, slots=True)
class CustomerHistory:
    """What this branch has seen of one person."""

    visits: list[Visit]
    feedback: list[Feedback]
    complaints: list[Complaint]


@dataclass(frozen=True, slots=True)
class CustomerExport:
    """The DPDP access right, assembled. The consent *history* rather than its current state: what
    somebody agreed to and when is the part that is evidence."""

    customer: Customer
    consents: list[CustomerConsent]
    history: CustomerHistory


@dataclass(frozen=True, slots=True)
class ErasureResult:
    """What was destroyed and what deliberately survives.

    Both halves, because the screen has to say both and because the test asserts the second: erasure
    must not move a rupee. `docs/security.md` — "it does not cascade-delete revenue history".
    """

    customer_id: uuid.UUID
    erased_at: datetime
    preferences_deleted: int
    orders_retained: int
    lifetime_value_retained: Decimal


class CustomerService:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session = session
        self.scope = scope
        self._customers = CustomerRepository(session, scope)
        self._preferences = CustomerPreferenceRepository(session, scope)
        self._consents = ConsentRepository(session, scope)
        self._orders = OrderRepository(session, scope)
        self._feedback = FeedbackRepository(session, scope)
        self._complaints = ComplaintRepository(session, scope)

    # ------------------------------------------------------------------ reading

    async def get(self, customer_id: uuid.UUID) -> Customer:
        customer = await self._customers.get_with_preferences(customer_id)
        if customer is None:
            raise NotFoundError("customer.not_found", "That customer no longer exists.")
        return customer

    async def search(
        self, *, term: str | None = None, limit: int | None = None, after: uuid.UUID | None = None
    ) -> Sequence[Customer]:
        """The customers of the branch this actor is working in.

        The branch filter lives in the repository, not here, so no caller can forget it: a service
        method that had to remember to pass a restaurant would eventually be called by one that
        did not.
        """
        return await self._customers.search(term=term, limit=limit, after=after)

    async def find_by_phone(self, phone: str) -> Customer | None:
        """Staff-side lookup. The guest surface has no equivalent, deliberately: `docs/security.md`
        says a guest lookup by phone must answer the same whether or not the number exists, and the
        simplest way to guarantee that is not to have one."""
        return await self._customers.by_phone(normalise_phone(phone))

    # ------------------------------------------------------------------ writing

    async def create(
        self,
        *,
        phone: str,
        name: str | None = None,
        email: str | None = None,
        birthday: object | None = None,
        anniversary: object | None = None,
    ) -> Customer:
        normalised = normalise_phone(phone)
        existing = await self._customers.by_phone(normalised)
        if existing is not None:
            # Returned rather than refused would quietly merge two people; refused with the id lets
            # the screen offer "open the existing customer" instead of making somebody search.
            raise ConflictError(
                "customer.phone_taken",
                "Somebody with this number is already a customer.",
                {"customer_id": str(existing.id)},
            )
        customer = Customer(
            organization_id=self.scope.organization_id,
            # The branch this person was first written down at. The organization owns the record;
            # the branch owns the view, and a customer created at a counter has no orders yet — this
            # is what stops them being invisible to whoever just typed them in.
            home_restaurant_id=self.scope.restaurant_id,
            phone=normalised,
            name=name,
            email=email,
            birthday=birthday,
            anniversary=anniversary,
        )
        self.session.add(customer)
        await self.session.flush()
        return customer

    async def update(self, customer_id: uuid.UUID, **fields: object) -> Customer:
        """No `phone`. It is the natural key: changing it silently merges or splits a person's
        history, and both are things somebody should have to do deliberately."""
        customer = await self.get(customer_id)
        if customer.erased_at is not None:
            raise ConflictError(
                "customer.erased", "This customer's details were erased at their request."
            )
        for name, value in fields.items():
            if value is not None:
                setattr(customer, name, value)
        await self.session.flush()
        return customer

    # ------------------------------------------------------------------ preferences

    async def add_preference(
        self,
        customer_id: uuid.UUID,
        *,
        type: PreferenceType,
        value: str,
        is_critical: bool = False,
    ) -> CustomerPreference:
        """What this person always wants, and whether the kitchen is told about it.

        `is_critical` means allergy. It does not mean "important": a spice level matters to the
        person and belongs on the waiter's screen, and a ticket carrying a regular's seating
        preference is noise — noise on a ticket is how a real allergy gets skimmed past.
        """
        customer = await self.get(customer_id)
        preference = CustomerPreference(
            organization_id=self.scope.organization_id,
            customer_id=customer.id,
            type=str(type),
            value=value,
            is_critical=is_critical,
        )
        self.session.add(preference)
        await self.session.flush()
        return preference

    async def remove_preference(self, customer_id: uuid.UUID, preference_id: uuid.UUID) -> None:
        customer = await self.get(customer_id)
        preference = await self._preferences.get_for_customer(customer.id, preference_id)
        if preference is None:
            raise NotFoundError("customer.preference_not_found", "That preference is already gone.")
        await self.session.delete(preference)
        await self.session.flush()

    # ------------------------------------------------------------------ the order attach

    async def attach_to_order(self, order_id: uuid.UUID, customer_id: uuid.UUID) -> str | None:
        """Put a customer on an order, and **freeze their allergies onto it**.

        Returns the note it wrote, or None when there is nothing to warn about.

        The copy is the whole point (`docs/modules/M10-customers-spec.md` decision 9). A live join
        would mean deleting a preference next week retroactively changes what the kitchen was told
        about a ticket it has already cooked. The kitchen's record of what it was warned about must
        be the warning it actually received — the same reasoning as M05's frozen batch costs and
        ADR 0011's frozen published metrics.

        Non-critical preferences are **not** copied and never reach the kitchen. They are for the
        waiter's screen, where `docs/customer-experience.md` puts them.
        """
        customer = await self.get(customer_id)
        order = await self._orders.get(order_id)
        if order is None:
            raise NotFoundError("order.not_found", "That order no longer exists.")

        allergies = await self._customers.critical_preferences(customer.id)
        note = ", ".join(allergies) or None

        order.customer_id = customer.id
        order.allergy_note = note
        await self.session.flush()
        logger.info(
            "customer.attached_to_order",
            extra={"has_allergy_note": note is not None, "allergies": len(allergies)},
        )
        return note

    # ------------------------------------------------------------------ consent

    async def record_consent(
        self,
        actor: Actor | None,
        customer_id: uuid.UUID,
        *,
        purpose: ConsentPurpose,
        granted: bool,
        notice_version: str,
        notice_language: str,
        source: ContactSource,
    ) -> CustomerConsent:
        """One purpose, one row. A withdrawal is `granted=False` and is exactly as easy.

        `actor` is None when the guest ticked it themselves, which is the case §B2 cares most about
        — and the only case where `captured_by` is null.
        """
        customer = await self.get(customer_id)
        if customer.erased_at is not None:
            # Consent for a person who has exercised erasure is a contradiction, and accepting one
            # would be the erasure quietly not holding.
            raise ConflictError(
                "customer.erased", "This customer's details were erased at their request."
            )
        consent = CustomerConsent(
            organization_id=self.scope.organization_id,
            customer_id=customer.id,
            purpose=str(purpose),
            granted=granted,
            notice_version=notice_version,
            notice_language=notice_language,
            source=str(source),
            captured_by=None if actor is None else actor.employee_id,
            occurred_at=datetime.now(UTC),
        )
        self.session.add(consent)
        await self.session.flush()
        logger.info(
            "customer.consent_recorded",
            extra={"purpose": str(purpose), "granted": granted, "source": str(source)},
        )
        return consent

    async def consent_state(self, customer_id: uuid.UUID) -> Sequence[CustomerConsent]:
        """The latest row per purpose. A purpose never answered is absent, not false — "we never
        asked" and "they said no" are different facts and a screen should show them differently."""
        return await self._consents.latest_per_purpose(customer_id)

    # ------------------------------------------------------------------ history

    async def history(self, customer_id: uuid.UUID) -> CustomerHistory:
        """Every visit, every rating, every complaint — for this branch.

        The branch filter is not an afterthought here either: a manager reading a customer's history
        reads what happened at their own restaurant. The record is the organization's so the person
        is recognised across branches; what each branch shows is its own.
        """
        customer = await self.get(customer_id)
        return CustomerHistory(
            visits=list(await self._customers.visits(customer.id, self.scope.restaurant_id)),
            feedback=list(await self._feedback.for_customer(customer.id)),
            complaints=list(await self._complaints.for_customer(customer.id)),
        )

    # ------------------------------------------------------------------ the two DPDP rights

    async def export(self, customer_id: uuid.UUID) -> CustomerExport:
        """Everything this product holds about one person, in one response — the DPDP access right.

        **Per customer, and there is no bulk version, in any role.** A customer list is a
        competitor's most valuable asset and the P1 design hands `customer.view` to waiters on
        purpose, so the control is the shape of the surface rather than the permission. Nothing here
        stops a determined person with an evening and a phone camera; it makes the fast version not
        exist.

        Audited, because a person reading out everything held about somebody is an event worth being
        able to ask about afterwards.
        """
        customer = await self.get(customer_id)
        return CustomerExport(
            customer=customer,
            consents=list(await self._consents.history(customer.id)),
            history=await self.history(customer.id),
        )

    async def erase(self, actor: Actor, customer_id: uuid.UUID) -> ErasureResult:
        """Destroy everything that names a person; keep everything that is a financial record.

        Irreversible, and the screen says so in those words before it is pressed. After this the
        same person returning is a new customer with no history — which is what erasure means.
        """
        customer = await self.get(customer_id)
        if customer.erased_at is not None:
            raise ConflictError(
                "customer.already_erased", "This customer's details were already erased."
            )

        retained = await self._customers.order_count(customer.id)
        lifetime_value = customer.lifetime_value
        deleted = await self._preferences.delete_all(customer.id)

        customer.phone = _ERASED_PHONE.format(customer_id=customer.id)
        customer.name = None
        customer.email = None
        customer.birthday = None
        customer.anniversary = None
        customer.is_active = False
        customer.erased_at = datetime.now(UTC)

        # The consent ledger is deliberately untouched. What survives is "marketing was granted on
        # this date and withdrawn on that one" against an id that no longer names anybody — which
        # is the record proving the erasure itself was lawful.
        self.session.add(
            AuditLog(
                restaurant_id=actor.restaurant_id,
                actor_employee_id=actor.employee_id,
                action="customer.erase",
                entity_type="customer",
                entity_id=customer.id,
                new_value={
                    "erased_at": customer.erased_at.isoformat(),
                    "preferences_deleted": deleted,
                    "orders_retained": retained,
                },
            )
        )
        await self.session.flush()
        logger.warning("customer.erased", extra={"preferences_deleted": deleted})
        return ErasureResult(
            customer_id=customer.id,
            erased_at=customer.erased_at,
            preferences_deleted=deleted,
            orders_retained=retained,
            lifetime_value_retained=lifetime_value,
        )
