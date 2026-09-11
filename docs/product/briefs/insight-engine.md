# Build brief · `insight-engine` — the modelling service

**Status: brief, not scope.** Written 2026-09-11. Third of the pre-data packages, and the largest.

---

## The reframe, and why it is not pedantry

The request was: a module that consumes whatever data it is given, engineers features, removes
outliers, builds models and returns insights.

**Schema-agnostic AutoML is the wrong shape for this product, and building it would produce
something that looks impressive and cannot be trusted.** Five specific reasons, each of which is a
real defect rather than a preference:

1. **The schema is known.** `docs/schema.md` documents every column. "Works on any data" solves a
   problem this product does not have, and solves it worse than a pipeline that knows the schema.

2. **A generic pipeline leaks across the business day.** A standard time-series split on
   `created_at` puts 01:30 Tuesday into Tuesday. This product's day starts at 05:00 (ADR 0004), so
   that row belongs to Monday. Every metric would be quietly optimistic and nothing downstream could
   detect it — the exact failure mode `business_day.py` exists to prevent.

3. **A generic pipeline casts money to float.** Invariant 3 forbids it. A model reading
   `NUMERIC(12,2)` into float64 is how a rupee figure stops reconciling.

4. **A generic pipeline would train across tenants.** That is a tenant-isolation breach in
   statistical form: restaurant A's demand shaping restaurant B's forecast. No row is copied, so no
   isolation test catches it, and it violates invariant 1 as surely as a missing `WHERE` clause.
   Cross-tenant learning may be *desirable* later — pooled priors are how cold start is solved — but
   it must be a deliberate, disclosed, opt-in design decision, never an accident of the default.

5. **A generic outlier remover deletes this product's most valuable rows.** In restaurant data an
   outlier is almost always a real event: a festival, a power cut, a wedding party, a cricket final.
   Removing it destroys the signal the owner most wants explained. And `docs/waste-model.md` is
   explicit that untracked staff meals look exactly like theft — a naive anomaly detector will
   accuse honest people, which is worse than saying nothing.

**The shape that is right: a contract-based, invariant-aware pipeline that is self-sustaining across
*tenants and time*, not across arbitrary schemas.** It accepts any data satisfying a declared
feature contract — which keeps it reusable and testable — while enforcing this product's rules.

---

## The two components that actually matter

Everyone builds the model ladder. Almost nobody builds these two, and they are what make the thing
usable on day one of a tenant's life rather than on day ninety.

### 1 · The readiness gate — deciding whether to model at all

Every new restaurant starts with zero history, and **that is the most common state a tenant is ever
in**. The correct output then is not a prediction. It is:

> *"Not yet. Dish-level demand needs about 60 business days; you have 14. Ingredient requirement is
> available now — it needs recipes, which you have. Stock-out prediction is blocked: the ledger has
> received no purchases in 9 days."*

That last line is the product working. It detects that the daily habit has lapsed — the thing
`docs/onboarding-cold-start.md` calls "the daily habit the whole system depends on" — and says so,
instead of forecasting from a ledger nobody is feeding.

A readiness verdict per use case: `ready` / `degraded` (with what is missing) / `blocked` (with why).
This is what makes the engine self-sustaining: it degrades honestly instead of producing confident
output from insufficient input.

### 2 · The refusal layer

Hard rules the engine enforces regardless of what a caller asks for:

- **never trains across tenants** unless a pooled prior is explicitly requested and disclosed in the
  output
- **never returns an insight below a confidence floor** — silence beats a plausible wrong number
- **never produces an individual-level employee prediction.** M17 and ADR 0011 exist because a score
  an employee cannot see is surveillance. A *predictive* score about a named person — "likely to
  underperform" — is a category this product does not enter. Workload *distribution* is a fairness
  view, not a model output
- **never emits an accusation.** Variance attribution ranks *causes*, and "staff meals not booked"
  must be ranked before "theft" whenever both fit, because one of them is usually true and the other
  ends someone's employment

Both components are testable now, with no data, and both are where the value is.

---

## The scenarios, ranked

Each with the data it needs and when that data exists.

