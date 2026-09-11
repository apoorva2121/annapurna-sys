# Database Schema

The concrete table specification. Conceptual model: `docs/domain-model.md`. Conventions:
ADR 0004 (money/time/units), ADR 0006 (preparations), ADR 0007 (identity), ADR 0008 (keys, deletion,
enums, numerics), ADR 0010 (idempotency, locking), ADR 0011 (performance).

**64 tables in 13 domains.** Everything here is Phase 1 unless marked `[1.5]`.

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

## 1 · Tenancy & identity — 9 tables

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
  address             jsonb
  settings            jsonb NN default '{}'      -- notification channels, feature toggles
  is_active           bool NN default true
  IX (organization_id)

user_account                                     -- authentication ONLY. ADR 0007.
  organization_id     uuid NN FK→organization
  email               text                       -- UQ (organization_id, email)
  phone               text                       -- UQ (organization_id, phone)
  password_hash       text                       -- null for invited-but-not-activated
  status              text NN check(invited|active|suspended|locked)
  mfa_secret          text
  last_login_at       timestamptz
  failed_attempts     smallint NN default 0
  locked_until        timestamptz
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
  is_active
  IX (restaurant_id, status)

station                                          -- tandoor | main_kitchen | chinese | cold | bar
  restaurant_id, code NN, name NN, seq, is_active
  UQ (restaurant_id, code)

tax_group                                        -- the tax CLASS. One row, for as long as it is charged.
  restaurant_id
  code                text NN                    -- UQ (restaurant_id, code). "GST5". Immutable.
  name                text NN                    -- a label; editable
  is_active
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

menu_item
  restaurant_id, menu_category_id NN FK→menu_category
  code                text NN                    -- UQ (restaurant_id, code)
  name                text NN
  description         text
  food_type           text NN check(veg|non_veg|egg)   -- legally required in India
  station_id          uuid NN FK→station         -- routing: which KOT printer/screen
  image_url           text
  is_active
  IX (restaurant_id, menu_category_id, is_active)

menu_item_variant                                -- Half/Full/Per-piece. PRICE LIVES HERE.
  restaurant_id, menu_item_id NN FK→menu_item
  code                text NN                    -- HALF|FULL|PIECE
  name                text NN
  price               numeric(12,2) NN
  tax_group_id        uuid NN FK→tax_group
  prep_minutes        smallint NN                -- standard; actuals come from kot_ticket
  is_active
  UQ (menu_item_id, code)

modifier_group                                   -- "Choose spice level", "Add-ons"
  restaurant_id, name NN
  min_select          smallint NN default 0
  max_select          smallint NN default 1
  is_required         bool NN default false

modifier
  restaurant_id, modifier_group_id NN FK→modifier_group
  name                text NN
  price_delta         numeric(12,2) NN default 0
  is_active

menu_item_modifier_group
  menu_item_id NN FK→menu_item, modifier_group_id NN FK→modifier_group, seq
  PK (menu_item_id, modifier_group_id)
```

Price on the **variant**, never the item. A half plate is a different price, a different recipe and
a different food cost.

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
  category            text                       -- meat|dairy|veg|grain|spice|oil
  storage_type        text check(ambient|chilled|frozen)
  current_unit_cost   numeric(14,6) NN default 0 -- cached weighted average; batches hold truth
  is_active
  IX (restaurant_id, kind, is_active)

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

recipe                                           -- versioned; belongs to a dish OR a preparation
  restaurant_id
  menu_item_variant_id    uuid FK→menu_item_variant
  produces_stock_item_id  uuid FK→stock_item     -- the preparation this recipe makes
  version             smallint NN
  is_current          bool NN
  effective_from      timestamptz NN
  notes               text
  CHECK (num_nonnulls(menu_item_variant_id, produces_stock_item_id) = 1)
  UQ (menu_item_variant_id, version), UQ (produces_stock_item_id, version)
  partial UQ on is_current per owner

recipe_line
  recipe_id           uuid NN FK→recipe
  component_id        uuid NN FK→stock_item      -- ingredient OR preparation: recipes nest
  quantity            numeric(14,4) NN           -- in the component's base_unit
  seq                 smallint NN
  IX (recipe_id), IX (component_id)              -- second index answers "what uses paneer?"
```

Nesting depth is capped at 3 and enforced in the service layer plus `seed/validate.py`. Historical
orders reference the recipe **version** live at the time, so food-cost history never rewrites itself.

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
  stock_count_id NN FK→stock_count, stock_item_id NN FK→stock_item
  system_quantity     numeric(14,4) NN           -- what the ledger says
  counted_quantity    numeric(14,4) NN           -- what is on the shelf
  variance_value      numeric(12,2) NN           -- the leakage number, in rupees
  reason              text
