# Database Schema

The concrete table specification. Conceptual model: `docs/domain-model.md`. Conventions:
ADR 0004 (money/time/units), ADR 0006 (preparations), ADR 0007 (identity), ADR 0008 (keys, deletion,
enums, numerics), ADR 0010 (idempotency, locking), ADR 0011 (performance).

**74 tables in 13 domains.** Everything here is Phase 1 unless marked `[1.5]`.

## Reading this document

```
column_name        type                    notes
```
`PK` primary key · `FK→x` foreign key · `NN` not null · `UQ` unique · `IX` index ·
`>` composite index in the order written.

**Applied to every table, not repeated below:**
- `id` — `uuid` PK, UUIDv7, application-generated.
- `created_at`, `updated_at` — `timestamptz NN default now()`.
- Tenant-owned tables carry `restaurant_id uuid NN FK→restaurant`, and **every index leads with it**.
- Deletion columns follow the ADR 0008 tier for that table — master data gets `is_active` +
  `deactivated_at`; transactional tables get none; ledgers get none.

`restaurant_id` is carried even where it is derivable through a parent (e.g. `order_line` could
reach it via `order`). That denormalisation is deliberate: it keeps every tenant filter a single
index seek and makes Row-Level Security a one-line policy per table when we enable it.

---

## 1 · Tenancy & identity — 11 tables

```
organization
  name                text NN
  slug                text NN UQ
  billing_email       text
  plan                text NN check(trial|active|suspended|cancelled)
  is_demo             bool NN default false      -- seeded orgs; excluded from all reporting

restaurant
  organization_id     uuid NN FK→organization
  name                text NN
  code                text NN                    -- UQ (organization_id, code)
  timezone            text NN default 'Asia/Kolkata'   -- IANA
  currency            char(3) NN default 'INR'
  business_day_start  time NN default '05:00'    -- ADR 0004; NOT midnight
  gstin               text
  gst_scheme          text NN check(regular|composition|unregistered) default 'regular'
                                                 -- decides the DOCUMENT, not just the rate (M07)
  service_charge_rate numeric(6,4)               -- NULL = disabled, the default (CCPA)
  address             jsonb
  settings            jsonb NN default '{}'      -- notification channels, feature toggles
  is_active           bool NN default true
  IX (organization_id)

user_account                                     -- authentication ONLY. ADR 0007.
  organization_id     uuid NN FK→organization
  email               text                       -- UQ (organization_id, email); stored lowercase (G-18)
  phone               text                       -- UQ (organization_id, phone); stored E.164, +91 default
  password_hash       text                       -- null for invited-but-not-activated
  status              text NN check(invited|active|suspended|locked)
  mfa_secret          text
  last_login_at       timestamptz
  failed_attempts     smallint NN default 0     -- unused since B5: attempts live in login_attempt
  locked_until        timestamptz                -- set only by a person since B5
  CHECK (email IS NOT NULL OR phone IS NOT NULL)

user_session
  user_account_id     uuid NN FK→user_account
  refresh_token_hash  text NN UQ                 -- hashed: a database dump yields no live session
  family_id           uuid NN                    -- every rotation of one login's token shares this
  device_info         jsonb
  ip_address          inet
  expires_at          timestamptz NN
  revoked_at          timestamptz
  IX (user_account_id, expires_at)
  IX (user_account_id) WHERE revoked_at IS NULL  -- the revocation sweep on deactivate

sign_in_choice                                   -- B4: one password opens several organizations
  token_hash          text NN UQ                 -- sha256 of the pass; the pass is never stored
  account_ids         uuid[] NN                  -- the accounts the password opened, nothing else
  expires_at          timestamptz NN             -- two minutes after it is issued
  used_at             timestamptz                -- set by the one request that uses it
  IX (expires_at)

login_attempt                                    -- B5: remembered so the next attempt can wait
  identifier_hash     text NN                    -- sha256 of the normalised login; never the login
  ip_address          inet                       -- for the per-network budget
  succeeded           bool NN
  IX (identifier_hash, created_at)
  IX (ip_address, created_at)

employee                                         -- business profile. Login is optional.
  organization_id     uuid NN FK→organization
  user_account_id     uuid UQ FK→user_account    -- NULLABLE: cleaners may never log in
  employee_code       text NN                    -- UQ (organization_id, employee_code)
  full_name           text NN
  phone               text
  date_of_birth       date
  joined_on           date NN
  employment_type     text NN check(full_time|part_time|contract)
  is_active           bool NN default true
  deactivated_at      timestamptz
  IX (organization_id, is_active)

role
  organization_id     uuid FK→organization       -- NULL = system template role
  code                text NN                    -- owner|admin|manager|chef|kitchen_staff|
                                                 -- waiter|store_manager|cleaner|accountant
  name                text NN
  rank                smallint NN default 100    -- seniority, lower is more senior. Nobody may
                                                 -- grant a role more senior than their own, and
                                                 -- nobody may edit their own roles at all. This,
                                                 -- not the permission set, is what stops a manager
                                                 -- promoting themselves to owner.
  description         text                       -- shown on the role-assignment screen
  is_system           bool NN default false      -- cannot be deleted
  UQ (organization_id, code)
  UQ (code) WHERE organization_id IS NULL        -- NULL does not constrain in a UNIQUE, and the
                                                 -- system templates are exactly the NULL rows

permission                                       -- static catalogue, seeded by migration
  code                text NN UQ                 -- 'order.void', 'stock.adjust',
                                                 -- 'report.financial.view'
  resource            text NN
  action              text NN
  description         text NN

role_permission
  role_id             uuid NN FK→role
  permission_id       uuid NN FK→permission
  PK (role_id, permission_id)

employee_role_assignment                         -- per restaurant: one person, different roles
  employee_id         uuid NN FK→employee        -- at different branches
  restaurant_id       uuid NN FK→restaurant
  role_id             uuid NN FK→role
  assigned_by         uuid FK→employee
  UQ (employee_id, restaurant_id, role_id)
  IX (restaurant_id, role_id)
```

Authorisation is always `require_permission("order.void")`. Comparing role names in code is a
review rejection (ADR 0007).

---

## 2 · Restaurant setup — 5 tables

```
dining_area
  restaurant_id, name NN, seq smallint NN, is_active

restaurant_table
  restaurant_id, dining_area_id NN FK→dining_area
  code                text NN                    -- UQ (restaurant_id, code). "T4", not the PK.
  seats               smallint NN
  status              text NN check(free|occupied|reserved|cleaning|out_of_service)
  cleaning_since      timestamptz                -- set exactly while status = cleaning (CHECK, 0022).
                                                 -- The floor shows the table free once the
                                                 -- restaurant's cleaning time has passed.
  is_active
  IX (restaurant_id, status)
  UQ (id, restaurant_id)                         -- target of order_table's composite FK (M07)

station                                          -- tandoor | main_kitchen | chinese | cold | bar
  restaurant_id, code NN, name NN, seq, is_active
  UQ (restaurant_id, code)

tax_group                                        -- the tax CLASS. One row, for as long as it is charged.
  restaurant_id
  code                text NN                    -- UQ (restaurant_id, code). "GST5". Immutable.
  name                text NN                    -- a label; editable
  is_active
  regime              text NN check(gst|non_gst) default 'gst'
                                                 -- non_gst: liquor, outside GST (Art. 366(12A))
  UQ (id, restaurant_id)                         -- target of tax_rate's composite FK

tax_rate                                         -- what that class charges, and between which dates
  restaurant_id, tax_group_id NN FK→tax_group
  rate                numeric(6,4) NN            -- 0.0500 = 5%
  is_inclusive        bool NN default false
  effective_from      date NN
  effective_to        date                       -- NULL = still current
  FK (tax_group_id, restaurant_id) → tax_group(id, restaurant_id)
  EXCLUDE (tax_group_id WITH =, daterange(effective_from, effective_to, '[]') WITH &&)
  IX (restaurant_id, effective_from), IX (tax_group_id, effective_from)
```

