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

## What now enforces this file · M18, 2026-09-19

This file used to be prose that a reviewer had to remember to check. Ten of its rules now run as
code: `app/core/compliance.py` holds each one as an **evaluator plus a citation plus a
`checked_on` date**, and `GET /api/v1/staff/compliance/findings` runs the lot against a
restaurant's own data whenever somebody opens the screen.

**The four states above are now structural.** `Rule.__post_init__` refuses to construct a rule
whose severity is `critical` and whose status is anything other than `in_force`:

> *"only a rule in force may be critical. This one is {status}, so it may inform and must not
> block."*

`tests/test_m18_compliance.py::TestTheRuleThatGovernsTheRules` asserts it over the whole catalogue,
including rules nobody has written yet. So the second standing rule below — never conflate *in
force* with *notified but not in force* with *unsettled* with *unverified* — is no longer something
a person has to hold in their head while editing.

What is still a person's job: **the citations themselves**. Nothing in code can tell you whether
the instrument says what this file says it says. That is what `checked_on` is for, and why it is
printed on the screen an owner reads rather than kept here.

| Rule here | Code | Severity |
|---|---|---|
| §A1 FSSAI licence validity | `fssai.expired`, `fssai.expiring`, `fssai.malformed` | critical / warning / critical |
| §A3 licence tier by turnover | `fssai.tier` | warning |
| §A4 GSTIN on a tax invoice | `gst.gstin_missing` | critical |
| §A5 current GST rate | `gst.rate_missing` | critical |
| §A2 allergen declaration | `labelling.allergens` | warning |
| §B1 calorie declaration | `labelling.calories` | warning (conditional) |
| §C/D DPDP consent | `dpdp.consent` | **advisory — notified, not in force** |
| CCPA service charge | `ccpa.service_charge` | **advisory — unsettled** |

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
establishment. **Modelled as text** (backlog-issues B8): `menu_item.allergen_statement`, shown to
guests; NULL means nobody has checked, and a dish with none says so in words. **No list of
allergens is written into code**: the regulation's own list has not been read from the instrument,
and it must be before any structured list or symbol set is built — see §D.

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

### A7 · The bill, the invoice, and what may change after it (M07)

Checked 2026-09-13 for `docs/modules/M07-orders-spec.md`. Its research table (R1–R19) carries every
source. The statuses below are copied from that table, not re-derived.

| Rule | Instrument | Status | Enforced by |
|---|---|---|---|
| A composition restaurant may not collect tax, and issues a bill of supply | CGST Act s.10; Rule 49 | in force | `test_a_composition_restaurant_puts_no_tax_on_the_bill`, `test_a_composition_restaurant_issues_a_bill_of_supply_with_no_tax`, and migration 0019's check |
| A tax invoice carries the supplier's GSTIN | CGST Rules, Rule 46 | in force | `test_a_regular_restaurant_without_its_gstin_cannot_issue_a_tax_invoice` |
| **A composition bill of supply carries the words "composition taxable person, not eligible to collect tax on supplies" at the top** | CGST Rules, **Rule 5(1)(f)** | in force; **primary text read 2026-09-20** from CBIC's own PDF of the CGST Rules 2017 (Part A, as amended to 24-09-2021), pages 3–4 | `test_a_composition_bill_of_supply_carries_the_declaration` |
| A composition restaurant displays "composition taxable person" on a signboard at each place of business | CGST Rules, Rule 5(1)(g) | in force; same source | **Not enforceable by software** — a physical signboard. Surfaced as advice, never as a check |

### A8 · Sending an SMS to an Indian customer (researched 2026-09-20, nothing built)

Researched because F9 — letting an owner recover their own password by a code to their phone —
cannot be planned without it. **Nothing in the product sends an SMS today**, and this section
exists so that whoever builds it starts from the instrument rather than from a vendor's blog.

