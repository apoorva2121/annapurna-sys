"""The API contract for the menu.

Same three conventions as `schemas/setup.py`, for the same reasons: money is a string in JSON, an
absent PATCH field means "leave it alone", and `extra="forbid"` refuses a misspelled field rather
than returning 200 and changing nothing.

Two rules specific to this module:

**A code is settable once and never again.** `menu_item.code`, `menu_category.code` and
`modifier_group.code` appear on create requests and on no update request. That is the first place
the rule is enforced, before the service and before the database: there is no field here to send.
They are join keys to `seed/`, to `library/dishes.yaml` and to every recipe M04 will attach.

**Price is on the variant and nowhere else.** `MenuItemCreateRequest` cannot carry one. A dish does
not have a price; the thing you can order does.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import FoodType

# The code format shared by every code in this module. Uppercase, digits and underscore, starting
# with a letter — which is what `seed/menu.yaml` and `library/dishes.yaml` already use.
_CODE_PATTERN = r"^[A-Z][A-Z0-9_]*$"


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ReadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


def _strip(value: Any) -> Any:
    """Strip **before** the length constraint, not after — see `schemas/setup.py` for why."""
    return value.strip() if isinstance(value, str) else value


def _upper(value: Any) -> Any:
    """Uppercase a code at the boundary rather than refusing a lowercase one.

    The pattern would reject `butter_chicken` for its case, which is a rule the person typing it
    has no way to know in advance. Normalising is friendlier and produces exactly one spelling in
    the database, which is what the unique constraint needs.
    """
    return value.strip().upper() if isinstance(value, str) else value


# --------------------------------------------------------------------------- read models


class ModifierResponse(_ReadSchema):
    id: uuid.UUID
    code: str
    name: str
    # A string in JSON, never a float. "no rice" may legitimately be negative.
    price_delta: Decimal
    is_active: bool


class ModifierGroupResponse(_ReadSchema):
    id: uuid.UUID
    code: str
    name: str
    min_select: int
    max_select: int
    is_required: bool
    is_active: bool
    modifiers: list[ModifierResponse]


class ModifierGroupListResponse(_Schema):
    items: list[ModifierGroupResponse]
    next_cursor: uuid.UUID | None = None


class MenuItemVariantResponse(_ReadSchema):
    id: uuid.UUID
    code: str
    name: str
    # A string in JSON. engineering-standards §4, CLAUDE.md invariant 3.
    price: Decimal
    tax_group_id: uuid.UUID
    prep_minutes: int
    seq: int
    is_active: bool


class MenuItemResponse(_ReadSchema):
    id: uuid.UUID
    menu_category_id: uuid.UUID
    code: str
    name: str
    description: str | None
    food_type: FoodType
    # What a guest with an allergy reads (compliance-rules §A2): text, NULL when never asked.
    allergen_statement: str | None = None
    # §B1, for a restaurant the calorie rule covers.
    calories_kcal: int | None = None
    serving_size: str | None = None
    station_id: uuid.UUID
    image_url: str | None
    seq: int
    is_active: bool
    variants: list[MenuItemVariantResponse]


class MenuItemDetailResponse(MenuItemResponse):
    """One dish, **including which option groups are attached to it**.

    A separate schema rather than a field on `MenuItemResponse`, because the list route loads only
    variants: putting the field on the base class would have every listed dish report an empty
    attachment set it never looked for, which is a worse lie than the omission it replaces. Every
    route that returns this one reloads through `MenuService.get_item`, which does load them.

    The editor needs this to exist at all. Attachment is a `PUT` of the whole set, and the screen
    had no way to know the current one — so it started from nothing ticked and saving *anything*
    silently detached every group the dish already had. Found by the M03/M04 review.
    """

    # Read from the `modifier_links` rows and published under the name the editor wants. The alias
    # is what lets the field be derived without a property on the model, which would fire
    # `lazy="raise"` on every path that has not loaded them.
    modifier_group_ids: list[uuid.UUID] = Field(validation_alias="modifier_links")

    @field_validator("modifier_group_ids", mode="before")
    @classmethod
    def _from_links(cls, value: Any) -> Any:
        """`modifier_links` are rows; the editor wants ids, in attachment order."""
        if isinstance(value, list) and value and not isinstance(value[0], uuid.UUID):
            return [link.modifier_group_id for link in sorted(value, key=lambda row: row.seq)]
        return value


class MenuItemListResponse(_Schema):
    items: list[MenuItemResponse]
    next_cursor: uuid.UUID | None = None


class MenuCategoryResponse(_ReadSchema):
    id: uuid.UUID
    code: str
    name: str
    seq: int
    is_active: bool


class MenuCategoryListResponse(_Schema):
    items: list[MenuCategoryResponse]
    next_cursor: uuid.UUID | None = None


# --------------------------------------------------------------------------- the tree


# The guest-facing schemas moved to `app/schemas/guest.py` in M10, and the move is the point rather
# than tidying: ADR 0009 says a guest response must not be able to reach a staff schema, and suite 5
# enforces that by *module*. While `GuestItem` lived here it carried the staff
# `ModifierGroupResponse` — which has `code` and `is_active` on the group and on every modifier —
# so a menu that carefully withheld `BUTTER_CHICKEN` handed over `EXTRA_CHEESE` one level down.


class StaffItem(_Schema):
    """A dish, as staff see it: everything, including what routes it and how long it takes."""

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    food_type: FoodType
    # What a guest with an allergy reads (compliance-rules §A2): text, NULL when never asked.
    allergen_statement: str | None = None
    # §B1, for a restaurant the calorie rule covers.
    calories_kcal: int | None = None
    serving_size: str | None = None
    station_id: uuid.UUID
    image_url: str | None
    is_active: bool
    variants: list[MenuItemVariantResponse]
    modifier_groups: list[ModifierGroupResponse]


class StaffCategory(_Schema):
    id: uuid.UUID
    code: str
    name: str
    is_active: bool
    items: list[StaffItem]


class MenuTreeResponse(_Schema):
    """The whole menu. `version` is the `ETag` a conditional GET compares against."""

    version: int
    categories: list[StaffCategory]


# --------------------------------------------------------------------------- write models


class MenuCategoryCreateRequest(_Schema):
    code: str = Field(min_length=1, max_length=32, pattern=_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=80)

    _upper_code = field_validator("code", mode="before")(_upper)
    _strip_name = field_validator("name", mode="before")(_strip)


class MenuCategoryUpdateRequest(_Schema):
    """No `code`. It is the key `seed/menu.yaml` and `library/dishes.yaml` join on."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    seq: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    _strip_name = field_validator("name", mode="before")(_strip)