**A tax group has an identity separate from its current rate** (M03 spec decision 1, migration 0008).
`menu_item_variant.tax_group_id` below points at the **group**, so a GST change adds a `tax_rate`
row and repoints nothing — the rate in force on a business date is resolved by date. M02 shipped one
table doing both jobs, which meant every dish on the menu would have pointed at a closed period the
first time a rate moved. The composite foreign key makes "a rate belongs to the same restaurant as
its group" a database guarantee rather than a service convention.

---

## 3 · Menu — 6 tables

```
menu_category
  restaurant_id, name NN, seq smallint NN, is_active
  code                text NN                    -- UQ (restaurant_id, code)

menu_item
  restaurant_id, menu_category_id NN FK→menu_category
  code                text NN                    -- UQ (restaurant_id, code)
  name                text NN
  description         text
  food_type           text NN check(veg|non_veg|egg)   -- legally required in India
  station_id          uuid NN FK→station         -- routing: which KOT printer/screen
  image_url           text
  seq                 smallint NN default 0      -- the order a category's dishes are listed in
  is_active
  IX (restaurant_id, menu_category_id, is_active)
  IX (menu_category_id, is_active)               -- selectinload keys on this alone; no skip-scan

menu_item_variant                                -- Half/Full/Per-piece. PRICE LIVES HERE.
  restaurant_id, menu_item_id NN FK→menu_item
  code                text NN                    -- HALF|FULL|PIECE
  name                text NN
  price               numeric(12,2) NN
  tax_group_id        uuid NN FK→tax_group
  prep_minutes        smallint NN                -- standard; actuals come from kot_ticket
  seq                 smallint NN default 0      -- Half before Full, as the menu reads
  is_active
  UQ (menu_item_id, code)
  UQ (id, restaurant_id)                         -- target of order_line's composite FK (M07)

modifier_group                                   -- "Choose spice level", "Add-ons"
  restaurant_id, name NN
  code                text NN                    -- UQ (restaurant_id, code)
  min_select          smallint NN default 0
  max_select          smallint NN default 1
  is_required         bool NN default false
  is_active
  CHECK (max_select >= min_select)
  CHECK (NOT is_required OR min_select >= 1)

modifier
  restaurant_id, modifier_group_id NN FK→modifier_group
  code                text NN                    -- UQ (modifier_group_id, code)
  name                text NN
  price_delta         numeric(12,2) NN default 0
  seq                 smallint NN default 0
  is_active
  IX (modifier_group_id, is_active)
  UQ (id, restaurant_id)                         -- target of order_line_modifier's FK (M07)

menu_item_modifier_group
  menu_item_id NN FK→menu_item, modifier_group_id NN FK→modifier_group, seq
  PK (menu_item_id, modifier_group_id)

restaurant.menu_version                          -- bumped by every menu write; the guest ETag
```

Price on the **variant**, never the item. A half plate is a different price, a different recipe and
a different food cost.

**Every one of these carries a `code`, and none of them lets it change.** The code is the join key:
`seed/menu.yaml` and `seed/operations.yaml` reference each other by it, `library/dishes.yaml` matches
on it, and every recipe M04 attaches finds its dish through it. Renaming one would break cost
tracking while sales carried on — so the update schemas omit the field rather than validating it.

**`restaurant.menu_version` is not decoration.** The guest menu is the highest-traffic read in the
product and it is cached on an ETag; a counter the writes bump is what lets a diner's phone skip the
whole tree on every load but the first. It lives on `restaurant` rather than per-category because a
modifier group attached to forty dishes changes all of them at once.

The M03 tables above shipped in migrations 0008-0010. The `ix_menu_item_category` index came later,
in 0013: `selectinload` emits `WHERE menu_category_id IN (…)` with no tenant predicate, the existing
index leads with `restaurant_id`, and Postgres has no index skip-scan — so the hottest query in the
product was sequentially scanning `menu_item`. A query-count test cannot see that, because a
sequential scan is one statement.

---

## 4 · Stock items & recipes — 5 tables

The unification that makes ADR 0006 work: an ingredient and a preparation are both things that hold
stock, expire and have a cost, so they share one identity table. That lets `recipe_line` and
`stock_batch` carry a single clean foreign key instead of a nullable pair.

```
stock_item                                       -- ingredients AND preparations
  restaurant_id
  kind                text NN check(ingredient|preparation)
  code                text NN                    -- UQ (restaurant_id, code)
  name                text NN
  base_unit           text NN check(g|ml|unit)   -- ADR 0004: one canonical unit, always
  category            text                       -- meat|dairy|veg|grain|spice|oil|bakery|sweet
  storage_type        text check(ambient|chilled|frozen)
  current_unit_cost   numeric(14,6) NN default 0 -- cached weighted average; batches hold truth
  cost_source         text NN default 'market_rate' check(market_rate|manual|purchase)
  is_active
  IX (restaurant_id, kind, is_active)
  IX (restaurant_id) where cost_source = 'market_rate'   -- the un-confirmed prices

ingredient_profile                               -- 1:1 where kind='ingredient'
  stock_item_id       uuid PK FK→stock_item
  purchase_unit       text NN                    -- 'kg', 'litre', 'dozen'
  purchase_to_base    numeric(14,4) NN           -- 1 kg = 1000 g
  yield_factor        numeric(6,4) NN default 1  -- 0.72 = 28% trim loss
  shelf_life_days     smallint NN
  default_supplier_id uuid FK→supplier
  reorder_level       numeric(14,4)              -- base units
  reorder_quantity    numeric(14,4)

preparation_profile                              -- 1:1 where kind='preparation'
  stock_item_id       uuid PK FK→stock_item
  batch_yield         numeric(14,4) NN           -- one standard batch, in base_unit
  shelf_life_hours    smallint NN                -- HOURS. A gravy dies in 36.
  station_id          uuid NN FK→station
  prep_minutes        smallint NN

recipe                                           -- versioned; a dish, a preparation OR a modifier
  restaurant_id
  menu_item_variant_id    uuid FK→menu_item_variant
  produces_stock_item_id  uuid FK→stock_item     -- the preparation this recipe makes
  modifier_id             uuid FK→modifier       -- "extra cheese" is 40 g of cheese (M03 → M04)
  version             smallint NN
  is_current          bool NN
  effective_from      timestamptz NN
  notes               text
  unit_cost           numeric(14,6) NN default 0 -- frozen when this version became current (X8)
  source              text NN check(typed|seeded|library)
  confirmed_at        timestamptz                -- NULL = nobody has checked these quantities
  CHECK (num_nonnulls(menu_item_variant_id, produces_stock_item_id, modifier_id) = 1)
  UQ (menu_item_variant_id, version), UQ (produces_stock_item_id, version), UQ (modifier_id, version)
  UQ (id, restaurant_id)                         -- the target of recipe_line's composite FK
  partial UQ on is_current per owner, SCOPED BY restaurant_id

recipe_line
  restaurant_id       uuid NN FK→restaurant
  recipe_id           uuid NN
  component_id        uuid NN                    -- ingredient OR preparation: recipes nest
  quantity            numeric(14,4) NN           -- in the component's base_unit
  seq                 smallint NN
  PK (recipe_id, component_id)
  FK (recipe_id, restaurant_id)    → recipe(id, restaurant_id)
  FK (component_id, restaurant_id) → stock_item(id, restaurant_id)
  IX (component_id)                              -- answers "what uses paneer?"
```

