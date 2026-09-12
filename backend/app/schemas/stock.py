"""The API contract for stock items and recipes.

Same conventions as the rest: money and quantities are strings in JSON, an absent PATCH field means
"leave it alone", `extra="forbid"` refuses a misspelled field.

**Quantities are strings too, not only money.** A recipe line can be `0.05` g of saffron, and a
`float` round-trip through JavaScript is how that becomes `0.05000000000000000277` and then, after
`numeric(14,4)`, `0.0500` — which happens to be right, until the day it is `0.1` and comes back
`0.1000000000000000055`. The rule that keeps money exact is the same rule, and applying it to
quantities costs nothing.

**There is no recipe *edit* request.** A change is a new version and the only write is
`RecipeVersionRequest`. The schema is the first place that is enforced, before the service and
before the partial unique index.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CODE_PATTERN = r"^[A-Z][A-Z0-9_]*$"


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ReadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _upper(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


# --------------------------------------------------------------------------- read


class IngredientProfileResponse(_ReadSchema):
    purchase_unit: str
    purchase_to_base: Decimal
    # The fraction of what you buy that reaches the pan: trim loss for a weight, breakage and
    # spoilage for a count.
    yield_factor: Decimal
    shelf_life_days: int
    reorder_level: Decimal | None
    reorder_quantity: Decimal | None


class PreparationProfileResponse(_ReadSchema):
    batch_yield: Decimal
    # HOURS. A gravy made from seven-day cream dies in thirty-six (ADR 0006).
    shelf_life_hours: int
    station_id: uuid.UUID
    prep_minutes: int


class StockItemResponse(_ReadSchema):
    """A stock item **without its price**.

    `recipe.view` is held by the chef, the kitchen staff and the store manager, and
    `seed/organization.yaml` is explicit that a chef sees grams and not rupees. An earlier version
    of this schema carried `current_unit_cost` on every read — so the whole ingredient price list
    was one `GET /stock-items` away from anyone who could read a recipe, and the separation this
    module called its headline did not exist. Found by the M03/M04 review.

    `PricedStockItemResponse` adds the price back for a caller holding `cost.view`.
    """

    id: uuid.UUID
    kind: str
    code: str
    name: str
    base_unit: str
    category: str | None
    storage_type: str | None
    is_active: bool
    ingredient: IngredientProfileResponse | None = None
    preparation: PreparationProfileResponse | None = None


class PricedStockItemResponse(StockItemResponse):
    """What a `cost.view` holder sees. Today's price, never a historical answer (finding S16)."""

    current_unit_cost: Decimal


# **A union, and a subclass would not do.** The obvious version of this declared the base class and
# relied on `PricedStockItemResponse` being a subclass — and FastAPI serialises strictly by the
# declared type, so every price was silently filtered back out and the owner saw the chef's view.
# Naming both, priced first, lets Pydantic's smart union keep whichever one the route actually
# built. It also keeps the OpenAPI schema honest: the field genuinely is sometimes absent.
AnyStockItemResponse = PricedStockItemResponse | StockItemResponse


class StockItemListResponse(_Schema):
    items: list[AnyStockItemResponse]
    next_cursor: uuid.UUID | None = None


class RecipeLineResponse(_ReadSchema):
    component_id: uuid.UUID
    quantity: Decimal
    seq: int


class RecipeResponse(_ReadSchema):
    """A recipe **without its cost** — grams, not rupees.

    `unit_cost` used to sit here, which meant a chef saving a recipe was told what it cost in the
    response body. Found by the M03/M04 review; `PricedRecipeResponse` carries it for `cost.view`.
    """

    id: uuid.UUID
    menu_item_variant_id: uuid.UUID | None
    produces_stock_item_id: uuid.UUID | None
    modifier_id: uuid.UUID | None
    version: int
    is_current: bool
    effective_from: datetime
    notes: str | None
    # `typed` | `seeded` | `library`. A recipe matched from the starter library carries quantities
    # nobody at this restaurant has checked — `library/PROVENANCE.md` says most of it is estimated.
    source: str
    confirmed_at: datetime | None
    lines: list[RecipeLineResponse]


class PricedRecipeResponse(RecipeResponse):
    """Frozen when this version became current (X8). What M13 reads for a historical cost."""

    unit_cost: Decimal


# Same union, same reason: see `AnyStockItemResponse`.
AnyRecipeResponse = PricedRecipeResponse | RecipeResponse


class CostedLineResponse(_Schema):
    component_id: uuid.UUID
    code: str
    quantity: Decimal
    unit_cost: Decimal
    cost: Decimal


class DishCostResponse(_Schema):
    """One dish's cost, **with its lines**.

    "Butter Chicken costs ₹126.70" is not actionable; the line saying ₹63 of it is chicken tikka is
    what an owner uses when the price of chicken moves.
    """

    menu_item_variant_id: uuid.UUID
    cost: Decimal
    price: Decimal
    # `None` at a price of zero — a complimentary side is a real menu line, and "0%" would be a lie.
    food_cost_percent: Decimal | None
    margin: Decimal
    lines: list[CostedLineResponse]
    # False when no current recipe exists. The screen must say "not costed yet" rather than "₹0.00",
    # which reads as a dish that is free to make.
    has_recipe: bool


