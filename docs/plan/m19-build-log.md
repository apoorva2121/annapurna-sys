# M19 · Owner Analytics — build log

Spec: `docs/modules/M19-analytics-spec.md`. Branch: `feat/m11-communication` — see
§"Why this is not on `feat/m19-analytics`" below.

| Chunk | What | State |
|---|---|---|
| A | Trends: series endpoints, the metric table, the org decision implemented | **done** 2026-09-20 |
| B | The charts, code-split, bundle test, drill-through | **done** 2026-09-20 |
| C | The action queue | not started |
| D | One forecast, scored | not started |

---

## Decision 1, answered — org view or one branch at a time

**Asked of the owner on 2026-09-19** (`docs/owner-actions.md` Q3, which had been marked 🔴 and
blocking). **Answered the same day: a comparison first and a sum second.**

Acceptance criterion 1 of the spec is *"Decision 1 is answered by the owner and the answer is
written in the build log before any query is written"* — this section is that record, and it was
written before the first line of chunk A.

What the answer commits the build to, in the order the code has to honour it:

1. **Revenue and covers sum across branches.** They are counts of the same thing in the same unit,
   and a sum of them is a figure with a meaning.
2. **Nothing tax-shaped sums.** Tax, and anything derived from tax, is carried **per branch with no
   total on the response at all** — not a total the client is asked politely not to render. Two
   restaurants under one organization can hold different GSTINs and different schemes (one regular,
   one composition); a summed tax figure across those is arithmetic with no legal referent. Checked
   against `docs/compliance-rules.md` before writing this, not recalled.
3. **A branch that did not trade for the whole period is named.** A per-cover or per-day figure
   that silently averages in a branch which traded nine days of thirty is wrong in the direction
   that looks fine — it looks like a soft month rather than a closed shop. Each branch row carries
   the number of business days it actually issued an invoice on, and any per-day figure is computed
   over *that* count.
4. **Which branches the view covers was not part of the question and is not invented here.** The
   owner chose the *shape* of the view. The access rule already exists:
   `AuthService.switch_restaurant` admits exactly the branches in
   `AccessService.restaurants_for_employee(employee.id)`, within the actor's own organization and
   active. The org view reuses that set. A two-branch manager therefore sees their two, and the
   owner's view is the general case rather than a separate feature. Restricting the org view to
   owners specifically would be a permission change layered on top, not a different query — and it
   is not made here because nobody asked for it.

**Where the widening actually happens.** `ReportingRepository._real_restaurants()` is a single
`Select[tuple[uuid.UUID]]` that every M13 query already filters through with `.in_(...)`. It
returns one id today. The org view is that method returning several. **No M13 query changes**,
which is the whole reason this is a chunk and not a rewrite — and it is also the risk: widening a
tenant filter is invariant 1's blast radius, so the tenant-isolation tests below are the ones that
matter, not the arithmetic ones.

---

## The metric table

Acceptance criterion 2: *every metric has its four-column row — metric, source tables, formula,
render — and no two screens compute the same metric twice.* The reason is in the spec: M13 lists
screens and rules but never pins the arithmetic, **which is how two dashboards end up computing
"food cost %" differently.**

Every formula below is the one M13 already computes. Where a cell says *"M13:"* it names the method
that owns it, and this module calls that method rather than restating the SQL.

