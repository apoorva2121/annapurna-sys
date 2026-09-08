# 0011 — Performance scores are frozen, controllable, and visible to the employee

**Status:** Accepted · 2026-09-08 · Qualifies the "performance is a query, not a table" elimination
in `docs/schema.md`

## Context
The owner wants to see who is actually carrying the workload — one waiter handling far more requests
than another — and reward accordingly, to raise morale and give people the incentive they deserve.

`docs/schema.md` deliberately eliminated `waiter_performance` and `chef_performance` on the grounds
that performance figures are queries, not tables, and storing them creates a second source of truth
that silently drifts. That reasoning still holds for **live** metrics. It does not hold once a
number has been used to pay somebody.

Three decisions follow, and each is as much an ethical commitment as a technical one — a
measurement system aimed at morale can destroy morale if built carelessly
(`docs/workload-fairness.md`).

## Decision

### 1. Live metrics stay queries. Published periods are frozen.
A `performance_period` moves `draft → published → finalised`. While draft, every metric is computed
live from orders, KOT timestamps, feedback and shifts — no stored duplicates. On **publish**, the
computed metrics and points are written into `performance_score` as frozen values and never
recomputed.

The reason is the same one that freezes `theoretical_food_cost` on a settled order (ADR 0004): a
later correction — a voided order, a re-attributed complaint, an edited recipe — must not silently
rewrite the basis on which a bonus was already paid. An employee who screenshots their score must
find that score unchanged next month.

Only four things are therefore stored that cannot be derived: the frozen snapshot, the manager's
note, the award that was granted, and the scheme configuration. Everything else stays a query.

### 2. Only controllable metrics carry weight.
Each metric is classified `controllable` or `context`. Only `controllable` metrics contribute
points; `context` metrics are displayed beside them and contribute zero. Kitchen delays, section
footfall, table size and tips are context — a waiter penalised for the tandoor running slow will
correctly conclude the system is stupid and ignore all of it.

Every metric is normalised **per hour worked** or **per cover in section**, and compared only within
like-for-like shift types. Raw counts are never ranked.

Volume metrics never stand alone: a volume weight may not exceed the combined weight of the accuracy
and rating metrics, enforced when a scheme is saved. Without that rule the system pays people to
rush, which is the opposite of the goal.

### 3. Every employee can always see their own score and its inputs.
`performance.view.own` is granted to every role by default and cannot be removed by configuration.

A score an employee cannot see is surveillance and lowers morale; the same score, visible with its
inputs shown, is feedback and raises it. This is the decision that determines which of the two this
feature becomes, so it is a structural guarantee rather than a setting.

Correspondingly, **no endpoint returns a bottom-ranked list.** Top contributors are visible to the
team; low performers are visible only to their manager, as a coaching prompt.

### 4. No automatic payouts.
Points never trigger money. A human with `recognition.award` grants an award, with the manager's
context note attached, and the grant is audit-logged. Data informs the decision; it never makes it.

## Alternatives rejected
- **Recompute scores on demand, always** — simplest, and it silently rewrites payroll history.
- **Store live metrics continuously** — the drift problem `docs/schema.md` already rejected.
- **Rank on raw totals** — measures the shift, not the person, and would make the feature actively
  unfair, which is the exact injustice it exists to fix.
- **Peer rating** — becomes a popularity contest and a bullying vector.
- **Automatic bonus on threshold** — removes the manager's context and guarantees gaming.

## Consequences
- Five new tables and one new column (`shift_assignment.dining_area_id`), taking the schema to 63.
- Assists are **derived**, not logged: an order taken by employee X at a table in a section assigned
  to employee Y is an assist. No `assist_event` table, and nobody has to remember to record helping
  a colleague — which is what makes the team-player incentive actually work.
- Publishing a period is an irreversible, audit-logged, permission-gated action. It needs a
  confirmation step in the UI naming what is about to be frozen.
- The scheme weight validator (volume ≤ accuracy + rating) is a unit-tested business rule, not a
  guideline.
