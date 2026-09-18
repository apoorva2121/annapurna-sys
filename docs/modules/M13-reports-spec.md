# M13 · Dashboards & Reports — Module Spec

**Depends on** M07 (orders, settlement, the frozen theoretical cost), M05 (the ledger), M09
(waste), M04 (recipes and costing), M08 (prep timestamps), M10 (ratings).
**Status** — spec written 2026-09-18, before any code, per `docs/sdlc.md` step 1.
Build log: `docs/plan/m13-build-log.md`.

Tables: **none**. Endpoints: `GET /dashboard/today`, `/reports/sales`,
`/reports/food-cost-variance`, `/reports/dish-performance`, `/reports/waste`, each with a CSV form.
Screens: manager today, food-cost variance, dish performance, waste breakdown, owner summary.

**Two owner decisions taken before this spec was written** (2026-09-18):

1. **Build M13 now against per-report fixtures.** The 14 planted signals need M15's 120-day
   generator, which does not exist; each report is instead proven against a dataset engineered to
   make it fail, and the 14-signal test becomes **M15's** exit criterion.
2. **CSV export is in.** An accountant works in Excel, and a report you cannot get out of the
   screen is a report somebody re-types by hand.

---

## Where the product finally shows its face

Every module so far has been a place to *put* information. This is the first one that gives any of
it back, and the vision document's commercial argument — *we will show you where your food cost
actually goes* — is one screen in this module or it is nothing.

So the standard is not "the numbers are correct". M04's golden tests and M07's property tests
already establish correctness, and a correct number nobody acts on is the thing this product exists
to replace. The standard is **would a restaurateur change what they do on Monday because of this
screen**, and only the owner can answer it, in the manual pass.

---

## Research — what binds this module, checked 2026-09-18

**`docs/compliance-rules.md`: nothing in §A or §B binds a report.** Checked rather than assumed.
No menu text, no restaurant identity, no tax rate charged to anybody, no customer data leaving the
building. §A5 binds the *invoice*, which M07 owns; a report reads what M07 wrote and changes
nothing.

**`docs/schema.md` already refused this module's tempting shortcut.**
`chef_performance`, `dish_stats` and `waiter_performance` are not a table between them: it
eliminated all three with a sentence this module inherits rather than re-argues — **"These are
queries, not tables. Storing them creates a second source of truth that silently drifts."**

