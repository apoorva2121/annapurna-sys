# M07 · Orders / POS — Module Spec

**Status:** approved to build by instruction (owner, 2026-09-13: *"you start with M07 as well once
you are done with M06"*), with one request back: **please read decisions 1–7 and the research
section before the manual pass.** This is the module where the product issues legal documents, and
the owner's time is best spent where a wrong assumption is a filing error rather than a bug.

Schema designed: `docs/schema.md` §7 (and §12 for `idempotency_key`). Module entry: `docs/modules.md`
M07. Binding: `docs/compliance-rules.md`, ADR 0004, ADR 0008, ADR 0010, `docs/security.md` A04/A08
and its GST section, audit findings S1, S4–S7, S9.

Depends on M03 (menu, variants, modifiers, tax groups) and M05 (the ledger) — both shipped. M05's
manual pass was **accepted rather than run** (`docs/checklist.md`), which unblocked settlement's
stock write; §B2 of that script remains open.

---

## Why this module is the money

Everything before this recorded what a restaurant *could* sell and what it *should* cost. M07 is
where it actually sells something, and three things happen at once that nothing else in the product
does:

- **A legal document is issued.** A GST tax invoice is not a receipt. It has a statutory numbering
  rule, statutory particulars, and statutory consequences for getting either wrong.
- **Theoretical consumption is posted.** Settlement writes the recipe-derived half of invariant 7 —
  the half M13's headline variance report is computed against.
- **Cash enters a till that nobody reconciles.** The cash-up is invariant 7 pointed at money:
  expected against counted, the variance recorded and never corrected away.

It is also the largest module in the product, and this spec is honest about that in Risks.

---

## Research — what binds this module, checked 2026-09-13

`docs/compliance-rules.md`'s first rule is *never fill an Indian rate, threshold or commencement date
from memory*. Everything below was looked up for this spec. Its second rule is *never conflate in
force, notified-but-not-in-force, unsettled and unverified* — so every row says which.

Two real bills were examined as ground truth (supplied by the owner): a Bangalore bill from
**06/06/2015** (VAT + Service Tax, pre-GST — used for structure only, never for a rate) and a Jaipur
bill from **19/04/2025** (CGST 9% + SGST 9% on a ₹1,580 subtotal).

| # | Rule | Instrument | Status |
|---|---|---|---|
| R1 | Restaurant service outside "specified premises": **5%, no input tax credit** | CGST rate notifications; see R2 | **in force** — consistent across sources |
| R2 | Restaurant service in "specified premises": **18% with ITC**. Definition changed w.e.f. **1 Apr 2025** to the *actual* value of any hotel unit in the *preceding* FY above ₹7,500/day, plus an Annexure VII opt-in declaration | Notification 05/2025-CTR (16 Jan 2025); CBIC FAQs 28 Mar 2025 | **in force**; the "exceeds" vs "₹7,500 or more" wording differs between sources and is **unverified** against the notification text |
| R3 | A **composition** restaurant pays tax on turnover and **may not collect tax** from customers; issues a **bill of supply**, not a tax invoice | CGST Act s.10; Rule 49 | **in force** |
| R4 | Composition bill of supply must be headed *"composition taxable person, not eligible to collect tax on supplies"* | CGST Rules, **Rule 5(1)(f)** ((g) is the signboard rule) | **in force**. My prior belief was (g); two sources corrected it |
| R5 | Tax invoice particulars: supplier name, address, **GSTIN**; date; per-item description, quantity, value, taxable value, rate and amount of tax | CGST Rules, Rule 46 | **in force** |
| R6 | Invoice serial: **consecutive, ≤ 16 characters, digits/letters and `-` `/`, unique for a financial year**, one or more series | Rule 46(b) | **in force** |
| R7 | Financial year commences **1 April** | General Clauses Act 1897, s.3(21) | **in force** |
| R8 | A cancelled invoice keeps its number; issued/cancelled counts and serial ranges are reported | GSTR-1 Table 13 (documents issued) | **in force** (return practice) |
| R9 | A reduction after an invoice is issued is a **credit note** with its own serial, referencing the original invoice number and date | CGST Act s.34; Rule 53 | **in force** |
| R10 | Discount given at or before supply **and recorded on the invoice** is excluded from taxable value; a post-supply discount needs a credit note | CGST Act s.15(3)(a),(b) | **in force** |
| R11 | Change in rate: the rate follows whichever side of the change **two of three** events fall on — supply, invoice, payment | CGST Act s.14 | **in force**; primary text not fetched (TLS failure on the CBIC site), four secondary sources agree |
| R12 | Tax payable is rounded to the nearest rupee (≥ 50 paise up); returns report invoice values to two decimals | CGST Act s.170; GST portal guidance | **in force**. Whether an *invoice's* payable total is rounded is **practice, not law** — the 2015 bill rounded, the 2025 bill did not |
| R13 | Tax invoice optional below ₹200 to an unregistered recipient, with an end-of-day consolidated invoice | CGST Act s.31(3)(b); Rule 46 proviso | **in force**, permissive — not used (decision 1) |
| R14 | SAC **996331**; required on B2C invoices only above ₹5 Cr aggregate turnover | Notification 78/2020-CT | **in force** |
| R15 | Alcoholic liquor for human consumption is **outside GST**; state VAT/excise applies | Constitution Art. 366(12A) (101st Amendment) | **in force** |
| R16 | A service charge **may not be added by default** or under another name | CCPA guidelines (4 Jul 2022), upheld by Delhi HC single judge (28 Mar 2025) | **in force** at first instance; **appeal pending** before a division bench — *unsettled* at appellate level |
| R17 | Whether GST applies *to* a service charge | — | **unsettled**. A POS vendor says it may not be taxed; valuation law suggests it is part of value; CCPA forbids taxing the food-plus-charge total. Not resolved here |
| R18 | Packaging charged on takeaway is part of the composite supply, taxed at the food rate | CGST Act s.8 (composite supply) | reported consistently; **unverified** against a ruling |
| R19 | GST registration threshold for services: ₹20 lakh (₹10 lakh special-category states) | CGST Act s.22 | reported consistently; **not used by M07** |

**What the Jaipur bill shows, stated carefully.** It charges 18% and prints no GSTIN. Under R1–R3 a
standalone restaurant charges 5% (regular) or collects nothing (composition), and under R5 a
registered supplier's tax invoice carries its GSTIN. So the bill is inconsistent with the rules *as
reported* whichever scheme applies. This spec does not call it illegal — sources are partly
secondary, and M18's rule is *no legal advice* — but it is exactly the case M18 exists to surface,
found on the first real bill examined.

---

## The eleven decisions that matter

### 1 · An invoice is its own legal document, numbered at settlement

`docs/security.md` says invoice numbers are gapless per financial year. Finding S1 says the schema
has nowhere to put them. So there is an `invoice` table, and its number is allocated **at settlement
and not before**:

- An order that is opened, sent and then cancelled **never consumed an invoice number**, so its
  cancellation cannot make a gap. The pre-settlement printout is a *provisional bill* carrying the
  order number, never an invoice number.
- Allocation uses the **transaction-scoped advisory lock M06 rehearsed** for purchase-order numbers,
  keyed on restaurant + financial year. M06 proved it under five-way contention; M07 needs it per
  bill, during service.
- Format **`2026-27/000123`** — 14 characters, digits plus `-` and `/`, which satisfies R6 and makes
  the financial year part of the number, so a new year starts a new series without a lookup.
- **1 order ↔ 1 invoice.** Splitting a bill by items moves the chosen lines to a new order on the
  same table *before* settlement (decision 9), so "which invoice covers this line" is always a single
  join. Finding S1 proposed `invoice_line` under one order; that duplicates `order_line`, which is
  already immutable after settlement (invariant 6), and a copy that can disagree with its source is
  the thing invariant 2 exists to stop.
- R13's sub-₹200 consolidated invoice is **not used**. Issuing an invoice for every settled order is
  always permitted; the relaxation saves paper and costs a second reporting path.

**The financial year comes from the calendar date of issue in the restaurant's timezone, never from
`business_date`.** R5 makes the invoice date the date of issue. A bill settled at 01:30 on 1 April
belongs to **business day 31 March** and to the **new financial year's series**. The FY boundary is
midnight; the business-day boundary is 05:00. A new helper in `app/core/business_day.py` computes it,
tested across that exact night.

### 2 · A refund is a negative payment *and* a credit note — and those are different things

`docs/schema.md` deliberately **eliminated a `refund` table**: *"A refund is a negative payment. A
second table means two places to sum."* `docs/security.md` says *"Refunds are credit notes, linked to
the original invoice."* These are not in conflict, and the spec has to say why in words, or the next
reader sees `credit_note` as the eliminated table returning:

- **The money** going back is a `payment` row with a negative amount. No refund table. One place to
  sum, as the schema intended.
- **The legal document** that reduces output tax is a `credit_note` (R9): its own serial, referencing
  the invoice number and date. It moves no cash. A credit note can exist with no refund at all — a
  complaint settled with a discount on a bill already paid — and its lines say which items and how
  much tax.

A settled order is never edited (invariant 6). After settlement the only reversal is a credit note,
full or partial. **Invoice cancellation** (R8 — status `cancelled`, number retained) is allowed only
on the **business date of issue**, requires `order.void` and a reason, and exists for the invoice
issued in error; anything later is a credit note.

### 3 · Only a regular-scheme restaurant may collect tax. The "two 5%s" trap

The most confusable thing in this module is two rules both called five percent:

| | **Regular**, 5% without ITC | **Composition** |
|---|---|---|
| Collects tax from the customer | yes — CGST 2.5% + SGST 2.5% | **no** (R3) |
| Document | **tax invoice** | **bill of supply** |
| Header | — | *"composition taxable person, not eligible to collect tax on supplies"* (R4) |
| Tax line on the bill | yes | **none** |

So `restaurant.gst_scheme` (`regular` \| `composition` \| `unregistered`) is a setting, audited on
change, and it decides the document. **Only `regular` may put tax on a bill** — enforced in the
service and by a CHECK on `invoice` (`tax_total = 0 unless document_type = 'tax_invoice'`). A
composition restaurant printing CGST/SGST is a direct breach of R3; the database refuses to let the
product do it. The seed restaurant uses `GST5 (restaurant, no ITC)`, which is the regular scheme.

M07 does **not** evaluate eligibility (turnover thresholds, specified premises). Which scheme and
which rate a restaurant is under is its legal declaration, entered as configuration; M18 is where
the product checks those declarations against evidence.

### 4 · Tax per line, CGST and SGST computed independently

ADR 0004 requires tax computed and stored per line. For intra-state supply — every dine-in, because
the place of supply is the restaurant — the line's rate is split in two and **each half is computed
on the line's taxable value and rounded to the paisa independently**: `cgst = round(v × r/2)`,
`sgst = round(v × r/2)`. They are therefore always equal, which is what the Jaipur bill shows
(`142.20` each on `₹1,580`). Computing a total and halving it produces an odd paisa that has to be
given to one side; computing each half directly never does.

The printed "CGST @2.5% on ₹X" groups **sum the stored lines**; they are never recomputed from the
group base, which could differ by a paisa from the sum of what was actually charged.

`tax_group` gains a **`regime`** (`gst` \| `non_gst`). A `non_gst` line (R15, liquor) is not split
into CGST/SGST. M07 builds the column and refuses to split such a line; it does **not** research or
seed any state's VAT rate — no pilot restaurant serves alcohol, and 28 states' excise schedules are
not a guess worth making.

Inclusive rates (`tax_rate.is_inclusive`, from M02) extract tax as `price × r / (1 + r)`.

### 5 · The rate follows Section 14, which means the median of three timestamps

The obvious rule — snapshot the rate when the line is added — is wrong at a rate change, and the
live example is midnight on 22 Sep 2025. R11: the rate follows the side of the change on which **two
of** supply, invoice and payment fall. For one change boundary, *two of three before* is exactly
*the median is before*. So:

```
rate_date = median(served_at, invoiced_at, paid_at)     → the rate effective on that date
```

Food served 23:55, UPI paid 23:58, bill printed 00:02 on a change night: two events before, **old
rate** — although the invoice is dated after. "Use the rate at settlement" gets that wrong.

The rate is **snapshotted at line add** (so the bill shown before payment is right in the ordinary
case) and **re-frozen at settlement** from the median date. It is stored once, at settlement, and
never re-derived afterwards (ADR 0004). A property test asserts the median rule equals the two-of-
three rule for every ordering of three instants around a boundary.

This needs a **`served_at`** on the order. Until M08 exists it is set when the order is marked
served, or defaults to the settlement instant.

### 6 · Discounts come before tax, are on the invoice, and are apportioned to lines

R10: a discount at or before supply, **recorded on the invoice**, reduces taxable value. So discount
precedes tax, and because tax is per line (decision 4), an order-level discount has to reach the
lines: it is **apportioned pro rata by line value using the largest-remainder method**, so the line
shares sum to the discount exactly, to the paisa, with no rounding residue to lose.

- Every discount and every comp carries `authorised_by NOT NULL` and a reason (`docs/security.md`
  A04). Seed signal 11 — *comps ≈ ₹9k/month, 70% authorised by one manager* — is unanswerable
  without it.
- `order.discount` is not held by a waiter (P1 design: *"the classic leakage vectors"*).
- **After settlement a discount is a credit note** (R10(b)), never an edit.
- **A discount never grows past what its authoriser approved.** A percentage or a comp is
  recomputed as the bill changes, so a dish coming off shrinks it, but dishes added afterwards
  do not stretch it: `authorised_amount` records the rupee figure at authorisation, and
  `amount <= authorised_amount` is a CHECK (second reader, finding 4; migration 0021).

### 7 · Charges: packaging taxed, service charge off by default, tips outside the base

- **Packaging** (takeaway) is part of the composite supply (R18) and taxed at the restaurant rate.
- **Service charge** is **disabled unless a restaurant deliberately enables it**, is **never
  default-applied** to an order, is added as an explicit removable line, and cannot be relabelled
  (R16). Its own GST treatment is unsettled (R17), so `order_charge.tax_group_id` is **nullable** and
  a restaurant that enables service charge chooses its treatment — the settings screen says, in
  words, to ask their accountant. The default makes the whole question moot, which is why it is the
  default.
- **Tips** are recorded on `payment.tip_amount`, outside taxable value, and attributed to the
  order's waiter — M17 names `tips_received` as a context metric.

`order_charge` is audit finding S7's table.

### 8 · Idempotency: the key is made at the tap, and the wrapper refuses to forget it

ADR 0010 asks for two things that pull against each other: the key must be **created when the user
taps** (so a retry after a timeout carries the same key), and the client wrapper must attach it
**automatically** (so it cannot be forgotten per call site). Generating it inside `apiPost` breaks
the first — TanStack Query's retry would mint a fresh key every attempt.

Resolution: **the hook creates the key at tap time and passes it with the mutation; the wrapper
refuses to send a listed endpoint without one.** Both rules hold.

Server side, `idempotency_key` is written **in the same transaction as the effect**:

- a duplicate key **blocks on the unique index** until the first transaction finishes, then
  **replays the stored response** — serialisation from Postgres, not from application code;
- if the first transaction **rolls back**, its key row rolls back with it, so an honest retry is
  allowed;
- the same key with a **different request body** is `409` — a client bug, not a retry (ADR 0010).

Behind it in M07: settle, payment, refund, void, credit note. **Retrofitted:** `POST /goods-receipts`
and `POST /purchase-orders/{id}/receive`, which `docs/backlog.md` explicitly un-defers with M07 (a
market purchase has no invoice number, so today a double tap books stock twice). M05's stock POSTs
follow in a late chunk if it fits; otherwise they get a backlog row with that trigger.

`order.version` is the optimistic lock for collaborative edits (ADR 0010): a stale version is `409`
with the current state, never last-write-wins.

### 9 · Split bills: payments split by default, orders split by items

"We'll pay separately" in an Indian restaurant is overwhelmingly several UPI payments against one
bill. So **several payments on one invoice** is the default split, and it needs no new structure —
`payment` already has many rows per order.

Splitting **by items** — "the corporate lunch goes on a separate GST invoice" — moves the chosen lines
to a new order on the same table before settlement, and each order settles to its own invoice
(decision 1). Splitting one invoice into fractional shares of each line is **not built**: it produces
invoice lines with fractional quantities that no customer can reconcile against the menu.

### 10 · Settlement is one transaction, and theoretical consumption does not explode preparations

Settle writes, atomically or not at all (ADR 0010 §Transaction boundaries): the invoice and its
number, the payments, the re-frozen line tax (decision 5), a `consumption` movement per recipe
component with `basis = 'theoretical'`, `ref_type = 'order'`, the frozen `theoretical_food_cost`, and
the audit rows.

- **Consumption uses the recipe's direct components and does not explode preparations to raw
  ingredients.** A dish consumes makhani gravy from gravy stock; the onions were consumed when the
  gravy was *produced* (M05). Exploding them again would double-count every preparation in the
  product.
- **Modifier recipes are consumed too.** "Extra cheese" is 40 g that no dish recipe accounts for;
  M04 built `current_for_modifier` for exactly this.
- **`theoretical_food_cost` is frozen from the cost engine at settlement**, at today's unit costs,
  with the costing snapshot loaded **once per settlement** rather than per line. It is deliberately
  a different number from the FEFO batch cost the consumption movements carry: one is what the recipe
  says the plate should cost, the other what the stock on the shelf actually cost. Both are stored;
  neither overwrites the other (invariant 7's shape).
- Consumption is never refused for insufficient stock (M05 decision 2). A restaurant that never
  recorded producing its gravy will see gravy go negative at the first settlement — which is the
  signal, not a bug.

### 11 · Cash-up: expected is derived, the variance is recorded, and a payout is a row

`cash_session` opens with a declared float and closes with a counted amount; `cash_count` holds the
denomination breakdown. **Expected cash is never stored** (`docs/modules.md`): opening float + cash
payments inside the session − payouts inside the session. That stays stable after close because
payments and payouts are append-only and a later refund posts to the session in which it happens.
The **variance is stored at close and never corrected away**; a correction is a new adjustment row
with a reason, by a different employee from the one who closed it (M05's count-approval rule, held
the same way).

**Cash is posted only into an open till.** Settlement and refunds share-lock the open till, so a
till being closed is waited for rather than written into, and migration 0021 refuses a payment
into a closed one. **A cancelled invoice's cash stops counting towards its till**, because the same
notes are settled again against the right table; once that till has been counted, the invoice can
no longer be cancelled, so a closed till still never moves (second reader, findings 1 and 3).

**Payouts are modelled nowhere today**, though `docs/modules.md`'s own formula subtracts them — ₹300
handed to a vegetable vendor from the till is the most ordinary cash event in the country. So
**`cash_payout`**: append-only, amount, reason, authoriser.

**The P1 permission design has no cash permission.** `tests/test_permissions_catalogue.py` refuses
any code the design does not contain, and it has been right to twice. So this spec **amends the
design** in `seed/organization.yaml` with **`cash.manage`** (owner, manager) — recorded here as an
amendment rather than slipped into the catalogue. A waiter holds `order.settle` and takes cash; a
waiter does not close the till.

---

## Not in scope

- **KOT tickets** — M08 owns `kot_ticket`/`kot_ticket_line`. M07's "send" changes status and stamps
  `sent_at` per line; it creates no tickets.
- **IRN / e-invoicing** — out of scope for month 1 (CLAUDE.md). Nullable `irn` and recipient-GSTIN
  columns exist so it needs no schema change later (`docs/security.md`).
- **Liquor VAT rates** — the regime column only (decision 4).
- **Aggregator CSV import** — finding S4's `channel` and `external_order_id` columns are captured;
  the importer is not built. Aggregator tax duties do not apply (`docs/compliance-rules.md` §C).
- **Consolidated sub-₹200 invoicing** (R13), **fractional-share invoice splits** (decision 9).
- **Offline outbox / service worker** — the waiter screens show the persistent offline banner and
  retry safely (the idempotency key makes a retry harmless); queued offline writes are a later piece.
  Offline-first sync is out of scope for month 1.
- **Payment gateway integration** — `payment.method` and `reference` record what happened; no money
  is moved by the product.
- **Table merge UI beyond "add a table to this order"** — finding S9's join table is built so merging
  needs no migration.

---

## Deliverables

### Migrations
- **0019** — the order tables; `order_table` (S9); `order_charge` (S7); `invoice`; `credit_note` and
  `credit_note_line`; `idempotency_key`; `cash_session`, `cash_count`, `cash_payout`;
  `restaurant.gst_scheme`; `tax_group.regime`.
- **0020** — `order.*` and `cash.manage` permissions.
- Invoice and credit-note numbers are unique per `(restaurant_id, financial_year, number)`; settled
  orders, invoices, credit notes, payments and payouts **refuse UPDATE and DELETE by trigger** where
  they are append-only, as `stock_movement` and `goods_receipt` do.

### Backend
Repositories → services → API, per layer rules. New helpers: `financial_year_of()` beside
`business_date_of()`; `tax.split_line()` and `tax.rate_date()`; largest-remainder apportionment.

### Endpoints (every one declares a permission; every path parameter gets a victim row)

| Method | Path | Permission |
|---|---|---|
| GET/POST | `/orders` | `order.view` / `order.create` |
| GET | `/orders/{order_id}` | `order.view` |
| POST/PATCH/DELETE | `/orders/{order_id}/lines[/{line_id}]` | `order.modify` |
| POST | `/orders/{order_id}/send` · `/served` · `/bill` | `order.modify` |
| POST | `/orders/{order_id}/split` | `order.modify` |
| POST | `/orders/{order_id}/discounts` | `order.discount` |
| POST/DELETE | `/orders/{order_id}/charges[/{charge_id}]` | `order.modify` |
| POST | `/orders/{order_id}/settle` · `/payments` | `order.settle` |
| POST | `/orders/{order_id}/cancel` | `order.modify` (unsettled only) |
| POST | `/orders/{order_id}/waiter/claim` | `order.modify` — Assign to me, an unserved dine-in order only *(2026-09-14)* |
| POST | `/orders/{order_id}/waiter` | `order.assign` — move to another waiter, with a reason *(2026-09-14)* |
| GET | `/waiters` | `order.assign` — active staff holding `order.create` here *(2026-09-14)* |
| POST | `/invoices/{invoice_id}/cancel` | `order.void` |
| POST | `/invoices/{invoice_id}/credit-notes` | `order.void` |
| GET | `/invoices/{invoice_id}` | `order.view` |
| POST | `/setup/tables/{table_id}/status` | `restaurant.configure` |
| GET/POST | `/cash/sessions` · `/cash/sessions/{session_id}/close` · `/payouts` · `/adjustments` | `cash.manage` |

The last-but-one row closes a backlog item owed to M07: `status` leaves the general table PATCH, and
a transition table refuses `free` or `out_of_service` while an order is open on the table.

### Frontend (waiter and manager surfaces)
Table map · order taking (thumb-reachable, ≥ 48 px, primary action bottom-right, ≤ 2 taps table →
send) · bill view (provisional, then invoice) · split · payment · void / credit note · cash session
open, payout, close. The waiter patterns `docs/ui/design-system.md` §5 says M07 owes — *table map
cell, order line row, money display, quantity stepper* — are documented there in the same PR.

### Fixes this module owes the codebase
- **Log context was never set.** `restaurant_id_var` and `actor_id_var` exist in
  `app/core/logging.py` and are read by the formatter, but nothing ever sets them, so every business
  event M05 and M06 emits logs with no tenant — and `docs/observability.md` claims otherwise. Fixed in
  `current_actor`, with a regression test written first.
- **Table status transitions** (backlog, *"Un-defer with M07"*).
- **Receiving idempotency** (backlog, *"Un-defer with M07"*).

### Seed
Enough to make the screens non-empty: an open order, a sent order, a settled order with an invoice,
one partial credit note, a closed cash session with a small deliberate shortfall. The 120-day volume
is M15's.

---

## Threat question — *what would an insider do with this?*

| Attack | Control |
|---|---|
| Tamper with a price on the client | The server recomputes every price, tax and total; the client sends only what was ordered (A04) |
| Settle, pocket the cash, then delete or edit the order | Settled orders, invoices and payments refuse UPDATE/DELETE by trigger; reversal is a credit note with an actor and a reason |
| Cancel a paid bill to make the cash disappear | Invoice cancellation only on its business date, needs `order.void` (not held by a waiter), keeps its number and is reported as cancelled (R8) |
| Skip invoice numbers to hide sales | Numbers allocated under an advisory lock inside the settlement transaction; gaplessness asserted by test |
| Comp a friend's bill | `authorised_by NOT NULL` + reason + audit row; comps by authoriser is seed signal 11 |
| Double-tap settle to charge twice | Idempotency key; duplicate replays the original response |
| Short the till and blame the float | Expected cash derived from payment rows; variance stored at close; correction by a different employee, with a reason |
| Take cash out as an undocumented "payout" | Payouts are rows with an authoriser and a reason, and they appear in the expected-cash formula |
| Charge a mandatory service charge disguised as something else | Service charge off by default, never default-applied, cannot be relabelled (R16) |
| Collect GST under the composition scheme | CHECK: tax only on a `tax_invoice`, and only a `regular` restaurant issues one (decision 3) |
| Read another restaurant's bills | Composite tenant FKs, scoped repositories, generic suite 1 over every route |

---

## Schema review checklist (G-13)

**1 · Metric and timestamp.** Bill-to-settle — *"the single most complained-about moment in Indian
dining"* (`docs/customer-experience.md`) — needs **`bill_requested_at`**. Seat-to-order needs
`placed_at` (order opened) and **`first_sent_at`**. Order-to-complete needs line-level `sent_at` now
and M08's served timestamps later. Section 14 needs **`served_at`**. None can be reconstructed
afterwards, so all are captured.

**2 · Where did the row come from?** `order.channel` (`pos` \| `qr` \| `aggregator`) and
`external_order_id` (S4). `payment.method` and `reference`.

**3 · Legal document?** **Yes, twice.** `invoice` and `credit_note` are legal documents: own tables,
own sequences, own immutability — never a status on `order` (S1, S8).

**4 · Does an option change consumption?** Yes — modifier recipes are consumed at settlement
(decision 10).

**5 · What does a human count at close?** Cash. `cash_count` beside a derived expected, variance
stored (decision 11).

**6 · Is a derived number O(N) forever?** Expected cash is summed over one session's payments — bounded
by the session, indexed on `(restaurant_id, cash_session_id)`. Order totals are stored on the order
because every list screen reads them.

**7 · ADR 0008 tier.** `order`, `payment`, `invoice`, `credit_note`, `cash_session` — transactional,
immutable after their terminal state; `cash_payout`, `cash_count`, `idempotency_key` — ledger /
append-only; all carry `restaurant_id`.

**8 · Insider.** The table above.

---

## Acceptance criteria

1. **Tax splits sum exactly**, property-based: for any price × quantity × rate × discount,
   `Σ(taxable + cgst + sgst) + charges ± round_off = payable`, with CGST = SGST on every line.
2. **The Jaipur golden case** reproduces: ₹1,580 at 18% → CGST ₹142.20, SGST ₹142.20, total ₹1,864.40.
3. **Invoice numbers are gapless and unique** under five parallel settlements — and the test fails
   with the advisory lock removed.
4. **A bill at 01:30 on 1 April** lands on business day 31 March and the new financial year's series.
5. **Section 14**: median-of-three equals two-of-three for every ordering of three instants around a
   rate change; a supply straddling a change takes the correct rate.
6. **A composition restaurant cannot produce a bill with tax on it** — refused by the service and by
   the database.
7. **Double-submitted settle with one key charges once** and replays the original response; the
   same key with a different body is `409`; a rolled-back first attempt lets a retry through.
8. **Concurrent settle of one order → one succeeds, one `409`.**
9. **A tampered client price is ignored.**
10. **Settle is atomic**: a forced failure after consumption leaves no invoice, payment, movement or
    audit row.
11. **Theoretical consumption uses direct components and modifier recipes**, never exploding a
    preparation.
12. **A discount apportions to the paisa** by largest remainder; a comp without an authoriser is
    refused.
13. **After settlement, a refund is a negative payment plus a credit note**; no path edits a settled
    order.
14. **Invoice cancellation** only on the business date of issue, keeps its number.
15. **Service charge is never on an order unless added explicitly**, and is removable.
16. **Expected cash is derived** and the variance survives a later refund in another session.
17. **A log line from an authenticated request carries `restaurant_id`** (the logging fix).
18. **Table status**: `free` refused while an order is open; status gone from the general PATCH.
    *Extended by backlog-issues B2 (2026-09-13), from the manual pass:* a settled table is being
    cleared until someone taps **Mark ready** (`order.create`) or the restaurant's cleaning time
    passes (default five minutes, derived when the floor is read from
    `restaurant_table.cleaning_since`); in a busy window, or with busy mode switched on from the floor
    (`floor.manage`, owner and manager, off again at the next business day), a settled table is free
    at once; tapping a table being cleared opens no order; an unsettled order is cancelled from the
    order screen behind a confirmation that asks why.
    **G-13 for `cleaning_since`:** (1) the metric it serves is table turn time, and it is the moment
    that metric needs; (2) it comes from settlement or a person setting `cleaning`; (3) not a legal
    document; (4) no consumption; (5) nothing is counted; (6) not a ledger; (7) master-data tier, on a
    row that already carries `restaurant_id`; (8) an insider could mark a dirty table ready — which
    is what the button is for, and the floor, not the audit log, is where that shows.
19. **Receiving is idempotent**: a double-tapped market purchase books stock once.
20. **Who is serving a table** *(added 2026-09-14, owner decisions D7–D10 in `docs/plan/backlog-issues-build-log.md`)*: every order, the table map and the bills list name the waiter; a waiter who opens a dine-in order serves it; whoever holds `order.assign` (owner, manager) names the waiter when opening or leaves it unassigned, and is never credited by default; takeaway and delivery are counter orders with no waiter; Assign to me claims only an unserved dine-in order; moving an order needs `order.assign` and a reason, is refused on a settled or cancelled order, and accepts only active staff holding `order.create` at this restaurant (a login is not required); every change is an `audit_log` row (`order.waiter_assigned`: from, to, by whom, why). **Auto-assignment is planned with M12**, which is what knows who is on the floor.
    **G-13:** no new table or column — `order.waiter_employee_id` and its index exist since this module shipped; (1) the metric is covers and sales per waiter per shift (M17), and the history is the audit row's `occurred_at`; (2) who set it is the audit row's actor; (3) not a legal document; (4) no consumption; (5) nothing is counted; (6) not a ledger; (7) transactional tier, on a row that carries `restaurant_id`; (8) an insider could move busy tables to themselves — which is why only `order.assign` moves one, always with a reason on the record.
21. Tenant isolation and the permission matrix over every new route; `make check` clean; 100%
    coverage on the money, stock and permission paths.

---

## Chunks — split into three PRs, as `docs/modules.md` requires

| PR | # | Chunk |
|---|---|---|
| 1 · orders & tax | A | Log-context fix (test first) · table status transitions |
| | B | Migration 0019 + models + schema doc · enums both sides |
| | C | Permissions 0020 + `cash.manage` design amendment |
| | D | Tax core: `financial_year_of`, line split, median rate date, apportionment — pure, property-tested |
| | E | Orders, lines, modifiers, charges, discounts, split — repositories, services, API |
| 2 · money | F | Idempotency mechanism + retrofit M06 receiving |
| | G | Settlement: invoice numbering, payments, consumption, cost freeze — atomic |
| | H | Credit notes, invoice cancellation, refunds |
| | I | Cash sessions, counts, payouts, adjustments |
| 3 · screens | J | Table map, order taking, bill, split, payment |
| | K | Void / credit note, cash-up screens, waiter patterns in design-system.md |
| | L | Seed, adversarial review, second reader, manual script, build log, compliance-rules.md |

---

## Risks, recorded before they are discovered

- **The estimate is wrong, and knowingly.** `docs/modules.md` says 7 days. The research added two legal
  document types, a scheme distinction, the Section 14 rule, idempotency as a mechanism rather than a
  call, a payout table and two owed fixes. Realistically this is **10–11 days**. The estimate is left
  untouched until actuals exist rather than replaced with a second guess.
- **R17 is genuinely unsettled** and the design avoids needing an answer only by defaulting service
  charge off. A restaurant that enables it takes on the question; the screen says so.
- **R16 may move.** If the division bench overturns the single judge, "never default-applied" becomes
  stricter than the law requires — which costs nothing.
- **Unverified against primary text:** R2's threshold wording, R11's exact statutory branch, R18.
  Each is used in a way that is safe whichever reading is correct, and each is recorded in
  `docs/compliance-rules.md` with this check date so a later reader knows how far to trust it.
- **Section 14 at a rate change is rare** — a few nights a decade — and exactly the kind of rule
  that is never tested and always wrong. It gets a property test for that reason.
- **Negative preparation stock at the first real settlement** will look alarming to a new restaurant.
  It is M05 decision 2 working as designed, and the M05 §B2 wording question is where that lands.
