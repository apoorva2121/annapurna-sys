# Edge features — doing better than every competitor combined

**Status: proposal, not scope.** Written 2026-09-13 from `docs/product/comparison.md` and the three
research files in `docs/product/competitor-research/`. Nothing here is a commitment. Promoting an
item into `docs/modules.md` is a deliberate decision taken between modules (`docs/backlog.md` rule).
Every item is filed in `docs/backlog.md`, either already (the 2026-09-13 comparison rows) or by this
document (rows sourced *Edge features, 2026-09-13*).

This document does not repeat the comparison. It answers one question per feature: **the competitor
already does something like this — how do we do it better, and why can we?**

---

## The seven rules that make a version "better"

Each rule comes from a pattern in the research, not from taste.

| # | Rule | Where it comes from |
|---|---|---|
| 1 | **Say it in rupees and one action.** A finding with no rupee figure and no next step is not a finding. | Petpooja's selling point is "80+ reports"; its reviews complain about ease of use, not missing reports |
| 2 | **No new typing.** If a feature needs staff to enter something they don't enter today, it must remove more typing than it adds. | Top specialist complaint is setup effort (MarketMan, Apicbase, Restroworks) |
| 3 | **Propose, never write.** Anything extracted, predicted or inferred is a draft a person confirms. Only a confirmation writes to the ledger. | `candidate-flagship-features.md`; invariant 2; wrong stock destroys the variance number |
| 4 | **Say how sure we are, and when we'll know more.** Every estimate shows its confidence; every empty screen says what it needs and when it lights up. | Tenzo is the only vendor of 35 that publishes a data threshold; `onboarding-cold-start.md` empty-state rule |
| 5 | **Meet people where they already are.** WhatsApp, Hindi/Marathi, phone, paper bills — not a new habit. | Reelo's success; every Play Store app leads with WhatsApp bills; kachcha bills |
| 6 | **Make trust visible.** Correctness, pricing and support are shown in the product, not promised in a sales call. | §1 of the comparison: support, price surprises and wrong numbers dominate complaints |
| 7 | **Never accuse, never rank the bottom.** Anything touching staff follows ADR 0011 and `workload-fairness.md`. | M17 guardrails; attribution that confuses staff meals with theft harms honest people |

---

## Theme 1 · Trust you can see

Competitors lose customers on support, surprise pricing and wrong numbers (comparison §1). None of
them turns trust into a product surface. This theme does.

### 1.1 · Books verified tonight

- **Best competitor version:** "GST-compliant" printed on every product page. Nothing checks it
  after the fact.
- **Where it falls short:** Zobaze taxed the pre-discount price for years (reviews 2019–2022);
  myBillBook has an alleged invoice-type error; Vyapar users report "calculations did not match".
- **Our version:** a nightly self-audit per restaurant that re-derives, from the ledger, what must
  hold: invoice serials consecutive per financial year with no gaps; each invoice's tax equals the
  sum of its lines; credit notes never exceed their invoice; the till's expected cash equals its
  payments; stock on hand equals the sum of movements. The owner home shows one line: **"Books
  verified — 214 bills, 3 credit notes, 1 till. 0 problems."** A problem becomes an alarm with the
  rows attached, and a support ticket is opened automatically.
- **Why we can:** every one of these rules is already a tested invariant (M05 property test, M07
  §A7 tests). The audit runs the same assertions against live data instead of fixtures.
- **Guardrail:** a check that fails must never "fix" anything. It reports; a correction is a new row
  (invariants 2 and 6).

### 1.2 · Help that arrives with the context

- **Best competitor version:** phone and chat support (Restroworks lists 24×7 channels).
- **Where it falls short:** "support vanishes after payment" is the single most repeated complaint
  across all three tiers.
- **Our version:** a **"Something's wrong"** button on every screen. It attaches the screen, the last
  `request_id`s (already on every error), app version and the last few actions — no customer
  personal data — and lets the person add a voice note in their own language. The ticket shows its
  status and the promised response time inside the app, so silence is visible to both sides.
