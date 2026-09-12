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
- [ ] **F · Backend tests green** — incl. the 1,000-operation property test
- [ ] **G · Frontend: on-hand + alerts**
- [ ] **H · Frontend: receive, produce, count entry**
- [ ] **I · Seed + gate + adversarial review + manual script**

## Next action

> Chunk F. Write `tests/test_inventory_property.py`: the 1,000-operation property test
> (acceptance criterion 1) — random receipts, consumptions and adjustments against one item, with
> a **fixed seed** so a failure is reproducible, asserting `on_hand == SUM(quantity_delta)`
> throughout. Then `make check` whole and read the exit code, not the tail.

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
