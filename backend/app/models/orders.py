"""Orders, invoices, payments and the till — `docs/schema.md` §7, migration 0019.

Argued in `docs/modules/M07-orders-spec.md`. Four things in this file are load-bearing and each is
held by the database rather than by a service remembering:

**1 · A settled order does not change.** Invariant 6. A trigger refuses every change to a settled
order except voiding it, and the late kitchen timestamps a counter-service restaurant writes after
taking the money. Lines, discounts, charges, tables and modifiers cannot be added to, changed on or
removed from a final order; a settled line may only move through the kitchen; and a line is deleted
only while unsent, after which it is cancelled with a reason.

**2 · An invoice is a legal document, not a status.** Its number is gapless per restaurant per
financial year, at most sixteen characters (CGST Rules, Rule 46(b) — a CHECK here), and it survives
cancellation (GSTR-1 Table 13). It snapshots the supplier's name, address, GSTIN and FSSAI number at
issue, because a reprint must reproduce the document as issued even after the settings change.

**3 · Only a tax invoice carries tax, and only with a GSTIN on it.** A `bill_of_supply` — what a
composition restaurant issues — has zero CGST and SGST by CHECK, and a `tax_invoice` without a
supplier GSTIN is refused. The product will not print what the Jaipur bill printed.

**4 · A refund is a negative payment that references a credit note.** `docs/schema.md` eliminated a
refund table; `docs/security.md` says refunds are credit notes. Both hold: the cash is a `Payment`
with a negative amount, the tax document is a `CreditNote`, and a CHECK refuses a negative payment
that references none.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    CashMovementType,
    CashSessionStatus,
    ChargeType,
    DiscountType,
    DocumentType,
    IdempotencyState,
    InvoiceStatus,
    OrderChannel,
    OrderLineStatus,
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentStatus,
    TaxRegime,
)
from app.models.base import Base, TimestampedUUIDMixin
from app.models.identity import Employee
from app.models.setup import RestaurantTable


def _in(column: str, values: type[Any]) -> str:
    return f"{column} IN ({', '.join(repr(member.value) for member in values)})"


# The statuses from which nothing changes. Kept beside the models so the triggers in 0019 and the
# service read one definition.
FINAL_ORDER_STATUSES = frozenset({OrderStatus.SETTLED, OrderStatus.CANCELLED, OrderStatus.VOIDED})


def _uuid() -> Any:
    return postgresql.UUID(as_uuid=True)


class CashSession(TimestampedUUIDMixin, Base):
    """One till, from float to count. **Expected cash is never stored** (`docs/modules.md`).

    Expected is derived: the opening float, plus cash payments inside the session, minus payouts
    inside it. That is stable after close because payments and movements are append-only and a later
    refund posts to the session in which it happens. The *variance* is stored at close and never
    corrected away — a correction is a `CashMovement` of type `adjustment`.
    """

    __tablename__ = "cash_session"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_cash_session_id_restaurant"),
        CheckConstraint(_in("status", CashSessionStatus), name="ck_cash_session_status"),
        CheckConstraint("opening_float >= 0", name="ck_cash_session_float"),
        CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL AND closed_by IS NOT NULL "
            "AND counted_cash IS NOT NULL AND variance IS NOT NULL)",
            name="ck_cash_session_closed_complete",
        ),
        # One open till per restaurant. Two counters is a real thing and out of scope for month 1.
        Index(
            "uq_cash_session_one_open",
            "restaurant_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_cash_session_restaurant_date", "restaurant_id", "business_date"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default=CashSessionStatus.OPEN)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    opened_by: Mapped[uuid.UUID] = mapped_column(_uuid(), ForeignKey("employee.id"), nullable=False)
    opening_float: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    counted_cash: Mapped[object | None] = mapped_column(Numeric(12, 2))
    variance: Mapped[object | None] = mapped_column(Numeric(12, 2))
    # No foreign key: `shift` is M12's. Nullable so M07 does not wait on a roster.
    shift_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())


class Order(TimestampedUUIDMixin, Base):
    """What a table, or a takeaway customer, is having. Never deleted (ADR 0008)."""

    __tablename__ = "order"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_order_id_restaurant"),
        # Short, per business day — "table 6, order 42" is what a waiter calls out.
        UniqueConstraint(
            "restaurant_id", "business_date", "order_number", name="uq_order_number_per_day"
        ),
        ForeignKeyConstraint(
            ["parent_order_id", "restaurant_id"],
            ["order.id", "order.restaurant_id"],
            name="fk_order_parent_tenant",
        ),
        CheckConstraint(_in("type", OrderType), name="ck_order_type"),
        CheckConstraint(_in("channel", OrderChannel), name="ck_order_channel"),
        CheckConstraint(_in("status", OrderStatus), name="ck_order_status"),
        CheckConstraint("covers IS NULL OR covers > 0", name="ck_order_covers"),
        CheckConstraint(
            "subtotal >= 0 AND discount_total >= 0 AND charge_total >= 0 AND tax_total >= 0 "
            "AND grand_total >= 0",
            name="ck_order_money_not_negative",
        ),
        CheckConstraint("discount_total <= subtotal", name="ck_order_discount_within_subtotal"),
        CheckConstraint("round_off BETWEEN -0.50 AND 0.50", name="ck_order_round_off"),
        CheckConstraint(
            "status NOT IN ('cancelled', 'voided') OR cancel_reason IS NOT NULL",
            name="ck_order_final_has_reason",
        ),
        Index("ix_order_restaurant_date", "restaurant_id", "business_date"),
        # The live-orders index: the table map and the waiter's list read nothing else.
        Index(
            "ix_order_live",
            "restaurant_id",
            "status",
            postgresql_where=text("status IN ('open', 'sent', 'served')"),
        ),
        Index("ix_order_customer", "restaurant_id", "customer_id"),
        # M10: a guest exchanging the QR on their bill for a session. Unique because the raw token
        # is 24 random bytes and its hash identifies exactly one order.
        Index("ix_order_guest_token_hash", "guest_token_hash", unique=True),
        CheckConstraint(
            "(guest_token_hash IS NULL) = (guest_token_expires_at IS NULL)",
            name="ck_order_guest_token_pair",
        ),
        Index("ix_order_waiter_date", "restaurant_id", "waiter_employee_id", "business_date"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    order_number: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False, default=OrderChannel.POS)
    external_order_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=OrderStatus.OPEN)
    # M07 left this a bare column with a note saying "`customer` is M10's — the same arrangement
    # M05 used for `supplier_id`". This is M10, and migration 0036 adds the foreign key.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("customer.id"))
    waiter_employee_id: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    covers: Mapped[int | None] = mapped_column(SmallInteger)
    # Split lineage: an order created by splitting another names where its lines came from.
    parent_order_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    # The five timestamps G-13 item 1 asked for. None of them can be reconstructed afterwards.
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bill_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # M10: the capability the QR on the bill carries, **stored hashed** — `hash_refresh_token`'s
    # reasoning applied to a second bearer token, so a stolen dump yields no live ones. Minted when
    # the bill is printed, returned once to the client that draws the QR, and never readable again;
    # a reprint mints a new one and the old photograph stops working.
    guest_token_hash: Mapped[str | None] = mapped_column(Text)
    guest_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    subtotal: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    charge_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    round_off: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    grand_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    # Frozen at settlement from the cost engine. Deliberately not the FEFO batch cost the
    # consumption movements carry — one is what the recipe says, the other what the shelf cost.
    theoretical_food_cost: Mapped[object | None] = mapped_column(Numeric(12, 2))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    # ADR 0010. Two waiters, one table: last-write-wins loses a dish.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    lines: Mapped[list[OrderLine]] = relationship(
        back_populates="order", lazy="raise", order_by="OrderLine.seq"
    )
    discounts: Mapped[list[OrderDiscount]] = relationship(lazy="raise")
    charges: Mapped[list[OrderCharge]] = relationship(lazy="raise")
    tables: Mapped[list[OrderTable]] = relationship(lazy="raise")
    # Who is serving the table, loaded wherever an order is shown (waiter assignment, 2026-09-14).
    # `foreign_keys` because `voided_by` points at `employee` too.
    waiter: Mapped[Employee | None] = relationship(foreign_keys=[waiter_employee_id], lazy="raise")

    # ADR 0010, enforced by the ORM: every UPDATE is `... WHERE version = :loaded` and bumps it, so
    # a stale write fails instead of silently winning. `DeclarativeBase` already types this
    # attribute, which is why it cannot carry the `ClassVar` annotation ruff would otherwise want.
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class OrderTable(TimestampedUUIDMixin, Base):
    """Which tables an order occupies. A join rather than one column (finding S9): a party of twelve
    pushes three tables together, and a single column cannot say so."""

    __tablename__ = "order_table"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "restaurant_id"],
            ["order.id", "order.restaurant_id"],
            name="fk_order_table_order_tenant",
        ),
        ForeignKeyConstraint(
            ["restaurant_table_id", "restaurant_id"],
            ["restaurant_table.id", "restaurant_table.restaurant_id"],
            name="fk_order_table_table_tenant",
        ),
        UniqueConstraint("order_id", "restaurant_table_id", name="uq_order_table_pair"),
        Index(
            "uq_order_table_one_primary",
            "order_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        Index("ix_order_table_table", "restaurant_id", "restaurant_table_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    restaurant_table_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Added by M08. The waiter's screens resolve a table id against the floor plan they have
    # already loaded; a kitchen display has no floor plan and no reason to fetch one, and "T6" is
    # what a runner needs in order to carry the food anywhere. `viewonly`, because an order's
    # tables are changed through `OrderService`, never through this.
    restaurant_table: Mapped[RestaurantTable] = relationship(
        primaryjoin="and_(OrderTable.restaurant_table_id == RestaurantTable.id, "
        "OrderTable.restaurant_id == RestaurantTable.restaurant_id)",
        foreign_keys="[OrderTable.restaurant_table_id, OrderTable.restaurant_id]",
        viewonly=True,
        lazy="raise",
    )


class OrderLine(TimestampedUUIDMixin, Base):
    """One dish on an order, with its price and tax copied rather than joined.

    Tax is stored per line (ADR 0004), and for a `gst` line CGST and SGST are computed independently
    on the taxable value, so they are always equal — held by CHECK. The rate is snapshotted when the
    line is added and re-frozen at settlement from Section 14's median-of-three date.
    """

    __tablename__ = "order_line"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_order_line_id_restaurant"),
        ForeignKeyConstraint(
            ["order_id", "restaurant_id"],
            ["order.id", "order.restaurant_id"],
            name="fk_order_line_order_tenant",
        ),
        ForeignKeyConstraint(
            ["menu_item_variant_id", "restaurant_id"],
            ["menu_item_variant.id", "menu_item_variant.restaurant_id"],
            name="fk_order_line_variant_tenant",
        ),
        ForeignKeyConstraint(
            ["recipe_id", "restaurant_id"],
            ["recipe.id", "recipe.restaurant_id"],
            name="fk_order_line_recipe_tenant",
        ),
        ForeignKeyConstraint(
            ["tax_group_id", "restaurant_id"],
            ["tax_group.id", "tax_group.restaurant_id"],
            name="fk_order_line_tax_group_tenant",
        ),
        CheckConstraint("quantity > 0", name="ck_order_line_quantity"),
        CheckConstraint(_in("status", OrderLineStatus), name="ck_order_line_status"),
        CheckConstraint(_in("tax_regime", TaxRegime), name="ck_order_line_regime"),
        CheckConstraint(
            "unit_price >= 0 AND line_subtotal >= 0 AND line_discount >= 0 AND taxable_value >= 0 "
            "AND cgst_amount >= 0 AND sgst_amount >= 0 AND tax_amount >= 0 AND line_total >= 0",
            name="ck_order_line_money_not_negative",
        ),
        CheckConstraint("line_discount <= line_subtotal", name="ck_order_line_discount_within"),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 1", name="ck_order_line_rate_fraction"),
        CheckConstraint("line_total = taxable_value + tax_amount", name="ck_order_line_total"),
        # Decision 4, held by the database: a GST line's two halves are equal and sum to its tax; a
        # non-GST line is never split.
        CheckConstraint(
            "(tax_regime = 'gst' AND cgst_amount = sgst_amount "
            "AND tax_amount = cgst_amount + sgst_amount) "
            "OR (tax_regime = 'non_gst' AND cgst_amount = 0 AND sgst_amount = 0)",
            name="ck_order_line_gst_split",
        ),
        CheckConstraint(
            "status <> 'cancelled' OR cancel_reason IS NOT NULL",
            name="ck_order_line_cancel_reason",
        ),
        Index("ix_order_line_order", "order_id"),
        Index("ix_order_line_variant", "restaurant_id", "menu_item_variant_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    menu_item_variant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    # The recipe VERSION this line was costed against, frozen at settlement.
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    quantity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Copied, not joined: menu prices change and a past bill must not.
    unit_price: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    # (unit_price + the modifiers' price deltas) x quantity.
    line_subtotal: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    line_discount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_group_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    tax_regime: Mapped[str] = mapped_column(Text, nullable=False, default=TaxRegime.GST)
    tax_rate: Mapped[object] = mapped_column(Numeric(6, 4), nullable=False)
    # The rate's `is_inclusive`, copied with it. A reprice has to know whether the line's price
    # already contains its tax, and the rate row may have changed since.
    tax_inclusive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    taxable_value: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    cgst_amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    sgst_amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    theoretical_unit_cost: Mapped[object | None] = mapped_column(Numeric(14, 6))
    status: Mapped[str] = mapped_column(Text, nullable=False, default=OrderLineStatus.PENDING)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    special_instructions: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    order: Mapped[Order] = relationship(back_populates="lines", lazy="raise")
    modifiers: Mapped[list[OrderLineModifier]] = relationship(
        lazy="raise", cascade="all, delete-orphan"
    )


class OrderLineModifier(TimestampedUUIDMixin, Base):
    """ "Extra cheese", with its price copied and its recipe consumed at settlement."""

    __tablename__ = "order_line_modifier"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_line_id", "restaurant_id"],
            ["order_line.id", "order_line.restaurant_id"],
            name="fk_order_line_modifier_line_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["modifier_id", "restaurant_id"],
            ["modifier.id", "modifier.restaurant_id"],
            name="fk_order_line_modifier_modifier_tenant",
        ),
        ForeignKeyConstraint(
            ["recipe_id", "restaurant_id"],
            ["recipe.id", "recipe.restaurant_id"],
            name="fk_order_line_modifier_recipe_tenant",
        ),
        UniqueConstraint("order_line_id", "modifier_id", name="uq_order_line_modifier_pair"),
        Index("ix_order_line_modifier_line", "order_line_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    order_line_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    modifier_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    # May be negative: "no rice" can be a discount (M03).
    price_delta: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())


class OrderDiscount(TimestampedUUIDMixin, Base):
    """A discount or a comp, and **always** who authorised it (`docs/security.md` A04).

    `amount` is the rupee figure actually taken off, frozen. For a percentage or a comp that is
    derived from `rate`; for a flat discount it is `flat_amount`. Applied before tax and apportioned
    to the lines by largest remainder, because CGST Act s.15(3)(a) excludes a discount recorded on
    the invoice from taxable value.
    """

    __tablename__ = "order_discount"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "restaurant_id"],
            ["order.id", "order.restaurant_id"],
            name="fk_order_discount_order_tenant",
        ),
        ForeignKeyConstraint(
            ["order_line_id", "restaurant_id"],
            ["order_line.id", "order_line.restaurant_id"],
            name="fk_order_discount_line_tenant",
        ),
        CheckConstraint(_in("type", DiscountType), name="ck_order_discount_type"),
        CheckConstraint(
            "(type = 'flat') = (flat_amount IS NOT NULL) AND (type <> 'flat') = (rate IS NOT NULL)",
            name="ck_order_discount_shape",
        ),
        CheckConstraint("rate IS NULL OR (rate > 0 AND rate <= 1)", name="ck_order_discount_rate"),
        CheckConstraint("flat_amount IS NULL OR flat_amount > 0", name="ck_order_discount_flat"),
        CheckConstraint("amount >= 0", name="ck_order_discount_amount"),
        CheckConstraint("amount <= authorised_amount", name="ck_order_discount_within_authorised"),
        Index("ix_order_discount_order", "order_id"),
        Index("ix_order_discount_authoriser", "restaurant_id", "authorised_by"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    # NULL for an order-level discount.
    order_line_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    type: Mapped[str] = mapped_column(Text, nullable=False)
    rate: Mapped[object | None] = mapped_column(Numeric(6, 4))
    flat_amount: Mapped[object | None] = mapped_column(Numeric(12, 2))
    amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    # The rupee figure its authoriser approved. `amount` may shrink below it and never exceed it.
    authorised_amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # Comps need a name. Always. Seed signal 11 is unanswerable without it.
    authorised_by: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )


class OrderCharge(TimestampedUUIDMixin, Base):
    """Packaging, delivery, or an *optional* service charge (finding S7).

    `tax_group_id` is nullable because whether GST applies to a service charge is unsettled; a
    restaurant that enables one decides its treatment. Packaging is part of the composite supply and
    takes the restaurant's own tax group.
    """

    __tablename__ = "order_charge"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "restaurant_id"],
            ["order.id", "order.restaurant_id"],
            name="fk_order_charge_order_tenant",
        ),
        ForeignKeyConstraint(
            ["tax_group_id", "restaurant_id"],
            ["tax_group.id", "tax_group.restaurant_id"],
            name="fk_order_charge_tax_group_tenant",
        ),
        CheckConstraint(_in("type", ChargeType), name="ck_order_charge_type"),
        # CCPA guidelines, 4 Jul 2022, upheld 28 Mar 2025: never mandatory.
        CheckConstraint(
            "type <> 'service_charge' OR is_optional", name="ck_order_charge_service_optional"
        ),
        CheckConstraint(
            "amount >= 0 AND cgst_amount >= 0 AND sgst_amount >= 0 AND tax_amount >= 0",
            name="ck_order_charge_money_not_negative",
        ),
        CheckConstraint(
            "cgst_amount = sgst_amount AND tax_amount = cgst_amount + sgst_amount",
            name="ck_order_charge_gst_split",
        ),
        CheckConstraint(
            "tax_group_id IS NOT NULL OR tax_amount = 0", name="ck_order_charge_untaxed"
        ),
        Index("ix_order_charge_order", "order_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    tax_group_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    tax_rate: Mapped[object | None] = mapped_column(Numeric(6, 4))
    cgst_amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    sgst_amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Invoice(TimestampedUUIDMixin, Base):
    """The legal document. One per order, numbered at settlement and never before."""

    __tablename__ = "invoice"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_invoice_id_restaurant"),
        UniqueConstraint("order_id", name="uq_invoice_one_per_order"),
        UniqueConstraint(
            "restaurant_id", "financial_year", "sequence", name="uq_invoice_sequence_per_fy"
        ),
        UniqueConstraint("restaurant_id", "invoice_number", name="uq_invoice_number"),
        ForeignKeyConstraint(
            ["order_id", "restaurant_id"],
            ["order.id", "order.restaurant_id"],
            name="fk_invoice_order_tenant",
        ),
        CheckConstraint(_in("document_type", DocumentType), name="ck_invoice_document_type"),
        CheckConstraint(_in("status", InvoiceStatus), name="ck_invoice_status"),
        # CGST Rules, Rule 46(b): not exceeding sixteen characters.
        CheckConstraint("char_length(invoice_number) <= 16", name="ck_invoice_number_length"),
        CheckConstraint("financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="ck_invoice_fy_format"),
        CheckConstraint("sequence > 0", name="ck_invoice_sequence"),
        # Decision 3: a bill of supply collects no tax (CGST Act s.10).
        CheckConstraint(
            "document_type <> 'bill_of_supply' OR (cgst_total = 0 AND sgst_total = 0)",
            name="ck_invoice_bill_of_supply_untaxed",
        ),
        # Rule 46(a): a tax invoice carries the supplier's GSTIN.
        CheckConstraint(
            "document_type <> 'tax_invoice' OR supplier_gstin IS NOT NULL",
            name="ck_invoice_tax_invoice_has_gstin",
        ),
        CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL AND cancel_reason IS NOT NULL)",
            name="ck_invoice_cancel_complete",
        ),
        CheckConstraint(
            "taxable_total >= 0 AND cgst_total >= 0 AND sgst_total >= 0 AND non_gst_tax_total >= 0 "
            "AND discount_total >= 0 AND charge_total >= 0 AND grand_total >= 0",
            name="ck_invoice_money_not_negative",
        ),
        CheckConstraint("round_off BETWEEN -0.50 AND 0.50", name="ck_invoice_round_off"),
        Index("ix_invoice_restaurant_date", "restaurant_id", "invoice_date"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    financial_year: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    invoice_number: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=InvoiceStatus.ISSUED)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The calendar date of issue in the restaurant's timezone, NOT business_date. A bill at 01:30
    # on 1 April is business day 31 March and the new financial year's series.
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Snapshotted at issue: a reprint reproduces the document as issued.
    supplier_name: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_address: Mapped[dict[str, Any] | None] = mapped_column(postgresql.JSONB)
    supplier_gstin: Mapped[str | None] = mapped_column(Text)
    fssai_licence: Mapped[str | None] = mapped_column(Text)
    # Rule 46(d), for a registered recipient; also what e-invoicing will need.
    recipient_name: Mapped[str | None] = mapped_column(Text)
    recipient_gstin: Mapped[str | None] = mapped_column(Text)
    recipient_address: Mapped[str | None] = mapped_column(Text)
    sac_code: Mapped[str] = mapped_column(Text, nullable=False, default="996331")
    taxable_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    cgst_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    sgst_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    non_gst_tax_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    charge_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    round_off: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    grand_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))
    # E-invoicing (IRN) is out of scope for month 1; modelled so it needs no schema change later.
    irn: Mapped[str | None] = mapped_column(Text)
    irn_ack_no: Mapped[str | None] = mapped_column(Text)
    irn_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CreditNote(TimestampedUUIDMixin, Base):
    """A reduction after an invoice was issued (CGST Act s.34; Rule 53). Its own series. Moves no
    cash on its own — a refund is a negative `Payment` that references this row."""

    __tablename__ = "credit_note"
    __table_args__ = (
        UniqueConstraint("id", "restaurant_id", name="uq_credit_note_id_restaurant"),
        UniqueConstraint(
            "restaurant_id", "financial_year", "sequence", name="uq_credit_note_sequence_per_fy"
        ),
        UniqueConstraint("restaurant_id", "credit_note_number", name="uq_credit_note_number"),
        ForeignKeyConstraint(
            ["invoice_id", "restaurant_id"],
            ["invoice.id", "invoice.restaurant_id"],
            name="fk_credit_note_invoice_tenant",
        ),
        CheckConstraint(
            "char_length(credit_note_number) <= 16", name="ck_credit_note_number_length"
        ),
        CheckConstraint("financial_year ~ '^[0-9]{4}-[0-9]{2}$'", name="ck_credit_note_fy_format"),
        CheckConstraint("sequence > 0", name="ck_credit_note_sequence"),
        CheckConstraint(
            "taxable_total >= 0 AND cgst_total >= 0 AND sgst_total >= 0 AND non_gst_tax_total >= 0 "
            "AND grand_total > 0",
            name="ck_credit_note_money",
        ),
        Index("ix_credit_note_invoice", "invoice_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    financial_year: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    credit_note_number: Mapped[str] = mapped_column(Text, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note_date: Mapped[date] = mapped_column(Date, nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    issued_by: Mapped[uuid.UUID] = mapped_column(_uuid(), ForeignKey("employee.id"), nullable=False)
    taxable_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    cgst_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    sgst_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    non_gst_tax_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    grand_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)

    lines: Mapped[list[CreditNoteLine]] = relationship(lazy="raise")


class CreditNoteLine(TimestampedUUIDMixin, Base):
    """Which items a credit note reverses, and the tax with them: the cold soup, not the bill."""

    __tablename__ = "credit_note_line"
    __table_args__ = (
        ForeignKeyConstraint(
            ["credit_note_id", "restaurant_id"],
            ["credit_note.id", "credit_note.restaurant_id"],
            name="fk_credit_note_line_note_tenant",
        ),
        ForeignKeyConstraint(
            ["order_line_id", "restaurant_id"],
            ["order_line.id", "order_line.restaurant_id"],
            name="fk_credit_note_line_order_line_tenant",
        ),
        UniqueConstraint("credit_note_id", "order_line_id", name="uq_credit_note_line_pair"),
        CheckConstraint("quantity > 0", name="ck_credit_note_line_quantity"),
        CheckConstraint(
            "taxable_value >= 0 AND cgst_amount >= 0 AND sgst_amount >= 0 AND tax_amount >= 0 "
            "AND line_total >= 0",
            name="ck_credit_note_line_money",
        ),
        CheckConstraint(
            "line_total = taxable_value + tax_amount", name="ck_credit_note_line_total"
        ),
        Index("ix_credit_note_line_note", "credit_note_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    credit_note_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    order_line_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    quantity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    taxable_value: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    cgst_amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    sgst_amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_total: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)


class Payment(TimestampedUUIDMixin, Base):
    """Money that moved. Append-only. **A refund is negative, and names its credit note.**"""

    __tablename__ = "payment"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "restaurant_id"],
            ["order.id", "order.restaurant_id"],
            name="fk_payment_order_tenant",
        ),
        ForeignKeyConstraint(
            ["invoice_id", "restaurant_id"],
            ["invoice.id", "invoice.restaurant_id"],
            name="fk_payment_invoice_tenant",
        ),
        ForeignKeyConstraint(
            ["credit_note_id", "restaurant_id"],
            ["credit_note.id", "credit_note.restaurant_id"],
            name="fk_payment_credit_note_tenant",
        ),
        ForeignKeyConstraint(
            ["cash_session_id", "restaurant_id"],
            ["cash_session.id", "cash_session.restaurant_id"],
            name="fk_payment_cash_session_tenant",
        ),
        CheckConstraint(_in("method", PaymentMethod), name="ck_payment_method"),
        CheckConstraint(_in("status", PaymentStatus), name="ck_payment_status"),
        CheckConstraint("amount <> 0", name="ck_payment_amount_not_zero"),
        CheckConstraint("tip_amount >= 0", name="ck_payment_tip"),
        # Decision 2, held by the database: the cash going back is always tied to the tax document.
        CheckConstraint(
            "amount > 0 OR credit_note_id IS NOT NULL", name="ck_payment_refund_has_credit_note"
        ),
        Index("ix_payment_restaurant_date", "restaurant_id", "business_date"),
        Index("ix_payment_order", "order_id"),
        Index("ix_payment_cash_session", "restaurant_id", "cash_session_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    credit_note_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    cash_session_id: Mapped[uuid.UUID | None] = mapped_column(_uuid())
    method: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    # Outside taxable value; attributed to the order's waiter (M17 `tips_received`).
    tip_amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    reference: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=PaymentStatus.SUCCESS)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    received_by: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))


class CashCount(TimestampedUUIDMixin, Base):
    """The denominations counted at close. Written once."""

    __tablename__ = "cash_count"
    __table_args__ = (
        ForeignKeyConstraint(
            ["cash_session_id", "restaurant_id"],
            ["cash_session.id", "cash_session.restaurant_id"],
            name="fk_cash_count_session_tenant",
        ),
        UniqueConstraint("cash_session_id", "denomination", name="uq_cash_count_denomination"),
        CheckConstraint("denomination > 0", name="ck_cash_count_denomination"),
        CheckConstraint("quantity >= 0", name="ck_cash_count_quantity"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    cash_session_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    denomination: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)


class CashMovement(TimestampedUUIDMixin, Base):
    """Cash out of the till that is not a refund: a payout, or a post-close correction.

    `docs/modules.md` subtracts payouts from expected cash and nothing modelled one. ₹300 handed to
    a vegetable vendor is the most ordinary cash event in the country. One table for both types
    because they have one shape; two tables would be two places to sum.
    """

    __tablename__ = "cash_movement"
    __table_args__ = (
        ForeignKeyConstraint(
            ["cash_session_id", "restaurant_id"],
            ["cash_session.id", "cash_session.restaurant_id"],
            name="fk_cash_movement_session_tenant",
        ),
        CheckConstraint(_in("type", CashMovementType), name="ck_cash_movement_type"),
        CheckConstraint("amount <> 0", name="ck_cash_movement_amount_not_zero"),
        CheckConstraint("type <> 'payout' OR amount > 0", name="ck_cash_movement_payout_positive"),
        Index("ix_cash_movement_session", "restaurant_id", "cash_session_id"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    cash_session_id: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("employee.id"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)


class IdempotencyKey(TimestampedUUIDMixin, Base):
    """ADR 0010. The waiter double-tapped "Settle".

    Written in the same transaction as the effect, so a duplicate blocks on the unique index until
    the first finishes and then replays its stored response, and a rolled-back first attempt takes
    its key row with it, which is what lets an honest retry through.
    """

    __tablename__ = "idempotency_key"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "key", name="uq_idempotency_key_per_restaurant"),
        CheckConstraint(_in("state", IdempotencyState), name="ck_idempotency_key_state"),
        CheckConstraint("char_length(key) BETWEEN 16 AND 128", name="ck_idempotency_key_length"),
        Index("ix_idempotency_key_expires", "expires_at"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("restaurant.id"), nullable=False
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int | None] = mapped_column(SmallInteger)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(postgresql.JSONB)
    state: Mapped[str] = mapped_column(Text, nullable=False, default=IdempotencyState.IN_PROGRESS)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_employee_id: Mapped[uuid.UUID | None] = mapped_column(_uuid(), ForeignKey("employee.id"))


__all__ = [
    "FINAL_ORDER_STATUSES",
    "CashCount",
    "CashMovement",
    "CashSession",
    "CreditNote",
    "CreditNoteLine",
    "IdempotencyKey",
    "Invoice",
    "Order",
    "OrderCharge",
    "OrderDiscount",
    "OrderLine",
    "OrderLineModifier",
    "OrderTable",
    "Payment",
]