- **Why we can:** the error envelope already carries `request_id`, and logs are already redacted
  (M00). The plain-language error work raised in the M03 manual pass is the first half of this.
- **Guardrail:** attachments pass the same redaction as logs (guardrail G-12).

### 1.3 · Your data leaves with you

- **Best competitor version:** CSV exports of individual reports.
- **Where it falls short:** MarketMan's cancellation friction (60-day notice, forced retention
  calls) and Zobaze's free-to-paid switch show owners fear being trapped.
- **Our version:** **one button exports everything** the restaurant owns — menu, recipes, stock
  ledger, bills, suppliers, customers (with consent state) — as documented CSV and JSON, at any
  time, on any plan, including after cancelling for a stated retention window.
- **Why we can:** tenant scope is structural (invariant 1), so "everything for restaurant X" is a
  well-defined query. M10 already plans DPDP export per customer; this is the same idea for the
  business.
- **Open question:** the retention window after cancellation must respect legal record-keeping
  periods — look them up and cite them; do not assume.

### 1.4 · Nothing disappears in an update

- **Best competitor version:** release notes, when they exist.
- **Where it falls short:** a Petpooja Play Store review: an update removed seeing previous days'
  sales on the home page.
- **Our version:** an in-app "What changed" page in plain language, and a product rule: **a
  capability a customer uses is never removed without notice and a replacement.** Usage of each
  screen is measured (M13 query layer, no personal data) so a removal can see who it would hurt.

### 1.5 · Your plan, on one screen

- **Best competitor version:** Restrofi and GoRestro publish INR prices.
- **Where it falls short:** add-ons appearing after purchase (myBillBook), renewal jumps (SalaryBox),
  training at ~30% extra (GoFrugal).
- **Our version:** a "Your plan" page showing what is included, the renewal price and date, and a
  written promise that existing customers keep what they have if tiers change. Commercial decision
  first (comparison §7); this is where it becomes visible.

---

## Theme 2 · Data gets in without anyone typing

The variance number — the product's core promise — needs purchases, counts and waste every day.
Competitors assume staff will type. This theme removes the typing.

### 2.1 · Bill-to-ledger, WhatsApp-native (improves flagship #1)

- **Best competitor version:** Petpooja Purchase and MarketMan photograph a bill and OCR it (m).
- **Where it falls short:** built for printed invoices; neither documents what happens to a line it
  cannot match (`03-point-solutions.md` §MarketMan "not found").
