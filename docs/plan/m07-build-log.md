# M07 · Orders / POS — Build Log

**Started 2026-09-13**, continuing the autonomous run from M06 on the owner's instruction
(*"you start with M07 as well once you are done with M06… refresh ur memory and then start M07"*).

Spec: `docs/modules/M07-orders-spec.md` (`a40ea95`). **Resume from the State table below.**

---

## State

| PR | Chunk | What | State | Commit |
|---|---|---|---|---|
| — | — | Research + spec | ☑ done | `a40ea95` |
| 1 | A | Log-context fix · UUID redaction fix | ☑ done | `6dfec22` |
| 1 | B | Migration 0019 + models + schema doc + enums | ☑ done | this commit |
| 1 | C | Permissions 0020 + `cash.manage` design amendment | ☐ | — |
| 1 | D | Tax core: FY, line split, median rate date, apportionment | ☐ | — |
| 1 | E | Orders, lines, modifiers, charges, discounts, split | ☐ | — |
| 2 | F | Idempotency mechanism + retrofit M06 receiving | ☐ | — |
| 2 | G | Settlement: invoice numbering, payments, consumption, cost freeze | ☐ | — |
| 2 | H | Credit notes, invoice cancellation, refunds | ☐ | — |
| 2 | I | Cash sessions, counts, payouts, adjustments | ☐ | — |
| 3 | J | Table map, order taking, bill, split, payment | ☐ | — |
| 3 | K | Void / credit note, cash-up screens, waiter patterns | ☐ | — |
| 3 | L | Seed, review, second reader, manual script, compliance-rules.md | ☐ | — |

**Resequenced from the spec:** chunk A was planned as "log-context fix · table status transitions".
The table-status guard refuses `free` while an order is open, which needs the `order` table — so it
moved after chunk B and ships with chunk E.

**Full `make check` runs at the end of each PR**, not after every chunk: running it while the next
chunk's files are being written lets pytest collect half-written modules and blame the wrong commit.
Every chunk still has its targeted tests, the generic suites, lint, types and both audits before it
is committed.

---

## Chunk A — two defects nothing could see (`6dfec22`)

**The tenant was never on a log line.** `docs/observability.md` said every line carried
`restaurant_id` and `actor_id` automatically. `app/core/logging.py` declared both context variables
and the formatter read them — but nothing ever *set* them. Fixed in `current_actor`, plus a middleware
step: the access line is written after the handler returns, in a context the handler's variables
don't reach, so the tenant is carried back via `request.state`.

**The phone redactor ate UUIDs.** Its boundaries excluded digits but not hex letters, so a UUID whose
last group held a bounded ten-digit run starting 6–9 logged as `…-[redacted]ab` — about one id in two
hundred, including locked-account ids in the security log. Fixed by carving whole UUIDs out of the
scan; the wider fix (loosening the phone boundaries) was rejected because it would stop redacting a
phone number glued to a word.

Red run before the fix: **5 failed, 1 passed** — the passing one was the leak test, trivially true
while nothing was set. Green after: 69 targeted, 21 generic suites.

**Also found, deliberately not fixed here:** no handler anywhere logs a business event at INFO — only
three auth warnings exist. The Definition of Done's *"business events logged at INFO with request_id
and restaurant_id"* was unmet by every module before M07, not merely unenforceable. M07 logs its own
events. The retrofit for M03–M06 belongs in `docs/backlog.md` at the end of this module, with the list
of events each should emit.

---

## Findings that shaped chunk B, before any of it was written

**Three parents lack the constraint a composite foreign key needs.** `recipe`, `stock_item` and
`tax_group` carry `UNIQUE (id, restaurant_id)`; `menu_item_variant`, `modifier` and `restaurant_table`
do not. Migration 0019 adds those three first. Safe on any existing data by construction — `id` is
already unique, so the pair is too.

**`order` is a reserved word.** SQLAlchemy quotes it in generated DDL and queries; every raw
`op.execute` in the migration — the immutability triggers — must write `"order"` by hand.

**Settled orders are immutable, open orders are not.** So the `order` trigger cannot be the blanket
append-only trigger `stock_movement` and `goods_receipt` use. It refuses UPDATE and DELETE only when
the *existing* row is in a terminal state.

