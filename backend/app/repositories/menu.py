"""Queries for the menu — categories, items, variants, modifiers, and the tree.

Two things here are not ordinary CRUD:

**`load_tree` is the hottest query in the product.** The waiter PWA calls `GET /menu` on every app
start, and the menu is three levels deep over a couple of hundred dishes. The obvious
implementation — load categories, then each category's items, then each item's variants — is O(N)
round trips, and it looks fine against a twelve-dish test fixture. `selectinload` turns the whole
tree into a fixed number of statements no matter how big the menu is, and
`test_menu_tree_query_count_is_flat` asserts that against a *generated 400-dish* menu, because a
test that only ever sees the seed cannot tell flat from linear.

**`MenuItemModifierGroupRepository` cannot inherit the tenant filter.** Its table has no
`restaurant_id` — both parents already carry one, and a third copy is a third thing that can
disagree (M03 spec, schema checklist Q7). So it takes the scope like every other repository and
joins through `menu_item` to apply it, rather than pretending the base class can help.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Select, delete, func, literal, select, tuple_, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import selectinload

from app.models.menu import (
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    MenuItemVariant,
    Modifier,
    ModifierGroup,
)
from app.models.tenancy import Restaurant
from app.repositories.base import (
    RestaurantScopedRepository,
    ScopedRepository,
    page_size,
)


def _as_uuid(value: uuid.UUID) -> ColumnElement[uuid.UUID]:
    """A bound parameter with an explicit type.

    Inside `tuple_` the driver has no column to infer the type from, and asyncpg refuses a bare
    `uuid.UUID` it has not been told about.
    """
    return literal(value, type_=postgresql.UUID(as_uuid=True))


class MenuCategoryRepository(RestaurantScopedRepository[MenuCategory]):
    model = MenuCategory

    async def list_all(
        self,
        *,
        limit: int | None = None,
        after: uuid.UUID | None = None,
        include_inactive: bool = True,
    ) -> Sequence[MenuCategory]:
        """`seq` order, because a menu has an order that means something to whoever reads it.

        The cursor is a row comparison over `(seq, id)` rather than the id alone: two categories can
        share a `seq`, so the id on its own is not a total order and a page boundary would repeat or
        skip rows. Same shape as `DiningAreaRepository` in M02, for the same reason.
        """
        query = self.scoped()
        if not include_inactive:
            query = query.where(MenuCategory.is_active.is_(True))
        if after is not None:
            # Scoped. An unscoped subquery here reads another restaurant's row to build the page
            # boundary, which is how M02's cursors leaked before its review round.
            cursor_seq = (
                select(MenuCategory.seq)
                .where(
                    MenuCategory.id == after,
                    MenuCategory.restaurant_id == self.scope.restaurant_id,
                )
                .scalar_subquery()
            )
            query = query.where(
                tuple_(MenuCategory.seq, MenuCategory.id) > tuple_(cursor_seq, _as_uuid(after))
            )
        query = query.order_by(MenuCategory.seq, MenuCategory.id)
        return (await self.session.scalars(query.limit(page_size(limit)))).all()

    async def code_exists(self, code: str) -> bool:
        found = await self.session.scalar(
            self.scoped()
            .with_only_columns(literal(1))
            .where(MenuCategory.code == code.strip())
            .limit(1)
        )
        return found is not None

    async def get_for_update(self, category_id: uuid.UUID) -> MenuCategory | None:
        result = await self.session.scalars(
            self.scoped().where(MenuCategory.id == category_id).with_for_update()
        )
        return result.first()

    async def next_seq(self) -> int:
        """One past the highest, so a new category lands at the end rather than at the top.

        `COALESCE(max(seq), -1) + 1` rather than `count(*)`: a deactivated category still holds its
        `seq`, so counting would reuse a number and put two categories in one position.
        """
        highest = await self.session.scalar(
            select(func.coalesce(func.max(MenuCategory.seq), -1)).where(
                MenuCategory.restaurant_id == self.scope.restaurant_id
            )
        )
        return int(highest or 0) + 1

    async def count_active_items(self, category_id: uuid.UUID) -> int:
        """Asked before deactivating a category, so the refusal can say how many dishes are in the
        way rather than merely refusing."""
        total = await self.session.scalar(
            select(func.count())
            .select_from(MenuItem)
            .where(
                MenuItem.restaurant_id == self.scope.restaurant_id,
                MenuItem.menu_category_id == category_id,
                MenuItem.is_active.is_(True),
            )
        )
        return total or 0


class MenuItemRepository(RestaurantScopedRepository[MenuItem]):
    model = MenuItem

    def _base(self, *, include_inactive: bool) -> Select[tuple[MenuItem]]:
        query = self.scoped()
        if not include_inactive:
            query = query.where(MenuItem.is_active.is_(True))
        return query

    async def list_all(
        self,
        *,
        category_id: uuid.UUID | None = None,
        limit: int | None = None,
        after: uuid.UUID | None = None,
        include_inactive: bool = True,
    ) -> Sequence[MenuItem]:
        query = self._base(include_inactive=include_inactive).options(
            selectinload(MenuItem.variants)
        )
        if category_id is not None:
            query = query.where(MenuItem.menu_category_id == category_id)
        if after is not None:
            cursor_seq = (
                select(MenuItem.seq)
                .where(MenuItem.id == after, MenuItem.restaurant_id == self.scope.restaurant_id)
                .scalar_subquery()
            )
            query = query.where(
                tuple_(MenuItem.seq, MenuItem.id) > tuple_(cursor_seq, _as_uuid(after))
            )
        query = query.order_by(MenuItem.seq, MenuItem.id)
        return (await self.session.scalars(query.limit(page_size(limit)))).all()

    async def get_with_variants(self, item_id: uuid.UUID) -> MenuItem | None:
        result = await self.session.scalars(
            self.scoped()
            .options(selectinload(MenuItem.variants), selectinload(MenuItem.modifier_links))
            .where(MenuItem.id == item_id)
        )
        return result.first()

    async def get_for_update(self, item_id: uuid.UUID) -> MenuItem | None:
        result = await self.session.scalars(
            self.scoped().where(MenuItem.id == item_id).with_for_update()
        )
        return result.first()

    async def code_exists(self, code: str) -> bool:
        found = await self.session.scalar(
            self.scoped()
            .with_only_columns(literal(1))
            .where(MenuItem.code == code.strip())
            .limit(1)
        )
        return found is not None

    async def next_seq(self, category_id: uuid.UUID) -> int:
        highest = await self.session.scalar(
            select(func.coalesce(func.max(MenuItem.seq), -1)).where(
                MenuItem.restaurant_id == self.scope.restaurant_id,
                MenuItem.menu_category_id == category_id,
            )
        )
        return int(highest or 0) + 1

    async def ids_in_category(self, category_id: uuid.UUID) -> Sequence[uuid.UUID]:
        """Every active item in a category, for the bulk modifier-group apply."""
        return (
            await self.session.scalars(
                select(MenuItem.id).where(
                    MenuItem.restaurant_id == self.scope.restaurant_id,
                    MenuItem.menu_category_id == category_id,
                    MenuItem.is_active.is_(True),
                )
            )
        ).all()


class MenuItemVariantRepository(RestaurantScopedRepository[MenuItemVariant]):
    model = MenuItemVariant

    async def list_for_item(self, item_id: uuid.UUID) -> Sequence[MenuItemVariant]:
        return (
            await self.session.scalars(
                self.scoped()
                .where(MenuItemVariant.menu_item_id == item_id)
                .order_by(MenuItemVariant.seq, MenuItemVariant.id)
            )
        ).all()

    async def get_for_update(self, variant_id: uuid.UUID) -> MenuItemVariant | None:
        result = await self.session.scalars(
            self.scoped().where(MenuItemVariant.id == variant_id).with_for_update()
        )
        return result.first()

    async def code_exists(self, item_id: uuid.UUID, code: str) -> bool:
        found = await self.session.scalar(
            self.scoped()
            .with_only_columns(literal(1))
            .where(MenuItemVariant.menu_item_id == item_id, MenuItemVariant.code == code.strip())
            .limit(1)
        )
        return found is not None

    async def next_seq(self, item_id: uuid.UUID) -> int:
        highest = await self.session.scalar(
            select(func.coalesce(func.max(MenuItemVariant.seq), -1)).where(
                MenuItemVariant.restaurant_id == self.scope.restaurant_id,
                MenuItemVariant.menu_item_id == item_id,
            )
        )
        return int(highest or 0) + 1

    async def count_active_for_item(self, item_id: uuid.UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(MenuItemVariant)
            .where(
                MenuItemVariant.restaurant_id == self.scope.restaurant_id,
                MenuItemVariant.menu_item_id == item_id,
                MenuItemVariant.is_active.is_(True),
            )
        )
        return total or 0


class ModifierGroupRepository(RestaurantScopedRepository[ModifierGroup]):
    model = ModifierGroup

    async def list_all(
        self, *, limit: int | None = None, after: uuid.UUID | None = None
    ) -> Sequence[ModifierGroup]:
        query = self.scoped().options(selectinload(ModifierGroup.modifiers))
        if after is not None:
            cursor_code = (
                select(ModifierGroup.code)
                .where(
                    ModifierGroup.id == after,
                    ModifierGroup.restaurant_id == self.scope.restaurant_id,
                )
                .scalar_subquery()
            )
            query = query.where(
                tuple_(ModifierGroup.code, ModifierGroup.id) > tuple_(cursor_code, _as_uuid(after))
            )
        query = query.order_by(ModifierGroup.code, ModifierGroup.id)
        return (await self.session.scalars(query.limit(page_size(limit)))).all()

    async def get_with_modifiers(self, group_id: uuid.UUID) -> ModifierGroup | None:
        result = await self.session.scalars(
            self.scoped()
            .options(selectinload(ModifierGroup.modifiers))
            .where(ModifierGroup.id == group_id)
        )
        return result.first()

    async def get_for_update(self, group_id: uuid.UUID) -> ModifierGroup | None:
        result = await self.session.scalars(
            self.scoped().where(ModifierGroup.id == group_id).with_for_update()
        )
        return result.first()

    async def code_exists(self, code: str) -> bool:
        found = await self.session.scalar(
            self.scoped()
            .with_only_columns(literal(1))
            .where(ModifierGroup.code == code.strip())
            .limit(1)
        )
        return found is not None

    async def ids_owned(self, group_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        """Which of these groups belong to the caller's restaurant.

        The answer to "may this item be attached to these groups?", asked as one query rather than
        one per group. The difference between the set that comes back and the set that went in *is*
        the refusal, and the service reports the missing ids rather than a bare 404.
        """
        if not group_ids:
            return set()
        found = await self.session.scalars(
            select(ModifierGroup.id).where(
                ModifierGroup.restaurant_id == self.scope.restaurant_id,
                ModifierGroup.id.in_(list(group_ids)),
            )
        )
        return set(found.all())


class ModifierRepository(RestaurantScopedRepository[Modifier]):
    model = Modifier

    async def get_for_update(self, modifier_id: uuid.UUID) -> Modifier | None:
        result = await self.session.scalars(
            self.scoped().where(Modifier.id == modifier_id).with_for_update()
        )
        return result.first()

    async def code_exists(self, group_id: uuid.UUID, code: str) -> bool:
        found = await self.session.scalar(
            self.scoped()
            .with_only_columns(literal(1))
            .where(Modifier.modifier_group_id == group_id, Modifier.code == code.strip())
            .limit(1)
        )
        return found is not None

    async def next_seq(self, group_id: uuid.UUID) -> int:
        highest = await self.session.scalar(
            select(func.coalesce(func.max(Modifier.seq), -1)).where(
                Modifier.restaurant_id == self.scope.restaurant_id,
                Modifier.modifier_group_id == group_id,
            )
        )
        return int(highest or 0) + 1


class MenuItemModifierGroupRepository(ScopedRepository[MenuItemModifierGroup]):
    """The join between a dish and the questions asked about it.

    **Not `RestaurantScopedRepository`**, because the table has no `restaurant_id` to filter on —
    see the module docstring. It still takes a scope, and every method applies it by joining through
    `menu_item`. That is deliberately more verbose than the base class would be: the tenant filter
    is visible at each call site rather than inherited and assumed.
    """

    model = MenuItemModifierGroup

    async def list_for_item(self, item_id: uuid.UUID) -> Sequence[MenuItemModifierGroup]:
        return (
            await self.session.scalars(
                select(MenuItemModifierGroup)
                .join(MenuItem, MenuItem.id == MenuItemModifierGroup.menu_item_id)
                .where(
                    MenuItem.restaurant_id == self.scope.restaurant_id,
                    MenuItemModifierGroup.menu_item_id == item_id,
                )
                .order_by(MenuItemModifierGroup.seq)
            )
        ).all()

    async def replace_for_item(self, item_id: uuid.UUID, group_ids: Sequence[uuid.UUID]) -> None:
        """Set the whole list, in order. Attachment is a set, so PUT is the honest verb.

        The delete is scoped through `menu_item` like everything else here: an unscoped
        `DELETE WHERE menu_item_id = ?` would be correct only because the caller checked ownership
        first, and "correct because the caller checked" is the shape of the bug this product's
        invariant 1 exists to prevent.
        """
        owned = (
            select(MenuItem.id)
            .where(MenuItem.id == item_id, MenuItem.restaurant_id == self.scope.restaurant_id)
            .scalar_subquery()
        )
        await self.session.execute(
            delete(MenuItemModifierGroup).where(
                MenuItemModifierGroup.menu_item_id.in_(select(owned))
            )
        )
        for seq, group_id in enumerate(group_ids):
            self.session.add(
                MenuItemModifierGroup(menu_item_id=item_id, modifier_group_id=group_id, seq=seq)
            )


class MenuTreeRepository(ScopedRepository[MenuCategory]):
    """`GET /menu` — the whole menu in a fixed number of queries.

    Fixed, not "few": the count must not depend on how many dishes there are. `selectinload` issues
    one extra statement per relationship level (an `IN` over the parent ids), so the tree costs the
    same six statements for a 12-dish demo and a 400-dish restaurant. Loading lazily instead would
    be one statement per category, then one per item, then one per variant — which passes every test
    written against the seed and falls over on the first real menu.

    `lazy="raise"` on the models is the other half: a relationship accessed without being eagerly
    loaded raises here rather than quietly issuing a query. An N+1 that works is much harder to find
    than one that crashes on the first request.
    """

    model = MenuCategory

    async def load_tree(self, *, include_inactive: bool) -> Sequence[MenuCategory]:
        variants = selectinload(MenuCategory.items).selectinload(MenuItem.variants)
        links = (
            selectinload(MenuCategory.items)
            .selectinload(MenuItem.modifier_links)
            .selectinload(MenuItemModifierGroup.group)
            .selectinload(ModifierGroup.modifiers)
        )
        query = (
            select(MenuCategory)
            .where(MenuCategory.restaurant_id == self.scope.restaurant_id)
            .options(variants, links)
            .order_by(MenuCategory.seq, MenuCategory.id)
        )
        if not include_inactive:
            query = query.where(MenuCategory.is_active.is_(True))
        return (await self.session.scalars(query)).unique().all()

    async def menu_version(self) -> int:
        """The `ETag`. One scalar read, and the whole point of the column.

        Computing a version from the tree would mean building the tree, which is the cost the
        conditional GET exists to avoid.
        """
        version = await self.session.scalar(
            select(Restaurant.menu_version).where(Restaurant.id == self.scope.restaurant_id)
        )
        return int(version or 0)

    async def bump_version(self) -> None:
        """Called by every menu write.

        An `UPDATE ... SET x = x + 1` rather than a read-modify-write, so two concurrent menu edits
        cannot both read 7 and both write 8 — which would leave one of them invisible to every
        client holding that ETag.
        """
        await self.session.execute(
            update(Restaurant)
            .where(Restaurant.id == self.scope.restaurant_id)
            .values(menu_version=Restaurant.menu_version + 1)
        )