| Metric | Source tables | Formula | Render |
|---|---|---|---|
| `revenue` | `invoices` ⋈ `orders` | `SUM(invoice.grand_total)` where `cancelled_at IS NULL`, grouped by `invoice.business_date`. M13: `sales_by_day`. Cancelled invoices keep their number for GST and contribute nothing | Line, ₹, one axis. Sums across branches |
| `covers` | `invoices` ⋈ `orders` | `SUM(order.covers)` over the same filtered invoices. M13: `sales_by_day` | Line, count. Sums across branches |
| `orders` | `invoices` | `COUNT(DISTINCT invoice.order_id)`, same filter. M13: `sales_by_day` | Line, count. Sums across branches |
| `average_bill` | derived | `revenue / orders`, `Decimal`, never a float, undefined (`null`, not `0`) when `orders = 0`. M13: `ReportingService.sales` via `_per` | Line, ₹. **Recomputed from summed revenue and summed orders, never averaged from per-branch averages** |
| `tax` | `invoices` | `SUM(cgst_total + sgst_total)`, same filter. M13: `sales_by_day` | Per branch only. **No total.** See decision 1.2 |
| `discounts` | `invoices` | `SUM(invoice.discount_total)`, same filter. M13: `sales_by_day` | Line, ₹. Sums across branches |
| `theoretical_value` | `stock_movements`, `recipes`, `order_lines` | M13: `consumption` — recipe usage costed at the movement's own valuation | Line, ₹. Never added to `actual_value` (invariant 7) |
| `actual_value` | `stock_movements`, `stock_counts` | M13: `consumption` — what the physical counts say left the store | Line, ₹, **second series on the same axis as theoretical**, never a second y-axis |
| `variance_value` | derived | `actual_value − theoretical_value`. M13: `_variance_line` | Line, ₹, signed |
| `unexplained_value` | derived | `variance_value − waste_value` — the part of the distance nobody wrote a reason for. M13: `_variance_line` | Line, ₹. The module's headline number |
| `waste_value` | `waste_events` ⋈ `waste_reasons` | `SUM(cost_value)` per stage and reason. M13: `waste_by_reason` | Stacked by **stage**, never one total (`docs/waste-model.md`: four stages, four owners, four fixes) |
| `food_cost_percent` | derived | `theoretical_value / revenue × 100`, `Decimal`, `null` when `revenue = 0`. **One definition, this row, and every screen that shows a food-cost percentage calls it** | Line, %, own chart — a % and a ₹ on one axis is the two-axis mistake wearing a disguise |
| `business_days_traded` | `invoices` | `COUNT(DISTINCT invoice.business_date)` where an invoice was issued. **Not** the number of days in the window | Never charted. Shown beside any per-day figure, and it is what decision 1.3 is enforced with |

### Decision 2, answered — what branches are compared *on*

**Asked of the owner on 2026-09-19 while chunk A was being written. Answered: revenue per cover.**

The comparison view needed a basis to rank on, and the choice is a product decision rather than a
technical one: rank on raw revenue and the screen reports that the big branch is big, which fails
the module's own rule that *every screen either shows a shape a table cannot, or produces an action
with a rupee figure on it*. Spend per guest is size-neutral — a 22-seat branch can beat a 60-seat
one — and it moves when something an owner controls moves.

**Implementing it exposed a defect in the obvious implementation.** `order.covers` is NULL for
takeaway and delivery (`ck_order_covers` permits NULL) and SQL `SUM` skips NULLs, so
`total_revenue / total_covers` charges a branch's entire takeaway trade to the guests who sat
down — a delivery-heavy branch posts an impossible spend per head and ranks healthiest. So
`sales_by_branch` carries `dine_in_revenue` as its own column and `comparison_basis` divides *that*
by covers. Found by checking the column rather than by a test failing, which is the only reason it
is not in the product.

**The blind spot is recorded rather than left to be discovered:** a branch whose footfall has
collapsed while its remaining guests spend well looks healthy on this basis. `BranchRow` carries
`covers` and `business_days_traded` so chunk B can put covers-per-trading-day beside it without
reopening this decision.

| Metric | Source tables | Formula | Render |
|---|---|---|---|
| `dine_in_revenue` | `invoices` ⋈ `orders` | `SUM(grand_total)` where `order.type = 'dine_in'`, same invoice filter as `revenue`. M19: `sales_by_branch` | Never charted alone. The numerator of the comparison basis |
| `comparison_basis` | derived | `dine_in_revenue / covers`, `Decimal`, `null` when `covers = 0` — a branch with no dine-in guests has no spend per guest, and a zero would rank a closed branch worst | The figure the branch comparison sorts on |

Two metrics named in the spec are **deliberately absent from chunk A**: anything from the action
queue (chunk C) and the forecast (chunk D). Both get their rows in this table when they are built,
not now, because a formula written before its query is a guess.

### The bucket rule, and why it is not `date_trunc`