- **Our version, beyond flagship #1:**
  - **Forward, don't photograph.** Suppliers already send bills on WhatsApp. Forwarding the message
    to the restaurant's number creates the draft. A photo is the fallback.
  - **Every supplier teaches the system.** Per-supplier alias memory: once the store manager confirms
    that Ramesh Traders' `TMT` is tomato, it is never asked again for that supplier. Confirmations
    across restaurants improve the shared lexicon (without sharing any restaurant's prices).
  - **Unmatched lines never vanish.** They sit in a visible "needs you" list with the original image
    crop beside them — meez's "New Purchase Items" queue, but with the evidence attached.
  - **Rate sanity, not just reading.** A line whose rate is far from this supplier's history or the
    city market rate is flagged before confirmation ("₹180/kg tomato — last 30 days ₹38–52").
- **Why we can:** market-rate layer (122 prices, city index), canonical base units (invariant 5),
  the lexicon brief, and a ledger that only a confirmation can write to.
- **Open decisions (from the flagship doc, still open):** data residency of bill images, per-bill
  model cost at an Indian price point, and who confirms a bill when the same person placed the order.

### 2.2 · Speak it in your language

- **Best competitor version:** DineOpen claims AI voice ordering for *customers* in eight Indian
  languages (m, no independent reviews). Nobody offers voice for back-of-house.
- **Where it falls short:** kitchen and store staff are the people least likely to type English, and
  they are the ones who must log waste and deliveries.
- **Our version:** hold-to-talk on the waste, receiving and count screens: *"do kilo paneer kharab,
  expiry"* becomes a draft — PANEER, 2000 g, reason: expired — shown back with big confirm/fix
  buttons. Under ten seconds, as `waste-model.md` requires.
- **Why we can:** the lexicon resolver is the same component bill-to-ledger needs; voice is one more
  input to it. Rule 3 applies unchanged.
- **Guardrail:** audio is not stored after transcription unless the person chooses to attach it.

### 2.3 · Count ten things, not a hundred

- **Best competitor version:** Supy's parallel counting cuts count time by "over 50%" (m); MarketMan
  supports partial counts.
- **Where it falls short:** both still assume the full list gets counted regularly. A single Indian
  outlet with no store clerk won't.
- **Our version:** **today's count list is chosen by the system**: the ~10 items where value ×
  recent unexplained variance × days since last count is highest. High-value proteins and dairy come
  up often; salt almost never. Over a month everything that matters is counted, and each day's count
  takes five minutes.
- **Why we can:** M05 already derives on-hand and holds counts; `onboarding-cold-start.md` already
  argues for counting the top 40 by value. This makes it continuous.
- **Guardrail:** the variance report states which items were counted and when, so a figure built on
  an old count says so (rule 4).

### 2.4 · Receive blind

- **Best competitor version:** three-way match — PO, invoice, receipt (MarketMan, Supy).
- **Where it falls short:** the receiver sees the billed quantity before weighing, and people
  anchor: "the bill says 10 kg, it's roughly 10 kg".
- **Our version:** an optional blind mode on the goods-receipt screen — weigh and enter first, then
  see the bill's figure and the difference. The same principle as the till counted blind (M07).
- **Why we can:** M06 already stores ordered, invoiced and received separately; this changes only the
  order in which the screen reveals them.
- **Note:** `docs/manual-tests/M06-procurement.md` §C asks whether a store manager fills the two
  inputs with different numbers. Blind mode is the answer if they don't.

### 2.5 · Cost the dishes that matter first

- **Best competitor version:** meez won't show a dish cost until every ingredient is costed, and
  documents four reasons why a recipe fails to cost.
- **Where it falls short:** it is all-or-nothing, and diagnosis is the customer's job.
- **Our version:** an **onboarding coverage score**: "Recipes cover **78% of last week's sales**. Cost
  these 6 dishes next to reach 95%." Dishes are ordered by revenue, not alphabet. Each incomplete
  dish names exactly what is missing (the filed "explain why a dish won't cost" row).
- **Why we can:** M04's rollup walks the recipe tree; M07 has sales per variant; `library/` supplies a
  proposed recipe for most gaps.

---

## Theme 3 · Money found, and proven

Competitors produce reports. This theme produces recovered rupees, and a running proof of them.

### 3.1 · The action queue, not a dashboard

- **Best competitor version:** Petpooja's 80+ reports; Restroworks' 100+ customisable reports (m).
- **Where it falls short:** a report nobody reads recovers nothing.
- **Our version:** every insight becomes **one card**: what happened, the rupees, the one action, and
  a button — *Do it*, *Not now*, *Not true (tell us why)*. Examples:
  - "Makhani gravy: 3.8 L thrown away four days running (₹1,140/day). Make 6.5 L tomorrow."
  - "Supplier A short on 3 of 4 deliveries this month (₹5,100). Send them the evidence?"
  - "Paneer ₹340/kg today vs ₹290 last month. Paneer Tikka margin falls to 41%. Review price?"
  *Not true* answers are data: they tune the rules and are shown in a monthly "what we got wrong".
- **Why we can:** M13 is already a query layer with drill-through; M14 already plans notification
  severity so this does not become noise; waste, procurement and cost data all exist by M09.

### 3.2 · The recovered-money ledger

- **Best competitor version:** vendor ROI claims (Winnow "2–10×", Supy "39% to 33%") — marketing,
  never shown per customer.
- **Where it falls short:** the owner has no way to see whether the software paid for itself.
- **Our version:** a running figure on the owner home: **"Recovered since you joined: ₹1,84,000 —
  your plan cost ₹24,000."** Each rupee links to the action that produced it and how it was
  measured: a prep batch reduced and leftover fell, a short delivery credited by a supplier, a price
  raised on a loss-making dish.
- **Guardrail (rule 4):** only measured before/after deltas count, labelled *measured* or
  *estimated*, with the method one tap away. An honest smaller number beats an impressive one nobody
  believes — and this figure is what renews the subscription.

### 3.3 · Supplier price → dish margin, instantly

- **Best competitor version:** Petpooja Purchase compares the same item across suppliers (m); meez
  recosts on a new invoice.
- **Where it falls short:** neither says which **dishes** a price rise just made unprofitable.
- **Our version:** when a confirmed receipt changes an ingredient's cost, show the dishes whose margin
  crosses the owner's threshold, with the price that restores it. The threshold is the owner's
  choice, never a default we invent.
- **Why we can:** `GET /stock-items/{id}/used-by` and the recursive cost rollup exist (M04); receipts
  freeze cost (M06).
- **Compliance:** a menu price change triggers M18's checks (tax group, display rules) before it
  publishes.

### 3.4 · True margin per channel

- **Best competitor version:** Petpooja and UrbanPiper sync Swiggy/Zomato orders and reconcile
  payouts (m).
- **Where it falls short:** nobody found shows the owner that a dish making 60% on dine-in makes 8%
  on delivery after commission, packaging and discounts.
- **Our version:** dish margin by channel, using the **commission and packaging costs the owner
  enters** (or imports from an aggregator payout statement). Works before any integration exists.
- **Compliance:** whether packaging is taxed at the food rate is **unverified** (`compliance-rules.md`
  §A7, R18). Never fill a commission rate or tax treatment from memory; the owner supplies rates, the
  tax treatment is cited before it is computed.

### 3.5 · Leakage signals, without accusation

- **Best competitor version:** Petpooja's captain app logs edits with staff name and time (m).
- **Where it falls short:** a log is not a signal; nobody reads it.
- **Our version:** patterns that historically mean leakage — lines cancelled after the kitchen ticket
  was sent, bills reprinted after settlement attempts, comps without a stated reason, discounts
  clustered on one login and shift — shown **to the owner only**, as a pattern with context ("3 of 4
  were during the 10 pm rush"), never as a named ranking.
- **Why we can:** invariant 6 already audits every price-affecting change; M07 records comps with an
  authoriser.
- **Guardrail (rule 7):** no bottom list, no automatic consequence, context first, and the same
  fairness review as M17's open questions before it ships.

### 3.6 · Evidence the supplier can't argue with

- **Best competitor version:** GoFrugal's vendor performance analysis (m).
- **Where it falls short:** analysis inside the restaurant's app changes nothing at the supplier.
- **Our version:** a one-tap, drafted WhatsApp message to the supplier: dates, billed vs weighed,
  rupees, photos from receiving. The owner reviews and sends it themselves. The drafted message and
  the supplier's credit, if any, are recorded (feeding 3.2).

### 3.7 · See what your menu loses — before you buy

- **Best competitor version:** free tiers and trials (Restrofi, 7shifts, PosBytz 14 days).
- **Where it falls short:** a trial shows an empty product; value needs weeks of data.
- **Our version:** photograph the menu, pick the city, and within minutes see **the dishes likely to
  lose money on every plate** — from the recipe library and market rates, clearly marked *estimated*.
  No signup until they want to keep it.
- **Why we can:** this is the day-1 row of `onboarding-cold-start.md` ("usually true") made into the
  first thing a prospect sees. No competitor has the library to do it.
- **Guardrail:** estimates are labelled at every figure; library confidence tiers are shown. This is
  a sales tool that must not overclaim.

---

## Theme 4 · Service people remember

### 4.1 · Catch the unhappy table before it leaves

- **Best competitor version:** Arow's anonymous QR feedback (m); Reelo's post-visit messages.
- **Where it falls short:** feedback arrives after the customer has decided not to return
  (`customer-experience.md`).
- **Our version:** a rating of 3 or below at the table alerts the manager on duty **while the guest is
  still seated**, with the order, the waiter and what went slowly. Recovery becomes possible, and M10's
  complaint workflow records whether they came back.
- **Why we can:** M10 plans order-linked feedback; M08 plans the five kitchen timestamps.

### 4.2 · The bill in under four minutes

- **Best competitor version:** "print bills in 3 secs" (Arow (m)).
- **Where it falls short:** printing speed is not the problem; the wait for someone to bring the bill
  is. `customer-experience.md` calls bill-to-settle the most complained-about moment in Indian dining.
- **Our version:** when a bill is requested, a timer starts on the waiter screens; at the owner's
  target it nudges the floor. Median bill-to-settle per shift appears in M13.
- **Why we can:** M07 already has `POST /orders/{id}/bill` and settlement timestamps.

### 4.3 · An honest wait quote

- **Best competitor version:** none found.
- **Our version:** at ordering, the waiter screen shows a quote from per-dish prep time and current
  station load, and warns when the kitchen is backed up — before the waiter promises
  (`customer-experience.md` "Quoted time beats fast time"). Needs M08's timestamps and a few weeks of
  history (rule 4: say so until then).

---

## Theme 5 · A kitchen that plans itself

### 5.1 · The prep sheet, smarter each week (improves the filed prep-sheet row)

- **Best competitor version:** none of 35 products has a prep sheet. Orbisk measures leftover by
  serving stage with cameras.
- **Our version, beyond `waste-model.md` §3:**
  - **Week 1:** the chef enters usual batch sizes; the system only measures leftover.
  - **Week 3:** suggestions from sold-through history, with a range, not a single number.
  - **Later:** the Indian demand calendar (festival eve, IPL nights, exam season, monsoon) adjusts the
    suggestion, with the reason shown ("Ganesh Chaturthi eve — last year +35% dine-in").
  - Near-expiry stock is pulled into tomorrow's suggestions first (the filed near-expiry row).
- **Guardrail:** calendar dates come from a cited source, never generated
  (`candidate-flagship-features.md` addendum B).

### 5.2 · Shift handover, written for you

- **Best competitor version:** 7shifts' Manager Log Book, a paid add-on where managers type notes.
- **Where it falls short:** someone has to write it, at the end of a long shift.
- **Our version:** an automatic handover card at shift end: dishes that ran out, short deliveries,
  open complaints, till difference, stock below par, tasks not done. The outgoing manager adds a line
  if they want. Sent to the incoming manager (and owner, if chosen) on WhatsApp.
- **Why we can:** every item is already an event in M05–M07 or planned in M09–M11.

### 5.3 · Practice mode for new staff

- **Best competitor version:** GoFrugal training that expires or costs extra (review).
- **Our version:** a practice restaurant on every account, loaded with the demo seed, where a new
  waiter can take orders, split bills and settle without touching real data. Resettable in one tap.
- **Why we can:** `make seed` already builds a complete restaurant mid-service; a practice tenant is
  the same data behind the same tenant isolation.

---

## Theme 6 · Built for Indian conditions

### 6.1 · Offline that can't corrupt anything

- **Best competitor version:** every Play Store app claims offline with auto-sync (m).
- **Where it falls short:** syncing edits to shared state is where data gets lost (Vyapar: "data
  disappeared"; SafetyCulture: sync delays under load).
- **Our version:** offline capture for the actions that happen at the worst signal — take an order,
  settle, log waste, receive — queued on the device as **append-only events with idempotency keys**
  and replayed when online. Because the ledger never edits in place (invariants 2 and 6) and replays
  are idempotent (ADR 0010), a replay cannot double-post or overwrite.
- **Design constraints to resolve first:** idempotency keys currently expire after 24 hours (ADR
  0010), so an offline queue older than that needs its own rule; invoice serials must be allocated
  without gaps when two devices settle offline (Rule 46 — a device must never mint a final number
  offline); the server still reprices every line on replay.
- **Status:** offline is out of scope for month 1; this is a design note so nothing built now blocks
  it (CLAUDE.md "design so none of these are blocked").

### 6.2 · The owner's day on WhatsApp

- **Best competitor version:** SOLO's separate owner app; Petpooja's reports.
- **Our version:** at close, one WhatsApp message to the owner: sales, bills, till difference, voids
  and comps, waste in rupees, and the top action card. Monday: the week's leak report
  (`waste-model.md` "The one report this all exists for").
- **Compliance:** the owner opts in. Customer-facing WhatsApp (campaigns, bills to guests) is a
  different matter: consent per purpose (M10, DPDP §B2) and India's commercial-communication rules
  must be researched and cited before any customer message is sent — **unverified today**.

---

## Priority

Scored on three things: rupee impact for a single outlet, what already exists to build on, and what it
waits for. Sizes are relative (S/M/L), not day estimates.

| Rank | Feature | Impact | Builds on | Waits for | Size |
|---|---|---|---|---|---|
| 1 | 5.1 Prep sheet (smarter each week) | Highest: largest waste stage | M04, M05, M07 (built) | M09 waste logging for leftover | M |
| 2 | 2.1 Bill-to-ledger, WhatsApp-native | Makes variance possible at all | M06, market rates, lexicon brief | Data-residency and cost decisions | L |
| 3 | 3.7 See what your menu loses | Acquisition — the first meeting | `library/`, market rates | Menu photo extraction | M |
| 4 | 1.1 Books verified tonight | Trust; turns tests into a selling point | M05, M07 invariants (built) | nothing | S |
| 5 | 3.1 Action queue + 3.2 recovered-money ledger | Retention — proves ROI | M13 query layer | M09, M13, M14 | L |
| 6 | 2.3 Count ten things + 2.4 receive blind | Better data for variance, less effort | M05, M06 (built) | nothing | S |
| 7 | 3.3 Price → dish margin | Protects margin weekly | M04, M06 (built) | nothing | S |
| 8 | 2.5 Coverage score | Faster onboarding | M04, M07 (built) | nothing | S |
| 9 | 6.1 Offline by replay | Removes the #1 table-stakes objection | ADR 0010, invariants | Decision to lift the month-1 exclusion | L |
| 10 | 4.1 Catch the unhappy table + 4.2 bill timer | Repeat visits | M07 (built) | M08, M10 | M |
| 11 | 3.4 True margin per channel | Delivery-heavy restaurants | M04, M07 | Owner-entered rates; R18 research | M |
| 12 | 1.2 Help with context + 1.3 export everything | Trust; support cost | M00 error envelope | nothing | M |
| 13 | 5.2 Handover card + 6.2 owner's day on WhatsApp | Daily habit | M05–M07 | WhatsApp Business setup; M11 | M |
| 14 | 3.5 Leakage signals + 3.6 supplier evidence | Leakage | Audit log, M06 | Fairness review (M17 questions) | M |
| 15 | 2.2 Voice in Indian languages | Removes typing for kitchen staff | Lexicon resolver from #2 | #2 | L |
| 16 | 5.3 Practice mode, 1.4 no silent removals, 1.5 plan page, 4.3 wait quote | Trust and polish | Seed, M13, M08 | Commercial decisions; M08 history | S–M |

**Suggested order of thinking, not of building:** items 4, 6, 7 and 8 need nothing new and could
follow the current modules closely. Items 1, 2 and 3 are the product's edge and deserve their own
module specs. Item 9 is a scope decision for the owner of this product.

---

## What this deliberately does not propose

- Anything that needs hardware a single outlet won't buy (waste cameras, IoT sensors first).
- AI that answers without evidence ("ask your data", voice ordering for customers).
- Any feature that ranks, scores or accuses individual staff outside M17's guardrails.
- Any Indian rate, threshold, commission or legal deadline filled from memory.

## Decisions this needs from you

1. **Offline:** keep it out of month 1, or promote 6.1 before the pilot?
2. **Bill and voice processing:** hosted model, self-hosted, or hosted with an opt-out (data leaves
   the restaurant's tenancy and possibly the country)?
3. **WhatsApp Business:** acceptable as the main channel for owner summaries and supplier messages?
4. **The recovered-money figure:** comfortable showing a conservative, measured number beside the plan
   price, knowing it will sometimes be smaller than the price?
