# M06 · Procurement — Module Spec

**Status:** approved to build (owner instruction, 2026-09-13: *"if m05 is complete go with m06 as
well… plan and execute… I trust ur recommendation"*). Written first and in full anyway, because
`docs/engineering-guardrails.md` §"Working with an AI pair" rule 7 is right about where the
expensive mistakes are cheapest.

Schema already designed: `docs/schema.md` §6. Module entry: `docs/modules.md` M06.
Depends on M05 (`stock_batch`, `stock_movement`, `InventoryService.receive_stock`) — all shipped.
Compliance obligations checked against `docs/compliance-rules.md` §A5 and §A6 (see decision 5).

---

## Why this module is the cheapest money in the product

`docs/waste-model.md` §1, verbatim: *ordered 50 kg, delivered 47 kg, invoiced 50 kg. This happens
constantly and nobody notices, because nobody weighs.* Receiving loss runs 1–3% of spend, and it is
the only waste stage whose fix is a scale and a screen rather than a behaviour change.

The report this module exists to produce is one sentence:

> Supplier A short-delivered 4.2% across 31 deliveries this quarter — ₹18,400.

That sentence pays for the software on its own, and it is **unanswerable** unless ordered, invoiced
and received are three separate numbers in three separate columns. Collapse them — as every
spreadsheet in every restaurant already does — and the leak becomes invisible for ever. This module
is four tables and one screen standing between a restaurant and that.

M05 made the ledger able to hold the truth. M06 is the first module that puts a *supplier's* claim
next to the restaurant's own observation and keeps the difference.

---

## Scope

Five tables (`docs/schema.md` §6), their repositories, services and endpoints, the four screens
`docs/modules.md` M06 names, and seed data so the variance report is non-empty in the demo.

Plus one debt M05 deliberately left: `stock_batch.supplier_id` and
`stock_batch.goods_receipt_line_id` are columns without foreign keys, because they pointed at
tables that did not exist. **This module creates those tables and adds the constraints**, which
`docs/schema.md` §5 and the M05 build log both name as M06's job.

### The seven decisions that matter

Everything else in this spec is mechanical. These are not.

#### 1 · Three numbers, and a fourth. Never collapsed, never derived away

`purchase_order_line.quantity_ordered` · `goods_receipt_line.quantity_invoiced` ·
`goods_receipt_line.quantity_received` · `goods_receipt_line.quantity_rejected`.

All four are stored. Nothing in this module ever writes a single `quantity` column, and no read
endpoint returns one. The derivations are computed at read time and named, so a caller cannot
accidentally ask for the wrong one:

```
accepted        = received − rejected          ← the only quantity that enters stock
short_delivery  = invoiced − received          ← billed and not delivered. The money leak.
order_shortfall = ordered  − received          ← the supplier under-supplied the order
rejection       = rejected                     ← arrived and refused on quality
```

`accepted` is the one with a physical meaning: it is what goes on the shelf, so it is what
`stock_batch.quantity_received` gets and what the `receipt` movement posts. The other three are
measurements of a disagreement and are only ever reported.

This is the same shape as `stock_count_line`'s `system_quantity` beside `counted_quantity`, and for
the same reason (G-13 checklist item 5): **what a human counts at the gate goes in its own column,
next to what was claimed, and the two are never reconciled into one.** Invariant 7 pointed at the
delivery door.

#### 2 · A goods receipt is append-only, enforced by the database

`docs/decisions/0008-persistence-conventions.md` assigns `purchase_order` to the *transactional*
tier. It does not name `goods_receipt`, so this spec assigns it — to the **ledger** tier, alongside
`stock_movement`.

The reason is the threat, not the taxonomy. A receipt is the document that says how much arrived; it
writes stock movements that the database already refuses to change. If the receipt itself stayed
editable, the attack is one `UPDATE`: receive 47 kg, take 3 kg home, then edit the receipt to say 50
so the invoice reconciles and the variance report goes quiet. The stock movements would still say
47 — and the two would disagree with nothing able to say which was edited.

So migration 0017 installs the same `UPDATE`/`DELETE` refusal trigger that 0015 put on
`stock_movement`, on both `goods_receipt` and `goods_receipt_line`. There is no `PATCH` and no
`DELETE` on either in the API, because the server would refuse them.

**The correction path is explicit and separately visible:** a `stock.adjust` movement with
`ref_type='goods_receipt'` and `ref_id` set to the receipt. `stock_movement`'s `ref_type` CHECK
already permits `goods_receipt` — M05 designed for this. An adjustment carries a mandatory reason
and writes an audit row, so a corrected receipt leaves a trail that says who corrected it and why.
That is strictly better than an editable receipt, which leaves none.

#### 3 · PO numbers are allocated under an advisory lock, and that is a rehearsal

`po_number` is unique per restaurant (`docs/schema.md` §6) and human-facing, so it is allocated
server-side as `PO-000001`, `PO-000002`, monotonic per restaurant for ever.

The naive `SELECT max(...) + 1` is a race: two managers raising an order in the same second both
read 41 and both try to write `PO-000042`. The unique constraint saves the data and hands one of
them a 500.

So allocation takes `pg_advisory_xact_lock` keyed on the restaurant and the word `po`, then reads
the maximum, inside the same transaction as the insert. The lock is transaction-scoped, so it is
released by the commit or the rollback and cannot be leaked.

**This is deliberately the same mechanism M07 will need for GST invoice numbers**, where
`docs/modules.md` M07 requires *"sequential per financial year with no gaps"* and gaplessness is a
legal requirement rather than a nicety. Proving the pattern here, on a document where a gap costs
nothing, is much cheaper than debugging it on one where a gap is a compliance breach. The
concurrency test in chunk G is therefore load-bearing for a module three ahead of this one.

#### 4 · The client does no arithmetic, and sees no rupee variance until after it posts

Two rules collide on the weighing screen and the resolution is not obvious, so it is written down.

`docs/compliance-rules.md` §A5 and CLAUDE.md invariant 3 forbid arithmetic on money on the client.
That alone would allow a quantity subtraction in the browser — "3.2 kg short" as you type.

`docs/waste-model.md` forbids it anyway, and is the stronger argument: showing the rupee value of a
waste event *before* it is logged suppresses honest reporting, which is why M09's rule is *"rupee
value shown after logging, never before"*. A receiving screen that says **"this weight will flag
your supplier for ₹4,200"** while somebody is holding the scale is asking a human to choose between
an accurate number and an awkward conversation. Some of them will move the number.

So: **the receipt screen shows ordered, invoiced and received side by side in one row** — the
discrepancy is *visible*, three figures a person can read, with no client-side subtraction and no
judgement attached. **The server computes every variance and every rupee figure, and the screen
shows them in a confirmation panel after the receipt is posted**, when the weight can no longer be
edited.

#### 5 · `unit_price` excludes tax; landed cost includes it; the split is captured

`docs/compliance-rules.md` §A6 is binding here and it is easy to get expensively wrong: a restaurant
on the 5% composition scheme **bears input GST and cannot reclaim it**, so a quoted price is not a
cost. Storing only the pre-tax price understates food cost by the whole tax rate — on the product's
headline number.

Three columns, three different facts:

| Column | What it is |
|---|---|
| `goods_receipt_line.unit_price` | the price on the invoice, per **base unit**, **excluding** tax — directly comparable to the PO line's quoted price |
| `goods_receipt.tax_amount` | what the invoice charged as tax. Nullable: an unregistered market trader charges none |
| `goods_receipt.invoice_amount` | the invoice total actually payable, tax included — what leaves the bank |

**Landed unit cost**, which is what `stock_batch.unit_cost` is frozen at and therefore what every
downstream food-cost figure is built on:

```
line_total   = Σ (quantity_invoiced × unit_price)      over the receipt's lines
landed(line) = unit_price × (1 + tax_amount / line_total)
```

Tax is apportioned **pro rata by line value**. That is exact whenever every line on the invoice
carries one rate, which for a single supplier's invoice is the ordinary case, and an approximation
otherwise. The alternative — a per-item GST rate — is not available: `stock_item` carries no tax
rate, and `library/market-rates.yaml`'s `gst_rate` is research about a national market, not this
supplier's invoice. Recorded in Risks below rather than discovered later.

`tax_amount` is a **deviation from the §6 sketch** and it is here because of G-13 checklist item 3:
capture what cannot be reconstructed later. Without it, "how much input GST did this restaurant bear
last year" is permanently unanswerable, and that is a question an owner asks and an accountant needs.

**No reclaim path is implied or built.** The product states the tax borne; it does not compute input
credit, which depends on a scheme election this module does not model. GST e-invoicing filing is
explicitly out of scope for month 1 (CLAUDE.md).

#### 6 · One supplier invoice can be booked exactly once

A partial unique index on `(restaurant_id, supplier_id, invoice_number)` where `invoice_number IS
NOT NULL`.

Booking the same invoice twice is the most ordinary error in accounts payable and the most ordinary
small fraud: pay it once for real and once to somebody's cousin. It also silently doubles stock and
halves the apparent food cost, which is worse than the money — a variance report built on
double-booked receipts is not wrong by a little.

Partial, because `invoice_number` is legitimately null: the market purchase this module exists to
accommodate arrives with no paperwork at all.

#### 7 · `purchase_order.status` is stored, and the stored value is tested against a recomputation

The one place in this module where something derivable is stored. G-13 checklist item 6 asks the
question directly, so here is the answer rather than a silent choice.

A PO's state is a function of its receipts: fully received when every line's summed `accepted`
reaches `quantity_ordered`, partly received when any line has anything. Computing that is cheap for
one PO and quadratic for a list screen that filters by status — which is the screen a store manager
lives on.

So `status` is maintained by the service on every receipt, and `test_procurement_service.py` asserts
the stored value equals a recomputation from the receipt lines after every transition. A stored
derived value with no test is a bug waiting; with the test it is a cache.

Transitions, forward-only, with `cancelled` and `received` terminal:

```
draft ──send──▶ sent ──receive──▶ partial ──receive──▶ received
  │               │                  │
  └───cancel──────┴──────cancel──────┘        (reason mandatory)
```

Lines are editable in `draft` only. A receipt against a `cancelled` PO is refused with a 409 — that
is the one place receiving *is* refused, and it is refused because the document does not exist any
more, not because of a quantity.

---

## Not in scope

- **Payment, payables, ageing.** `payment_terms_days` is stored and reported on; no money moves.
  Payment gateway integration is out of scope for month 1 (CLAUDE.md).
- **Supplier price lists / contracted rates.** A PO line's `unit_price` is typed. Comparing it to
  the supplier's last price is a M13 report over data this module records, not a new table.
- **Returns to supplier / credit notes.** A quality rejection at the gate is modelled
  (`quantity_rejected` + `rejection_reason`) because it happens on the weighing screen. A credit
  note issued three days later is a legal document needing its own table and sequence (G-13 item 3)
  and it is not this module. → `docs/backlog.md`.
- **Reorder points and suggested orders.** The prep sheet (`docs/waste-model.md` §3) and par-level
  reordering are the demand-forecast chain, and they need M07's sales history to be worth anything.
- **Multi-branch purchasing.** A PO belongs to one restaurant. Out of scope for month 1.
- **Approval workflows.** A PO over ₹X needing an owner's sign-off is a real request from real
  restaurants and it is a Phase 2 feature. The seniority machinery exists if it is ever wanted.

---

## Deliverables

### Migration `0017_m06_procurement` — 5 tables + the two M05 constraints

Exactly `docs/schema.md` §6, plus:

- **`restaurant_id` on `purchase_order_line` and `goods_receipt_line`**, a deviation from the
  sketch, carried for exactly the reason `stock_count_line` carries one: every parent reference is a
  **tenant-safe composite foreign key** on `(id, restaurant_id)` against a `uq_*_id_restaurant`
  constraint, so attaching a receipt line to another restaurant's stock item is refused by Postgres
  rather than by a repository remembering to filter.
- **`tax_amount numeric(12,2)`** on `goods_receipt` (decision 5).
- **`UPDATE`/`DELETE` refusal triggers** on `goods_receipt` and `goods_receipt_line` (decision 2).
- The **partial unique index** on the invoice number (decision 6).
- `is_active` + `deactivated_at` on `supplier` — master-data tier. ADR 0008's tier table also lists
  `deactivated_by`, but `docs/schema.md`'s "applied to every table" convention says *"master data
  gets `is_active` + `deactivated_at`"* and `employee` carries exactly those two. The narrower of
  the two is followed, because *who* deactivated a supplier is already recorded where every other
  actor is: the `audit_log` row the service writes. A supplier is never deleted; historical receipts
  point at it for ever.
- CHECK constraints that catch nonsense: `quantity_ordered > 0`, `unit_price >= 0`,
  `quantity_invoiced >= 0`, `quantity_received >= 0`, `quantity_rejected >= 0`,
  **`quantity_rejected <= quantity_received`** (you cannot refuse more than arrived),
  `invoice_amount >= 0`, `tax_amount >= 0`, `payment_terms_days >= 0`,
  and `(cancelled_at IS NULL) = (cancel_reason IS NULL)` — a cancellation with no reason reads as a
  cancellation nobody has to explain.
- UQ `(purchase_order_id, stock_item_id)` and UQ `(goods_receipt_id, stock_item_id)`: an item
  appears once on an order and once on a delivery. This is also what makes the receipt→PO line
  match exact without a `purchase_order_line_id` column (see the checklist, item 1).
- **`ALTER TABLE stock_batch` adding the two foreign keys M05 left as bare columns** —
  `supplier_id → supplier(id)` and `goods_receipt_line_id → goods_receipt_line(id)`. Composite and
  tenant-safe where the target carries `restaurant_id`.
- Every index §6 names. `downgrade()` implemented and tested up→down→up.

### Backend — repository → service → API

**Repositories** (`repositories/procurement.py`) — tenant-scoped, no business rules.
`SupplierRepository` (list/active filter, name lookup), `PurchaseOrderRepository`
(`get_with_lines`, `get_for_update`, `next_number` under the advisory lock, `list_by_status`),
`GoodsReceiptRepository` (`get_with_lines`, `list_recent`, `received_by_po_line` — the summed
`accepted` per PO line, one aggregate query), and `supplier_variance(start, end)` — one grouped
aggregate over `goods_receipt_line`, bounded by `business_date`, never a Python loop.

**Services** (`services/procurement.py`) — all rules here.
`create_supplier` / `update_supplier` / `deactivate_supplier` · `create_order` (numbering,
line validation, `total_amount` computed server-side) · `update_order` (draft only) · `send_order` ·
`cancel_order` (reason required) · `receive` — the transactional one: one `goods_receipt`, its
lines, the landed-cost apportionment, a `stock_batch` + `receipt` movement **per accepted line via
M05's `InventoryService`**, the `stock_item` reprice to `cost_source='purchase'`, the PO status
recomputation, and the audit rows. All of it or none of it. · `supplier_variance`.

**Receiving reuses `InventoryService.receive_stock`** rather than writing batches itself. That is
the layering rule doing its job: the ledger has exactly one write path, it already handles the
business-date computation, the batch code and the paired movement, and a second implementation is
how the two drift. M06 passes it `source='purchase'`, the supplier, the receipt line and the landed
unit cost.

**Endpoints** — `api/v1/staff/procurement.py`. Every one declares a permission; every one gets a
tenant-isolation test; three new path parameters registered in `_VICTIM_PARAMETERS` with victim rows
seeded, or the build fails (the M05 build log's standing warning).

| Method | Path | Permission |
|---|---|---|
| GET | `/suppliers` | `supplier.view` |
| POST | `/suppliers` | `supplier.manage` |
| GET | `/suppliers/{supplier_id}` | `supplier.view` |
| PATCH | `/suppliers/{supplier_id}` | `supplier.manage` |
| GET | `/suppliers/{supplier_id}/variance` | `supplier.view` |
| GET | `/purchase-orders` | `supplier.view` |
| POST | `/purchase-orders` | `purchase.manage` |
| GET | `/purchase-orders/{po_id}` | `supplier.view` |
| PATCH | `/purchase-orders/{po_id}` | `purchase.manage` |
| POST | `/purchase-orders/{po_id}/send` | `purchase.manage` |
| POST | `/purchase-orders/{po_id}/cancel` | `purchase.manage` |
| POST | `/purchase-orders/{po_id}/receive` | `stock.receive` |
| POST | `/goods-receipts` | `stock.receive` |
| GET | `/goods-receipts` | `supplier.view` |
| GET | `/goods-receipts/{receipt_id}` | `supplier.view` |

**Three permissions, taken verbatim from `seed/organization.yaml`** — `supplier.view`,
`supplier.manage`, `purchase.manage` — and no fourth invented, because
`tests/test_permissions_catalogue.py` refuses a code the P1 design does not contain and it was right
to do so twice already.

**Receiving sits behind `stock.receive`, not `purchase.manage`, and that is the interesting line.**
Posting a receipt writes the stock ledger, so it is the ledger's permission — the one
`seed/organization.yaml` gives to the store manager who takes the delivery. The consequence is
separation of duties for free: the design grants the **accountant** `purchase.manage` and *not*
`stock.receive`, so the person who reconciles invoices can raise an order and can never sign for
one; and the **chef** holds neither, so a kitchen cannot book in a sack it then cooks. In a
four-person restaurant one human will hold both, which is ordinary — so `created_by` and
`received_by` are both stored and both shown, making it a visibility control rather than a block.

### Frontend — 4 screens

Supplier list + create/edit · purchase order create and list/detail with send and cancel ·
**goods receipt with weighing (the money screen)** · supplier variance report. Manager and store
surface, tablet-first, per `docs/ui/conventions.md` and the `restaurant-ui` skill.

### Seed

Two suppliers for the demo restaurant, one PO fully received, one partially received (so the demo
has an open order), one ad-hoc market receipt with no PO, and **one deliberate short delivery** so
the variance report has something to say before anybody constructs it — the same reasoning that put
a deliberate negative in the M05 seed.

---

## Threat question — *what would an insider do with this?*

Receiving is where stock enters the building, which makes it the other end of the pipe M05 guards.
An insider at the gate does not need to steal from the shelf; they can simply agree with the
supplier about what arrived.

| Attack | Control |
|---|---|
| Book in stock that never arrived, sell it, pocket the cash | The receipt writes `audit_log` with the actor and stores `received_by`; every batch carries `goods_receipt_line_id`, so every gram on the shelf traces to a signed document. A supplier whose deliveries match the invoice *exactly*, every time, is itself the signal the variance report surfaces |
| Weigh honestly, then edit the receipt to match the invoice | `UPDATE`/`DELETE` refused at the database on `goods_receipt` and `goods_receipt_line` (decision 2), and on the movements they wrote (0015). The only correction is an adjustment with a reason and an audit row |
| Book one supplier invoice twice | Partial unique index on `(restaurant_id, supplier_id, invoice_number)` (decision 6) |
| Invent a supplier and launder purchases through it | `supplier.manage` is not held by chef or kitchen staff; create and edit are audited with the actor; the variance report is per supplier, so a supplier with two deliveries and a large invoice is conspicuous. A supplier is deactivated, never deleted |
| Raise the order and sign for the delivery alone | `purchase.manage` and `stock.receive` are separate permissions and the design separates them by role. Where one person holds both, `created_by` and `received_by` both name them on the receipt |
| Pad `unit_price` at receipt to inflate stock value and flatter food cost | The receipt price is compared to the PO line's quoted price and the divergence is part of the three-way report; the reprice writes `stock_item.repriced` to `audit_log` with old and new values |
| Cancel an over-order to hide it | Cancellation requires a reason, is audited, sets `cancelled_at`, and does not delete the PO |
| Accept a delivery against another restaurant's PO | Composite tenant foreign keys, tenant-scoped repositories, generic suite 1 over every new route |
| Read a competitor's supplier list and prices | Same. A supplier list *is* commercially sensitive — it is who you buy from and what you pay |
| Reject 50 of 50 kg, keep the "rejected" stock | `quantity_rejected <= quantity_received` is a CHECK; rejection requires a reason; rejected quantity never enters stock but **is** reported, so a store manager with a high rejection rate is visible |

---

## Schema review checklist (G-13) — answered for all five tables

**1 · What metric will someone want from this row in M13/M17, and which timestamp does it need?**
"Short-delivery percentage and rupee value per supplier per period" — needs
`goods_receipt.business_date` (present, ADR 0004) to group on, and the four quantity columns.
"Which suppliers deliver late" needs `purchase_order.expected_at` against
`goods_receipt.received_at`; both present, no new column. **Per-line timestamps are deliberately
not carried**: every line of one delivery arrives in the same moment, unlike `kot_ticket_line`
where each dish is cooked at a different one (finding S2). If per-line receiving times are ever
wanted, that is a new column and a real change, not a gap this spec is papering over.

**2 · Where did this row come from?** `goods_receipt.purchase_order_id IS NULL` is the channel
marker, and it is load-bearing rather than incidental: a receipt with no order behind it is a market
purchase at market prices, which is a different cost story from contracted supply, and M13 will want
to split them. `stock_batch.source` records `purchase` on the ledger side. No separate `source`
column, because the nullable foreign key already answers the question without a second thing to keep
in step.

**3 · Is this row a legal document?** **The supplier's invoice is; we do not issue it.** M06 records
its identifiers (`invoice_number`, `invoice_amount`, `tax_amount`) and does not reproduce it, so no
sequence and no immutability rule beyond the append-only trigger. `po_number` is unique per
restaurant but **gaplessness carries no legal weight** — that is M07's invoice numbers, where it is
GST law, and decision 3 rehearses the mechanism here on purpose. Input GST borne is captured
(decision 5, `docs/compliance-rules.md` §A6); a **credit note** is a legal document and is
deliberately out of scope with a backlog entry rather than a half-modelled status field.

**4 · Does a modifier / option / variant change consumption?** No — M06 has no modifiers. Stock
items arrive in base units, converted at the boundary (invariant 5).

**5 · What does a human count at close?** **The delivery, at the gate, and it is the centre of the
design.** `quantity_received` is `counted`; `quantity_invoiced` is `expected`. Same shape as
`stock_count_line`, same rule: both stored, never reconciled into one.

**6 · Is the derived number O(N) forever?** The variance report is a grouped aggregate over
`goods_receipt_line` bounded by `business_date` on an index — it never walks the stock ledger, so no
snapshot table. The one derived value that *is* stored is `purchase_order.status`, argued in
decision 7 and guarded by a test that recomputes it. `purchase_order.total_amount` is likewise
stored and computed server-side from the lines, never accepted from a client
(`docs/security.md` A04).

**7 · Which ADR 0008 deletion tier, and is `restaurant_id` on the row?**

| Table | Tier | `restaurant_id` |
|---|---|---|
| `supplier` | **master data** — `is_active` + `deactivated_at` (the actor is in `audit_log`) | yes |
| `purchase_order` | **transactional** — no delete column; `status` carries state, `cancel_reason` the why | yes |
| `purchase_order_line` | transactional, with its parent | yes (added, for the composite FK) |
| `goods_receipt` | **ledger** — append-only, assigned by this spec (decision 2) | yes |
| `goods_receipt_line` | **ledger**, with its parent | yes (added) |

**8 · What would an insider do with this row?** The table above.

---

## Acceptance criteria

1. **Three-way variance arithmetic is exact on a golden case**: ordered 50 kg, invoiced 50 kg,
   received 47 kg, rejected 0.5 kg at ₹42.00/kg → `accepted` 46.5, `short_delivery` 3,
   `short_delivery_value` ₹126.00, `order_shortfall` 3, and the accepted quantity that reaches
   stock is 46.5 kg and not 47.
2. **A receipt with no PO still creates batches** (the ad-hoc market purchase) and appears in the
   supplier variance report with `order_shortfall` null rather than zero — nothing was ordered, so
   nothing was under-supplied, and null and zero are different claims.
3. **Landed cost includes apportioned tax.** Two lines, ₹1,000 and ₹3,000 of value, ₹200 tax →
   landed prices carry ₹50 and ₹150 respectively, and `stock_batch.unit_cost` is the landed figure.
   With `tax_amount` null, landed equals `unit_price` exactly.
4. **Partial delivery leaves the PO partially open**: after receiving 30 of 50, status is `partial`
   and the remaining 20 is reported as open; after receiving the last 20, `received`. The stored
   status equals a recomputation at every step.
5. **A line delivering nothing creates no batch and no movement** — `accepted = 0` must not attempt
   a zero-quantity movement, which `ck_stock_movement_quantity_delta` would reject and which would
   fail the whole receipt.
6. **`UPDATE goods_receipt` raises at the database level**, and so does `DELETE`, and so do both on
   `goods_receipt_line`.
7. **Booking the same supplier invoice twice is refused** with a 409 and a sentence naming the first
   receipt.
8. **Concurrent PO creation allocates distinct consecutive numbers** — two parallel creates against
   one restaurant produce `PO-000001` and `PO-000002`, never a duplicate and never a 500. Verified
   in both directions: the test fails with the advisory lock removed.
9. **A receipt against a cancelled PO is refused** with 409; against a `draft` PO too — you cannot
   receive an order nobody sent.
10. **Receiving reprices the stock item** to the landed cost with `cost_source='purchase'` and writes
    a `stock_item.repriced` audit row with old and new values.
11. **The receipt is atomic**: a forced failure after the second line leaves no receipt, no lines,
    no batches and no movements.
12. **Tenant isolation on every new endpoint**; permission matrix on every new route; the three new
    path parameters have victim rows.
13. **`make check` clean, zero warnings**, and 100% coverage on the new money, stock and permission
    paths.

---

## Chunks — one commit each

| # | Chunk | Lands |
|---|---|---|
| A | Migration 0017 + models + `docs/schema.md` §5/§6 updated + the two M05 foreign keys | 5 tables, append-only receipts, tenant-safe FKs |
| B | Permissions: catalogue + migration 0018 + fingerprint | `supplier.view`, `supplier.manage`, `purchase.manage` |
| C | Repositories + the variance aggregate + query-count assertions | reads |
| D | Service: suppliers, PO lifecycle, numbering under the advisory lock | the commercial document |
| E | Service: `receive` — three-way, landed cost, batches via M05, reprice, status | **the money** |
| F | Schemas + API + victim rows + generic suites green | endpoints |
| G | Backend tests: golden variance, concurrency on numbering, atomicity | acceptance 1–11 |
| H | Frontend: suppliers, PO create and list | the two ordinary screens |
| I | Frontend: goods receipt with weighing + supplier variance report | the money screen |
| J | Seed + gate + adversarial review + manual script + build log | Definition of Done |

---

## Risks, recorded before they are discovered

- **Pro-rata tax apportionment is an approximation** when one invoice mixes GST rates (decision 5).
  It is exact for a single-rate invoice, which is the common case. The alternative needs a per-item
  tax rate the product does not hold. If a pilot restaurant's invoices routinely mix rates, this
  becomes a per-line `tax_amount` and a migration — noted in `docs/backlog.md` so the trigger is
  written down rather than remembered.
- **`purchase_order.status` is a stored derived value** (decision 7). Guarded by a recomputation
  test. If that test is ever deleted, the cache becomes a lie.
- **The advisory lock serialises PO creation per restaurant.** That is correct and it is also a
  throughput ceiling of one order at a time per restaurant — entirely acceptable for a document a
  human types once or twice a day, and worth knowing before the same pattern is copied to M07's
  invoice numbers, which are issued *per bill* during service. M07 will need the same test at a very
  different rate.
- **Receiving is the module most likely to be used wrongly rather than built wrongly.** A store
  manager who types the invoiced figure into the received box destroys the entire value of the
  module while every test stays green. That is a UI problem, not a schema one, and it is why the two
  fields are visually separated and labelled *"what the bill says"* and *"what the scale says"*
  rather than *"quantity"* and *"actual"*. The manual test script exists to check that a real person
  reads them the way they were meant.
- **`stock_batch`'s two new foreign keys are added to a table that already has rows** in any
  environment where M05 ran. Nothing writes those columns today (the M05 build log says so
  explicitly), so the constraint validates against nulls and the migration is safe — but the
  migration asserts that rather than assuming it.