Nesting depth is capped at 3 and enforced in the service layer, at save time, and in
`seed/validate.py`. All three count the same levels, which they did not until migration 0013's
review: the save-time walk seeded its chain with the owner's code and then counted that code, so it
refused at three what the other two allowed at three. Historical orders reference the recipe
**version** live at the time, so food-cost history never rewrites itself.

**`recipe_line` carries `restaurant_id` and `menu_item_modifier_group` does not**, and the
difference is deliberate. The menu join is a pure pair with no second writer; this one has a planned
second writer — M04 hands the `library/` matching flow to a later module — so the composite foreign
keys above are what keep a line's component on the line's tenant, rather than a check in one service
a second writer would never reach. There are no single-column foreign keys beside them: two paths
between the same pair of tables is a join SQLAlchemy cannot resolve at all.

The three `uq_recipe_current_*` partial indexes are scoped by `restaurant_id` for the same family of
reason. Keyed on the owner alone, one restaurant could take another's slot and permanently prevent
the owner from creating their own — a 500 with no recovery, on their own data.

**`recipe.unit_cost` is the frozen answer; `stock_item.current_unit_cost` is a cache.** Finding X8
asked for the first and finding S16 warns about the second: reading today's ingredient price to
cost a March order reports the wrong number with no sign that it is wrong. M13 reads the version.

**`cost_source` says how much that cache is worth trusting**, and exists because
`docs/onboarding-cold-start.md` promises bootstrapped prices will be "visibly marked estimated"
while nothing in the schema could express it. A restaurant that has recorded no purchases still
sees a food cost on day one — that is the commercial pitch — so a price bootstrapped from
`library/market-rates.yaml` must not read with the same authority as one off this restaurant's own
supplier bill. The default is `market_rate`, the *least* confident value, on purpose: a price whose
provenance nobody set is a price nobody vouched for, so the default fails toward honesty rather
than toward a guess that gets believed. It is exposed on `PricedStockItemResponse` only — a chef
who is not shown rupees has no use for where the rupees came from. Migration `0014`.

**`yield_factor` is the fraction of what you buy that reaches the pan**, and it applies to every
base unit. For a weight the loss is *inside* each unit — a kilo of chicken gives up 280 g of bone.
For a count it is *between* units — an egg is fine or it is cracked, and buying 341 to use 300 is
what a month actually looks like. Both divide identically, which is why one column covers both
(M04 spec, open decision S15, resolved in favour of keeping the arithmetic). What the finding was
pointing at is a data ambiguity rather than a code one: `LEMON 0.90` must mean "one lemon in ten is
bad" and never "you only get 90% of the juice out", because a recipe calling for `0.25` lemons has
already accounted for the second.

**`source` and `confirmed_at` exist because of `library/`.** `library/PROVENANCE.md` states that
most of the starter library is `estimated` — domain knowledge no chef has checked — so a recipe
matched from it must be distinguishable from one a chef wrote, or the dish-cost screen states a
number with confidence nobody has earned.

---

## 5 · Inventory — 4 tables

```
stock_batch
  restaurant_id, stock_item_id NN FK→stock_item
  batch_code          text NN                    -- UQ (restaurant_id, batch_code)
  quantity_received   numeric(14,4) NN           -- base units, immutable
  unit_cost           numeric(14,6) NN           -- frozen at receipt/production
  received_at         timestamptz NN
  expiry_date         date                       -- drives FEFO
  storage_location    text
  supplier_id         uuid FK→supplier           -- null for preparations
  goods_receipt_line_id uuid FK→goods_receipt_line
  source              text NN check(purchase|production|opening|transfer)
  IX (restaurant_id, stock_item_id, expiry_date)   -- the FEFO index
  IX (restaurant_id, expiry_date) WHERE expiry_date IS NOT NULL   -- expiry alerts

stock_movement                                   -- APPEND-ONLY LEDGER. Never update, never delete.
  restaurant_id, stock_batch_id NN FK→stock_batch
  stock_item_id       uuid NN FK→stock_item      -- denormalised: most queries never need the batch
  type                text NN check(receipt|production|consumption|wastage|staff_meal|
                                    complimentary|transfer|adjustment|count)
  quantity_delta      numeric(14,4) NN           -- signed. Negative consumes.
  unit_cost           numeric(14,6) NN           -- from the batch, frozen
  basis               text NN check(theoretical|actual)   -- INVARIANT 7. Never mix these.
  occurred_at         timestamptz NN
  business_date       date NN                    -- ADR 0004
  actor_employee_id   uuid FK→employee
  ref_type            text                       -- order|wastage_event|goods_receipt|stock_count|
                                                 -- production_batch
  ref_id              uuid                       -- the connective tissue
  note                text
  IX (restaurant_id, stock_item_id, business_date)
  IX (restaurant_id, type, business_date)
  IX (ref_type, ref_id)

stock_count                                      -- physical count header
  restaurant_id, counted_at NN, business_date NN
  scope               text NN check(full|partial|spot)
  status              text NN check(draft|submitted|approved)
  counted_by, approved_by  uuid FK→employee
  IX (restaurant_id, business_date)

stock_count_line
  restaurant_id NN                               -- carried so the tenant-safe composite FKs work
  stock_count_id NN FK→(stock_count.id, restaurant_id)
  stock_item_id  NN FK→(stock_item.id, restaurant_id)
  system_quantity     numeric(14,4) NN           -- what the ledger says, FROZEN when written
  counted_quantity    numeric(14,4) NN           -- what is on the shelf
  variance_value      numeric(12,2) NN           -- the leakage number, in rupees
  reason              text
  UQ (stock_count_id, stock_item_id)             -- an item appears once on a sheet
```

### What migration 0015 added beyond the sketch above

The sketch is the design; these are the guarantees that turned out to be needed to make it true.
All are in `0015_m05_inventory`, argued in `docs/modules/M05-inventory-spec.md`.

**`stock_movement` refuses UPDATE and DELETE**, via a trigger. Invariant 2 as a repository
convention is one careless `session.merge()` away from silent violation, and afterwards no test can
see it — the row simply looks different. Corrections are new `adjustment` rows, which is what the
invariant already prescribes.

**Tenant-safe composite foreign keys.** `stock_batch`, `stock_movement` and `stock_count_line`
reference their parents on `(id, restaurant_id)` rather than on `id` alone, against the
`uq_*_id_restaurant` constraints. Attaching a batch to another restaurant's item is therefore
refused by Postgres rather than by a repository remembering to filter — which is why
`stock_count_line` carries a `restaurant_id` the original sketch did not give it.

**CHECK constraints that catch nonsense:** `quantity_delta <> 0` (a zero movement is always a bug
and pollutes every average after it), `(ref_type IS NULL) = (ref_id IS NULL)` (a dangling reference
reads as a real link), non-negative `quantity_received`, `unit_cost` and `counted_quantity`, and
`approved_by <> counted_by` on `stock_count` — separation of duties held by the database, not only
by the service.

