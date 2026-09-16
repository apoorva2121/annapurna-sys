# M04 · Stock Items & Recipes — Module Spec

**Status:** **APPROVED.** S15 was the one open question and it is answered: **(a)**, keep the
arithmetic and fix the ambiguity in the data. `docs/schema.md` §4 now carries the defining sentence.
Every golden figure stands as `docs/modules.md` names it — Butter Chicken Full ₹126.70, makhani
gravy ₹0.1489/ml, weighted food cost 25.7%.
**Estimate:** 5 days · **Depends on:** M03 (built; manual pass pending)
`docs/modules.md` calls this "the heart of the product. Everything commercially interesting depends
on this being right."

---

## Scope

This is the module the product is *for*. Until now the database knows what a restaurant sells and
what it charges; after this it knows what a dish **costs**, which is the first number an owner has
never had. Three things here are not CRUD:

1. **The cost rollup is recursive and must agree with `seed/validate.py` to the paisa.** Two
   implementations of one calculation exist the moment this module ships — the validator that has
   guarded the seed since M00, and the service. `docs/modules.md` names the golden figures:
   Butter Chicken Full = **₹126.70**, makhani gravy = **₹0.1489/ml**, popularity-weighted food cost
   = **25.7%**. A test asserts all three against the running service. If they ever disagree, one of
   them is lying about the number this product sells.
2. **An ingredient and a preparation are the same kind of thing.** ADR 0006's central move: both
   hold stock, both expire, both have a cost, so they share one `stock_item` identity and
   `recipe_line.component_id` is a single clean foreign key instead of a nullable pair. That is what
   lets recipes nest.
3. **A recipe change must not move a past order's cost.** Recipes are versioned; `order_line` (M07)
   cites the version that was current when the line was added. A reprice of history is the same
   class of error as an edited tax rate, and has the same answer.

## Not in scope

- **Stock movements, batches, counts.** M05. This module gives them the `stock_item` to point at.
- **Purchase orders and supplier pricing.** M06.
- **Bill-to-ledger / the `indian-fnb-lexicon`.** A separate package with its own brief.
- **Loading `library/` into a restaurant.** The library exists (223 dishes, built 2026-09-12) and
  M04 builds the *shape* it will load into. The matching flow — "your menu has Butter Chicken,
  here's a standard recipe" — is an onboarding screen, and doing it now would mean designing
  onboarding before a single restaurant has been onboarded. See *Inherited obligations*.
- **Waste and variance.** M09 and M13. This module produces the *theoretical* half of invariant 7.

---

## Deliverables

### Migration — 5 tables (`docs/schema.md` §4)

`stock_item`, `ingredient_profile`, `preparation_profile`, `recipe`, `recipe_line`, as specified.
Plus:

- **`stock_item.category` CHECK covering eight values, not six.** `docs/schema.md` §4 comments
  `meat|dairy|veg|grain|spice|oil`; `library/validate.py` already validates against those plus
  `bakery` and `sweet`, and `library/ingredients.yaml` uses both (pav, bread, brownie; honey,
  jaggery, chocolate sauce). A CHECK with six values would refuse the product's own starter
  library on first load. The schema doc is updated to match.
- **`recipe.unit_cost numeric(14,6)`** — see decision 3.

`downgrade()` implemented and tested up→down→up with data, as 0008 was.

### The cost engine — the part that matters

One module, `app/services/costing.py`, and it is the only place the arithmetic exists.

```python
def prep_unit_cost(code) -> Decimal   # cost per 1 base unit of a preparation's yield
def line_cost(component, quantity) -> Decimal
def dish_cost(variant) -> DishCost    # per-line breakdown, not just a total
```

Four rules, each of which `seed/validate.py` already implements and which this must match:

1. **An ingredient line costs `quantity / yield_factor × price`.** The division is the trim loss:
   to *use* 720 g of chicken you must *buy* 1 kg, and the dish costs the kilo.
2. **A preparation line costs `quantity × prep_unit_cost(preparation)`.** Recursive.
3. **A preparation's unit cost is `Σ(line costs) / batch_yield`.** Birista yields 1200 g from
   4000 g of onion, and that loss is the point.
