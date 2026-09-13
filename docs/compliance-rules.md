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

### A7 · The bill, the invoice, and what may change after it (M07)

Checked 2026-09-13 for `docs/modules/M07-orders-spec.md`. Its research table (R1–R19) carries every
source. The statuses below are copied from that table, not re-derived.

| Rule | Instrument | Status | Enforced by |
|---|---|---|---|
| A composition restaurant may not collect tax, and issues a bill of supply | CGST Act s.10; Rule 49 | in force | `test_a_composition_restaurant_puts_no_tax_on_the_bill`, `test_a_composition_restaurant_issues_a_bill_of_supply_with_no_tax`, and migration 0019's check |
| A tax invoice carries the supplier's GSTIN | CGST Rules, Rule 46 | in force | `test_a_regular_restaurant_without_its_gstin_cannot_issue_a_tax_invoice` |
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
| No rendered invoice document | M07 follow-up | Rule 46's particulars and the restaurant's identity are stored on `invoice` at settlement, but nothing lays them out for a customer: no print, no PDF, and no Rule 5(1)(f) heading on a composition bill of supply. Printing is out of scope for month 1 (CLAUDE.md) |
| Documents-issued counts are not reported | M07 follow-up | A cancelled invoice keeps its number, which GSTR-1 Table 13 needs, but no report produces the counts or the serial ranges |
| `food_type` not in `app/core/enums.py` | M03 revisit | Violates CLAUDE.md's enum convention — currently a CheckConstraint plus two regexes plus a separate frontend type |

---

## How to add a rule here

1. Cite the instrument: name, number, date, and commencement date.
2. State whether it is **in force**, **notified but not in force**, **unsettled**, or
   **unverified**. Those are four different things and only the first is safe to build on.
3. Record the date you checked it. A rule with no check date is a rumour.
4. Name the test that enforces it, or say plainly that nothing does.
