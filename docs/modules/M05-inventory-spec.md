# M05 · Inventory Ledger — Module Spec

**Status:** awaiting your approval. No code until you approve (`docs/sdlc.md` step 1).
Schema already designed: `docs/schema.md` §5. Module entry: `docs/modules.md` M05.
Depends on M04 (`stock_item`, `recipe`, the cost engine) — all shipped.

---

## Why this module is the spine of the product

M03 said what a restaurant sells. M04 said what a dish *should* cost. M05 is where the product
stops being a menu system and starts being the thing it exists to be: **the ledger that makes
theoretical and actual comparable.**

Everything downstream needs it. M07 settlement posts consumption here. M09 waste posts here. M13's
variance report — the product's headline insight — is a query over this table. Get the ledger shape
wrong and every number above it is wrong.

---

## Scope

Four tables (`docs/schema.md` §5), their repositories, services and endpoints, the five screens
M05 names, and the seed data to make them non-empty.

### The three decisions that matter

Everything else in this spec is mechanical. These are not, and I want them agreed before I build.

#### 1 · `basis` — what invariant 7 actually forbids

`docs/schema.md` says *"a query that sums both together is a bug"*, which is right but easy to
misread as "on-hand may only use one basis". It does not mean that. The precise rule:

- **On-hand is the sum of every movement, regardless of basis.** That is the book position — what
  the ledger believes is on the shelf. A receipt you counted in and a consumption the recipe
  inferred both move the book.
- **`basis` labels how a quantity was *derived*, for consumption analysis only.**
  - `theoretical` — derived from a recipe. M07 settlement writes these.
  - `actual` — physically observed. Receipts, weighed wastage, counts.
- **The forbidden query is a single "consumption" figure that adds the two.** They are two
  independent *measurements of the same period*, and their difference is the product:

  ```
  theoretical consumption = Σ |delta| WHERE type='consumption' AND basis='theoretical'
  actual consumption      = opening counted + receipts − closing counted
  variance                = actual − theoretical        ← the leakage number
  ```

This is the classic food-cost variance model, and writing it down now is what lets M13 compute it
without re-litigating the ledger.

#### 2 · On-hand may go negative, and that is a feature

**A consumption posting is never refused for insufficient stock.**

Refusing would mean M07 cannot settle an order because the storeroom paperwork is behind — the
system would stop a restaurant taking money over a bookkeeping gap. That is unacceptable, and it is
also backwards: **negative on-hand is the single most useful diagnostic this product can emit**,
because it means stock is being consumed that nobody recorded receiving. That is precisely the
cold-start reality (`docs/onboarding-cold-start.md`): Indian restaurants keep no records, so the
first weeks of any real deployment *will* show negatives, and the product's job is to surface them,
not to refuse service until someone does data entry.

So: consume FEFO across available batches; put any remainder on the oldest open batch, driving it
negative at its last known cost. If the item has **no batch at all**, create one —
`source='opening'`, `quantity_received=0`, `unit_cost` from the item's current costing basis — and
mark the movement's note. Every negative raises an alert on the on-hand screen with the words
*"consumed without a recorded receipt"*, which tells the manager what to actually do.

**DECIDE:** I am confident this is right. Say so if you disagree — it is much cheaper now.

#### 3 · Append-only is enforced by the database, not by discipline

Invariant 2 says the ledger is append-only. Today that would be a convention a repository honours,
and a convention is one careless `session.merge()` away from being violated silently — with no test
able to see it, because the row simply looks different afterwards.

So `stock_movement` gets a **Postgres rule/trigger refusing `UPDATE` and `DELETE`**, in the
migration. A correction is a new `adjustment` movement, which is what invariant 2 already says.
This is the same reasoning as G-13's schema review: the guarantee belongs where it cannot be
forgotten.

---

## Not in scope

- **Purchase orders and supplier invoices** — M06. `stock_batch.goods_receipt_line_id` stays
  nullable and unused; a receipt here is an ad-hoc "we bought this" entry, which is how a real
  market purchase arrives anyway.
- **Wastage events** — M09 owns `wastage_event`. M05 exposes the `wastage` movement *type* so M09
  has something to write to, and nothing more.
- **Order-driven consumption** — M07 posts it. M05 provides the service method and proves it works;
  no order exists yet to call it.
- **Transfers between restaurants** — the `transfer` type exists in the check constraint and no
  endpoint writes it. Multi-branch is out of scope for month 1.
- **Low-stock reorder points** — the *alert* is in scope (a par level on `stock_item` already
  exists if M04 put one there; otherwise the alert is expiry-only and reorder waits for M06).

---

## Deliverables

### Migration `0015_m05_inventory` — 4 tables

Exactly `docs/schema.md` §5, plus:
- the `UPDATE`/`DELETE` refusal on `stock_movement`
- `CHECK (quantity_received >= 0)` on `stock_batch`, and `CHECK (quantity_delta <> 0)` on
  `stock_movement` — a zero movement is always a bug and silently pollutes counts
