# M19 · Owner Analytics — Module Spec

**Depends on** M07 (orders), M09 (waste), M13 (the report query layer), M14 (severity), M15 (120
days of generated trading to test against). **Status** — spec written 2026-09-19, before any code,
per `docs/sdlc.md` step 1. Build log: `docs/plan/m19-build-log.md` (not yet started).

Tables: **none.** Endpoints: trend and comparison variants of M13's five reports. Screens: one
analytics shell, charts behind the desktop breakpoint, and an action queue.

---

## What this module is, and the one sentence that decides its shape

`docs/product/vision.md` frames the product as three questions:

> **What is happening?** — real-time operations. **What is going to happen?** — forecasting.
> **What should I do?** — recommendations.

**M13 answered the first.** Five reports — today, sales, food-cost variance, dish performance,
waste by stage and reason — each with CSV export, each measured at p95 16–32 ms against an 800 ms
budget. This module is the second and third, and the temptation it has to survive is building the
second badly because it is more exciting than the third.

The owner's actual question is not *"what will happen"*. It is **"what should I do on Monday
morning"**, and `docs/product/competitor-research` says the market fails at exactly this: Petpooja
ships 80+ reports, Restroworks 100+, and a restaurant reads none of them. **Report count is the
failure mode, not the feature.**

So the module's own rule, and the thing to hold it to at review:

> **Every screen here either shows a shape a table cannot, or produces an action with a rupee
> figure on it. A screen that is a table with a chart on top is a screen this module should not
> ship.**

---

## Research — what binds this module

**`docs/backlog.md` carries eleven rows that belong here.** They were harvested from the rejected
enterprise-analytics proposal, from competitor research, and from M13's own deferrals. Seven are in
scope below; four are named as out.

**M13 deliberately ships no charting library.** Half a megabyte in a PWA a waiter loads on a
three-year-old Android, to draw four numbers read in two seconds. **That reasoning is sound for the
waiter's bundle and irrelevant for an owner on a laptop** — which is the whole reason this module
can exist without contradicting M13.

**The `dataviz` skill governs every chart**, and its non-negotiables are not style preferences:
one axis and never two; colour follows the entity and never its rank; a legend always for ≥2
series; the palette validated by running the validator rather than by eye.

**ADR 0011's fairness guardrails reach into this module.** Leakage patterns and variance
attribution both touch individual staff, and `docs/workload-fairness.md`'s review applies unchanged:
no bottom ranking, no automatic consequence, context shown beside the number.

**M15 is what makes a forecast checkable.** 120 days of generated trading with 14 planted signals,
already asserted by `tests/test_planted_signals.py`. A forecast can be **scored against data whose
answer is known** before a restaurant sees it — which is a thing this product has and its
competitors do not.

**`docs/compliance-rules.md` binds anything touching money or tax**, as it binds every module.

---

## The decisions that matter

### 1 · 🔴 OPEN — does the owner see one organization, or one branch at a time?

**This is the owner's decision and the spec cannot close without it** (`docs/owner-actions.md` Q3).

Today every report is **one branch**: `ReportingRepository._real_restaurants()` filters
`Restaurant.id == scope.restaurant_id`, and an owner with two branches switches between them
(`POST /auth/switch`). CLAUDE.md lists multi-branch rollups as deliberately out of scope for month
one — *"design so none of these are blocked later"* — and they are not blocked: `TenantScope`
already carries `organization_id`, every tenant table has `restaurant_id`, and every hot index
leads with it. An org view is `WHERE restaurant_id IN (…)` over queries that already exist.

Three things follow from the answer, and each is a product decision rather than a technical one:

1. **Do money figures sum across branches with different GST registrations?** Two restaurants under
   one organization can hold different GSTINs and even different schemes — one regular, one
   composition. A summed "revenue" across those is a number with no tax meaning. The honest answer
   is probably that **revenue sums and anything tax-shaped does not**, and the screen says so.
2. **What does a figure mean when one branch was closed for half the period?** A rollup that
   silently averages a closed branch into a per-cover figure is wrong in the direction that looks
   fine.
3. **Does a manager at two branches get a rollup of their two?** If yes, "org view" is really
   "every branch you hold a role at", which is a cleaner rule and makes the owner's view a special
   case rather than a separate feature.

**My recommendation, for the owner to accept or reject:** an org view that is a **comparison
first and a sum second**. A sum answers *"how are we doing"*; a comparison answers *"which branch
has the problem"*, and only the second leads to an action. Revenue and covers sum; anything
tax-shaped is shown per branch and never totalled.

### 2 · Charts live behind the desktop breakpoint, and the bundle proves it

Not "charts are fine now". The waiter's bundle must not grow, so:

