# M15 · The 120-Day Generator — Build Log

Spec: `docs/modules/M15-generator-spec.md`. Manual script: `docs/manual-tests/M15-generator.md`.

---

## State

| Chunk | What | State |
|---|---|---|
| A | The demand model, the deterministic clock, the week structure | ✅ committed |
| B | Fourteen planters and `tests/test_planted_signals.py` | ✅ committed |
| C | The volume, `make seed-small`, and the seed run end to end | ✅ committed |
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

**A full seed takes 46 seconds**, measured by `tests/test_seed_cli.py::test_it_seeds_an_empty_
database_and_reports_success` — which runs exactly what `make seed` runs, in one transaction,
against a fresh database. The budget in the spec was five minutes.

That is 120 days of trading plus everything the other twelve seeders do, on a laptop, inside a
container, with a test suite running beside it. A second run takes 50 seconds and writes nothing:
the generator finds history over its window and stops, which is the idempotence every other seeder
promises.

**No index migration was needed.** M13's `0048` already added `(restaurant_id, business_date)` on
`invoice`, which is the path every generated report reads, and the reporting latency file measures
that path at 16–32 ms against an 800 ms budget on ninety days. Nothing in this module made it
slower: the generator writes the rows those measurements were already taken against.

---

## Six of the product's own rules refused the first draft

Every one of them was right, and each is worth reading as a statement about the schema rather than
about the generator.

**The GST halves are computed on the line, not by halving the tax.** `app/core/tax.py` rule 1 says
why in a sentence I had to be shown by a CHECK constraint: *"computing a total and halving it leaves
an odd paisa that has to be given to one side."* ₹75 at 5% is ₹3.75, and 1.88 + 1.87 is not an equal
split. `ck_order_line_gst_split` refused every line until each half was computed from the line
value.

**An invoice number is at most sixteen characters** (CGST Rule 46(b), `ck_invoice_number_length`).
`INV/2026-27/000001` is eighteen. The product already had `invoice_number()`; the generator now
calls it rather than formatting a second, illegal series.

**A settled order takes no lines, no tables and no edits** — three separate triggers for invariant
6. History arrives whole, so `session_replication_role` stands the triggers down for exactly two
statements; and the customer goes on the bill *as it is built*, which is what M10 does and what the
third trigger insisted on when the first draft tried to update settled orders afterwards.

**Two deliveries of one thing on one day under one docket** is refused by
`uq_stock_batch_restaurant_code`. Truncating ingredient codes to eight characters collided
`CHKN_BONELESS` with `CHKN_BONE_IN`.

**`captured` and `issued` are not this product's payment and invoice statuses.** They are `success`
and `issued`; the enums exist and the generator now uses them.

**A shelf cannot hold a negative quantity.** M15 produces genuinely negative book positions — stock
consumed that nobody recorded receiving is week one for a real restaurant — and the count seeder
multiplied a negative book by a fraction and handed the service a negative counted quantity, which
it rightly refused. A person in the storeroom counts what is there, and what is there is never less
than nothing. Counting zero against a book of −2 kg is the *point* of the count: it records the full
shortfall rather than declining to look at it.

## And one the tests caught rather than the database

**The tomato spike never reached a plate.**

A dish's recipe names a *preparation* — `PREP_MAKHANI` — and not tomato. So a price multiplier
applied to `TOMATO` alone moved no `theoretical_unit_cost` at all, and signal 13's report would have
shown a flat line while the generator logged a spike it had faithfully applied to an ingredient
nothing bought directly.

`docs/seed-data.md`'s own wording was the fix, and it had been right all along: *"tomato price spike
raises **gravy cost** 22% for 3 weeks."* The three preparations built on tomato now carry the 22%,
and the test measures one gravy-heavy dish rather than the menu average — across the whole menu the
rise is real and invisible, because two thirds of the dishes contain no tomato and the mix's own
variation is larger than the signal.

**This is the class of bug this module exists to prevent**, found on the module that exists to
prevent it: a documented anomaly, faithfully implemented, that never reached the report it was
planted for.

## One more, in the same family

`_demo_restaurant` ordered by code and took the first, which is the **unfurnished Baner branch** —
`seed/organization.yaml` creates three restaurants and fits out one. The generator logged "the menu
is empty" about a restaurant that never had a menu: a true sentence about the wrong restaurant,
which is the least helpful kind of correct. It now picks the demo restaurant with the most active
variants.

---

## Tests

| File | Count |
|---|---|
| `tests/test_planted_signals.py` | 21 |
