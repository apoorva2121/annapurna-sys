# M05 — Inventory Ledger — Build Log

**Read this first if you are resuming with no memory of the conversation.** It states what is done,
what is next, and the exact next action. Updated and committed with each chunk.

Spec: `docs/modules/M05-inventory-spec.md` (**approved by the user, 2026-09-12**).
Schema: `docs/schema.md` §5. Branch: `feat/m01-identity`.

---

## Status

**Phase:** P3 · Implementation · module M05 Inventory Ledger
**Started:** 2026-09-12, ~21:30 IST

## Decisions locked (approved — do not re-litigate)

| Decision | Choice | Where it came from |
|---|---|---|
| What invariant 7 forbids | On-hand sums **both** bases. The forbidden query is a single *consumption* figure across them — their difference is the product | Spec decision 1, approved |
| Negative on-hand | **Allowed, and alerted.** A consumption is never refused for insufficient stock | Spec decision 2, user chose "allow and alert" |
| Append-only | Enforced by a **Postgres trigger**, not repository discipline | Spec decision 3 |
| Tenant safety | **Composite FKs** on `(id, restaurant_id)`, using the unique constraint 0011 left behind | Chunk A |

## Chunks — tick only when committed

- [x] **A · Migration + models + enums + schema guarantees** — 0015, 4 tables, append-only trigger,
      composite tenant FKs, 4 new enums mirrored to TS. 8 schema tests green.
- [x] **B · Repositories** — FEFO with `NULLS LAST` + row locks, on-hand aggregate, per-basis
      consumption. 15 tests green.
- [x] **C · Services: receive, adjust, consume** — FEFO write path, never-refusing consumption,
      mandatory adjustment reasons. 18 service + 2 concurrency tests green.
- [x] **D · Services: production, stock counts** — atomic production with real input costing,
      forward-only counts, no self-approval. 18 tests green.
- [x] **E · API + permissions + tenant-isolation suite** — 13 routes, 5 permissions from the P1
      design, generic suites green. Two real bugs found here: a tenant leak and missing commits.
- [x] **F · Backend tests green** — incl. the 1,000-operation property test, which was rebalanced
      after it was found to pass with the shortfall path disabled
- [x] **G · Frontend: on-hand + alerts** — `StockOnHandScreen`, API client, route, nav link,
      7 screen tests. The owner link test was made honest: it claimed "every screen this app has"
      and did not include the new one.
- [x] **H · Frontend: receive, produce, count entry** — three screens, routed behind their own
      permissions, 11 screen tests. The owner link test needed updating a second time.
- [x] **I · Seed + review + manual script + coverage** — seed, manual script, adversarial review
      (3 findings, each with a regression test), and every M05 module at **100% coverage**.

## Next action

> **M05's build is complete.** What remains is not code:
>
> 1. **Your manual pass** — `docs/manual-tests/M05-inventory.md`. Sections C and D can now be done
>    through the screens rather than the API; that doc still says otherwise and should be corrected
>    once you have run it.
> 2. **Re-run `make check` whole** after any further change, and **read the exit code, not the
>    tail**. It caught two things in this module that the targeted runs did not: an S311 lint
>    failure, and backend coverage falling to 93.37% while 623 tests passed.
> 3. Then M05's `U` and `D` columns tick in `docs/checklist.md`.

## Verified — commands actually run, output actually seen

| Check | Result |
|---|---|
| `ruff check` + `ruff format --check` | clean |
| `mypy app tests` (strict) | clean, 105 source files |
| `pytest tests/test_inventory_schema.py` | **8 passed** |
| `pytest tests/test_enum_mirror.py` | passed — Python/TS enums in step |
| `pytest tests/test_database.py` | **19 passed** — migration applies to a real Postgres |
| `pytest tests/test_inventory_repositories.py` | **15 passed** — FEFO order, NULLS LAST, on-hand, tenant isolation |
| `pytest tests/test_inventory_service.py` | **18 passed** — receive/consume/adjust, shortfalls, business date |
| `pytest tests/test_inventory_concurrency.py` | **2 passed** — and **verified to fail with the lock removed** |
| `pytest tests/test_inventory_production.py` | **18 passed** — production costing, atomicity, count workflow |
| all five M05 files together | **61 passed** |
| `pytest tests/test_inventory_endpoints.py` | **12 passed** |
| `pytest tests/test_generic_suites.py` | **21 passed** — tenant isolation + permissions on the new routes |
| `scripts/audit_docs.py` | 0 issues |