**`supplier_id` and `goods_receipt_line_id` were columns without foreign keys** until M06 created
the tables they point at. The migration-order note at the foot of this document anticipated exactly
this; migration **0017** adds both constraints, composite and tenant-safe against
`uq_supplier_id_restaurant` and `uq_gr_line_id_restaurant`. Nothing before 0017 wrote either column,
and 0017 asserts that rather than assuming it - a migration that fails loudly beats one that
silently validates nothing.

**One index beyond the sketch:** `ix_stock_movement_batch` on `stock_batch_id`, because the FEFO
selection's second statement aggregates movements grouped by batch.

`basis` is load-bearing. Recipe-driven consumption is `theoretical`; a physical count is `actual`.
Their difference is the product (invariant 7) — a query that sums both together is a bug.

---

## 6 · Procurement — 5 tables  `[1.5]`

Beyond the vision doc's Phase 1, but small and it pays immediately: three-way receiving variance is
the cheapest money in the product (`docs/waste-model.md` §1).

```
supplier
  restaurant_id, name NN, contact_person, phone, email, gstin
  payment_terms_days  smallint
  is_active, deactivated_at                      -- master data tier, ADR 0008
  UQ (restaurant_id, name)                       -- two spellings of one supplier cannot be summed
  IX (restaurant_id, is_active)

purchase_order
  restaurant_id, supplier_id NN FK→supplier
  po_number           text NN                    -- UQ (restaurant_id, po_number)
  status              text NN check(draft|sent|partial|received|cancelled)
  expected_at         timestamptz
  total_amount        numeric(12,2) NN default 0
  created_by, cancelled_at, cancel_reason
  IX (restaurant_id, status)

purchase_order_line
  restaurant_id NN                               -- carried so the tenant-safe composite FKs work
  purchase_order_id NN FK→(purchase_order.id, restaurant_id)
  stock_item_id     NN FK→(stock_item.id, restaurant_id)
  quantity_ordered    numeric(14,4) NN           -- base units
  unit_price          numeric(14,6) NN           -- quoted, excluding tax
  UQ (purchase_order_id, stock_item_id)          -- an item appears once on an order

goods_receipt                                    -- APPEND-ONLY LEDGER. Never update, never delete.
  restaurant_id, purchase_order_id FK→purchase_order   -- nullable: ad-hoc market purchases
  supplier_id NN, received_at NN, business_date NN
  invoice_number      text
  invoice_amount      numeric(12,2)              -- the total payable, tax included
  tax_amount          numeric(12,2)              -- how much of it was tax (compliance A6)
  received_by         uuid FK→employee
  UQ (restaurant_id, supplier_id, invoice_number) WHERE invoice_number IS NOT NULL
  IX (restaurant_id, business_date)
  IX (restaurant_id, supplier_id)

goods_receipt_line                               -- APPEND-ONLY, with its parent
  restaurant_id NN                               -- carried so the tenant-safe composite FKs work
  goods_receipt_id NN FK→(goods_receipt.id, restaurant_id)
  stock_item_id    NN FK→(stock_item.id, restaurant_id)
  quantity_invoiced   numeric(14,4) NN           -- what the bill says
  quantity_received   numeric(14,4) NN           -- what the scale says   <-- the variance
  quantity_rejected   numeric(14,4) NN default 0 -- quality rejection
  unit_price          numeric(14,6) NN           -- excluding tax; landed cost adds it back
  rejection_reason    text
  UQ (goods_receipt_id, stock_item_id)           -- an item appears once on a delivery
  IX (restaurant_id, stock_item_id)
```

Ordered / invoiced / received as three separate numbers is the whole point. Collapse them and
"Supplier A short-delivered 4.2% this quarter — ₹18,400" becomes unanswerable.

### What migration 0017 added beyond the sketch above

The sketch is the design; these are the guarantees that turned out to be needed to make it true.
All are in `0017_m06_procurement`, argued in `docs/modules/M06-procurement-spec.md`.

**`goods_receipt` and `goods_receipt_line` refuse UPDATE and DELETE**, by the same trigger 0015 put
on `stock_movement`. ADR 0008 does not assign these two a tier, so the M06 spec assigns them to
*ledger* — for the threat rather than the taxonomy. A receipt writes stock movements the database
already refuses to change, so an editable receipt is one `UPDATE` away from *"weigh 47, take 3 home,
edit the receipt to say 50 so the invoice reconciles"*: two records that disagree, with nothing able
to say which was altered. Corrections are `adjustment` movements carrying
`ref_type='goods_receipt'` — a reference `stock_movement`'s CHECK constraint already permits.

**Tenant-safe composite foreign keys, so `purchase_order_line` and `goods_receipt_line` carry a
`restaurant_id` the sketch did not give them.** Identical reasoning to `stock_count_line`: every
parent reference is on `(id, restaurant_id)`, so attaching a receipt line to another restaurant's
stock item is refused by Postgres rather than by a repository remembering to filter.

**`goods_receipt.tax_amount`.** `docs/compliance-rules.md` §A6 — a restaurant on the 5% composition
scheme *bears* input GST and cannot reclaim it, so a quoted price is not a cost. Storing only
`unit_price` understates food cost by the whole tax rate; storing only the tax-inclusive total makes
"how much input GST did we bear last year" permanently unanswerable. Both are kept, and the landed
cost frozen onto `stock_batch.unit_cost` apportions the tax pro rata by line value in the service.

**One supplier invoice, booked once:** a partial unique index on
`(restaurant_id, supplier_id, invoice_number)`. Double-booking is the most ordinary error in
accounts payable and the most ordinary small fraud, and it silently doubles stock — which makes
every food-cost figure built on it wrong by more than the money. Partial, because a market purchase
has no invoice number at all.

**CHECK constraints that catch nonsense:** `quantity_rejected <= quantity_received` (you cannot
refuse more than arrived), a rejection with no `rejection_reason` refused, `quantity_ordered > 0`,
non-negative everything else, and `(cancelled_at IS NULL) = (cancel_reason IS NULL)` — a
cancellation with no reason is the one somebody would use to make an over-order disappear.

**`purchase_order.status` is a stored derived value**, the only one in the module. A PO's state is a
function of its receipts, which is cheap for one order and quadratic for the list screen a store
manager lives on. The service maintains it and a test asserts the stored value equals a
recomputation; a stored derived value with no test is a bug waiting.

---

## 7 · Orders — 15 tables

The order, the bill, the money and the till. Designed and argued in
`docs/modules/M07-orders-spec.md`; built by migration 0019, except `kot_ticket` and
`kot_ticket_line`, which are M08's. Every parent reference is composite on `(id, restaurant_id)`.

