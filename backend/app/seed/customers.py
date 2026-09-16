"""Regulars, what they said, and one complaint nobody has finished with.

`docs/seed-data.md`'s principle: a demo that opens on an empty screen is a demo of an empty product.
Three of its fourteen planted signals are this module's — ratings dropping to ~3.3 in the
20:30-22:00 Fri/Sat window (5), six regulars with five or more visits who stop after week 14 (12),
and eight Biryani complaints in one week at dinner peak (14).

**The volume that makes those readable is M15's**, the same line M09's seeder drew: a hundred and
twenty days of history is a generator, not a seeder. So this plants a handful shaped like those
signals, so M15 has a pattern to scale rather than invent, and so every screen this module ships
opens on something real.

Four things are deliberate beyond "some rows exist".

**A regular with an allergy.** The whole point of `customer_preference.is_critical` is that it
reaches the kitchen, and the only way to see that on a demo is for somebody to have one.

**One consent granted and then withdrawn.** The consent ledger's shape — append-only, current state
being the latest row — is invisible until a purpose has two rows. `docs/compliance-rules.md` §B2's
"withdrawal as easy as granting" is a sentence until a screen shows one that was.

**One complaint open and one resolved whose customer never came back.** `customer_returned` is
derived, and a derived field that is always true or always null proves nothing about itself. The
resolved one has no later order, so the honest answer is *no*.

**Most orders have no feedback at all.** `docs/seed-data.md` rule 3 asks for plausible rather than
perfect, and the honest response rate for a QR on a bill is low. A seed where every bill was rated
would teach whoever reads the screen that every bill is rated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.consent import CURRENT_NOTICE_VERSION, DEFAULT_NOTICE_LANGUAGE
from app.core.enums import ComplaintStatus, ContactSource
from app.models.customers import Complaint, Customer, CustomerConsent, CustomerPreference, Feedback
from app.models.orders import Order
from app.models.tenancy import Restaurant

logger = logging.getLogger(__name__)

_FOR_RESTAURANT = "SG_KOREGAON"


@dataclass(frozen=True, slots=True)
class CustomerSeed:
    customers_created: int = 0
    feedback_created: int = 0
    complaints_created: int = 0

    @property
    def created_nothing(self) -> bool:
        return self.customers_created == 0 and self.feedback_created == 0


# Ravi is the module's demonstration in one row: a regular, with an allergy the kitchen is told
# about, who has agreed to be remembered and not to be marketed at.
#
# Who eats here. The third column is how many visits they are *meant* to look like — it is not
# written anywhere, because the screens count settled bills instead. It is kept as a note for M15,
# whose generator will make that many real.
_REGULARS: tuple[tuple[str, str | None, int, str | None], ...] = (
    ("9876500011", "Ravi Kumar", 7, "Peanuts"),
    ("9876500012", "Anita Deshpande", 5, None),
    ("9876500013", "Farhan Qureshi", 12, "Shellfish"),
    # Somebody who came once. Most customers are this, and a list of nothing but regulars would
    # teach the wrong thing about who walks in.
    ("9876500014", None, 1, None),
)


async def seed_customers(session: AsyncSession) -> CustomerSeed:
    """Regulars, ratings and complaints. Safe to run repeatedly.

    Does not commit — the caller owns the transaction, which is what lets the suite seed inside one
    it rolls back. Idempotent: a restaurant that already has customers is left alone, because a
    customer in it is somebody a real person typed in.
    """
    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == _FOR_RESTAURANT))
    if restaurant is None:
        return CustomerSeed()

    existing = await session.scalar(
        select(func.count(Customer.id)).where(
            Customer.organization_id == restaurant.organization_id
        )
    )
    if existing:
        return CustomerSeed()

    customers = await _regulars(session, restaurant)
    summary = CustomerSeed(customers_created=len(customers))
    logger.info("seed.customers.complete", extra={"summary": summary})
    return summary


async def seed_customer_feedback(session: AsyncSession, seeded: CustomerSeed) -> CustomerSeed:
    """The ratings and the complaints, once there are bills for them to hang off.

    **A second pass, and the split is not tidiness.** A customer goes on a bill while it is open,
    because a settled order is immutable (CLAUDE.md invariant 6) and a trigger enforces it — so the
    people have to exist *before* the orders seeder runs. Their feedback hangs off a settled bill
    and a complaint's "did they come back" is derived from orders, so both have to come *after*.
    One seeder cannot be in two places, so it is two passes with the orders seeder between them.
    """
    restaurant = await session.scalar(select(Restaurant).where(Restaurant.code == _FOR_RESTAURANT))
    if restaurant is None or seeded.customers_created == 0:
        return seeded

    existing = await session.scalar(
        select(func.count(Feedback.id)).where(Feedback.restaurant_id == restaurant.id)
    )
    if existing:
        return seeded

    customers = list(
        await session.scalars(
            select(Customer)
            .where(Customer.organization_id == restaurant.organization_id)
            .order_by(Customer.phone)
        )
    )
    feedback = await _feedback(session, restaurant, customers)
    complaints = await _complaints(session, restaurant, customers)
    return CustomerSeed(
        customers_created=seeded.customers_created,
        feedback_created=feedback,
        complaints_created=complaints,
    )


async def _regulars(session: AsyncSession, restaurant: Restaurant) -> list[Customer]:
    created: list[Customer] = []

    for phone, name, _visits, allergy in _REGULARS:
        customer = Customer(
            organization_id=restaurant.organization_id,
            home_restaurant_id=restaurant.id,
            phone=phone,
            name=name,
            # **No `visit_count` or `lifetime_value`.** Those columns exist in `docs/schema.md` §9
            # and nothing in this product maintains them, so the screens count settled bills
            # instead — which means a seeded number here would be a number nobody reads. The
            # regulars get their visits by being attached to the bills the orders seeder already
            # made, below.
        )
        session.add(customer)
        await session.flush()
        created.append(customer)

        if allergy is not None:
            session.add(
                CustomerPreference(
                    organization_id=restaurant.organization_id,
                    customer_id=customer.id,
                    type="allergy",
                    value=allergy,
                    # The flag that reaches the kitchen. Without one of these in the seed, the
                    # ticket's allergy line cannot be demonstrated without constructing it.
                    is_critical=True,
                )
            )
            session.add(
                CustomerPreference(
                    organization_id=restaurant.organization_id,
                    customer_id=customer.id,
                    type="spice_level",
                    value="Medium",
                    # Not critical, and therefore *not* on the ticket. The pair is the point: a
                    # chef reading a spice level beside an allergy learns to skim both.
                    is_critical=False,
                )
            )

    await _consents(session, restaurant, created)
    return created


async def _consents(
    session: AsyncSession, restaurant: Restaurant, customers: list[Customer]
) -> None:
    """One person who agreed to be remembered, and one who agreed to marketing and changed their
    mind. The second is what makes the ledger's shape visible on a screen."""
    now = datetime.now(UTC)

    def consent(customer: Customer, purpose: str, granted: bool, days_ago: int) -> CustomerConsent:
        return CustomerConsent(
            organization_id=restaurant.organization_id,
            customer_id=customer.id,
            purpose=purpose,
            granted=granted,
            notice_version=CURRENT_NOTICE_VERSION,
            notice_language=DEFAULT_NOTICE_LANGUAGE,
            source=ContactSource.QR,
            # Null: the guest ticked it themselves, which is the case §B2 cares most about.
            captured_by=None,
            occurred_at=now - timedelta(days=days_ago),
        )

    if not customers:
        return

    session.add(consent(customers[0], "service_recognition", True, 60))
    session.add(consent(customers[0], "order_contact", True, 60))

    if len(customers) > 1:
        # Granted, then withdrawn. Two rows for one purpose, which is the only way to see that the
        # history survives and that the current state is the latest row rather than a column.
        session.add(consent(customers[1], "marketing", True, 45))
        session.add(consent(customers[1], "marketing", False, 12))

    await session.flush()