A series over eight weeks needs weeks, and a week here is **seven business dates**, not
`date_trunc('week', …)`. `invoice.business_date` is already the restaurant's day — invariant 4 was
paid for once, in M07, and re-deriving a calendar from `timestamptz` in this module would be
paying for it a second time and getting a different answer at 2am. So bucketing is arithmetic on
`business_date`, anchored to the **end** of the window and counted backwards, so the most recent
bucket is always whole and the oldest is the ragged one. An owner comparing "this week" against a
partial week that happens to sit at the start of the window is being shown a fall that is not
there.

---

## Why this is not on `feat/m19-analytics`

The spec says *"four PRs against `feat/m19-analytics`"*. M15, M17 and M18 were all built on
`feat/m11-communication`, which now carries 58 commits that have never been pushed anywhere. Cutting
a new branch off it would fragment an already-unpushed line of work across two local-only branches,
and the failure mode that actually threatens this work is a dead disk, not a tangled history.
**Recorded as a deviation from the spec rather than done quietly.** It should be revisited the
moment the branch is pushed.

---

## Runs

| Run | Result |
|---|---|
| `make check` (baseline, before chunk A) | see below |

---

## Chunk A — finished 2026-09-20

`GET /analytics/trend` and `GET /analytics/branches`, behind `report.financial.view` — the same
permission M13's money screens use, so these are screens a manager does not have rather than
screens with blanks in them.

**No response carries a tax field**, and a test asserts it against the wire rather than trusting the
schema. Two restaurants under one organization can hold different GSTINs and different schemes, so
a summed tax figure has no legal referent; the forbidden total is unrepresentable rather than
discouraged.

The comparison is ordered by spend per dine-in guest, the owner's chosen basis. A branch with no
dine-in guests sorts **last**: `None` means "no answer", and ranking it first would put an empty
restaurant at the head of the table.

### What the endpoint tenant tests prove, and what they do not

**Measured, not assumed.** Deleting the organization filter inside `_real_restaurants` leaves every
endpoint test green. They cannot see it — the API gives no way to name a restaurant id, so
`branch_ids` has already narrowed the set before that filter is reached.

So the endpoint tests ask *"does this leak another tenant's trading"*, which is the question a
client can actually pose. The second lock is tested where it can fail, at the repository, by
`test_across_cannot_reach_another_organizations_branch` — which **does** go red when the filter is
removed. Both layers are worth having: the day somebody adds an endpoint that takes branch ids from
a request, the repository test is the one still standing.

Two of the endpoint tests were also rewritten to be non-vacuous. `len(restaurant_ids) == 1` is true
when the second tenant was never created, which is the shape of green test that proves nothing;
they now assert the other tenant exists and has trading of its own.

    pytest test_analytics_endpoints + test_m19_analytics -> 17 passed
    ruff, mypy clean

---

## Chunk B — finished 2026-09-20

The analytics shell at `/analytics`, two charts, the branch comparison, and the drill-through.

### The deviation, recorded rather than done quietly

**The spec says "import a charting library only in a code-split route". No charting library was
installed, and the charts are hand-drawn SVG.**

The spec's own wording collides with a guardrail that predates it. `reportDiscipline.test.ts` rule 3
asserts that `package.json` contains **no** charting library — `recharts`, `chart.js`, `d3`,
`victory`, `nivo`, `echarts`, `plotly` — and it reads the *manifest*, not the bundle, so
code-splitting does not satisfy it. Building chunk B literally as written would have required
weakening an existing test whose stated reason still holds: *"half a megabyte in a PWA a waiter
loads on a three-year-old Android is spent on four numbers somebody reads in two seconds."*

Hand-drawn SVG satisfies **acceptance criterion 3 absolutely rather than conditionally** — a library
that is not installed cannot reach any bundle — and it turned out to be the easier way to hit
`dataviz`'s mark specs exactly (2px stroke, 8px end marker ringed in the surface colour, a 4px
rounded data-end square at the baseline, a hairline solid grid) rather than bending a library's
defaults toward them. `TrendChart.tsx` and `BarChart.tsx` together are about 450 lines.

### Criterion 3, measured at the bundle rather than argued

`vite build`, 2026-09-20:

    dist/assets/AnalyticsScreen-CW-zjcuF.js    14.45 kB | gzip:  4.54 kB
    dist/assets/staff-BsKOZi7H.js             557.29 kB | gzip: 153.55 kB
    dist/assets/guest-Dpdh7IcJ.js              14.46 kB | gzip:  4.42 kB

    grep -c 'stroke-series-1|fill-series-1'
      AnalyticsScreen chunk ... 1
      staff bundle ............ 0
      guest bundle ............ 0