```
cash_session                                     -- one till, float to count
  restaurant_id
  status              text NN check(open|closed)
  opened_at           timestamptz NN
  opened_by           uuid NN FK→employee
  opening_float       numeric(12,2) NN           -- >= 0
  business_date       date NN
  closed_at           timestamptz
  closed_by           uuid FK→employee
  counted_cash        numeric(12,2)
  variance            numeric(12,2)              -- counted − expected. Stored, never corrected away
  shift_id            uuid                       -- no FK until M12 builds shift
  CHECK (status = 'closed') = (closed_at, closed_by, counted_cash, variance all present)
  UQ (restaurant_id) WHERE status = 'open'       -- one open till per restaurant
  IX (restaurant_id, business_date)

order
  restaurant_id
  order_number        text NN                    -- UQ (restaurant_id, business_date, order_number)
  type                text NN check(dine_in|takeaway|delivery)
  channel             text NN check(pos|qr|aggregator) default 'pos'
  external_order_id   text                       -- an aggregator's id: recorded, not integrated
  status              text NN check(open|sent|served|settled|cancelled|voided)
  customer_id         uuid                       -- no FK until M10 builds customer
  waiter_employee_id  uuid FK→employee
  covers              smallint                   -- headcount; needed for per-cover metrics
  parent_order_id     FK→(order.id, restaurant_id)   -- split lineage
  placed_at           timestamptz NN
  first_sent_at       timestamptz
  served_at           timestamptz
  bill_requested_at   timestamptz
  settled_at          timestamptz
  cancelled_at        timestamptz
  business_date       date NN                    -- ADR 0004. Group reports on THIS.
  subtotal            numeric(12,2) NN default 0
  discount_total      numeric(12,2) NN default 0 -- <= subtotal
  charge_total        numeric(12,2) NN default 0
  tax_total           numeric(12,2) NN default 0
  round_off           numeric(12,2) NN default 0 -- CGST Act s.170; between −0.50 and 0.50
  grand_total         numeric(12,2) NN default 0
  theoretical_food_cost numeric(12,2)            -- frozen at settlement from the cost engine
  cancel_reason       text                       -- NN once cancelled or voided
  voided_by           uuid FK→employee
  version             integer NN default 1       -- optimistic lock (ADR 0010). Two waiters,
                                                 -- one table: last-write-wins loses a dish.
  IX (restaurant_id, business_date)
  IX (restaurant_id, status) WHERE status IN ('open','sent','served')   -- the live-orders index
  IX (restaurant_id, customer_id)
  IX (restaurant_id, waiter_employee_id, business_date)

order_table                                      -- which tables an order occupies
  restaurant_id
  order_id            NN FK→(order.id, restaurant_id)
  restaurant_table_id NN FK→(restaurant_table.id, restaurant_id)
  is_primary          bool NN default false
  UQ (order_id, restaurant_table_id)
  UQ (order_id) WHERE is_primary
  IX (restaurant_id, restaurant_table_id)

order_line
  restaurant_id
  order_id            NN FK→(order.id, restaurant_id)
  menu_item_variant_id NN FK→(menu_item_variant.id, restaurant_id)
  recipe_id           FK→(recipe.id, restaurant_id)   -- the VERSION costed, frozen at settlement
  quantity            smallint NN                -- > 0
  unit_price          numeric(12,2) NN           -- copied, not joined: menu prices change
  line_subtotal       numeric(12,2) NN           -- (unit_price + modifier deltas) × quantity
  line_discount       numeric(12,2) NN default 0 -- this line's share of discounts; <= subtotal
  tax_group_id        NN FK→(tax_group.id, restaurant_id)
  tax_regime          text NN check(gst|non_gst) default 'gst'
  tax_rate            numeric(6,4) NN            -- snapshot when added, re-frozen at settlement
  tax_inclusive       bool NN default false      -- the rate's is_inclusive, copied with it
  taxable_value       numeric(12,2) NN
  cgst_amount         numeric(12,2) NN default 0
  sgst_amount         numeric(12,2) NN default 0
  tax_amount          numeric(12,2) NN default 0
  line_total          numeric(12,2) NN           -- = taxable_value + tax_amount, by CHECK
  theoretical_unit_cost numeric(14,6)
  status              text NN check(pending|sent|preparing|ready|served|cancelled|returned)
  sent_at             timestamptz
  special_instructions text
  cancel_reason       text                       -- NN once cancelled
  seq                 smallint NN default 0
  CHECK gst ⇒ cgst = sgst AND tax = cgst + sgst;  non_gst ⇒ cgst = sgst = 0
  UQ (id, restaurant_id)
  IX (order_id), IX (restaurant_id, menu_item_variant_id)

order_line_modifier
  restaurant_id
  order_line_id       NN FK→(order_line.id, restaurant_id) ON DELETE CASCADE
  modifier_id         NN FK→(modifier.id, restaurant_id)
  price_delta         numeric(12,2) NN           -- copied; may be negative
  recipe_id           FK→(recipe.id, restaurant_id)
  UQ (order_line_id, modifier_id)

order_discount
  restaurant_id
  order_id            NN FK→(order.id, restaurant_id)
  order_line_id       FK→(order_line.id, restaurant_id)   -- NULL for an order-level discount
  type                text NN check(percentage|flat|comp)
  rate                numeric(6,4)               -- percentage and comp only
  flat_amount         numeric(12,2)              -- flat only
  amount              numeric(12,2) NN           -- the rupees actually taken off, frozen
  authorised_amount   numeric(12,2) NN           -- what the authoriser approved; amount <= it, by CHECK
  reason              text NN
  authorised_by       uuid NN FK→employee        -- comps need a name. Always.
  IX (order_id), IX (restaurant_id, authorised_by)

order_charge                                     -- packaging, delivery, an OPTIONAL service charge
  restaurant_id
  order_id            NN FK→(order.id, restaurant_id)
  type                text NN check(packaging|service_charge|delivery)
  amount              numeric(12,2) NN
  tax_group_id        FK→(tax_group.id, restaurant_id)   -- nullable: GST on service charge unsettled
  tax_rate            numeric(6,4)
  cgst_amount         numeric(12,2) NN default 0
  sgst_amount         numeric(12,2) NN default 0
  tax_amount          numeric(12,2) NN default 0
  is_optional         bool NN default false
  CHECK type = 'service_charge' ⇒ is_optional    -- CCPA guidelines, upheld 28 Mar 2025

invoice                                          -- THE LEGAL DOCUMENT. Cancel only. Never deleted.
  restaurant_id
  order_id            NN FK→(order.id, restaurant_id)   -- UQ (order_id): one invoice per order
  document_type       text NN check(tax_invoice|bill_of_supply)
  financial_year      text NN                    -- '2026-27', from the calendar date of issue
  sequence            integer NN                 -- UQ (restaurant_id, financial_year, sequence)
  invoice_number      text NN                    -- UQ (restaurant_id, invoice_number); <= 16 chars
  status              text NN check(issued|cancelled)
  issued_at           timestamptz NN
  invoice_date        date NN                    -- calendar date in the restaurant's timezone
  business_date       date NN
  supplier_name       text NN                    -- supplier_* and fssai_licence are SNAPSHOTTED
  supplier_address    jsonb
  supplier_gstin      text                       -- NN on a tax_invoice, by CHECK (Rule 46(a))
  fssai_licence       text
  recipient_name      text
  recipient_gstin     text
  recipient_address   text
  sac_code            text NN default '996331'
  taxable_total       numeric(12,2) NN
  cgst_total          numeric(12,2) NN default 0 -- zero on a bill_of_supply, by CHECK
  sgst_total          numeric(12,2) NN default 0
  non_gst_tax_total   numeric(12,2) NN default 0
  discount_total      numeric(12,2) NN default 0
  charge_total        numeric(12,2) NN default 0
  round_off           numeric(12,2) NN default 0
  grand_total         numeric(12,2) NN
  cancelled_at        timestamptz
  cancel_reason       text
  cancelled_by        uuid FK→employee
  irn                 text                       -- e-invoicing: modelled, not built
  irn_ack_no          text
  irn_ack_at          timestamptz
  IX (restaurant_id, invoice_date)

credit_note                                      -- CGST Act s.34, Rule 53. APPEND-ONLY. Own series.
  restaurant_id
  invoice_id          NN FK→(invoice.id, restaurant_id)
  financial_year      text NN
  sequence            integer NN                 -- UQ (restaurant_id, financial_year, sequence)
  credit_note_number  text NN                    -- UQ (restaurant_id, credit_note_number); <= 16
  issued_at           timestamptz NN
  note_date           date NN
  business_date       date NN
  reason              text NN
  issued_by           uuid NN FK→employee
  taxable_total       numeric(12,2) NN
  cgst_total          numeric(12,2) NN default 0
  sgst_total          numeric(12,2) NN default 0
  non_gst_tax_total   numeric(12,2) NN default 0
  grand_total         numeric(12,2) NN           -- > 0
  IX (invoice_id)

credit_note_line                                 -- APPEND-ONLY, with its parent
  restaurant_id
  credit_note_id      NN FK→(credit_note.id, restaurant_id)
  order_line_id       NN FK→(order_line.id, restaurant_id)
  quantity            smallint NN
  taxable_value       numeric(12,2) NN
  cgst_amount         numeric(12,2) NN default 0
  sgst_amount         numeric(12,2) NN default 0
  tax_amount          numeric(12,2) NN default 0
  line_total          numeric(12,2) NN           -- = taxable_value + tax_amount, by CHECK
  UQ (credit_note_id, order_line_id)

payment                                          -- APPEND-ONLY
  restaurant_id
  order_id            NN FK→(order.id, restaurant_id)
  invoice_id          FK→(invoice.id, restaurant_id)
  credit_note_id      FK→(credit_note.id, restaurant_id)   -- NN when amount < 0, by CHECK
  cash_session_id     FK→(cash_session.id, restaurant_id)   -- an OPEN till only, by trigger (0021)
  method              text NN check(cash|card|upi|wallet|online|due)
  amount              numeric(12,2) NN           -- NEGATIVE for a refund. No separate table.
  tip_amount          numeric(12,2) NN default 0 -- outside taxable value
  reference           text                       -- UPI txn / card auth
  status              text NN check(success|failed)
  paid_at             timestamptz NN
  business_date       date NN
  received_by         uuid FK→employee
  IX (restaurant_id, business_date), IX (order_id), IX (restaurant_id, cash_session_id)

cash_count                                       -- denominations counted at close. APPEND-ONLY.
  restaurant_id
  cash_session_id     NN FK→(cash_session.id, restaurant_id)
  denomination        numeric(12,2) NN           -- UQ (cash_session_id, denomination)
  quantity            integer NN

cash_movement                                    -- cash out that is not a refund. APPEND-ONLY.
  restaurant_id
  cash_session_id     NN FK→(cash_session.id, restaurant_id)
  type                text NN check(payout|adjustment)
  amount              numeric(12,2) NN           -- a payout is positive; an adjustment either sign
  reason              text NN
  recorded_by         uuid NN FK→employee
  occurred_at         timestamptz NN
  business_date       date NN
  IX (restaurant_id, cash_session_id)

kot_ticket                                       -- one per order per station
  restaurant_id, order_id NN FK→order, station_id NN FK→station
  ticket_number       text NN
  status              text NN check(new|acknowledged|preparing|ready|served|cancelled)
  printed_at          timestamptz NN
  acknowledged_at     timestamptz
  started_at          timestamptz
  ready_at            timestamptz
  served_at           timestamptz
  IX (restaurant_id, station_id, status)         -- the KDS query
  IX (restaurant_id, printed_at)

kot_ticket_line
  kot_ticket_id NN FK→kot_ticket, order_line_id NN FK→order_line
  quantity            smallint NN
  status              text NN check(pending|preparing|ready|served|cancelled|remake)
  remake_reason       text
```