| Rule | Instrument | Status | Enforced by |
|---|---|---|---|
| Commercial communication to Indian subscribers is governed by TCCCPR 2018, which **mandates Distributed Ledger Technology** for registering senders, headers and consent | TRAI, Telecom Commercial Communications Customer Preference Regulations, **2018** — issued 19 July 2018 | **in force from 28 February 2019**, per TRAI's own summary of the regulation | Nothing. No code sends an SMS |
| A sender must be registered, and messages carry a **registered header**; content is matched against a **registered template** | TCCCPR 2018 and the access providers' Codes of Practice | in force | Nothing |

**What this means for the product, and it is not a technical problem.** Entity registration, a
header and each message template are registered by the **business**, through the access providers'
DLT platforms — not by software, and not by me. Until the pilot restaurant's organisation holds a
registered header, an OTP the product sends is a message the network drops.

**So the code is not the long pole.** A token table, an expiry and a screen are a few days. The
registration is an owner action with a lead time nobody here controls, which is why F9 is not
built: shipping a recovery flow that cannot deliver is worse than shipping none, because it fails
at the moment somebody is already locked out.

**Verified to the level stated, and no further.** TRAI's own site gives the regulation, its date
and the DLT mandate. The operational specifics repeated everywhere — six-character alphabetical
headers for transactional traffic, template scrubbing at the network, penalty ceilings — come from
**vendor documentation, not from the instrument**, and are recorded here as *unverified*. Anyone
building this reads the Codes of Practice before relying on any of them.
| The invoice serial is consecutive, at most 16 characters, and unique per financial year | Rule 46(b) | in force | `test_every_invoice_number_a_year_can_reach_fits_the_rule`, `test_five_bills_settling_at_once_take_five_consecutive_numbers` |
| The financial year starts on 1 April | General Clauses Act 1897, s.3(21) | in force | `test_an_invoice_number_carries_its_year` |
| A cancelled invoice keeps its number | GSTR-1 Table 13 (documents issued) | in force (return practice) | `test_an_invoice_issued_in_error_is_cancelled_keeps_its_number_and_voids_its_order` |
| A reduction after issue is a credit note in its own series, against the invoice | CGST Act s.34; Rule 53 | in force | `test_a_credit_note_has_its_own_series_and_fills_sixteen_characters`, `test_crediting_every_portion_one_at_a_time_adds_up_to_the_bill_exactly` |
| A discount recorded on the invoice at supply comes off the taxable value | CGST Act s.15(3)(a) | in force | `test_an_order_discount_reaches_the_lines_to_the_paisa`, `test_a_comp_on_one_dish_takes_the_dish_and_its_tax_off_the_bill` |
| On a rate change, the rate follows two of three: supply, invoice, payment | CGST Act s.14 | in force; primary text not fetched, and four secondary sources agree | `test_the_median_is_before_exactly_when_two_of_three_are`, `test_a_bill_served_and_paid_before_a_rate_change_takes_the_old_rate` |
| No service charge by default, or under another name | CCPA guidelines, 4 Jul 2022; Delhi HC single judge, 28 Mar 2025 | in force at first instance; **unsettled** at appellate level, with an appeal pending | `test_no_order_carries_a_service_charge_it_was_not_given`, `test_a_service_charge_is_refused_where_the_restaurant_has_none` |

What the code must do:

- **The client never sends a price, a tax or a total.** The server prices every line
  (`test_a_price_sent_by_the_client_is_refused_and_changes_nothing`).
- **A settled bill is never edited**, and migration 0019 makes the database refuse it. Money going
  back is a credit note with a refund. It is never an edit, and never a cancellation.
- **Not decided here, and blocking nobody:** whether GST applies to a service charge (R17,
  **unsettled**), and whether packaging is taxed at the food rate (R18, **unverified**).

---

## B · Conditional — model the condition, not the outcome

### B1 · Calorie declaration
Binds establishments holding a **Central Licence** *or* operating **ten or more outlets**. Most
tenants of this product will not be covered; some will. The obligation is therefore a derived
per-restaurant flag, never a global setting. **The fields exist** (`calories_kcal`, `serving_size`,
backlog-issues B8); the derived applicability flag and publication gate do not yet — see §D.