- the charting library is imported **only** in a route that code-splits, and
- `frontend/src/staff/bundleBudget.test.ts` (new) asserts the guest and service bundles do not
  import it at all — the same shape as `reportDiscipline.test.ts` and `complianceDiscipline.test.ts`.

A test rather than a convention, because the failure is invisible until somebody profiles a phone.

### 3 · Every metric is specified as metric → source tables → formula → render

Adopted from the backlog row that harvested it: M13 lists screens and rules but never pins the
arithmetic, **which is how two dashboards end up computing "food cost %" differently**. Every
metric in this module gets a four-column row in the build log before it gets a query, and the
formula column is the one a reviewer checks.

### 4 · Trends before forecasts, and a forecast that has not been scored does not ship

Every M13 report already takes `since`/`until`, so a series over eight weeks is the same query
repeated — cheap, and it makes the existing reports worth opening twice.

A forecast is a claim about the future made to somebody who will **order stock against it**. So:

- it is scored against M15's generated 120 days, where the answer is known;
- the score is published on the screen beside the number — *"this forecast has been within 12% on
  historical data"* — rather than kept in a build log;
- **it shows its interval, not a point.** A single number invites somebody to order to it.

### 5 · The action queue is the third question, and it is the point of the module

One card per insight: **a rupee figure, one action, and three answers — Do it / Not now / Not
true.** *Not true* is the interesting one: it tunes the rule, and the tuning is published monthly
so the owner can see the product learning rather than being told it does.

It needs M14's severity so it does not become the 81st report. **A card with no rupee figure does
not go in the queue** — that is what stops it filling with advice.

### 6 · Anything naming a person goes through the fairness review first

Leakage patterns — cancelled-after-KOT lines, reprints, unexplained comps, discounts clustered by
login and shift — are the highest-value and highest-risk thing in this module. `docs/workload-
fairness.md`'s guardrails apply without modification: **no bottom ranking, no automatic
consequence, context beside every number**, and the same ethics questions answered in the build log
before the screen is written.

Variance attribution keeps staff meals and comps separate from theft, as `docs/waste-model.md` §4
already insists.

---

## Not in scope

- **Natural-language analytics and the AI advisor.** Vision Phase 3. *"Why did profit fall this
  month?"* wants the first three things here to be trustworthy before anybody asks it a question.
- **Reorder points, par levels and suggested orders.** The owner asked for "weekly requirements"
  and **this is not analytics** — a suggested order is an *action*, and it belongs beside
  procurement where it can be turned into a purchase order. `docs/backlog.md`'s M06 row owns it,
  and it should probably be built **before** this module.
- **Customer analytics (RFM, cohort retention, CLV) and basket analysis.** Genuinely valuable, and
  a module of their own — they need M10's customer data at a volume no pilot has yet.
- **A WhatsApp close-of-day report.** Needs a messaging channel, out of scope for month one.
- **Per-channel dish margin.** Needs aggregator orders, which this product does not take.

---

## Acceptance criteria

1. Decision 1 is answered by the owner and the answer is written in the build log before any query
   is written.
2. Every metric has its four-column row — metric, source tables, formula, render — and no two
   screens compute the same metric twice.
3. The charting library appears in **no** bundle a waiter or a guest loads, asserted by a test.
4. Every chart passes the `dataviz` palette validator, run rather than eyeballed, in both light and
   dark mode.
5. No chart has two y-axes. No categorical colour is one of the six alert hues. Every chart with
   ≥2 series has a legend, and ≥4 series are also directly labelled.
6. Every figure on every screen opens the rows it came from, **already filtered** — closing the
   M13 row that left this at "the right screen" rather than "the right row".
7. A forecast displays an interval and its historical score, or it is not shown.
8. Every action-queue card carries a rupee figure and exactly one action.
9. Nothing that names an individual ships without the `docs/workload-fairness.md` review answered
   in the build log.
10. The dashboard latency budget (800 ms, `docs/checklist.md`) holds on 120 days of generated data,
    measured rather than assumed.
11. `make check` clean.

---

## Chunks — four PRs against `feat/m19-analytics`

**A · Trends.** The series endpoints over M13's existing queries, the metric table, and the
org-vs-branch decision implemented whichever way the owner answered. No charts yet — this chunk
ends with JSON and tests.

**B · The charts.** The analytics shell, code-split, the palette validated, the bundle test, and
the drill-through that lands on the right row.

**C · The action queue.** Cards with rupees, three answers, M14 severity, and the monthly tuning
report. The fairness review answered in the build log before the leakage card is written.

**D · One forecast, scored.** The narrowest useful one — next week's covers by day — scored
against M15's generated history, shown as an interval with its score beside it. If it cannot beat
"last week's number", **it does not ship**, and the build log says so.