## The adversarial review found three more (chunk I)

Each was invisible to a green suite, and for a different reason — which is the argument for the
review step rather than for simply writing more of the same tests.

1. **Every production shared one reference.** Consumption movements were referenced to `recipe.id`
   rather than to the batch being produced, so *"show me the movements this production wrote"*
   returned every production of that recipe since the beginning. Nothing failed: the totals were
   right, the reference pointed at a real row, and it was wrong only in what it could answer —
   which happens to be M13's stated requirement that a metric drills through to its own rows. Fixed
   by creating the output batch **before** consuming the inputs, so the batch's id is the
   reference. Regression test verified in both directions.
2. **`open_count` did not deduplicate**, so a client listing the same item twice hit
   `uq_stock_count_line_count_item` and got a 500 for an obvious, harmless typo.
3. **`consume` fetched batches with `session.get`**, which reads by primary key with **no tenant
   filter**. Safe as written — the id came from a scoped query a line earlier — but an unscoped
   read in the hot path of the most-written table is how the #1 bug class returns via whoever edits
   the loop next. Now goes through the scoped repository.

## What the coverage gate caught that the tests did not

`make check` failed at **93.37%** with 623 tests passing. Three separate things were hiding behind
that number, and the third is the one worth remembering:

- `app/seed/inventory.py` at 0% — its tests existed but that run predated them.
- Several endpoint bodies and error branches never executed at all.
- **A test that could decide not to run.** `test_producing_a_preparation_over_http` fetched the
  station list and `return`ed early when it was empty — which it always was in that fixture. The
  test passed, every time, having done nothing. It now creates the station directly.

All six M05 modules are now at **100%**.

## Two real bugs the tests found in chunk E — worth knowing before writing another module

1. **A tenant leak.** `GET /stock/items/{id}/movements` answered **200 with an empty list** for
   another tenant's item id. `test_generic_suites.py` suite 1 refused it, exactly as designed. The
   fix resolves the item in tenant scope first and 404s. **Any new route with a path parameter
   needs the parameter registered in `_VICTIM_PARAMETERS` and a victim row seeded**, or the suite
   fails the build rather than silently skipping the route.
2. **Missing commits.** This codebase's convention is that **the route commits and the service only
   flushes**. The first draft of the inventory routes omitted every commit, and the symptom was not
   a crash: each write returned `201` with a populated body and then vanished when the session
   closed. No unit test could have caught it — inside one transaction the write is visible to the
   code that made it. Only the endpoint tests, which cross request boundaries, could.

## Notes for whoever picks this up

- **Run pytest from `backend/`, not the repo root.** Alembic resolves `script_location` relative to
  the working directory, so from the root `test_database.py` fails with
  `Path doesn't exist: alembic` — which looks exactly like a broken migration and is not one.
- `supplier_id` and `goods_receipt_line_id` on `stock_batch` are **columns without foreign keys**.
  Both target M06 tables that do not exist. `docs/schema.md` asks for the constraints in a
  follow-up migration; M06 adds them. Nothing in M05 writes either column.
- **The concurrency test was worthless in its first form and is not now.** A plain
  `asyncio.gather` of two consumptions passed identically with `with_for_update()` removed, because
  the coroutines never interleaved at the moment that matters. It now forces contention by holding
  the first transaction open, and it has been re-verified in both directions: **fails without the
  lock, passes with it.** Any change to the FEFO read should repeat that check — remove the lock,
  confirm the test goes red, put it back.
- The append-only trigger does **not** break the suite: `conftest.py` cleans up by rolling back an
  outer transaction rather than issuing DELETEs, and row triggers do not fire on TRUNCATE.
