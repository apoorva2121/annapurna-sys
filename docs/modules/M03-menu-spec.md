# M03 · Menu — Module Spec

**Status:** **DRAFT — four open decisions at the end need your answer before chunk A.**
**Estimate:** 4 days (+0.5 if decision 1 is taken) · **Depends on:** M02 (done, manual pass pending)
**Gate:** M02's automated gate is clean. Its manual pass is deliberately deferred — see *Risks*.

---

## Scope

The menu is the spine of everything commercial. `order_line` points at a variant forever, `recipe`
hangs off a variant, every margin number in M13 and every menu-engineering verdict in vision §12
resolves through these six tables. It looks like CRUD. Three parts of it are not:

1. **`GET /menu` is the hottest endpoint in the product.** The waiter PWA loads it on every app
   start, on a restaurant basement network, and it is a three-level tree over ~220 dishes. A naive
   implementation is O(N) queries and a payload nobody can load on 3G. This gets the highest-effort
   attention in the module, the way `business_date_of` did in M02.
2. **`menu_item.code` is the join key to `library/`.** `library/dishes.yaml` and `seed/menu.yaml`
   both key on `BUTTER_CHICKEN`. That code is how M04's onboarding does *"match, don't create"*
   (`docs/onboarding-cold-start.md`). It is not decoration and it is not renameable.
3. **The variant is where price, tax and recipe all meet.** Getting its identity right is cheap now
   and expensive after M04 hangs recipes off it and M07 hangs order lines off it.

## Not in scope

- **Recipes.** M04. This module creates the variant a recipe will attach to, nothing more.
- **"86'd tonight" / today-only availability.** See *Known gaps*, which names the consequence.
- **Menu photography and image upload.** `image_url` is a column; filling it needs object storage
  and an upload path, which is M16's. Column ships, screen shows it read-only.
- **Menu engineering / dish scoring** (vision §11–12). Needs orders and recipes. M13.
- **Combos, meal deals, happy-hour pricing.** No table supports them; adding one now guesses at
  rules nobody has specified.
- **Modifier recipes.** "Extra cheese" consumes 40 g of cheese. The link belongs to M04's `recipe`
  table — see *Inherited obligations*, which is where M04 must pick it up.
- **Per-channel pricing** (dine-in vs delivery). Real, and out of month 1 (CLAUDE.md).

---

## Two schema defects found while planning

Both are the same shape as M02's tax finding, and both are cheapest to fix before the foreign keys
exist. Neither is a matter of taste.

### Defect 1 · `modifier_group` has no `code`, but the seed joins on one

`docs/schema.md` §3 gives `modifier_group` only `restaurant_id, name`. `seed/operations.yaml`
already uses codes as the join key:

```yaml
modifier_groups:
  - code: SPICE_LEVEL
    name: Spice level
modifier_attachments:
  - {categories: [MAIN_VEG, MAIN_NONVEG], groups: [SPICE_LEVEL, JAIN_PREF, ADDONS_GRAVY]}
```

Without a `code` column the seeder joins on the display name, so renaming "Spice level" to
"Heat level" silently breaks the attachment. Same class of bug M02 fixed by keeping `station.code`
immutable while the name is editable. **Fix: add `modifier_group.code`, unique per restaurant,
immutable after creation.** Small, and not really a decision — I will do this unless you object.

### Defect 2 · The seed attaches modifiers to *categories*; the schema attaches them to *items*

`menu_item_modifier_group` is per item. The seed says "all main courses get a spice level", which
is how an owner actually thinks and how any real menu is described.

These are not in conflict — they are a model/interaction mismatch, and the schema is right.
Per-item is strictly more expressive: one dish in MAIN_VEG can opt out of Jain preference because
it already has no onion. Per-category cannot express that.

**Resolution, no schema change:** the loader expands category → items at seed time, and the *UI*
offers "apply to every item in this category" as a bulk action. Storage is per item; the
interaction is per category. Recorded here because the next person to read the seed will think one
of the two files is wrong, and neither is.