- every index §5 names, including the two FEFO ones
- `downgrade()` implemented and tested up→down→up

### Backend — repository → service → API

**Repositories** (`repositories/inventory.py`) — tenant-scoped, no business rules.
- `batches_for_item_fefo(...)` — `ORDER BY expiry_date NULLS LAST, received_at` with `FOR UPDATE`
- `on_hand(...)` — one aggregate query over movements, never a Python loop
- `movements_for(...)`, `count_*`

**Services** (`services/inventory.py`) — all rules live here.
- `receive_stock` — creates a batch and its paired `receipt` movement in one transaction
- `produce_batch` — consumes inputs **and** produces the output batch in one transaction; output
  `unit_cost` = total input cost ÷ output quantity, via M04's cost engine, frozen at production
- `adjust` — an explicit correction, reason required
- `consume` — FEFO, `FOR UPDATE`, negative-tolerant per decision 2. This is what M07 will call.
- `submit_count` / `approve_count` — on **approval only**, post `adjustment` movements bringing book
  to counted, and compute `variance_value` in rupees per line

**Endpoints** — as `docs/modules.md` M05 lists. Every one declares a permission (default-deny) and
gets a tenant-isolation test.

### Frontend — 5 screens
Stock on hand (with negatives surfaced, not hidden) · receive stock · produce a preparation batch ·
physical count entry · expiry and low-stock alerts. Per `docs/ui/conventions.md` and the
`restaurant-ui` skill; manager surface, tablet-first.

### Seed
Opening batches for every seeded `stock_item`, a few near-expiry, and one deliberate negative so
the alert path is visible in the demo without anyone having to create it.

---

## Threat question — *what would an insider do with this?*

This is the module an insider steals through. The ledger is the only record of what was on the
shelf, so every write is a theft opportunity.

| Attack | Control |
|---|---|
| Edit a past movement to hide a shortfall | `UPDATE`/`DELETE` refused at the database |
| Post an adjustment to erase a variance | Adjustments require a reason, write `audit_log`, and are a *distinct type* the variance report shows separately — an adjustment is never invisible |
| Approve one's own count | `approve_count` requires a different employee from `counted_by`, and a permission a waiter does not hold |
| Inflate a receipt, pocket the difference | Receipt writes `audit_log` with actor; M06 will reconcile against supplier invoices |
| Consume against another restaurant's batch | Repository is tenant-scoped; isolation test per endpoint |
| Quietly delete a count that came out badly | `stock_count` status is forward-only: draft → submitted → approved. No delete endpoint |

---

## Acceptance criteria

1. On-hand equals the movement sum after **1,000 randomised operations** (property-based).
2. Concurrent consumption of one batch does not oversell — two parallel consumes of the same batch
   serialise via `FOR UPDATE`, and the total consumed equals what was requested.
3. FEFO picks the earliest-expiring batch, with `NULL` expiry last.
4. Production writes input consumption and output production **atomically** — a forced failure
   mid-way leaves neither.
5. A consumption exceeding stock succeeds, drives on-hand negative, and raises the alert.
6. An approved count posts adjustments such that book == counted afterwards.
7. A submitted count posts **nothing** until approved.
8. `UPDATE stock_movement` raises at the database level.
9. Tenant isolation on every endpoint; permission matrix on every route.
10. `make check` clean, zero warnings.

---

## Chunks — one commit each

| # | Chunk | Lands |
|---|---|---|
| A | Migration + models + schema doc check | tables, constraints, append-only rule |
| B | Repositories + on-hand aggregate + FEFO selection | with query-count assertions |
| C | Services: receive, adjust, consume (FEFO + negative) | the ledger's write path |
| D | Services: production, and stock counts | the two transactional ones |
| E | API + permissions + tenant-isolation suite | endpoints |
| F | Backend tests green, incl. the property-based one | acceptance 1–8 |
| G | Frontend: on-hand + alerts | the read screens |
| H | Frontend: receive, produce, count entry | the write screens |
| I | Seed + gate + adversarial review + manual script | Definition of Done |

**Tonight realistically reaches D–F.** G–I is a second sitting.

---

## Risks

- **The 1,000-operation property test is where bugs actually surface**, and it is also where a
  flaky test would cost the most. It gets a fixed seed so a failure is reproducible.
- **`FOR UPDATE` + FEFO under concurrency is the hardest thing in this module.** It needs a real
  database and real parallel sessions — `fresh_database`, not the shared-session fixture. This is
  exactly the class of defect guardrail G-2 exists for.
- **Cost attribution on a negative batch** is arguable: I use the batch's last known unit cost. The
  alternative (the item's current market rate) is defensible. Recorded here so the choice is
  visible rather than discovered.