| # | Scenario | Needs | Available | Verdict |
|---|---|---|---|---|
| 1 | **Ingredient requirement** from forecast demand × recipes | dish demand + recipes | M04 + #2 | **Highest value per unit of difficulty.** Mostly deterministic arithmetic once #2 exists — the ML surface is small and the output is a purchase order |
| 2 | **Dish-level demand** | ~60 business days of orders | M07 + 2 months | The ML core. Long-tail dishes are sparse — needs hierarchical pooling across the menu, not a model per dish |
| 3 | **Daily covers / revenue** | ~60 business days | M07 + 2 months | Easier than #2 and the base it rests on. Festival blindness is the failure mode; `indian-demand-calendar` is the fix |
| 4 | **Stock-out date** | ledger + consumption rate | M05 + fed ledger | **Deterministic plus an uncertainty band, not a model.** Highest owner-perceived value for the least machinery |
| 5 | **Variance attribution** | purchases, counts, recipes, waste | M05/M06/M09 | The product's actual promise. Attribution, not prediction. See the refusal layer |
| 6 | **Waste prediction** (prep over-production) | waste logs | M09 + history | Real money, and the first saving most restaurants see |
| 7 | **Staffing by shift** | #2/#3 + service times | M12 + M08 | Derived, later |
| 8 | **Repeat / churn** | guest identity | M10 | DPDP-sensitive. Consent before modelling, not after |
| 9 | **Transaction anomaly** (voids, discounts, cash) | orders | M07 | Powerful and dangerous. Accusation risk; ships behind the refusal layer or not at all |

**Two things worth noticing.** #1 and #4 — arguably the two most valuable outputs — are *not machine
learning*. They are arithmetic over a correct ledger plus an uncertainty band. The ML surface is
smaller than it first appears, which is good news: the expensive, fragile part is narrower than the
valuable part.

---

## Architecture

```
feature contracts  →  readiness gate  →  feature engineering  →  model ladder  →  evaluation  →  insight  →  refusal layer
```

- **Feature contracts.** Each use case declares what it needs: `daily_demand` requires
  `(business_date, restaurant_id, item_id, quantity)`. Any source satisfying the contract works —
  this app's tables today, a different product's tomorrow. That is what "plug and play" means here,
  and it is the version that is safe.
- **Feature engineering is declared, not discovered.** Lags, rolling windows, calendar joins from
  `indian-demand-calendar`. Automatic feature synthesis on 60 rows finds noise and calls it signal.
- **Outliers are labelled, never removed.** An outlier row gets an explanation attempt — festival,
  fixture, weather, logged closure — and is reported. "Last Tuesday was 3× normal, and it was the
  IPL final" is an insight. Deleting it and smoothing the line is destroying one.
- **The model ladder is short and enforced.** Seasonal naive → day-of-week mean → EWMA → gradient
  boosting. **A model ships only if it beats the baseline by a stated margin on a proper backtest;
  otherwise the baseline ships.** Most AutoML has no such rule, which is why so much of it is a
  worse mean.
- **Evaluation** is the `forecast-eval` harness: splits that respect `business_date`, and metrics in
  rupees with asymmetric costs — over-prep wastes food, under-prep loses a sale, and they are not
  the same number.
- **Insight generation** is mostly not ML. It is turning a number into a sentence with a cause and a
  rupee figure. "₹8,400 last month, mostly paneer, on Tuesdays and Fridays when one supplier
  delivers" is what an owner acts on; "variance 12%" is what they stop reading.

## Boundaries

As with the other packages: **never imports `app.*`**, no database access, no network at runtime,
`Decimal` for anything monetary, own tests and version. It receives dataframes satisfying a contract
and returns plain data. The application maps its tables to contracts; the engine never knows the ORM
exists.

## What is buildable now, with no data

1. **the feature contracts** — from `docs/schema.md`, which is written
2. **the readiness gate** — pure logic over data availability, fully testable with synthetic inputs
3. **the refusal layer** — pure rules, and the most important thing here to get right
4. **the evaluation harness** — including the `business_date` split, which is the leak nobody catches
5. **the model ladder and baselines** — baselines need no training
6. **the outlier labeller** — its explanations come from `indian-demand-calendar`, not from the data
7. **the whole pipeline exercised against M15's synthetic generator** — as a *harness test*, never
   as a trained artefact

**What is not buildable now: trained models.** A model fitted to the synthetic generator learns the
generator, including its planted signals. Build the machinery; fit nothing.

## Done means

1. installs and tests pass with no database, no network, no `app` package present
2. the readiness gate returns `blocked` with a specific reason on an empty tenant, and a test asserts
   the exact sentence
3. a test proves the `business_date` split does not leak: a row at 01:30 Tuesday trains as Monday
4. a test proves cross-tenant training is refused by default
5. a test proves an outlier is labelled and retained, never dropped
6. the model ladder demonstrably falls back to the baseline when the candidate fails to beat it
7. no employee-level predictive endpoint exists, and a test asserts the refusal
