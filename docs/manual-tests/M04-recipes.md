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
| D2 | Open the **Recipe** link on that row, raise the ghee quantity, **Save this recipe** | Saves, and the version number above the table goes up by one |
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
| E3 | As the chef, open **Ingredients & preparations** | Works — grams, shelf lives, batch yields. **There is no cost column at all**, not a column of dashes |
| E4 | As the **manager**, try `POST /api/v1/staff/recipes` | **403.** A manager may read a recipe and not change it |
| E5 | As the chef, open any dish's **Recipe** | Works, and shows not one rupee figure anywhere on the page |
| E6 | Sign in as **kitchen staff**, open the same recipe | Readable, and every save and remove control is gone — with a sentence saying why |

**This split is from your own P1 design**, not my invention. `seed/organization.yaml` says it in a
comment on the chef role: *"NOT granted: any price, cost or financial permission. A chef sees grams,
not rupees."* And the manager gets `recipe.view` without `recipe.manage`.

So the person who writes the recipe cannot see the margin, and the person who sees the margin
cannot change the recipe that produces it. **Is that separation right for a restaurant you know?**
It is a real constraint on a small kitchen where the chef and the manager may be the same
conversation, and I would rather hear now than after the pilot.

---

## E2 · The recipe editor — *new, and the screen M04 first shipped without*

| # | Step | Expect |
|---|---|---|
| R1 | As the **chef**, open **Dish costs** → any row → **Recipe** | The lines, each with its own unit beside the number |
| R2 | On a dish matched from the library | "Nobody has checked these quantities", with the reason |
| R3 | Press **Confirm these quantities** | The banner becomes "Confirmed by a chef" and the button goes |
| R4 | Add the same ingredient that is already on the recipe | Refused, in a sentence, **before** anything is sent |
| R5 | Add an ingredient with quantity `0` | Refused the same way |
| R6 | Remove every line and save | "A recipe needs at least one ingredient" — nothing is sent |
| R7 | Open a dish that has never had a recipe | "No recipe yet", an empty table, and the add row ready |
| R8 | Change a quantity in place, without saving | The **Confirm** button greys out, and says why |
| R9 | Clear a quantity entirely and press Save | Refused, and nothing is sent |

**R7 is the one worth dwelling on.** A dish with *no* recipe and a dish with an *empty* recipe are
different things: the first is uncosted and the second costs nothing to make. The cost screen's
whole honesty rests on never confusing them, so the editor opens empty rather than inventing a
zero-line recipe.

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
- **The recipe editor now exists** — section E2 above. It was deferred on the grounds that ADR 0006
  asks it to "make it visually obvious when a line is a preparation vs a raw ingredient" and that
  deserved a design pass; the M03/M04 review pointed out that deferring it left a chef with no way
  to write a recipe at all, which is the module's own headline. The obviousness ADR 0006 asks for is
  a word beside every line saying *Bought in* or *Made here*, and the unit beside every number.
  Re-read that pair with a real kitchen in mind — it is the part most likely to be not quite enough.
- **`stock_item.current_unit_cost` is today's price, not history.** Finding S16 flags reading it for
  a past order; `recipe.unit_cost` is frozen per version for exactly that.
- **No stock movements, batches or counts.** M05.

## S15 — answered, and here is the arithmetic behind the answer

**You chose (a): the arithmetic stays.** `docs/schema.md` §4 now carries the sentence that removes
the ambiguity, and every golden figure stands. The reasoning is kept because the number it protects
is the one the pitch quotes.

The finding said `yield_factor` should not apply to counted ingredients. Its example is `EGG 0.88`
and `LEMON 0.90`.

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

The status quo is what shipped. Switching later would cost only the recomputation.