Those five `kot_ticket` timestamps are the entire kitchen-performance module and half of the CX
module. They cost nothing to capture now and cannot be reconstructed later.

### What migration 0019 added beyond the sketch above

The sketch above is now the built design; these are the decisions that changed it, each argued in
`docs/modules/M07-orders-spec.md`.

**A settled order does not change, and Postgres says so.** An open order is edited constantly, so it
cannot take `stock_movement`'s blanket append-only trigger. Its trigger refuses DELETE always, any
change to a cancelled or voided order, and on a settled order every change except voiding it and
the kitchen timestamps a counter-service restaurant writes after taking the money. The comparison
is *every column except the allowed ones*, so a money column a later migration adds is frozen
without anybody remembering to list it. Lines, discounts, charges, tables and modifiers follow their
order on INSERT as well as UPDATE and DELETE, because adding a line to a paid bill is the edit that
matters most. A settled line may still move through the kitchen. A line is deleted only while
unsent; afterwards it is cancelled with a reason, because deleting a sent line is how a served dish
leaves a bill.

**The invoice is a table, not a column on the order.** It is a legal document with its own life:
numbered at settlement and never before, consecutive per restaurant per financial year, at most
sixteen characters (Rule 46(b), a CHECK), and it survives cancellation because GSTR-1 Table 13
reports cancelled documents. The financial year comes from the calendar date of issue, not
`business_date`: a bill at 01:30 on 1 April belongs to business day 31 March and to the new year's
series. Supplier name, address, GSTIN and FSSAI number are snapshotted at issue, so a reprint is the
document as issued. A `tax_invoice` without a supplier GSTIN and a `bill_of_supply` carrying CGST or
SGST are both refused by CHECK.

**A refund is a negative payment that names a credit note.** The eliminated refund table stays
eliminated — the cash is a `payment` row. `docs/security.md` says refunds are credit notes, and
that holds too: the tax document is a `credit_note` (CGST Act s.34), and a CHECK refuses a negative
payment that references none. `payment.status` loses `pending` and `refunded`: a status that has to
change later cannot live on an append-only row.

**GST is stored per line in two equal halves.** CGST and SGST are each computed on the taxable
value, never one as the remainder of the other, so a CHECK holds them equal. `tax_regime` is
`non_gst` for liquor, which is outside GST and never split. Where GST on a service charge is
unsettled, `order_charge.tax_group_id` is nullable and the restaurant decides.

**`restaurant.gst_scheme` decides the document, not just the rate.** A regular restaurant issues a
tax invoice; a composition restaurant may not collect tax and issues a bill of supply. Both are
called "5%", which is the trap.

**`order_table` replaces `order.restaurant_table_id`.** A party of twelve pushes three tables
together, and one column cannot say so.

**`order_number` is unique per business day.** "Table 6, order 42" is what a waiter calls out, and
a counter that never resets is not.

**`cash_movement`, not a payout table.** `docs/modules.md` subtracted payouts from expected cash and
nothing modelled one. A payout and a post-close correction have one shape, so they share a table
with a `type`; two tables would be two places to sum. Expected cash stays derived.

**`menu_item_variant`, `modifier` and `restaurant_table` gained `UNIQUE (id, restaurant_id)`**, the
target every composite foreign key above needs. Safe on existing data by construction: `id` was
already unique.
---

## 8 · Waste — 2 tables

