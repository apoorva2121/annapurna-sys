# M03 · Menu — Manual Test

**Module:** M03 · Menu · **Built:** 2026-09-12 · **Gate:** `make check` exit 0, 458 backend + 127
frontend tests.

Sign in as **owner@spicegarden.test**, **manager@spicegarden.test** or
**waiter@spicegarden.test** — passwords are in `seed/organization.yaml`. Run `make seed` first: the
menu is seeded now, so nothing here begins by hand-building one.

---

## What I already ran, and what still wants you

I drove the API and the browser through the mechanical steps, so your time goes on what a script
cannot do. **This is information, not permission to skip.** Every defect M03 found late was found
by doing something by hand after every automated check was green.

| Section | State |
|---|---|
| **A · the menu loads** | A1–A4 verified against the API. **A5–A6 want a browser** — reordering is where a wrong answer looks right |
| **B · the permission line** | B1 and B3 verified. **B2 is the one to do yourself**: sign in as the manager and confirm the price control is *absent*, not disabled |
| **C · codes are contracts** | Verified against the API. C2 still wants your eyes on the wording |
| **D · options** | D1–D2 verified. **D3, the bulk apply, is the highest-value step here** |
| **E · the tree and its cache** | Verified with `curl`. **E1 wants the browser's network tab**, which is the only place the 304 is visible as a person would experience it |
| **F · exploratory** | Not run. **Entirely yours**, and the most valuable ten minutes |

Short of time? Do **B2, D3, E1, C2** and the F charter. About twelve minutes.

**Before you start**, if the frontend shows a Vite overlay about `@radix-ui/react-select`: the
container's `node_modules` volume predates M02's dependencies. Renew it with
`docker compose up -d --build --force-recreate --renew-anon-volumes web`. This is a known trap
documented in `docker-compose.yml`; it is not an M03 defect.

---

## A · The menu loads

| # | Step | Expect |
|---|---|---|
| A1 | Sign in as **owner**, open **Menu** | Six sections: Veg Starters, Non-Veg Starters, Veg Main Course, Non-Veg Main Course, Rice & Breads, Chinese |
| A2 | Select **Non-Veg Main Course** | Six dishes, including Butter Chicken |
| A3 | Look at Butter Chicken's row | A **brown-red triangle** before the name, the code `BUTTER_CHICKEN` in grey, and `Half ₹320.00 · Full ₹470.00` |
| A4 | Look at any Veg Main Course row | A **green circle**. Different shape, not only a different colour |
| A5 | Press **↓** on Veg Starters | It swaps with the section below. Reload: the new order holds |
| A6 | Turn on **Show deactivated** | Nothing new appears — the seed deactivates nothing. Turn it off again |

**A3 and A4 together are the point.** The veg/non-veg mark is legally required on an Indian menu
and sits exactly on the red-green colour-blindness axis. If the only difference you can see between
them is the colour, that is a defect worth reporting.

---

## B · The permission line — *the section that matters most*

`seed/organization.yaml` gives a manager `menu.manage` and withholds `menu.price` by name. This is
where you check the product agrees.

| # | Step | Expect |
|---|---|---|
| B1 | As **owner**, open Butter Chicken | Each variant row has a **Change** button beside its price |
| B2 | Sign in as **manager**, open the same dish | **No Change button anywhere.** A blue note says changing a price needs the `menu.price` permission. The prices are still *visible* |
| B3 | As manager, change the dish's name and Save | Saves. A manager shapes the menu |

**B2 is the step to do properly.** A disabled button that fails on submit would be worse than
either extreme: it reads as a bug in the product rather than a boundary in it. What you should see
is a control that was never offered, and a sentence saying who can.

Also worth trying as the manager: the browser's dev tools, `PATCH /api/v1/staff/menu/variants/…`
with a new price. It must return **403**. The screen hiding the button is a courtesy; the server
refusing is the control.

---

## C · Codes are contracts

| # | Step | Expect |
|---|---|---|
| C1 | Open any dish as **owner** | **Dish code** is filled in and cannot be typed into |
| C2 | Read the hint under it | It explains *why* — the code is how a recipe finds this dish |
| C3 | Add a section with code `main_veg` | Refused: that code is taken (it is stored uppercase) |
| C4 | Add a section with code `desserts` | Created as `DESSERTS` — lowercase is accepted and normalised, not rejected |

