# Candidate flagship features — what to build that is not table stakes

**Status: proposal, not scope.** Nothing here is committed. Promoting any of it into
`docs/modules.md` is a deliberate decision taken between modules, per the rule in `docs/backlog.md`.

Written 2026-09-11, after M02, in answer to "what exceptional thing should we build".

---

## The finding that decides the ranking

`docs/onboarding-cold-start.md` already names the answer, and the build plan does not contain it:

> **Purchases** — photograph the supplier bill or forward the WhatsApp message; extract lines with
> an LLM; store manager confirms. **This is the daily habit the whole system depends on**, so it
> must take under a minute.

> **Menu** — photograph the printed menu, extract items and prices with an LLM, chef confirms.
> Never make anyone type 120 dish names.

`docs/modules.md` has eighteen modules and **no mention of `photograph`, `extract`, `LLM` or
`WhatsApp`**. M06 builds "goods receipt with weighing (the money screen)" — manual line entry, one
line at a time.

So the strategy document and the build plan disagree about the thing the strategy document calls
load-bearing. That is the same class of defect this project keeps finding in code — a claim with
nothing behind it — and it is worth more than any feature idea invented from scratch.

---

## Why this is the highest-leverage thing, not merely a nice one

The product's differentiator is CLAUDE.md invariant 7: **theoretical ≠ actual consumption, and the
variance between them is the core product insight.** Everything the product sells rests on that
number being real.

That number requires three inputs:

| Input | Frequency | Friction |
|---|---|---|
| Recipes | once, at setup | high, but survivable — it happens once |
| **Purchases / goods receipt** | **every delivery, every day** | **high, and it repeats forever** |
| Physical counts | weekly-ish | high, partially solved by counting only the top 40 by value |

If purchases are not entered, the stock ledger is empty, variance is undefined, and the product's
entire differentiator never activates — while the POS half keeps working fine, so the customer
concludes the analytics are "not accurate" rather than "not fed".

And the memory of this project is explicit: **Indian restaurants keep no records.** A product whose
core insight requires daily disciplined data entry from people who have never kept records is a
product that demos beautifully and churns in month two.

So the question is not "what clever analytics can we add". It is **"what makes the data exist at
all"** — because every analytic below is downstream of that.

---

## Ranked

### 1 · Bill-to-ledger — supplier document intelligence

**What it is.** Photograph a supplier bill, or forward the WhatsApp message, and get a *draft*
goods receipt: supplier, date, lines of (ingredient, quantity, unit, rate, amount), each with a
confidence, matched against the tenant's ingredient catalogue and against the open PO if there is
one. The store manager confirms or corrects. Under a minute.

**Why it is exceptional rather than commodity OCR.** Invoice OCR is a solved, crowded category —
for *printed Western invoices with item codes*. None of that survives contact with an Indian
supplier bill:

- **kachcha vs pukka** — the unofficial handwritten slip and the GST invoice are different
  documents for the same delivery, and both exist
- **handwriting**, frequently Devanagari or mixed Devanagari/Latin
- **no item codes, ever** — free text, in supplier shorthand: `Kanda` (onion), `TMT`, `Aloo`,
  `Dahi 5`, abbreviations that differ per supplier and sometimes per delivery boy
- **units that are not units** — `nag` (piece), `pkt`, `gunny`/`bora` (~50kg sack), `tin` (~15kg
  oil), `peti` (crate), `dozen` — and a rate quoted per kg while billed per gunny
- **WhatsApp instead of paper** — "bhaiya 20 kilo aloo bhej do" is the purchase order, and the
  reply is the invoice

