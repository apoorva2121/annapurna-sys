# Indian compliance rules that bind this codebase

Researched 2026-09-12 against current sources. **Read this before touching menu display, restaurant
identity, tax, pricing or customer data.** Full statutory reference, including the domains that do
*not* apply here: <https://claude.ai/code/artifact/df037615-e97f-4619-95e7-5b19e3bbd32f>

Rules are grouped by whether they bind **today**, bind **conditionally**, or do not bind this
product at all. The third group exists because it is the easiest way to waste a week.

---

## Why this file exists, and the rule it is really about

The research that produced it returned **stale-but-confident law three times in one session**:

| Believed | Actually |
|---|---|
| GST has 12% and 28% slabs | Both abolished 22 Sep 2025 — notification `09/2025-CTR` |
| FSSAI registration threshold is ₹12 lakh | Raised to **₹1.5 crore**, w.e.f. 1 Apr 2026 |
| DPDP obligations are live | Core provisions commence **13 May 2027** |

Each was stated as current fact by multiple sources. So:

> **Never fill an Indian rate, threshold or commencement date from memory — your own or a model's.
> Look it up, cite the instrument, and record the date you checked.**

A wrong rate is invisible in review and expensive in production, because it looks exactly like a
right one.

---

## A · In force, and binds this product today

### A1 · The veg / non-veg / egg mark
`FSS (Labelling and Display) Regulations, 2020` · enforced 1 Jul 2022

- Every menu item declares its food type. `menu_item.food_type` is `NOT NULL` with a
  `CHECK IN ('veg','non_veg','egg')`. **No default** — a dish whose type nobody chose must not
  publish.
- **Veg = green. Non-veg = brown.** The brown triangle replaced the older red circle in the 2020
  regulations. Colours come from the locked `--food-veg` / `--food-nonveg` / `--food-egg` tokens in
  `tokens.css`, never from the alert set.
- The egg mark's amber is **product convention, not statute**. A distinct egg mark has been
  proposed; its notified status is unconfirmed. Do not cite an amendment for it.
- Colour is never the only signal (`docs/ui/conventions.md` rule 5): three meanings, three shapes —
  circle, triangle, square.

*Enforced by* `frontend/src/shared/ui/foodTypeMark.test.tsx` and the locked-layer assertions in
`frontend/src/shared/theme/theme.test.ts`.

### A2 · Allergen declaration
Allergen information must appear on the menu, in text or clear symbols, for every covered
establishment. **Not yet modelled — see §D.**

### A3 · The FSSAI licence number
- Format: 14 digits. **First digit is the type — `1` licence, `2` basic registration.** Nothing
  else is issued. Pattern: `^[12][0-9]{13}$`.
- Digits 2–3 state code (`00` = Central licence) · 4–5 year of issue · 6–8 registering authority ·
  9–14 serial.
- **There is no check digit.** A well-formed number cannot be shown to have been issued. Format
  validation removes typos and lazy fabrications and nothing more; only a FoSCoS lookup verifies.
  Never let code or copy imply a validated number is a verified one.
- It prints on every bill (finding S13), so it is audited on change.

### A4 · Licence tiers
`FSS (Licensing and Registration) Amendment Regulations, 2026` · gazette 10 Mar 2026 · **w.e.f. 1 Apr 2026**

| Tier | Annual turnover |
|---|---|
| Basic Registration | up to ₹1.5 crore |
| State Licence | above ₹1.5 crore to ₹50 crore |
| Central Licence | above ₹50 crore |

The older ₹12 lakh / ₹20 crore figures are superseded. Any tier logic written against them
mis-tiers most Indian restaurants.

### A5 · Money and tax
- Money is `NUMERIC(12,2)` / `Decimal`. Never float, never `round()` on a float
  (CLAUDE.md invariant 3). No arithmetic on rupee amounts on the client.
- **Tax rates are dated, never constants.** `tax_rate.effective_from` / `effective_to` already
  implement this — use them. Rates in this space moved four times in eighteen months; reprinting
  an old bill must reproduce the old rate.
- GSTIN is format-validated structurally, not merely for length, and is redacted from logs.

### A6 · Restaurant-borne input GST
A restaurant on the 5% scheme **bears input GST and cannot reclaim it**, so landed cost is
`price * (1 + gst_rate/100)` and a quoted price is not a cost. `library/market-rates.yaml` carries
`gst_rate` and `gst_hsn` per ingredient for this reason; `library/gst_build.py` holds the
derivation and the citations.

---

## B · Conditional — model the condition, not the outcome

### B1 · Calorie declaration
Binds establishments holding a **Central Licence** *or* operating **ten or more outlets**. Most
tenants of this product will not be covered; some will. The obligation is therefore a derived
per-restaurant flag, never a global setting. **Not yet modelled — see §D.**

### B2 · DPDP Act 2023 — build now, enforceable 13 May 2027
Rules notified 13 Nov 2025, commencing in three phases:

| Phase | Date | What commences |
|---|---|---|
| 1 | 13 Nov 2025 ✅ | Board constituted; complaints can be filed |
| 2 | 13 Nov 2026 | Consent Manager registration |
| 3 | **13 May 2027** | Notice, consent, security, breach, children's data, rights, penalties |

Consent architecture cannot be retrofitted — you cannot lawfully re-derive consent never captured.
So build to the Phase 3 standard in M10, but **do not describe these obligations as currently in
force**. When M10 starts: one consent row per purpose (never a single boolean), withdrawal as easy
as granting, notice version and language retained, erasure on purpose completion.

---

## C · Does **not** apply to this product

This is a restaurant management platform, not a marketplace. A restaurant using it is not an
e-commerce operator. The following are aggregator obligations and must not be implemented here
without an ADR establishing that the product's nature has changed:

- **Section 9(5) CGST** liability shift, and the "specified premises" branch
- **GST TCS (§52)** and **income-tax TDS (§194-O)** on marketplace payouts
- 18% on delivery fees under notification `17/2025-CTR`
- **Consumer Protection (E-Commerce) Rules, 2020** — platform grievance officer, 48-hour / one-month SLAs
- **CCPA dark-pattern** obligations that attach to marketplace pricing and checkout
- **Code on Social Security, 2020** aggregator contribution and gig-worker portal reporting

The *design principles* behind some of these remain good practice — show all mandatory charges
before payment, never pre-select a tip — but they are not statutory duties of this product.

---

## D · Known gaps

Raised by the 2026-09-12 audit and not yet closed. These are scope for the owning module, not
mid-module additions:

| Gap | Owner | Note |
|---|---|---|
| No allergen fields on `menu_item` | M03 revisit | §A2 is in force; this is the largest open gap |
| No calorie / serving-size fields | M03 revisit | §B1; needs the derived applicability flag too |
| No FSSAI expiry date or status | M02 revisit | The licence prints on every bill; nothing stops an expired one printing |
| `food_type` not in `app/core/enums.py` | M03 revisit | Violates CLAUDE.md's enum convention — currently a CheckConstraint plus two regexes plus a separate frontend type |

---

## How to add a rule here

1. Cite the instrument: name, number, date, and commencement date.
2. State whether it is **in force**, **notified but not in force**, **unsettled**, or
   **unverified**. Those are four different things and only the first is safe to build on.
3. Record the date you checked it. A rule with no check date is a rumour.
4. Name the test that enforces it, or say plainly that nothing does.
