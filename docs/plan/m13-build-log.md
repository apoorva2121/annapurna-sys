# M13 · Reports & Dashboards — Build Log

Spec: `docs/modules/M13-reports-spec.md`. Manual script: `docs/manual-tests/M13-reports.md`.

---

## State

| Chunk | What | State |
|---|---|---|
| A | `repositories/reporting.py`, `services/reporting.py`, migration 0047, 17 tests | ✅ committed |
| B | `schemas/reporting.py`, four routes + streamed CSV, 12 endpoint tests | ✅ committed |
| B′ | The fifth report (`/reports/waste`), and the duplication it costs | ✅ committed |
| C | Five screens, `StatTile`, `ExportButton`, `reportDiscipline`, the latency file, migration 0048 | ✅ committed |
| — | Manual pass | **Owner's** |

Built in one autonomous run on 2026-09-18, on `feat/m11-communication` after M11 and M12.

---

## Acceptance criterion 13 — the measurement, with its plans

The spec: *"The budget is 800 ms at p95 and an unmet budget is a finding. Measured on seeded data
with the plan attached. **Silence is not a result.**"*

Measured against ninety business days of trading in a single restaurant — **1800 bills, 5400 order
lines, 7200 ledger movements, 40 ingredients, 6 dishes** — built by `tests/test_reporting_latency.py`
and `ANALYZE`d first, because a planner with no statistics chooses a different plan from the one a
real database would and a measurement of the wrong plan is not a measurement.

Nine runs each after a warm-up, on the test container (Postgres 16, Docker Desktop, Windows laptop):

| Report | median | slowest of nine | budget |
|---|---|---|---|
| `sales` | **16.3 ms** | 18.1 ms | 800 ms |
| `food_cost_variance` | **22.5 ms** | 28.0 ms | 800 ms |
| `dish_performance` | **32.0 ms** | 36.4 ms | 800 ms |
| `waste` | **5.8 ms** | 7.2 ms | 800 ms |

Every report is between 4% and 5% of its budget, on a laptop, inside a container, with the suite
running. **Decision 1's trigger is therefore not met**: no rollup, no materialised view, no nightly
job is justified, and the trigger stays where the spec put it — a *measured* breach on realistic
data, not a feeling.

### The plans, and the one thing they found

```
sales_by_day        HashAggregate (rows=90)  ← Hash Join ← Seq Scan on invoice (1800 rows, 52 buffers)
                    Execution Time: 2.871 ms
dish_performance    HashAggregate (rows=6)   ← Hash Join ← Seq Scan on order_line (5400 rows, 135 buffers)
                    Execution Time: 5.330 ms
consumption         HashAggregate (rows=40)  ← Seq Scan on stock_movement (7200 rows, 150 buffers)
                    Execution Time: 6.872 ms
waste_by_reason     GroupAggregate           ← Nested Loop Semi Join
                    Execution Time: 0.140 ms
```

The sequential scans are the planner being right: 7200 rows in 150 buffers is cheaper to read than
to index-seek, and forcing an index there would make the report slower.

**What the plans did find is a column filtered with no index on it, and it is not a scale
argument.** `invoice` carries `ix_invoice_restaurant_date` on `(restaurant_id, invoice_date)` — the
date printed on the document. Every report filters on `business_date`, the restaurant's own trading
day, which starts at 05:00 and is a *different column with different values for every bill settled
after midnight*. So the product's most-run report had an index for the column beside the one it
uses. `0048_m13_report_indexes` adds `(restaurant_id, business_date)` and nothing else: `order`,
`payment`, `stock_movement` and `wastage_event` each already carry that pair or better.

`test_reporting_latency.py` keeps the shape rather than the number: a catastrophe bound of 4 s
(a report that has stopped being a query), and an assertion that ninety days does not cost ninety
times one day. The product's 800 ms budget is verified on staging, where the hardware is the
product's own — the same split `test_kitchen_latency.py` made for the rail, and for the same
reason: a test that asserts a production budget on a laptop fails for reasons nobody can act on and
gets deleted rather than investigated.

---

## The findings

### 1 · The acceptance query is answered by two reports, not one

`docs/domain-model.md`'s chain — *"per dish: units sold, revenue, theoretical food cost, actual
ingredient consumption, the variance between them, waste attributed to it, average prep time,
average rating"* — is criterion 1, and it does not fit in one report. Not because the query is hard,
but because **half of it is not a per-dish fact**.

Units, revenue, theoretical cost, prep time and rating are per dish, read from figures frozen on the
settled line. Actual consumption is measured at the shelf, per *ingredient*: a kilo of paneer that
went missing did not arrive with a note saying which dish it was meant for. Splitting it across
dishes in proportion to what the recipes say would produce a figure that looks per dish and is
really the theoretical number wearing a different hat — which is exactly what invariant 7 forbids.

So the chain is answered per dish by `dish_performance` and per ingredient by `food_cost_variance`,
over the same period and the same restaurant, and `TestTheChainThatHasToWork` asserts both halves
together because a test of each separately would not show that the chain works end to end.