---

## Deliverables

### Migration — 6 tables (`docs/schema.md` §3)

`menu_category`, `menu_item`, `menu_item_variant`, `modifier_group`, `modifier`,
`menu_item_modifier_group`, as specified, plus:

- `modifier_group.code text NOT NULL`, `UQ (restaurant_id, code)` — defect 1
- whatever decision 1 settles for the tax reference

`downgrade()` implemented and tested up→down→up.

### The menu tree endpoint — the part that matters

```
GET /menu        →  categories → items → variants, plus each item's modifier groups
```

Three properties, each asserted by a test rather than hoped for:

1. **Bounded query count.** Six queries, regardless of whether the menu has 12 dishes or 400.
   `assert_max_queries` already exists from M02 and this is what it was built for. A three-level
   tree plus a many-to-many is the textbook N+1; `docs/modules.md` names this as M03's headline test.
2. **Conditional GET.** `restaurant.menu_version` is an integer bumped by any menu write. The
   endpoint returns it as an `ETag`; a client sending `If-None-Match` gets `304` and no body. The
   waiter opening the app for the ninth time that shift transfers nothing. This is why the column
   exists — without it the cache in `docs/modules.md`'s "(full tree, cached)" is a client-side
   guess with no way to be right.
3. **Active-only by default.** `GET /menu` returns sellable rows. `GET /menu?include_inactive=true`
   is the manager's view. A waiter must never see a deactivated dish; a manager must always be able
   to find one to reactivate it.

### Backend — repository → service → API

```
GET    /menu                                  the tree, ETagged (waiter + manager)
GET    /menu/categories                       list, seq order
POST   /menu/categories
PATCH  /menu/categories/{id}                  rename, reorder, deactivate
GET    /menu/items                            list, filter by category, paginated
POST   /menu/items
PATCH  /menu/items/{id}                       name, description, station, category, deactivate
POST   /menu/items/{id}/variants              price lives here
PATCH  /menu/items/{id}/variants/{vid}
GET    /menu/modifier-groups                  list with their modifiers
POST   /menu/modifier-groups
PATCH  /menu/modifier-groups/{id}             name, min/max/required — never the code
POST   /menu/modifier-groups/{id}/modifiers
PATCH  /menu/modifier-groups/{id}/modifiers/{mid}
PUT    /menu/items/{id}/modifier-groups       set the whole attachment list, ordered
POST   /menu/categories/{id}/modifier-groups  bulk-apply to every item in the category
```

**Immutable after creation:** `menu_item.code`, `modifier_group.code`. Editable: everything a human
reads. This is M02's `station.code` rule, and the reason is the same — the code is a contract with
`seed/`, `library/` and every future recipe, while the name is a label.

**Mutable on purpose:** `menu_item_variant.price`. A menu price genuinely changes and must not be
effective-dated. History is protected structurally instead: `order_line` copies the price at the
moment the line is added (M07), so a reprice cannot rewrite a past bill. Price *history* is
derivable from `order_line` when M13 wants "did the reprice work?" — see schema checklist Q1.
**Do not "fix" this later by effective-dating prices.** It would double the tax-group machinery for
a question the order table already answers.

**Deletion follows ADR 0008** — deactivate, never delete. `order_line` points at a variant forever.

### Permissions