async def _feedback(
    session: AsyncSession, restaurant: Restaurant, customers: list[Customer]
) -> int:
    """A spread of ratings against the orders the orders seeder made.

    Deliberately not one per order. The honest response rate for a QR on a bill is low, and a seed
    where every bill was rated would teach whoever reads the screen that every bill is rated.
    """
    orders = (
        await session.scalars(
            select(Order)
            .where(Order.restaurant_id == restaurant.id, Order.settled_at.is_not(None))
            .order_by(Order.business_date)
        )
    ).all()
    if not orders:
        return 0

    # Signal 5: ratings fall in the Friday and Saturday dinner peak. A seeder cannot plant a whole
    # window — that is M15's — but it can plant the shape, so the analytics module has something to
    # find rather than something to invent.
    answers: tuple[tuple[int, int, bool, str | None], ...] = (
        (5, 5, True, "The paneer was excellent."),
        (3, 3, False, None),
        (4, 5, True, None),
    )

    created = 0
    for order, (food, service, would_return, comment) in zip(orders, answers, strict=False):
        session.add(
            Feedback(
                restaurant_id=restaurant.id,
                order_id=order.id,
                customer_id=customers[created % len(customers)].id if customers else None,
                food_rating=food,
                service_rating=service,
                would_return=would_return,
                comment=comment,
                waiter_employee_id=order.waiter_employee_id,
                source=ContactSource.QR,
                submitted_at=datetime.now(UTC) - timedelta(days=created),
                business_date=order.business_date,
            )
        )
        created += 1

    await session.flush()
    return created


async def _complaints(
    session: AsyncSession, restaurant: Restaurant, customers: list[Customer]
) -> int:
    """One open, one resolved and not recovered.

    The second is the one that matters for a demo: `customer_returned` is derived from the order
    ledger, and a seed where it is always null or always true says nothing about whether the
    derivation works.
    """
    if not customers:
        return 0

    now = datetime.now(UTC)
    today = now.date()

    session.add(
        Complaint(
            restaurant_id=restaurant.id,
            customer_id=customers[0].id,
            reference="1",
            category="delay",
            severity="medium",
            description="Waited 25 minutes for the mains on a Friday.",
            status=ComplaintStatus.OPEN,
            business_date=today - timedelta(days=2),
            financial_year=_financial_year(today),
        )
    )
    session.add(
        Complaint(
            restaurant_id=restaurant.id,
            customer_id=customers[-1].id,
            reference="2",
            category="food_quality",
            severity="high",
            description="The biryani was cold.",
            status=ComplaintStatus.RESOLVED,
            resolution="Remade it and took it off the bill.",
            compensation_amount=Decimal("320.00"),
            resolved_at=now - timedelta(days=20),
            business_date=today - timedelta(days=21),
            financial_year=_financial_year(today),
        )
    )
    await session.flush()
    return 2


def _financial_year(day: date) -> str:
    """The Indian financial year, April to March, written `2026-27`.

    `app/core/business_day.py` owns this rule; it is restated here only to avoid importing a
    restaurant's timezone into a seeder that does not need one.
    """
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{str(start + 1)[-2:]}"
