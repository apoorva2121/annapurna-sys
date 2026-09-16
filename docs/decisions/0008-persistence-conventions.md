# 0008 — Keys, deletion, enums and numeric types

**Status:** Accepted · 2026-09-08

## Context
Four conventions that are cheap to set now and expensive to change once fifty tables exist.

## Decision

### Primary keys — UUIDv7, not UUIDv4
Every table gets a UUID surrogate primary key. Natural keys (phone number, table number, employee
code, dish name) are never primary keys; several of them legitimately change.

The version matters. **UUIDv4 is random**, so inserts scatter across the B-tree — on append-heavy
tables (`stock_movement`, `order_line`, `message`, `audit_log`, which will be the four largest here)
that causes page splits, poor cache locality and index bloat that grows with table size. **UUIDv7 is
time-ordered** in its high bits, so inserts append to the right-hand edge like a sequence, while
keeping the properties we actually want from a UUID: generated client- or service-side without a
round trip, safe to expose in URLs, and no leaked row counts.

Business-readable identifiers (`order_number`, `employee_code`, `po_number`) are **separate columns**
with a unique constraint per restaurant. They are for humans; the UUID is for foreign keys.

### Deletion — three tiers, and no `deleted_at` where it does not belong
Blanket soft-delete is a trap: every query then needs `WHERE deleted_at IS NULL`, and the one place
it is forgotten becomes a data-correctness bug that is invisible in review. Tables are therefore
assigned one of three explicit tiers, and a table only gets the columns for its tier:

| Tier | Applies to | Mechanism |
|---|---|---|
| **Master data** | employee, menu_item, ingredient, supplier, table, role | `is_active` + `deactivated_at` + `deactivated_by`. Never hard deleted — historical rows point at them forever. |
| **Transactional** | order, payment, task, purchase_order, complaint | **No delete column at all.** State lives in `status`. An order is not deleted, it is `cancelled` or `voided`, with a reason and an actor. |
| **Ledger** | stock_movement, audit_log, task_event, kot_ticket timestamps | **Append-only.** No update, no delete, no status. Corrections are new compensating rows. |

Deliberately: an order can never be soft-deleted, and no code ever needs to remember to filter it
out. `message` is the one edge case — it gets `deleted_at` for user-initiated deletion, rendered as
"message deleted" rather than removed, so the conversation stays coherent.

### Enums — text plus CHECK, mirrored from Python
Status and type columns are `TEXT` with a `CHECK (col IN (...))` constraint, not Postgres native
`ENUM`. Native enums require `ALTER TYPE` to add a value (which cannot run inside some transactions)
and effectively cannot drop one. A CHECK constraint is a normal, reversible migration.

`app/core/enums.py` is the single source of truth; `frontend/src/shared/enums.ts` mirrors it and a test
asserts the two match. Lookup tables are used only where rows carry extra data (`role`,
`permission`, `tax_group`, `wastage_reason`), never for a fixed list of strings.

### Numeric types
- **Money** — `NUMERIC(12,2)`. Never float. Serialised as a JSON string, never a JS number.
- **Quantity** — `NUMERIC(14,4)` in the item's base unit. Four decimals because saffron is dosed at
  0.05 g and yield factors compound.
- **Percentage / rate** — `NUMERIC(6,4)` stored as a fraction (0.0500 = 5%), never as `5.00`.
- **Unit cost** — `NUMERIC(14,6)`. Cost per gram is routinely a fraction of a paisa, and rounding at
  the ingredient level would corrupt every dish cost built on it.

## Consequences
- `uuid7()` is generated in the application, not the database, so a service knows an entity's id
  before it is persisted — which the audit decorator and event dispatch both rely on.
- The tier table above is the authority. Adding `deleted_at` to a transactional table is a review
  rejection, not a preference.
- Every timestamp column is `timestamptz` per ADR 0004. Every table has `created_at` and
  `updated_at`; `created_by`/`updated_by` appear only where a human actor is meaningful (not on
  ledger rows, which already carry `actor_employee_id`).
