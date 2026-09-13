# 0010 — Idempotency, optimistic locking, and stock row locking

**Status:** Accepted · 2026-09-08

## Context
A POS runs on bad wifi, on cheap tablets, operated by people in a hurry. Three concurrency failures
are not edge cases here — they are Tuesday:

1. **The double tap.** A waiter taps "Settle" and nothing visibly happens because the network stalled.
   They tap again. Without protection that is two `payment` rows and a customer charged twice.
2. **The lost update.** A captain adds a dessert to table 6 while a waiter, holding a stale copy of
   that order, removes an item. Last write wins and the dessert vanishes — or is served free.
3. **The oversell.** Two orders for the last 200g of paneer settle in the same instant. Both read
   the batch as available, both consume it, and the ledger goes negative.

Each corrupts exactly the data this product sells.

## Decision

### Idempotency for money and stock effects
Every `POST` that creates a financial or inventory effect requires an `Idempotency-Key` header:
order settle, payment, refund, void, stock receipt, production batch, wastage, adjustment.

A new `idempotency_key` table stores key → (endpoint, request hash, response, status). Replaying a
key returns the **stored original response**, not a new effect. A key replayed with a *different*
request body is a `409 Conflict` — that means a client bug, not a retry. Keys are scoped per
restaurant and expire after 24 hours.

The client generates the key when the user taps, not when the request is sent, so a retry after a
timeout carries the same key.

### Optimistic locking for collaborative edits
`order` gets a `version integer NOT NULL DEFAULT 1`. Every mutation sends the version it read;
the `UPDATE ... WHERE id = ? AND version = ?` bumps it. Zero rows affected means someone else moved
first — the API returns `409` with the current state, and the UI merges rather than overwrites.

Applied to `order` only for now. Rows edited by one person at a time do not need it, and adding it
everywhere costs more in complexity than it returns.

### Pessimistic row locking for stock consumption
FEFO consumption selects candidate batches with `SELECT ... FOR UPDATE` ordered by `expiry_date`,
inside the settlement transaction. This serialises concurrent consumers of the same batch, which is
correct and cheap — contention is per ingredient, and two orders needing the identical batch in the
same millisecond is rare.

A `CHECK` at the ledger level cannot express "sum of movements ≥ 0", so the service asserts
available quantity inside the lock, and a nightly reconciliation job flags any batch that has gone
negative as a data-integrity alert.

### Transaction boundaries
One business operation is one database transaction. Settling an order writes the order, its
payments, its stock movements and its audit entries atomically, or writes none of them. Services
own transactions; repositories never commit.

## Alternatives rejected
- **Deduplicate by natural key** (order + amount + timestamp) — guesses at intent, and legitimately
  identical requests exist (two ₹100 cash payments on one bill).
- **Pessimistic locking on orders** — a waiter who locks table 6 and walks away blocks the captain.
  Wrong model for humans.
- **Serializable isolation everywhere** — high retry rates under KDS load, and it hides the design
  question rather than answering it.

## Consequences
- One extra table (`idempotency_key`) and one extra column (`order.version`).
- The API client wrapper attaches the header automatically for the listed endpoints, so this cannot
  be forgotten per call site.
  *Refined by M07 spec decision 8 (2026-09-13):* the wrapper **refuses** a listed endpoint sent
  without a key rather than inventing one, because the key must be made when the person taps. A key
  made inside the request would differ on every retry — which is the double effect this ADR exists
  to prevent. The key is made once per submission and renewed on success.
- Tests must include a concurrent-settlement case and a double-submit case. Both are in the module
  Definition of Done for Orders and Inventory.