Two new codes in `backend/app/core/permissions.json`, which forces a migration by the catalogue
fingerprint (M02's `CATALOGUE_FINGERPRINT` mechanism — expected, not a surprise).

| Code | Held by | Why the split |
|---|---|---|
| `menu.view` | every staff role | A waiter cannot take an order without reading the menu |
| `menu.edit` | owner, admin | Creating dishes, setting prices, attaching tax. This is a money path |

A manager is deliberately excluded from `menu.edit`. A manager running a shift does not reprice the
menu, for the same reason M02 kept them off `restaurant.configure`. The daily thing a manager
*actually* needs — taking a dish off tonight — is the gap named under *Known gaps*, and giving them
`menu.edit` as a workaround would hand them repricing to solve an availability problem.

### Frontend — the menu manager

Three screens in the staff bundle, and the first one reuses a pattern M02 already shipped:

- **`MenuScreen`** — master-detail, exactly `FloorPlanScreen`'s shape: category list on the left
  (reorderable with the same ↑/↓ buttons and the same `seq` swap), items in the selected category
  on the right. No tree widget, no drag library. The nesting is real; the interaction is two lists.
- **`MenuItemScreen`** — one dish: name, code (read-only after creation, with the reason in the
  hint text), description, `food_type`, station, category, variants with prices and tax, and the
  attached modifier groups.
- **`ModifierGroupsScreen`** — groups, their modifiers, min/max/required, and the bulk
  apply-to-category action.

**New shared work, both non-negotiables in `docs/ui/conventions.md` that no module has needed yet:**

- `formatINR()` — `₹1,23,456.00`, Indian digit grouping, two decimals, tabular numerals. M02
  displayed no money at all. Every price in this module goes through it and nothing else.
- **`food_type` gets the legally-required veg/non-veg/egg mark** — the green, brown and red
  bordered-dot symbols Indian menus must carry. A dropdown saying "veg" is not what FSSAI means
  and not what a customer looks for. This is a small component and it belongs in `shared/ui`.

### Seed

`backend/app/seed/menu.py` — nothing currently loads `seed/menu.yaml` (32 items, 36 variants, 6
categories) or `operations.yaml`'s modifier groups and attachments. `make seed` must produce a
restaurant with a full, orderable menu, because M04 and M07 both start from one and because M02's
review round found the module *undemonstrable* when its seed data was thin.

---

## Schema review checklist (guardrail G-13)

Answered for all six tables, as the guardrails require.

**1 · What metric will someone want from this row in M13/M17, and which timestamp does it need?**
`menu_item_variant` is the unit of menu engineering (vision §12: popularity × profitability × rating
× complexity). It needs **no timestamp of its own** — `order_line` carries the sale instant and the
price it charged, so demand, revenue and price history are all derivable there. `menu_item.code` is
the key those reports group by, and it is the key `library/` matches on, which is why it is
immutable. `prep_minutes` is the *standard*; M08's `kot_ticket` carries actuals, and the gap between
them is a real operational metric — do not overwrite one with the other (invariant 7's shape again).

**2 · Where did this row come from?** Three sources, and they will diverge: typed by a human,
seeded from `seed/menu.yaml`, or matched from `library/dishes.yaml` during onboarding (M04). The
third is the one that matters — a matched dish carries a recipe the chef has not yet confirmed, and
`library/PROVENANCE.md` says most of the library is `estimated`. **M04 must be able to tell a
confirmed recipe from a proposed one.** That is M04's column to add; M03's obligation is to keep
`code` stable so the match survives.

**3 · Is this row a legal document?** `food_type` is the closest. FSSAI requires veg/non-veg
declaration on menus and packaging; it is `NOT NULL` with a CHECK for that reason, not for tidiness.
`menu_item_variant.price` and its tax group are cited by every invoice, but through the copy
`order_line` takes — the menu row itself is not the document.

**4 · Does a modifier / option / variant change consumption?** **Yes, and M03 does not model it.**
A variant does (Half vs Full is a different recipe — M04 handles it, `recipe.menu_item_variant_id`).
A modifier does too — "extra cheese" is 40 g of cheese — and `recipe`'s CHECK is
`num_nonnulls(menu_item_variant_id, produces_stock_item_id) = 1`, which has no room for a modifier.
Until that is extended, every modifier ordered makes theoretical consumption wrong, and invariant 7
says that variance is the product. Carried as an explicit obligation below rather than left to be
rediscovered.

**5 · What does a human count at close?** Nothing here.

**6 · Is the derived number O(N) forever?** `GET /menu` is the risk and the answer is the bounded
query count plus the ETag. `menu_version` is an integer bump, not a recount.

**7 · Which tier of ADR 0008 deletion, and is `restaurant_id` on the row?** All six are master data
— deactivated, never deleted. Five carry `restaurant_id NOT NULL`. **`menu_item_modifier_group` is
the exception**: it is a pure join table keyed `(menu_item_id, modifier_group_id)`, and both parents
are already tenant-scoped. Adding `restaurant_id` to it would be a third place the tenant can
disagree with itself. The service must therefore verify **both** sides belong to the caller's
restaurant before inserting, and a test asserts that attaching another tenant's modifier group is
refused — because the repository base class cannot catch this one for us.

**8 · What would an insider do with this row?** Below.

## Threat question — *what would an insider do with this?*

| Attack | Control |
|---|---|
| **A manager quietly raises a price**, takes the difference in cash, and the bill still looks right | `menu.edit` is owner/admin only. Every price change writes `audit_log` with before/after and an actor (invariant 6) |
| **A dish is pointed at a lower tax group** so less GST is remitted while the customer pays the same | Tax reference is constrained to that restaurant's groups, change is audited, and `order_line` copies the rate at order time so the discrepancy is visible in the books rather than absorbed |
| Someone **renames a dish's `code`** so it no longer matches its recipe, breaking cost tracking while sales continue | `code` is immutable after creation. Not a permission — a schema-level refusal |
| A dish is **deactivated mid-service** with open order lines pointing at it | Deactivation never deletes; M07 owns the open-order refusal and M03 leaves the check point, exactly as M02 did for tables |
| A waiter at branch A **reads branch B's menu and prices** to infer its positioning | `RestaurantScopedRepository` + the four generic suites over every new route |
| Another tenant's **modifier group is attached** to an item, leaking its existence and price deltas | Explicit both-sides check in the service, plus its own test — the join table has no `restaurant_id` for the base class to filter on (checklist Q7) |
| A **₹0 variant** is created and used to give food away without a discount record | Price `>= 0` is allowed (a ₹0 side exists), so this is not a schema refusal. It is an audited creation by an owner/admin, and M07's discount reporting is where a pattern of it shows up |

---

## Chunks

Eight, each ending in a commit, so a token limit costs at most one chunk.

| # | Content | Ends with |
|---|---|---|
| **A** | Decision 1's tax work, if approved: migration, M02 tax service/repo/screen rework, tests green | `make check` clean on the reshaped tax model |
| **B** | Migration for 6 tables + SQLAlchemy models + `menu_version` on `restaurant` | up→down→up tested |
| **C** | Repositories + service + API for categories, items, variants. Permission catalogue + fingerprint migration | Generic suites pass over the new routes |
| **D** | Modifier groups, modifiers, item attachment, category bulk-apply. The cross-tenant attachment test | Attaching another tenant's group is refused, by test |
| **E** | `GET /menu` — tree assembly, ETag/304, `assert_max_queries`, active-only default | Query count flat from 12 dishes to 400, asserted |
| **F** | Seed loader for `menu.yaml` + modifier groups and attachments | `make seed` yields an orderable 32-dish menu |
| **G** | `MenuScreen` + `MenuItemScreen`, `formatINR`, the veg/non-veg mark component | Screens usable against the seeded menu |
| **H** | `ModifierGroupsScreen`, bulk apply, empty states, then the manual-test script | `docs/manual-tests/M03-menu.md` written |

The end-of-module adversarial review is a separate ask — it is where I would want agents, as in M02.

## Acceptance criteria

1. `GET /menu` issues the same number of queries for a 12-dish menu and a 400-dish menu
2. A second `GET /menu` with `If-None-Match` returns `304` and an empty body
3. Any menu write bumps `menu_version`, and the next conditional GET returns `200`
4. `GET /menu` omits deactivated items; `?include_inactive=true` includes them
5. A price is stored and returned as `Decimal`, never a float, and rendered `₹1,23,456.00`
6. `menu_item.code` cannot be changed after creation — refused at the API, asserted by test
7. Attaching a modifier group belonging to another restaurant is refused
8. A manager receives 403 on every `menu.edit` route and 200 on every `menu.view` route
9. Deactivating a category does not delete it, and its items remain resolvable
10. Every dish in `seed/menu.yaml` loads with its variants, prices and modifier attachments
11. Every new route declares a permission and passes the four generic suites unmodified
12. `make check` clean, zero warnings

## Tests

| Test | Asserts |
|---|---|
| `test_menu_tree_query_count_is_flat` | 12 dishes and 400 dishes cost the same queries — the headline test |
| `test_menu_tree_etag_returns_304` | conditional GET works |
| `test_menu_write_bumps_version` | and invalidates the ETag |
| `test_menu_excludes_inactive_by_default` | a waiter cannot see a deactivated dish |
| `test_item_code_is_immutable` | PATCH may rename, never recode |
| `test_variant_price_is_decimal` | invariant 3 at the API boundary |
| `test_cross_tenant_modifier_attachment_refused` | the join table's missing `restaurant_id` (checklist Q7) |
| `test_manager_cannot_edit_menu` | the permission split |
| `test_deactivated_category_keeps_its_items` | ADR 0008 tier behaviour |
| `test_seed_menu_loads_fully` | 32 items, 36 variants, attachments resolved |
| `test_modifier_group_code_is_immutable` | defect 1's guarantee |
| generic suites | tenant isolation, permission matrix, persona separation, route declaration |

---

## Known gaps — named now, with the consequence stated

**A dish cannot be taken off for tonight only.** `menu_item.is_active` is the ADR 0008 lifecycle
flag — "this dish is gone" — not "we are out of paneer until the delivery arrives". A waiter will
hit this on day one of the pilot, and the only tool available will be deactivating the dish, which
is a heavier and more forgettable action than the situation deserves.

Deliberately not built here, because M05 derives availability from stock and a manual flag added now
becomes a second source of truth that disagrees with the ledger. **Un-defer at M07**, when waiters
first take orders and the need becomes concrete rather than predicted. Backlogged.

**Substitution modifiers change consumption in two directions** — "brown rice instead of white"
removes one ingredient and adds another. `modifier.price_delta` models a price change and nothing
models the swap. Out of scope; recorded so M04 does not assume `price_delta` implies additive.

## Inherited obligations — things M03 hands to a later module

| Owed by | What | Why it cannot be done here |
|---|---|---|
| **M04** | Extend `recipe`'s owner CHECK to a third column so a modifier can carry a recipe | `recipe` does not exist yet. Checklist Q4 |
| **M04** | Distinguish a chef-confirmed recipe from a `library/`-proposed one | `library/PROVENANCE.md` says most of the library is `estimated`; a matched dish must not look confirmed. Checklist Q2 |
| **M07** | Refuse deactivating an item or category with open order lines | Orders do not exist yet; M03 leaves the check point |
| **M07** | Today-only availability | See *Known gaps* |

---

## Open decisions — I need your answer before chunk A

### 1 · The tax reference: is a tax group an identity, or a dated row?

**This is the one that matters, and it is the reason M03 cannot start silently.**

`docs/schema.md` gives `menu_item_variant.tax_group_id NN FK→tax_group`. But M02 built `tax_group`
as an **effective-dated row**: a rate change creates a new row and closes the old one. So the moment
GST changes, every variant points at a dead row and nothing links it forward.

`docs/backlog.md` has this filed twice, and **both rows name the wrong module** — one says
"un-defer at M06", the other says "M04's `menu_item_variant.tax_group_id`". `docs/modules.md:68`
puts `menu_item_variant` in **M03**. The foreign key the backlog wants decided before is the one
chunk C is about to create. Its own words: *"far cheaper before … creates foreign keys pointing at
these rows than after."*

| | **(a) Split identity from rate** *(recommended)* | **(b) Ship as specified** |
|---|---|---|
| Shape | `tax_group` becomes the identity — `code`, `name`, one row per family. A new `tax_rate` table holds the effective-dated rows and the EXCLUDE constraint moves to it | `menu_item_variant.tax_group_id` points at a dated row, as written |
| `menu_item_variant` | `tax_group_id FK→tax_group` — **the schema doc's line is unchanged and becomes true** | unchanged, and quietly wrong after the first rate change |
| On a GST change | Nothing to repoint. One new `tax_rate` row; every dish follows automatically | ~250 variants repointed by hand, by someone who remembers to |
| Cost now | ~0.5 day: one migration, rework M02's tax repo/service/`TaxRatesScreen` and its tests | zero |
| Cost later | zero | a data migration plus a repoint of every variant, after M04 and M07 have built on the wrong shape |
| Also settles | the "no class discriminator" backlog row — `code` *is* the discriminator | nothing |

**My recommendation: (a).** It is the smallest change that makes the schema doc's own sentence true,
it deletes two backlog rows, and M02's existing EXCLUDE constraint moves across almost unmodified.
The half-day is real and I would rather spend it before three modules are built on top.

If you pick (b), I will build it as specified and the backlog rows stay open — that is a legitimate
choice, and the cost is a known manual step at the first rate change, not a bug.

### 2 · Does a manager hold `menu.edit`?

My recommendation: **no** — owner and admin only, matching `restaurant.configure`. Pricing is a
money path. The manager's real daily need is tonight-only availability, which is the *Known gaps*
item, and handing them full menu editing as a workaround is the wrong trade.

Say if managers at a real restaurant you know would expect to edit the menu, because that is
evidence and my reasoning is inference.

### 3 · Does `GET /menu` serve the guest bundle too?

ADR 0009 splits staff and guest into two applications. A QR-code menu for diners is vision §5 and
M10's, but the *data* is this endpoint. Building the route persona-aware now costs almost nothing;
retrofitting it later means re-deciding what a guest may see (cost? station? `prep_minutes`? No).

My recommendation: **add the persona filter now, ship no guest screen.** `GET /menu` for a guest
returns name, description, `food_type`, variants and prices — never station, never `prep_minutes`,
never anything inactive. The generic persona-separation suite already exists and will cover it.

### 4 · Estimate — `docs/modules.md` says 3 days; I am saying 4, or 4.5 with decision 1

Not really a question, but you should see it rather than discover it. M03 is 6 tables against M02's
4, plus the tree endpoint, plus two screens with a master-detail pattern and the first money
formatting in the product. M02 was estimated at 2, restated at 3, and ran longer once the review
round was counted. I would rather say 4 now.

---

## Risks

| Risk | Mitigation |
|---|---|
| **M02's manual pass is still outstanding while M03 builds on it** | Accepted deliberately. The real exposure is not M02 breaking — it is a UI defect being *copied* into M03's screens before anyone sees it, and M03's screens deliberately reuse M02's master-detail pattern, which concentrates that risk. **Mitigation: the twelve-minute short path in `docs/manual-tests/M02-restaurant-setup.md` (E1, D1, A5–A8, C3, F2 + the G charter) before chunk G**, which is the first chunk that copies a screen pattern. Chunks A–F are backend and carry no such exposure |
| `GET /menu` is subtly O(N) and nothing notices until a real 400-dish menu | The query-count test runs against a **generated 400-dish** menu, not the 32-dish seed. A test that only sees 32 dishes cannot distinguish flat from linear |
| The menu manager becomes a tree-widget project | It is two lists and a detail pane, reusing `FloorPlanScreen`'s shape. If a tree library is reached for, that is the signal the design went wrong |
| `library/` and `menu.yaml` drift from what the tables accept | `library/validate.py` already runs in `make check`; chunk F's loader reads the same YAML, so a shape mismatch fails the build rather than the demo |
| Scope creep from "while we are in the menu…" — combos, happy hour, channel pricing | Named in *Not in scope*. Anything that arrives goes to `docs/backlog.md` |