**The frozen cost is the module's foundation, and it already exists.** `order_line.
theoretical_unit_cost` (`NUMERIC(14,6)`) and `order.theoretical_food_cost` are written at
settlement from the recipe version in force *then* — `settlement.py`'s own words: *"what did this
bill cost in March is answered from March's recipe rather than today's."* Every dish figure in this
module reads those columns. **No report recomputes a cost from today's recipes**, because that
would let a recipe edit rewrite last month.

**Invariant 7 is the module's subject.** `stock_movement.basis` separates theoretical from actual,
and the enum's own docstring states the rule: on-hand sums both; a single *consumption* figure
never may.

**Invariant 4 decides every date.** Aggregations group on the denormalised `business_date`, never
on `date_trunc('day', created_at)`.

**The P1 design's permission split is sharper than it first looks**, and it decides the screens:

| Role | `report.operational.view` | `report.financial.view` | 
|---|---|---|
| owner | ✅ | ✅ |
| accountant | ✅ | ✅ |
| manager | ✅ | ❌ |
| store_manager | ✅ | ❌ |

**A manager does not see the money.** That is the design's line, and it means the financial screens
belong to the owner and the accountant — not a manager screen with blanks in it.

---

## The decisions that matter

### 1 · These are queries, not tables, and the trigger to change that is a measurement

No new tables, no materialised views, no nightly rollup.

A rollup becomes justified when a dashboard query is **measured** slower than its budget on
realistic data — not when it feels slow, and not pre-emptively. Until then every number is computed
from the rows that produced it, which is what makes drill-through free and a wrong number traceable
to a wrong row rather than to a stale cache.

The measurement goes in the build log with its query plan, so the trigger is a number somebody can
check rather than a feeling somebody had.

### 2 · Theoretical and actual are never summed, and the report *is* the gap

| Column | Where it comes from |
|---|---|
| Theoretical consumption | `stock_movement` where `basis='theoretical'`, written by settlement |
| Actual consumption | `basis='actual'` — receipts, weighed waste, physical counts |
| Variance | the difference, in base units **and** in rupees at the batch cost |
| Attributed waste | `wastage_event` — variance somebody *explained* |
| **Unexplained** | variance minus attributed waste |

The last row is the module. Everything above it is arithmetic; that line is what an owner acts on,
and it is the line a competitor's report does not have.

### 3 · Every number carries its baseline, computed on the server

`docs/ui/conventions.md`: *"Every metric shows a comparison (vs yesterday, vs last week) — a number
with no baseline is not information."*

The comparison comes from the API, over the same bounded query. Not from the client: a browser
subtracting two separately-fetched numbers is one rounding rule away from disagreeing with the
figure beside it.

### 4 · Every number drills through to the rows behind it

A figure that cannot be opened is a figure nobody trusts the second time it surprises them. Free,
because of decision 1.

### 5 · The quadrant gives advice, and says that it is advice

Vision doc §12. Popularity against margin, with rating and waste beside it: **Stars**,
**Plough-horses** (planted signal 7 — Chilli Paneer at 46% food cost), **Hidden gems** (signal 8 —
Malai Kofta, 4.7 rating, 11 orders), **Dogs**.

**The screen recommends; it never acts.** A product that removed a dish because a quadrant said so
would be wrong about one restaurant in five, and the one it was wrong about would be somebody's
signature dish.

### 6 · CSV is the same query, streamed — never a second code path

A CSV that disagrees with the screen is the worst defect a report can have: both look
authoritative and nobody can tell which is lying. The export calls the same repository method with
the same bounds and differs only in serialisation. A test asserts they agree, row for row.

Streamed rather than assembled — a year of order lines is not a string in memory.

### 7 · Money stays a string to the boundary, and is never rounded twice

`Decimal` in Python, string on the wire (invariant 3). A percentage is computed once, at the end,
from unrounded inputs — M09's summary already set the rule, and a report is where rounding twice
looks most harmless and is most wrong.

### 8 · The demo organization is excluded from reporting

`organization.is_demo` has existed since M01. The exclusion lives in the repository, not in each
query: one place to be right.

### 9 · The budget is 800 ms at p95, and an unmet budget is a finding

Measured on seeded data with the plan attached. Silence is not a result.

---

## Not in scope

- **No new tables, no materialised views, no nightly job.** Decision 1.
- **No AI advisor.** Vision §26 is Phase 3; planted signal 14 exists for it, and this module only
  has to make the data reachable.
- **No emailed digest.** Email is not in month 1; notification paths are M14's.
- **No custom report builder.** Five reports answering known questions beat a query builder nobody
  uses.
- **No cross-branch rollups.** Out of month 1 (CLAUDE.md).
- **No performance-by-employee figure.** Variance is attributed to a dish and a period, never to a
  person: M17 is where people are measured and it has guardrails this module does not.
- **The 14-signal test does not run here.** Owner's decision 1; it is written and pointed at M15.

---

## Deliverables

### Migrations — two, and neither adds a table

`0047_m13_permissions`: `report.operational.view` and `report.financial.view`, both already in the
P1 design, granted as the table above.

`0048_m13_report_indexes`: whatever the query plans show missing once the reports run against real
data. Written **last, from measurements** — an index added speculatively is a write cost nobody can
justify later. If the plans show nothing missing, the migration is not written and the build log
says so.

### Backend

- `app/repositories/reporting.py` — every aggregate, one method each, bounded by `business_date`
  and scoped by the repository. No service assembles SQL.
- `app/services/reporting.py` — baselines, quadrant classification, the unexplained-variance
  arithmetic. Nothing a query should have done.
- `app/api/v1/staff/reports.py` — five reports and the dashboard, each with `?format=csv`.
- `app/schemas/reporting.py` — money as strings, `extra="forbid"`, every figure with its comparison.

### Endpoints

```
GET /dashboard/today                 report.operational.view   the manager's glance
GET /reports/sales                   report.financial.view     revenue, covers, average bill
GET /reports/food-cost-variance      report.financial.view     theoretical vs actual vs waste
GET /reports/dish-performance        report.operational.view   the quadrant, per dish
GET /reports/waste                   report.operational.view   M09's summary, widened
GET /reports/<any>?format=csv        (as above)                the same query, streamed
```

### Frontend (staff bundle)

Manager surface for the operational reports, owner surface for the summary and the money. Per
`docs/ui/design-system.md` and the `restaurant-ui` skill; charts per the `dataviz` skill, loaded
**before** the first chart is written.

---

## Threat question — *what would an insider do with this?*

**Read another branch's figures.** Every query is repository-scoped and suite 1 probes every route.
Cross-branch rollups are out of scope precisely so there is no legitimate cross-tenant query to
hide behind.

**Read the money without the permission.** `report.financial.view` is the owner's and the
accountant's, and the *screens differ* rather than one screen rendering blanks — a disabled figure
invites somebody to find the endpoint.

**Use the variance report to learn what is not being watched.** That is the point; the report
exists to make shrinkage visible. What it must never do is name a person as the cause.

**Export the customer list through a report.** No report returns a customer's name or number.

---

## Acceptance criteria

1. `docs/domain-model.md`'s acceptance query — per dish, last week: units sold, revenue,
   theoretical cost, actual consumption, variance, waste attributed, average prep time, average
   rating — is answerable, and the dish-performance report *is* that query.
2. Dish costs come from `order_line.theoretical_unit_cost`, so editing a recipe moves no historical
   figure.
3. Every figure carries a comparison computed on the server over the same bounds.
4. Every aggregate links through to the rows behind it.
5. Theoretical and actual are never summed into one consumption figure, asserted per report.
6. Unexplained variance = total variance − attributed waste, on a fixture where the two differ by a
   known amount.
7. The CSV and the screen agree row for row, for every report.
8. Every aggregation groups on `business_date`; no report calls `date_trunc` on a timestamp.
9. A 01:30 order counts towards the previous business day in every report.
10. The demo organization appears in no report.
11. A manager cannot reach a financial report.
12. Query counts are bounded: a report over 7 days and over 90 days issues the same number.
13. p95 under 800 ms on seeded data, measured, with the plan in the build log.
14. Percentages are computed once from unrounded inputs and sum to 100 within a paisa.
15. Generic suites 1–5 pass.

---

## Chunks — three PRs against `feat/m13-reports`

**A · The queries.** The reporting repository and service, the two permissions, and the tests: each
report against a fixture engineered to make it fail, plus the acceptance query.

**B · The endpoints and CSV.** Five routes, the dashboard, the streamed export, the agreement test.

**C · The screens.** Five, with their charts, and the manual script. Ends with `make check` clean
and the measured p95 in the build log.
