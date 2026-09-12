# M06 · Procurement — Build Log

**Built 2026-09-13**, in one autonomous session, on the owner's instruction to carry straight on
from M05 without waiting for a spec approval or the manual pass
(*"if m05 is complete go with m06 as well… plan and execute… I trust ur recommendation"*).

Spec: `docs/modules/M06-procurement-spec.md`. Manual script: `docs/manual-tests/M06-procurement.md`.

---

## State

| Chunk | What | Commit |
|---|---|---|
| — | Spec, written in full despite there being no approval gate this time | `21fce94` |
| A | Migration 0017: 5 tables, append-only receipts, and the two foreign keys M05 left dangling | `bc633eb` |
| B | Migration 0018: `supplier.view`, `supplier.manage`, `purchase.manage` | `66c0b95` |
| C–G | Repositories, service, schemas, 15 endpoints, and the tests | `abf2d50` |
| H–I | Five screens, including the weighing screen | `541d1a5` |
| J | Seed, adversarial review, manual script, docs | this commit |

**Definition of Done: every line true except the manual pass, which is yours.**

---

## What the module is, in one paragraph

`docs/waste-model.md` §1 says receiving loss runs 1–3% of spend and nobody sees it, because *ordered
50 kg, delivered 47 kg, invoiced 50 kg* is invisible to a spreadsheet with one quantity column. M06
keeps four numbers where the spreadsheet keeps one — ordered, invoiced, received, rejected — and
every figure it reports is one of those or a difference between them. The output is a sentence:
*"Supplier A short-delivered 4.2% across 31 deliveries this quarter — ₹18,400."*

---

## The seven decisions, and which ones bit

Full argument in the spec. What is worth knowing afterwards:

**Decision 2 — a goods receipt is append-only, by trigger.** ADR 0008 assigns no tier to
`goods_receipt`, so the spec assigned one, and for the threat rather than the taxonomy: an editable
receipt is one `UPDATE` away from *weigh 47, take 3 home, edit the receipt to say 50*. Cost nothing
to implement, and it is the control the manual script's G2 is about.

**Decision 3 — PO numbers under a transaction-scoped advisory lock.** Verified in both directions:
five parallel creations take `PO-000001`…`PO-000005` with the lock, and die on
`uq_purchase_order_restaurant_num` without it. **This is a rehearsal for M07**, where GST law
requires a gapless invoice sequence per financial year — at a very different rate, because invoices
are issued per bill during service rather than twice a day. Re-verify the same way: delete the
`pg_advisory_xact_lock` call from `PurchaseOrderRepository.next_number` and watch the test go red.

**Decision 5 — landed cost includes tax the restaurant cannot reclaim.** `docs/compliance-rules.md`
§A6. This is the decision that most changes the product's numbers: before M06 a restaurant's food
cost rested on a researched national average, and one delivery moves it to their own supplier's
bill, tax included. The approximation (pro rata by line value on a mixed-rate invoice) is in the
backlog with the question to ask a pilot restaurant.

---

## What the tests found that review would not have

**The golden case caught a real cost bug.** Landed cost was computed as
`price × (1 + tax / line_total)` and left unquantized, so the confirmation panel reported
`0.10500000` while `stock_batch.unit_cost` — `NUMERIC(14,6)` — stored `0.105000`. Harmless at that
value; with a non-terminating apportionment (a third of a rupee of tax) the response would carry 28
significant digits and the batch a rounded 6, and the screen and the ledger would disagree about
what the stock cost **on the one field every food-cost figure in the product is built from**. Now
quantized where it is computed, half-even to match `services/costing.py` — two rounding modes in one
product is a discrepancy nobody would ever find.

**The endpoint tests caught a lazy-load that no unit test could.** `ReceiptResult` returned the
`GoodsReceipt` ORM object, whose `lines` relationship is `lazy="raise"`; serialising it raised, and
the route commits between creating it and reading it, which expires it anyway. The service now
returns an **id** and the route re-reads with the lines eagerly loaded. Same lesson as M05's missing
commits: the defects on this seam are only visible across a request boundary.