So the charts cost a waiter **nothing**, and cost an owner who opens the screen 4.54 kB gzipped.
`bundleBudget.test.ts` holds the line in source: no charting library in the manifest or in any
import, the chart components have exactly one importer, the screen is reached only through
`lazy()`, and the guest bundle references none of it. **Each of its four rules was verified by
breaking it and watching it go red**, then reverting — a green discipline test that has never
failed is a test nobody has checked.

### Criterion 4, run rather than eyeballed

The palette is three locked tokens, `--series-1/2/3`, added to the locked layer of `tokens.css`
beside the alert set and the FSSAI marks — not to the themeable set. A series colour is **identity,
not paint**: a theme that repainted it would change a branch's colour between two screenshots of the
same week.

    node scripts/validate_palette.js "#7069D3,#13A4AE,#68840B" --mode light --surface "#FFFFFF"
    node scripts/validate_palette.js "#7069D3,#13A4AE,#68840B" --mode dark  --surface "#10141E"
    -> ALL CHECKS PASS, exit 0, both modes

One set serves both modes because each slot clears 3:1 against **both** grounds — indigo 4.52/4.08,
teal 3.02/6.09, olive 4.29/4.29 — which is what makes locking legal instead of shipping two themed
sets. Three intermediate palettes were rejected by the validator before this one: two for a teal
below the 0.10 chroma floor (cyan is inherently low-chroma in OKLCH at mid lightness) and one for an
olive/teal pair at deltaE 13.7, under the normal-vision floor of 15.

**The HSL round-trip was checked, and it mattered.** The first set was validated as hex and then
written as HSL triplets, which round to slightly different colours; the shipped tokens were
re-validated as *what the browser actually renders*, not as what was intended.

### Why only three slots, and why a fourth is not a free choice

Every chart hue must sit **at least 25 degrees from every alert hue and from `--brand`** — the rule
`docs/ui/design-system.md` lists as designed-but-unimplemented, applied here for the first time.
Excluding 25 degrees either side of critical (0), warning (25), caution (45), success (142),
neutral (215), info (217) and brand (322) leaves exactly three usable bands: **70-117, 167-190,
242-297**. The three slots sit in them. A fourth series is a validator run, and if it cannot be
placed the chart needs fewer series rather than a new colour. `theme.test.ts` now asserts the three
are outside the themeable set.

### Criterion 5

One y-axis on every chart, and every baseline starts at zero. No categorical colour is an alert
hue. Each chart draws **one** series, so the heading does the legend's job — a legend box with a
single swatch restates the heading. `analyticsDiscipline.test.ts` rule 5 is written so that the day
a second series appears, the legend stops being optional.

The branch comparison is deliberately **two charts, not one with two axes**: spend per dine-in
guest (slot 1) and guests per trading day (slot 2). That pairing is the recorded blind spot of the
owner's decision 2 — a branch whose footfall has collapsed but whose remaining guests spend well
looks healthy on spend alone — shown beside it rather than left to be discovered.

### Criterion 6 — the drill-through lands on rows, not on a screen

`SalesReportScreen` now reads `since`/`until` from the URL, so a bucket opens the bills that made
it, already filtered. The window travels in the URL rather than in memory, so the link is shareable
and survives a reload.

**A branch row was the interesting case.** Another branch's rows are not merely a different screen —
they are outside this token's scope (invariant 1), and `/staff/reports/sales` resolves from
`actor.scope`. So the drill-through switches branch, and `switchBranch()` *loads the destination*
rather than reloading in place: a document load preserves the URL, so the filter arrives with the
new scope already in force. No handoff through storage, and so nothing that can go stale if the
switch fails. `BranchSwitcher` was refactored onto the same function rather than keeping a second
copy of the reload reasoning.

### The invariant-3 question a chart forces, and how it was answered

