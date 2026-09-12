"""The rules for building a menu.

Most of this is master-data CRUD. Five rules are not, and they are why this file is longer than the
endpoints it serves:

**1 · A code is set once and never changed.** `menu_item.code`, `menu_category.code` and
`modifier_group.code` are join keys — to `seed/menu.yaml`, to `library/dishes.yaml`, to
`seed/operations.yaml`'s modifier attachments, and to every recipe M04 will hang off a variant.
Renaming one breaks cost tracking while sales carry on, which is a silent failure. The schemas offer
no field to send; this file never assigns one after creation.

**2 · Every write bumps `restaurant.menu_version`.** It is the `ETag` on `GET /menu`, and a write
that forgets to bump it is a change no client will see until its cache expires — which, for a
conditional GET, is never. It is done in one place (`_touch`) so it cannot be forgotten per method.

**3 · A dish must be sellable or deactivated, never neither.** Deactivating the last active variant
of an active dish is refused: a dish on the menu with no orderable variant is a line a waiter taps
and nothing happens. Same for deactivating a category that still holds active dishes.

**4 · Cross-tenant attachment is checked by hand.** `menu_item_modifier_group` has no
`restaurant_id` for the repository base class to filter on (M03 spec, schema checklist Q7), so this
service verifies both sides belong to the caller before inserting — and says which ids were refused.

**5 · Price changes are audited.** `menu_item_variant.price` is deliberately editable, and it is a
money path: a manager raising a price and taking the difference on cash orders leaves no other
trace (M03 spec threat table). CLAUDE.md invariant 6 requires the audit row; `menu.price` requires
the permission.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.errors import AppError, ConflictError, NotFoundError
from app.models.audit import AuditLog
from app.models.menu import (
    MenuCategory,
    MenuItem,
    MenuItemVariant,
    Modifier,
    ModifierGroup,
)
from app.repositories.menu import (
    MenuCategoryRepository,
    MenuItemModifierGroupRepository,
    MenuItemRepository,
    MenuItemVariantRepository,
    MenuTreeRepository,
    ModifierGroupRepository,
    ModifierRepository,
)
from app.repositories.setup import StationRepository, TaxGroupRepository
from app.schemas.menu import (
    AttachModifierGroupsRequest,
    BulkAttachRequest,
    MenuCategoryCreateRequest,
    MenuCategoryUpdateRequest,
    MenuItemCreateRequest,
    MenuItemUpdateRequest,
    MenuItemVariantCreateRequest,
    MenuItemVariantUpdateRequest,
    ModifierCreateRequest,
    ModifierGroupCreateRequest,
    ModifierGroupUpdateRequest,
    ModifierUpdateRequest,
)

# Changing one of these on a variant is a money event and writes an `audit_log` row. `prep_minutes`
# is not here: it is an operational standard, not a price.
_PRICED_FIELDS = frozenset({"price", "tax_group_id"})

# The same rule for a modifier. `price_delta` is added to every order line that carries the option,
# so "extra paneer" moving from Rs 30 to Rs 150 is a price change in every sense that matters — and
# it was reachable with `menu.manage` and left no audit row at all until the M03/M04 review.
_PRICED_MODIFIER_FIELDS = frozenset({"price_delta"})


class MenuService:
    """One service for the whole menu surface. The caller owns the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ repositories

    def _categories(self, actor: Actor) -> MenuCategoryRepository:
        return MenuCategoryRepository(self.session, actor.scope)

    def _items(self, actor: Actor) -> MenuItemRepository:
        return MenuItemRepository(self.session, actor.scope)

    def _variants(self, actor: Actor) -> MenuItemVariantRepository:
        return MenuItemVariantRepository(self.session, actor.scope)

    def _groups(self, actor: Actor) -> ModifierGroupRepository:
        return ModifierGroupRepository(self.session, actor.scope)

    def _modifiers(self, actor: Actor) -> ModifierRepository:
        return ModifierRepository(self.session, actor.scope)

    def _links(self, actor: Actor) -> MenuItemModifierGroupRepository:
        return MenuItemModifierGroupRepository(self.session, actor.scope)

    def _tree(self, actor: Actor) -> MenuTreeRepository:
        return MenuTreeRepository(self.session, actor.scope)

    async def _touch(self, actor: Actor) -> None:
        """Rule 2. Every write goes through here."""
        await self._tree(actor).bump_version()

    # ------------------------------------------------------------------ the tree

    async def menu_version(self, actor: Actor) -> int:
        return await self._tree(actor).menu_version()

    async def load_tree(
        self, actor: Actor, *, include_inactive: bool
    ) -> tuple[int, Sequence[MenuCategory]]:
        """The version *and* the tree, read in that order.

        Version first so a write landing between the two reads produces a stale-looking version
        against a newer tree — which a client resolves by fetching again. The other order caches a
        new version against an old tree, and the client never fetches again because its ETag
        matches. One of those errors is self-correcting and the other is permanent.
        """
        tree = self._tree(actor)
        version = await tree.menu_version()
        categories = await tree.load_tree(include_inactive=include_inactive)
        return version, categories

    # ------------------------------------------------------------------ categories

    async def list_categories(
        self,
        actor: Actor,
        *,
        limit: int | None = None,
        after: uuid.UUID | None = None,
        include_inactive: bool = True,
    ) -> Sequence[MenuCategory]:
        return await self._categories(actor).list_all(
            limit=limit, after=after, include_inactive=include_inactive
        )

    async def create_category(
        self, actor: Actor, request: MenuCategoryCreateRequest
    ) -> MenuCategory:
        repo = self._categories(actor)
        if await repo.code_exists(request.code):
            raise ConflictError(
                "menu_category.code_taken",
                f"A category with code {request.code!r} already exists. Codes are permanent, so "
                "pick another.",
            )
        category = MenuCategory(
            restaurant_id=actor.restaurant_id,
            code=request.code,
            name=request.name,
            seq=await repo.next_seq(),
            is_active=True,
        )
        self.session.add(category)
        await self.session.flush()
        await self._touch(actor)
        return category

    async def update_category(
        self, actor: Actor, category_id: uuid.UUID, request: MenuCategoryUpdateRequest
    ) -> MenuCategory:
        repo = self._categories(actor)
        category = await repo.get_for_update(category_id)
        if category is None:
            raise NotFoundError("menu_category.not_found", "That category does not exist.")

        changes = request.model_dump(exclude_unset=True)
        if changes.get("is_active") is False and category.is_active:
            # Rule 3. A deactivated category whose dishes are still active leaves those dishes in
            # a section nothing renders — orderable by id, invisible on every screen.
            active = await repo.count_active_items(category_id)
            if active:
                raise ConflictError(
                    "menu_category.has_active_items",
                    f"{category.name!r} still has {active} active "
                    f"{'dish' if active == 1 else 'dishes'}. Move or deactivate them first.",
                    details={"active_items": active},
                )
        for field, value in changes.items():
            setattr(category, field, value)
        await self.session.flush()
        await self._touch(actor)
        return category

    # ------------------------------------------------------------------ items

    async def list_items(
        self,
        actor: Actor,
        *,
        category_id: uuid.UUID | None = None,
        limit: int | None = None,
        after: uuid.UUID | None = None,
        include_inactive: bool = True,
    ) -> Sequence[MenuItem]:
        return await self._items(actor).list_all(
            category_id=category_id,
            limit=limit,
            after=after,
            include_inactive=include_inactive,
        )

    async def get_item(self, actor: Actor, item_id: uuid.UUID) -> MenuItem:
        item = await self._items(actor).get_with_variants(item_id)
        if item is None:
            raise NotFoundError("menu_item.not_found", "That dish does not exist.")
        return item

    async def create_item(self, actor: Actor, request: MenuItemCreateRequest) -> MenuItem:
        """A dish and its variants, in one call.

        Two requests would mean every failure between them leaves a dish on the menu with nothing
        orderable under it — which rule 3 exists to prevent and which a client cannot be relied on
        to clean up.
        """
        repo = self._items(actor)
        if await repo.code_exists(request.code):
            raise ConflictError(
                "menu_item.code_taken",
                f"A dish with code {request.code!r} already exists. The code is how recipes and "
                "the starter library find this dish, so it is permanent — pick another.",
            )
        await self._require_category(actor, request.menu_category_id)
        await self._require_station(actor, request.station_id)

        item = MenuItem(
            restaurant_id=actor.restaurant_id,
            menu_category_id=request.menu_category_id,
            code=request.code,
            name=request.name,
            description=request.description,
            food_type=request.food_type,
            station_id=request.station_id,
            image_url=request.image_url,
            seq=await repo.next_seq(request.menu_category_id),
            is_active=True,
        )
        self.session.add(item)
        await self.session.flush()

        for seq, variant in enumerate(request.variants):
            await self._add_variant(actor, item, variant, seq=seq)

        await self.session.flush()
        await self._touch(actor)
        return await self.get_item(actor, item.id)

    async def update_item(
        self, actor: Actor, item_id: uuid.UUID, request: MenuItemUpdateRequest
    ) -> MenuItem:
        item = await self._items(actor).get_for_update(item_id)
        if item is None:
            raise NotFoundError("menu_item.not_found", "That dish does not exist.")

        changes = request.model_dump(exclude_unset=True)
        if "menu_category_id" in changes and changes["menu_category_id"] is not None:
            await self._require_category(actor, changes["menu_category_id"])
        if "station_id" in changes and changes["station_id"] is not None:
            await self._require_station(actor, changes["station_id"])

        for field, value in changes.items():
            setattr(item, field, value)
        await self.session.flush()
        await self._touch(actor)
        return await self.get_item(actor, item_id)

    # ------------------------------------------------------------------ variants

    async def add_variant(
        self, actor: Actor, item_id: uuid.UUID, request: MenuItemVariantCreateRequest
    ) -> MenuItem:
        item = await self._items(actor).get_for_update(item_id)
        if item is None:
            raise NotFoundError("menu_item.not_found", "That dish does not exist.")
        await self._add_variant(actor, item, request, seq=None)
        await self.session.flush()
        await self._touch(actor)
        return await self.get_item(actor, item_id)

    async def _add_variant(
        self,
        actor: Actor,
        item: MenuItem,
        request: MenuItemVariantCreateRequest,
        *,
        seq: int | None,
    ) -> MenuItemVariant:
        repo = self._variants(actor)
        if await repo.code_exists(item.id, request.code):
            raise ConflictError(
                "menu_item_variant.code_taken",
                f"{item.name!r} already has a {request.code!r} variant.",
            )
        await self._require_tax_group(actor, request.tax_group_id)
        variant = MenuItemVariant(
            restaurant_id=actor.restaurant_id,
            menu_item_id=item.id,
            code=request.code,
            name=request.name,
            price=request.price,
            tax_group_id=request.tax_group_id,
            prep_minutes=request.prep_minutes,
            seq=seq if seq is not None else await repo.next_seq(item.id),
            is_active=True,
        )
        self.session.add(variant)
        await self.session.flush()
        await self._audit(
            actor,
            action="menu_item_variant.created",
            entity_id=variant.id,
            old_value=None,
            new_value={"code": variant.code, "price": variant.price},
        )
        return variant

    async def update_variant(
        self, actor: Actor, variant_id: uuid.UUID, request: MenuItemVariantUpdateRequest
    ) -> MenuItem:
        repo = self._variants(actor)
        variant = await repo.get_for_update(variant_id)
        if variant is None:
            raise NotFoundError("menu_item_variant.not_found", "That variant does not exist.")

        changes = request.model_dump(exclude_unset=True)
        if "tax_group_id" in changes and changes["tax_group_id"] is not None:
            await self._require_tax_group(actor, changes["tax_group_id"])

        if changes.get("is_active") is False and variant.is_active:
            # Rule 3, the other half. A dish whose last orderable variant is switched off is a line
            # a waiter taps to no effect — the dish should be deactivated instead, deliberately.
            remaining = await repo.count_active_for_item(variant.menu_item_id)
            item = await self._items(actor).get(variant.menu_item_id)
            if remaining <= 1 and item is not None and item.is_active:
                raise ConflictError(
                    "menu_item_variant.last_active",
                    "That is the only variant this dish can be ordered as. Deactivate the dish "
                    "itself, or add another variant first.",
                )

        priced = {field: getattr(variant, field) for field in changes if field in _PRICED_FIELDS}
        for field, value in changes.items():
            setattr(variant, field, value)
        await self.session.flush()

        if priced:
            # Rule 5. Invariant 6: everything price-affecting writes an audit row, with before and
            # after, so a quiet reprice has a name and a timestamp on it.
            await self._audit(
                actor,
                action="menu_item_variant.repriced",
                entity_id=variant.id,
                old_value=priced,
                new_value={field: getattr(variant, field) for field in priced},
            )
        await self._touch(actor)
        return await self.get_item(actor, variant.menu_item_id)

    # ------------------------------------------------------------------ modifier groups

    async def list_modifier_groups(
        self, actor: Actor, *, limit: int | None = None, after: uuid.UUID | None = None
    ) -> Sequence[ModifierGroup]:
        return await self._groups(actor).list_all(limit=limit, after=after)

    async def create_modifier_group(
        self, actor: Actor, request: ModifierGroupCreateRequest
    ) -> ModifierGroup:
        repo = self._groups(actor)
        if await repo.code_exists(request.code):
            raise ConflictError(
                "modifier_group.code_taken",
                f"A modifier group with code {request.code!r} already exists.",
            )
        self._require_selectable(request.min_select, request.max_select, request.is_required)

        group = ModifierGroup(
            restaurant_id=actor.restaurant_id,
            code=request.code,
            name=request.name,
            min_select=request.min_select,
            max_select=request.max_select,
            is_required=request.is_required,
            is_active=True,
        )
        self.session.add(group)
        await self.session.flush()
        for seq, modifier in enumerate(request.modifiers):
            self.session.add(
                Modifier(
                    restaurant_id=actor.restaurant_id,
                    modifier_group_id=group.id,
                    code=modifier.code,
                    name=modifier.name,
                    price_delta=modifier.price_delta,
                    seq=seq,
                    is_active=True,
                )
            )
        await self.session.flush()
        await self._touch(actor)
        return await self._reload_group(actor, group.id)

    async def update_modifier_group(
        self, actor: Actor, group_id: uuid.UUID, request: ModifierGroupUpdateRequest
    ) -> ModifierGroup:
        group = await self._groups(actor).get_for_update(group_id)
        if group is None:
            raise NotFoundError("modifier_group.not_found", "That modifier group does not exist.")

        changes = request.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(group, field, value)
        # Checked against the merged result, not the request: sending only `max_select` must not be
        # able to leave the row with a max below a min it did not mention.
        self._require_selectable(group.min_select, group.max_select, group.is_required)
        await self.session.flush()
        await self._touch(actor)
        return await self._reload_group(actor, group_id)

    async def add_modifier(
        self, actor: Actor, group_id: uuid.UUID, request: ModifierCreateRequest
    ) -> ModifierGroup:
        """Add an option to a group.

        A non-zero `price_delta` makes this a money write, and the route requires `menu.price` for
        exactly that reason — otherwise a `menu.manage` holder creates "Extra paneer +Rs 150" and
        the permission boundary the P1 design drew is decoration.
        """
        group = await self._groups(actor).get_for_update(group_id)
        if group is None:
            raise NotFoundError("modifier_group.not_found", "That modifier group does not exist.")
        repo = self._modifiers(actor)
        if await repo.code_exists(group_id, request.code):
            raise ConflictError(
                "modifier.code_taken",
                f"{group.name!r} already has a {request.code!r} option.",
            )
        modifier = Modifier(
            restaurant_id=actor.restaurant_id,
            modifier_group_id=group_id,
            code=request.code,
            name=request.name,
            price_delta=request.price_delta,
            seq=await repo.next_seq(group_id),
            is_active=True,
        )
        self.session.add(modifier)
        await self.session.flush()
        if request.price_delta:
            await self._audit(
                actor,
                action="modifier.priced",
                entity_id=modifier.id,
                old_value=None,
                new_value={"code": modifier.code, "price_delta": modifier.price_delta},
            )
        await self._touch(actor)
        return await self._reload_group(actor, group_id)

    async def update_modifier(
        self, actor: Actor, modifier_id: uuid.UUID, request: ModifierUpdateRequest
    ) -> ModifierGroup:
        modifier = await self._modifiers(actor).get_for_update(modifier_id)
        if modifier is None:
            raise NotFoundError("modifier.not_found", "That option does not exist.")

        changes = request.model_dump(exclude_unset=True)
        priced = {
            field: getattr(modifier, field) for field in changes if field in _PRICED_MODIFIER_FIELDS
        }
        for field, value in changes.items():
            setattr(modifier, field, value)
        await self.session.flush()

        if priced and any(priced[field] != getattr(modifier, field) for field in priced):
            # Invariant 6. A quiet change from +Rs 30 to +Rs 150 on a popular add-on leaves no
            # other trace: the menu still reads "Extra paneer" and the bill is simply larger.
            await self._audit(
                actor,
                action="modifier.repriced",
                entity_id=modifier.id,
                old_value=priced,
                new_value={field: getattr(modifier, field) for field in priced},
            )
        await self._touch(actor)
        return await self._reload_group(actor, modifier.modifier_group_id)

    # ------------------------------------------------------------------ attachment

    async def attach_modifier_groups(
        self, actor: Actor, item_id: uuid.UUID, request: AttachModifierGroupsRequest
    ) -> MenuItem:
        """Set a dish's whole list of modifier groups, in order."""
        item = await self._items(actor).get_for_update(item_id)
        if item is None:
            raise NotFoundError("menu_item.not_found", "That dish does not exist.")
        await self._require_groups(actor, request.modifier_group_ids)
        await self._links(actor).replace_for_item(item_id, request.modifier_group_ids)
        await self.session.flush()
        await self._touch(actor)
        return await self.get_item(actor, item_id)

    async def bulk_attach_to_category(
        self, actor: Actor, category_id: uuid.UUID, request: BulkAttachRequest
    ) -> int:
        """Apply modifier groups to every active dish in a category. Returns how many were changed.

        Expanded here rather than stored as a category-level rule: the data model is per item so a
        single dish can opt out, and a stored rule would then need reconciling against every
        exception forever. `seed/operations.yaml` writes attachments by category for the same reason
        an owner describes them that way — this is where that shorthand is unfolded.
        """
        await self._require_category(actor, category_id)
        await self._require_groups(actor, request.modifier_group_ids)

        links = self._links(actor)
        item_ids = await self._items(actor).ids_in_category(category_id)
        for item_id in item_ids:
            if request.replace:
                wanted = list(request.modifier_group_ids)
            else:
                existing = [link.modifier_group_id for link in await links.list_for_item(item_id)]
                wanted = existing + [
                    group_id for group_id in request.modifier_group_ids if group_id not in existing
                ]
            await links.replace_for_item(item_id, wanted)
        await self.session.flush()
        await self._touch(actor)
        return len(item_ids)

    # ------------------------------------------------------------------ shared

    async def _require_category(self, actor: Actor, category_id: uuid.UUID) -> MenuCategory:
        category = await self._categories(actor).get(category_id)
        if category is None:
            raise NotFoundError("menu_category.not_found", "That category does not exist.")
        return category

    async def _require_station(self, actor: Actor, station_id: uuid.UUID) -> None:
        station = await StationRepository(self.session, actor.scope).get(station_id)
        if station is None:
            raise NotFoundError("station.not_found", "That kitchen station does not exist.")

    async def _require_tax_group(self, actor: Actor, tax_group_id: uuid.UUID) -> None:
        group = await TaxGroupRepository(self.session, actor.scope).get(tax_group_id)
        if group is None:
            raise NotFoundError("tax_group.not_found", "That tax group does not exist.")

    async def _require_groups(self, actor: Actor, group_ids: Sequence[uuid.UUID]) -> None:
        """Rule 4. Every id must belong to this restaurant.

        The refusal names the ids that failed rather than returning a bare 404, because a caller
        sending twelve ids needs to know which one was wrong. It is deliberately the same message
        whether an id belongs to another tenant or does not exist at all — distinguishing them would
        turn this endpoint into a probe for which ids are real elsewhere.
        """
        owned = await self._groups(actor).ids_owned(group_ids)
        missing = sorted(str(group_id) for group_id in set(group_ids) - owned)
        if missing:
            raise NotFoundError(
                "modifier_group.not_found",
                f"{len(missing)} of those modifier groups do not exist.",
                details={"missing": missing},
            )

    def _require_selectable(self, min_select: int, max_select: int, is_required: bool) -> None:
        if max_select < min_select:
            raise AppError(
                "modifier_group.max_below_min",
                f"A group cannot allow {max_select} choices while requiring {min_select}.",
                status_code=422,
            )
        if is_required and min_select < 1:
            raise AppError(
                "modifier_group.required_needs_one",
                "A required group must ask for at least one choice, or there is no answer that "
                "satisfies it.",
                status_code=422,
            )

    async def _reload_group(self, actor: Actor, group_id: uuid.UUID) -> ModifierGroup:
        """Re-read with modifiers attached: the relationship is `lazy="raise"`, so a freshly
        created group would otherwise blow up in the serialiser rather than silently N+1."""
        group = await self._groups(actor).get_with_modifiers(group_id)
        if group is None:  # pragma: no cover - written in this transaction
            raise NotFoundError("modifier_group.not_found", "That modifier group does not exist.")
        return group

    async def _audit(
        self,
        actor: Actor,
        *,
        action: str,
        entity_id: uuid.UUID,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any],
    ) -> None:
        self.session.add(
            AuditLog(
                restaurant_id=actor.restaurant_id,
                actor_employee_id=actor.employee_id,
                action=action,
                entity_type="modifier" if action.startswith("modifier") else "menu_item_variant",
                entity_id=entity_id,
                old_value=_jsonable(old_value),
                new_value=_jsonable(new_value),
            )
        )


def _jsonable(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """`Decimal` and `UUID` are not JSON. Stringified rather than floated — a price in an audit row
    that reads `470.0000000001` is worse than useless in a dispute."""
    if value is None:
        return None
    return {key: str(item) if item is not None else None for key, item in value.items()}