**The generic suites refused the build the moment the routes registered**, exactly as the M05 build
log predicted they would — three path parameters with no victim rows. `supplier_id`, `po_id` and
`receipt_id` are now registered and seeded. This remains the standing rule: **any new route with a
path parameter needs the parameter in `_VICTIM_PARAMETERS` and a victim row in `_victim_resources`**,
or the build fails rather than silently skipping the route.

---

## The adversarial review (step 7) — what it found in my own diff

Two real findings, both fixed before the gate:

1. **The same SELECT twice per delivery.** `_ordered_quantities` and `_ordered_prices` each called
   `orders.lines_of(order.id)`. Merged into one `_order_lines` returning both. An N+1 at n=2 is
   still the shape, and it is the kind that grows when a third caller wants a third field.
2. **A join with no tenant predicate that is nonetheless safe, and did not say so.**
   `_accepted()` and `supplier_variance` scope on `goods_receipt_line.restaurant_id` and join
   `goods_receipt` and `stock_item` without their own filters. That is safe because the composite
   foreign keys make a line and its parents structurally same-tenant — but it reads exactly like the
   #1 bug class, so it now carries the paragraph explaining why it is not.

Three findings recorded in `docs/backlog.md` rather than fixed: **no idempotency on receiving** (a
double-submit with no invoice number books twice — `Idempotency-Key` is M07's mechanism and
inventing a second one early would be the wrong kind of tidy), **two item reads per received line**
(a write path a human touches a few times a day), and **mixed-rate tax apportionment**.

The rest of the checklist came up clean: money is `Decimal` everywhere and quantized once, at the
boundary; every datetime is `datetime.now(UTC)` and every business date goes through
`InventoryService.business_date_now`; no client-supplied total is trusted (`invoice_amount` and
`tax_amount` are facts a supplier wrote down, not computations, and are documented as such); the
supplier audit rows carry `name` and `is_active` and deliberately **not** phone or GSTIN; no error
message names a table or a constraint.

---

## Verified — commands actually run, output actually seen

| Check | Result |
|---|---|
| `ruff check` + `ruff format --check` | clean |
| `mypy app tests` (strict) | clean |
| `eslint --max-warnings 0` + `tsc --noEmit` | clean |
| `pytest tests/test_procurement_schema.py` | **16 passed** — append-only, composite FKs, every CHECK |
| `pytest tests/test_procurement_endpoints.py` | **31 passed** — the golden case, landed cost, the lifecycle |
| `pytest tests/test_procurement_service.py` | **22 passed** — the status recomputation guard, the guards no request reaches |
| `pytest tests/test_procurement_concurrency.py` | **2 passed** — and **verified to fail with the advisory lock removed** |
| `pytest tests/test_seed_procurement.py` | **7 passed** |
| `pytest tests/test_generic_suites.py` | **21 passed** — all four suites over the fifteen new routes |
| `pytest tests/test_database.py` | **19 passed** — 0017 and 0018 apply up→down→up on real Postgres |
| coverage on the six M06 modules | **100%** each (models, schemas, repositories, service, API, seed) |
| `make check` | **clean, exit 0** — 730 backend tests, 213 frontend tests, **97.28%** total coverage, zero warnings |

---

## The gate was not failing on coverage, and now it is

**Found at the start of this session and fixed in it.** The baseline `make check` printed

```
FAIL Required test coverage of 95% not reached. Total coverage: 94.83%
```

in red, and then printed `make check: clean` and exited 0.

Both obvious explanations were ruled out by measurement rather than by reading: pytest **does**
exit 1 on a coverage-only failure here (run directly, exit code read without a pipe), and `make`
**does** propagate a non-zero exit through `cd backend && ...` on this Windows GNU Make (reproduced
with a probe Makefile that fails only on coverage; make stopped with `Error 1` and never reached the
next target).