**The moat is the resolver, not the OCR.** Extraction gets you text. The hard, defensible part is
mapping messy supplier text to **the canonical ingredient and its base unit** (invariant 5: `g`,
`ml`, `unit`). That mapping compounds twice over: per tenant (this supplier's `TMT` is tomato) and
across tenants (a shared Indian ingredient and unit lexicon that no Western vendor has and no new
entrant can assemble quickly). Every confirmation and every correction is a labelled example.

**The safety property that makes it shippable.** A silent extraction error writes wrong stock — and
wrong stock destroys the variance number, which is the thing being sold. So the boundary must be
architectural, not a UI nicety:

> **Extraction proposes. It never writes to the ledger.** It emits a draft with per-field
> confidence; a human confirms; the confirmation is what creates the stock movements. A correction
> after confirmation is a new `adjustment` movement, never an edit (invariant 2).

That boundary is also what makes this safe to hand to a separate model or team entirely: with no
write path, a bad extraction costs a correction, not corruption.

**What it unblocks.** M05's ledger has real data. M06's three-way variance (ordered / invoiced /
received) becomes computable from documents rather than from typing. M13's dashboards have
something true to show. The daily habit forms because it costs sixty seconds instead of twenty
minutes.

---

### 2 · Variance attribution — the product's actual promise, made explainable

**What it is.** Not "your paneer variance is 12%" — the product will already compute that. Rather:
*why*, ranked, with evidence. Short delivery from the supplier; portion drift on one dish; wastage
logged under the wrong reason; staff meals not being booked; theft. Each with the rows that support
it and a rupee figure.

**Why it matters.** "Variance is 12%" is a number an owner cannot act on and will stop reading.
"₹8,400 last month, most of it paneer, and it appears on Tuesdays and Fridays when one supplier
delivers" is a decision. This is where the product stops being a POS with reports and becomes the
thing the vision describes.

**Why it is second, not first.** It is entirely downstream of data existing — and its inputs are
exactly what #1 produces. Building it first means building an engine that runs on a dataset nobody
is feeding.

**The hard part.** Attribution, not detection. `docs/waste-model.md` already makes the key domain
point: *staff meals, untracked, look exactly like theft and poison every variance number.* An
attribution engine that cannot separate those will accuse honest people, which is worse than
saying nothing — and is an ADR 0011 problem (the fairness guardrails) as much as a statistics one.

---

### 3 · Demand forecasting on the Indian calendar

Vision §27 lists demand/inventory/staffing/customer forecasting as "later versions". The
differentiated version is not the model — it is the **calendar**: festivals that move every year,
the regional ones that matter in Pune specifically, cricket fixtures, exam season, monsoon onset,
dry days. A generic forecaster trained on 90 days of history will be confidently wrong on exactly
the days that matter most to a restaurant's cash.

Third because it needs 60–90 days of clean history per tenant — which, again, #1 produces.

---

### 4 · Menu engineering and price intelligence

Popularity × margin quadrants, price-change simulation against recipe cost. Genuinely valuable,
largely deterministic arithmetic over data the product already has by M04. Worth building — not
worth calling exceptional, and not the thing to spend a best-in-class model on.

### 5 · Conversational analytics ("ask your data")

Demos extremely well. Low durable value here: the questions an owner actually repeats are few
enough to be dashboard tiles, and it inherits every data-quality problem above while adding a new
way to be confidently wrong. Deliberately last.

---

## What I would want decided before any of this is built

These are not implementation details; each one can change the answer.

1. **Data residency and consent.** Sending a supplier bill to a hosted model means customer
   commercial data leaves the country and the tenancy. DPDP consent flows are M16. Decide whether
   extraction is a hosted API, a self-hosted model, or hosted-with-an-opt-out — *before* the
   architecture assumes one.
2. **Unit economics.** Per-extraction cost against an Indian SMB price point, at maybe 5–15
   documents a day per restaurant. This decides whether a big model runs on every document or only
   on the ones a cheap path flags as low-confidence.
3. **Connectivity.** Restaurant networks are bad and the goods-receipt moment is at a back door
   with one bar of signal. Capture must queue locally and reconcile later — which is an
   offline-first requirement, and `docs/modules.md` lists offline sync as explicitly out of scope
   for month 1.
4. **Who confirms.** The store manager confirming their own supplier's bill is a control weakness
   if that person is also the one ordering. Worth a deliberate answer, not a default.

## Recommendation

Give Fable **#1**, scoped tightly as a *proposing* service with no write path: input is images, PDFs
or forwarded text plus the tenant's ingredient catalogue and supplier history; output is a draft
receipt with per-line confidence and resolution candidates. It is self-contained, genuinely hard,
sits behind a clean contract, and cannot corrupt anything if it is wrong.

Then build **#2** on the data it produces, because that is the feature the product is actually for.

---

# Addendum · What can be built *now*, before any real data exists

Asked 2026-09-11: can a strong external model build state-of-the-art preprocessing, analysis and ML
now, as plug-and-play modules, to be used later?

## The trap to avoid

**Do not train predictive models now.** There is no real data. The only dataset is M15's synthetic
generator, and a model trained on it learns the generator — including its *planted* signals — rather
than restaurants. The result demos well, cannot be validated, and rots as the schema moves.

There is also a carrying cost that is not tokens: an unused artefact ages, and the next person
trusts it. A model built today and plugged in nine months from now is a confident stranger.

## The distinction that makes this worth doing

Split every candidate by whether it needs *your customers' data*:

| Needs customer data | Does not |
|---|---|
| trained demand / churn / staffing models | domain **knowledge** encoded as data |
| anything tuned on real distributions | **infrastructure** that models plug into |

Everything in the right-hand column can be built now, validated now, and still be correct in a year.
Everything in the left should wait until there is history to learn from and to test against.

## Build now

### A · `indian-fnb-lexicon` — the ingredient and unit resolver

**The single best use of external model effort**, because it is pure domain knowledge, it needs no
customer data, and it is the moat under the bill-to-ledger feature above.

- canonical ingredient list for Indian restaurant kitchens, each with a base unit (`g`/`ml`/`unit`,
  invariant 5), category, and regional aliases across Hindi, Marathi, Tamil, Bengali, Gujarati — in
  both Devanagari and transliteration
- supplier shorthand: `Kanda`, `TMT`, `Aloo`, `Dahi`, the abbreviations that differ per supplier
- **the unit parser, which is the hard part**: `nag`, `pkt`, `gunny`/`bora`, `tin`, `peti`, `dozen`,
  `kg`, `gm`, `ltr` — parsed from free text into a base-unit quantity
- a resolver: messy line text → ranked candidate ingredients with scores

**The safety requirement, and it is not optional.** A wrong unit conversion writes wrong stock, and
wrong stock destroys the variance number the product sells. A `gunny` is *approximately* 50kg and
varies by commodity and region. So every conversion must carry **provenance and a confidence**, and
anything below threshold is a human confirmation rather than a silent number. An artefact that
states `gunny = 50000g` as fact is worse than one that says "50kg ± regional, confirm".

Generated entries need verification against a real source before they are trusted. A model will
produce a plausible, confident, wrong conversion without hesitating.

### B · `indian-demand-calendar` — the feature library forecasting will need

A forecaster is commodity. **The calendar is the differentiator**, and it is knowledge work that can
be done now:

- festivals with regional applicability (they move every year, and Ganesh Chaturthi matters in Pune
  in a way it does not in Kolkata)
- festival eve / day / day-after, which behave completely differently for a restaurant
- cricket fixtures — IPL and international, day vs night
- monsoon onset and withdrawal by city; exam season; school holidays
- dry days by state; paydays (the 1st and the last working day are real demand events in India)
- long weekends

Output is plain feature rows keyed by date and city. **Dates must be verified against an
authoritative source, not generated** — a model inventing Diwali 2027 is plausible and wrong, and
the error is invisible until the day it matters most.

### C · `forecast-eval` — the harness, not the model

Most forecasting projects fail on evaluation rather than modelling. Buildable now, against synthetic
data, and it is what will later prove any model is real:

- time-series splits that respect `business_date` boundaries, so there is no leakage across the
  05:00 line (a naive split leaks tomorrow into today for every restaurant that serves past midnight)
- baselines that a real model must beat: seasonal naive, day-of-week mean, EWMA
- **metrics aligned to the decision, not to the literature**: over-prep and under-prep cost different
  amounts, so quantile/pinball loss, reported in rupees
- the interface a model must implement to be swapped in

Lower priority than A and B only because its consumer is further away.

## How they must be built to be genuinely plug-and-play

Non-negotiable, or they will not be reusable and cannot be sold separately:

- **standalone packages that never import `app.*`** — the application depends on them, never the
  reverse
- inputs and outputs are plain data (dicts, dataframes, Pydantic models), never SQLAlchemy objects
- their own test suites, their own versioning, their own changelog
- no database access of any kind

## What is sellable on its own

A and B. The ingredient lexicon and unit resolver is an asset any Indian F&B or grocery product
needs and none of them can assemble quickly; the demand calendar is licensable to anyone doing
Indian retail analytics. C is internal quality infrastructure with no external market.

## Order

**A, then B. Hold C until there is a model to evaluate.** A has a near-term consumer — the
bill-to-ledger feature — which is what stops it becoming shelfware. B rots slowly and needs an
annual refresh, so it can wait behind A without cost.