class MenuCategoryReorderRequest(_Schema):
    """The whole menu's section order in one request (backlog-issues B3). Every active section
    exactly once; see `app/services/reorder.py`."""

    category_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class MenuItemCreateRequest(_Schema):
    """A dish, and optionally the variants it is sold as.

    Variants are accepted here because a dish with none cannot be ordered, and making the client
    issue two requests means every failure between them leaves an unsellable dish on the menu.
    """

    menu_category_id: uuid.UUID
    code: str = Field(min_length=1, max_length=64, pattern=_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    # FSSAI requires the declaration. No default: a dish whose food type nobody chose is a dish
    # nobody may legally print on a menu.
    food_type: FoodType
    # Compliance-rules §A2: a statement in text. No list of allergens is written into code until
    # the regulation's own list is verified from the instrument. NULL is "never asked".
    allergen_statement: str | None = Field(default=None, max_length=500)
    calories_kcal: int | None = Field(default=None, ge=0, le=10000)
    serving_size: str | None = Field(default=None, max_length=60)
    station_id: uuid.UUID
    image_url: str | None = Field(default=None, max_length=500)
    variants: list[MenuItemVariantCreateRequest] = Field(default_factory=list)

    _upper_code = field_validator("code", mode="before")(_upper)
    _strip_name = field_validator("name", mode="before")(_strip)
    _strip_description = field_validator("description", mode="before")(_strip)


class MenuItemUpdateRequest(_Schema):
    """No `code`, and no price — price is a property of a variant."""

    menu_category_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    food_type: FoodType | None = None
    # Compliance-rules §A2: a statement in text. No list of allergens is written into code until
    # the regulation's own list is verified from the instrument. NULL is "never asked".
    allergen_statement: str | None = Field(default=None, max_length=500)
    calories_kcal: int | None = Field(default=None, ge=0, le=10000)
    serving_size: str | None = Field(default=None, max_length=60)
    station_id: uuid.UUID | None = None
    image_url: str | None = Field(default=None, max_length=500)
    seq: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    _strip_name = field_validator("name", mode="before")(_strip)
    _strip_description = field_validator("description", mode="before")(_strip)


class MenuItemVariantCreateRequest(_Schema):
    code: str = Field(min_length=1, max_length=32, pattern=_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=60)
    # `ge=0` and not `gt=0`: a complimentary side is a real menu line at zero. `max_digits`/
    # `decimal_places` mirror NUMERIC(12,2), so a third decimal is refused here rather than
    # silently rounded by Postgres.
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    tax_group_id: uuid.UUID
    prep_minutes: int = Field(gt=0, le=600)

    _upper_code = field_validator("code", mode="before")(_upper)
    _strip_name = field_validator("name", mode="before")(_strip)


class MenuItemVariantUpdateRequest(_Schema):
    """Price *is* editable, unlike a tax rate.

    A menu price genuinely changes, and `order_line` copies the price when the line is added (M07),
    so a reprice cannot rewrite a past bill. The protection is structural rather than a refusal
    here — see `models/menu.py`.
    """

    name: str | None = Field(default=None, min_length=1, max_length=60)
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    tax_group_id: uuid.UUID | None = None
    prep_minutes: int | None = Field(default=None, gt=0, le=600)
    seq: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    _strip_name = field_validator("name", mode="before")(_strip)


class ModifierCreateRequest(_Schema):
    code: str = Field(min_length=1, max_length=32, pattern=_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=60)
    # No `ge`: "no rice" can be a discount.
    price_delta: Decimal = Field(default=Decimal(0), max_digits=12, decimal_places=2)

    _upper_code = field_validator("code", mode="before")(_upper)
    _strip_name = field_validator("name", mode="before")(_strip)


class ModifierUpdateRequest(_Schema):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    price_delta: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    seq: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    _strip_name = field_validator("name", mode="before")(_strip)


class ModifierGroupCreateRequest(_Schema):
    """A group and, optionally, its choices.

    `min_select`/`max_select` are checked against each other by the database as well as here: a
    group that allows fewer choices than it requires is a question with no valid answer.
    """

    code: str = Field(min_length=1, max_length=32, pattern=_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    min_select: int = Field(default=0, ge=0, le=50)
    max_select: int = Field(default=1, ge=1, le=50)
    is_required: bool = False
    modifiers: list[ModifierCreateRequest] = Field(default_factory=list)

    _upper_code = field_validator("code", mode="before")(_upper)
    _strip_name = field_validator("name", mode="before")(_strip)


class ModifierGroupUpdateRequest(_Schema):
    """No `code` — `seed/operations.yaml` attaches groups to categories by it."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    min_select: int | None = Field(default=None, ge=0, le=50)
    max_select: int | None = Field(default=None, ge=1, le=50)
    is_required: bool | None = None
    is_active: bool | None = None

    _strip_name = field_validator("name", mode="before")(_strip)


def _dedupe(value: Any) -> Any:
    """Drop repeats, keep the first position of each.

    `menu_item_modifier_group`'s primary key is the pair, so the same group twice was an
    `IntegrityError` and — because that exception is unmapped — a 500. A UI that lets somebody tick
    "Spice level" twice before saving produced it. De-duplicating is friendlier than refusing: the
    request means exactly one thing, and it is the thing that happens.
    """
    if isinstance(value, list):
        return list(dict.fromkeys(value))
    return value


class AttachModifierGroupsRequest(_Schema):
    """The whole attachment list, in order. A PUT, because attachment is a set and not a log."""

    modifier_group_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)

    _dedupe_ids = field_validator("modifier_group_ids", mode="before")(_dedupe)


class BulkAttachRequest(_Schema):
    """Apply modifier groups to every active item in a category.

    The data model is per item — one dish in MAIN_VEG can opt out of Jain preference because it has
    no onion — but "all main courses get a spice level" is how an owner describes a menu and how
    `seed/operations.yaml` writes one down. This endpoint is the bridge, and it expands at call time
    rather than storing a category-level rule that would then have to be reconciled forever.
    """

    modifier_group_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)

    _dedupe_ids = field_validator("modifier_group_ids", mode="before")(_dedupe)

    # Replace an item's whole list, or add to it. Adding is the safer default; replacing is what
    # someone wants after deciding the category's modifiers were wrong from the start.
    replace: bool = False