A chart must turn `"1234.50"` into a y-coordinate, which invariant 3 and `reportDiscipline` rule 1
forbid doing to a rupee amount. Both are right about different things: **a pixel is not a figure
anybody reconciles.** So the conversion lives in exactly one file, `charts/plot.ts`, which exists
for geometry and never renders, and `analyticsDiscipline.test.ts` enforces the quarantine — no other
analytics file may call `Number`/`parseFloat`/`parseInt`, and no plot helper may appear inside JSX.
Every figure on screen is formatted from the server's own string through `formatINR`.

`toPlotValue` is also stricter than `Number`: `"1e3"`, `"0x10"`, `"Infinity"` and `"1,234"` all
become `null` (a gap) rather than a mark drawn somewhere absurd. And `null` stays `null` rather than
becoming zero — a day the restaurant was shut has no average bill, and a zero draws a line through
the floor of the chart, inventing the catastrophe the module exists to detect.

### Runs

| Target | Result |
|---|---|
| `make lint-web` | **0** |
| `make test-web` | **499 passed**, 64 files (was 463); **508 after the review pass**, measured rather than assumed |
| `vite build` | exit 0; analytics in its own 4.54 kB gzipped chunk |
| `validate_palette.js` light + dark | ALL CHECKS PASS, exit 0 |
| `make lint-api` | **0** — ruff, ruff format, mypy strict over 327 files |
| `make test-api` | **exit 0** — **1900 passed** in 1:06:18, coverage **95.59%** against the 95% floor |
| `make audit-docs` · `audit-guardrails` · `audit-deps` | **0 · 0 · 0** |

The gate was run as separate targets rather than one `make check`, because `check` no longer fits
in one invocation on this machine. **Exit codes were read, not the last lines** — `TEST_API_EXIT=0`
— which is the habit CLAUDE.md records having produced a false "clean" claim twice. The coverage
verdict and the exit code agree, which is the second half of that rule: `precision = 2` is what
stopped them disagreeing between ~94.5% and 95%.

### What chunk B did not do

No forecast (chunk D) and no action queue (chunk C); their metric-table rows are still deliberately
absent, because a formula written before its query is a guess. The dashboard latency budget
(criterion 10, 800 ms over 120 days of generated data) is **not yet measured** — it needs the M15
generator's 120-day dataset, and measuring it on the 30-day seed would be the kind of green result
that proves nothing.

---

## Chunk B — the review pass, and the four defects it found

Committed separately from the chunk so each fix carries its own reasoning. None of these were caught
by the tests that shipped with the chunk, which is the point of recording them: each names a class
of thing the tests could not see.

**1. `₹80,000.00` on every gridline.** Found by `dataviz`'s own last step — *render it and look at
it* — which is the one step a validator cannot do. Ticks round to clean numbers, and two decimals
repeated five times is noise that also eats the width the plot needs.

The distinction that makes the fix safe: **an axis tick is a number `niceTicks()` generated, not a
figure the server sent.** A gridline is a scale label and nobody reconciles one. The exact amount
still reaches the reader through the tooltip and the table, both formatted from the server's own
string. `formatINRAxis` carries that warning in its docstring and a test pins it —
`formatINRAxis('79999.50')` is `₹80,000` where `formatINR('79999.50')` is `₹79,999.50`: right for a
gridline, wrong for a bill.

**2. The current branch drilled through a full document load.** `window.location.assign` was used
for *every* branch, but only the cross-branch case needs it — that load is what carries the filter
across the token re-issue. The branch already in scope had nothing to re-issue and was taking the
expensive path for less than nothing: **the access token lives in a module variable, not in
storage, so a document load throws it away.** Observed directly while checking the screen in a
browser — a full navigation logged the session out.

The regression test observes a document load without performing one, by replacing `window.location`
with a stub whose `assign` is a spy, and it was verified by restoring the bug.

**3. The chart's keyboard controls were focusable but invisible.** The `sr-only` list gives the
chart a keyboard path, and a focusable element that stays clipped is *worse* than no control: a
sighted keyboard user tabs into somewhere they cannot see. Screen reader users were never affected,
because they navigate by list and heading rather than only by tab — **which is exactly why this
ships without anybody noticing.** `focus:not-sr-only` undoes the clipping on focus, the same way a
skip link does.

The same list offered a control for **every** bucket, including buckets with no trading: fifty-six
tab stops at the default day view, most of them offering to open bills that do not exist. Only
buckets with something in them get one now.