### B2 · DPDP Act 2023 — build now, enforceable 13 May 2027
Rules notified 13 Nov 2025, commencing in three phases:

| Phase | Date | What commences |
|---|---|---|
| 1 | 13 Nov 2025 ✅ | Board constituted; complaints can be filed |
| 2 | 13 Nov 2026 | Consent Manager registration |
| 3 | **13 May 2027** | Notice, consent, security, breach, children's data, rights, penalties |


**Employee data is covered too, and by a different route — §7(i), researched 2026-09-19 for M17.**
The Act's Section 7 lists "legitimate uses" for which consent is *not* required, and clause (i) is:

> *"for the purposes of employment or those related to safeguarding the employer from loss or
> liability, such as prevention of corporate espionage, maintenance of confidentiality of trade
> secrets, intellectual property, classified information or provision of any service or benefit
> sought by a Data Principal who is an employee."*

So M17's performance measurement needs **no consent** — commentary treats performance evaluation as
squarely inside clause (i). Two things that does not settle, and they are the ones this file exists
to keep apart:

1. **It is not in force.** Phase 3 above is 13 May 2027. *Notified but not in force*, and only *in
   force* may block a user.
2. **Purpose limitation survives.** §7(i) covers employment purposes and nothing else. M17
   therefore does not export a score, share one outside the restaurant, or use one for anything the
   employee's own screen does not say it is used for.

**Retention, decided in M17's spec because it cannot be retrofitted:** a frozen `performance_score`
is kept for three financial years after its period, and is erased when the employee leaves **unless
an award was granted against it** — in which case it is kept with the award, as the record of why
money was paid.

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
| Allergens are a text statement, not a verified list | before M10 (guest app) | §A2 is met in text. A structured list or symbols needs the regulation's own list, read from the instrument |
| ~~No calorie applicability flag~~ | ~~M18~~ | **Closed 2026-09-19.** `labelling.calories` derives it per restaurant: the Central Licence test (digits 2–3 `00`) *or* ten or more active restaurants in the organization. No stored flag — a setting would be a second place to be wrong |
| No FSSAI registry status | M18 → deferred | The declared expiry date drives `fssai.expired` and `fssai.expiring`, and the malformed-number check runs once a bill has been issued. **FoSCoS status and last-verified remain unmodelled**: they need an integration the product does not have, and asserting a licence is live on the strength of a date somebody typed would be exactly the confident wrongness this file exists to prevent |
| ~~No rendered invoice document~~ | ~~M07 follow-up~~ | **Closed 2026-09-20.** The bill prints from the browser, with Rule 46's particulars laid out and Rule 5(1)(f)'s declaration at the top of a composition bill of supply. **The gap survived on a misreading**: it cited CLAUDE.md's exclusion of *printing*, but that exclusion is of "printer/hardware **drivers**" — and the product already browser-printed credit notes (D27). One word did sixteen modules of work |
| Documents-issued counts are not reported | M07 follow-up | A cancelled invoice keeps its number, which GSTR-1 Table 13 needs, but no report produces the counts or the serial ranges |

---

## How to add a rule here

1. Cite the instrument: name, number, date, and commencement date.
2. State whether it is **in force**, **notified but not in force**, **unsettled**, or
   **unverified**. Those are four different things and only the first is safe to build on.
3. Record the date you checked it. A rule with no check date is a rumour.
4. Name the test that enforces it, or say plainly that nothing does.
5. If it should reach an owner, add it to `app/core/compliance.py` — an evaluator, an instrument, a
   commencement, a `checked_on` date and a status. The catalogue is code rather than a table
   because a rule is a query plus a citation, and a query does not live in a row.
6. **A rule that is not in force cannot be critical.** The constructor will refuse it, and that is
   the point: it may inform, and it must not block.
