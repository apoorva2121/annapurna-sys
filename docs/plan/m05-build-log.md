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
- [ ] **C · Services: receive, adjust, consume** — the write path, FEFO + negative-tolerant
- [ ] **D · Services: production, stock counts** — the two transactional ones
- [ ] **E · API + permissions + tenant-isolation suite**
- [ ] **F · Backend tests green** — incl. the 1,000-operation property test
- [ ] **G · Frontend: on-hand + alerts**
- [ ] **H · Frontend: receive, produce, count entry**
- [ ] **I · Seed + gate + adversarial review + manual script**

## Next action

> Chunk C. Create `app/services/inventory.py`: `receive_stock`, `adjust`, and `consume`. `consume`
> walks `batches_for_consumption` FEFO, and when the batches run out it charges the remainder to
> `newest_batch_for_update` and lets on-hand go negative (spec decision 2) — it never refuses.
> When the item has no batch at all, create a zero-quantity `opening` batch first.

## Verified — commands actually run, output actually seen

| Check | Result |
|---|---|
| `ruff check` + `ruff format --check` | clean |
| `mypy app tests` (strict) | clean, 105 source files |
| `pytest tests/test_inventory_schema.py` | **8 passed** |
| `pytest tests/test_enum_mirror.py` | passed — Python/TS enums in step |
| `pytest tests/test_database.py` | **19 passed** — migration applies to a real Postgres |
| `pytest tests/test_inventory_repositories.py` | **15 passed** — FEFO order, NULLS LAST, on-hand, tenant isolation |

## Notes for whoever picks this up

- **Run pytest from `backend/`, not the repo root.** Alembic resolves `script_location` relative to
  the working directory, so from the root `test_database.py` fails with
  `Path doesn't exist: alembic` — which looks exactly like a broken migration and is not one.
- `supplier_id` and `goods_receipt_line_id` on `stock_batch` are **columns without foreign keys**.
  Both target M06 tables that do not exist. `docs/schema.md` asks for the constraints in a
  follow-up migration; M06 adds them. Nothing in M05 writes either column.
- The append-only trigger does **not** break the suite: `conftest.py` cleans up by rolling back an
  outer transaction rather than issuing DELETEs, and row triggers do not fire on TRUNCATE.
