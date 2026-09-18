# M15 · The 120-Day Generator — Module Spec

**Depends on** M03–M13. It writes through the schema every one of them built, and it exists so
that M13's reports have something to find.
**Status** — spec written 2026-09-19, before any code, per `docs/sdlc.md` step 1.
Build log: `docs/plan/m15-build-log.md`.

Tables: none new. Endpoints: none. Screens: none.
Deliverable: `backend/app/seed/generate.py`, and **fourteen tests that fail if a signal is missing**.

---

## Why this module is not "more seed data"

`docs/seed-data.md` says the thing this module rests on, and it is worth quoting exactly:

> **Random data has nothing to find, so every analytics feature would look broken. Each anomaly
> below is deliberately planted, and each one is the acceptance test for a feature.**

M13 shipped four reports and a dashboard against fixtures built to break their arithmetic. What no
fixture could test is whether the reports *find things* — whether a menu-engineering quadrant
actually puts Chilli Paneer where it belongs, whether the variance report surfaces a 12% portion
drift, whether a complaint cluster is visible as a cluster. M13's spec deferred that test by name
and pointed it here:

> **"The 14-signal test does not run here. Owner's decision 1; it is written and pointed at M15."**

So the deliverable is not volume. It is **fourteen documented signals, each with a test that fails
when the generator stops planting it** — which is also what stops a future change to the generator
from quietly flattening the data every demo is given on.

**And the second reason, from `docs/onboarding-cold-start.md`:** there is no real data. Indian
restaurants keep few records, the pilot has no live site, and every screen in this product will be
shown to a restaurateur running on this dataset first. A demo where the numbers do not move like a
restaurant's numbers is a demo that ends the conversation.

---

## Research — what binds this module

**`docs/seed-data.md` is the specification**, not a suggestion: the demand shape, the volumes, the
cost movements and the fourteen signals are all stated there with numbers. This module implements
that file. Where reality forces a departure, the departure goes in the build log **and** back into
that file, because rule 4 of it is *"an undocumented anomaly is indistinguishable from a generator
bug"*.

**Rule 2: never in production.** Every seeded organization carries `is_demo = true`, and M13's
reporting repository excludes them in one place (`_real_restaurants()`). This module writes a great
deal of plausible data; the thing that keeps it out of a real report is that one filter, and a test
here asserts it end to end rather than trusting it.

**Rule 1: deterministic.** Same seed, same data. A regression in an analytics query then shows up
as a *changed figure*, which is a diff somebody can read.

**Invariant 4 decides every date.** A restaurant's day starts at 05:00, so an order placed at 01:30
belongs to the previous business day. A generator that wrote `business_date = created_at::date`
would put every late order on the wrong day and every report would be quietly wrong about the
restaurants this product is for.

**Invariant 7 is the point of the data.** Theoretical consumption comes from recipes at settlement;
actual consumption is what the generator plants as waste, drift, comps and staff meals. The ~6-point
gap between 25.7% and ~32% is, in `docs/seed-data.md`'s own words, *"the entire product"*.

**`docs/compliance-rules.md`:** every generated invoice is a real tax invoice — gapless sequence per
financial year, supplier GSTIN, the GST split that `ck_order_line_gst_split` enforces. A generator
that produced documents the product could not legally issue would be demonstrating a different
product.

---

## The decisions that matter

### 1 · Through the services or around them, decided by a measurement

M07's seeder states the rule this module has to answer to: *"Everything goes through the services,
never around them, so the seeded bill is priced, taxed, numbered and consumed exactly as a real one
would be — a seed that wrote rows directly would demo arithmetic the product never performed."*

That is right, and at ~14,000 orders it may be unaffordable: settlement explodes recipes, walks
batches FEFO and numbers an invoice under a lock. **The decision is a measurement, taken first**:
time one day of generated trading through the services, multiply by 120, and compare against a
budget of **five minutes for `make seed`**.

- **Under budget** → through the services, unchanged, and the rule stands.
- **Over budget** → a hybrid: the services for one day in each week (so the full path is exercised
  against real generated data) and bulk writes for the rest, with **a test that generates the same
  day both ways and asserts the totals are identical**. That test is the price of the shortcut and
  the reason it is safe.

