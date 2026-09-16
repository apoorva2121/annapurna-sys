# Competitor analysis

**Status: research, not scope.** Rewritten 2026-09-13 from three research passes covering 35
products. Nothing here changes a module. Every gap marked **keep** is filed in `docs/backlog.md`,
to be promoted into `docs/modules.md` between modules, never during one.

Research files, with every claim tagged and linked:

| File | Products | Strongest evidence | Weakest evidence |
|---|---|---|---|
| `competitor-research/01-platforms.md` | Petpooja, Restroworks, GoFrugal, Rista, PosBytz, DineOpen, Recaho, Restrofi, UrbanPiper, LimeTray, DotPe | Capterra reviews of Petpooja, GoFrugal, Restroworks | 63 of ~110 tags are vendor marketing; no public help centre found for the top three |
| `competitor-research/02-play-store-apps.md` | Vyapar Table, Arow, Zobaze, Namma Restaurant, Shopto, SOLO, myBillBook, GoRestro, BillSarthi, BoltBills | Zobaze and myBillBook reviews; published INR prices | No independent reviews for 7 of 10 apps; Play Store pages unreadable |
| `competitor-research/03-point-solutions.md` | MarketMan, Supy, Restaurant365, meez, Apicbase, Winnow, Orbisk, SalaryBox, EZHRM, 7shifts, SafetyCulture, Reelo, Hyperpure, Tenzo | 49 help-centre citations; 7shifts' 1,211 reviews | Winnow, Orbisk, EZHRM have almost no independent reviews |

**How to read a claim.** A vendor saying it has a feature is not evidence the feature works. Where a
verdict below rests only on marketing, the competitor is marked **(m)**. Nothing here was used
hands-on.

**Our state, as of 2026-09-13** (`docs/checklist.md`):
- **built**: code written and `make check` green. The manual pass is still pending for every module
  except M05, so *built* is not *done*. M07's gate is green in its build log; its checklist row is
  not yet ticked.
- **planned: Mxx**: a designed module, not built.
- **designed, unscheduled**: described in a doc (`docs/waste-model.md`,
  `docs/customer-experience.md`, `docs/onboarding-cold-start.md`,
  `docs/product/candidate-flagship-features.md`) but in no module.
- **out of scope, month 1**: excluded by CLAUDE.md.
- **missing**: in no doc and no module.

---

## 1 · The finding that matters most

Across 35 products, owners rarely complain that a feature is **absent**. They complain about five
things, and the same five appear in every tier:

| What customers punish | Where it was reported |
|---|---|
| **Support disappears after payment** | Petpooja ("too busy with expansion"), GoFrugal ("once they take amount… not responded"), Vyapar ("once package renewed, they don't attend any issues"), myBillBook, UrbanPiper, LimeTray, Restroworks |
| **The price changes underneath them** | Zobaze (free to paid), myBillBook (paid add-ons after a two-year purchase; charged after cancelling), SalaryBox (renewal jump), GoFrugal (training expires or costs ~30% of the software; KOT printing extra), MarketMan (12-month contract, 60-day notice) |
| **The numbers are wrong** | Zobaze (tax on the pre-discount price), myBillBook (alleged RCM / invoice-type error), Vyapar ("data disappeared and the calculations did not match"), Apicbase (sync bugs "make whole lines of reports useless"), Restaurant365 (unit-of-measure bug took weeks), Reelo (messages sent under **another restaurant's name**) |
| **Setup is too hard** | MarketMan ("really difficult to implement"), Apicbase ("complicated to setup"), Restroworks ("not beginner friendly… lots of manual inputs"), Restaurant365 (onboarding failed while billing continued) |
| **It is slow or down when it matters** | Petpooja (slow at peak), GoFrugal (slow on 32 GB hardware), LimeTray (server lag), 7shifts (login 404s), Restaurant365 (down during close week) |

**What follows.** Nobody has earned trust yet, so trust is open ground. Our product rules already aim
at the third row: an append-only ledger, prices worked out on the server, invoice rules with tests
citing the law, and a tenant-isolation test on every endpoint. Competitors treat those as internals.
**They should be the pitch**, backed by a demonstration rather than a claim. The other four rows are
decisions about pricing, support and onboarding, not code (§7).

---

## 2 · The market in one table

| Tier | Examples | Price seen | Wins on | Loses on | For us |
|---|---|---|---|---|---|
| All-in-one platforms | Petpooja, Restroworks, GoFrugal | Mostly unpublished; Petpooja ~₹3–12k/month per a competitor's blog (directional only) | Breadth, Swiggy/Zomato sync, 80+ reports, reach | Support, setup, training costs, speed at peak | The real competition. Beat on trust and on the insights they list but don't explain |
| Challenger platforms | Restrofi, PosBytz, Recaho, DineOpen, Rista | Restrofi free / ₹499 / ₹1,499 a month; PosBytz $39–199 a month; Recaho ~₹12,000 a year (third party) | Price, a free tier, AI labels | Almost no independent reviews; AI claims unverified | Sets a low price ceiling |
| Play Store apps | Vyapar Table, myBillBook, Zobaze, GoRestro, SOLO | ₹0 (BoltBills) to ~₹10,000 a year (SOLO); GoRestro ₹999–1,999 a year; myBillBook from ₹199 a month | Install to first bill in minutes, offline, cheap | Shallow (no costing or variance), GST bugs, pricing surprises, template resellers | Sets the expectation for speed and offline |
| Specialists | MarketMan, meez, Supy, Restaurant365, 7shifts, SafetyCulture, Reelo | $19–449 a month; Reelo ₹39,000/outlet/year; SalaryBox ₹1,500–3,000 a month | Depth in one area | Western assumptions, chain pricing, integration overhead | Sets the depth to beat in each area |

---

## 3 · Everything, area by area

**Verdicts.** **Parity**: needed just to be considered. **Beat**: we can do meaningfully better (§4).
**Later**: real, but not now. **Skip**: does not fit this market or product (§6).

### A · Billing, invoicing & GST

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| GST bill; credit notes in their own series; cancelled invoice keeps its number | Everyone claims it; Petpooja deepest (m) | **built** (M07), each rule with a named test (`docs/compliance-rules.md` §A7) | **Beat**: competitors have reported GST bugs; ours are tested against the cited rule |
| Discount reduces the taxable value | Zobaze gets this wrong (review) | **built**: `test_an_order_discount_reaches_the_lines_to_the_paisa` | **Beat** |
| Split / merge bills | Petpooja (m) | **built** (M07 split) | Parity |
| Printed or PDF bill | Everyone | **missing** (compliance §D; printing out of scope, month 1) | Parity: PDF and share first, printer later |
| Bill sent on WhatsApp / email | Vyapar, Shopto, BillSarthi, Rista, Zobaze (m) | **missing** | Parity. Cheap. **keep** |
| Zone pricing (AC hall vs non-AC) | SOLO (m) | **missing**: price lives on the variant only | Parity for India. **keep** |
| GSTR-1 register / documents-issued report | Petpooja (m), GoFrugal (m) | **missing** (compliance §D) | Parity. **keep** (already §D) |
| E-invoice to IRP, e-way bill | Petpooja Invoice (m) | out of scope, month 1 | Later. Who it applies to must be looked up, never assumed |

### B · Ordering & table service

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| Captain / waiter ordering on a phone | Petpooja, Recaho (free), Arow (m) | **built** (M07, PWA) | Parity |
| Take orders and bill **offline** | Petpooja, Zobaze (review), Shopto, BillSarthi, Vyapar (m) | out of scope, month 1 | Parity. **The most-cited table stake in 02.** **keep**, to decide before the pilot |
| QR self-ordering | 6 of 11 platforms (m) | planned M10 gives QR menu and feedback, not ordering | Later |
| Reservations, walk-in queue | Rista, GoRestro (m) | **missing** | Later |
| Honest wait quote at order time | none found | designed, unscheduled (`customer-experience.md` "Quoted time") | **Beat** |

### C · Kitchen

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| KDS by station | Petpooja add-on, GoFrugal, Restrofi, Zobaze (m) | planned M08 | Parity |
| KOT printed per station or food category | GoFrugal, SOLO (m) | out of scope (printers) | Later |
| Per-line prep timing | Restrofi claims "40% faster" with no method (m) | planned M08: five timestamps per ticket | **Beat**: feeds the CX time intervals and M17 |

### D · Menu

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| Variants, add-ons, veg / non-veg mark | Most | **built** (M03); mark differs by shape and colour, tested (§A1) | Parity; **Beat** on compliance |
| Allergen declaration | meez Enterprise | **missing**. Compliance §A2 is in force and this is its largest open gap | Parity (legal). **keep** (already §D) |
| Menu from a photo | Arow "AI menu upload" (m) | designed, unscheduled (cold-start) | **Beat**: match against the recipe library, not just extract text. **keep** |
| "Sold out today" without deactivating | Restrofi QR availability (m) | not in `modules.md` (deactivating ≠ sold out) | Parity. **keep**, verify M03 first |
| Menu engineering quadrant | Petpooja reports, meez Enterprise | planned M13 | Parity |
| One menu across outlets | Restroworks, GoFrugal (m) | out of scope (multi-branch) | Later |

### E · Recipes & food costing

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| Recipe cost with automatic stock deduction on sale | Petpooja, GoFrugal (m); MarketMan | **built** (M04: nested to depth 3, versioned, golden tests) | Parity |
| **A starter recipe library** | **none of 35 products** | **built**: `library/`, 223 dishes with confidence tiers | **Beat, unique** |
| Explains *why* a dish won't cost | meez's "Top 4 reasons" help article [help] | **missing** | **Beat**: we can compute the reason for each dish instead of documenting it. **keep** |
| Purchase unit ↔ recipe unit | meez's unit equivalency [help] | canonical base units (invariant 5); Indian pack units (`bori`, `tin`, `peti`) designed in the lexicon brief, unbuilt | **Beat** |
| What-if price / portion simulation | meez; Apicbase margin solver [help] | **missing** | Later (flagship #4) |
| Labour cost inside dish cost | Apicbase [help] | **missing** | **Skip** in that form (§6) |
| Sub-recipe held as its own stock | Apicbase [help] | **built** (preparations, M04/M05) | Parity |

### F · Inventory & stock

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| Batches, expiry, FEFO | GoFrugal (m) | **built** (M05): stock derived from movements, never edited | **Beat**: every number traces to a movement |
| Count templates, partial counts | MarketMan, Restaurant365 [help], Supy | **built** (M05); guided top-40 count designed | Parity |
| Several people counting at once, auto-merged | Supy (m) | **missing** | Later |
| Counting with no signal | Supy, MarketMan | out of scope (offline) | Parity eventually |
| Near-expiry becomes an action ("3.2 kg paneer: feature Paneer Tikka") | none found | designed, unscheduled (`waste-model.md` §2) | **Beat**. **keep** |
| **Daily prep sheet with a leftover loop** | **none found** | designed, unscheduled (`waste-model.md` §3 calls it "the highest-ROI feature in the entire product") | **Beat**. **keep, highest priority** |
| Par levels → drafted purchase order | MarketMan Growth, Supy (m) | **missing** | Later |
| Transfers needing the receiver's acceptance | Supy (m) | out of scope (multi-branch) | Skip for now |

### G · Procurement & suppliers

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| Suppliers, POs, goods receipts | GoFrugal (m), Supy, MarketMan | **built** (M06) | Parity |
| Ordered, billed and **weighed** kept as three numbers | none claims weighing at the gate | **built** (M06); one short delivery seeded | **Beat** |
| Photo or WhatsApp bill → draft receipt | Petpooja Purchase (m), MarketMan (m): trained on printed invoices | designed, unscheduled (flagship #1) | **Beat**: handwritten `kachcha` bills, Devanagari, loose units; proposes, never writes. **keep** |
| Supplier price history, cross-supplier compare | Petpooja Purchase (m), GoFrugal vendor analysis (m) | partial: 122 real market prices plus a city index | **Beat**: a neutral benchmark, unlike Hyperpure (a supplier owned by the aggregator). **keep** |
| Forwarded-email invoice intake | MarketMan Enterprise, meez Premium | **missing** | Fold into flagship #1 |

### H · Theoretical vs actual variance

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| Theoretical vs actual report | Petpooja (m), MarketMan, Supy, Restaurant365 [help] | planned M13 | Parity |
| **Finding the cause** | Restaurant365's WEPT (Waste / Errors / Portioning / Theft) [help]: a *manual* walk the manager does | designed, unscheduled (flagship #2) | **Beat**: automate the walk and separate staff meals and comps from theft (`waste-model.md` §4). **keep** |
| Waste logged in under 10 s | GoFrugal, Petpooja (m) | planned M09: cost shown after logging, never before | Parity; **Beat** on honesty of reporting |
| Automatic waste capture by camera and scale | Winnow, Orbisk | **missing** | **Skip** (§6) |

### I · Aggregators & online ordering

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| Swiggy / Zomato orders and menu sync | Petpooja, UrbanPiper, SOLO (m); GoFrugal resells UrbanPiper | out of scope, month 1 | Parity. **The #1 sales objection.** **keep**: integrate through a hub rather than build connectors |
| Swiggy / Zomato export to backfill months of demand | none found | designed, unscheduled (cold-start "Never trust no data") | **Beat**. **keep** |
| Aggregator panel inside the POS | Petpooja only | n/a | Skip |
| ONDC; own ordering site | GoFrugal, Rista; DotPe, Shopto (m) | **missing** | Later |

### J · Payments & cash

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| Till counted blind at close, shortfall recorded and never corrected away | **none found** | **built** (M07); a ₹50 short till is seeded | **Beat** |
| UPI QR printed on the bill | SOLO (m) | **missing** (needs no payment gateway) | Parity. Cheap. **keep** |
| Running tab / credit (*udhaar*), partial payments | Rista (b) | **missing** | Parity for India. **keep** |
| Matching cash / UPI / card to bank payouts | Petpooja Finance (m) | payments recorded; gateway out of scope | Later |

### K · Customers, feedback, loyalty

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| Customer profile, history, preferences | GoFrugal, Zobaze, Shopto (m) | planned M10 | Parity |
| Three-tap feedback at the table, linked to the order | Arow: anonymous QR (m) | planned M10 | **Beat**: linked to the order, so it reaches the dish, waiter and station |
| Complaint → owner → deadline → did they come back | none found | planned M10 complaint workflow + `customer-experience.md` | **Beat** |
| Regular recognised on the waiter's screen; alert when a regular stops coming | Reelo win-back campaigns | designed, unscheduled (`customer-experience.md`) | **Beat**: one phone call, no campaign spend. **keep** |
| Loyalty (points / visits / spend) | Reelo, Rista, Petpooja (m) | **missing** | Later |
| Behaviour segments + WhatsApp campaigns with revenue attribution | Reelo | **missing** | Later: build on M10's consent records. Reelo's wrong-restaurant-name bug is exactly our invariant 1 |
| Consent recorded per purpose | none found | planned M10 (compliance §B2: core duties commence 13 May 2027) | **Beat** |

### L · Staff

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| Roles and permissions | Everyone | **built** (M01) | Parity |
| Clock in / out | Petpooja Attendo, SalaryBox (m) | planned M12, minimal | Parity |
| Attendance that resists clocking in for a colleague (selfie, geofence, QR kiosk) | SalaryBox (m) | **missing** | Later |
| Payroll with PF / ESI / PT / TDS | SalaryBox, EZHRM, Attendo (m) | **missing** | **Skip / integrate** (§6) |
| Labour budget against forecast sales while building the roster | 7shifts [help] | **missing** | **Skip** in its hourly form (§6) |
| **Workload fairness** | **none found** | planned M17, with eight open questions (`docs/workload-fairness.md`) | **Beat, unique** |
| Shift handover notes, side-work tasks | 7shifts paid add-ons | planned M11 | Parity |
| Staff health-certificate expiry | EZHRM, SalaryBox market it as FSSAI (m) | **missing** | Later. Legal basis **unverified**; if confirmed and cited, an M18 rule |

### M · Reports, analytics, AI

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| Report count (Petpooja: 80+) | Petpooja (m) | planned M13: a handful, each with a baseline and drill-through | **Beat** on meaning, not count |
| Export for the accountant (Tally) | GoFrugal (m), Rista (b), SalaryBox Enterprise | CSV planned M13; Tally **missing** | Parity for India. **keep** |
| Demand forecast | Restroworks (m), Supy, 7shifts, Tenzo | **missing** (flagship #3) | **Beat** later: Indian festival calendar, plus stating when the forecast becomes reliable (Tenzo's 90-day floor is the only one published) |
| Separate owner monitoring app | SOLO | PWA on the owner's phone | Parity |
| Ask-your-data chat | Restrofi RestroAI (m) | **missing** | **Skip** (flagship #5) |
| AI voice ordering in Indian languages | DineOpen (m, no independent reviews) | **missing** | **Skip** |

### N · Compliance & food safety

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| **A warning before a decision puts the licence at risk** | **none found**; competitors store documents | planned M18 | **Beat, unique** |
| FSSAI licence number on the bill | Petpooja (m) | **built** (§A3: format-checked, audited on change) | Parity |
| Food-safety checklists → corrective action with owner and due date | SafetyCulture [help] | **missing**; M11 tasks could host it | Later. **keep** |
| Temperature logs | SafetyCulture IoT sensors [help] | **missing** | Later: a manual log first; sensors must survive power cuts |

### O · Multi-outlet

Central kitchen, multi-brand, cross-outlet menu and stock: Restroworks, Petpooja, Supy.
**Out of scope, month 1.** `library/` already stands in for an org-level recipe master (backlog S11).
Later.

### P · Platform, hardware, integrations

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| Offline | Every Play Store app (m) | out of scope, month 1 | Parity. Highest-risk gap (see B) |
| Thermal printers, cash drawer | Most | out of scope, month 1 | Parity, later |
| Staff screens in Indian languages | Arow claims 11 languages (m) | **missing** | Parity for staff screens. **keep** (also M17 open question 6) |
| Fast at peak | Complaints about Petpooja, GoFrugal, LimeTray | performance budgets set: M08 ticket list 50 ms, M13 dashboard p95 800 ms | **Beat**, if held under load (M16 k6) |

### Q · Onboarding

| Capability | Best in market | Us | Verdict |
|---|---|---|---|
| Time to go live | GoFrugal "one day" (m); Reelo 24–48 h, vendor-run (m); Supy ~15 days (review); MarketMan paid install | target **under two hours** for a 120-dish menu (`onboarding-cold-start.md`) | **Beat**, if met |
| Useful on day one with zero history | none found; Tenzo needs 90 days | designed: dish margin on day one, then a stated countdown per screen | **Beat** |
| Free tier / trial | Restrofi, 7shifts Comp, Reelo, SafetyCulture free; PosBytz 14 days | undecided | Decision (§7) |
| Training included | GoFrugal charges ~30% (review) | undecided | **Beat** by policy (§7) |

---

## 4 · Where we beat the best version of each feature

The standard for this section: name a competitor's **actual** best version and its **documented**
limit, then show our version is credible because something already exists (a built module, a
product rule, a design doc), not because we intend it.

| # | Their best version | Its documented limit | Our version | Why it is credible |
|---|---|---|---|---|
| 1 | **Starter recipes:** none. Every product assumes you enter your own (MarketMan: "the single biggest time-to-value cost") | Setup is the top specialist complaint | Match your menu to 223 Indian dishes with confidence tiers; the chef corrects instead of writing from scratch | **Built**: `library/`, validated in `make check` |
| 2 | **Bill digitisation:** Petpooja Purchase and MarketMan OCR, including handwriting (m) | Trained on printed Western invoices; neither documents what happens to a line it can't match | Photo or WhatsApp → a draft with per-line confidence, resolved to the canonical ingredient and base unit, with Indian pack units; **proposes, never writes** | Flagship #1 and the lexicon brief; the ledger already refuses edits (invariant 2) |
| 3 | **Variance cause:** Restaurant365's WEPT, a manual walk from category to item to invoice to recipe [help] | The manager does the investigation; theft sits in the same bucket as staff meals | The walk automated and ranked in rupees, with staff meals and comps as separate movement types, so honest staff aren't accused | Flagship #2; `waste-model.md` §4; M17's rule against published bottom rankings |
| 4 | **Receiving:** three-way matching of PO, invoice and receipt (MarketMan, Supy) | Nobody claims to weigh at the back door | Ordered, billed and **weighed** kept as three numbers, rolled up per supplier over time | **Built** (M06) |
| 5 | **GST billing:** "GST-compliant" on every app | Tax on the pre-discount price (Zobaze), RCM mishandled (myBillBook) | Each invoice rule tested against the cited instrument; the server prices every line | **Built** (M07); `compliance-rules.md` §A7 |
| 6 | **Compliance:** FSSAI documents stored (Petpooja (m), EZHRM (m)) | Stored, not watched | Warns before a menu, price or tax decision creates licence risk; four legal states never conflated; keeps the record | Planned M18, rules drafted with instruments |
| 7 | **Waste:** Winnow / Orbisk cameras, zero-effort capture | Western food images, quote-only pricing, hardware, no independent reviews | A prep sheet that measures leftover per batch (the largest waste stage, 4–8%) with no hardware | `waste-model.md` §3 (designed, unscheduled) |
| 8 | **Forecasting:** Tenzo, 7shifts (95% / 90% claims) | Tenzo needs 90 days; 7shifts documents nothing for a new restaurant | The Indian festival calendar as features; every screen says when it will become useful, never a blank | Flagship #3, demand-calendar brief, cold-start empty-state rule |
| 9 | **Staff measurement:** SalaryBox / Attendo attendance, 7shifts labour cost | Measures presence and cost, not fairness | Workload distribution that exposes an unfair roster, with guardrails published | Planned M17, ADR 0011 |
| 10 | **Customer marketing:** Reelo RFM segments and WhatsApp campaigns | Sent messages under the wrong restaurant's name; fees "2.5× higher" (review) | Recognise the regular at the table; flag the regular who stopped; consent recorded per purpose; tenant isolation tested on every endpoint | `customer-experience.md`; invariant 1; planned M10 |
| 11 | **Till:** a cash-in-drawer total at best (not found anywhere) | Shortfalls vanish into "adjustments" | Counted blind, shortfall recorded and never corrected away | **Built** (M07) |
| 12 | **Costing errors:** meez's help article listing four causes | The customer diagnoses it by reading an article | Each dish that can't cost says exactly which ingredient, unit or sub-recipe is missing | M04's cost rollup already walks the tree; the reason is a by-product |

---

## 5 · What we are missing, ranked

Every **keep** item is filed in `docs/backlog.md` under the source *Competitor analysis,
2026-09-13*.

**Tier 1: blocks a sale or breaks a rule**
1. **Offline ordering and billing**: every cheap app has it; power and network cuts are ordinary.
   Out of scope for month 1 by CLAUDE.md. Decide before the pilot, not after the first outage.
2. **Swiggy / Zomato orders**: the first objection from any delivery-heavy restaurant. Integrate
   through an aggregation hub (UrbanPiper already serves other POS vendors) rather than build
   connectors.
3. **A bill the customer can receive**: PDF, WhatsApp share, then printer (compliance §D).
4. **Allergen declaration**: in force (§A2), already the largest open compliance gap (§D).
5. **Tally export**: what the restaurant's accountant uses.

**Tier 2: our differentiators, designed but in no module**
6. **Daily prep sheet** with leftover logging (`waste-model.md` §3).
7. **Bill-to-ledger** from a photo or WhatsApp (flagship #1). Without it, the variance number has
   no input.
8. **Variance attribution** (flagship #2).
9. **Menu from a photo**, matched against the library.
10. **Near-expiry → action.**
11. **Regular recognition and "a regular stopped coming".**
12. **"Why this dish won't cost" explained per dish.**
13. **Swiggy / Zomato export backfill** for demand history.

**Tier 3: cheap parity for India**
14. Zone pricing (AC vs non-AC).
15. UPI QR on the bill.
16. Running tabs / *udhaar* with partial payments.
17. Staff screens in Hindi and Marathi first.
18. GSTR-1 register and documents-issued report (§D).
19. "Sold out today" separate from deactivating a dish.

**Tier 4: later, after real data exists**
Loyalty and consented WhatsApp campaigns · attendance that resists proxy clock-ins · reservations
and QR self-ordering · par levels → drafted PO · food-safety checklists with corrective actions and
temperature logs · festival-aware forecasting · e-invoicing, once its applicability is looked up.

---

## 6 · What not to copy, and why

| Feature | Who | Why not |
|---|---|---|
| Camera and scale waste capture | Winnow, Orbisk | Hardware and quote-only pricing for a cash-constrained outlet; recognition trained on non-Indian food (a thali's mixed leftovers is unverified); no independent reviews. The prep sheet gets most of the saving with no hardware |
| Labour hours × hourly rate in dish cost; live labour budget while rostering | Apicbase, 7shifts | Assumes hourly wages; Indian kitchen staff are mostly on monthly salaries. If ever built, allocate salary share, not punched hours |
| Payroll with statutory deductions | SalaryBox, EZHRM, Attendo | A regulated domain where every rate changes, and our rule is never to fill a rate from memory. Integrate or export; don't own it |
| Count posts straight to the general ledger | Restaurant365 | Assumes formal double-entry accounts, which most single outlets don't keep. Tally export meets the real need |
| Swiggy's panel inside the POS | Petpooja | Only reachable as the aggregator's chosen partner |
| Ask-your-data chat; AI voice ordering | Restrofi, DineOpen | Unverified claims, no independent reviews; a new way to be confidently wrong (flagship #5) |
| Being the supplier | Hyperpure | Channel conflict (the aggregator taking a commission on sales and a margin on costs), and not software. Benchmark prices against it instead |
| Free app, then paywall the reports | Zobaze | The most reliable way found to create one-star reviews |

---

## 7 · Commercial lessons (decisions, not code)

These follow directly from §1. Nothing here sets a price. `docs/checklist.md` still has "Pricing
drafted" open.

1. **Publish the price list.** meez is the only product in 35 with every tier and add-on public;
   Restrofi and GoRestro show INR prices openly. Quote-only pricing is common at the top and
   distrusted at the bottom.
2. **Never take away what was free.** If a tier changes, existing customers keep what they had.
   Zobaze's and myBillBook's reviews show the cost of breaking this.
3. **Training and onboarding are included**, not an add-on (GoFrugal ~30% complaint), and onboarding
   is measured against the two-hour target.
4. **Support is part of the product.** Every error already carries a `request_id`. Making error
   messages say what went wrong and how to fix it (raised in the M03 manual pass on 2026-09-13) is
   the first piece of that.
5. **Show correctness, don't just claim it.** A demo that settles a discounted bill and shows the tax
   worked out correctly, then a till counted short, is something no competitor demo shows.
6. **Price anchors found** (all dated 2026-09-13, sources in the research files): free (BoltBills,
   Restrofi's free tier); ₹999–1,999 a year (GoRestro); ~₹8,000–12,000 a year (SOLO, Namma, Recaho);
   ₹6,000–18,000 a year (Restrofi paid); ₹39,000/outlet/year for CRM alone (Reelo); Petpooja
   ~₹3,000–12,000 a month (a competitor's blog, directional only).

---

## 8 · Risks this analysis exposes

- **What's built today competes on table stakes plus the library.** Items 2–12 in §4 mostly aren't
  built. A pitch that presents planned modules as present would repeat the competitors' worst
  habit.
- **Offline and aggregators** (§5, items 1–2) are the two objections likeliest to end a pilot
  conversation.
- **The price floor is near zero** at the bottom of the market, so the product must sell outcomes
  (rupees recovered from waste, short deliveries, till shortfalls), not features.
- **Evidence is uneven.** The all-in-one tier is judged mostly from marketing. Petpooja's variance
  report and bill OCR may be deeper, or shallower, than they appear.

## 9 · Verify by hand before relying on this

- [ ] Petpooja demo: does the Consumption Report show theoretical vs actual per ingredient, and does
      it say *why*?
- [ ] Petpooja Purchase: photograph a handwritten *kachcha* bill with Hindi item names. What
      happens to lines it can't match?
- [ ] Install myBillBook and Vyapar Table: time from install to first bill; try a discounted bill
      and check the GST.
- [ ] Ask two restaurant owners: which would make them switch (offline, Swiggy/Zomato, price,
      support)?
- [ ] Record each competitor's quoted price, with the date checked.