**4. Counts were not grouped.** Revenue read `₹1,20,000` while guests read `1200` beside it.

Worth recording for *how* it was fixed rather than what: **`analyticsDiscipline.test.ts` refused the
naive version**, because no analytics file outside `plot.ts` may call `Number()`. That rule fired
correctly. A formatter reviewed as a formatter is a different artefact from a `Number()` buried in a
screen, even though the two produce identical pixels — so `formatCount` went into `money.ts`, where
it says in its own docstring that a count is an integer and therefore has no precision to lose
(invariant 3 is about money).

### Verified in a browser, both modes

Chunk A and the chunk B tests both run headless. The screen was opened at `localhost:5173` as the
seeded owner and checked in the Warm and Dark themes. The indigo holds against the dark theme's 9%
ground exactly as the computed 4.08:1 predicted; the grid stays recessive in both. The tooltip was
checked live: hovering 5 Sept shows `₹73,899.12` while the axis beside it reads `₹80,000` — which is
the axis decision above, working as intended rather than merely argued.

---

## Chunk C — the fairness review, answered before the leakage card is written

**Decision 3, answered by the owner on 2026-09-20: a leakage card names the pattern and its rupee
figure, never the person; the drill-through opens the rows, which carry who.** The question was put
with all three options costed — name them, name nobody and drill to rows, or name nobody and
withhold the person column downstream. The owner chose the middle one. The third was rejected for a
reason worth keeping: M07's bill screen already shows who settled a bill, so withholding it here
would leave two screens disagreeing about the same recorded fact.

Spec §6: *"Anything naming a person goes through the fairness review first … the same ethics
questions answered in the build log before the screen is written."* This section is that answer. It
was written before the first line of chunk C, which is the only ordering that makes it a gate
rather than a justification.

### The one decision that makes the rest easy: **no card in this queue names a person**

The spec lists the leakage patterns as *"cancelled-after-KOT lines, reprints, unexplained comps,
discounts clustered by login and shift"* — and three of those four are phrased as *per-login*
figures. Clustering by login is the whole point of the pattern, and it is also precisely the thing
`docs/workload-fairness.md` was written to constrain.

**The queue shows the pattern and its rupee figure. It does not show who.** The reasons are not
squeamishness:

1. **`docs/waste-model.md` §4 and CLAUDE.md invariant 7 already say the number cannot carry the
   accusation.** A missed waste log and theft produce exactly the same unexplained figure.
   `VarianceReportScreen` was built on that rule — `reportDiscipline.test.ts` rule 4 refuses the
   words `employee`, `staff_id`, `reported_by`, `waiter` and `blame` anywhere near the unexplained
   figure — and an action queue that names somebody beside the same arithmetic would reintroduce,
   on a more prominent screen, exactly what that test forbids on a quieter one.
2. **Ethics question 5 — attribution is the weakest link — is unresolved *for this data*.** M17
   could answer it because every metric it scores carries its own `count` that a person can point
   at. A discount "clustered by login" carries no such handle: a shared till login, a captain
   entering another waiter's order, or a manager approving a comp on somebody else's screen all
   produce a cluster under a name that did not do it. M17's answer does not transfer, and the
   honest response to an unresolved attribution question is not to name anybody.
3. **Question 2 — punitive use is not ruled out — binds harder here than in M17.** M17's scores are
   read by three endpoints and nothing else. A card that said *"₹4,200 of comps, mostly Ravi"*
   beside a **Do it** button is a deduction waiting to be written, and the queue's own framing —
   one action, now — is the framing that makes it one.

**So the card names the pattern, the rupee figure and the window; the drill-through opens the
rows.** The rows are the bills, and a bill has always carried who settled it — that is the audit
trail M13 and M07 already built, reached deliberately by somebody who chose to look, rather than a
name pushed onto a dashboard next to a number and a button. **That difference is the whole review.**

### The eight questions, and which of them chunk C can even reach

M17 answered all eight (`docs/plan/m17-build-log.md`). Most do not apply to a queue that names
nobody; the three that still bite are recorded rather than waved through.