4. **Depth is capped at 3 and cycles are refused**, at save time *and* in the service (ADR 0006).

**Memoised per request, not cached across them.** A dish-cost screen asks for forty dishes, each
resolving the same makhani gravy; without memoisation that is forty identical recursive walks. With
a cross-request cache it is a stale number the day an ingredient price changes. Finding X8 asks for
both memoisation and persistence — see decision 3 for where the persisted copy goes.

**`Decimal` throughout, quantised only at the boundary.** Intermediate values keep full precision;
`numeric(14,6)` is the column and six places is what a per-gram cost needs (`0.1489` per ml of
gravy is already four).

### Backend

```
GET    /stock-items                        list, filter by kind and category
POST   /stock-items                        an ingredient or a preparation
GET    /stock-items/{id}
PATCH  /stock-items/{id}
GET    /stock-items/{id}/used-by           "what uses paneer?" — the reverse index
GET    /recipes/{id}
POST   /recipes                            for a variant, or for a preparation
POST   /recipes/{id}/version               a change is a new version, never an edit
GET    /menu-items/{variant_id}/cost       the breakdown, line by line
GET    /menu/costs                         every dish's cost and margin — the day-1 screen
```

**`GET /stock-items/{id}/used-by` is not a convenience.** `docs/modules.md` lists it, and
`docs/schema.md` §4 puts an index on `recipe_line.component_id` specifically to answer it. It is
what makes "paneer went up 12%, here are the nine dishes that changed" possible, and it is the
question an owner asks first.

**Permissions**, from `seed/organization.yaml`'s P1 design, which — as M03 learned — has already
thought about this:

| Code | Held by | Why |
|---|---|---|
| `recipe.view` | manager, chef, kitchen_staff, store_manager | A chef reads recipes. That is the job |
| `recipe.manage` | owner, chef | The chef owns the recipe. Not the manager: the design gives a manager `recipe.view` and stops there |
| `cost.view` | owner, manager | Rupees. The design's comment on `chef` is explicit: **"a chef sees grams, not rupees"** |

That last line is the interesting one and it shapes the API: **the recipe editor and the cost
screen are different surfaces behind different permissions**, because the person who owns the
recipe is deliberately not shown what it costs.

### Frontend

- **`StockItemsScreen`** — the ingredient and preparation master, one list with a kind filter.
- **`RecipeEditorScreen`** — the recipe for a variant or a preparation. ADR 0006: *"the recipe
  editor must make it visually obvious when a line is a preparation vs a raw ingredient"*, because
  a line that looks the same but nests is how someone creates a cycle without noticing.
- **`DishCostScreen`** — the day-1 screen the audit asked for, behind `cost.view`. Cost, price,
  food-cost %, margin, per dish, sorted worst-first. `docs/audit/…findings.md`: *"Build the day-1
  dish-margin screen in M04, not M13."*
- **`UsedByPanel`** — "what uses this ingredient?", on the stock item.

### Seed

`seed/ingredients.yaml` (61), `seed/preparations.yaml` (11) and the recipes embedded in
`seed/menu.yaml` all load. After this, `make seed` produces a restaurant whose food cost can be
computed — which is the first moment this product does the thing it is for.

---

## Schema review checklist (guardrail G-13)

**1 · What metric will someone want from this row in M13/M17, and which timestamp does it need?**
`recipe.version` + `effective_from` are the timestamps that matter: M13 asks "what did this dish
cost *in March*", and the answer is the version live in March, not today's. `recipe_line` needs no
timestamp of its own — it is immutable once its version is current, because a new version is how a
line changes. `stock_item.current_unit_cost` is a *cache* and M13 must never read it for a
historical question; the batch cost (M05) is the truth for what was actually consumed.

