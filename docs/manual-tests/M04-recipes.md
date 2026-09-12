# M04 · Stock Items & Recipes — Manual Test

**Module:** M04 · **Built:** 2026-09-12 · **Gate:** `make check` clean.

Run `make seed` first. The demo restaurant now has 61 ingredients, 11 preparations and a recipe for
every dish — so this script starts from a kitchen, not from an empty table.

**This is the module the product is for.** Before it, the database knew what a restaurant sells and
what it charges. After it, it knows what a dish *costs*, which is the number the pilot restaurant
has never had. Section B is the one to do properly.

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · the number** | Verified against the API **and** against `seed/validate.py`. A2 still wants your eyes: check the arithmetic against a calculator, as `docs/modules.md` asks |
| **B · the day-1 screen** | Verified. **Entirely yours in spirit** — this is the screen the pitch rests on, and whether it is *convincing* is not something a test can assert |
| **C · what uses this** | Verified. C2 wants a browser |
| **D · versions** | Verified against the API |
| **E · the permission line** | Verified. **E2 is the one to do yourself**: sign in as the chef and confirm the cost screens are simply not there |
| **F · exploratory** | Not run. Yours |

Short of time? Do **A2, B1, E2** and the F charter. Ten minutes.

---

## A · The number

| # | Step | Expect |
|---|---|---|
| A1 | Sign in as **owner**, open **Dish costs** (`/costs`) | 36 rows, worst food cost first |
| A2 | Find **Butter Chicken · Full**. Press **Breakdown** | Cost **₹126.70**, price ₹470.00, food cost **27.0%**. The breakdown lists `PREP_MAKHANI`, `PREP_CHKN_TIKKA`, `BUTTER`, `CREAM`, `KASURI`, `CORIANDER` |
| A3 | Run `python seed/validate.py` in a terminal | Same figure: `BUTTER_CHICKEN/FULL … cost 126.70 … 27.0%` |
| A4 | Open **Ingredients & preparations** → filter **Made here** → look at Makhani gravy | Cost per unit ≈ **₹0.15** per ml (the validator prints 0.1489) |

**A2 and A3 together are the point.** Two independent implementations of one calculation — the
validator that has guarded the seed since M00, and the service — and they agree to the paisa. A
test asserts it on every build; doing it by hand once is what makes you believe the test.

`docs/modules.md` asks you to "build a recipe by hand, confirm the cost matches a calculator". Do
that in section F.

---

## B · The day-1 screen — *this is the pitch*

| # | Step | Expect |
|---|---|---|
| B1 | Read the top of **Dish costs** | **Chilli Paneer at ~46%** is the worst row |
| B2 | Read the summary figures | Average food cost, dish count, and how many have no recipe (0 in the seed) |
| B3 | Look for a "High" tag | On Chilli Paneer, as a **word** and not only a colour |

**B1 is the demo.** `seed/menu.yaml` plants Chilli Paneer at ~46% food cost deliberately — "sells
well, earns almost nothing" — and the whole point of this screen is that an owner sees it in the
first five seconds without being told where to look.

**The question I actually want your answer on:** would this screen change what the pilot restaurant
does on Monday? If it only makes them nod, something is missing from it, and I would rather find
that out from you than from them.

---

## C · What uses this

| # | Step | Expect |
|---|---|---|
| C1 | Open **Ingredients & preparations**, find **Cashew**, press **What uses this** | Preparations include **Makhani gravy** and **White gravy** |
| C2 | In the same panel, read the **Dishes** list | **Butter Chicken is there** — even though its recipe contains no cashew directly |

**C2 is the one worth checking.** Butter Chicken contains makhani gravy, and the gravy contains
cashew. A single query over recipe lines finds the gravy and misses the dish, which is the answer
nobody wanted. If Butter Chicken is missing here, the walk is broken.

---

## D · A recipe is never edited

| # | Step | Expect |
|---|---|---|
| D1 | Open **Jeera Rice**'s cost breakdown, note the figure | Around ₹42 |
| D2 | Through the API, `POST /api/v1/staff/recipes` with that variant and a larger ghee quantity | 201, `version: 2` |
| D3 | Re-open the cost | It has moved |
| D4 | `GET /api/v1/staff/recipes/{the version-1 id}` | Still there, `is_current: false`, **its lines unchanged** |