| # | Question | Chunk C |
|---|---|---|
| 1 | An employee cannot dispute a score | **Not reached.** No score, no person, nothing to dispute. The *rule* is disputable by anyone who sees the card — that is what **Not true** is for |
| 2 | Punitive use is not ruled out | **Binding.** No card names an individual, so no card can be used as evidence against one without somebody first opening the rows |
| 3 | "Top contributors" leaks the bottom in a small team | **Binding, and the reason for the rule above.** In a three-waiter shop, *"discounts cluster on one login"* names a person however carefully it is worded. There is no `MIN_TEAM_SIZE` that fixes a cluster of one |
| 4 | Attendance can score protected reasons | Not reached — no attendance input |
| 5 | Attribution is the weakest link | **Binding, and unresolved for this data.** See reason 2 above |
| 6 | Visible is not understandable | Applies to the card text, not to a score: every card is a sentence with a rupee figure, and Hindi/Marathi remain **unshipped** here exactly as in M17 |
| 7 | The legal basis is unverified | Researched at M17: DPDP §7(i) makes employment purposes a legitimate use, recorded in `docs/compliance-rules.md` with both caveats. A queue naming nobody does not process employee personal data at all, so it does not rely on that finding |
| 8 | There is no stop rule | **Still a gap**, named here rather than ticked. It was named as a gap in M17 too. The queue's own tuning report is not a stop rule |

### What *Not true* does, and the one thing it must not do

**Not true** tunes the rule and the tuning is published monthly — the spec's phrase is that the
owner should *"see the product learning rather than being told it does"*.

It must not become a per-person suppression. A rule dismissed as untrue for a reason
(*"we comp staff meals on Tuesdays"*) is a fact about the restaurant; the same dismissal recorded
against a login would be a quiet way of building the per-person view this review just refused.
**The dismissal records the rule, the window and the reason — never a subject.**

### Chunk C's metric table, written before its queries

Acceptance criterion 2: every metric gets its four-column row before it gets a query, because a
formula written after the fact is a description of whatever the query happened to do.

**A card with no rupee figure does not go in the queue** (spec §5) — that is what stops it filling
with advice. Every row below therefore ends in rupees, and a pattern that cannot be priced is not a
card.

| Metric | Source tables | Formula | Render |
|---|---|---|---|
| `comp_value` | `order_discount` ⋈ `order` ⋈ `invoice` | `SUM(amount)` where `type = 'comp'` and the invoice is not cancelled, over the window's business dates | Card, ₹. Never charted |
| `authorised_headroom` | `order_discount` | `SUM(authorised_amount)` where `type = 'comp'`, beside `comp_value`. **Not** `amount − authorised_amount` — see below | Card, ₹, as context beneath the figure |
| `cancelled_after_kot_value` | `kot_ticket_line` ⋈ `order_line` | `SUM(order_line.line_total)` where the order line is `cancelled` **and** its KOT line reached `preparing` or beyond — food that was cooked and then binned | Card, ₹ |
| `remake_value` | `kot_ticket_line` ⋈ `order_line` | `SUM(line_total)` where `kot_ticket_line.status = 'remake'`, grouped by `remake_reason` | Card, ₹ |
| `unexplained_value` | derived | Already defined in chunk A's table. M13: `_variance_line`. **The queue reuses it rather than recomputing** — that is what criterion 2 is for | Card, ₹. Already the variance report's headline |

### The card that will not be built, and why that is a finding rather than a gap

The obvious leakage card is *"discounts taken above what was approved"*. **It would report ₹0
forever.** Verified against the running database rather than recalled from the schema doc:

    ck_order_discount_within_authorised  CHECK ((amount <= authorised_amount))

`amount > authorised_amount` is **unrepresentable**. A card for it is theatre — a permanently green
number that teaches an owner the queue is decorative, which is the one thing a queue of four cards
cannot afford.

**So the question is turned around.** The interesting figure is not whether somebody exceeded an
authorisation — the database refuses that — but whether the *authorisation itself* was generous.
That is `authorised_amount`, it is very much representable, and it is a question about a policy
rather than about a person, which is what decision 3 asks of every card here.

This is the same shape of finding as M17's freeze test, which could not void a settled order
because invariant 6 forbids it: **a constraint that refuses the test is the constraint doing its
job, and the test is better for being rewritten around it.**
