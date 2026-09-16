"""Feedback: three questions, once per order, and a phone number only if somebody offers one.

`docs/customer-experience.md` is the spec behind the spec, and four of its statements are
load-bearing here.

**1 · Three questions maximum.** "Food, service, would-you-return. Free text optional. Every extra
question halves completion." The request schema has no room for a fourth, which is the cheapest
possible way to keep that true.

**2 · Always order-linked.** Feedback that is not attached to an order "can't reach the dish,
waiter, station or prep time - and is nearly worthless". The bill token supplies all four without
the guest identifying themselves at all, which is why anonymous feedback here is *not* the weak
kind: it is fully linked to everything that matters operationally and linked to nobody personally.

**3 · Never ask twice in one visit.** A unique index on `feedback.order_id`, and this service
returning the existing row rather than raising. A guest who taps Send twice on a slow network gets
"thank you" both times, because the alternative is telling somebody they have already done the thing
they are trying to do.

**4 · The waiter is derived, never asked.** `feedback.waiter_employee_id` comes from the order, so
a rating lands on whoever actually served the table. Asking a guest which waiter it was would get a
guess, and M17 pays attention to these numbers.

**And the rule that is not from that document.** A phone number is personal data and its capture is
separate from the feedback: the rating is written whether or not a number was given, and a number
with no consent ticked is not stored at all. `docs/compliance-rules.md` §B2 - the notice, the
purposes, and the fact that none of them is pre-ticked - is the reason this method is longer than
it looks like it should be.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.consent import (
    CURRENT_NOTICE_VERSION,
    DEFAULT_NOTICE_LANGUAGE,
    GUEST_OFFERABLE,
)
from app.core.enums import ConsentPurpose, ContactSource
from app.core.errors import AppError, NotFoundError
from app.core.guest_token import GuestScope
from app.core.phone import normalise_phone
from app.models.customers import CustomerConsent, Feedback
from app.repositories.guest import (
    GuestCustomerRepository,
    GuestFeedbackRepository,
    GuestOrderRepository,
)

logger = logging.getLogger(__name__)


class GuestFeedbackService:
    """The guest side. There is a staff side too, and they are deliberately different classes:
    a manager writing down a phone call and a diner tapping three buttons share a table and almost
    nothing else."""

    def __init__(self, session: AsyncSession, scope: GuestScope) -> None:
        self.session = session
        self.scope = scope
        self._feedback = GuestFeedbackRepository(session, scope)
        self._orders = GuestOrderRepository(session, scope)
        self._customers = GuestCustomerRepository(session, scope)

    async def submit(
        self,
        order_id: uuid.UUID,
        *,
        food_rating: int | None,
        service_rating: int | None,
        would_return: bool | None,
        comment: str | None,
        phone: str | None,
        consents: list[ConsentPurpose],
        notice_version: str | None,
        notice_language: str | None,
    ) -> tuple[Feedback, bool]:
        """Returns the row and whether it already existed.

        The order of operations matters and is not the obvious one: **the feedback is written
        first**, and the phone number is attached afterwards. If capturing the number fails - a
        malformed number, a consent for a purpose that no longer exists - the restaurant still has
        the rating. The opposite order loses the thing the guest actually came to say in order to
        protect a field they were told was optional.
        """
        existing = await self._feedback.for_order(order_id)
        if existing is not None:
            return existing, True

        context = await self._orders.feedback_context(order_id)
        if context is None:
            # The dependency already proved this order is in scope, so this is a race rather than
            # an attack: the order was voided between opening the session and tapping Send.
            raise NotFoundError("feedback.order_not_found", "That order is no longer open.")

        feedback = Feedback(
            restaurant_id=self.scope.restaurant_id,
            order_id=order_id,
            # Null until, and unless, a phone number is given and consented to below. Anonymous is
            # the default path and it is complete: this row already reaches the dish, the waiter,
            # the station and the prep time through the order.
            customer_id=None,
            food_rating=food_rating,
            service_rating=service_rating,
            would_return=would_return,
            comment=comment,
            # Derived from the order, never asked. A guest asked which waiter it was would guess,
            # and M17 pays attention to these numbers.
            waiter_employee_id=context.waiter_employee_id,
            source=ContactSource.QR,
            submitted_at=datetime.now(UTC),
            # The order's business day, not today's. A table that ordered at 1am belongs to the
            # night it ate, and `restaurant.business_day_start` is what says so (invariant 4).
            business_date=context.business_date,
        )
        self.session.add(feedback)
        await self.session.flush()

        # The rating is written before the phone number is touched. If capturing the number fails,
        # the restaurant still has what the guest came to say.
        if phone and consents:
            await self._attach_contact(
                feedback,
                phone=phone,
                consents=consents,
                notice_version=notice_version,
                notice_language=notice_language,
            )

        logger.info(
            "feedback.submitted",
            extra={
                # Ratings and a count. No number, no name, no comment text: "no PII in logs" is a
                # Definition-of-Done line and this is the first module with real PII in it.
                "food_rating": food_rating,
                "service_rating": service_rating,
                "would_return": would_return,
                "has_comment": comment is not None,
                "consents": len(consents),
            },
        )
        return feedback, False

    async def _attach_contact(
        self,
        feedback: Feedback,
        *,
        phone: str,
        consents: list[ConsentPurpose],
        notice_version: str | None,
        notice_language: str | None,
    ) -> None:
        """A phone number, and one consent row per purpose the guest actually ticked.

        Four rules, all from `docs/compliance-rules.md` §B2, and each one is a line somebody could
        reasonably have written differently:

        **A number with nothing ticked is not stored.** Not stored with a false consent, not stored
        "pending" — not stored. A number typed and then reconsidered is a number we were not given.

        **A purpose the guest did not tick produces no row at all.** Not a row saying `granted =
        false`: "they said no" and "we never asked" are different facts, and a screen that showed
        them the same way would be showing something untrue.

        **The notice is recorded from what the client says it displayed**, and the client's constant
        is held to the server's by `tests/test_consent_notice.py`. A version the guest never saw is
        a consent record that proves nothing.

        **`GUEST_OFFERABLE` bounds what this path may grant.** A request naming
        `feedback_followup` is refused rather than honoured: that purpose is granted by staff on the
        profile, when somebody agrees on the phone, and a three-tap form is not where it belongs.
        """
        unofferable = [purpose for purpose in consents if purpose not in GUEST_OFFERABLE]
        if unofferable:
            raise AppError(
                "consent.purpose_not_offered",
                "That is not something this form can ask for.",
                status_code=422,
            )

        customer = await self._customers.find_or_create(normalise_phone(phone))
        feedback.customer_id = customer.id

        version = notice_version or CURRENT_NOTICE_VERSION
        language = notice_language or DEFAULT_NOTICE_LANGUAGE
        for purpose in consents:
            self.session.add(
                CustomerConsent(
                    organization_id=customer.organization_id,
                    customer_id=customer.id,
                    purpose=str(purpose),
                    granted=True,
                    notice_version=version,
                    notice_language=language,
                    source=ContactSource.QR,
                    # Null: the guest ticked it themselves, which is the case §B2 cares most about.
                    captured_by=None,
                    occurred_at=datetime.now(UTC),
                )
            )
        await self.session.flush()

    async def withdraw(
        self,
        order_id: uuid.UUID,
        *,
        purpose: ConsentPurpose,
        notice_version: str,
        notice_language: str,
    ) -> CustomerConsent:
        """Take a consent away, from the screen the guest is already looking at.

        §B2 asks that withdrawing be as easy as granting, and one tap on the same screen is the only
        reading of that sentence worth having. It reaches the customer through *this order* — a
        guest may withdraw a consent for the bill in their hand and for nothing else.

        **There is no grant here.** An anonymous surface cannot know whose phone is in whose hand,
        so a bill token may take a consent away and may never hand one out. The asymmetry is
        deliberate: withdrawing on somebody's behalf is at worst an inconvenience, and granting on
        their behalf is a fabricated consent.
        """
        feedback = await self._feedback.for_order(order_id)
        if feedback is None or feedback.customer_id is None:
            # Nothing was ever given from this bill, so there is nothing to take away — and saying
            # which of the two it was would be an oracle for whether a number is held.
            raise NotFoundError("consent.nothing_to_withdraw", "There is nothing to turn off here.")

        consent = CustomerConsent(
            organization_id=await self._customers.organization_id(),
            customer_id=feedback.customer_id,
            purpose=str(purpose),
            granted=False,
            notice_version=notice_version,
            notice_language=notice_language,
            source=ContactSource.QR,
            # The guest did this themselves, which is the case §B2 cares most about.
            captured_by=None,
            occurred_at=datetime.now(UTC),
        )
        self.session.add(consent)
        await self.session.flush()
        logger.info("consent.withdrawn", extra={"purpose": str(purpose)})
        return consent