The cause is in `pytest_cov/plugin.py`, and it is that **the verdict and the message use different
comparisons**:

| | code | at 94.83% vs a floor of 95 |
|---|---|---|
| the red message | `self.cov_total < self.options.cov_fail_under` | `FAIL ... not reached` |
| the **exit status** | `should_fail_under(total, fail_under, precision)` | passes |

`coverage.results.should_fail_under` is `round(total, precision) < fail_under`, and pytest-cov's
default precision is **0**. `round(94.83, 0)` is `95`, and `95 < 95` is false. So the floor has a
blind spot roughly half a percentage point wide — from about 94.5% to 95.0%, every run prints FAIL
in red and passes the gate. The baseline sat at 94.83%, squarely inside it.

**Fixed by `[tool.coverage.report] precision = 2`** in `backend/pyproject.toml`, which makes the two
comparisons agree and makes the `TOTAL` row print the number the verdict actually used.
`tests/test_toolchain_pins.py::test_the_coverage_floor_can_actually_fail_the_build` asserts the
setting **and demonstrates the arithmetic** — `should_fail_under(94.83, 95, precision)` must now be
true — so the line cannot be removed by somebody who reads it as "how many decimals to print".

This is worth remembering beyond the one line of config. CLAUDE.md already warns that `make check |
tail` reports `tail`'s exit code, and that warning was written after two false "clean" claims. This
is a *second*, independent way for the same gate to report clean while a floor is breached, and
this one survives reading the exit code correctly. **The general lesson is that a red line in the
output is evidence regardless of the exit status** — and if the two disagree, one of them is a bug
worth an hour.

## Notes for whoever picks this up

- **Run pytest from `backend/`, not the repo root.** Still true, still the same symptom: Alembic
  resolves `script_location` relative to the working directory, so from the root `test_database.py`
  fails with `Path doesn't exist: alembic`, which looks exactly like a broken migration.
- **The coverage floor is a global 95%, not per-module.** The six M06 modules are individually at
  100%, which is what the Definition of Done asks for on money, stock and permission paths — but the
  *project* total is what `make check` compares, and it moves when any module's tests do.
- **`purchase_order.status` is the only stored derived value in the module.** It is guarded by
  `test_procurement_service.py::TestTheStoredStatusAgreesWithARecomputation`, which recomputes it
  independently at every step of a split delivery. **If that test is ever deleted, the cache becomes
  a lie** — the spec's decision 7 exists to make that explicit rather than discovered.
- **`quantity_rejected` does not fill the order.** Accepted is `received − rejected`, and that is
  what both the ledger and the PO status use. A supplier who delivers 50 kg of which 6 are rotten
  has delivered 44 against the order, and it stays open for the rest. This trips people up: it is
  the difference between `short_delivery` (billed and not delivered) and `order_shortfall` (still
  owed), which are different numbers on the same row on purpose.
- **Admin holds none of the three procurement permissions**, following `seed/organization.yaml`'s P1
  design, which gives an administrator configuration and people rather than commerce. M05's
  migration was more generous to `admin` than the design was; this one is not, and the divergence is
  worth noticing rather than copying.

---

## What M07 inherits from this

- The **advisory-lock numbering pattern**, proven under concurrency, for gapless GST invoice numbers.
- `stock_batch.supplier_id` and `goods_receipt_line_id` are now real foreign keys, so a settlement
  that traces a consumed gram back to the delivery it arrived on has a path to walk.
- `stock_item.cost_source = 'purchase'` starts appearing the moment a restaurant books its first
  delivery, which is what makes M13's food-cost variance a number about *this* restaurant rather
  than about a national average.
- **Receiving is the second write in this product where a duplicate is money.** Settle is the first.
  When `idempotency_key` lands, put both behind it.
