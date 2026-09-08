# Domain Model

**Concepts and invariants.** The concrete tables, columns, keys and indexes are in
`docs/schema.md`; this document explains *why* they are shaped that way. Where the two disagree,
`schema.md` is authoritative for structure and this document for intent.

The vision doc's closing principle is the design constraint: **everything must be connectable**.
A complaint must reach `dish → order → waiter → prep time → ingredient → batch → cost`. Every
entity below therefore carries the foreign keys needed to walk that chain, even where month-1
screens don't yet use them.

## Tenancy

```
organization  ──<  restaurant (branch)  ──<  everything else
                        │
user_account ─1:0..1─ employee ──< employee_role_assignment >── restaurant
                                              └── role ──< role_permission >── permission
```

- `organization` — the paying customer. Billing lives here.
- `restaurant` — a single outlet. Holds `timezone`, `currency`, `business_day_start`, GST number.
- `user_account` / `employee` — authentication is split from the employment profile (ADR 0007). An
  employee without a login is normal; a customer can authenticate without being an employee.
- `employee_role_assignment` — (employee, restaurant, role), so one person holds different roles at
  different branches. Roles per vision doc §2: `owner`, `admin`, `manager`, `chef`, `kitchen_staff`,
  `waiter`, `store_manager`, `cleaner`, `accountant`. `customer` is **not** a role — customers are a
  separate entity, not staff users.

Every table below has `restaurant_id NOT NULL` unless stated otherwise.

## Front of house

- `dining_area` (zone/section) ──< `restaurant_table` (`code`, `seats`, `status`)
- `customer` — phone is the natural key in India; unique per organization, not per restaurant,
  so a chain recognises the same diner across outlets.

## Menu

```
menu_category ──< menu_item ──< menu_item_variant   (Half/Full, Regular/Jain)
                      │
                      └──< modifier_group ──< modifier   (Extra cheese, No onion)
```

Price and tax live on **`menu_item_variant`**, never on `menu_item` — a half plate and a full plate
are different prices, different recipes and different food costs. `tax_group` holds the GST rate;
restaurant food is typically 5% non-ITC, packaged items differ, so rate is per item, not global.

## Recipes, preparations and ingredients

Indian kitchens are base-driven, so recipes **nest**. See ADR 0006.

```
ingredient ──< recipe_line >── preparation ──< recipe_line >── menu_item_variant
                                    │
                                    └── batch_yield, shelf_life_hours, station
```

- `ingredient` — raw material master. Has `base_unit` (`g`/`ml`/`unit`), `shelf_life_days`,
  `storage_type`, default supplier, and `yield_factor` for trim loss (1kg raw chicken ≈ 700g usable).
- `preparation` — an in-house intermediate: makhani gravy, birista, boiled rice, marinated chicken.
  Has a standard `batch_yield`, `shelf_life_hours` (hours, not days — a gravy dies in two), and a
  station. Holds stock in batches and expires exactly like an ingredient.
- `recipe_line` — references **either** an ingredient or a preparation. Quantity in base units.
- Nesting is capped at 3 levels so cost rollup stays cheap.
- Recipes are **versioned**. Changing a recipe creates a new version; historical orders keep
  pointing at the version live when they were placed, or food-cost history rewrites itself
  retroactively.
- Producing a preparation batch writes `consumption` movements for its inputs and a `production`
  movement for its output, with unit cost frozen onto the batch at production time.

## Inventory — the ledger

```
stock_batch   (ingredient, batch_no, qty_received, expiry_date, unit_cost, supplier, location)
stock_movement (batch, type, qty_delta, reason, actor, occurred_at, ref_type, ref_id)
```

`stock_movement.type` ∈ `receipt | production | consumption | wastage | staff_meal |
complimentary | transfer | adjustment | count`.

`staff_meal` and `complimentary` are split out from `consumption` deliberately. Both are real,
both are large in Indian restaurants, and both look like theft or waste when lumped in with
ordinary consumption. Separating them is what makes the variance number trustworthy.

**Append-only.** On-hand quantity for a batch is `SUM(qty_delta)`. On-hand for an ingredient is the
sum across its non-depleted batches. This is what makes stock auditable and makes vision doc §30
(audit trail) free rather than a feature.

- **FEFO** (§10) — consumption draws from the batch with the earliest `expiry_date` first.
- `ref_type`/`ref_id` link a movement back to the order, wastage event or purchase that caused it.
  This is the connective tissue for "why did we lose ₹4,000 on paneer this week".

## Orders

```
order ──< order_line ──< order_line_modifier
  │         │
  │         └── menu_item_variant, recipe_version
  ├──< payment          (method, amount, reference)
  ├──< order_discount
  └──< kot_ticket ──< kot_ticket_line
```

- `order` carries `type` (`dine_in|takeaway|delivery`), table, waiter, customer, `status`,
  `placed_at`, `settled_at`, and a denormalised `business_date`.
- On settlement: post theoretical `consumption` movements from the recipe, and freeze
  `theoretical_food_cost` onto the order. Frozen, because ingredient prices move.
- Voids and refunds are sibling rows, never mutations. See CLAUDE.md invariant 6.

## Kitchen

- `station` — Tandoor, Chinese, Cold, Bar. `menu_item_variant` routes to a station.
- `kot_ticket` — one per order per station. Timestamps `printed_at`, `acknowledged_at`,
  `started_at`, `ready_at`, `served_at`. Those five timestamps are the entire kitchen-performance
  module (§16) and half of the customer-experience module; capture them from day one even though
  nothing reads them until M13.

## Waste, feedback, comms, tasks

- `wastage_event` — quantity, `wastage_reason` (a lookup **table**, not an enum: its rows carry
  policy such as `requires_photo` and the four-stage classification in `docs/waste-model.md`),
  stage, shift, actor, optional dish/batch link. Always writes a paired `stock_movement` of type
  `wastage`. Never one without the other.
- `feedback` — ratings (overall, food, service, cleanliness) plus optional per-dish rating, linked to
  `order` and therefore to waiter, kitchen and prep time. Feedback not linked to an order is nearly
  worthless for analytics — always try to attach it.
- `complaint` — the resolution workflow (severity, owner, SLA, what was comped, and whether the
  customer came back). It replaces the vision doc's separate `incident` entity (§21).
- `customer_preference` — Jain, no onion/garlic, allergy, spice level. Persists across visits;
  critical ones surface to the kitchen.
- `conversation ──< conversation_participant` and `conversation ──< message ──< attachment`.
  Conversations are typed (`direct`, `group`, `task`, `complaint`, `announcement`) so escalation
  (§25) can route by type. Unread state is a **watermark** on the participant
  (`last_read_message_id`), not a receipt row per message per person — see the eliminated-tables
  table in `docs/schema.md`.
- `task ──< task_event` — lifecycle `created → assigned → accepted → in_progress → completed →
  verified`. A message can be promoted to a task, keeping `source_message_id`.
- `audit_log` — actor, action, entity, before/after JSON. Written by a service-layer decorator, not
  by hand at each call site.

## The chain that has to work

This query must be answerable in SQL, because it is the product. It is the acceptance test for
M13 (`docs/modules.md`) and the exit criterion for the architecture phase:

> For last week, per dish: units sold, revenue, theoretical food cost from recipes, actual
> ingredient consumption from the ledger, the variance between them, waste attributed to it,
> average prep time, and average customer rating.

If a schema change would break that query, it's the wrong change.