```
wastage_reason                                   -- lookup: rows carry policy, so a table not an enum
  restaurant_id, code NN, name NN
  stage               text NN check(receiving|storage|prep|service)   -- docs/waste-model.md
  requires_photo      bool NN default false
  requires_approval   bool NN default false
  is_active

wastage_event
  restaurant_id, stock_item_id NN FK→stock_item, stock_batch_id FK→stock_batch
  wastage_reason_id   uuid NN FK→wastage_reason
  quantity            numeric(14,4) NN
  cost_value          numeric(12,2) NN           -- computed; never asked of the person logging
  occurred_at NN, business_date NN
  reported_by         uuid NN FK→employee
  shift_id            uuid FK→shift
  station_id          uuid FK→station
  menu_item_variant_id uuid FK→menu_item_variant -- when a specific dish caused it
  order_line_id       uuid FK→order_line         -- returns / remakes
  approved_by         uuid FK→employee
  note                text
  IX (restaurant_id, business_date)
  IX (restaurant_id, stock_item_id, business_date)
```

Every `wastage_event` writes a paired `stock_movement` of type `wastage` in the same transaction.
Never one without the other.

---

## 9 · Customers & feedback — 5 tables

```
customer                                         -- organization-scoped: a chain recognises the
  organization_id NN FK→organization             -- same diner across branches
  user_account_id     uuid UQ FK→user_account    -- nullable
  phone               text NN                    -- UQ (organization_id, phone)
  name                text
  email               text
  first_visit_at, last_visit_at  timestamptz
  visit_count         int NN default 0
  lifetime_value      numeric(12,2) NN default 0
  birthday, anniversary  date                    -- cheap, high-impact repeat driver
  is_active
  IX (organization_id, phone), IX (organization_id, last_visit_at)

customer_preference                              -- persists across visits. Jain, no onion, allergy.
  customer_id NN FK→customer
  type                text NN check(dietary|allergy|spice_level|seating|other)
  value               text NN
  is_critical         bool NN default false      -- allergy: must surface to the kitchen
  UQ (customer_id, type, value)

feedback
  restaurant_id, order_id FK→order               -- nullable but strongly nudged
  customer_id         uuid FK→customer
  overall_rating      smallint check(1..5)
  food_rating, service_rating, cleanliness_rating  smallint
  waiter_employee_id  uuid FK→employee
  comment             text
  source              text NN check(qr|app|staff|call)
  submitted_at NN, business_date NN
  IX (restaurant_id, business_date), IX (restaurant_id, waiter_employee_id)

feedback_line                                    -- per-dish rating
  feedback_id NN FK→feedback, order_line_id NN FK→order_line
  menu_item_variant_id uuid NN FK→menu_item_variant
  rating              smallint check(1..5)
  comment             text
  IX (menu_item_variant_id)

complaint                                        -- replaces the vision doc's separate Incident
  restaurant_id, customer_id FK→customer, order_id FK→order, order_line_id FK→order_line
  feedback_id         uuid FK→feedback
  category            text NN check(food_quality|service|delay|billing|hygiene|staff_conduct|other)
  severity            text NN check(low|medium|high|critical)
  description         text NN
  reported_by         uuid FK→employee           -- null when the customer raised it directly
  assigned_to         uuid FK→employee
  status              text NN check(open|investigating|resolved|closed)
  resolution          text
  compensation_amount numeric(12,2)
  resolved_at, closed_at  timestamptz
  customer_returned   bool                       -- the only honest measure of recovery
  IX (restaurant_id, status), IX (restaurant_id, business_date)
```

---

## 10 · Communication & tasks — 6 tables

```
conversation
  restaurant_id
  type                text NN check(direct|group|task|complaint|announcement)
  title               text
  ref_type, ref_id                               -- attaches a thread to a task or complaint
  created_by          uuid NN FK→employee
  last_message_at     timestamptz                -- denormalised: powers the inbox sort
  IX (restaurant_id, last_message_at DESC)

conversation_participant
  conversation_id NN FK→conversation, employee_id NN FK→employee
  joined_at NN, left_at
  last_read_message_id  uuid FK→message          -- watermark. See "eliminated" below.
  is_muted            bool NN default false
  UQ (conversation_id, employee_id)
  IX (employee_id, conversation_id)              -- "my conversations"

message
  restaurant_id, conversation_id NN FK→conversation
  sender_employee_id  uuid NN FK→employee
  body                text
  priority            text NN check(normal|high|urgent)
  reply_to_message_id uuid FK→message
  deleted_at          timestamptz                -- the one soft-delete exception (ADR 0008)
  IX (conversation_id, created_at DESC)

task
  restaurant_id
  title               text NN
  description         text
  source_message_id   uuid FK→message            -- a message promoted into a task
  complaint_id        uuid FK→complaint
  assigned_to         uuid FK→employee
  assigned_by         uuid FK→employee
  priority            text NN check(low|normal|high|urgent)
  status              text NN check(created|assigned|accepted|in_progress|completed|verified|
                                    cancelled)
  due_at              timestamptz
  completed_at, verified_at  timestamptz
  verified_by         uuid FK→employee
  IX (restaurant_id, assigned_to, status), IX (restaurant_id, due_at) WHERE status != 'verified'

task_event                                       -- append-only lifecycle log
  task_id NN FK→task, actor_employee_id NN FK→employee
  from_status, to_status  text
  note                text
  occurred_at         timestamptz NN

attachment                                       -- one table, many owners
  restaurant_id
  owner_type          text NN check(message|task|complaint|wastage_event|feedback|goods_receipt)
  owner_id            uuid NN
  file_key            text NN                    -- S3-compatible key (ADR 0005)
  file_name, mime_type  text NN
  size_bytes          bigint NN
  uploaded_by         uuid NN FK→employee
  IX (owner_type, owner_id)
```

---

## 11 · Shifts — 2 tables

Minimal on purpose. Waste and performance must attribute to a shift; full attendance, leave,
overtime and swaps are Phase 2.

```
shift
  restaurant_id, name NN                         -- 'Morning', 'Evening'
  start_time, end_time  time NN
  is_active

shift_assignment
  restaurant_id, shift_id NN FK→shift, employee_id NN FK→employee
  dining_area_id      uuid FK→dining_area        -- the section they cover. ADR 0011: an order
                                                 -- taken elsewhere is a DERIVED assist, so nobody
                                                 -- has to log helping a colleague.
  business_date       date NN
  status              text NN check(scheduled|present|absent|late|leave)
  clock_in_at, clock_out_at  timestamptz
  UQ (shift_id, employee_id, business_date)
  IX (restaurant_id, business_date)
```

---

## 12 · System — 3 tables

```
audit_log                                        -- APPEND-ONLY. Written by a service decorator.
                                                 -- Table created in M01, not M14: M01 introduces
                                                 -- role grants, deactivations and password resets,
                                                 -- which are exactly what an insider would use.
                                                 -- M14 still owns the decorator, /audit and the UI.
  restaurant_id       uuid                       -- nullable: org-level actions exist
  actor_employee_id   uuid FK→employee
  action              text NN                    -- 'order.void', 'recipe.update', 'stock.adjust'
  entity_type         text NN
  entity_id           uuid NN
  old_value           jsonb
  new_value           jsonb
  ip_address          inet
  metadata            jsonb
  occurred_at         timestamptz NN
  IX (restaurant_id, occurred_at DESC)
  IX (entity_type, entity_id)                    -- "who changed this dish's price?"
  IX (restaurant_id, actor_employee_id, occurred_at DESC)

idempotency_key                                  -- ADR 0010. The waiter double-tapped "Settle".
  restaurant_id
  key                 text NN                    -- UQ (restaurant_id, key); client-generated; 16–128
  endpoint            text NN
  request_hash        text NN                    -- same key + different body = 409, a client bug
  response_status     smallint
  response_body       jsonb
  state               text NN check(in_progress|completed|failed)
  expires_at          timestamptz NN             -- 24h; swept by a nightly job
  actor_employee_id   uuid FK→employee
  IX (expires_at)

notification
  restaurant_id, recipient_employee_id NN FK→employee
  severity            text NN check(critical|warning|caution|info|success)  -- matches UI tokens
  title NN, body
  ref_type, ref_id
  channels            text[] NN                  -- {in_app,push,email,whatsapp}
  read_at, dispatched_at  timestamptz
  IX (recipient_employee_id, read_at) WHERE read_at IS NULL
```

