# 0006 — Preparations (sub-recipes) are first-class

**Status:** Accepted · 2026-09-08 · Amends the recipe model in ADR 0002's scope

## Context
The vision doc models cost as `dish → recipe → ingredients` (§7):

> Butter Chicken: Chicken 250g, Cream 40ml, Tomato 100g, Butter 20g, Spices Xg

That is how a Western à-la-carte kitchen works. It is **not** how an Indian kitchen works.

An Indian kitchen is base-driven. In the morning the cook prepares 8 litres of makhani gravy, 6
litres of yellow gravy, 4 litres of white gravy, a batch of boiled rice, marinated chicken, and
fried onion (birista). Those bases then feed many dishes: one makhani gravy becomes Butter Chicken,
Paneer Makhani, Malai Kofta, Butter Paneer and Chicken Tikka Masala.

Flattening bases into dish recipes loses the three things that actually drive money:

1. **Where waste happens.** Leftover gravy at close is the largest single waste line in most Indian
   restaurants, and it is invisible in a flattened model — the ingredients look "consumed by dishes"
   that were never sold.
2. **The prep decision.** The daily question is not "how much chicken to buy" but "how much makhani
   gravy to make today". That decision has no home in a flattened model.
3. **Shelf life.** Raw cream lasts 7 days; makhani gravy made from it lasts 2. Shelf life belongs to
   the preparation, not only to the ingredient.

## Decision
Introduce **`preparation`** as a first-class entity that sits between ingredients and dishes.

```
ingredient ──< recipe_line >── preparation ──< recipe_line >── menu_item_variant
                                    │
                                    └── batch_yield, yield_unit, shelf_life_hours, station
```

- A `recipe_line` may reference **either** an `ingredient` or a `preparation`. Recipes nest.
- A preparation has a standard batch yield (e.g. 8 L), a shelf life in **hours**, and a station.
- Producing a batch writes movements: `consumption` of its inputs, `production` of the preparation.
  Preparations therefore hold stock and carry expiry exactly like ingredients do.
- Cost rolls up: preparation unit cost is derived from its inputs at production time and frozen on
  the batch. Dish food cost then sums ingredient lines and preparation lines uniformly.
- FEFO applies to preparation batches too — and matters far more there, since shelf life is hours.

Nesting is allowed but capped at **3 levels** (ingredient → prep → prep → dish), enough for
"birista → yellow gravy → dish" and shallow enough that cost rollup stays cheap and comprehensible.

## Alternatives rejected
- **Flatten bases into each dish** — the vision doc's implied model. Simpler, and wrong for this
  market. It would make the waste module report confident, useless numbers.
- **Model preparations as ingredients with a "made in-house" flag** — avoids a table, but then a
  preparation cannot have inputs, so cost rollup and production batches have nowhere to live.

## Consequences
- The recipe editor must handle nesting, and the UI must make it obvious when a line is a
  preparation rather than a raw ingredient.
- Cost rollup is recursive, so it is computed and cached at production time, not per query.
- **This unlocks the daily prep sheet** (`docs/waste-model.md`) — forecast covers → dish demand →
  preparation demand → "make 6L makhani today, not 10L". That is the highest-ROI waste feature in
  the product, and it is not possible without this entity.