**2 · Where did this row come from?** Three sources and they will diverge: typed by a chef, seeded,
or **matched from `library/dishes.yaml` during onboarding**. The third is the one that matters.
`library/PROVENANCE.md` says most of the library is `estimated` — a chef has not confirmed it — so a
matched recipe must not look like a confirmed one. **`recipe.source` (`typed` / `seeded` /
`library`) and `recipe.confirmed_at`** are added for this: an unconfirmed recipe is a proposal, and
the dish-cost screen must be able to say "this number rests on a recipe nobody has checked". Without
the column, M04 ships a cost figure with false confidence, which is the exact failure the library's
own confidence tiers exist to prevent.

**3 · Is this row a legal document?** No. Cost is internal. The *invoice* cites price and tax
(M03, M07), not cost.

**4 · Does a modifier / option / variant change consumption?** **A variant does and is handled** —
`recipe.menu_item_variant_id` means Half and Full are separate recipes, which is why price lives on
the variant. **A modifier does and is not**, and this is M03's inherited obligation landing: "extra
cheese" is 40 g of cheese that no recipe accounts for. The `recipe` CHECK is
`num_nonnulls(menu_item_variant_id, produces_stock_item_id) = 1`. **Decision 2 below.**

**5 · What does a human count at close?** Not here — M05's `stock_count`. But this module decides
what is *countable*: every `stock_item`, ingredient and preparation alike, which is ADR 0006's whole
point. A preparation that could not be counted would make the prep-waste line invisible, and
`docs/waste-model.md` calls that the largest waste line in the restaurant.

**6 · Is the derived number O(N) forever?** **Yes, and it is the risk in this module.** Dish cost is
a recursive walk; a menu-wide cost screen is that walk per dish. Memoised per request it is one walk
per *preparation*, not per dish. A query-count test asserts the menu cost screen does not scale with
the menu, exactly as M03's tree test does.

**7 · Which tier of ADR 0008 deletion, and is `restaurant_id` on the row?** `stock_item` and the two
profiles are master data — deactivated, never deleted. **`recipe` is different: it is never
deactivated *or* deleted**, because an order from last year cites a version and that version must
resolve forever. `is_current` moves; rows do not go away. `recipe_line` has no `restaurant_id` —
like M03's join table, its parent carries one — and the service checks both sides.

**8 · What would an insider do with this row?** Below.

## Threat question — *what would an insider do with this?*

| Attack | Control |
|---|---|
| **A chef inflates a recipe's quantities** so theoretical consumption matches the stock they are removing, hiding the shortfall | Recipe changes are versioned and audited with an actor. A quantity that moves without a reason is visible as a version diff — and `recipe.manage` is held by owner and chef only |
| **A recipe is edited rather than versioned**, silently restating what every past order cost | There is no edit path. `POST /recipes/{id}/version` is the only write, and the old version keeps its rows |
| A manager reads dish margins they are not meant to see | `cost.view` is owner and manager per the P1 design; `recipe.view` does not imply it. **A chef holds `recipe.manage` and not `cost.view`** — "a chef sees grams, not rupees" |
| **`yield_factor` is quietly raised** so food cost looks better without anything changing in the kitchen | Audited, and M05's actual-vs-theoretical variance is what catches it — a yield that does not match reality shows up as a variance that will not close |
| A competitor's recipes are read across tenants | `RestaurantScopedRepository`, the four generic suites, and `recipe_line`'s explicit both-sides check |
| **A preparation references itself** through three hops, and the cost walk never terminates | Depth cap enforced in the service *and* at save time (ADR 0006); a cycle test exists in both `seed/validate.py` and the service |

---

## S15 — answered: (a)

**Answered.** Option (a): the arithmetic stays, and `docs/schema.md` §4 gained the sentence that
removes the ambiguity. The reasoning below is kept as the record of why, because the number it
protects is the product's headline food cost and a future reader will want to know it was a choice.

`docs/audit/remediation-plan.md` assigns M04: *"S15 `yield_factor` on `unit`-based ingredients
(`EGG 0.88`, `LEMON 0.90`) inflates cost by count → yield applies to weight only."*

I do not think that fix is right, and implementing it silently would change the number this product
sells. Here is the arithmetic.