**D4 is the rule.** M07 will cite a recipe version on every order line, so a version whose lines
moved would restate what every past order cost. There is no edit endpoint at all — that is not an
oversight, it is the design.

---

## E · Who sees grams and who sees rupees

| # | Step | Expect |
|---|---|---|
| E1 | Sign in as **manager**, open **Dish costs** | Works. A manager sees margins |
| E2 | Sign in as **chef** (`chef@spicegarden.test`), try `/costs` | **Refused.** The chef sees no rupees anywhere |
| E3 | As the chef, open **Ingredients & preparations** | Works — grams, shelf lives, batch yields |
| E4 | As the **manager**, try `POST /api/v1/staff/recipes` | **403.** A manager may read a recipe and not change it |

**This split is from your own P1 design**, not my invention. `seed/organization.yaml` says it in a
comment on the chef role: *"NOT granted: any price, cost or financial permission. A chef sees grams,
not rupees."* And the manager gets `recipe.view` without `recipe.manage`.

So the person who writes the recipe cannot see the margin, and the person who sees the margin
cannot change the recipe that produces it. **Is that separation right for a restaurant you know?**
It is a real constraint on a small kitchen where the chef and the manager may be the same
conversation, and I would rather hear now than after the pilot.

---

## F · Exploratory — ten minutes, your charter

- **Build a recipe by hand and check it against a calculator.** `docs/modules.md` asks for this
  specifically. Pick a dish with a preparation in it, so the nesting is exercised.
- **Try to break the nesting rules.** Make a preparation contain itself, directly or through two
  hops. Both should refuse *and name the chain* — "there is a cycle" is not actionable.
- **Change an ingredient price and watch the menu move.** Put paneer up 20% and see which dishes
  change and by how much. That is the loop the product sells.
- **Look for a number that is wrong.** You know these dishes. If any cost looks implausible, that is
  the most valuable thing you can find in this whole module.

---

## Known, and deliberate

- **The starter library is not loaded yet.** `library/` has 223 dishes and M04 builds the shape they
  load into; the matching flow — *"your menu has Butter Chicken, here's a standard recipe"* — is an
  onboarding screen, and designing onboarding before one restaurant has been onboarded is guessing.
  `recipe.source` and `recipe.confirmed_at` ship here so that flow has somewhere to land.
- **No recipe editor screen.** The API is complete and tested; the editor UI is deferred, because
  ADR 0006 asks it to "make it visually obvious when a line is a preparation vs a raw ingredient"
  and that deserves a design pass rather than a table. Backlogged. The seed and the API cover every
  recipe path meanwhile.
- **`stock_item.current_unit_cost` is today's price, not history.** Finding S16 flags reading it for
  a past order; `recipe.unit_cost` is frozen per version for exactly that.
- **No stock movements, batches or counts.** M05.

## Known, and not yet decided — *please read this one*

**Finding S15 says `yield_factor` should not apply to counted ingredients, and I think that is
wrong.** The audit's example is `EGG 0.88` and `LEMON 0.90`.

A recipe needing 3 eggs, priced ₹7 each:

| | Cost | Assumes |
|---|---|---|
| **Today** | `3 / 0.88 × 7` = **₹23.86** | 12% of eggs bought are cracked or bad |
| **S15's fix** | `3 × 7` = **₹21.00** | Eggs never break |

Breakage is real and costs money; "buy 341 to use 300" is right over a month. What S15 is probably
pointing at is an ambiguity in the *data*: `LEMON 0.90` could mean "one lemon in ten is bad" or "you
get 90% of the juice", and if the recipe already says `0.25` lemons the second reading
double-counts.

**Measured:** implementing S15 as written drops Butter Chicken Full from ₹126.70 to **₹122.54** and
moves the weighted food cost off 25.6% — the figures `docs/modules.md` names as this module's
golden tests, and the number the pitch quotes.

I have built the status quo and left the decision to you, because changing the product's headline
food-cost figure on a finding I believe is mistaken, while you were away, is not a thing to do
quietly. Switching later costs only the recomputation.