---

## 13 · Performance & recognition — 5 tables

Live metrics remain **queries** (`docs/schema.md` eliminated `waiter_performance` for good reason).
Stored here is only what cannot be derived: a frozen snapshot, a manager's note, an award that was
granted, and the scheme. See ADR 0011 and `docs/workload-fairness.md`.

```
incentive_scheme                                 -- the owner's weighting. Config, not results.
  restaurant_id, name NN
  period_type         text NN check(weekly|monthly)
  weights             jsonb NN                   -- {"accuracy":0.25,"rating":0.20,...}; sums to 1
                                                 -- RULE: volume weight <= accuracy + rating
                                                 -- (ADR 0011); enforced on save, unit-tested
  is_active           bool NN default true
  effective_from      date NN
  IX (restaurant_id, is_active)

performance_period
  restaurant_id, incentive_scheme_id NN FK→incentive_scheme
  period_start, period_end  date NN
  status              text NN check(draft|published|finalised)
  published_at        timestamptz                -- the freeze moment
  published_by        uuid FK→employee
  UQ (restaurant_id, incentive_scheme_id, period_start)
  IX (restaurant_id, status)

performance_score                                -- FROZEN on publish. Never recomputed. ADR 0011.
  restaurant_id, performance_period_id NN FK→performance_period
  employee_id         uuid NN FK→employee
  hours_worked        numeric(8,2) NN            -- the normalisation denominator
  metrics             jsonb NN                   -- {"covers_per_hour":4.2,"accuracy_pct":98.1,...}
                                                 -- each tagged controllable|context
  points              numeric(8,2) NN
  rank_in_period      smallint                   -- computed; NEVER exposed as a bottom-ranked list
  UQ (performance_period_id, employee_id)
  IX (restaurant_id, employee_id)

performance_note                                 -- manager context. Travels with the score.
  restaurant_id, performance_period_id NN FK→performance_period
  employee_id NN FK→employee, author_employee_id NN FK→employee
  note                text NN                    -- "was training the new hire"; "section closed"
  visible_to_employee bool NN default true
  IX (performance_period_id, employee_id)

recognition_award                                -- granted by a human. Never automatic.
  restaurant_id, performance_period_id FK→performance_period
  employee_id         uuid NN FK→employee
  type                text NN check(cash|leave|shift_preference|meal|recognition_only)
  amount              numeric(12,2)              -- null for non-cash
  citation            text NN                    -- what it is for, in words, shown to the employee
  granted_by          uuid NN FK→employee
  granted_at          timestamptz NN
  IX (restaurant_id, employee_id, granted_at DESC)
```

New permissions: `performance.view.own` (**granted to every role, not removable** — ADR 0011),
`performance.view.team`, `performance.publish`, `incentive.configure`, `recognition.award`.

---

## What was deliberately eliminated

Cut, with the reason. Each of these is a table someone would reasonably have created.

| Not built | Why | Instead |
|---|---|---|
| `message_read_receipt` | Would be the **largest table in the schema** — participants × messages. Your sketch had `read_at` on `message`, which cannot represent a group thread read by 3 of 5 people. | `conversation_participant.last_read_message_id` watermark. Unread count is one comparison. |
| `unit`, `unit_conversion` | Only three base units exist and conversion is one factor. | `base_unit` enum + `ingredient_profile.purchase_to_base` |
| `incident` (§21) | Structurally identical to `complaint` + `task` + `attachment`. Two tables for one concept diverge. | `complaint`, with `task` for follow-up |
| `waiter_performance`, `chef_performance`, `dish_stats` | **These are queries, not tables.** Storing them creates a second source of truth that silently drifts. | Views now; materialised rollups only when a dashboard query is measured to be too slow |
| `order_status_history` | `audit_log` already records every transition. | `audit_log` |
| `refund` | A refund is a negative payment. A second table means two places to sum. | `payment.amount < 0`, which must reference a `credit_note` — the tax document |
| `attendance` | Same rows as `shift_assignment` with a different name. | `shift_assignment.status` |
| `cctv_*`, `video_retention` | Vision doc §22. Legal exposure, storage cost, sells nothing. | — |
| `loyalty_*`, `quotation`, `delivery_platform_*` | Phase 2+. | — |
| `menu_item.price` | Half and full plates are different prices, recipes and costs. A price here would be wrong for every variant. | `menu_item_variant.price` |
| Screen-shaped tables | Your own principle, and the right one. | Entities; screens compose them |
| `assist_event` | Derivable: an order taken at a table in another employee's assigned section *is* an assist. A table would need someone to remember to log helping a colleague — the one thing the incentive must never depend on. | `order` + `shift_assignment.dining_area_id` |
| `employee_metric_daily` (live rollup) | The drift problem again. Live metrics are queries; only the published period is frozen (ADR 0011). | query, then `performance_score` on publish |
| Automatic payout trigger | A number must never pay a person. | `recognition_award.granted_by` |
| `deleted_at` on transactional tables | Blanket soft delete guarantees a forgotten `WHERE deleted_at IS NULL` eventually. | ADR 0008 three-tier deletion |

---

## The query this schema exists to answer

Per dish, last week: units sold, revenue, theoretical food cost, actual consumption, the variance,
waste attributed, average prep time, average rating.

```
menu_item_variant
  → order_line (sold, revenue)
  → recipe@version → recipe_line → stock_item      (theoretical cost, recursive through preparations)
  → stock_movement WHERE basis='actual'            (actual consumption)
  → wastage_event                                  (waste)
  → kot_ticket (ready_at − started_at)             (prep time)
  → feedback_line                                  (rating)
```

Every hop is a single indexed foreign key. If a proposed change adds a hop or removes an index on
that path, it is the wrong change.

## Migration order

Dependencies force roughly this sequence:

1. organization, restaurant
2. permission, role, role_permission, user_account, user_session, sign_in_choice, login_attempt, employee,
   employee_role_assignment
3. dining_area, restaurant_table, station, tax_group, tax_rate
4. supplier, stock_item, ingredient_profile, preparation_profile
5. menu_category, menu_item, menu_item_variant, modifier_group, modifier, menu_item_modifier_group
6. recipe, recipe_line
7. stock_batch, stock_movement, stock_count, stock_count_line
8. purchase_order, purchase_order_line, goods_receipt, goods_receipt_line
9. customer, customer_preference
10. cash_session, order, order_table, order_line, order_line_modifier, order_discount, order_charge,
    invoice, credit_note, credit_note_line, payment, cash_count, cash_movement
11. kot_ticket, kot_ticket_line
12. wastage_reason, wastage_event
13. feedback, feedback_line, complaint
14. shift, shift_assignment
15. conversation, conversation_participant, message, task, task_event, attachment
16. audit_log, notification, idempotency_key
17. incentive_scheme, performance_period, performance_score, performance_note, recognition_award

`stock_batch.goods_receipt_line_id` and `conversation_participant.last_read_message_id` are circular
against later steps — add both as a nullable FK in a follow-up migration.
