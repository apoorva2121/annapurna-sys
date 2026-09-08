# Workload Fairness & Recognition

The ask: measure how much each employee actually does, so the owner can see that one waiter is
handling far more than another, reward the people carrying the load, and keep morale high.

This is a good feature and a genuinely common injustice in restaurants — senior staff take the good
sections, some people coast, and the hardest worker often goes unnoticed. But it is also the single
easiest feature in this product to build **badly**, in a way that lowers morale instead of raising
it. This document is mostly about how not to do that.

---

## Two risks, stated once

**1. Any metric that determines pay gets gamed.** Score waiters on covers served and they will rush
tables, push upsells, dodge difficult customers, and quietly compete for large parties. The metric
goes up; the restaurant gets worse. This is not cynicism about your staff — it is what happens to
every measured workforce, everywhere.

**2. Individual competition destroys teamwork.** Service is a team sport. If helping a colleague
earns nothing and serving your own table earns points, people stop helping. A restaurant where
nobody covers for anybody is worse than one with no scoring at all.

Both are design problems with design solutions, below. Neither is a reason not to build it.

---

## The reframe that makes this work

**The primary output is not a ranking of employees. It is a diagnosis of unfair distribution.**

> Friday dinner: Suresh handled **34%** of covers, Ravi handled **11%**.
> An even split across 5 waiters would be 20% each.
> Ravi's section (Terrace) turned 1.4× slower — it is the section, not the waiter.

That finding fixes the injustice *at its source* — by rebalancing sections and assignments — which
is worth more than any bonus. The reward layer sits on top of it, not instead of it.

Lead the product with fairness. Recognition follows.

---

## Design principles

### 1. Normalise everything. Never rank on raw counts.
Raw totals measure the shift, not the person. Every metric is **per hour worked** or **per cover in
their section**, and compared only against like-for-like shifts. A waiter on Tuesday lunch and one
on Saturday dinner are not comparable and the system must never pretend they are.

### 2. Only score what the employee controls.
Split metrics into two classes, and score only the first:

| Controllable — scored | Not controllable — shown as context only |
|---|---|
| Order accuracy | Kitchen prep delays |
| Seat-to-order time | Section quality and footfall |
| Bill-to-settle time | Menu availability |
| Attendance and punctuality | Table size assigned |
| Assists given to other sections | Weather, festivals, staffing gaps |

A waiter penalised for the tandoor running slow will correctly conclude the system is stupid, and
then ignore all of it.

### 3. Volume never stands alone.
Every volume metric is paired with a quality metric. Covers served is always shown beside accuracy
and customer rating. **A high-volume, high-error waiter must score below a steady, accurate one** —
otherwise the system explicitly rewards rushing.

### 4. Reward the team player, structurally.
An **assist** — serving a table in a section assigned to someone else — is *derived automatically*
from the order and the shift's section assignment. Nobody has to log it, so it cannot be forgotten,
and generosity shows up in the numbers instead of costing the giver points.

Alongside individual points, a **shift team score** exists so a good night lifts everyone.

### 5. The employee sees their own numbers. Always.
This is the decision that determines whether the feature raises or destroys morale. A score you
cannot see is surveillance. The same score, visible, with the inputs shown, is feedback.

Every employee sees their own metrics, their own points, and exactly how the points were computed —
from their first day, not after a dispute.

### 6. Never publish a bottom ranking.
Top contributors are shown to the team. Low performers are shown **only to their manager**, framed
as a coaching prompt, never as a public list. Public shaming produces resentment and turnover.

### 7. The manager can add context, and the human decides.
A manager annotates a period — *"was training the new hire"*, *"section closed for repairs"*,
*"covered two shifts for Anil"* — and that note travels with the score. **Data informs the reward
decision; it never makes it.** No automatic payout, ever.

### 8. The owner sets the weights.
Different restaurants value different things. The scoring formula's weights are configuration, set
by the owner, visible to everyone, and changes are audit-logged — because "who changed the weight
that decided my bonus" is a question that will be asked.

---

## What gets measured

**Waiters / captains** — covers per hour, orders per hour, order accuracy (errors per 100 lines),
seat-to-order, bill-to-settle, order-linked customer rating, attributable complaints, table turn
rate, assists given, attendance and punctuality, revenue per cover (context only — see §3).

**Kitchen** — items prepared per hour, prep time vs the dish standard (normalised per dish, so a
biryani cook is not compared to a naan cook), remake rate, attributable waste, station load handled,
food-quality complaints, hygiene checklist completion.

**All staff** — attendance, punctuality, shifts covered for others, tasks completed on time.

Every one of these already exists in the schema. This module computes and freezes them; it invents
no new measurement.

---

## Points and rewards

```
period (week or month)
  → per employee: normalised metrics
  → weighted by the owner's scheme
  → points, FROZEN when the period is published
  → manager review + notes
  → award granted (or not) by a human
```

**Award types** are configurable and need not be money: cash bonus, extra leave, preferred shift
choice, a meal, or simple public recognition. In Indian restaurants, non-cash recognition often
lands harder than a small bonus — "Employee of the Month" on a board by the kitchen door is cheap
and works.

**Suggested starting weights** (owner-adjustable): accuracy 25%, customer rating 20%, workload
volume 20%, service speed 15%, attendance 10%, assists 10%. Note that volume is only a fifth — that
ratio is deliberate and is what keeps §3 honest.

---

## Why scores are frozen

Once a bonus has been paid against a score, that score must never move. A later data correction — a
voided order, a re-attributed complaint, an edited recipe — would otherwise silently rewrite last
month's payroll basis, and an employee who screenshots their score will find it changed.

So a published `performance_period` stores its computed metrics and points as **frozen values**,
exactly as an order freezes `theoretical_food_cost` at settlement (ADR 0004). Same principle, same
reason.

This is also why performance gets tables at all, when `docs/schema.md` deliberately eliminated
`waiter_performance` and `chef_performance` as "queries, not tables". That elimination stands: the
**live** metrics remain queries. What is stored here is only what cannot be derived — a frozen
snapshot, a manager's note, an award that was granted, and the scheme configuration.

---

## What we deliberately do not build

| Not built | Why |
|---|---|
| Automatic payouts from a score | A number must never pay a person. A human authorises, with context. |
| Public leaderboards including the bottom | Produces resentment and turnover, not effort. |
| Peer rating of colleagues | Becomes a popularity contest and a bullying vector. |
| Real-time individual tracking | Reads as surveillance. Periods are the unit, not minutes. |
| Cross-restaurant employee ranking | Different sites, different conditions. Meaningless comparison. |
| Scoring on tips | Tips track section quality and luck more than effort. Shown as context only. |

---

## Privacy and law

Employee performance data is personal data under **DPDP 2023**. It follows the same rules as
customer data in `docs/security.md`: purpose limitation, retention limits, and the employee's right
of access — which is satisfied by design here, since they can already see everything about
themselves.

Wage and bonus figures are gated behind their own permission, separate from operational performance
data, so a manager can coach on service quality without seeing compensation.

---

## How we will know it worked

Not by whether scores go up — scores going up is exactly what gaming looks like. Instead:

- **Workload spread narrows** — the gap between the busiest and least busy waiter shrinks
- **Accuracy holds or improves** while volume rises (if accuracy falls, §3 has failed and the
  weights are wrong)
- **Assists increase** — people are still helping each other
- **Retention improves** — the real measure, and the one that pays for the feature

If assists fall or accuracy drops after launch, the scheme is doing harm. Change the weights.
