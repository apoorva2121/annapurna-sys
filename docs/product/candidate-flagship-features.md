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
