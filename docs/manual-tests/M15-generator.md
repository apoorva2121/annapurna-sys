# M15 · The 120-Day Generator — Manual Test

**Module:** M15 · **Built:** 2026-09-19 · **Gate:** `make check`. The runs and their results are in
`docs/plan/m15-build-log.md`.

Run `make seed` first — **this is the first module where that takes minutes rather than seconds**,
because it is generating four months of trading. Then `make dev`, and sign in as
**owner@spicegarden.test**.

**What you are testing is not the data. It is whether the reports find things.**

Every screen in this product has been built against fixtures designed to break its arithmetic. That
proves the sums. It proves nothing about whether an owner opening the dish report on a Tuesday
morning learns anything. This pass is the first time the product is pointed at four months of a
restaurant that has fourteen specific things wrong with it, and the question in every section is the
same: **would you have found this yourself?**

The fourteen are listed in `docs/seed-data.md`. **Read that table before you start.** You are
looking for planted anomalies, and knowing what was planted is the only way to tell "the report
found it" from "the report showed me something and I decided it was interesting".

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · the shape** | Verified: volumes, the weekday curve, the business day, gapless invoices |
| **B · the fourteen** | Verified by `tests/test_planted_signals.py` — each fails if its planter is removed. **B15 is the question** |
| **C · do the reports find them** | Partly verified. **This is the section that matters** |
| **D · the gap** | Verified: theoretical ~25.7%, actual ~32%. **D3 wants your judgement** |
| **E · determinism** | Verified: same seed, same window, same figures |
| **F · exploratory** | Not run. Yours |

Short of time? Do **C**, then **D3**.

---

## A · The shape of four months

| # | Step | Expect |
|---|---|---|
| A1 | Open **Reports → Sales** and set the range to the last 30 days | A row per day. Friday, Saturday and Sunday are roughly 1.7× a weekday; Tuesday is the quietest |
| A2 | Look at the last week of any month against the first three days | A dip at the end and a bump at the start. That is the salary cycle, and it is real |
| A3 | Find a day in July or August | Quieter. Monsoon in Pune |
| A4 | Add up a month's revenue | Around ₹15.5 lakh. If it is wildly different, the demand model has drifted and I need to know |
| A5 | Sort the dish report by units | The top eight dishes are roughly 55% of covers. A long tail, not a flat list |
| A6 | Look at any bill settled after midnight | Its business day is the day it **started**. A 1:30am table belongs to the night before |

---

## B · The fourteen, one at a time

Each of these is planted. The test suite asserts each one exists; what you are judging is whether
it is *visible to a person*.

| # | Signal | Where to look |
|---|---|---|
| B1 | Makhani gravy over-produced on Tue/Wed | **Reports → Waste**, filter the range to a fortnight. Prep should be the biggest stage |
| B2 | Paneer over-ordered on Mondays, expires | **Stock on hand** → the expiring list |
| B3 | A supplier short-delivers | Deliveries vary in size against what was used |
| B4 | Tandoor slows 40% at the Fri/Sat peak | **Kitchen** ticket times on a Friday evening against the same station at lunch |
| B5 | Ratings fall in that same window | **Today**, on a Saturday — the average rating is lower |
| B6 | One waiter's errors, dinner only | Service-stage waste, concentrated on one person and one shift |
| B7 | Chilli Paneer sells well and earns nothing | **Reports → Dish performance**: it should be a **plough-horse** |
| B8 | Malai Kofta: 4.7 rating, few orders | The same report: a **hidden gem** |
| B9 | Butter Chicken uses 12% more gravy | **Reports → Food-cost variance**: unexplained variance on the gravy |
| B10 | Staff meals ≈ ₹18k/month | Present as their own movement type, and **not** in the waste report |
| B11 | Comps ≈ ₹9k/month, 70% one manager | Present, and attributable |
| B12 | Six regulars stop after week 14 | Customer screens |
| B13 | Tomato spikes 2.4× for three weeks | Dish costs rise in that window and fall back |
| B14 | Eight biryani complaints in one week | **Complaints**, filtered to that week |
| B15 | **The question** | Which of these fourteen did you find *without* the list? Any you could not find is a report that needs work, and that is the most useful thing this pass produces |

---

## C · Do the reports find them — **this is the module**

Twenty minutes, no steps. Open the reports as an owner who has never seen this list, and answer in
writing:

| # | Question |
|---|---|
| C1 | Open **Dish performance**. Without looking at the signal table: which three dishes would you change something about, and what? |
| C2 | Open **Food-cost variance**. What is the biggest unexplained line, and would you know what to do about it on Monday? |
| C3 | Open **Waste**. Which stage would you attack first, and who would you talk to? |
| C4 | Now read the signal table. How many of your answers match a planted signal? |

**C4 is the number this module is judged by.** If the reports surfaced the planted problems, the
analytics work is doing its job. If they did not, the data is fine and the reports need another
pass — and it is far better to learn that here than from a restaurant that has paid for it.

---

## D · The gap that is the product

| # | Step | Expect |
|---|---|---|
| D1 | `python seed/validate.py` | Blended **theoretical** food cost around 25.7% |
| D2 | **Reports → Food-cost variance** over 30 days: actual against theoretical | Actual lands around 32%. The difference is the ~6 points of waste, drift, comps and staff meals |
| D3 | **The judgement.** On ₹15.5 lakh a month that gap is roughly ₹95,000 | Is that a number you would pay for software to find? If the answer is no, say so — that is the product's central claim and it should be tested on you before it is tested on a customer |

---

## E · Determinism

| # | Step | Expect |
|---|---|---|
| E1 | Note a month's revenue figure | — |
| E2 | `make seed` again | It says history is already present and changes nothing |
| E3 | Wipe and re-seed with the same end date | **The same figures.** Different numbers mean the generator has stopped being deterministic, which makes every future report regression invisible |

---

## F · Exploratory charter — 20 minutes

**Charter:** *Find something in this data that looks wrong and is not planted.*

Anything you find is either a generator bug or a real product bug, and both are worth an hour. Look
especially at: a day with no trading; the first and last day of the window; an ingredient that never
appears in a recipe; a bill with one line; the busiest Saturday.

**Rule 4 of `docs/seed-data.md`:** *"an undocumented anomaly is indistinguishable from a generator
bug."* If you find an anomaly that is not in the table, it is one of the two and I need to know
which.