A recipe needs **3 eggs**. `EGG` is `base_unit: unit`, `price: 7.00`, `yield_factor: 0.88`.

| | Cost | What it assumes |
|---|---|---|
| **Today** (yield applies) | `3 / 0.88 × 7.00` = **₹23.86** | 12% of eggs bought are cracked or bad, so using 3 means buying 3.41 |
| **S15's fix** (weight only) | `3 × 7.00` = **₹21.00** | Eggs never break |

**The current behaviour is arithmetically correct.** Breakage is real, it costs money, and over a
month "buy 341 to use 300" is exactly right. You cannot buy 0.41 of an egg, but that is a rounding
question at the purchase counter, not a costing error.

**What S15 is probably actually pointing at is an ambiguity in the data, not the code.** For a
weight-based ingredient, yield loss happens *inside* each unit — you buy a kilo of chicken and trim
280 g of bone off it. For a count-based one it happens *between* units — the egg is fine or it is
not. Both divide identically, but `LEMON` at `0.90` is genuinely unclear: does it mean "one lemon in
ten is bad", or "you only get 90% of the juice out"? If the recipe already says `0.25` *lemons*, the
second reading double-counts.

**My recommendation: (a).**

| | **(a) Keep the arithmetic, fix the ambiguity** *(recommended)* | **(b) Implement S15 as written** |
|---|---|---|
| Change | `yield_factor` keeps applying to every unit. `docs/schema.md` gains one sentence defining it as *"the fraction of what you buy that reaches the pan — trim loss for weight, breakage and spoilage for count"* | `yield_factor` is ignored when `base_unit = 'unit'` |
| Butter Chicken Full | stays **₹126.70** | **₹122.54** — measured, by running the engine with yield disabled. A 3.3% understatement on the product's headline dish |
| Weighted food cost | stays **25.6%** | falls, and `docs/seed-data.md`'s ~26% target moves with it |
| Egg breakage | costed | free |
| Golden tests | pass as `docs/modules.md` specifies them | every golden figure has to be recomputed and the module's headline test rewritten against numbers nobody has validated |
| Cost | one doc sentence | a coordinated edit across `seed/validate.py`, the service, the seed docs and the audit plan |

(b) would have meant changing the product's headline food-cost figure on a finding I think is
mistaken. **(a) was chosen**, so the code is the status quo, the one doc sentence is written, and
the golden tests are the ones `docs/modules.md` already names. Switching to (b) later would cost the
recomputation and nothing else.

## Decisions I have made

**1 · S11 — org-level recipe master: deferred, deliberately.** The finding says `stock_item`/`recipe`
per restaurant means "chains re-enter everything", and proposes an org-level master with
per-restaurant overrides. **Not now.** An override layer is a second source of truth for every
quantity, and the problem it solves — a chain re-entering recipes — is solved better and *already*
by `library/`, which is a cross-restaurant catalogue with no tenancy at all. A second branch
onboards by matching the library, exactly as a new restaurant does. Revisit when a real chain has
two branches whose recipes genuinely must stay in lockstep; that is evidence, and "a chain might"
is not. Recorded in `docs/backlog.md` with that trigger.

**2 · A modifier gets a recipe, and the CHECK grows to three columns.** M03 handed this over and it
cannot wait: every modifier ordered makes theoretical consumption wrong, and invariant 7 says that
variance *is* the product. `recipe.modifier_id` joins the owner CHECK as
`num_nonnulls(menu_item_variant_id, produces_stock_item_id, modifier_id) = 1`. Most modifiers have
no recipe and never will ("mild" consumes nothing); the ones that do — extra cheese, extra portion —
are exactly the ones that move stock.

**3 · X8 — `unit_cost` persists on the recipe version, not only per request.** The finding asks for
"memoise per request; persist `unit_cost` on the recipe version and each production batch". The
per-batch half is M05's (ADR 0006 freezes cost at production time). The per-version half belongs
here: a recipe version is immutable, so its cost at the moment it became current is a fact worth
storing, and it is what M13 needs to answer "what did this dish cost in March" without replaying
March's ingredient prices. `stock_item.current_unit_cost` stays a cache and is never read for a
historical question — finding S16 already flags it as unsafe for that, and this column is what makes
ignoring it possible.