**This is a finding for the owner, not a decision taken quietly**: if a per-dish variance figure is
wanted later, it is an apportionment with a stated method and an uncertainty, not a measurement, and
it belongs beside M17's guardrails rather than in a report that currently only states facts.

### 2 · The fifth report is a second query over rows M09 already aggregates

The spec's route table lists `GET /reports/waste` as "M09's summary, widened". It is not a wrapper
around M09's: it is a second aggregation in `ReportingRepository`, and the reason is the P1
permission design.

`/wastage/summary` sits behind `stock.view` — a chef and a kitchen hand hold it, an accountant does
not. `/reports/waste` sits behind `report.operational.view` — an accountant holds it, a chef does
not. **Neither role can reach the other's screen**, so collapsing the two would take the waste
report away from somebody. And every report carries the demo-organization exclusion (decision 8) in
one place, `_real_restaurants()`; bending M09's repository to take a reporting concern would have
put that rule in two.

The price is paid explicitly: `test_the_waste_report_agrees_with_m09s_own_summary` runs both against
one fixture and compares them line for line, and
`test_the_accountant_reads_the_waste_the_chefs_screen_withholds` asserts the permission split that
justifies them both existing. Two queries over the same rows drift; those are the tests that stop
them.

### 3 · Four of the product's own constraints refused the fixtures

Continuing the pattern from chunk A, where seven did. Each refusal was the schema being right:

- **`spoilage` is not a waste stage.** `ck_wastage_reason_stage` refused the row. The four are
  receiving, storage, prep and service (`docs/waste-model.md`), and a fifth invented from memory
  would have reached a report.
- **A GST line's two halves must be equal and sum to its tax** (`ck_order_line_gst_split`, M07
  decision 4). The latency fixture carried `tax_amount` with `cgst_amount = sgst_amount = 0` and
  was refused — the rule every Indian invoice this product issues has to satisfy.
- **A settled order takes no new lines** (invariant 6, enforced by trigger). Chunk A's fixture had
  to be rebuilt open → line → settled; the bulk fixture here inserts each bill whole, the way a
  restore would.
- **`business_date` is not `invoice_date`.** Caught by a query plan rather than a constraint, and
  the subject of migration 0048 above.

### 4 · A test that asserted three thirds add to exactly 100 was asserting something false

A third of a total is 33.33% at two decimal places and three of those are 99.99%. Criterion 14 says
*"sum to 100 within a paisa"* and means it; the test now says that, and names the failure it
actually rules out — a share computed per row in SQL, which drifts by whole percentage points.

A second test claiming to prove the share is computed from an *unrounded* cost was **deleted rather
than kept**: `wastage_event.cost_value` is `NUMERIC(12,2)`, so the database has already rounded
before the service sees a figure, and the test was proving the column's work. A vacuous test is
worse than no test — it reports safety that is not there.

---

## The screens, and why there is still no charting library

The `dataviz` skill was loaded before the first screen was written, and its own form heuristic sent
every one of these to tiles and tables: *"a handful of headline numbers → a KPI row of stat tiles"*
and *"more than ~7 classes that all carry meaning → a table"*. Neither is a chart. A charting bundle
is roughly half a megabyte in a PWA a waiter loads on a three-year-old Android, and it would have
been spent drawing four numbers somebody reads in two seconds. `reportDiscipline.test.ts` names the
seven libraries anybody would reach for and fails if one appears in `package.json`.

**The delta is never rendered in an alert colour**, which is a deliberate reading of
`docs/ui/conventions.md`. The six alert colours are locked and `critical` means *somebody must act
now*. Revenue down against yesterday is information, not an alarm — painting it red spends the
product's strongest signal on a Tuesday being quieter than a Monday, and teaches people to ignore
red. Direction is an arrow and a word in muted ink.

**A manager is not offered the money at all** — not a disabled link, not a screen with blanks.
`TodayScreen.test.tsx` asserts both halves of that: a manager is offered dishes and waste, an owner
is offered all four.

---

## What is not here

- **The 14 planted signals.** Owner's decision, 2026-09-18: they need M15's 120-day generator, and a
  report run over the handful of days the seed currently holds would pass and prove almost nothing.
  The test is written and pointed at M15, which is where it becomes an exit criterion.
- **A filtered drill-down.** Decision 4 is met the way it can be: an ingredient on the variance
  report links to the ledger, a dish on the performance report links to the costing screen, and a
  day on the sales report links to the bills — each link gated on the permission that opens the
  screen behind it, because offering a door that answers 403 reads as a broken product. What is not
  built is the *pre-filtered* version of each — the ledger already showing that item, the bills list
  already showing that day. That is a screen taking a query parameter rather than a link, and it
  goes on `docs/backlog.md`.

---

## Tests

| File | Count |
|---|---|
| `tests/test_reporting.py` | 27 |
| `tests/test_reports_endpoints.py` | 14 |
| `tests/test_reporting_latency.py` | 5 |
| `frontend/src/staff/reportDiscipline.test.ts` | 6 |
| `frontend/src/staff/screens/TodayScreen.test.tsx` | 4 |
