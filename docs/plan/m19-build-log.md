# M19 · Owner Analytics — build log

Spec: `docs/modules/M19-analytics-spec.md`. Branch: `feat/m11-communication` — see
§"Why this is not on `feat/m19-analytics`" below.

| Chunk | What | State |
|---|---|---|
| A | Trends: series endpoints, the metric table, the org decision implemented | in progress |
| B | The charts, code-split, bundle test, drill-through | not started |
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