**4 · `stock_item.category` takes eight values.** `bakery` and `sweet` are added, because
`library/ingredients.yaml` already uses them and a six-value CHECK would refuse the starter library
on first load. `docs/schema.md` §4's comment is corrected rather than the library.

---

## Chunks

| # | Content | Ends with |
|---|---|---|
| **A** | Migration + models: 5 tables, the three-column CHECK, `recipe.unit_cost`, `source`, `confirmed_at` | up→down→up with data |
| **B** | `costing.py` + its tests **against the golden figures**, before any endpoint exists | ₹126.70, ₹0.1489/ml and 25.7% asserted |
| **C** | Repositories + service: stock items, profiles, `used-by` | Generic suites pass |
| **D** | Recipes: create, version, depth and cycle refusal at save time | A depth-4 recipe and a cycle both refused, by test |
| **E** | Cost endpoints + the menu-wide cost screen's query-count test | Cost of 400 dishes costs the same queries as 12 |
| **F** | Seed: ingredients, preparations, dish recipes | `make seed` yields a restaurant whose food cost computes |
| **G** | `StockItemsScreen` + `RecipeEditorScreen` (nesting made obvious) | Screens usable against the seed |
| **H** | `DishCostScreen` + `UsedByPanel` + manual script | `docs/manual-tests/M04-recipes.md` |

## Acceptance criteria

1. `prep_unit_cost('PREP_MAKHANI')` returns `0.1489` per ml, matching `seed/validate.py`
2. Butter Chicken Full costs **₹126.70** through the API
3. The popularity-weighted menu food cost is **25.7%**
4. A recipe nested four deep is refused at save time *and* by the service
5. A cycle is refused, and the refusal names the chain
6. Changing a recipe creates a version; the old version's lines are unchanged and still resolve
7. A dish's cost is unchanged by a later recipe version — asserted by computing it at both versions
8. The menu-wide cost screen issues the same query count for 12 dishes and 400
9. A chef holds `recipe.manage` and receives 403 on every `cost.view` route
10. `GET /stock-items/{id}/used-by` returns every variant and preparation consuming it, transitively
11. Every dish in `seed/` loads with its recipe and costs what the validator says
12. `make check` clean, zero warnings

## Risks

| Risk | Mitigation |
|---|---|
| **The service and `seed/validate.py` drift**, and the product's headline number depends on which one you ask | The golden test *is* the mitigation, and it runs in `make check`. It compares the service's answer to the figures in `docs/modules.md`, so a drift in either is a red build |
| Recursive cost with memoisation is subtly wrong in a way small fixtures hide | The seed has a genuine depth-3 chain (`ONION → PREP_BIRISTA → PREP_YELLOW → dish`) and it is in the golden test, not a synthetic fixture |
| **M03's manual pass is still outstanding, and M04 now builds on it too** | Unchanged from M03's own risk table, and the mitigation is the same twelve-minute short path. M04's backend does not touch M03's screens; chunk G is where that exposure would start |
| Scope creep from "while we are in recipes…" — the library matching flow, purchase prices, waste | Named in *Not in scope*. Everything that arrives goes to `docs/backlog.md` |

## Inherited obligations — handed to a later module

| Owed by | What | Why not here |
|---|---|---|
| **M05** | Freeze `unit_cost` on each production batch (ADR 0006) | `stock_batch` does not exist yet |
| **M05** | Stop reading `stock_item.current_unit_cost` as a historical cost (finding S16) | The recipe-version column added here is what makes that possible |
| **M07** | Cite the recipe *version* on `order_line`, not the recipe | Orders do not exist yet |
| **Onboarding (M16 or its own module)** | The library matching flow — "your menu has Butter Chicken, here is a standard recipe" | Designing onboarding before one restaurant has been onboarded is guessing. `recipe.source` and `confirmed_at` are the columns it will need, and they ship here |
