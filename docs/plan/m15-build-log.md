# M15 · The 120-Day Generator — Build Log

Spec: `docs/modules/M15-generator-spec.md`. Manual script: `docs/manual-tests/M15-generator.md`.

---

## State

| Chunk | What | State |
|---|---|---|
| A | The demand model, the deterministic clock, the week structure | ⏳ |
| B | Fourteen planters and `tests/test_planted_signals.py` | ⏳ |
| C | The volume, `make seed-small`, and the reports asserted against generated data | ⏳ |
| — | Manual pass | **Owner's** |

Built on 2026-09-19, on `feat/m11-communication` after M14.

---

## The finding that decided the module's shape

**The services take no clock, and that is correct.**

M07's seeder states the rule this module had to answer to: *"Everything goes through the services,
never around them, so the seeded bill is priced, taxed, numbered and consumed exactly as a real one
would be — a seed that wrote rows directly would demo arithmetic the product never performed."*

The spec expected to decide this with a stopwatch: time a day through the services, multiply by 120,
compare against a five-minute budget. The measurement was never needed, because
`OrderService.create` and `SettlementService.settle` read `datetime.now(UTC)` for `placed_at`,
`settled_at`, `business_date` and the invoice date — and for a real bill that is exactly right. A
service that took a clock would be a service with a back-dating parameter in it, which is a worse
thing to have than a generator that writes rows.

**Driving them fourteen thousand times would have produced fourteen thousand bills all dated
today.** Not slow history — no history at all.

So the generator writes rows, computes what the services compute, and the tests assert the result
rather than the mechanism: gapless invoice sequences per financial year, an equal GST split on every
line, a business date that respects the 05:00 start, and M13's own reports reading what it wrote.

---

## The second structural decision: a week at a time

`stock_movement.stock_batch_id` is NOT NULL, and rightly — a consumption from no batch is a
consumption at no cost, and invariant 2's whole point is that cost travels with the stock. A
generator that wrote a day at a time would have to buy stock before it knew what the day would use.

So it works a week at a time: build the week's trading in memory, buy what it needs, then write the
bills and the movements that draw on those batches. A restaurant buys on Monday for the week; so
does this. It also bounds memory, which 120 days of orders held at once would not.

---

## What is planted, and the three that are shaped differently from the table

`docs/seed-data.md` now carries this too, because rule 4 — *an undocumented anomaly is
indistinguishable from a generator bug* — is equally true of a documented one planted differently
from how it reads.

All fourteen are planted and each has a test that fails when its planter is removed. Three differ:

- **Signal 3 (short delivery)** is a batch smaller than what was ordered, not a goods-receipt
  variance against a purchase order. The generator writes no purchase orders: four months of them
  to carry one signal would be a second procurement history nobody reads, and M06's three-way match
  is tested by its own fixtures. What the ledger shows is what a restaurant without paperwork
  actually sees — less stock than the money paid for.
- **Signal 11 (comp concentration)** sits on `stock_movement.actor_employee_id`, because a comp in
  this schema is a `complimentary` movement rather than a document.
- **Signal 6 (one waiter's errors)** is planted as service-stage waste on that person's dinner
  bills. **Not as a score.** `docs/workload-fairness.md` and ADR 0011 are emphatic that measuring
  people needs guardrails this module does not have, so the generator plants the fact and M17 is
  where anybody is measured by it. The finding it exists for is that the pattern is *systemic* —
  the same person is fine at lunch.

---

## Two things the tests forced

**`covers_scale`.** The signals that need a long window — the tomato spike at day 62, the complaint
week at day 96, the regulars who leave at week 14 — are about *shape*, and generating a hundred days
of full-volume trading three times inside a gate that already takes the best part of an hour would
be minutes spent proving what a tenth of the volume proves. `make seed` never passes it.

**A dinner service that crosses midnight.** The first draft's latest table was 23:40, so no
generated bill ever fell after midnight — and `test_a_late_bill_belongs_to_the_day_it_started`, the
test for the invariant this codebase is most careful about, would have passed vacuously for want of
a single late table. The dinner tail now reaches 01:30, which still belongs to the business day it
started in.

---

## Measurements

*(to be filled in when the run completes: `make seed` wall time, row counts, and the query plan for
the heaviest generated report)*

---

## Tests

| File | Count |
|---|---|
| `tests/test_planted_signals.py` | 19 |
