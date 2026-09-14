"""Queries over orders and what they cost. Business rules live in the service, not here.

Four of these carry weight.

**`lock` takes the order row, and every change goes through it.** ADR 0010 chose optimistic
locking for *people*: a stale version is a 409. But two requests carrying the same, current
version still have to be serialised, or both pass the version check and the second reprice
overwrites the first. The lock is held only for one request, so a waiter who walks away blocks
nobody (the ADR's reason for rejecting pessimistic locking on orders).

**`next_order_number` takes a transaction-scoped advisory lock** per restaurant and business day —
the arrangement M06 proved for purchase-order numbers under five-way contention. Two waiters opening
tables in the same second must not both be "order 42".

**`live_order_on_table` is the question the table-status endpoint asks** before letting a table be
marked free: is anybody still eating here?

**`PricingRepository.rate_on` never locks.** `TaxRateRepository.live_on` takes `FOR UPDATE` because
its caller may be about to insert a successor rate; pricing a dish is not, and a lock there would
serialise every order in the restaurant behind whichever tab is adding a line.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from sqlalchemy import Integer, Select, and_, cast, func, literal, or_, select, update
from sqlalchemy.orm import joinedload, selectinload

from app.core.enums import (
    CashMovementType,
    CashSessionStatus,
    InvoiceStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)
from app.models.menu import (
    MenuItem,
    MenuItemModifierGroup,
    MenuItemVariant,
    Modifier,
    ModifierGroup,
)
from app.models.orders import (
    CashCount,
    CashMovement,
    CashSession,
    CreditNote,
    CreditNoteLine,
    Invoice,
    Order,
    OrderDiscount,
    OrderLine,
    OrderTable,
    Payment,
)
from app.models.setup import DiningArea, RestaurantTable, TaxGroup, TaxRate
from app.repositories.base import RestaurantScopedRepository, ScopedRepository, page_size

# A namespace for the two-int advisory lock, distinct from M06's 60_001, so an order-number lock can
# never collide with a purchase-order-number lock on the same restaurant.
_ORDER_NUMBER_LOCK_NAMESPACE = 70_001

LIVE_ORDER_STATUSES = (OrderStatus.OPEN, OrderStatus.SENT, OrderStatus.SERVED)


class OrderRepository(RestaurantScopedRepository[Order]):
    model = Order

    def _detailed(self) -> Select[tuple[Order]]:
        return self.scoped().options(
            selectinload(Order.lines).selectinload(OrderLine.modifiers),
            selectinload(Order.discounts),
            selectinload(Order.charges),
            selectinload(Order.tables),
            selectinload(Order.waiter),
        )

    async def get_detail(self, order_id: uuid.UUID, *, refresh: bool = False) -> Order | None:
        """The order with everything a bill reads, in five statements whatever its size.

        `refresh` re-reads rows already in the session. A change flushes and then reprices from what
        the database now holds; without it, the identity map would hand back the collections as they
        were before the change, and a deleted line would still be on the bill.
        """
        query = self._detailed().where(Order.id == order_id)
        if refresh:
            query = query.execution_options(populate_existing=True)
        return (await self.session.scalars(query)).first()

    async def lock(self, order_id: uuid.UUID) -> bool:
        """Lock the order row for the rest of the transaction. False when there is no such order."""
        locked = await self.session.scalar(
            self.scoped().where(Order.id == order_id).with_for_update()
        )
        return locked is not None

    async def list_page(
        self,
        *,
        statuses: Sequence[str] | None = None,
        business_date: date | None = None,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[Order]:
        """Newest first. Ids are UUIDv7 and so time-ordered, which makes the id the cursor.

        Tables are loaded in one extra statement for the page, never one per order.
        """
        query = self.scoped().options(selectinload(Order.tables), selectinload(Order.waiter))
        if statuses:
            query = query.where(Order.status.in_(statuses))
        if business_date is not None:
            query = query.where(Order.business_date == business_date)
        if after is not None:
            query = query.where(Order.id < after)
        query = query.order_by(Order.id.desc()).limit(page_size(limit))
        return (await self.session.scalars(query)).all()

    async def next_order_number(self, business_date: date) -> str:
        """The next number for this business day, allocated under a lock held to commit.

        Counting restarts every business day because "table 6, order 42" is what a waiter calls
        out, and a number that never resets is not something anyone calls out.
        """
        key = f"{self.scope.restaurant_id}:{business_date.isoformat()}"
        await self.session.execute(
            select(
                func.pg_advisory_xact_lock(
                    literal(_ORDER_NUMBER_LOCK_NAMESPACE), func.hashtext(key)
                )
            )
        )
        highest = await self.session.scalar(
            self.scoped()
            .with_only_columns(func.max(cast(Order.order_number, Integer)))
            .where(Order.business_date == business_date)
        )
        return str((highest or 0) + 1)

    async def move_lines(self, line_ids: Sequence[uuid.UUID], to_order_id: uuid.UUID) -> None:
        """Move lines, and the discounts aimed at them, to another order of this restaurant.

        Both statements are scoped, and migration 0019 refuses the move if either order is final.
        """
        await self.session.execute(
            update(OrderLine)
            .where(
                OrderLine.id.in_(line_ids),
                OrderLine.restaurant_id == self.scope.restaurant_id,
            )
            .values(order_id=to_order_id)
        )
        await self.session.execute(
            update(OrderDiscount)
            .where(
                OrderDiscount.order_line_id.in_(line_ids),
                OrderDiscount.restaurant_id == self.scope.restaurant_id,
            )
            .values(order_id=to_order_id)
        )

    async def floor_tables(self) -> Sequence[tuple[DiningArea, RestaurantTable]]:
        """Every active table with its area, in floor order. One statement, unpaged on purpose:
        a floor plan cut off at a page boundary is a table nobody can seat."""
        rows = await self.session.execute(
            select(DiningArea, RestaurantTable)
            .join(RestaurantTable, RestaurantTable.dining_area_id == DiningArea.id)
            .where(
                DiningArea.restaurant_id == self.scope.restaurant_id,
                RestaurantTable.restaurant_id == self.scope.restaurant_id,
                DiningArea.is_active.is_(True),
                RestaurantTable.is_active.is_(True),
            )
            .order_by(DiningArea.seq, DiningArea.id, RestaurantTable.code)
        )
        return rows.tuples().all()

    async def live_at_tables(self) -> Sequence[tuple[Order, uuid.UUID]]:
        """Every live order with each table it sits at. One statement for the whole floor."""
        rows = await self.session.execute(
            self.scoped()
            # Joined, not select-in: the waiter's name rides on the same statement, so the map costs
            # the same with no orders open as with forty (tests/test_floor.py).
            .options(joinedload(Order.waiter))
            .add_columns(OrderTable.restaurant_table_id)
            .join(OrderTable, OrderTable.order_id == Order.id)
            .where(Order.status.in_(LIVE_ORDER_STATUSES))
            .order_by(Order.placed_at)
        )
        return rows.tuples().all()

    async def live_order_on_table(
        self, table_id: uuid.UUID, *, excluding: uuid.UUID | None = None
    ) -> Order | None:
        query = (
            self.scoped()
            .join(OrderTable, OrderTable.order_id == Order.id)
            .where(
                OrderTable.restaurant_table_id == table_id,
                Order.status.in_(LIVE_ORDER_STATUSES),
            )
        )
        if excluding is not None:
            query = query.where(Order.id != excluding)
        return (await self.session.scalars(query.limit(1))).first()


@dataclass(frozen=True, slots=True)
class SaleableVariant:
    variant: MenuItemVariant
    item: MenuItem


@dataclass(frozen=True, slots=True)
class RateOnDate:
    regime: str
    rate: Decimal
    inclusive: bool


class PricingRepository(ScopedRepository[MenuItemVariant]):
    """What the menu says a dish costs and how it is taxed. Read here; never taken from a client.

    Scoped by hand on every table it touches, because it joins across four of them and the base
    class's `scoped()` covers only one.
    """

    model = MenuItemVariant

    async def saleable_variant(self, variant_id: uuid.UUID) -> SaleableVariant | None:
        row = (
            await self.session.execute(
                select(MenuItemVariant, MenuItem)
                .join(MenuItem, MenuItem.id == MenuItemVariant.menu_item_id)
                .where(
                    MenuItemVariant.id == variant_id,
                    MenuItemVariant.restaurant_id == self.scope.restaurant_id,
                    MenuItem.restaurant_id == self.scope.restaurant_id,
                )
            )
        ).first()
        return None if row is None else SaleableVariant(variant=row[0], item=row[1])

    async def groups_for_item(self, item_id: uuid.UUID) -> Sequence[ModifierGroup]:
        """The active questions asked about this dish, with their selection limits."""
        result = await self.session.scalars(
            select(ModifierGroup)
            .join(
                MenuItemModifierGroup,
                MenuItemModifierGroup.modifier_group_id == ModifierGroup.id,
            )
            .where(
                MenuItemModifierGroup.menu_item_id == item_id,
                ModifierGroup.restaurant_id == self.scope.restaurant_id,
                ModifierGroup.is_active.is_(True),
            )
        )
        return result.all()

    async def modifiers_for_item(
        self, item_id: uuid.UUID
    ) -> Sequence[tuple[Modifier, ModifierGroup]]:
        """Every active answer those questions offer."""
        rows = await self.session.execute(
            select(Modifier, ModifierGroup)
            .join(ModifierGroup, ModifierGroup.id == Modifier.modifier_group_id)
            .join(
                MenuItemModifierGroup,
                MenuItemModifierGroup.modifier_group_id == ModifierGroup.id,
            )
            .where(
                MenuItemModifierGroup.menu_item_id == item_id,
                Modifier.restaurant_id == self.scope.restaurant_id,
                ModifierGroup.restaurant_id == self.scope.restaurant_id,
                Modifier.is_active.is_(True),
                ModifierGroup.is_active.is_(True),
            )
        )
        return [(modifier, group) for modifier, group in rows.tuples().all()]

    async def rate_on(self, tax_group_id: uuid.UUID, on: date) -> RateOnDate | None:
        """The group's regime and the rate whose period covers `on`. Never locks: see the module."""
        row = (
            await self.session.execute(
                select(TaxGroup.regime, TaxRate.rate, TaxRate.is_inclusive)
                .join(TaxRate, TaxRate.tax_group_id == TaxGroup.id)
                .where(
                    TaxGroup.id == tax_group_id,
                    TaxGroup.restaurant_id == self.scope.restaurant_id,
                    TaxRate.restaurant_id == self.scope.restaurant_id,
                    TaxRate.effective_from <= on,
                    or_(TaxRate.effective_to.is_(None), TaxRate.effective_to >= on),
                )
                .order_by(TaxRate.effective_from.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            return None
        regime, rate, inclusive = row
        rate_value = rate if isinstance(rate, Decimal) else Decimal(str(rate))
        return RateOnDate(regime=str(regime), rate=rate_value, inclusive=bool(inclusive))


# ----------------------------------------------------------------------------------------- invoices
#
# Appended to app/repositories/orders.py by chunk G's patch.

# Distinct from the order-number (70_001) and purchase-order (60_001) namespaces, so an invoice
# lock can never collide with either on the same restaurant.
_INVOICE_NUMBER_LOCK_NAMESPACE = 80_001


class InvoiceRepository(RestaurantScopedRepository[Invoice]):
    model = Invoice

    async def get_for_update(self, invoice_id: uuid.UUID) -> Invoice | None:
        """Locked, so a cancellation and a credit note against one invoice cannot interleave."""
        query = self.scoped().where(Invoice.id == invoice_id).with_for_update()
        return (await self.session.scalars(query)).first()

    async def next_sequence(self, financial_year: str) -> int:
        """The next consecutive number in this restaurant's series for the year, under a lock held
        to commit (CGST Rules, Rule 46(b); spec decision 1).

        **Gapless because the lock and the insert share a transaction.** A settlement that fails
        after allocating a number rolls back its invoice row, and the next settlement — waiting on
        this lock — reads the same maximum and takes the same number. A sequence object would hand
        out the number and keep it, leaving exactly the gap an assessment asks about.
        """
        key = f"{self.scope.restaurant_id}:{financial_year}"
        await self.session.execute(
            select(
                func.pg_advisory_xact_lock(
                    literal(_INVOICE_NUMBER_LOCK_NAMESPACE), func.hashtext(key)
                )
            )
        )
        highest = await self.session.scalar(
            self.scoped()
            .with_only_columns(func.max(Invoice.sequence))
            .where(Invoice.financial_year == financial_year)
        )
        return int(highest or 0) + 1

    async def for_order(self, order_id: uuid.UUID) -> Invoice | None:
        return (
            await self.session.scalars(self.scoped().where(Invoice.order_id == order_id))
        ).first()


@dataclass(frozen=True, slots=True)
class TillTotals:
    """What moved through one till. Expected cash is derived from these, never stored."""

    cash_taken: Decimal = Decimal("0.00")
    payouts: Decimal = Decimal("0.00")
    adjustments: Decimal = Decimal("0.00")


class CashSessionRepository(RestaurantScopedRepository[CashSession]):
    model = CashSession

    async def open_id(self) -> uuid.UUID | None:
        """The till open now, if any, share-locked until the transaction ends.

        At most one, by migration 0019's partial unique index. The lock is what keeps cash out of a
        till being counted: a close holds the row, so a caller posting a payment waits for it, and
        once the close commits the re-checked status no longer matches and there is no open till
        (second reader, finding 1). Migration 0021's trigger refuses the write regardless.
        """
        found: uuid.UUID | None = await self.session.scalar(
            self.scoped()
            .with_only_columns(CashSession.id)
            .where(CashSession.status == CashSessionStatus.OPEN)
            .with_for_update(read=True)
        )
        return found

    async def status_for_share(self, till_id: uuid.UUID) -> str | None:
        """A till's status, share-locked so a close cannot finish while the caller acts on it."""
        found: str | None = await self.session.scalar(
            self.scoped()
            .with_only_columns(CashSession.status)
            .where(CashSession.id == till_id)
            .with_for_update(read=True)
        )
        return found

    async def get_for_update(self, till_id: uuid.UUID) -> CashSession | None:
        return (
            await self.session.scalars(
                self.scoped().where(CashSession.id == till_id).with_for_update()
            )
        ).first()

    async def list_page(
        self, *, limit: int | None = None, after: uuid.UUID | None = None
    ) -> Sequence[CashSession]:
        """Newest first; the UUIDv7 id is the cursor."""
        query = self.scoped()
        if after is not None:
            query = query.where(CashSession.id < after)
        result = await self.session.scalars(
            query.order_by(CashSession.id.desc()).limit(page_size(limit))
        )
        return result.all()

    async def totals_for(self, till_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, TillTotals]:
        """Cash taken, paid out and adjusted, per till, in two statements for any number of tills.

        Cash taken is every successful cash payment posted to the till, refunds included as the
        negatives they are. Both sums are bounded by the till, on `ix_payment_cash_session` and
        `ix_cash_movement_session` (G-13 item 6).
        """
        totals = {till_id: TillTotals() for till_id in till_ids}
        if not till_ids:
            return totals
        taken = await self.session.execute(
            select(Payment.cash_session_id, func.sum(Payment.amount))
            .join(
                Invoice,
                and_(
                    Invoice.id == Payment.invoice_id,
                    Invoice.restaurant_id == Payment.restaurant_id,
                ),
            )
            .where(
                Payment.restaurant_id == self.scope.restaurant_id,
                Payment.cash_session_id.in_(till_ids),
                Payment.method == PaymentMethod.CASH,
                Payment.status == PaymentStatus.SUCCESS,
                # Cash on an invoice cancelled as issued in error is settled again against the
                # right order; counting it here too would expect the same notes twice.
                Invoice.status == InvoiceStatus.ISSUED,
            )
            .group_by(Payment.cash_session_id)
        )
        for till_id, amount in taken.tuples().all():
            if till_id is not None:
                totals[till_id] = replace(totals[till_id], cash_taken=Decimal(str(amount)))
        moved = await self.session.execute(
            select(CashMovement.cash_session_id, CashMovement.type, func.sum(CashMovement.amount))
            .where(
                CashMovement.restaurant_id == self.scope.restaurant_id,
                CashMovement.cash_session_id.in_(till_ids),
            )
            .group_by(CashMovement.cash_session_id, CashMovement.type)
        )
        for till_id, kind, amount in moved.tuples().all():
            field = "payouts" if kind == CashMovementType.PAYOUT else "adjustments"
            totals[till_id] = replace(totals[till_id], **{field: Decimal(str(amount))})
        return totals

    async def counts_of(self, till_id: uuid.UUID) -> Sequence[CashCount]:
        result = await self.session.scalars(
            select(CashCount)
            .where(
                CashCount.restaurant_id == self.scope.restaurant_id,
                CashCount.cash_session_id == till_id,
            )
            .order_by(CashCount.denomination.desc())
        )
        return result.all()

    async def movements_of(self, till_id: uuid.UUID) -> Sequence[CashMovement]:
        result = await self.session.scalars(
            select(CashMovement)
            .where(
                CashMovement.restaurant_id == self.scope.restaurant_id,
                CashMovement.cash_session_id == till_id,
            )
            .order_by(CashMovement.id)
        )
        return result.all()


class PaymentRepository(RestaurantScopedRepository[Payment]):
    model = Payment

    async def received_on(self, invoice_id: uuid.UUID) -> Decimal:
        """Money actually received on an invoice, net of refunds already given.

        `due` is a promise to pay rather than money, so it counts for nothing here.
        """
        total = await self.session.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.restaurant_id == self.scope.restaurant_id,
                Payment.invoice_id == invoice_id,
                Payment.method != PaymentMethod.DUE,
                Payment.status == PaymentStatus.SUCCESS,
            )
        )
        return Decimal(str(total))

    async def tills_holding_cash_of(self, invoice_id: uuid.UUID) -> list[uuid.UUID]:
        """Every till an invoice's cash, or a refund of it, was posted into."""
        rows = await self.session.scalars(
            select(Payment.cash_session_id)
            .distinct()
            .where(
                Payment.restaurant_id == self.scope.restaurant_id,
                Payment.invoice_id == invoice_id,
                Payment.cash_session_id.is_not(None),
            )
        )
        return [till_id for till_id in rows.all() if till_id is not None]

    async def for_credit_note(self, credit_note_id: uuid.UUID) -> Sequence[Payment]:
        result = await self.session.scalars(
            self.scoped().where(Payment.credit_note_id == credit_note_id).order_by(Payment.id)
        )
        return result.all()

    async def for_order(self, order_id: uuid.UUID) -> Sequence[Payment]:
        result = await self.session.scalars(
            self.scoped().where(Payment.order_id == order_id).order_by(Payment.id)
        )
        return result.all()


# ------------------------------------------------------------------------------- credit notes
#
# Appended to app/repositories/orders.py by chunk H's patch, after chunk G's invoice repositories.

# Its own namespace: a credit-note lock can never collide with an invoice, order or purchase-order
# lock on the same restaurant.
_CREDIT_NOTE_LOCK_NAMESPACE = 90_001


@dataclass(frozen=True, slots=True)
class CreditedSoFar:
    """What earlier credit notes against one invoice already took off one dish."""

    quantity: int = 0
    taxable: Decimal = Decimal("0.00")
    cgst: Decimal = Decimal("0.00")
    tax: Decimal = Decimal("0.00")


class CreditNoteRepository(RestaurantScopedRepository[CreditNote]):
    model = CreditNote

    async def next_sequence(self, financial_year: str) -> int:
        """Consecutive per restaurant per year, under a lock held to commit — for the same reason
        `InvoiceRepository.next_sequence` gives. A credit note is a document with its own series
        (Rule 53), and a gap in it is the same question an invoice gap is."""
        key = f"{self.scope.restaurant_id}:{financial_year}"
        await self.session.execute(
            select(
                func.pg_advisory_xact_lock(literal(_CREDIT_NOTE_LOCK_NAMESPACE), func.hashtext(key))
            )
        )
        highest = await self.session.scalar(
            self.scoped()
            .with_only_columns(func.max(CreditNote.sequence))
            .where(CreditNote.financial_year == financial_year)
        )
        return int(highest or 0) + 1

    async def credited_so_far(self, invoice_id: uuid.UUID) -> dict[uuid.UUID, CreditedSoFar]:
        """Per dish, what earlier credit notes against this invoice took off. One statement."""
        rows = await self.session.execute(
            select(
                CreditNoteLine.order_line_id,
                func.sum(CreditNoteLine.quantity),
                func.sum(CreditNoteLine.taxable_value),
                func.sum(CreditNoteLine.cgst_amount),
                func.sum(CreditNoteLine.tax_amount),
            )
            .join(CreditNote, CreditNote.id == CreditNoteLine.credit_note_id)
            .where(
                CreditNote.invoice_id == invoice_id,
                CreditNote.restaurant_id == self.scope.restaurant_id,
                CreditNoteLine.restaurant_id == self.scope.restaurant_id,
            )
            .group_by(CreditNoteLine.order_line_id)
        )
        return {
            line_id: CreditedSoFar(
                quantity=int(quantity),
                taxable=Decimal(str(taxable)),
                cgst=Decimal(str(cgst)),
                tax=Decimal(str(tax)),
            )
            for line_id, quantity, taxable, cgst, tax in rows.tuples().all()
        }

    async def get_detail(self, credit_note_id: uuid.UUID) -> CreditNote | None:
        query = (
            self.scoped()
            .options(selectinload(CreditNote.lines))
            .where(CreditNote.id == credit_note_id)
        )
        return (await self.session.scalars(query)).first()