```

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
  is_active
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
  purchase_order_id NN FK→purchase_order, stock_item_id NN FK→stock_item
  quantity_ordered    numeric(14,4) NN           -- base units
  unit_price          numeric(14,6) NN

goods_receipt
  restaurant_id, purchase_order_id FK→purchase_order   -- nullable: ad-hoc market purchases
  supplier_id NN, received_at NN, business_date NN
  invoice_number      text
  invoice_amount      numeric(12,2)              -- what they billed
  received_by         uuid FK→employee
  IX (restaurant_id, business_date)

goods_receipt_line
  goods_receipt_id NN FK→goods_receipt, stock_item_id NN FK→stock_item
  quantity_invoiced   numeric(14,4) NN           -- what the bill says
  quantity_received   numeric(14,4) NN           -- what the scale says   <-- the variance
  quantity_rejected   numeric(14,4) NN default 0 -- quality rejection
  unit_price          numeric(14,6) NN
  rejection_reason    text
```

Ordered / invoiced / received as three separate numbers is the whole point. Collapse them and
"Supplier A short-delivered 4.2% this quarter — ₹18,400" becomes unanswerable.

---

## 7 · Orders — 7 tables

```
order
  restaurant_id
  order_number        text NN                    -- UQ (restaurant_id, order_number). Human-facing.
  type                text NN check(dine_in|takeaway|delivery)
  status              text NN check(open|sent|served|settled|cancelled|voided)
  restaurant_table_id uuid FK→restaurant_table   -- null for takeaway
  customer_id         uuid FK→customer
  waiter_employee_id  uuid FK→employee
  covers              smallint                   -- headcount; needed for per-cover metrics
  placed_at           timestamptz NN
  settled_at          timestamptz
  business_date       date NN                    -- ADR 0004. Group reports on THIS.
  subtotal            numeric(12,2) NN default 0
  discount_total      numeric(12,2) NN default 0
  tax_total           numeric(12,2) NN default 0
  grand_total         numeric(12,2) NN default 0
  theoretical_food_cost numeric(12,2)            -- frozen at settlement; prices move
  cancel_reason       text
  voided_by           uuid FK→employee
  version             integer NN default 1       -- optimistic lock (ADR 0010). Two waiters,
                                                 -- one table: last-write-wins loses a dish.
  IX (restaurant_id, business_date)
  IX (restaurant_id, status) WHERE status IN ('open','sent','served')   -- the live-orders index
  IX (restaurant_id, customer_id)
  IX (restaurant_id, waiter_employee_id, business_date)

order_line
  restaurant_id, order_id NN FK→order
  menu_item_variant_id uuid NN FK→menu_item_variant
  recipe_id           uuid FK→recipe             -- the VERSION used, frozen
  quantity            smallint NN
  unit_price          numeric(12,2) NN           -- copied, not joined: menu prices change
  line_discount       numeric(12,2) NN default 0
  tax_rate            numeric(6,4) NN            -- copied from tax_group at order time
  tax_amount          numeric(12,2) NN
  line_total          numeric(12,2) NN
  status              text NN check(pending|preparing|ready|served|cancelled|returned)
  special_instructions text
  cancel_reason       text
  IX (order_id), IX (restaurant_id, menu_item_variant_id)

order_line_modifier
  order_line_id NN FK→order_line, modifier_id NN FK→modifier
  price_delta         numeric(12,2) NN           -- copied

order_discount
  order_id NN FK→order
  type                text NN check(percentage|flat|comp)
  value               numeric(12,2) NN
  amount              numeric(12,2) NN
  reason              text NN
  authorised_by       uuid NN FK→employee        -- comps need a name. Always.

payment
  restaurant_id, order_id NN FK→order
  method              text NN check(cash|card|upi|wallet|online|due)
  amount              numeric(12,2) NN           -- NEGATIVE for a refund. No separate table.
  reference           text                       -- UPI txn / card auth
  status              text NN check(pending|success|failed|refunded)
  paid_at             timestamptz
  IX (restaurant_id, business_date via order)

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
  key                 text NN                    -- UQ (restaurant_id, key); client-generated
  endpoint            text NN
  request_hash        text NN                    -- same key + different body = 409, a client bug
  response_status     smallint
  response_body       jsonb
  state               text NN check(in_progress|completed|failed)
  expires_at          timestamptz NN             -- 24h; swept by a nightly job
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
| `refund` | A refund is a negative payment. A second table means two places to sum. | `payment.amount < 0` |
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
2. permission, role, role_permission, user_account, user_session, employee, employee_role_assignment
3. dining_area, restaurant_table, station, tax_group, tax_rate
4. supplier, stock_item, ingredient_profile, preparation_profile
5. menu_category, menu_item, menu_item_variant, modifier_group, modifier, menu_item_modifier_group
6. recipe, recipe_line
7. stock_batch, stock_movement, stock_count, stock_count_line
8. purchase_order, purchase_order_line, goods_receipt, goods_receipt_line
9. customer, customer_preference
10. order, order_line, order_line_modifier, order_discount, payment
11. kot_ticket, kot_ticket_line
12. wastage_reason, wastage_event
13. feedback, feedback_line, complaint
14. shift, shift_assignment
15. conversation, conversation_participant, message, task, task_event, attachment
16. audit_log, notification, idempotency_key
17. incentive_scheme, performance_period, performance_score, performance_note, recognition_award

`stock_batch.goods_receipt_line_id` and `conversation_participant.last_read_message_id` are circular
against later steps — add both as a nullable FK in a follow-up migration.