The measurement and the choice go in the build log. Guessing here — in either direction — is how a
seed becomes either unusably slow or quietly wrong.

### 2 · Determinism means *seed plus end date*, and the end date is explicit

"120 days ending today" cannot be deterministic across two days. So the generator takes an
`end_date` and defaults it to the restaurant's current business date; **determinism is the promise
that the same seed and the same end date produce identical data**, and the signal tests pin the end
date so they assert figures rather than approximations.

`make seed` uses today, because a demo wants yesterday to be yesterday.

### 3 · Every signal is a named planter, and every planter has a test

Fourteen functions, each named for its signal, each with a docstring saying which feature it exists
to prove and a test that fails when it stops. Not fourteen `if` branches inside one loop: a signal
that is a branch is a signal somebody deletes while tidying.

The test file is `backend/tests/test_planted_signals.py`, and it is the module's exit criterion.

### 4 · Plausible, not perfect — and the imperfections are planted too

`docs/seed-data.md` rule 3: *"Include missing feedback, a forgotten stock count, two voided orders,
a day the waste log was skipped. Perfectly clean data hides bugs that real data will find."*

This is not decoration. A report that only ever sees complete data is a report nobody has tested
against a real restaurant, where the waste log is skipped on the night it mattered most.

### 5 · The generator writes no audit rows for itself

M14 made `audit_log` one path with one writer. A generator that wrote 14,000 audit rows would fill
the trail with the machine's own work and bury the handful of rows a demo is meant to show. Seeded
history is history; the audit trail starts when a person does.

Where a service writes one as a side effect, it stays — decision 1's "through the services" means
accepting what they do — and the build log records how many that is.

### 6 · `make seed-small` is seven days and is what tests use

Five minutes is fine for a demo and intolerable in a test suite. `make seed-small` generates seven
days with the same code and the same seed. The signal tests that need a long window generate their
own span directly rather than relying on the small one.

---

## Not in scope

- **No new tables, no new endpoints, no new screens.** This module writes data.
- **No second tenant's history.** `seed/tandoor-house.yaml` has no loader yet; a second tenant with
  a hundred days of trading is not what tenant isolation needs to be tested, and one exists already.
- **No AI advisor.** Signal 14 is planted so vision §26 can be tested when it is built. Phase 3.
- **No performance data.** M17 owns measurement of people, with guardrails this module does not
  have. Signal 6 (one waiter's error rate) is planted as *order data*, not as a score.

---

## Acceptance criteria

1. All **fourteen** planted signals from `docs/seed-data.md` are present and each has a test that
   fails when its planter is removed.
2. **M13's reports find them**: the dish-performance report puts Chilli Paneer in `plough_horse` and
   Malai Kofta in `hidden_gem`; the variance report shows Butter Chicken's gravy drift; the waste
   report shows the Tuesday/Wednesday makhani over-production.
3. Same seed and same end date produce byte-identical figures across two runs.
4. Blended **theoretical** food cost is 25.7% ± 0.5; **actual** lands at 32% ± 1.5 — the gap that is
   the product.
5. Every order's `business_date` respects the 05:00 start, asserted on an order generated after
   midnight.
6. Every invoice sequence is gapless per financial year, and every GST line splits equally.
7. No generated data reaches a real report: a non-demo restaurant's reports are unchanged by a run.
8. `make seed` completes inside five minutes, measured, with the figure in the build log.
9. `make seed-small` generates seven days and is what the suite uses.
10. The generator is idempotent in the same sense the other seeders are: a restaurant that already
    has generated history is left alone.

---

## Chunks — three PRs against `feat/m15-generator`

**A · The shape.** The demand model, the deterministic clock, the dish mix and the measurement that
decides decision 1. Ends with one day generated and verified by hand.

**B · The signals.** Fourteen planters and `test_planted_signals.py`.

**C · The volume and the proof.** 120 days, `make seed-small`, the M13 reports asserted against the
generated data, and the seed-data doc updated with anything reality changed. Ends with `make check`
clean and the timing in the build log.