class MenuCostRow(_Schema):
    menu_item_id: uuid.UUID
    menu_item_name: str
    menu_item_variant_id: uuid.UUID
    variant_name: str
    cost: Decimal
    price: Decimal
    food_cost_percent: Decimal | None
    margin: Decimal
    has_recipe: bool
    # Surfaced per row, because a cost computed from an unconfirmed library recipe is a proposal
    # and a screen that does not say so is stating a number with confidence nobody has earned.
    recipe_confirmed: bool


class MenuCostResponse(_Schema):
    rows: list[MenuCostRow]
    # Popularity is not known here (it is observed demand, M07), so this is the plain average
    # across costed dishes — clearly labelled, because the seed's 25.6% figure is weighted and the
    # two numbers must not be confused.
    average_food_cost_percent: Decimal | None
    uncosted: int
    # True when the menu is larger than one report can carry. The screen must say so: a worst-first
    # list that quietly stopped would hide the dish it exists to surface.
    truncated: bool = False


class UsedByResponse(_Schema):
    """What consumes a stock item, transitively.

    Paneer is in makhani gravy and makhani gravy is in six dishes — so both lists matter, and a
    screen showing only the direct consumers answers the wrong question.
    """

    preparations: list[AnyStockItemResponse]
    dishes: list[uuid.UUID]
    dish_names: list[str]


# --------------------------------------------------------------------------- write


class IngredientProfileRequest(_Schema):
    purchase_unit: str = Field(min_length=1, max_length=20)
    purchase_to_base: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    yield_factor: Decimal = Field(default=Decimal(1), gt=0, le=1, max_digits=6, decimal_places=4)
    shelf_life_days: int = Field(gt=0, le=3650)
    reorder_level: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4)
    reorder_quantity: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4)

    _strip_unit = field_validator("purchase_unit", mode="before")(_strip)


class PreparationProfileRequest(_Schema):
    batch_yield: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    shelf_life_hours: int = Field(gt=0, le=8760)
    station_id: uuid.UUID
    prep_minutes: int = Field(gt=0, le=1440)


class StockItemCreateRequest(_Schema):
    """An ingredient or a preparation, with the profile that makes it one or the other.

    Both profiles are optional in the schema and exactly one is required by the service, keyed on
    `kind`. Expressing that here would need a discriminated union whose error messages are worse
    than the sentence the service produces.
    """

    kind: str = Field(pattern=r"^(ingredient|preparation)$")
    code: str = Field(min_length=1, max_length=64, pattern=_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    base_unit: str = Field(pattern=r"^(g|ml|unit)$")
    category: str | None = Field(
        default=None, pattern=r"^(meat|dairy|veg|grain|spice|oil|bakery|sweet)$"
    )
    storage_type: str | None = Field(default=None, pattern=r"^(ambient|chilled|frozen)$")
    current_unit_cost: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=6)
    ingredient: IngredientProfileRequest | None = None
    preparation: PreparationProfileRequest | None = None

    _upper_code = field_validator("code", mode="before")(_upper)
    _strip_name = field_validator("name", mode="before")(_strip)


class StockItemUpdateRequest(_Schema):
    """No `kind` and no `code`.

    `kind` decides which profile table the row has, so changing it would orphan one and require the
    other — a migration dressed as a PATCH. `code` is the join key to `seed/`, `library/` and every
    recipe line.
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(
        default=None, pattern=r"^(meat|dairy|veg|grain|spice|oil|bakery|sweet)$"
    )
    storage_type: str | None = Field(default=None, pattern=r"^(ambient|chilled|frozen)$")
    current_unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=6)
    is_active: bool | None = None
    ingredient: IngredientProfileRequest | None = None
    preparation: PreparationProfileRequest | None = None

    _strip_name = field_validator("name", mode="before")(_strip)


class RecipeLineRequest(_Schema):
    component_id: uuid.UUID
    # In the component's base unit. Four decimal places because 0.05 g of saffron is a real line and
    # two would round it to nothing.
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=4)


class RecipeVersionRequest(_Schema):
    """A recipe's lines, as of now.

    **The only write.** Creating the first version and changing an existing one are the same
    operation — a new version, with the previous one stood down — because "edit" is a verb this
    table does not support: `order_line` cites a version, and a version whose lines moved would
    restate what every past order cost.
    """

    # Exactly one, checked by the service: a recipe belongs to a dish variant, a preparation it
    # produces, or a modifier.
    menu_item_variant_id: uuid.UUID | None = None
    produces_stock_item_id: uuid.UUID | None = None
    modifier_id: uuid.UUID | None = None
    lines: list[RecipeLineRequest] = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
    source: str = Field(default="typed", pattern=r"^(typed|seeded|library)$")
    # A chef ticking "yes, this is what we actually make". Separate from creating it, because a
    # recipe matched from the library arrives unconfirmed by definition.
    confirmed: bool = False

    _strip_notes = field_validator("notes", mode="before")(_strip)