**C2 is a judgement call and I want yours.** A read-only field with no explanation reads as an
oversight. Does the hint actually explain it, or does it read like developer justification?

---

## D · Options

| # | Step | Expect |
|---|---|---|
| D1 | Open **Menu → Options** (`/menu/options`) | Four groups from the seed: Spice level, Preparation preference, and two more |
| D2 | Look at Spice level | Mild, Medium, Spicy, Extra spicy — each with a blank price column, because they are free |
| D3 | Under **Apply to every dish in a section**, pick *Rice & Breads*, tick **Spice level**, Apply | "Applied to 7 dishes." Open a rice dish and confirm Spice level is now on it |
| D4 | Add an option "Extra cheese" at `40` to Add-ons | Appears as **+₹40.00** |
| D5 | Add an option "No rice" at `-20` | Appears as **−₹20.00** with a real minus sign, not a hyphen |

**D3 is the highest-value step in this script.** The menu stores options per dish so one dish can
opt out; nobody describes a menu that way. The bulk apply is the bridge, and it is the feature most
likely to be subtly wrong — check it did not also touch dishes in *other* sections.

---

## E · The tree and its cache

| # | Step | Expect |
|---|---|---|
| E1 | Open dev tools → Network, reload the menu screen, then reload again | The second `GET /menu` returns **304 Not Modified** with no body |
| E2 | Change something — a dish name — then reload | `GET /menu` returns **200** with a new `ETag` |
| E3 | Sign in as **waiter**, open `/menu` | The menu loads. A waiter who cannot read the menu cannot take an order |
| E4 | As waiter, try `/menu/options` | It loads read-only; no create controls do anything useful |

**E1 is why `restaurant.menu_version` exists.** The waiter app will load this on every start, on a
restaurant basement network. If you see 200 both times, the cache is not working and the test suite
missed it.

---

## F · Exploratory — ten minutes, your charter

Not a script. You know restaurants; I do not.

- **Build a dish the way a real owner would.** Add a section, add a dish to it, price it. Where did
  you hesitate? What did you expect to be able to do that you could not?
- **Try to break the sellability rule.** Deactivate a dish's only variant. Deactivate a section that
  still has dishes. Both should refuse *and say why in a sentence you would accept*.
- **Look at the prices.** `₹1,23,456.00` is Indian grouping. Does every price on every screen use
  it, or is there one that slipped through as `₹123,456.00`?
- **Read the empty states.** Select a section with no dishes. Does it tell you what will appear and
  how to make it appear, or does it just say nothing is there?
- **Is anything here slow?** The menu tree is the endpoint the waiter app will hit hardest.

---

## Known, and deliberate

- **Reordering is buttons, not drag.** Same deviation M02 recorded, same reasons — drag needs a
  library plus a keyboard path, and the buttons *are* the keyboard path. Backlogged.
- **A dish cannot be taken off for tonight only.** `is_active` is the lifecycle flag, not "we are
  out of paneer until the delivery arrives". A waiter will want this on day one. Deliberately
  deferred to M07, when M05 can derive availability from stock rather than a second manual flag
  disagreeing with the ledger. Backlogged.
- **No dish photographs.** `image_url` is a column with no upload path — that needs object storage,
  which is M16's.
- **No guest menu screen.** The `GET /menu` endpoint is already persona-aware (a diner would see no
  station, no prep time, no inactive rows), but the QR-code screen is M10's.
- **Recipes are not here.** M04. This module creates the variant a recipe attaches to.

## Known, and not yet decided — please read this one

**`POST /menu/items` needs `menu.price`, not `menu.manage`.** A manager therefore cannot create a
dish at all, even though they can edit every part of one afterwards. The reasoning: the create
request may carry variants, and a variant carries a price — so accepting it under `menu.manage`
would let a manager create a dish priced at ₹1 and walk around the boundary entirely.

The cost is real: a manager adding Friday's special has to ask the owner to create it, then can
edit everything else themselves. **Is that the right trade for a restaurant you know?** The
alternative is a create endpoint that accepts no variants, so a manager makes the dish and the
owner prices it — two steps, and a window where the dish exists unsellable.

I do not think I can answer this from inference. You can.
