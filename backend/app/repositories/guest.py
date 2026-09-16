"""Every query the guest realm is allowed to make. A third scope, because there is a third attacker.

`app/repositories/base.py` has two scoped classes and says why: "the threat model has two
attackers" — another organization, and another branch of the same one. The guest surface is a
third, and it cannot use either of them. A `TenantScope` requires an `organization_id`, and the
guest token deliberately does not carry one: which organization a restaurant belongs to is how a
chain recognises a diner across branches, and it is none of a table's business.

So a guest query is scoped by `restaurant_id` alone, from a `GuestScope`, through this file. The
Definition of Done's "tenant scoping through the repository layer only" then holds on the guest side
as well — and, more usefully, **no guest code can reach a staff repository**, because the scope
object those require cannot be constructed from a guest token.

What is here is deliberately small: a menu, a bill, one feedback row. Anything a guest cannot see is
not a filtered query in this file; it is a query this file does not have.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import OrderLineStatus
from app.core.guest_token import GuestScope
from app.models.base import Base
from app.models.customers import Customer, Feedback
from app.models.menu import MenuItem, MenuItemVariant
from app.models.orders import Order, OrderLine
from app.models.setup import RestaurantTable
from app.models.tenancy import Restaurant


class GuestScopedRepository[ModelT: Base]:
    """Scoped by restaurant, from a guest token, and constructible no other way."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession, scope: GuestScope) -> None:
        self.session = session
        self.scope = scope

    def scoped(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(
            self.model.restaurant_id == self.scope.restaurant_id  # type: ignore[attr-defined]
        )


class GuestTableRepository(GuestScopedRepository[RestaurantTable]):
    model = RestaurantTable


class GuestOrderRepository(GuestScopedRepository[Order]):
    model = Order

    async def feedback_context(self, order_id: uuid.UUID) -> FeedbackContext | None:
        """Two columns. Not the order: an order object in a write path is an order object one
        refactor away from being serialised to a guest."""
        row = (
            await self.session.execute(
                select(Order.waiter_employee_id, Order.business_date).where(
                    Order.id == order_id, Order.restaurant_id == self.scope.restaurant_id
                )
            )
        ).first()
        if row is None:
            return None
        return FeedbackContext(waiter_employee_id=row[0], business_date=row[1])

    async def bill(self, order_id: uuid.UUID) -> tuple[Order, Sequence[BillLine]] | None:
        """The order's totals, and its lines with dish names attached.

        **Two queries and no N+1**, which is a Definition-of-Done line rather than a preference: the
        totals come off `order`, and the lines come back in one statement that joins through
        `menu_item_variant` to `menu_item` for the name. A guest bill is read once per table per
        meal and it is read on a phone on a bad network; eleven round trips for eleven dishes is the
        difference between a screen that opens and one that does not.

        Cancelled lines are excluded. A dish that was sent back and taken off the bill is not on the
        bill, and showing it struck through is a conversation the guest has to start.
        """
        order = (await self.session.scalars(self.scoped().where(Order.id == order_id))).first()
        if order is None:
            return None

        rows = await self.session.execute(
            select(
                MenuItem.name,
                MenuItemVariant.name,
                OrderLine.quantity,
                OrderLine.line_subtotal,
            )
            .join(MenuItemVariant, MenuItemVariant.id == OrderLine.menu_item_variant_id)
            .join(MenuItem, MenuItem.id == MenuItemVariant.menu_item_id)
            .where(
                OrderLine.order_id == order_id,
                OrderLine.restaurant_id == self.scope.restaurant_id,
                OrderLine.status != OrderLineStatus.CANCELLED,
            )
            .order_by(OrderLine.seq)
        )
        lines = [
            BillLine(
                # "Butter Chicken (Full)" when the variant says something, "Butter Chicken" when it
                # is the only one. A bill that reads "Butter Chicken (Regular)" on every line is a
                # bill that has learned to say nothing in three extra words.
                name=item_name
                if variant_name.lower() in _SILENT_VARIANTS
                else f"{item_name} ({variant_name})",
                quantity=quantity,
                amount=subtotal,
            )
            for item_name, variant_name, quantity, subtotal in rows.all()
        ]
        return order, lines

    async def token_state(self, order_id: uuid.UUID) -> TokenState | None:
        """The order's current bill token and when it dies. None when there is no such order here.

        Two columns rather than the row, because the dependency that calls this needs nothing else
        and an order object in an auth path is an order object one refactor away from being
        serialised to a guest.
        """
        row = (
            await self.session.execute(
                select(Order.guest_token_hash, Order.guest_token_expires_at).where(
                    Order.id == order_id, Order.restaurant_id == self.scope.restaurant_id
                )
            )
        ).first()
        if row is None:
            return None
        return TokenState(token_hash=row[0], expires_at=row[1])


# Variant names that add nothing to a bill line. A menu with one size calls it "Regular" or
# "Full" and printing it beside every dish is three words that say nothing.
_SILENT_VARIANTS = frozenset({"regular", "standard", "default"})


@dataclass(frozen=True, slots=True)
class TokenState:
    """An order's current bill token and when it dies. Two columns, never the order row: an order
    object in an auth path is an order object one refactor away from being serialised to a guest."""

    token_hash: str | None
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class BillLine:
    """One line of what this table is having, before tax and before any discount."""

    name: str
    quantity: int
    amount: Decimal


@dataclass(frozen=True, slots=True)
class FeedbackContext:
    """What a feedback row needs from its order, and nothing else.

    The waiter and the business day are *derived* — a guest is never asked either. Asking which
    waiter it was would get a guess, and M17 pays attention to these numbers; asking which day it
    was would get today's, and a table that ordered at 1am belongs to the night it ate.
    """

    waiter_employee_id: uuid.UUID | None
    business_date: date


class GuestFeedbackRepository(GuestScopedRepository[Feedback]):
    model = Feedback

    async def for_order(self, order_id: uuid.UUID) -> Feedback | None:
        """Used to answer a second submission with the first row rather than an error."""
        result = await self.session.scalars(self.scoped().where(Feedback.order_id == order_id))
        return result.first()


class GuestCustomerRepository:
    """The one place the guest realm may write to an organization-scoped table.

    A customer belongs to the organization, and a guest token deliberately carries no organization
    — so this resolves the restaurant's organization itself, server-side, and nothing a guest sends
    influences the lookup. It is the server knowing something about its own restaurant.

    `find_or_create` and nothing else. A guest may cause a customer row to exist by typing their own
    number into the feedback form; they may not read one, search for one, or change one. There is no
    method here for any of that, which is a stronger guarantee than a permission check would be.
    """

    def __init__(self, session: AsyncSession, scope: GuestScope) -> None:
        self.session = session
        self.scope = scope

    async def find_or_create(self, phone: str) -> Customer:
        organization_id = await self.session.scalar(
            select(Restaurant.organization_id).where(Restaurant.id == self.scope.restaurant_id)
        )
        existing = await self.session.scalars(
            select(Customer).where(
                Customer.organization_id == organization_id, Customer.phone == phone
            )
        )
        found = existing.first()
        if found is not None:
            # Deliberately returns the row and tells the caller nothing about whether it existed.
            # `docs/security.md`: a guest lookup by phone must answer identically either way, and a
            # service that cannot learn the difference cannot leak it.
            return found

        customer = Customer(organization_id=organization_id, phone=phone)
        self.session.add(customer)
        await self.session.flush()
        return customer


# --------------------------------------------------------------------------- establishing a scope
#
# Exactly two queries in this module have no scope, and they are the two that *establish* one. A
# slug and a token hash are each globally unique, so each determines a restaurant rather than
# assuming one. Everything else in the guest realm is scoped by what these return, and there is no
# third: a guest query without a scope is a bug, and keeping the exceptions in one place, under one
# heading, is what makes a third one visible if somebody adds it.


async def table_by_slug(session: AsyncSession, slug: str) -> RestaurantTable | None:
    """A table's public id, off the sticker. Inactive tables do not resolve."""
    result = await session.scalars(
        select(RestaurantTable).where(
            RestaurantTable.guest_slug == slug, RestaurantTable.is_active.is_(True)
        )
    )
    return result.first()


async def order_by_token_hash(session: AsyncSession, token_hash: str) -> Order | None:
    """A bill's capability, off the QR on the bill.

    The *hash* is what is compared, because the raw token is never stored - the same reasoning as
    `hash_refresh_token`: a stolen dump must yield no live ones. Expiry is checked by the caller,
    not here, so that "there is no such token" and "that bill is finished with" are one refusal at
    one place (`docs/security.md`: no enumeration).
    """
    result = await session.scalars(select(Order).where(Order.guest_token_hash == token_hash))
    return result.first()
