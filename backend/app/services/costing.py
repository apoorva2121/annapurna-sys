"""What a dish costs. The calculation this product exists to perform.

**This module must agree with `seed/validate.py` to the paisa.** Two implementations of one
arithmetic now exist: the validator that has guarded the seed since M00, and this. `docs/modules.md`
names the figures that prove they agree — Butter Chicken Full at **₹126.70**, makhani gravy at
**₹0.1489 per ml**, and a popularity-weighted menu food cost of **25.7%** — and
`tests/test_costing.py` asserts all three against the running service. If they ever disagree, one of
them is lying about the only number this product sells.

The four rules, which are `seed/validate.py`'s rules restated:

1. **An ingredient line costs `quantity / yield_factor * unit_cost`.** The division is the loss
   between buying and cooking: to *use* 720 g of chicken you must *buy* a kilo, and the dish costs
   the kilo. It applies to every base unit, count included — breakage is a real cost. (Finding S15
   proposes limiting it to weight; the M04 spec argues that is wrong and leaves it open.)
2. **A preparation line costs `quantity * prep_unit_cost(preparation)`.** Recursive: a preparation's
   own lines may be preparations.
3. **A preparation's unit cost is `sum(line costs) / batch_yield`.** Birista yields 1200 g of fried
   onion from 4000 g of raw, and that loss is exactly what makes the unit cost worth computing.
4. **Depth is capped at three and cycles are refused** (ADR 0006).

**Memoised per call, never across calls.** A menu-wide cost screen asks for two hundred dishes, most
of which resolve the same makhani gravy; without memoisation that is two hundred identical recursive
walks. With a cache that outlived the request it would be a stale number the morning an ingredient
price changed — and a food-cost figure that is quietly out of date is worse than one that is slow.

**`Decimal` throughout, and quantised only where a number leaves.** Intermediate values keep full
precision; rounding a per-gram cost to two places makes saffron free.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.core.errors import AppError

# ADR 0006: ingredient → prep → prep → dish. Counted in *preparation* hops, which is what
# `seed/validate.py` counts, so the two agree on what "depth 3" means.
MAX_NESTING_DEPTH = 3

# What a money figure is rounded to when it reaches a person. Unit costs are not rounded here —
# `0.1489` per ml is already four places and two would make it `0.15`, a 0.7% error on every gram
# of gravy in the restaurant.
_RUPEES = Decimal("0.01")


class RecipeCycleError(AppError):
    """A preparation that, through some chain, contains itself."""

    def __init__(self, chain: Sequence[str]) -> None:
        super().__init__(
            "recipe.cycle",
            "That would make a preparation contain itself: " + " → ".join(chain) + ".",
            details={"chain": list(chain)},
            status_code=422,
        )


class RecipeTooDeepError(AppError):
    """More than three levels of nesting (ADR 0006)."""

    def __init__(self, chain: Sequence[str]) -> None:
        super().__init__(
            "recipe.too_deep",
            f"Recipes may nest {MAX_NESTING_DEPTH} levels deep. This one goes further: "
            + " → ".join(chain)
            + ".",
            details={"chain": list(chain), "limit": MAX_NESTING_DEPTH},
            status_code=422,
        )


@dataclass(frozen=True, slots=True)
class Component:
    """A stock item as the cost engine needs it — no ORM, so this is testable with literals.

    `price` is per *base unit*: rupees per gram, per ml, or per piece. The purchase-unit conversion
    (`1 kg = 1000 g`) happens once when a price is recorded, not here.
    """

    id: uuid.UUID
    code: str
    kind: str
    base_unit: str
    # Ingredients only. A preparation's cost comes from its own lines.
    price: Decimal | None = None
    yield_factor: Decimal | None = None
    # Preparations only.
    batch_yield: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Line:
    component_id: uuid.UUID
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class CostedLine:
    """One line of a breakdown. The *breakdown* is the product, not the total.

    "Butter Chicken costs ₹126.70" tells an owner nothing they can act on. "₹126.70, of which ₹62.15
    is the chicken tikka and ₹40.20 the makhani gravy" tells them where to look when it moves.
    """

    component_id: uuid.UUID
    code: str
    quantity: Decimal
    unit_cost: Decimal
    cost: Decimal


@dataclass(frozen=True, slots=True)
class Cost:
    total: Decimal
    lines: tuple[CostedLine, ...]

    @property
    def rupees(self) -> Decimal:
        """The total, rounded for display. Only ever called at a boundary."""
        return self.total.quantize(_RUPEES)


class CostEngine:
    """Costs recipes against a fixed snapshot of components and recipe lines.

    Takes plain mappings rather than a session: the arithmetic is the part that must be right, and
    tying it to the ORM would mean it could only be tested through a database. The repository loads
    everything in two queries and hands it here.
    """

    def __init__(
        self,
        components: Mapping[uuid.UUID, Component],
        # Lines of the *current* recipe that produces each preparation, keyed by the stock item it
        # produces. A preparation with no current recipe costs nothing and says so.
        preparation_lines: Mapping[uuid.UUID, Sequence[Line]],
    ) -> None:
        self._components = components
        self._preparation_lines = preparation_lines
        self._memo: dict[uuid.UUID, Decimal] = {}

    # ------------------------------------------------------------------ public

    def unit_cost(self, component_id: uuid.UUID) -> Decimal:
        """Cost of one base unit of a component: per gram, per ml, or per piece."""
        return self._unit_cost(component_id, ())

    def cost_of(self, lines: Iterable[Line]) -> Cost:
        """A recipe's cost, line by line.

        The lines are costed independently, so one preparation appearing twice is memoised rather
        than walked twice — which is the whole reason the menu-wide cost screen is affordable.
        """
        costed: list[CostedLine] = []
        total = Decimal(0)
        for line in lines:
            component = self._require(line.component_id, ())
            unit = self._unit_cost(line.component_id, ())
            cost = line.quantity * unit
            costed.append(
                CostedLine(
                    component_id=line.component_id,
                    code=component.code,
                    quantity=line.quantity,
                    unit_cost=unit,
                    cost=cost,
                )
            )
            total += cost
        return Cost(total=total, lines=tuple(costed))

    def check_depth_and_cycles(
        self, lines: Iterable[Line], *, owner_code: str, owner_is_preparation: bool
    ) -> None:
        """Refuse a recipe that would nest too deep or contain itself, **before** it is saved.

        ADR 0006 asks for this in the service *and* at save time. Costing would raise the same
        errors, but only when somebody asked for a cost — which could be weeks later, and by then
        the recipe is in use.

        **`owner_is_preparation` is what keeps this check honest.** The owner's code goes into the
        chain either way, because a preparation whose recipe contains itself is a cycle and the
        chain is how that is seen. But it must only count toward the *depth* when the owner really
        is a preparation: a dish is not a level of nesting. Counting it made this one level stricter
        than `cost_of` and than `seed/validate.py` — so a legitimately three-deep recipe was refused
        at save time and would have costed perfectly well, and the seed the product ships accepted
        what its own API rejected. Found by the M03/M04 review.
        """
        depth = 1 if owner_is_preparation else 0
        for line in lines:
            self._walk(line.component_id, (owner_code,), depth=depth)

    # ------------------------------------------------------------------ internals

    def _require(self, component_id: uuid.UUID, chain: tuple[str, ...]) -> Component:
        component = self._components.get(component_id)
        if component is None:
            raise AppError(
                "recipe.unknown_component",
                "A recipe line points at something that is not a stock item.",
                details={"component_id": str(component_id), "chain": list(chain)},
                status_code=422,
            )
        return component

    def _unit_cost(self, component_id: uuid.UUID, chain: tuple[str, ...]) -> Decimal:
        component = self._require(component_id, chain)

        if component.kind == "ingredient":
            # Rule 1. `yield_factor` defaults to 1 in the schema, so a missing profile costs the
            # raw price rather than crashing — an ingredient with no profile is incomplete data,
            # not a reason to refuse to show a menu.
            price = component.price or Decimal(0)
            yield_factor = component.yield_factor or Decimal(1)
            return price / yield_factor

        if component.code in chain:
            raise RecipeCycleError([*chain, component.code])
        if len(chain) >= MAX_NESTING_DEPTH:
            raise RecipeTooDeepError([*chain, component.code])

        if component_id in self._memo:
            return self._memo[component_id]

        # Rule 3. A preparation with no current recipe costs nothing — which is visible as a zero
        # on the cost screen rather than as an exception on an unrelated request.
        lines = self._preparation_lines.get(component_id, ())
        batch_yield = component.batch_yield or Decimal(1)
        total = Decimal(0)
        for line in lines:
            # Rule 2, and the recursion. The chain grows by this preparation, so a cycle three hops
            # away is still caught and the error can name the whole path.
            total += line.quantity * self._unit_cost(line.component_id, (*chain, component.code))
        unit = total / batch_yield
        # Memoised *after* the walk, so a cycle raises rather than caching a half-computed zero.
        self._memo[component_id] = unit
        return unit

    def _walk(self, component_id: uuid.UUID, chain: tuple[str, ...], *, depth: int) -> None:
        """Depth and cycle check with no arithmetic, for the save path.

        `depth` is carried separately from `len(chain)` because the two count different things:
        the chain exists to name a cycle and so includes the owner, while the depth must match what
        `_unit_cost` counts, which is preparations only.

        Deliberately not memoised: the memo is keyed by component and says nothing about the chain
        that reached it, so reusing it here would skip exactly the paths this is checking.
        """
        component = self._require(component_id, chain)
        if component.kind != "preparation":
            return
        if component.code in chain:
            raise RecipeCycleError([*chain, component.code])
        if depth >= MAX_NESTING_DEPTH:
            raise RecipeTooDeepError([*chain, component.code])
        for line in self._preparation_lines.get(component_id, ()):
            self._walk(line.component_id, (*chain, component.code), depth=depth + 1)


def food_cost_percentage(cost: Decimal, price: Decimal) -> Decimal | None:
    """Cost as a percentage of the pre-tax price, to one decimal place.

    `None` rather than an exception at a price of zero: a complimentary side is a real menu line,
    and "food cost 0%" would be a lie while a crash would take down the whole screen for one row.
    """
    if price <= 0:
        return None
    return (cost / price * 100).quantize(Decimal("0.1"))
