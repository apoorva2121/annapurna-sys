# The transactional & analytics architecture proposal — harvested, not adopted

**Decision, 2026-09-12:** an enterprise transactional-data and analytics architecture proposal was
evaluated against this codebase. It is **not adopted as a module.** Six items are harvested into
the modules that already own that ground; three are rejected outright. This file records what was
taken, what was refused, and why — so the same proposal does not arrive twice and get a different
answer.

---

## Why it is not a module

**It is an e-commerce architecture, not a restaurant one.** It models split shipments, carrier
tracking, return merchandise authorisation, multi-warehouse allocation, backorders, serial and lot
tracking, On-Time Delivery Rate and warehouse picking efficiency. A restaurant ships nothing,
backorders nothing, and issues no RMA. Its proposed lifecycle —
`Pending → Paid → Processing → Shipped → Delivered → Returned` — is not ours, which is
`Draft → Placed → KOT fired → Preparing → Ready → Served → Settled`.

Its single best instinct, *"locking item prices at purchase time"*, **is already implemented**:
CLAUDE.md invariant 6 and the cost freeze at settlement.

**It duplicates six planned modules** — M05, M06, M07, M10, M13, M15 — and M07 is already the more
domain-correct design, because it encodes Indian law the proposal has no knowledge of: GST stored
per line as CGST/SGST at order time, and **invoice numbers sequential per financial year with no
gaps, so a cancellation keeps its number**. Adopting the proposal would create two sources of
truth for orders, which is the worst available outcome.

---

## Rejected, and these should stay rejected

### 1. `MockDataProvider` / `LiveDataProvider` behind a `DATA_SOURCE=MOCK|LIVE` toggle

**This project has already paid for this lesson once.** `docs/plan/m00-build-log.md` records
defects 9, 10 and 11 — a cold start that never ran its migration, make targets that ran on the
wrong host, and a UI returning 500 because the dev proxy pointed at `localhost`. Its own conclusion:

> all three lived in the composed system, and all three were invisible to a fully green suite,
> because every test runs against testcontainers rather than against the stack a person opens

A dual-provider swap is that anti-pattern one level up. An analytics layer built against synthetic
data never exercises the real query planner, the real tenant scoping (**the #1 bug class in this
product**), real N+1 behaviour, or the business-day boundary. "Switch to live without structural
rewrites" is precisely the promise that failed before and required `scripts/smoke.py` to be
invented.

**We already have the better answer.** `make seed` builds a demo restaurant on real Postgres with
real constraints and real tenant scope; M15 owns making it richer. Same plug-and-play demo, none of
the divergence. And a `MOCK` flag in a multi-tenant product is a live footgun: ship it wrong once
and a real restaurant makes purchasing decisions on invented numbers.

### 2. Snowflake / BigQuery as the analytics store
ADR 0005: nothing cloud-proprietary. M13 is explicitly **queries, not tables**.

### 3. Multi-currency with exchange rates, chargebacks, gateway transaction IDs
Currency is per-restaurant and INR today (CLAUDE.md invariant 3). Payment gateway integration is
named out of scope for month 1. Chargebacks are a card-network concept; Indian restaurant payments
are overwhelmingly UPI and cash, where disputes do not work that way.

**Also refused:** more `JSONB` "for dynamic metadata without migration". That fights finding S13,
which moved `fssai_licence` *out* of settings JSONB precisely because it prints on every bill.
JSONB is where fields go to avoid being designed.

---

## Harvested

| # | Item | Owner | State |
|---|---|---|---|
| 1 | **Cash reconciliation** — expected vs counted, per till session | **M07** | ✅ added to `docs/modules.md` |
| 2 | Metric → source table → SQL → UI matrix as the spec format | M13 | backlog |
| 3 | RFM segmentation, cohort retention, CLV, repeat purchase rate | M13 + M10 | backlog |
| 4 | Basket analysis — frequently ordered together | M13 | backlog |
| 5 | Executive / Operational Control Tower / Vendor dashboard taxonomy | M13 | backlog |
| 6 | Historical versioning of customer addresses | M10 | backlog |

Already present, and needing nothing: idempotency keys on payment (ADR 0010, M07), state-transition
audit (`audit_log`, M14), price snapshotting (invariant 6), check constraints and compound indexes
(ADR 0008).

### Why cash reconciliation was the one item promoted straight into a module

It is the only thing in the proposal that is **both absent here and squarely the product's own
thesis.** This product exists because a restaurant's theoretical position and its actual position
diverge, and nobody measures the gap. `stock_movements` does that for the stockroom. Nothing did it
for the till — and cash is where an Indian restaurant most commonly loses money.

It is the same arithmetic the product already performs, pointed at a second surface: expected
minus counted, with the variance recorded rather than overwritten. That is invariant 7 applied to
money.

**Placed in M07, not M12,** deliberately: expected cash is derived from `payment` rows on settled
orders, so it belongs with the module that owns payment. M07 depends on M03 and M05, not on M12 —
putting the cash-up in Shifts would make M07's money story wait for a roster.

---

## The standing lesson

The proposal was a good *document* and the wrong *fit*, and the difference was only visible against
what is already built. Before adopting any externally-shaped architecture here, check it against:
`docs/schema.md` (64 tables), the 11 ADRs, CLAUDE.md's 7 invariants, and
`docs/compliance-rules.md`. A proposal that is silent on tenant isolation, the business-day
boundary, append-only stock, or Indian GST invoice numbering has not been written for this product,
however well written it is.
