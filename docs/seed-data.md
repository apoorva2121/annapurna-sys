# Seed Data — the synthetic restaurant

No real restaurant data exists yet, and Indian restaurants keep few records
(`docs/onboarding-cold-start.md`), so **we build and demo entirely against a synthetic restaurant**
until real data arrives. It has to be good enough that a real restaurateur watching the demo
recognises their own business.

## The restaurant

**Spice Garden** — Pune, North Indian + Chinese-Indian, the most common independent format in India.

A **second organization, Tandoor House**, exists on purpose with a single manager. Every
tenant-isolation test needs a second tenant to fail against, and a bug that only appears with two
tenants is the worst bug this product can have.

| | |
|---|---|
| Seats | 48 across 14 tables, 2 zones (AC hall, terrace) |
| Service | Lunch 12:00–15:30, Dinner 19:00–23:30 |
| Business day start | 05:00 IST |
| Covers | ~110/day weekday, ~190/day Fri–Sun |
| Avg order value | ₹640 dine-in, ₹410 takeaway |
| Monthly revenue | ~₹15.5 lakh |
| Staff | 17 at Spice Garden: owner, admin, manager, chef, 4 kitchen, 5 waiters, store, 2 cleaners, accountant. **4 have no login** — an employee without a user account must work (ADR 0007). |
| Menu | 32 items / 36 variants, 6 categories |
| Ingredients | 62 |
| Preparations | 12 base gravies and preps |

Recipe-only (**theoretical**) food cost across the sales mix works out at **25.7%** — verified by
`seed/validate.py`, not asserted. The generator then makes **actual** food cost land at ~32%, because
of planted waste, portion drift, comps and staff meals.

**That ~6-point gap is the entire product.** On ₹15.5 lakh/month it is roughly ₹95,000 — which is
what the software is ultimately selling back to the owner.

## Generation rules

**Demand shape** — this is what makes data feel real rather than uniform:

- Weekday/weekend: Fri–Sun ≈ 1.7× Mon–Thu. Tuesday is the trough.
- Intraday: lunch peak 13:00–14:00, dinner peak 20:30–22:00. Dinner ≈ 2.2× lunch revenue.
- Monthly: a dip in the last week (salary cycle), a bump on the 1st–3rd.
- Seasonality: mild dip in monsoon (Jul–Aug), lift around festivals.
- Dish mix follows a long tail — top 8 dishes are ~55% of covers, bottom 12 are ~6%.
- Party size: 60% of dine-in tables are 2–3 covers.

**Volume** — 120 days of history ending today. ~14,000 orders, ~38,000 order lines.

**Cost movement** — ingredient prices drift, and two move sharply: tomato spikes 2.4× for three
weeks (this happens every year and wrecks gravy cost), onion drifts up 30% over the period.

## Planted signals — the most important part

Random data has nothing to find, so every analytics feature would look broken. Each anomaly below is
deliberately planted, and **each one is the acceptance test for a feature.**

| # | Planted signal | Feature it proves |
|---|---|---|
| 1 | Makhani gravy over-produced ~35% every Tue/Wed; discarded at close | Prep sheet / prep waste (`waste-model.md` §3) |
| 2 | Paneer expires ~2×/month — over-ordered Mondays, shelf life 4 days | FEFO + expiry alerts |
| 3 | Supplier "Fresh Farms" short-delivers 3–5% on ~40% of deliveries | Three-way receiving variance |
| 4 | Tandoor prep time rises 40% at 20:30–22:00 Fri/Sat | Kitchen bottleneck detection (§5) |
| 5 | Ratings drop to ~3.3 in that same window | CX↔ops correlation (`customer-experience.md`) |
| 6 | Waiter "Suresh" — 2.1× the accuracy errors of peers, only on dinner shifts | Staff performance, systemic vs individual |
| 7 | Chilli Paneer: high volume, 46% food cost — sells well, earns nothing | Menu engineering, "popular but unprofitable" |
| 8 | Malai Kofta: 4.7 rating, 11 orders/month | "Hidden Gems" (§6) |
| 9 | Butter Chicken consumes 12% more gravy than recipe | Portion drift / theoretical-vs-actual |
| 10 | Staff meals ≈ ₹18k/month, untracked before separation | `staff_meal` movement type |
| 11 | Comps ≈ ₹9k/month, 70% authorised by one manager | Leakage detection |
| 12 | 6 regulars (5+ visits) stop coming after week 14 | Churn / win-back signal |
| 13 | Tomato price spike raises gravy cost 22% for 3 weeks | Cost-change alerting, supplier trends |
| 14 | Biryani: 8 complaints in one week, all dinner peak | Complaint clustering → §26 AI advisor |

