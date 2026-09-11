"""Queries for the restaurant's own settings, its floor, its stations and its tax rates.

The first users of `RestaurantScopedRepository`, which M01 built and never called. Every class here
starts from `scoped()`, so the `restaurant_id` filter is structural rather than remembered
(CLAUDE.md invariant 1).

**`RestaurantRepository` is the exception, and says so in its own docstring** — the `restaurant`
table has no `restaurant_id` column, it *is* the restaurant, so it cannot use the same base class
and has to state its boundary by hand. That is the one place in this module where scoping is
written out rather than inherited, which is why it is also the one place most worth reading twice.

**Ordering and cursors.** Dining areas and stations are ordered by `seq`, not by id, because a floor
plan and a kitchen pass both have a left-to-right that means something to the people reading them.
That makes the id a useless cursor on its own — two rows can share a `seq` — so the cursor is a row
comparison over `(seq, id)`, which is total and matches the `(restaurant_id, seq)` index the
migration already created. The alternative was to cap these lists and return the first hundred rows,
which is how M01 shipped a staff list that silently hid nine people.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import ColumnElement, Select, func, literal, or_, select, tuple_
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import selectinload

from app.models.setup import DiningArea, RestaurantTable, Station, TaxGroup, TaxRate
from app.models.tenancy import Restaurant
from app.repositories.base import (
    RestaurantScopedRepository,
    ScopedRepository,
    page_size,
)


class RestaurantRepository(ScopedRepository[Restaurant]):
    """The restaurant row itself.

    Not a `RestaurantScopedRepository`: that class filters `model.restaurant_id`, and this table has
    no such column. Scoping is therefore written out here — by primary key *and* by organization.

    The organization clause is redundant today, because `restaurant_id` is taken from a verified
    token and a restaurant belongs to exactly one organization. It is here anyway: it costs nothing,
    and it means a future bug that lets a token carry a mismatched pair produces no rows instead of
    another tenant's settings.
    """

    model = Restaurant

    def scoped(self) -> Select[tuple[Restaurant]]:
        return select(Restaurant).where(
            Restaurant.id == self.scope.restaurant_id,
            Restaurant.organization_id == self.scope.organization_id,
        )

    async def get(self) -> Restaurant | None:
        return (await self.session.scalars(self.scoped())).first()

    async def get_for_update(self) -> Restaurant | None:
        return (await self.session.scalars(self.scoped().with_for_update())).first()


class _SeqOrdered[ModelT: DiningArea | Station](RestaurantScopedRepository[ModelT]):
    """Shared paging for the two lists a human arranges by hand."""

    async def list_all(
        self,
        *,
        include_inactive: bool = False,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[ModelT]:
        query = self.scoped()
        if not include_inactive:
            query = query.where(self.model.is_active.is_(True))
        if after is not None:
            query = query.where(_after_in_seq_order(self.model, after, self.scope.restaurant_id))
        query = query.order_by(self.model.seq, self.model.id).limit(page_size(limit))
        return (await self.session.scalars(query)).all()

    async def next_seq(self) -> int:
        """Where a new row goes: the end of the list, not the front.

        Includes deactivated rows deliberately. Reusing a deactivated area's `seq` would make the
        two swap places in the list the moment it is reactivated.
        """
        highest = await self.session.scalar(
            select(self.model.seq)
            .where(self.model.restaurant_id == self.scope.restaurant_id)
            .order_by(self.model.seq.desc())
            .limit(1)
        )
        return 0 if highest is None else highest + 1


def _as_uuid(value: uuid.UUID) -> ColumnElement[uuid.UUID]:
    """A bound parameter with an explicit type.

    Inside `tuple_` the driver has no column to infer the type from, and asyncpg refuses a bare
    `uuid.UUID` it has not been told about.
    """
    return literal(value, type_=postgresql.UUID(as_uuid=True))


def _after_in_seq_order(
    model: type[DiningArea] | type[Station], after: uuid.UUID, restaurant_id: uuid.UUID
) -> ColumnElement[bool]:
    """`(seq, id) > (cursor.seq, cursor.id)` — the cursor for a hand-ordered list.

    A subquery rather than a second round trip, so a page is still one statement.

    **The subquery carries the tenant filter itself.** The outer `scoped()` does not reach in here,
    and an earlier version of this comment claimed a foreign cursor id "is NULL, so the page comes
    back empty" — the exact opposite of what happened. The subquery found the other tenant's row and
    returned its `seq`, so the page came back offset by a foreign ordinal. No rows crossed the
    boundary, but the *ordering key* did, and feeding ids in and watching where the page starts
    reads it back out. Found by external review; CLAUDE.md invariant 1 is explicit that a query
    without an explicit `restaurant_id` filter is the product's #1 bug class.

    Scoped, an id belonging to anyone else yields NULL, the row comparison is NULL, and the page is
    empty — which is the right answer for a cursor that means nothing here.
    """
    cursor_seq = (
        select(model.seq)
        .where(model.id == after, model.restaurant_id == restaurant_id)
        .scalar_subquery()
    )
    return tuple_(model.seq, model.id) > tuple_(cursor_seq, _as_uuid(after))


class DiningAreaRepository(_SeqOrdered[DiningArea]):
    model = DiningArea

    async def name_exists(self, name: str, *, excluding: uuid.UUID | None = None) -> bool:
        """Asked before an insert so a duplicate reads as a conflict rather than a 500.

        The unique constraint is still the authority — this is a better message, not the guarantee.
        """
        query = self.scoped().where(DiningArea.name == name.strip())
        if excluding is not None:
            query = query.where(DiningArea.id != excluding)
        return (await self.session.scalars(query)).first() is not None


class StationRepository(_SeqOrdered[Station]):
    model = Station

    async def code_exists(self, code: str, *, excluding: uuid.UUID | None = None) -> bool:
        query = self.scoped().where(Station.code == code.strip())
        if excluding is not None:
            query = query.where(Station.id != excluding)
        return (await self.session.scalars(query)).first() is not None


class RestaurantTableRepository(RestaurantScopedRepository[RestaurantTable]):
    model = RestaurantTable

    async def list_all(
        self,
        *,
        dining_area_id: uuid.UUID | None = None,
        include_inactive: bool = False,
        limit: int | None = None,
        after: uuid.UUID | None = None,
    ) -> Sequence[RestaurantTable]:
        """Ordered by code, which is what staff say out loud and what the floor map shows."""
        query = self.scoped()
        if dining_area_id is not None:
            # Scoped first, then filtered: an area id from another tenant matches nothing rather
            # than widening the query.
            query = query.where(RestaurantTable.dining_area_id == dining_area_id)
        if not include_inactive:
            query = query.where(RestaurantTable.is_active.is_(True))
        if after is not None:
            # Scoped, for the reason spelled out on `_after_in_seq_order`: unscoped, this reads
            # another tenant's table code and offsets the page by it.
            cursor_code = (
                select(RestaurantTable.code)
                .where(
                    RestaurantTable.id == after,
                    RestaurantTable.restaurant_id == self.scope.restaurant_id,
                )
                .scalar_subquery()
            )
            query = query.where(
                tuple_(RestaurantTable.code, RestaurantTable.id)
                > tuple_(cursor_code, _as_uuid(after))
            )
        query = query.order_by(RestaurantTable.code, RestaurantTable.id).limit(page_size(limit))
        return (await self.session.scalars(query)).all()

    async def code_exists(self, code: str, *, excluding: uuid.UUID | None = None) -> bool:
        query = self.scoped().where(RestaurantTable.code == code.strip())
        if excluding is not None:
            query = query.where(RestaurantTable.id != excluding)
        return (await self.session.scalars(query)).first() is not None

    async def count_in_area(self, dining_area_id: uuid.UUID) -> int:
        """Active tables in one area. Asked before deactivating the area, so the refusal can say
        how many tables are in the way rather than just refusing.

        `count(*)` rather than fetching the rows and taking `len`: the caller wants a number, and
        loading sixty ORM objects to discard all of them is the shape of query that becomes a
        problem the first time something calls it in a loop.
        """
        total = await self.session.scalar(
            select(func.count())
            .select_from(RestaurantTable)
            .where(
                RestaurantTable.restaurant_id == self.scope.restaurant_id,
                RestaurantTable.dining_area_id == dining_area_id,
                RestaurantTable.is_active.is_(True),
            )
        )
        return total or 0


class TaxGroupRepository(RestaurantScopedRepository[TaxGroup]):
    """The tax *classes* a restaurant charges. One row each, for as long as it charges them.

    Read this next to `TaxRateRepository`, which holds what each group charges and when. The split
    is M03 spec decision 1: `menu_item_variant.tax_group_id` points here, so these rows must outlive
    every rate change or the first GST revision orphans the whole menu.
    """

    model = TaxGroup

    async def list_all(
        self, *, limit: int | None = None, after: uuid.UUID | None = None
    ) -> Sequence[TaxGroup]:
        """Every group, code order, with its rates loaded.

        `selectinload` rather than a lazy relationship: the rates are what the screen is for, and
        `lazy="raise"` on the model means the alternative is not an N+1 but a crash — which is the
        point. A relationship that loads silently per row is the same bug with better manners.
        """
        query = self.scoped().options(selectinload(TaxGroup.rates))
        if after is not None:
            # Scoped. Unscoped, the subquery reads another restaurant's row to build the page
            # boundary — which leaked *when a competitor changed their GST rate* before M02's
            # review round caught the same shape on every other cursor in this file.
            cursor_code = (
                select(TaxGroup.code)
                .where(TaxGroup.id == after, TaxGroup.restaurant_id == self.scope.restaurant_id)
                .scalar_subquery()
            )
            query = query.where(
                tuple_(TaxGroup.code, TaxGroup.id) > tuple_(cursor_code, _as_uuid(after))
            )
        query = query.order_by(TaxGroup.code, TaxGroup.id)
        return (await self.session.scalars(query.limit(page_size(limit)))).all()

    async def get_with_rates(self, tax_group_id: uuid.UUID) -> TaxGroup | None:
        result = await self.session.scalars(
            self.scoped().options(selectinload(TaxGroup.rates)).where(TaxGroup.id == tax_group_id)
        )
        return result.first()

    async def code_exists(self, code: str) -> bool:
        """`code` is immutable and unique per restaurant, so this is asked once, at creation.

        The unique constraint is still the authority — this is a better message, not the guarantee.
        """
        found = await self.session.scalar(
            self.scoped()
            .with_only_columns(literal(1))
            .where(TaxGroup.code == code.strip())
            .limit(1)
        )
        return found is not None

    async def get_for_update(self, tax_group_id: uuid.UUID) -> TaxGroup | None:
        """Scoped exactly like `get`, and separate only so the intent is visible at the call site.

        Scoping reads but not writes is the version of the tenant-isolation bug that survives
        review, because the read path is the one everybody tests.
        """
        result = await self.session.scalars(
            self.scoped().where(TaxGroup.id == tax_group_id).with_for_update()
        )
        return result.first()


class TaxRateRepository(RestaurantScopedRepository[TaxRate]):
    """The effective-dated rates beneath the groups.

    Nothing here is ever updated except `effective_to`, and that only to close a period when its
    successor opens. A rate is copied onto an order line and cited by an invoice; editing one in
    place restates tax already filed.
    """

    model = TaxRate

    async def live_on(self, tax_group_id: uuid.UUID, on: date) -> TaxRate | None:
        """The rate of this group whose period covers `on`, locked.

        **This is the resolution M03 decision 1 bought.** A menu item names a group; the rate it
        charges on a given business date is this. Nothing is repointed when GST changes.

        `FOR UPDATE` because a caller is usually deciding whether to create a successor: without the
        lock two admins pressing Save together both see no conflict and both insert, and the
        exclusion constraint answers one of them with an IntegrityError rather than a readable
        refusal.

        Keyed on the group, not on a display name as M02 had it: renaming "GST 5%" to "GST 5% food"
        used to change which rows counted as the same rate, silently, with no error anywhere.
        """
        return (
            await self.session.scalars(
                self.scoped()
                .where(
                    TaxRate.tax_group_id == tax_group_id,
                    TaxRate.effective_from <= on,
                    or_(TaxRate.effective_to.is_(None), TaxRate.effective_to >= on),
                )
                .with_for_update()
            )
        ).first()

    async def list_all(
        self, *, limit: int | None = None, after: uuid.UUID | None = None
    ) -> Sequence[TaxRate]:
        """Newest first, **including superseded rows**.

        Superseded rates are not history nobody needs: an invoice from March cites the rate that was
        effective in March, and someone checking that invoice has to be able to see it. Hiding them
        would make the screen look tidy and the audit impossible.
        """
        query = self.scoped()
        if after is not None:
            cursor_from = (
                select(TaxRate.effective_from)
                .where(TaxRate.id == after, TaxRate.restaurant_id == self.scope.restaurant_id)
                .scalar_subquery()
            )
            # Descending, so "after" means "further down the page" — a smaller effective_from.
            query = query.where(
                tuple_(TaxRate.effective_from, TaxRate.id) < tuple_(cursor_from, _as_uuid(after))
            )
        query = query.order_by(TaxRate.effective_from.desc(), TaxRate.id.desc())
        return (await self.session.scalars(query.limit(page_size(limit)))).all()

    async def scheduled_on_or_after(self, tax_group_id: uuid.UUID, on: date) -> TaxRate | None:
        """The earliest rate of this group that starts on or after `on`, if any.

        Asked before inserting a rate at `on`. Periods within a group tile — closing the live rate
        the day before a new one opens is what makes them tile — so a rate already scheduled in the
        future would overlap the open-ended row this insert creates. The exclusion constraint is the
        authority and would refuse it, but an `IntegrityError` reaches the catch-all handler as a
        500 with a reference number (`docs/backlog.md`). This is the readable refusal instead, and
        it names the date in the way.
        """
        return (
            await self.session.scalars(
                self.scoped()
                .where(TaxRate.tax_group_id == tax_group_id, TaxRate.effective_from >= on)
                .order_by(TaxRate.effective_from)
            )
        ).first()

    async def get_for_update(self, tax_rate_id: uuid.UUID) -> TaxRate | None:
        result = await self.session.scalars(
            self.scoped().where(TaxRate.id == tax_rate_id).with_for_update()
        )
        return result.first()
