"""The floor, the kitchen stations and the tax rates — `docs/schema.md` §2.

The first tables in this product owned by a *restaurant* rather than an organization. An employee is
employed by the company and can work at two branches; a table belongs to one floor and cannot. That
difference is why `RestaurantScopedRepository` exists as a separate class from the organization-
scoped one, and these are its first users.

Two of these are ordinary master data and two are not:

- `dining_area` and `station` are lookups with an order. `seq` exists because a floor plan and a
  kitchen pass both have a left-to-right that matters to the people reading them.
- `restaurant_table` carries live state (`status`), which makes it the one row here that changes
  during service rather than during setup.
- `tax_group` and `tax_rate` are the closest thing in this module to a legal document, and they are
  two tables because a tax group has an **identity** separate from what it currently charges. The
  group is "GST 5% (restaurant, no ITC)", code `GST5`, and it exists once. The rates beneath it are
  effective-dated: a change is a new `tax_rate` row and the old one keeps its dates (ADR 0004, M02
  spec decision 2). A menu item references the *group*; the rate is resolved by business date, so
  nothing needs repointing when GST moves (M03 spec decision 1).

Everything here is deactivated and never deleted (ADR 0008): a table that hosted an order last year
must still resolve when that order is read.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import TableStatus
from app.models.base import Base, TimestampedUUIDMixin

_TABLE_STATUSES = ", ".join(f"'{member.value}'" for member in TableStatus)


class DiningArea(TimestampedUUIDMixin, Base):
    """A named section of the floor — AC Hall, Terrace, Garden.

    More load-bearing than it looks: `shift_assignment.dining_area_id` is what makes an "assist"
    derivable in M17 (ADR 0011). An order taken at a table in another person's section *is* someone
    helping a colleague, and deriving it means nobody has to remember to log it.
    """

    __tablename__ = "dining_area"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "name", name="uq_dining_area_restaurant_name"),
        Index("ix_dining_area_restaurant_seq", "restaurant_id", "seq"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Display order. A floor plan has a left-to-right that means something to the person reading it,
    # and alphabetical is not it.
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RestaurantTable(TimestampedUUIDMixin, Base):
    """One table on the floor.

    `restaurant_table`, not `table` — `table` is reserved in SQL, and a model named after a reserved
    word produces errors that read as syntax problems rather than naming ones.
    """

    __tablename__ = "restaurant_table"
    __table_args__ = (
        # "T4" is what staff say out loud and what prints on a KOT. Unique per restaurant, because
        # two branches both having a T4 is normal.
        UniqueConstraint("restaurant_id", "code", name="uq_restaurant_table_code"),
        CheckConstraint(f"status IN ({_TABLE_STATUSES})", name="ck_restaurant_table_status"),
        CheckConstraint("seats > 0", name="ck_restaurant_table_seats_positive"),
        # The hot path in M07: "what is free right now?", asked every time a waiter opens the map.
        Index("ix_restaurant_table_restaurant_status", "restaurant_id", "status"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    dining_area_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("dining_area.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    seats: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Live state, unlike everything else in this module. `reserved` is set by hand by a manager
    # taking a walk-in booking (M02 spec decision 3); there is no reservation system behind it and
    # it does not pretend to be one.
    status: Mapped[str] = mapped_column(Text, nullable=False, default=TableStatus.FREE)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Station(TimestampedUUIDMixin, Base):
    """A kitchen section a ticket is routed to — tandoor, main kitchen, chinese, cold, bar.

    `code` is a contract, not free text: `seed/menu.yaml` already routes dishes by these values and
    M08 will render one column per station. Renaming a code orphans that routing, which is why the
    name is editable and the code is not.
    """

    __tablename__ = "station"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "code", name="uq_station_restaurant_code"),
        Index("ix_station_restaurant_seq", "restaurant_id", "seq"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TaxGroup(TimestampedUUIDMixin, Base):
    """A tax class a menu item belongs to. One row, for as long as the restaurant charges it.

    "GST 5% (restaurant, no ITC)" is a *group*; the five percent it charges this year is a
    `TaxRate` beneath it. The distinction is not pedantry — `menu_item_variant.tax_group_id`
    references this row, so a rate change must not move it. Point a dish at a rate row and the
    first GST revision leaves every dish on the menu pointing at a closed period.

    `code` is the stable key (`GST5`), immutable once created, and the one `seed/operations.yaml`
    has always carried. `name` is a label and may be edited freely: the exclusion constraint that
    keeps two live rates apart now keys on this row's id rather than on its display string, so
    renaming a group can no longer change which rates are considered the same rate.
    """

    __tablename__ = "tax_group"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "code", name="uq_tax_group_restaurant_code"),
        # The target of TaxRate's composite foreign key. It makes "a rate belongs to the same
        # restaurant as its group" a database guarantee rather than something the service remembers.
        UniqueConstraint("id", "restaurant_id", name="uq_tax_group_id_restaurant"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    rates: Mapped[list[TaxRate]] = relationship(
        back_populates="group", order_by="TaxRate.effective_from.desc()", lazy="raise"
    )


class TaxRate(TimestampedUUIDMixin, Base):
    """What a tax group charges, and between which dates.

    **Rates change and history must not move.** The rate is copied onto every order line at order
    time and cited by an invoice, so editing this row in place would silently restate tax already
    charged and reported — which is not a data-quality problem but a filing one.

    A change is therefore a new row: the old row gets an `effective_to`, the new row an
    `effective_from`. The service refuses an `effective_from` before today's business date, because
    back-dating is how a legitimate-looking rate change reaches invoices that were already issued.
    """

    __tablename__ = "tax_rate"
    __table_args__ = (
        # NUMERIC, never float. 0.0500 is five percent (ADR 0004, CLAUDE.md invariant 3).
        CheckConstraint("rate >= 0 AND rate <= 1", name="ck_tax_rate_rate_is_a_fraction"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_tax_rate_period_is_ordered",
        ),
        ForeignKeyConstraint(
            ["tax_group_id", "restaurant_id"],
            ["tax_group.id", "tax_group.restaurant_id"],
            name="fk_tax_rate_group_same_restaurant",
        ),
        Index("ix_tax_rate_restaurant_effective", "restaurant_id", "effective_from"),
        Index("ix_tax_rate_group", "tax_group_id", "effective_from"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("restaurant.id"), nullable=False
    )
    tax_group_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    # 6,4 rather than 5,4: a rate of 1.0000 (100%) must fit, even though no jurisdiction charges it.
    rate: Mapped[object] = mapped_column(Numeric(6, 4), nullable=False)
    # Whether the menu price already contains the tax. Changes the arithmetic on every line, so it
    # belongs to the rate rather than to a setting somewhere else.
    is_inclusive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    # NULL means "still current". Set when a replacement rate supersedes this one.
    effective_to: Mapped[date | None] = mapped_column(Date)

    group: Mapped[TaxGroup] = relationship(back_populates="rates", lazy="raise")