Signal 14 is the vision doc's own §26 example. When the AI advisor is built, it must reconstruct
that explanation from this data unaided. That is the Phase 3 acceptance test, planted now.

## Implementation

- **Static content** — hand-authored, schema-independent, already written. This is the slow part
  and it is done:
  `seed/ingredients.yaml` (61) · `seed/preparations.yaml` (11) · `seed/menu.yaml` (32 items) ·
  `seed/organization.yaml` (2 orgs, 3 restaurants, 53 permissions, 9 roles, 19 employees) ·
  `seed/operations.yaml` (14 tables, 3 stations, 2 tax groups, 2 shifts, 5 suppliers,
  12 wastage reasons, 4 modifier groups, the M17 incentive scheme) ·
  `seed/tandoor-house.yaml` (the second tenant — 49 menu rows over 47 library dishes, 8 tables,
  3 stations; **data only, no loader reads it yet** — see the STATUS block in that file)
- **Validator** — `seed/validate.py`. Checks every recipe reference resolves, that preparation
  nesting has no cycles and stays within depth 3, and prints per-dish and blended food cost. Run it
  after any edit to the YAML; it runs in CI. It has already caught three errors in this data.
  `seed/validate_tandoor_house.py` does the same for the second tenant and additionally proves
  every dish cooks at a station that restaurant actually has — it caught four orphaned dishes and a
  non-existent variant on its first run.
- **Generator** — `backend/app/seed/generate.py`, written in week 1 once the schema exists.
  Deterministic (fixed seed) so every developer and every demo sees identical numbers, and so a
  regression in an analytics query is visible as a changed figure.
- `make seed` wipes and regenerates. `make seed-small` does 7 days for fast tests.

### What the generator actually plants, and the three that differ from the table

Written 2026-09-19, when `backend/app/seed/generate.py` was built. Rule 4 below says an
undocumented anomaly is indistinguishable from a generator bug; the same is true of a documented one
that is planted differently from how it reads.

All fourteen are planted, and `backend/tests/test_planted_signals.py` fails when any planter is
removed. Three are shaped differently from the row above:

**Signal 3 — the short delivery** is planted as a *batch smaller than what was ordered*, not as a
goods-receipt variance against a purchase order. The generator writes no purchase orders: M06's
three-way match compares `quantity_ordered` on a PO line with what arrived, and generating four
months of purchase orders to carry one signal would be a second procurement history nobody reads.
What the ledger shows is the thing a restaurant without paperwork actually sees — less stock than
the money paid for. **The three-way match itself is still tested by M06's own fixtures.**

**Signal 11 — the comp concentration** is planted on `stock_movement.actor_employee_id` rather than
as an authorisation record, because a comp in this schema is a `complimentary` movement and not a
document. The concentration is visible where it matters: 70% of the comped food carries one name.

**Signal 6 — the waiter's errors** are planted as service-stage waste events on that person's
dinner bills, at about twice everybody else's rate. Not as a score: `docs/workload-fairness.md` and
ADR 0011 are emphatic that measuring people needs guardrails this module does not have, so the
generator plants the fact and M17 is where anybody is measured by it.

**And one thing the table does not say:** the generator writes rows rather than driving the
services, because `OrderService.create` and `SettlementService.settle` take no clock — they read
`datetime.now(UTC)`, correctly, for a real bill. Driving them fourteen thousand times would produce
fourteen thousand bills all dated today. `docs/plan/m15-build-log.md` carries the argument.


## Rules

1. **Deterministic.** Same seed, same data, always.
2. **Never in production.** Seeded orgs carry `is_demo = true` and are excluded from all reporting.
3. **Plausible, not perfect.** Include missing feedback, a forgotten stock count, two voided orders,
   a day the waste log was skipped. Perfectly clean data hides bugs that real data will find.
4. **Signals stay documented.** Adding a planted anomaly means adding a row to the table above.
   An undocumented anomaly is indistinguishable from a generator bug.