**`customer` does not exist until M10**, so `order.customer_id` is a column without a foreign key — the
same arrangement M05 used for `stock_batch.supplier_id` until M06 created `supplier`.

---

## Chunk B — fourteen tables, and what the database now refuses

Migration `0019_m07_orders`, `app/models/orders.py`, fifteen enums mirrored to TypeScript, and
`tests/test_orders_schema.py` (56 tests, every one against real Postgres). `docs/schema.md` §7 is
rewritten to the built design with a *"What migration 0019 added"* section; header 64 → 72 tables.

**Refinements to the committed spec, decided while writing the schema:**

- **`cash_payout` became `cash_movement` (`payout` | `adjustment`).** Same shape; two tables would be
  two places to sum — the reason `refund` was eliminated.
- **`payment.status` is `success | failed`.** `pending` and `refunded` both describe a row changing
  later, which an append-only row cannot do.
- **`order_line.status` gained `sent`**, and already allows M08's `preparing` and `ready`.
- **`order_number` is unique per business day**, not per restaurant forever.
- **The invoice snapshots supplier name, address, GSTIN and FSSAI number.** A reprint is the
  document as issued.
- **CHECKs, not conventions:** a negative payment must reference a credit note; a tax invoice must
  carry a supplier GSTIN; a bill of supply carries no CGST/SGST; invoice and credit-note numbers ≤ 16
  characters; a GST line's halves are equal; a service charge is optional; a till cannot close
  without its count.

**Three holes found in my own first trigger design, before any test ran:**

1. **A line could be added to a settled order** — the triggers fired on UPDATE and DELETE only.
   Adding a line to a paid bill is the edit that matters most. Children now trigger on INSERT.
2. **Counter service pays before it cooks.** A trigger freezing every column would stop the kitchen
   marking a paid order's dishes ready. A settled order may change only `served_at`,
   `first_sent_at` and the void fields; a settled line only its kitchen status and `sent_at`.
   The comparison is `to_jsonb(NEW) - allowed` against `to_jsonb(OLD) - allowed`, so **a money
   column a later migration adds is frozen by default**, not by remembering to list it.
3. **Deleting a sent line** is how a served dish leaves a bill. A line may be deleted only while
   `pending`; afterwards it is cancelled with a reason.

**Constraints chunk G must respect:**

- **Flip the order to `settled` last.** Re-freezing line tax, writing `recipe_id` and
  `theoretical_unit_cost`, and adding charges must all happen while the order is still live — the
  triggers refuse them one statement later.
- **`Order.version` is SQLAlchemy's `version_id_col`.** Every ORM UPDATE is
  `… WHERE version = :loaded` and bumps it; a stale write raises `StaleDataError`, which the service
  must map to 409. A Core `update()` does not bump it.
- **The invoice number's uniqueness is the database's; its gaplessness is the service's** —
  the per-restaurant, per-FY advisory lock in chunk G.

**Deviations from habit, recorded so a reviewer does not "fix" them:** three trigger bodies carry
`# noqa: S608` — they interpolate only module constants, never input. `__mapper_args__` carries
`# noqa: RUF012`, because `DeclarativeBase` already types it and mypy rejects `ClassVar`.

Green before commit: 56 schema tests; 146 across migration round-trip, generic suites, enum mirror
and the M01/M06 schema suites; ruff, format, mypy over `app` and `tests`; `tsc`, eslint on the enum
mirror; both audits.

---

## Notes for whoever picks this up

- **Use `backend/.venv/Scripts/python -m pytest`, never bare `python`.** Bare `python` on this
  machine is Anaconda, whose `argon2` is too old for `app.core.security`; conftest fails to import
  and nothing runs.
- **Very long inline shell commands fail here** (`ENAMETOOLONG`, or bash losing a heredoc). Write a
  script to the scratchpad and run it.

- **Run pytest from `backend/`, not the repo root** — Alembic resolves `script_location` relatively.
- **Two bill images sit untracked at the repository root** (`restaurant_bill.png`,
  `restuarant_bill_latest.png`), supplied by the owner as research. They carry a real restaurant's
  phone number and tax registration. **Never stage them** — commit by explicit path. G-16's check only
  covers tracked files, so it will not stop a careless `git add -A`.
