# 03 — Single-purpose ("point") tools: best-in-class specialists

## Scope, date, method, caveat

- **Scope.** This file covers single-purpose specialist tools relevant to a single-outlet Indian
  restaurant SaaS: inventory/food-cost/variance (Supy, MarketMan, Restaurant365, meez, Apicbase),
  food-waste measurement (Orbisk, Winnow), staff/roster/attendance/payroll (SalaryBox, EZHRM,
  7shifts), food-safety/checklists (SafetyCulture), and India-specific extras (Reelo, Zomato
  Hyperpure, and a sales/labour-forecasting tool). It does **not** re-research the all-in-one
  platforms in `01-platforms.md` or the Play Store billing apps in `02-play-store-apps.md` — only
  their "Merged feature table" sections were read, to avoid duplicate rows.
- **Date.** Research conducted 2026-09-13. Pricing and product claims are dated at the point of
  citation; "contact sales" is recorded as unknown rather than guessed.
- **Method.** Public sources only: vendor help-centres/knowledge bases (priority — MarketMan,
  Restaurant365, 7shifts, SafetyCulture, Apicbase and meez all publish one), vendor marketing
  pages, Capterra/SoftwareAdvice/SelectHub/G2 (G2 often 403s), Techjockey for Indian products, and
  Reddit (r/restaurateur, r/KitchenConfidential) for unfiltered opinion. Every claim below carries
  an evidence tag — `[help]`, `[pricing]`, `[marketing]`, `[review]`, `[blog]` — with a source URL.
  Where nothing was found, this file says "not found" rather than filling the gap.
- **Caveat.** This is desk research from public sources, not hands-on use of any of these products.
  No claim here should be read as verified by direct testing. Indian regulatory/rate claims are
  out of scope for this file (see `docs/compliance-rules.md` for that domain) — nothing here should
  be used to fill an Indian rate, threshold or commencement date.

---

## Products covered

Fourteen products, all researched: **MarketMan, Supy, Restaurant365, meez, Apicbase** (inventory /
food cost / variance / recipes); **Winnow, Orbisk** (food waste measurement); **SalaryBox, EZHRM,
7shifts** (staff / rosters / attendance / payroll); **SafetyCulture** (food safety / checklists /
compliance); **Reelo, Zomato Hyperpure, Tenzo** (India-specific extras — reasoning for each is in
its own section below). No further extras were added beyond the three named in the brief: the
fourteen already give full coverage of every required capability area (E, F, G, H, K, L, M, N, Q)
with at least one deep example each, and two of the three India extras (Reelo, Hyperpure) already
carry India-specific evidence that a fourth or fifth generic addition would not have improved.

---

## Product sections

<!-- PRODUCT_SECTIONS_START -->

### MarketMan — inventory / food cost / variance

**Target.** Independent restaurants up to small multi-unit chains; positions itself as an
inventory-and-purchasing specialist that plugs into a POS rather than replacing one [marketing]
(https://www.marketman.com/platform/restaurant-inventory-management-software).

**Pricing (as found 2026-09-13 — two inconsistent published figures, both cited).**
- Capterra/search-summary route: Starter $199/mo, Growth $249/mo, Enterprise custom; ~15%
  discount annual; $500 one-time install fee (waived in a July-2026 promo) [pricing]
  (https://www.capterra.com/p/136439/Marketman-Restaurant-Inventory/pricing/).
- Vendor pricing page fetched directly: Starter $249/mo, Growth $299/mo, Enterprise from
  $449/mo, plus metered add-ons (API access $25–199/mo by location count; Commissary module
  $499–749/mo) [pricing] (https://www.marketman.com/pricing-for-restaurant-inventory-management-system).
  The two sources disagree by $50/tier — flagged as unresolved rather than averaged; a reviewer
  ([review] https://dishcost.com/blog/dishcost-vs-marketman) separately cites "$199-249/mo,
  12-month contract," suggesting the lower figures may be stale/legacy pricing. Enterprise is
  effectively "contact sales" (custom).
- 60-day cancellation notice and (per user reports) a 12-month contract are recurring complaint
  themes, not vendor-stated terms [review] (https://checkthat.ai/brands/marketman/reviews).

**Core workflow, step by step.**
1. **Setup (one-time, human-supplied data).** Restaurant enters its inventory item list
   (ingredients, packaging), builds recipes/sub-recipes with yields, sets par levels per item,
   registers suppliers, and connects its POS and (optionally) accounting system (QuickBooks,
   Xero, Sage Intacct) [help/marketing] (https://www.marketman.com/page/perpetual-inventory).
   This item-and-recipe entry is the single biggest time-to-value cost — nothing downstream works
   without it.
2. **Receiving (invoice to stock).** Staff photograph a paper or emailed supplier invoice with the
   mobile app; OCR digitizes it and matches line items to existing inventory items (handwritten
   invoices are explicitly supported, not just printed ones) [marketing]
   (https://www.marketman.com/page/restaurant-invoice-management-system). A received invoice
   posts a stock-in movement and updates the item's cost (price tracking/alerts flag cost
   increases). Enterprise tier adds email-based invoice ingestion (forward invoices to an
   address) [pricing] (https://www.marketman.com/pricing-for-restaurant-inventory-management-system).
3. **Sale (POS to theoretical depletion).** Each POS sale explodes the sold menu item's recipe and
   deducts the theoretical ingredient quantities from the perpetual inventory balance
   automatically — this is the "perpetual inventory" the product is named for [marketing]
   (https://www.marketman.com/page/perpetual-inventory).
4. **Physical count (actual).** Staff perform a count via the mobile app — barcode scan, manual
   entry, or "shelf-to-sheet" sheets ordered to match physical storage layout — on a schedule the
   operator sets (daily for high-value/fast-moving items like proteins and alcohol, weekly for dry
   goods; partial counts are supported so a full count isn't required every time) [marketing/blog]
   (https://www.getsauce.com/post/taking-stock-marketman-cloud-based-restaurant-inventory-management).
   The app works offline in a walk-in and syncs once reconnected.
5. **Variance.** MarketMan compares the theoretical balance (POS deductions since the last count)
   against the actual count and produces a variance report per item — the gap surfaces waste,
   theft, over-portioning or receiving errors [marketing] (https://www.marketman.com/page/perpetual-inventory).
   Reports roll up into COGS, food-cost %, profitability and waste dashboards.
6. **Ordering loop (Growth+).** "Order by recipe" and vendor price comparison let the system
   suggest or place purchase orders against par levels; Enterprise adds "AI ordering" [pricing]
   (https://www.marketman.com/pricing-for-restaurant-inventory-management-system).

**What it automates vs. asks a human.** Automates: theoretical depletion on sale, invoice line
matching (OCR), cost/price-change alerts, variance arithmetic, COGS roll-up. Still needs a human
for: initial item/recipe/par setup, the physical count itself (no computer-vision auto-count
found), reconciling OCR mis-reads on messy invoices, and deciding what to do about a variance.

**Handling of bad/missing data.** OCR is designed for handwritten invoices, which suggests
tolerance for messy supplier paperwork, but no help-centre article was found describing what
happens when OCR cannot match a line item to an existing inventory item (queued for manual match,
or silently dropped?) — not found; flagged as a gap.

**Feature-area bullets.**
- E (Recipes & costing): recipe/sub-recipe costing tied to live ingredient prices; "unlimited
  AI-powered recipe creation" and "AI recipe optimization" at Growth+ [pricing]
  (https://www.marketman.com/pricing-for-restaurant-inventory-management-system).
- F (Inventory): perpetual (real-time, POS-linked) inventory; barcode/manual/shelf-to-sheet counts;
  offline mobile counting [marketing] (https://www.marketman.com/page/perpetual-inventory).
- G (Procurement): OCR invoice capture (handwritten + digital), vendor EDI integrations (1 at
  Starter, up to unlimited at Enterprise), purchase-order placing/receiving, price-change alerts
  [pricing/marketing] (https://www.marketman.com/pricing-for-restaurant-inventory-management-system).
- H (Variance): theoretical-vs-actual variance report is the product's core output [marketing]
  (https://www.marketman.com/page/perpetual-inventory).
- P (Integrations): POS integrations (Square named explicitly) plus accounting integrations
  (QuickBooks, Xero, Sage Intacct) [marketing] (https://www.marketman.com/page/square-restaurant-inventory-management).
- Q (Onboarding): setup requires full item/recipe/par/supplier data entry before value; a $500
  one-time install fee (sometimes waived) signals vendor-assisted onboarding is the norm, not
  self-serve [pricing] (https://www.capterra.com/p/136439/Marketman-Restaurant-Inventory/pricing/).
- R (Pricing): per-location SaaS subscription with metered add-ons (API calls, Commissary module)
  — see pricing block above.

**What users complain about.**
1. Setup/implementation difficulty for new users: "I find it really difficult to implement,
   especially getting it started" — Natalie J. [review]
   (https://www.capterra.com/p/136439/Marketman-Restaurant-Inventory/reviews/).
2. POS integration gaps persisting for years: "was never integrated with our POS system — which
   made it clunky and inefficient... If not I wouldn't consider them" — Jon D. [review]
   (https://www.capterra.com/p/136439/Marketman-Restaurant-Inventory/reviews/).
3. Cancellation/retention friction: 60-day notice, "forced retention calls," a customer "misled by
   a sales deal that pushed us to pay for a full year upfront" and then refused a refund [review]
   (https://checkthat.ai/brands/marketman/reviews).
4. Weak mobile app: "the very poor smartphone app" forcing laptop use — Ken W.; "wished the mobile
   app was a little more developed" — David F. [review]
   (https://www.capterra.com/p/136439/Marketman-Restaurant-Inventory/reviews/).

**What users praise.**
- Time saved on invoice capture/vendor management: "Saves me a ton of time" — Brandon K. [review]
  (https://www.capterra.com/p/136439/Marketman-Restaurant-Inventory/reviews/).
- Ease of use for managers with little training: "Very intuitive... does not require a lot of
  training" — Dan C. [review] (same URL).
- Customer support during onboarding: "a great business partner and provides the best customer
  service" — Frank C. [review] (same URL).
- Multi-location cloud reporting: "Cloud-based access and reporting that make it easier to manage
  multiple locations" — Dhinesh E. [review] (same URL).

### Supy — inventory / procurement / food-cost variance (multi-branch focus)

**Target.** Multi-branch F&B groups (Supy is built in Dubai, positions itself for "multi-branch
F&B" across 30+ countries) rather than single-outlet independents — relevant here as the ceiling
for variance root-cause analysis, even though the target segment is larger than this product's
[marketing] (https://supy.io/platform/restaurant-inventory-management-software).

**Pricing (2026-09-13).** Published starting price "from $250/month" on the vendor's own pricing
page, but framed as "tailored pricing" — final price depends on location count and payment terms,
via demo/quote [pricing] (https://supy.io/supy-pricing). One flat plan covers unlimited users per
location; add-ons (AI ordering, ERP integration, dedicated success manager, central-kitchen
operations, Power BI/Tableau plugins) are priced separately and not disclosed publicly [pricing]
(https://supy.io/supy-pricing). No free tier or public trial found.

**Core workflow, step by step (theoretical-vs-actual variance, the product's flagship claim).**
1. **Setup.** Recipes are entered with ingredient yields and prep wastage factored in; POS
   integration (50+ POS integrations claimed, with new ones "built at no charge... before
   implementation") links each sold item to its recipe [marketing] (https://supy.io/supy-pricing;
   https://supy.io/blog/learn-theoretical-vs-actual-food-cost-variance).
2. **Receiving.** Deliveries are logged as goods-received notes against purchase orders, updating
   stock and cost [blog] (https://supy.io/blog/learn-theoretical-vs-actual-food-cost-variance).
3. **Stock count.** Counts use reusable, shelf-ordered templates; multiple staff can count
   different sections of the same site in parallel and the app auto-merges their submissions —
   Supy claims this cuts count time by "over 50%" versus ad hoc counting. Counting also works
   offline in a "dead zone," syncing once connectivity returns — a specific, named feature rather
   than an implied one [marketing/blog] (https://supy.io/blog/learn-restaurant-stock-count-offline;
   https://supy.io/blog/learn-restaurant-stock-management-software).
4. **Theoretical cost.** Computed as recipe cost × units sold from POS, i.e. "what food cost
   should be if every portion were made exactly to recipe, with no unrecorded spoilage, no waste
   beyond yield allowances" [blog] (https://supy.io/blog/learn-theoretical-vs-actual-food-cost-variance).
5. **Actual cost.** Derived from stock movements and deliveries — what was actually spent/consumed
   [blog] (same URL).
6. **Variance & root-cause isolation.** The gap between theoretical and actual is computed and
   shown at group, site, menu-category and individual-item granularity — explicitly designed so a
   high-performing site cannot mask an underperforming one in a blended, chain-wide number. The
   worked example in Supy's own explainer names three concrete causes an operator would then dig
   into: stale recipe costs (example: ~$840/week variance from one recipe), unrecorded spoilage
   (~3.2% of purchases), and portion inconsistency (~$2,580/month at one site) — diagnosed by
   sorting sites by variance size, then drilling into item-level usage and waste logs [blog]
   (https://supy.io/blog/learn-theoretical-vs-actual-food-cost-variance). A customer testimonial
   claims "food cost has dropped from 39% to 33%, and variance is down from 15% to 9%" after
   adoption [marketing] (https://supy.io/blog/learn-restaurant-stock-management-software) —
   vendor-supplied and not independently corroborated.
7. **Ordering loop.** "AI Predictive Ordering" builds a ready-to-submit purchase order from a
   14-day AI sales forecast run through recipe logic against current stock [marketing]
   (https://supy.io/blog/learn-restaurant-stock-management-software).
8. **Transfers.** Inter-branch stock transfers require the receiving branch to explicitly accept
   before the stock adjustment is applied — a control against silent shrinkage in transit
   [marketing] (https://supy.io/blog/learn-restaurant-stock-management-software).

**What it automates vs. asks a human.** Automates: theoretical-cost calculation, variance
arithmetic and multi-level roll-up, purchase-order drafting from forecast + recipe + stock.
Human-required: the physical count (parallelized but still manual), recipe/yield data entry,
interpreting *why* a specific site's variance is high (the tool surfaces the number and lets an
operator drill in, it does not diagnose root cause automatically).

**Handling of bad/missing data.** The offline stock-count feature is the one explicit
bad-conditions design decision documented (a count started with no connectivity is not lost, and
syncs later) [blog] (https://supy.io/blog/learn-restaurant-stock-count-offline). No help-centre
article was found on OCR/invoice error-handling or on what happens to a count when an item has no
recipe attached — not found.

**Feature-area bullets.**
- E: recipe costing with explicit prep-wastage/yield modeling [blog]
  (https://supy.io/blog/learn-theoretical-vs-actual-food-cost-variance).
- F: real-time multi-branch stock; parallel-counter templates; offline-capable counting; wastage
  logged by item/quantity/reason with cost impact by branch and period [marketing]
  (https://supy.io/blog/learn-restaurant-stock-management-software).
- G: requisitions, POs, supplier management, invoices, 50+ POS integrations, accounting
  integration [pricing] (https://supy.io/supy-pricing).
- H: theoretical-vs-actual variance at group/site/category/item granularity, explicitly designed
  to prevent blended-figure masking across sites — the deepest multi-site variance drill-down
  found in this whole research set [blog] (https://supy.io/blog/learn-theoretical-vs-actual-food-cost-variance).
- M: 14-day AI sales forecast driving auto-drafted purchase orders; BI dashboards; Power
  BI/Tableau plugin add-on [marketing/pricing] (https://supy.io/blog/learn-restaurant-stock-management-software;
  https://supy.io/supy-pricing).
- O: built specifically for multi-branch/central-kitchen operation (transfer accept/reject
  workflow, central-kitchen add-on) [marketing/pricing] (https://supy.io/blog/learn-restaurant-stock-management-software;
  https://supy.io/supy-pricing).
- Q: vendor case-mention of "setup... straightforward and quick, completed within fifteen days"
  [review] (https://www.g2.com/products/supy/reviews, via search snippet — G2 itself 403'd to
  direct fetch, so this is a secondhand quote, flagged accordingly).
- R: single tailored plan from $250/mo, quote-based beyond the headline figure, add-ons priced
  separately and undisclosed [pricing] (https://supy.io/supy-pricing).

**What users complain about.** Independent review access was limited — G2 returned 403 to direct
fetch and no Capterra review page could be located (404). From search-snippet secondhand access to
G2: "sometimes prone to human error, which can be disruptive" is the one complaint theme
surfaced [review] (https://www.g2.com/products/supy/reviews, via search snippet). No third-party
Reddit discussion of Supy was found — this product has a much thinner independent review footprint
than MarketMan or Restaurant365, which is itself worth noting: **not found** for anything beyond
this single complaint theme.

**What users praise.** From the same secondhand G2 snippet: strong ease-of-use, support and
analytics scores (9.8, 9.9, 9.9 out of 10) and a fast (~15-day) setup [review]
(https://www.g2.com/products/supy/reviews, via search snippet).

### Restaurant365 — accounting-led back-office platform (inventory/variance module)

**Target.** US multi-unit restaurant groups needing combined accounting + operations
(Restaurant365 is really an accounting/ERP platform with inventory bolted on, not a
pure inventory point tool — included here because its variance/troubleshooting workflow is one of
the deepest publicly documented) [marketing] (https://www.restaurant365.com/blog/closing-the-gap-between-actual-and-theoretical-food-costs/).

**Pricing (2026-09-13, conflicting sources — both cited, none fully reliable).** Search-aggregated
figures put entry pricing anywhere from "$249 per location per month" to "$499 per month," with a
10-location group's 3-year total cost of ownership estimated at $50,000–150,000+ depending on
negotiated terms and customization; no free trial is offered [pricing]
(https://www.capterra.com/p/139768/Restaurant365/pricing/; https://pricingnow.com/question/restaurant365-pricing/).
Treat exact figures as unverified third-party estimates — Restaurant365 does not appear to publish
a public price list; "contact sales" is the effective model.

**Core workflow, step by step.**
1. **Setup.** An Inventory Template must exist per location before any count can be run — this
   template defines which items are counted and in what shelf/storage order [help]
   (search-indexed content from https://help.restaurant365.net/support/solutions/articles/12000075374-inventory-counts-create-and-enter-an-inventory-count,
   title only — the article itself 404'd on direct fetch in this session).
2. **Physical count.** A user selects a location and an available template, physically counts
   items, and enters quantities into the system (web or the R365 mobile app; approval, however,
   must happen in the web app, not mobile) [help] (https://docs.restaurant365.com/docs/mobile-inventory-counts-overview,
   via search summary). As quantities are entered, the system live-updates a completion percentage
   and automatically flags "unusual variances" against the prior count.
3. **Review & approve.** The entry user reviews any alert flags raised during entry — these flag
   a discrepancy between this count and the last one — resolves what needs resolving, marks the
   count complete, and a separate approval step finalizes it. A completed, approved count becomes
   the Inventory Journal Entry in the Accounting module, with the GL distribution calculated
   automatically if GL posting is enabled — i.e. the physical count *is* the accounting entry, not
   a separate reconciliation exercise [help] (https://help.restaurant365.net/support/solutions/articles/12000075375-inventory-counts-review-and-approve-an-inventory-count,
   via search summary).
4. **Theoretical usage.** Computed from recipe setups linked to POS sales/PMIX data: when a menu
   item sells, the system determines what ingredients *should* have been consumed given the
   configured recipe and portion size [help] (https://docs.restaurant365.com/docs/actual-vs-theoretical-analysis-troubleshooting-variances).
   The Theoretical vs Actual Variance Report also computes a theoretical *ending inventory* by
   taking the prior period's actual ending count as the new beginning balance, then adding
   purchases and subtracting usage and waste [help] (https://docs.restaurant365.com/food-variance-report,
   via search summary).
5. **Actual usage/cost.** Comes from approved purchase invoices (received quantities in proper
   units of measure) and physical inventory counts [help]
   (https://docs.restaurant365.com/docs/actual-vs-theoretical-analysis-troubleshooting-variances).
6. **Variance & the WEPT troubleshooting framework.** Variance = actual − theoretical consumption.
   Restaurant365's own help content frames root-cause diagnosis as **W-E-P-T**: **W**aste (logged
   separately in Waste Logs so it doesn't get miscounted as unexplained variance), **E**rrors
   (named as "the most common cause of variances" — wrong unit of measure on an invoice, an
   incorrect recipe setup, or a POS ring-up mistake, found via report drill-down), **P**ortioning
   (over/under-portioning, checked by observing service and spot-checking), and **T**heft (reduced
   via security/accountability policy, not something the software detects directly) [help]
   (https://docs.restaurant365.com/docs/actual-vs-theoretical-analysis-troubleshooting-variances).
   The documented analysis sequence: run category-level rollups to find high-variance ingredient
   categories → drill into the specific items with the largest variance → expand actual usage to
   check invoices for entry errors → check theoretical usage to confirm all menu items have
   correct recipes mapped → correct the transaction/recipe error → re-run the report to confirm
   the fix worked [help] (same URL). This explicit, named, repeatable troubleshooting loop — not
   just a number — is the most process-complete variance workflow found in this whole research
   set.

**What it automates vs. asks a human.** Automates: theoretical usage/cost calculation from
POS+recipe data, variance arithmetic and category rollups, turning an approved count directly into
a GL journal entry (no separate accounting re-entry). Human-required: building the inventory
template and recipe/UoM setup, doing the physical count, the entire WEPT diagnostic walk (the tool
surfaces where to look, not what caused it), and the approval step (deliberately kept off mobile).

**Handling of bad/missing data.** Wrong units of measure on invoices are explicitly named as a
common source of variance-report error, and a real user complaint below confirms this is a
long-standing, slow-to-fix defect in production, not just a theoretical risk [help/review]
(https://docs.restaurant365.com/docs/actual-vs-theoretical-analysis-troubleshooting-variances;
https://www.getapp.com/retail-consumer-services-software/a/restaurant365/reviews/, via search
summary).

**Feature-area bullets.**
- E: recipe/portion-size setup drives theoretical usage; no separate costing UI details found
  beyond this [help] (https://docs.restaurant365.com/docs/actual-vs-theoretical-analysis-troubleshooting-variances).
- F: template-driven counts with live completion % and automatic variance-vs-last-count flagging;
  mobile entry, web-only approval [help] (https://help.restaurant365.net/support/solutions/articles/12000075374-inventory-counts-create-and-enter-an-inventory-count;
  https://docs.restaurant365.com/docs/mobile-inventory-counts-overview).
- H: named, repeatable WEPT root-cause framework; Theoretical vs Actual Variance Report; Summary
  Variance Report; Usage Variance (w/ Theo Usage) report — three distinct, separately documented
  variance reports at different grains [help]
  (https://docs.restaurant365.com/docs/theoretical-vs-actual-report;
  https://radar.help.restaurant365.com/support/solutions/articles/12000084049-summary-variance-report;
  https://radar.help.restaurant365.com/support/solutions/articles/12000084062-usage-variance-w-theo-usage-).
- A completed inventory count posts directly as a GL journal entry — inventory and accounting are
  the same system, not integrated systems (relevant since R365 is accounting-first) [help]
  (https://help.restaurant365.net/support/solutions/articles/12000075374-inventory-counts-create-and-enter-an-inventory-count,
  via search summary).
- Q: onboarding is vendor-led and can go badly — see complaints below; no self-serve/free-trial
  path found [pricing] (https://pricingnow.com/question/restaurant365-pricing/).
- R: no public price list; third-party estimates range $249–499/location/month, multi-year
  contracts implied by the TCO framing [pricing]
  (https://www.capterra.com/p/139768/Restaurant365/pricing/; https://pricingnow.com/question/restaurant365-pricing/).

**What users complain about.**
1. Broken/incomplete onboarding leading to unusable software while billing continued: a BBB
   complainant reported the company "failed to deliver a functional onboarding process, which left
   the software unusable" and "continued to bill for quarters of service that were never provided"
   [review] (https://www.bbb.org/us/ca/irvine/profile/restaurant-management/restaurant365-1126-1000129633/complaints,
   via search summary).
2. Post-update bugs and instability: GetApp reviewers describe "frequent bugs, glitches, and
   occasional crashes, especially after updates," plus POS integration hiccups [review]
   (https://www.getapp.com/retail-consumer-services-software/a/restaurant365/, via search summary).
3. Slow fixes to core accounting mechanics: invoice approval workflow "has taken a long time to
   release and still does not always work correctly," and a units-of-measure conversion defect on
   reports "took weeks for developers to fix" [review] (same GetApp source, via search summary).
4. Availability during critical periods: some users report "the entire site being down during
   accounting close weeks" — the worst possible timing for an accounting-led platform [review]
   (same source, via search summary).
5. Customer-service responsiveness: support rated 3.8/5 on Capterra against a 4.1 overall, with
   reviewers citing "slow follow-up and unresolved tickets" [review]
   (https://capterra.com/p/139768/Restaurant365/reviews/, via search summary).

**What users praise.** Despite the bug complaints, some of the same reviewers note "the support
team is great and they fix [problems] right away" once engaged [review]
(https://www.getapp.com/retail-consumer-services-software/a/restaurant365/, via search summary);
overall Capterra rating sits at 4.1/71 reviews [review] (https://capterra.com/p/139768/Restaurant365/reviews/,
via search summary).

### meez — recipe management & food costing

**Target.** Spans a wide range: individual chefs and recipe developers at the low end up to
multi-unit hotel, stadium and hospitality groups at Enterprise [marketing]
(https://www.getmeez.com/pricing). Its differentiator versus MarketMan/Restaurant365 is that meez
treats the recipe itself — not the stock ledger — as the primary object; inventory is a Pro-tier
add-on, not the core.

**Pricing (2026-09-13, vendor page fetched directly).**
- **Starter** — $19/mo annual ($24 monthly): unlimited recipes/recipe books, AI recipe import,
  basic costing, yield calculations, order lists.
- **Pro** — $89/mo annual ($119 monthly): adds 5 active devices, inventory management.
- **Premium** — $179/mo annual ($199 monthly): adds BackOffice system connections, 1 costing feed,
  invoice processing service.
- **Enterprise** — custom: adds custom integrations, menu engineering & analytics, nutrition
  labels, allergen tagging, POS integration, priority support.
- Add-ons: extra recipe-viewer locations $60/mo each; extra cost feeds $199/mo (Premium) or
  $179/mo (Enterprise); "meez Intelligence" $60/mo/location; data-warehouse sync from $489/mo;
  hourly services $50/hr (5-hr minimum). 20% discount for annual billing.
[pricing] (https://www.getmeez.com/pricing). This is the most granular, fully public price list
found across every point-solution product in this file — no "contact sales" gate below Enterprise.

**Core workflow, step by step (recipe costing — the product's core loop).**
1. **Build the recipe.** A chef/manager enters ingredients with quantity and unit (e.g. "1 cup,"
   "300 grams"); if no unit is given, meez silently assumes "each," which is flagged in the help
   docs as a common, non-obvious cause of costing failure [help]
   (https://intercom.help/getmeez/en/articles/7204464-top-4-reasons-why-your-recipes-aren-t-costing).
   AI recipe import (Starter+) can ingest a recipe from another format rather than manual retyping
   [pricing] (https://www.getmeez.com/pricing).
2. **Attach ingredient cost.** meez needs to know "what you paid for each ingredient" — populated
   four ways depending on tier: manual entry or a spreadsheet cost-template import (Starter/Pro),
   or an automated integration that continuously syncs invoices, or an invoice-processing service
   that accepts screenshots, spreadsheets, or forwarded emails (Premium/Enterprise) [help/pricing]
   (https://intercom.help/getmeez/en/articles/5344988-costing-your-recipes;
   https://www.getmeez.com/pricing). When the same ingredient is bought from multiple suppliers,
   meez by default assigns the cost of the *most recent* invoice; a restaurant wanting per-supplier
   cost tracking must create a separate ingredient record per supplier [help]
   (https://intercom.help/getmeez/en/articles/5344988-costing-your-recipes).
3. **Unit-equivalency conversion.** Because a case of tomatoes must translate to a cost-per-tomato
   used in a recipe, meez requires an explicit "Unit Equivalency" mapping between the purchase unit
   and the recipe unit for every ingredient that isn't already 1:1 — this is a distinct, named data
   entity in the product, not an implicit conversion [help]
   (https://intercom.help/getmeez/en/articles/5344988-costing-your-recipes).
4. **Cost roll-up, including sub-recipes.** A recipe won't show a total cost/cost-per-unit until
   every ingredient (and every sub-recipe nested inside it) is fully costed; a warning appears next
   to a menu item even when its top-level costs look assigned, if a nested sub-recipe is still
   missing a cost somewhere inside it [help]
   (https://intercom.help/getmeez/en/articles/5344988-costing-your-recipes).
5. **What-if / menu engineering.** Once costed, the user can test changes to portion size, sell
   price, or ingredients and see the effect on food-cost %, profit margin and revenue instantly,
   before committing the change to the live menu [help/marketing]
   (https://intercom.help/getmeez/en/articles/5344988-costing-your-recipes).
6. **Diagnosing why a recipe won't cost.** meez's help centre publishes a named, ranked "Top 4
   reasons" troubleshooting list — treated here as the deepest self-service debugging documentation
   found for any costing tool in this research set: (1) an ingredient missing either its purchase
   cost or its purchase unit — "there's no way to see how much the ingredient costs in your
   recipes" until both exist, fixed on the ingredient page or in the New Purchase Items table;
   (2) duplicate ingredient names (e.g. "salt" vs. "kosher salt") where a cost added under one name
   doesn't propagate to recipes using the other — fixed by merging the ingredient records;
   (3) a recipe ingredient missing quantity or unit — meez silently defaults an ingredient with no
   stated unit to "each," which breaks equivalency math downstream; (4) a missing unit-equivalency
   entry between the ingredient's purchase unit type and its recipe unit type — fixed in the
   ingredient's UoM Equivalency tab [help]
   (https://intercom.help/getmeez/en/articles/7204464-top-4-reasons-why-your-recipes-aren-t-costing).

**What it automates vs. asks a human.** Automates: cost roll-up through nested sub-recipes, unit
conversion once equivalencies exist, cost reassignment on new invoice ingestion (Premium+),
what-if margin/price simulation. Human-required: entering unit equivalencies the first time,
merging duplicate ingredient names, correcting any of the four costing-failure causes, and (below
Premium) manually entering or spreadsheet-importing every cost.

**Handling of bad/missing data.** This is the single most explicit product in the whole research
set about *why* automation fails and how to fix it — the "Top 4 reasons" article is effectively a
public decision tree for missing/bad cost data. New Purchase Items that the system could not
automatically match against invoices are queued in a dedicated "New Purchase Item" tab pending
manual attention rather than silently applied or dropped [help]
(https://intercom.help/getmeez/en/articles/5344988-costing-your-recipes).

**Feature-area bullets.**
- E: the deepest recipe-costing UX found in this research set — explicit sub-recipe cost
  dependency chains, unit-equivalency as a first-class object, "assume each" default behavior
  documented rather than hidden, AI recipe import, yield calculations [help]
  (https://intercom.help/getmeez/en/articles/5344988-costing-your-recipes;
  https://intercom.help/getmeez/en/articles/7204464-top-4-reasons-why-your-recipes-aren-t-costing).
- F: inventory management appears only from Pro tier up — meez is recipe-first, stock-second,
  the inverse emphasis of MarketMan/Supy [pricing] (https://www.getmeez.com/pricing).
- G: invoice processing service (accepts screenshots/spreadsheets/forwarded email) at Premium+;
  automated cost-feed integrations also Premium+ [pricing] (https://www.getmeez.com/pricing).
- M: menu engineering & analytics, nutrition labels, allergen tagging gated to Enterprise
  [pricing] (https://www.getmeez.com/pricing).
- Q: Starter tier is genuinely self-serve (manual/spreadsheet costing, no integration needed) —
  a materially lower time-to-first-value path than MarketMan/Supy, which assume POS+vendor
  integration from day one [pricing] (https://www.getmeez.com/pricing).
- R: the most transparent, fully public, granular price list of any product surveyed in this file
  — every add-on has a published price, not just the base tiers [pricing]
  (https://www.getmeez.com/pricing).

**What users complain about.**
1. Software instability while building recipes: "buggy when deleting ingredients while building a
   recipe" [review] (https://www.getapp.com/hospitality-travel-software/a/meez/reviews/, via
   search summary).
2. Performance: "painfully slow downloading and uploading information" [review] (same source, via
   search summary).
3. Multi-outlet/hotel data modeling confusing: "the concept of 'concepts' confusing for hotel
   operations where they wanted to have recipes for several outlets in one location" [review]
   (same source, via search summary).
4. A harsh minority view: one reviewer called it "overall a very under-developed product that
   really wasn't worth the money," alongside complaints of "poorly developed software and
   second-rate service support" [review] (same source, via search summary).

**What users praise.** "Excellent program definitely created for chefs," with recipe upload/
creation described as "very quick" [review]
(https://www.getapp.com/hospitality-travel-software/a/meez/reviews/, via search summary); for its
target users (professional chefs, recipe developers, small culinary businesses) it's called "a
game-changer with unmatched precision and organization," crediting intelligent scaling and
real-time costing [review] (https://eathealthy365.com/our-honest-meez-recipe-app-review/, via
search summary — note this source reads as a consumer-recipe-app review site, not a B2B review
platform, so weight it lower than the GetApp/Capterra sources).

### Apicbase — recipe/menu costing + multi-site inventory & production

**Target.** Multi-site restaurant, dark-kitchen and catering groups; explicitly built around
"fully costed recipes" as the single source of truth that every other module (menus, production
plans, orders, inventory, nutrition, allergens, costing) syncs from [marketing]
(https://get.apicbase.com/food-costing-software/).

**Pricing (2026-09-13).** No public price list; four editions (implied Growth/Professional/
Enterprise plus a bundle) all quoted individually by number of modules and sites. Search-aggregated
starting figures range from "$149/month" to "$160/Single Outlet Bundle" to "EUR/USD 249/month" —
three different numbers from three different secondary sources, none of them the vendor's own
page, so treat all three as approximate [pricing]
(aggregated via WebSearch: g2.com/products/https-get-apicbase-com/pricing;
softwaresuggest.com/apicbase-food-management). Monthly billing carries a 15% surcharge over annual
card billing; volume discount for adding locations; a free trial is offered [pricing] (same
aggregated sources).

**Core workflow, step by step.**
1. **Recipe entry with cost AND labor.** Unlike every other costing tool in this file, Apicbase's
   base "food cost" calculation is explicitly ingredient cost + a waste percentage (custom or a
   library default), and it goes further to compute a **prime cost** = food cost + personnel cost,
   where personnel cost is labor hours × hourly rate summed across three distinct labor categories
   — prepping, cooking, plating — configured once in library settings and applied per recipe [help]
   (https://support.apicbase.com/help/food-cost-calculation). This is the only product surveyed
   that folds labor time into the per-dish cost calculation as a first-class input, not just
   ingredient cost.
2. **Selling price & margin target.** The user enters a selling price including VAT (VAT is
   deducted by the system before margin math) and a target profit margin; Apicbase then shows
   actual margin achieved (selling price vs. prime cost) against that target, and can solve either
   direction — target prime cost given a fixed selling price, or target selling price given a fixed
   prime cost [help] (https://support.apicbase.com/help/food-cost-calculation).
3. **Per-serving normalization.** Whatever the recipe's total batch size, the displayed food cost
   is always normalized to a single portion/serving — stated explicitly in the help doc, addressing
   a common source of costing confusion (batch cost vs. per-plate cost) [help] (same URL).
4. **Propagation on price change.** Because every downstream module reads from the same recipe
   object, a supplier price change recosts the dish automatically, and that recost ripples into
   menu, production-plan and margin reporting without manual re-entry [marketing]
   (https://get.apicbase.com/food-costing-software/).
5. **Variance (theoretical vs. actual).** Marketing copy defines theoretical food cost as what
   dishes *should* cost based on recipes and what sold, versus actual food cost from physical stock
   counts, with the gap attributed to "waste, over-portioning, spoilage or theft" [marketing]
   (https://get.apicbase.com/food-cost-control/) — the same four-cause framing as Restaurant365's
   WEPT, but Apicbase's own help centre does not publish an equivalent step-by-step troubleshooting
   article; the fetched food-cost-calculation help page covers only the recipe/margin side, not the
   count-vs-theoretical variance mechanics — **not found** at the same depth as Restaurant365's
   WEPT article.
6. **Stockable (semi-finished) recipes.** A named "adding a stockable recipe to your inventory"
   workflow lets a prepared sub-recipe (e.g. a house sauce) itself be tracked as an inventory item
   with its own stock level, not just as a costing component — relevant for kitchens that batch-
   prep components ahead of service [help]
   (https://support.apicbase.com/help/adding_semifinished_product_to_stock, title/topic confirmed
   via search index; page content not independently re-fetched in this session).

**What it automates vs. asks a human.** Automates: cost/prime-cost/margin math, cross-module
recost propagation on a price change, per-serving normalization regardless of batch size. Human-
required: setting waste-percentage assumptions and labor-time-per-recipe the first time, running
physical counts, and (per the review evidence below) fixing sync errors between POS/supplier
integrations that can corrupt report data.

**Handling of bad/missing data.** Not documented at the same explicit level as meez's "Top 4
reasons" article — no equivalent public troubleshooting page was found for a recipe that fails to
cost. Independent reviews report that supplier/POS sync bugs can actively corrupt report data
(see complaints below), which is a materially worse failure mode than "flagged and queued for
review" if accurate.

**Feature-area bullets.**
- E: recipe costing uniquely includes labor cost per dish (prep/cook/plate hourly-rate model),
  target-margin solving in both directions, per-serving normalization [help]
  (https://support.apicbase.com/help/food-cost-calculation).
- F: multi-site inventory; stockable semi-finished/sub-recipes as trackable stock items [help]
  (https://support.apicbase.com/help/adding_semifinished_product_to_stock).
- G: supplier integrations exist but are named in complaints as a bug source (see below)
  [review] (search-aggregated Capterra/G2 summary).
- H: theoretical-vs-actual variance framed around the same four causes as Restaurant365's WEPT,
  but with materially thinner published self-service documentation of the diagnostic workflow
  [marketing] (https://get.apicbase.com/food-cost-control/).
- M: nutrition/allergen data and forecasting exist but forecasting is flagged in a review as
  limited [review] (search-aggregated summary).
- O: built for multi-site from the ground up — pricing itself is quoted per number of sites
  [pricing] (search-aggregated summary).
- Q: free trial available, but real-world setup is reported as complicated (see complaints).
- R: no public price list; per-module, per-site custom quotes; 15% monthly-billing surcharge over
  annual [pricing] (search-aggregated summary).

**What users complain about.**
1. Complicated setup with a steep learning curve: "Complicated to setup, bugs and connection
   problems within suppliers and POS" [review]
   (https://capterra.com/p/171584/Apicbase-Restaurant-Management/reviews/, via search summary).
2. Performance degradation under concurrent use: "slower page loads, especially when many users are
   logged in at once" [review] (same source, via search summary).
3. Data-integrity risk from integration bugs: "bugs or connection problems that can make whole
   lines of reports useless due to corrupted data" [review] (same source, via search summary).
4. Supplier/POS sync bugs corrupting report data, and "limited forecasting options" [review] (same
   source, via search summary).

**What users praise.** Rated 4.5/5 (60 reviews) on G2 and 4.6/5 (35 reviews) on Capterra — among
the higher ratings found in this research set [review]
(https://www.g2.com/products/apicbase/reviews; https://capterra.com/p/171584/Apicbase-Restaurant-Management/reviews/,
via search summary). One user: "very pleased and thankful for how ApicBase has changed our
operations for the better, helping us manage our expenses and raise our profitability" [review]
(same Capterra source, via search summary).

### Winnow — AI camera + scale food-waste measurement

**Target.** Commercial kitchens of all sizes; claims 3,500+ sites live across 94 countries, the
most widely deployed AI food-waste platform found in this research set [marketing]
(https://www.winnowsolutions.com/product/food-waste-management-software).

**Pricing (2026-09-13).** No public price list. Quoted per site by kitchen size and product tier,
across four packages: Winnow Track (tablet-only, no camera/AI), VisionControl, VisionAI and
VisionAI Plus [marketing/pricing] (https://www.winnowsolutions.com/en/faq, via search summary).
One data-aggregator figure of "$30,000/user/month" surfaced in search results but reads as a
scraping artifact, not a real price point — excluded as unreliable. Vendor claims 2–8% food-
purchasing-cost reduction with typical first-year ROI of 2–10x, and that "most customers recoup
the subscription within the first few months" [marketing] (https://www.winnowsolutions.com/en/faq)
— vendor-supplied, not independently corroborated.

**Core workflow, step by step.**
1. **Hardware.** A bin sits on a connected scale; a camera (pole-mounted, wall-mounted, or free-
   standing) is positioned above it. Installation is fast — "a pole-mounted unit can be assembled
   in about 15 minutes" [help] (https://www.winnowsolutions.com/en/faq).
2. **"Throw & Go" capture.** Kitchen staff throw unsold/prepped food away exactly as they normally
   would — no scanning, no on-screen category selection, no logging step. The camera captures a
   burst of 30+ images per disposal event and the system selects the clearest frame for
   identification [help] (https://www.winnowsolutions.com/en/faq).
3. **Recognition.** Winnow's VisionAI, pre-trained on 500+ million food-waste images and
   recognizing over 1,000 food items, identifies the item and simultaneously logs its weight (from
   the scale), its cost, and (where configured) a disposal reason — with no manual input required
   [marketing] (https://www.winnowsolutions.com/product/food-waste-management-software). Because
   the model is pre-trained rather than trained on-site, the vendor claims "no long calibration
   period" and "accurate data from day one" [help] (https://www.winnowsolutions.com/en/faq) — a
   direct contrast with systems that need weeks of site-specific training data.
4. **Reporting.** Daily reports translate captured waste into purchasing, menu and portioning
   decisions for chefs [marketing] (https://www.winnowsolutions.com/en/faq).

**What it automates vs. asks a human.** Automates: item recognition, weighing, costing and logging
of every discarded item, with zero staff action beyond the normal act of throwing something away.
Human-required: acting on the daily report (adjusting purchasing/menu/portions) — Winnow measures
and surfaces waste, it does not itself change ordering or recipes.

**Handling of bad/missing data.** Not found — the fetched FAQ does not document what happens when
an item is unrecognized, when the bin is shared for non-food waste, or how the system behaves
during a power/network outage.

**Feature-area bullets (waste-specific — this is the entire product, so most areas are N/A).**
- H (variance): indirectly supports theoretical-vs-actual food-cost work by quantifying the
  "waste" component of the variance gap with weight/cost/reason detail no manual log can match at
  this granularity.
- Q (onboarding): 15-minute physical install, no menu-input step, "accurate from day one" claimed
  — the fastest time-to-value of any product surveyed in this file, if the vendor claim holds
  [help] (https://www.winnowsolutions.com/en/faq).
- R (pricing): fully quote-based, no public tiers or numbers — impossible to comparison-shop
  without a sales call [pricing] (search-aggregated summary).

**What users complain about.** Not found — no independent review with a star rating, a named
reviewer, or a specific complaint was located for Winnow in this session. The one Capterra page
fetched showed "0 user reviews" for Winnow itself (comparative feedback was for a *different*
competing product, Via Analytics) [review] (https://www.capterra.com/p/143157/The-Winnow-System/,
via direct fetch). This absence is itself notable: Winnow is the most-cited brand name in this
category yet has one of the thinnest independent review footprints of any product across all three
research files.

**What users praise.** Not found at the individual-reviewer level (see above); only aggregate
vendor-supplied savings claims exist.

**Distinctive fact.** Winnow sued Orbisk (below) for patent infringement over vision-based
waste-tracking technology at the Unified Patent Court; the court found no infringement by Orbisk
and partially revoked Winnow's patent (decision 2025-08-13, case ACT_36388/2024) [blog]
(https://www.mlex.com/mlex/articles/2376515/upc-partially-revokes-winnow-patent-finds-no-infringement-by-orbisk).
This confirms the two products are direct, technically overlapping competitors, not adjacent tools.

---

### Orbisk — AI camera + scale food-waste measurement (Winnow's direct competitor)

**Target.** Commercial kitchens and multi-site hospitality/restaurant groups; Dutch-founded,
positions itself on zero-workflow-change deployment [marketing]
(https://orbisk.com/product/how-it-works/).

**Pricing (2026-09-13).** Not disclosed on the vendor's own product page. One third-party
aggregator lists "starts at $400 per month" [pricing] (search-aggregated, unverified against a
primary source — flagged as the weakest-sourced pricing figure in this file). Vendor-claimed
savings: "€38k–€120k in 6 months," 24–35% waste reduction, and 2x–10x ROI within 4–8 months
[marketing] (https://orbisk.com/product/how-it-works/) — vendor-supplied, not independently
corroborated.

**Core workflow, step by step.**
1. **Above-bin capture.** A camera captures food waste as it's discarded, before it mixes in the
   bin, paired with an automatic weight reading — explicitly marketed as requiring "no open bin,
   no menu input, no IT dependency" [marketing] (https://orbisk.com/product/how-it-works/).
2. **Recognition.** Claims 800+ ingredients recognized at 90% identification accuracy — a specific,
   quantified accuracy figure that Winnow's own materials do not state as plainly [marketing]
   (https://orbisk.com/product/how-it-works/). Note this is a vendor-published number, not an
   independently audited one.
3. **Granularity.** Data is logged at ingredient level with actual weights — "1kg fish, 400g
   lettuce," explicitly contrasted against a coarser "300g mixed waste" alternative approach
   [marketing] (https://orbisk.com/product/how-it-works/).
4. **Reporting.** A dashboard organizes waste by ingredient, waste stream, serving stage (e.g.
   prep vs. plate waste) and location, and produces a "ranked list of what to fix" with
   ingredient-level recommendations — a more prescriptive output than Winnow's daily report
   [marketing] (https://orbisk.com/product/how-it-works/). For portfolio operators, a comparative
   view ranks waste performance across multiple locations.
5. **Onboarding.** Same-day setup claimed, with "0 hrs training required" and no change to kitchen
   staff workflow [marketing] (https://orbisk.com/product/how-it-works/).

**What it automates vs. asks a human.** Same automation profile as Winnow: full automatic capture,
weighing, and identification with zero staff action; a human still has to act on the ranked
recommendations.

**Handling of bad/missing data.** Not found — no fallback behavior for unrecognized ingredients or
network/power interruptions was documented on the fetched page.

**Feature-area bullets.**
- H: ingredient-level, serving-stage-level waste breakdown feeding directly into a "ranked list of
  what to fix" — the most prescriptive (not just descriptive) waste output found in this research
  set [marketing] (https://orbisk.com/product/how-it-works/).
- O: named multi-location comparative view for portfolio operators [marketing] (same URL).
- Q: same-day setup, zero training claimed — matching Winnow's fast-onboarding positioning
  [marketing] (same URL).
- R: least-verified pricing figure in this file ($400/mo from a single secondary aggregator, not
  the vendor) [pricing] (search-aggregated, unverified).

**What users complain about / praise.** Not found. No independent customer review (Capterra, G2,
Trustpilot, Reddit) was located for Orbisk in this session — search results returned only a
vendor-partner case study (data-labeling vendor Sama, praising its own contribution) and press
coverage of the Winnow patent litigation, not end-user restaurant feedback [blog]
(https://www.sama.com/case-studies/orbisk-is-using-accurate-ai-to-help-restaurants-reduce-food-waste-up-to-70).
Like Winnow, this product category has almost no independent review footprint — worth flagging as
a pattern rather than a per-product gap.

### SalaryBox — India staff attendance & payroll

**Target.** Small-to-mid Indian businesses moving off paper/spreadsheet attendance, including
restaurants/QSRs by name [marketing]
(https://salarybox.in/blog/best-attendance-payroll-software-for-restaurants-qsrs-in-india-2026/).

**Pricing (2026-09-13, vendor page fetched directly).**
- **Starter** — ₹1,500/mo flat or ₹30/user/mo (₹1,350 / ₹27 with quarterly billing; 33% off
  annual): GPS attendance, leave management, real-time notifications, attendance reports.
- **Business** (marked "most popular") — ₹3,000/mo flat or ₹75/user/mo (₹2,700 / ₹67.50
  quarterly): adds fraud prevention, rosters, automated payroll, compliance filing, payslip
  generation.
- **Enterprise** — custom/contact sales: adds API access, Tally integration, dedicated relationship
  manager, aimed at 200+ staff across multiple states.
- Add-ons: live location tracking ₹100/user/mo, field-force CRM ₹250/user/mo, background
  verification ₹350/user, bank account verification ₹10/verification, biometric device available
  in-app.
[pricing] (https://salarybox.in/pricing/). A 3-day full-access trial requires a ₹1 refundable
verification charge before billing starts [marketing] (search-aggregated summary).

**Core workflow, step by step.**
1. **Attendance capture — five interchangeable methods.** AI selfie/face-recognition attendance
   (marketed explicitly as stopping "buddy punching" — one staff member clocking in for another),
   QR-code kiosk attendance (any tablet becomes a scan point), geofence attendance (auto-marks
   entry/exit against a defined work-area boundary), field-staff GPS live tracking, and plain
   selfie-from-phone attendance [marketing]
   (https://salarybox.in/salarybox-attendance-management-how-ai-selfie-geofencing-and-smart-attendance-tracking-are-eliminating-buddy-punching-for-indian-businesses/).
2. **Offline resilience.** Attendance can be marked with no internet connection; data syncs
   automatically once connectivity returns — directly relevant to the intermittent-connectivity
   reality of a single-outlet Indian restaurant [marketing] (search-aggregated summary).
3. **Leave integration.** An approved leave request automatically reflects in the attendance
   calendar with no separate manual marking step in a register [marketing] (search-aggregated
   summary).
4. **Payroll.** Automated salary calculation computes wages, deductions and bonuses from the
   attendance/leave data with (per marketing) "no manual errors" [marketing] (search-aggregated
   summary); statutory PF/ESI/PT/TDS support is built in at Business tier and above [pricing]
   (https://salarybox.in/pricing/).

**What it automates vs. asks a human.** Automates: attendance capture across multiple modalities,
leave-to-attendance reconciliation, wage/deduction calculation, compliance filing (Business+).
Human-required: approving leave requests, resolving any attendance-method failure (e.g. face
recognition rejecting a match), and — per the complaints below — negotiating pricing at renewal
time.

**Handling of bad/missing data.** Offline queuing for attendance marks is the one explicit
bad-conditions design decision found; no help documentation was located on what happens when face
recognition fails to match (fallback method?) — not found.

**Feature-area bullets.**
- L: the deepest attendance-method breadth found in this research set — five distinct capture
  modes covering fixed-location kitchen staff, delivery/field staff, and BYOD tablet kiosks in one
  product [marketing] (https://salarybox.in/salarybox-attendance-management-how-ai-selfie-geofencing-and-smart-attendance-tracking-are-eliminating-buddy-punching-for-indian-businesses/).
  Indian statutory compliance (PF/ESI/PT/TDS) built in, not bolted on [pricing]
  (https://salarybox.in/pricing/).
- Q: 3-day trial gated behind a ₹1 verification charge — a low but non-zero friction point
  [marketing] (search-aggregated summary).
- R: transparent per-user AND flat-fee pricing published directly by the vendor, rare in this
  category [pricing] (https://salarybox.in/pricing/).

**What users complain about.**
1. Steep pricing jump at renewal/scale: "pricing for renewal and adding employees is
   disproportionately high compared to the initial subscription" [review] (Google Play Store, via
   search summary).
2. Perceived profit motive: "the company's approach appears overly profit-driven" [review] (same
   source, via search summary).
3. App stability: "the app freezing from time to time" [review] (same source, via search summary).
4. Feature ceiling at the low end: "extremely low pricing sometimes means fewer advanced features"
   and a wish for "more advanced analytics and customizable reports" [review]
   (https://www.techjockey.com/reviews/salarybox, via search summary).

**What users praise.** "Highly affordable," "great value for small and mid-sized businesses";
"attendance tracking is accurate with GPS and selfie verification"; "automated payroll feature
saves hours of manual calculation" [review] (https://www.techjockey.com/reviews/salarybox, via
search summary).

---

### EZHRM — India HR & payroll software

**Target.** Indian SMEs, 5–500 employees, positioned as AI-powered HR/payroll rather than
restaurant-specific [marketing] (https://ezhrm.in/).

**Pricing (2026-09-13).** No consistent public figure: one source cites "$1 per employee," another
"₹50/month/employee," and the vendor's own listing on Techjockey states "Price Available on
Request" with no tiers shown [pricing] (https://www.techjockey.com/detail/bharatbills-ezhrm-hr-software;
search-aggregated summary). Treat all as unverified; the vendor does not appear to publish a
primary price list.

**Core workflow, step by step.**
1. **Attendance sync.** Data flows in automatically from biometric devices, a mobile app, AI face
   recognition, geofencing, or IP-based (office-network) check-in — the IP-based method is aimed
   specifically at fixed-location office/back-of-house staff, distinct from geofencing for field
   staff [marketing] (https://ezhrm.in/attendance-management/; https://ezhrm.in/ip-based-attendance/).
2. **Attendance-to-payroll reconciliation.** Present days, late arrivals and half-days are
   calculated automatically from the synced attendance data "without any manual reconciliation"
   [marketing] (https://ezhrm.in/features/).
3. **Payroll run.** Marketing claims "most EZHRM customers run their complete monthly payroll in
   15–20 minutes" — salary, TDS, PF and ESI computed in real time and reviewed/approved from a
   single screen [marketing] (https://ezhrm.in/features/) — vendor-supplied and not independently
   corroborated by any review found in this session.
4. **Compliance.** PF, ESI, PT and TDS auto-calculated and kept current against filing deadlines
   [marketing] (https://ezhrm.in/features/).

**What it automates vs. asks a human.** Automates: attendance-to-payroll math, statutory deduction
calculation. Human-required: final payroll review/approval (explicitly a single-screen human
sign-off step, not fully automatic), and choosing/configuring which of the multiple attendance
capture methods fits which staff category.

**Handling of bad/missing data.** Not found — no help-centre article or review discussing failure
modes (e.g. a biometric device offline, a face-recognition mismatch) was located.

**Feature-area bullets.**
- L: IP-based attendance is a specific, less-common method (useful for a single fixed premises
  with a stable local network — plausible fit for a single-outlet restaurant's back office) layered
  alongside biometric/face/geofence/mobile [marketing] (https://ezhrm.in/ip-based-attendance/).
- Q: "5 to 500 employees" positioning suggests it targets slightly larger operations than a typical
  single Indian restaurant, but the entry end overlaps [marketing] (https://ezhrm.in/).
- R: pricing is genuinely unclear across all sources found — this is one of the least transparent
  products on pricing in this entire file.

**What users complain about / praise.** Review presence is very thin: Techjockey shows a 4.2/5
aggregate from only 5 verified ratings (Features 4.4, Value for Money 3.8, Ease of Use 3.8,
Customer Support 4.8, 90% would recommend) but explicitly states "No reviews are currently
available for EZHRM" — i.e. a rating exists with no backing quotes [review]
(https://www.techjockey.com/detail/bharatbills-ezhrm-hr-software). A separate search-aggregated
summary reports generic praise for "ease of use" and UI simplicity, unattributed to a specific
reviewer [review] (search-aggregated summary, source page not independently confirmed). No
complaint with a specific quote or reviewer was found — flagged as **not found** rather than
invented; this product has the thinnest independent evidence base of the three staff-management
tools in this file.

### 7shifts — restaurant scheduling, labor forecasting & compliance

**Target.** Restaurants from single-location to multi-unit; explicitly the market's dominant
restaurant-specific scheduling/labor tool, with a genuinely free tier for small single-location
operations [pricing] (https://costbench.com/software/employee-scheduling/7shifts/, via search
summary).

**Pricing (2026-09-13, aggregated from multiple secondary sources — vendor's own pricing page not
independently fetched in this session, flagged accordingly).**
- **Comp — free, no time limit, no card required**, for single-location under 30 employees: basic
  scheduling and team messaging.
- **Essentials — $39.99/mo**: advanced scheduling and team communication.
- **Pro — $79.99/mo**: adds time clocking and compliance tooling.
- **Premium — $134.99/mo**: adds full payroll, tip and task management, aimed at multi-location.
- All paid tiers are priced **per location**, not per employee.
- Add-on modules (priced separately, not bundled): 7shifts Payroll ($39.99/location/mo + $6/employee
  paid), Tip Management, Manager Log Book, Task Management, Employee Onboarding.
[pricing] (https://costbench.com/software/employee-scheduling/7shifts/, via search summary; cross-
checked against https://www.workstream.us/blog/7shifts-pricing, via search summary — the two
sources agree on these figures, which is unusual for this file and increases confidence.)

**Core workflow, step by step (the Labor Budget / Optimal Labor forecasting loop — its
differentiator over a generic scheduler).**
1. **Set targets.** A Labor Budget Tool sits at the bottom of the schedule-building page, letting a
   manager set a projected-sales figure and a labor-cost target for the week being scheduled [help]
   (https://kb.7shifts.com/hc/en-us/articles/4417514442771-The-Labor-Budget-Tool, title/content via
   search summary — direct fetch 403'd in this session).
2. **AI sales projection.** Projected sales are generated by a machine-learning model that factors
   in seasonal trends, claimed at 95% accuracy; if the location has an "Actual Sales" integration
   enabled (i.e. POS-linked), both real sales and projected sales populate the tool automatically
   rather than requiring manual entry [help] (same URL, via search summary).
3. **Live budget tracking while scheduling.** As a manager drags shifts onto the schedule, the
   labor-cost total updates in real time against the target set in step 1 — so overspending is
   visible during schedule construction, not discovered afterward on a payroll report [help] (same
   URL, via search summary).
4. **Hour-by-hour optimization.** A separate "Optimal Labor" tool goes further, giving hourly (not
   just daily/weekly) sales and labor forecasts and recommendations, claimed up to 90% accuracy when
   fed live POS data — enabling shift-level, not just day-level, staffing decisions [help]
   (https://kb.7shifts.com/hc/en-us/articles/4417514452115-The-Optimal-Labor-Tool, via search
   summary).
5. **Shift lifecycle.** Once published, employees self-serve most changes from their phone —
   requesting time off, swapping shifts, updating availability, picking up open shifts — with
   manager approval in real time; 7shifts' own claim is managers save ~14 hours/month building
   schedules this way versus manual methods [marketing] (https://www.7shifts.com/, via search
   summary).
6. **Compliance layer (Pro+).** Labor-law compliance checks (break rules, overtime, minor-labor
   restrictions — US-specific) are built into the scheduling flow itself rather than a separate
   audit step [marketing] (https://timeforge.com/industry-news/7shifts-simplifies-restaurant-labor-compliance-with-new-forecasting-features/,
   via search summary).

**What it automates vs. asks a human.** Automates: sales/labor forecasting (daily and hourly), live
budget-vs-actual tracking during schedule construction, shift-swap/time-off request routing,
compliance rule-checking against a built schedule. Human-required: actually placing each shift
(the tool recommends and warns, a manager still builds/publishes the schedule), and approving
employee-initiated changes.

**Handling of bad/missing data.** Without a POS "Actual Sales" integration, projected sales must be
entered manually rather than auto-populated — the tool degrades gracefully to manual input rather
than refusing to function, but loses its forecasting edge [help]
(https://kb.7shifts.com/hc/en-us/articles/4417514442771-The-Labor-Budget-Tool, via search summary).
No help content was found describing forecast behavior for a location with no sales history
(a genuinely new restaurant) — not found, and directly relevant to this platform's own cold-start
problem.

**Feature-area bullets.**
- L: the deepest labor-forecasting-to-scheduling loop found in this research set — two distinct
  tools (Labor Budget for weekly targets, Optimal Labor for hourly recommendations) at two
  different accuracy claims (95% daily sales, 90% hourly sales+labor) [help]
  (https://kb.7shifts.com/hc/en-us/articles/4417514442771-The-Labor-Budget-Tool;
  https://kb.7shifts.com/hc/en-us/articles/4417514452115-The-Optimal-Labor-Tool, via search
  summary). Manager Log Book and Task Management exist as separate paid add-ons for shift-handoff
  notes and side-work checklists [pricing] (https://costbench.com/software/employee-scheduling/7shifts/,
  via search summary).
- M: built-in labor-cost-vs-sales forecasting dashboard live during schedule building, not just a
  after-the-fact report [help] (same URLs).
- N (compliance): break/overtime/minor-labor rule checking built into the scheduling flow
  (US-specific rules) [marketing] (https://timeforge.com/industry-news/7shifts-simplifies-restaurant-labor-compliance-with-new-forecasting-features/,
  via search summary).
- Q: a genuinely usable free tier (Comp) for a single location under 30 staff, no card required,
  no time limit — one of very few true free tiers found across all three research files
  [pricing] (https://costbench.com/software/employee-scheduling/7shifts/, via search summary).
- R: per-location (not per-employee) pricing on the base product, with payroll separately metered
  per-employee-paid — an unusual hybrid pricing model [pricing] (same source).

**What users complain about.**
1. Login/technical instability: "a 404 error when logging in... a concern for a tool that
   restaurant managers depend on daily" [review]
   (https://www.capterra.com/p/123038/7shifts-Restaurant-Scheduling/reviews/, via search summary).
2. Notification reliability: "staff may not receive notifications about schedule releases or
   upcoming shifts... despite proper setup, requiring account password resets to resolve the
   issue" [review] (same source, via search summary).
3. Feature-gating behind paid add-ons: "some useful features like an events calendar and
   labor-to-sales based scheduling require extra payment" [review] (same source, via search
   summary) — i.e. the forecasting capability described above as the ceiling is itself an
   upcharge, not included at the base tier.

**What users praise.** Overall 4.7/5 across 1,211 verified Capterra reviews — one of the highest
review-volume, highest-rating products in this entire research set [review]
(https://www.capterra.com/p/123038/7shifts-Restaurant-Scheduling/reviews/, via search summary).
Managers describe it as "more agile and practical than payroll company alternatives," praising
drag-and-drop scheduling, open-shift pools, shift swapping, and direct manager-staff messaging
[review] (same source, via search summary).

### SafetyCulture (formerly iAuditor) — food safety / checklists / compliance

**Target.** General-purpose frontline-inspection platform used across many industries, not
restaurant-specific — included here for restaurant food-safety templates, corrective-action
workflow, and IoT temperature monitoring, all publicly documented [marketing]
(https://safetyculture.com/library/hospitality/food-safety-inspection-check-list-80wlikxzckvrwcqb).
Its own Capterra listing still carries the product's earlier name, iAuditor, in the URL, and as of
this session is also labeled "Mitti (by SafetyCulture)" — a naming inconsistency across the
vendor's own review-platform presence, not resolved by this research [review]
(https://www.capterra.com/p/141080/iAuditor/reviews/).

**Pricing (2026-09-13, aggregated).**
- **Free** — up to 10 users, basic features.
- **Premium** — $24/user/mo billed annually ($29/seat/mo month-to-month).
- **Enterprise** — custom, adds dedicated support and SSO.
- The OSHA-aligned safety-training content library is a **separate** licensed module (Training),
  adding an estimated $5–10+/user/mo on top of the base plan [pricing]
  (https://safetyteamtech.com/blog/safetyculture-pricing, via search summary — third-party
  estimate, not a vendor-quoted figure).

**Core workflow, step by step.**
1. **Template selection/customization.** A restaurant starts from a public template library —
   dozens of restaurant-specific checklists exist (daily food-safety inspection, HACCP
   self-inspection, monthly safety inspection, allergen control, cleaning/sanitation) covering named
   physical zones: cooking/holding temperatures, handwashing/hygiene stations, sanitizer
   concentration, walk-in coolers/freezers, dry storage, dishwashing, mop stations, beverage/ice
   machines, restrooms [marketing] (https://safetyculture.com/library/hospitality/food-safety-inspection-check-list-80wlikxzckvrwcqb;
   https://safetyculture.com/library/hospitality/food-safety-self-inspection-restaurants-1jblenpqt63hmmop).
   Templates are customizable rather than fixed forms.
2. **Inspection capture.** Staff walk the checklist on a phone/tablet, attaching photos as
   evidence, and can capture a digital signature to close out the inspection [marketing]
   (https://safetyculture.com/library/hospitality/food-safety-inspection-check-list-80wlikxzckvrwcqb).
3. **Corrective actions.** A failed checklist item can spawn a corrective action with an assignee,
   a priority level and a due date, tracked in-app until closed out — this is the mechanism that
   turns "we found a problem" into "someone is accountable for fixing it by when" rather than a
   static inspection record [marketing/help]
   (https://safetyculture.com/library/hospitality/food-safety-inspection-check-list-80wlikxzckvrwcqb;
   https://help.safetyculture.com/000068).
4. **IoT temperature monitoring (add-on hardware).** Wireless sensors placed in fridges/cool rooms
   send continuous readings to a nearby gateway, which forwards them to the platform — this
   replaces manual temperature-log sheets with automatic, continuous capture rather than periodic
   spot checks [help] (https://help.safetyculture.com/000068). A user defines critical thresholds
   and escalation rules; a breach triggers an automatic alert to designated personnel and can
   auto-generate a **pre-set** corrective action, closing the loop from sensor breach to assigned
   fix without a human first noticing the problem [help] (https://help.safetyculture.com/000068).
   One gateway can aggregate multiple sensors, letting one location's readings be monitored
   centrally [help] (https://help.safetyculture.com/000068).
5. **Export/reporting.** Completed inspections export as PDF, Word, Excel or a shareable web link
   — relevant for handing a completed audit trail to an inspector or franchisor [marketing]
   (https://safetyculture.com/library/hospitality/food-safety-inspection-check-list-80wlikxzckvrwcqb).

**What it automates vs. asks a human.** Automates: continuous temperature capture (with sensor
hardware), threshold-breach alerting, corrective-action creation on a breach, and report
generation/export. Human-required: performing the physical walk-through inspection itself
(no computer-vision inspection was found — SafetyCulture is a structured-checklist tool, not a
vision-based auditor), resolving a corrective action, and the initial choice/customization of
which checklist template applies.

**Handling of bad/missing data.** A documented sync-delay issue exists: "it takes longer to sync
inspections when multiple inspections are loaded up to sync, particularly when internet connection
is slow" — i.e. the product is used offline-first but sync is not instantaneous under load or poor
connectivity, a directly relevant data point for an intermittent-network environment [review]
(https://taqtics.co/reviews/safetyculture/, via search summary).

**Feature-area bullets.**
- N (compliance/food safety): the deepest, most restaurant-specific checklist library and
  corrective-action tracking loop found in this research set, plus the only IoT-sensor-based
  continuous temperature monitoring found among the required products [help/marketing]
  (https://help.safetyculture.com/000068; https://safetyculture.com/library/hospitality/food-safety-inspection-check-list-80wlikxzckvrwcqb).
- Q: free tier for up to 10 users; reviewers describe a genuinely short learning curve for
  nontechnical frontline staff [review] (https://taqtics.co/reviews/safetyculture/, via search
  summary).
- P (hardware/offline): purpose-built wireless sensor + gateway hardware line (Monnit-branded
  sensors supported) is a real hardware integration, not just a software feature [help]
  (https://help.safetyculture.com/003887; https://help.safetyculture.com/003295).
- R: per-user pricing structure explicitly flagged by reviewers as a burden for smaller teams, and
  advanced features/integrations withheld from the free plan [review]
  (https://taqtics.co/reviews/safetyculture/, via search summary).

**What users complain about.**
1. Sync delays under load/poor connectivity: "it takes longer to sync inspections when multiple
   inspections are loaded up to sync, particularly when internet connection is slow" [review]
   (https://taqtics.co/reviews/safetyculture/, via search summary).
2. Free-tier feature ceiling: "does not support all the advanced features and integrations in the
   free plans," a real constraint for smaller teams [review] (same source, via search summary).
3. Per-user pricing burden: "per-user pricing might be a challenge for smaller teams, and some
   advanced features are locked behind higher-tier plans" [review] (same source, via search
   summary).

**What users praise.** "Generally quick to onboard for frontline teams and nontechnical users,"
with "a short learning curve for forms, inspections, and reporting" [review]
(https://taqtics.co/reviews/safetyculture/, via search summary). Reviewers value template
customization, time saved on detailed reports, and responsive customer care; the corrective-action
loop is credited with "clear accountability for audit completion and follow-up" [review]
(https://www.capterra.com/p/141080/iAuditor/reviews/, via search summary).

### Reelo — India restaurant CRM, loyalty & WhatsApp marketing (India extra)

**Why included.** India-specific extra named directly in scope: an India-first restaurant CRM/
loyalty/WhatsApp platform, distinct from the generic loyalty bullets already logged for Rista/
GoFrugal in `01-platforms.md`'s merged table.

**Target.** Independent restaurants, cafes, bars and QSR chains in India seeking repeat-visit
marketing without building CRM/WhatsApp infrastructure themselves [marketing] (https://reelo.io/).

**Pricing (2026-09-13, vendor-published).**
- **Forever Free** — no time limit: SMS/email campaigns, customer insights, analytics, RFM
  (recency/frequency/monetary) segmentation.
- **Growth** — ₹39,000/outlet/year + GST (≈₹3,250/month/outlet): adds branded loyalty programs,
  automated marketing campaigns, deeper customer insights; a 14-day free trial is offered before
  committing.
[pricing] (https://reelo.io/pricing/, via search summary).

**Core workflow, step by step.**
1. **Capture at checkout.** Staff use the device camera at the POS/counter to capture a customer
   (a lightweight enrollment step, not a full sign-up form) and award/redeem loyalty points
   instantly [marketing] (https://reelo.io/loyalty).
2. **Loyalty structure choice.** A restaurant picks one of three reward models: points-based,
   visit-based, or spend-based [marketing] (https://reelo.io/blog/best-crm-for-restaurants-in-india-5-platforms-compared/).
3. **Automatic segmentation.** Reelo segments guests by behavior — first-timers, high spenders,
   lapsed customers — via RFM analysis, without a human building segments manually [marketing]
   (https://reelo.io/blog/restaurant-crm-with-whatsapp-marketing-the-complete-guide).
4. **Triggered, personalized messaging.** Birthdays, win-back sequences for lapsed customers,
   reminders and post-visit flows fire automatically once configured, and — notably — the message
   content itself varies by segment rather than being one broadcast to the full list [marketing]
   (same URL).
5. **WhatsApp delivery & tracking.** Messages go out as verified, template-based WhatsApp
   messages/carousels (i.e. using WhatsApp Business API templates, not casual chat messages); every
   send is tracked back to visits and revenue attributable to that specific campaign [marketing]
   (https://reelo.io/whatsapp-marketing).
6. **Setup.** Vendor claims most restaurants are live within 24–48 hours, with the Reelo team
   handling POS integration and initial campaign configuration rather than a self-serve setup
   [marketing] (search-aggregated summary) — a materially faster and more assisted onboarding claim
   than any of the inventory/costing tools in this file.

**What it automates vs. asks a human.** Automates: segmentation, trigger timing, message sending,
revenue attribution per campaign. Human-required: initial POS integration (vendor-assisted, not
self-serve), choosing the loyalty structure, and designing the message templates/offers themselves.

**Handling of bad/missing data.** Not found — no help-centre documentation was located on what
happens with duplicate customer records, a customer with no phone number capable of receiving
WhatsApp, or offline capture during a network outage at the counter.

**Feature-area bullets.**
- K: RFM auto-segmentation + WhatsApp-native triggered campaigns with per-campaign revenue
  attribution is a materially deeper CRM/loyalty loop than the WhatsApp-bill-delivery or
  tier-based-loyalty bullets already logged for GoFrugal/Rista in `01-platforms.md` — flagged here
  as *also in 01 (partial)* since WhatsApp marketing itself is not new, but automated behavioral
  segmentation triggering it is [marketing] (https://reelo.io/blog/restaurant-crm-with-whatsapp-marketing-the-complete-guide).
- Q: 24–48 hour vendor-assisted setup, a Forever Free entry tier with no time limit — one of the
  lowest-friction onboarding claims in this file [marketing/pricing] (https://reelo.io/pricing/).
- R: transparent public pricing (₹39,000/outlet/year for Growth), rare among CRM/loyalty tools
  surveyed [pricing] (https://reelo.io/pricing/).

**What users complain about.**
1. Automation bugs with real customer-facing consequences: "the auto campaign doesn't work
   properly; restaurant names in messages automatically get changed to some other restaurant, and
   customers start getting messages with the wrong restaurant name" [review]
   (https://www.capterra.in/software/1050827/reelo, via search summary) — a serious defect for a
   multi-tenant messaging platform, directly analogous to the tenant-isolation bug class this
   codebase treats as critical.
2. General software bugs beyond the core loyalty feature: "many bugs beyond the loyalty program
   functionality" [review] (same source, via search summary).
3. Pricing complaint on a specific feature: "loyalty cashback works, but the fees are 2.5 times
   higher than other platforms" [review] (same source, via search summary).
4. Slow support-ticket resolution reported alongside the automation bugs [review] (same source,
   via search summary).

**What users praise.** Ratings vary sharply by platform — 3.7/5 on Capterra India (6 reviews),
4.5/5 on Techjockey, 4.8/5 on Trustpilot [review] (https://www.capterra.in/software/1050827/reelo;
https://www.techjockey.com/detail/reelocrm, via search summary). Users cite "excellent customer
support and ease of use, particularly for loyalty programs and automated campaigns," smooth POS
integration and minimal staff training [review] (same sources, via search summary).

---

### Zomato Hyperpure — India restaurant supply procurement (India extra)

**Why included.** India-specific extra named directly in scope: a large, India-only B2B supply
platform feeding restaurants directly, structurally different from every generic "supplier
management" feature already logged in `01-platforms.md`/`02-play-store-apps.md` (those are
software managing *a restaurant's own* supplier relationships; Hyperpure *is* a supplier, run by
an aggregator with an obvious channel-conflict incentive worth naming explicitly).

**Target.** Restaurants, cloud kitchens and hotels in India buying fresh produce, dairy, poultry,
groceries, packaged goods and kitchen essentials; started as "WOTU" in 2015, acquired and rebranded
by Zomato in 2018 [blog] (https://managemententhusiast.com/hyperpure-by-zomato-revolutionizing-the-restaurant-supply-chain-in-india/).

**Pricing.** Not a subscription — Hyperpure's revenue model is the margin between what it pays
producers and what it charges the restaurant per order, i.e. pricing is embedded per-SKU rather
than a software fee [blog] (https://cultinvestor.com/zomato-hyperpure-business-model/). No
software "price" to record; the commercial question for a restaurant is per-item cost competitiveness
versus its existing mandi/local-supplier prices, not a subscription decision.

**Core workflow, step by step.**
1. **Sourcing.** Hyperpure runs a farm-to-fork model, sourcing directly from farmers, mills and
   producers to bypass traditional wholesale middlemen (mandi traders/agents), aiming to cut cost
   and shorten the chain versus a restaurant sourcing informally itself [blog]
   (https://inc42.com/features/inside-zomatos-hyperpure-the-battle-to-control-indias-54-bn-restaurant-economy/).
2. **Warehousing, QC, catalog.** Hyperpure itself handles warehousing, storage and quality control
   before an item ever reaches the restaurant's order screen — the restaurant is buying an already-
   quality-checked SKU from a catalog, not negotiating with an individual mandi vendor on a given
   morning [blog] (https://managemententhusiast.com/hyperpure-by-zomato-revolutionizing-the-restaurant-supply-chain-in-india/).
3. **Ordering.** A restaurant places orders through the Hyperpure app, browsing the catalog; the
   app's cart/checkout flow has been iterated on (a single-screen review-and-finalize cart) and
   supports recording a voice note with delivery instructions for the delivery agent [marketing]
   (search-aggregated Apple App Store update-notes summary).
4. **Delivery.** Supplies are promised for next-morning delivery within a selected time slot (e.g.
   9–10 AM, 12–1 PM); in practice, per user reviews, delivery personnel frequently arrive earlier
   than the selected slot, unpredictably [review] (search-aggregated App Store review summary).
5. **Consolidation value proposition.** Instead of managing many separate suppliers for produce,
   dairy, poultry and groceries, a restaurant buys everything from one catalog with (claimed)
   consistent quality and predictable pricing [blog] (https://cultinvestor.com/zomato-hyperpure/).

**What it automates vs. asks a human.** Automates: sourcing/QC/warehousing that a small
independent restaurant would otherwise do informally itself (or not do at all); single-catalog
ordering in place of managing many separate supplier relationships/phone calls. Human-required:
still placing the order, choosing a delivery slot, and — per the complaints below — chasing
resolution when an order doesn't match what was promised.

**Handling of bad/missing data.** Not applicable in the software sense — Hyperpure is the supplier,
not a tool a restaurant configures with its own data. The relevant "bad data" risk runs the other
direction: a restaurant depending on Hyperpure's catalog/QC has no independent way to verify what
it receives beyond visual inspection on delivery.

**Feature-area bullets.**
- G (Procurement): the ceiling case of *replacing* fragmented informal supplier relationships with
  a single QC'd catalog and predictable next-day delivery — the polar opposite approach from every
  OCR-invoice-digitization feature logged elsewhere in this file, which digitizes messy supplier
  relationships rather than replacing them [blog]
  (https://cultinvestor.com/zomato-hyperpure/).
- I/channel: run by the same company (Zomato) that also owns the restaurant's biggest aggregator-
  ordering channel — a structural conflict of interest worth flagging explicitly: the aggregator
  that takes a commission on a restaurant's sales is also positioned to be its supplier and take a
  margin on its costs [blog] (https://inc42.com/features/inside-zomatos-hyperpure-the-battle-to-control-indias-54-bn-restaurant-economy/).

**What users complain about.**
1. Delivery-time unpredictability despite a selected slot: "delivery personnel often arrive much
   earlier — sometimes unpredictably" [review] (search-aggregated App Store review summary).
2. Recurring, unresolved fulfillment problems: "delayed transport, missing items, last-minute
   cancellations, damaged packaging, poor quality produce, inconsistent stock availability, and
   random rate changes," with "complaints raised multiple times have not been resolved properly,
   with same issues repeating with no improvement" [review] (search-aggregated App Store review
   summary — a serious, repeated-failure pattern, not an isolated complaint).

**What users praise.** Not found at the individual-reviewer level in this session — search results
skewed toward the complaint pattern above and toward business-model analysis pieces rather than
satisfied end-user testimony; the underlying value proposition (sourcing/QC/logistics consolidation)
is well documented in blog analysis but not corroborated by positive first-person restaurant
reviews found here.

---

### Tenzo — sales & labour forecasting (India-relevant extra: the sales/labour forecasting
category the brief asked to check)

**Why included.** Named directly in scope as the "Tenzo or similar" sales/labour forecasting
category check; included as the specialist ceiling for demand forecasting distinct from 7shifts'
labor-scheduling-embedded forecast (7shifts forecasts primarily to build a schedule; Tenzo forecasts
as its entire product and feeds the number *into* other systems).

**Target.** Multi-site restaurant groups wanting a forecasting/analytics layer that sits on top of,
and pushes into, their existing POS, labour and inventory tools rather than replacing them
[marketing] (https://www.gotenzo.com/product-predict/).

**Pricing (2026-09-13).** No public price list; one third-party aggregator cites a starting figure
of "$600/year," with a free trial offered, but pricing is otherwise quote-based [pricing]
(search-aggregated summary, unverified against a primary vendor source).

**Core workflow, step by step.**
1. **Data ingestion.** Tenzo combines granular POS transaction data with external signals —
   weather, local events, holidays — and applies machine learning to forecast demand [marketing]
   (https://www.gotenzo.com/resources/insight/ai-demand-forecasting-for-restaurants/).
2. **Minimum viable data vs. optimal data.** The AI engine can begin forecasting with as little as
   90 days of history, but reaches its best accuracy with two years of historical data (needed to
   learn seasonality and annual event patterns) — an explicit, quantified cold-start threshold not
   found stated this precisely by any other forecasting feature in this research set [marketing]
   (https://www.gotenzo.com/resources/insight/restaurant-sales-forecasting-a-comprehensive-guide/).
3. **Forecast horizon and accuracy claim.** Predicts sales up to 21 days ahead, claimed to reduce
   forecasting error by 30–50% versus traditional (non-ML) approaches and to cut labour costs by
   5–10% as a downstream effect of better-matched staffing [marketing] (same URL) — vendor-supplied
   claims, not independently audited.
4. **Manager approval.** A GM reviews and approves the forecast before it's used downstream — a
   human-in-the-loop checkpoint rather than fully automatic staffing/ordering action [marketing]
   (https://www.gotenzo.com/resources/insight/ai-demand-forecasting-for-restaurants/).
5. **Breakdown and downstream push.** Once approved, the forecast is broken down by hour and by
   menu item, then pushed via API into external labour-scheduling tools (Deputy, Planday,
   RotaReady are named integration targets) so those tools can auto-generate rotas from Tenzo's
   forecast rather than their own weaker built-in one [marketing] (same URL). This makes Tenzo a
   forecasting layer that feeds other specialists, rather than a closed system like 7shifts'
   built-in forecast.

**What it automates vs. asks a human.** Automates: multi-signal demand forecasting (weather/
events/seasonality/history combined), hourly and per-item breakdown, and pushing the result into
connected labour tools. Human-required: the GM approval gate before a forecast is acted on, and
actually building rotas/orders in whichever downstream tool consumes the forecast (Tenzo itself is
not a scheduler or ordering tool).

**Handling of bad/missing data.** The 90-day minimum before the engine will forecast at all is the
one explicit, quantified cold-start threshold found among all forecasting features in this
research set — directly relevant to a genuinely new restaurant with zero sales history, which by
this stated threshold could not use Tenzo meaningfully until ~3 months of trading data exists
[marketing] (https://www.gotenzo.com/resources/insight/restaurant-sales-forecasting-a-comprehensive-guide/).

**Feature-area bullets.**
- M: the most explicit, quantified minimum-viable-data threshold (90 days) and accuracy-vs-data-
  volume claim (2 years for full seasonality) of any forecasting feature found in this file —
  directly useful as a ceiling benchmark against 7shifts' 95%/90% accuracy claims, which do not
  state a minimum data requirement [marketing] (https://www.gotenzo.com/resources/insight/restaurant-sales-forecasting-a-comprehensive-guide/;
  https://kb.7shifts.com/hc/en-us/articles/4417514442771-The-Labor-Budget-Tool, via search
  summary).
- L: forecast pushed via API into third-party labour tools (Deputy/Planday/RotaReady) — a
  "forecasting-as-upstream-service" architecture distinct from every other product in this file,
  which builds forecasting directly into its own scheduling/ordering UI [marketing]
  (https://www.gotenzo.com/resources/insight/ai-demand-forecasting-for-restaurants/).
- Q: 90-day cold-start floor is itself an onboarding-effort data point — a new restaurant gets
  materially less value in month one than month four.

**What users complain about.** Minimal complaints found; the one negative signal located was a
change of mind, not a standing complaint: "some users had the initial view that Tenzo was
expensive and didn't do anything for the business," which the source states was reversed on
further evaluation [review] (https://reviews.financesonline.com/p/tenzo/, via search summary).
Pricing opacity (no public figure) is itself worth logging as a friction point for a small
operator trying to budget.

**What users praise.** Trustpilot rating of 4.9/5 across ~94 reviews — one of the highest review
scores found in this entire research set [review] (https://www.trustpilot.com/review/gotenzo.com,
via search summary). Specific praise: "massive positive impact... stronger sales, lower wage
costs, and more communication from managers," and the dashboard is called "a game changer for
business decisions" [review] (same source, via search summary).
<!-- PRODUCT_SECTIONS_END -->

---

## What users complain about / What users praise

<!-- COMPLAINTS_PRAISE_START -->
Full quotes and links are under each product's own "What users complain about" / "What users
praise" subsections above. This index is a one-line-per-product pointer so the pattern across the
whole group is visible at a glance.

| Product | Top complaint theme | Top praise theme |
|---|---|---|
| MarketMan | Cancellation/retention friction (60-day notice, forced retention calls) | Time saved on invoice capture; intuitive for managers |
| Supy | Thin independent review footprint; "prone to human error" (single G2 snippet) | Fast (~15-day) setup; strong support/analytics scores (secondhand) |
| Restaurant365 | Broken onboarding while billing continued; bugs after updates; site down during close weeks | Support "fixes right away" once engaged; 4.1/5 overall |
| meez | Buggy ingredient deletion; slow up/download; "concepts" confusing for hotels | "Excellent program... created for chefs"; fast recipe entry |
| Apicbase | Complicated setup; POS/supplier sync bugs corrupt report data | 4.5-4.6/5 ratings; "changed our operations for the better" |
| Winnow | Not found — no individual reviewer/rating located | Not found at individual level; only aggregate vendor ROI claims |
| Orbisk | Not found — no independent customer review located at all | Not found — same gap |
| SalaryBox | Steep renewal/scale pricing jump; app freezing | "Highly affordable"; accurate GPS/selfie attendance |
| EZHRM | Not found — thinnest evidence base of the three staff tools | Generic "ease of use" praise, unattributed |
| 7shifts | Login instability (404 errors); notification reliability; forecasting gated behind paid add-on | 4.7/5 across 1,211 reviews; "more agile... than payroll company alternatives" |
| SafetyCulture | Sync delays under load/poor connectivity; free-tier feature ceiling; per-user pricing burden | Short learning curve for frontline staff; strong corrective-action accountability |
| Reelo | Auto-campaign bug sent wrong restaurant's name to customers; fees "2.5x higher" than alternatives | "Excellent customer support"; smooth POS integration |
| Zomato Hyperpure | Repeated, unresolved fulfillment failures (missing items, wrong rates, delays) | Not found at individual level in this session |
| Tenzo | Pricing opacity; one reversed "seemed expensive" first impression | 4.9/5 on Trustpilot; "game changer for business decisions" |

**Pattern worth naming.** The three category leaders with genuine public help-centres (7shifts,
SafetyCulture, and Restaurant365/MarketMan/meez/Apicbase for costing) also have the deepest,
most specific, most negative complaint threads — because they have enough reviewers to generate
them. The waste-camera category (Winnow, Orbisk) and the two smaller India HR tools (SalaryBox
being the exception with real Play Store complaints, EZHRM not) show almost no independent review
footprint at all — a small buyer evaluating them has materially less third-party signal to go on
than for the inventory/costing or scheduling categories.
<!-- COMPLAINTS_PRAISE_END -->

---

## The ceiling per capability

<!-- CEILING_START -->
For each area, what the best specialist here does that an all-in-one POS (per `01-platforms.md`)
typically does not.

**E — Recipes & food costing.**
- **Named, ranked, public troubleshooting for *why a recipe won't cost*.** meez's "Top 4 reasons"
  (missing purchase cost/unit → duplicate ingredient names → missing recipe quantity/unit →
  missing unit equivalency) is a decision tree, not a vague "check your data" message
  [help] (https://intercom.help/getmeez/en/articles/7204464-top-4-reasons-why-your-recipes-aren-t-costing).
  All-in-one platforms in `01-platforms.md` claim "recipe/BOM-based costing" as a feature line but
  none publish this level of failure-mode documentation.
- **Labor cost folded into per-dish cost as a first-class input**, not just ingredients — Apicbase's
  prime-cost model (ingredient cost + waste% + prep/cook/plate labor-hours × rate) [help]
  (https://support.apicbase.com/help/food-cost-calculation). No all-in-one platform surveyed
  computes a per-dish cost this way.
- **Unit equivalency as a first-class, explicit data object** the user manages (not an implicit
  conversion buried in a settings screen) — meez again [help]
  (https://intercom.help/getmeez/en/articles/5344988-costing-your-recipes).

**F — Inventory & stock.**
- **Parallel, template-driven counting with auto-merge** across multiple simultaneous counters, cut
  to under half the time of ad hoc counting — Supy [marketing/blog]
  (https://supy.io/blog/learn-restaurant-stock-management-software).
- **Counting that survives a genuine offline "dead zone"** as a named, specifically engineered
  feature (not just "the app has an offline mode") — Supy [blog]
  (https://supy.io/blog/learn-restaurant-stock-count-offline). MarketMan's mobile count sync is
  similar but less explicitly documented as designed-for-dead-zones.
- **A completed inventory count posting directly as the accounting journal entry** — no separate
  reconciliation between "what ops counted" and "what accounting booked" — Restaurant365 [help]
  (https://help.restaurant365.net/support/solutions/articles/12000075374-inventory-counts-create-and-enter-an-inventory-count,
  via search summary).

**G — Procurement & suppliers.**
- **A named, repeatable receiving-error workflow tied to unit-of-measure mismatches**, flagged as
  the single most common source of downstream cost errors — Restaurant365's WEPT "Errors" step
  explicitly calls out "wrong units of measure on invoices" [help]
  (https://docs.restaurant365.com/docs/actual-vs-theoretical-analysis-troubleshooting-variances).
- **OCR/invoice processing tolerant of handwritten, non-standard supplier paperwork**, not just
  clean digital invoices — MarketMan and meez's invoice-processing service both explicitly claim
  handwritten-document support [marketing/help]
  (https://www.marketman.com/page/restaurant-invoice-management-system;
  https://intercom.help/getmeez/en/articles/5344988-costing-your-recipes).
- **Replacing fragmented informal sourcing with a single QC'd, next-day catalog** entirely —
  Hyperpure's model is qualitatively different from every "digitize the supplier relationship"
  feature elsewhere: it removes the fragmented-supplier problem rather than managing it [blog]
  (https://cultinvestor.com/zomato-hyperpure/).

**H — Theoretical vs actual variance / food-cost control.**
- **A named, repeatable, four-cause root-cause framework baked into the product's own
  documentation** (Restaurant365's WEPT: Waste / Errors / Portioning / Theft), with an explicit
  drill-down sequence (category rollup → item drill-down → invoice check → recipe check → fix →
  re-run) [help] (https://docs.restaurant365.com/docs/actual-vs-theoretical-analysis-troubleshooting-variances).
  Apicbase names the same four causes but without an equally explicit workflow.
- **Multi-site variance shown at group/site/category/item granularity specifically to prevent one
  high-performing site from masking an underperforming one in a blended number** — Supy [blog]
  (https://supy.io/blog/learn-theoretical-vs-actual-food-cost-variance). An all-in-one platform's
  single-restaurant deployment in `01`/`02` has no equivalent need or feature.
- **Continuous, automatic, ingredient-level *input* to the waste half of the variance equation** —
  Winnow/Orbisk's camera+scale capture supplies real waste weight/cost/reason data with zero staff
  logging, versus every other product in this file that relies on a human writing waste into a log
  [marketing] (https://www.winnowsolutions.com/product/food-waste-management-software;
  https://orbisk.com/product/how-it-works/). No all-in-one POS surveyed has an equivalent
  automatic-capture waste input.

**K — CRM, loyalty, feedback, marketing.**
- **Automatic behavioral (RFM) segmentation driving per-segment, not per-list, WhatsApp message
  content**, with revenue attributed back to the individual campaign — Reelo [marketing]
  (https://reelo.io/blog/restaurant-crm-with-whatsapp-marketing-the-complete-guide). The all-in-one
  platforms' WhatsApp features (GoFrugal, Rista, per `01-platforms.md`'s merged table) are
  broadcast/bill-delivery tools, not behavior-triggered segmentation engines.

**L — Staff: roles, attendance, shifts, payroll, performance.**
- **Five interchangeable attendance-capture modalities in one product** (face recognition, QR
  kiosk, geofence, field GPS, plain selfie) purpose-built against a named integrity threat
  ("buddy punching") — SalaryBox [marketing]
  (https://salarybox.in/salarybox-attendance-management-how-ai-selfie-geofencing-and-smart-attendance-tracking-are-eliminating-buddy-punching-for-indian-businesses/).
- **A live labor-cost-vs-sales-target dashboard visible *while building the schedule*, before it's
  published** — not a report generated afterward — 7shifts' Labor Budget Tool [help]
  (https://kb.7shifts.com/hc/en-us/articles/4417514442771-The-Labor-Budget-Tool, via search
  summary), with a second, hourly-granularity layer (Optimal Labor, claimed 90% accuracy) on top.

**M — Reports, dashboards, analytics, forecasting, AI.**
- **A stated, quantified minimum-data threshold for when AI forecasting becomes reliable** (90 days
  to start, 2 years for full seasonality) — Tenzo is the only product in this entire research set
  (all three files) that states this number explicitly rather than implying forecasting "just
  works" from day one [marketing] (https://www.gotenzo.com/resources/insight/restaurant-sales-forecasting-a-comprehensive-guide/).
- **A forecast as a portable, API-delivered service consumed by other specialist tools**
  (Deputy/Planday/RotaReady), rather than a number locked inside one vendor's own scheduling UI —
  Tenzo [marketing] (https://www.gotenzo.com/resources/insight/ai-demand-forecasting-for-restaurants/).

**N — Compliance (food safety, licences, audits).**
- **A closed loop from an IoT sensor breach to an auto-generated, assigned corrective action with a
  due date**, with zero human noticing-the-problem step — SafetyCulture's sensor+gateway+alert+
  corrective-action chain [help] (https://help.safetyculture.com/000068). All-in-one platforms
  surveyed in `01`/`02` have wastage tracking or generic compliance mentions, but none combine
  continuous IoT sensing with automatic corrective-action assignment.

**Q — Onboarding & setup effort.**
- **A fully public, granular price list with zero "contact sales" gating below Enterprise** — meez
  is the only product in this entire three-file research set with every tier and every add-on
  publicly priced, letting a buyer self-qualify with no sales call [pricing]
  (https://www.getmeez.com/pricing).
- **Same-day, zero-training hardware deployment** — Orbisk's and Winnow's claimed setup (15 minutes
  to assemble a pole-mounted unit, "0 hrs training," "accurate from day one") is the fastest
  time-to-value claimed anywhere in this file, because there is no menu/recipe/item data entry step
  at all — the hardware just watches a bin [help/marketing]
  (https://www.winnowsolutions.com/en/faq; https://orbisk.com/product/how-it-works/).
<!-- CEILING_END -->

---

## Does it transfer to India?

<!-- INDIA_START -->
For each ceiling item above: what breaks or changes for a single-outlet Indian restaurant with no
records kept, handwritten supplier bills, WhatsApp ordering, mixed-literacy staff, loose units
("1 packet," "1 katori"), cash-heavy transactions, and power/network cuts.

**E — Recipes & food costing.**
- meez's "Top 4 reasons" decision tree — **needs adaptation.** The framework itself (missing
  cost/unit, duplicate names, missing quantity/unit, missing equivalency) transfers conceptually,
  but its worst-case trigger — "if no unit given, meez assumes 'each'" — is *routine*, not an edge
  case, for an Indian kitchen that measures in "1 packet," "1 katori," "andaz se" (by estimate), or
  a fistful of an ingredient. A tool built against this reality needs a much larger default
  vocabulary of loose/local units with built-in equivalencies, not just a warning when a unit is
  missing.
- Apicbase's labor-cost-in-recipe model — **needs adaptation.** Prepping/cooking/plating
  hourly-rate labor costing assumes tracked hourly wages per task; a single-outlet Indian
  restaurant's kitchen staff are more often paid a flat monthly salary with informally divided
  tasks, so the "labor hours × hourly rate per recipe" input would need a different unit of
  measurement (e.g., allocated staff-time-share, not a punched hourly rate) to be meaningful.
- Unit equivalency as an explicit object — **transfers**, and is in fact *more* necessary here than
  in a US/EU kitchen precisely because purchase units (a bori of rice, a tin of ghee, a bundle of
  coriander) rarely match recipe units cleanly.

**F — Inventory & stock.**
- Parallel template-driven counting with auto-merge (Supy) — **transfers.** Multiple staff counting
  simultaneously is workflow-neutral; the harder problem for India is the *template* itself needing
  to be built around loose retail units rather than assuming standardized case/pack sizes.
- Counting that survives an offline dead zone (Supy) — **transfers directly and is more relevant
  here**, not less: India's power/network reliability is generally worse than the US/EU markets
  these tools were built for, so "the count isn't lost if wifi drops in the walk-in" matters more
  for a single Indian outlet than for the chains these vendors were designed around.
- A completed count posting straight to the accounting ledger (Restaurant365) — **needs
  adaptation.** This assumes a restaurant already runs formal double-entry accounting connected to
  the same platform. Per this codebase's own compliance/domain docs and the memory record that
  "Indian restaurants keep no records," most single-outlet operators have no such formal ledger to
  post into — the feature is real, but its precondition (an existing accounting system) frequently
  does not exist yet.

**G — Procurement & suppliers.**
- Unit-of-measure-mismatch error handling (Restaurant365's WEPT "Errors" step) — **transfers, and
  is the single most directly relevant ceiling item in this whole file** for the stated India
  reality: handwritten supplier bills quoting "1 bori," "1 tokri," "1 katta" are exactly the
  unit-mismatch failure mode this feature is built to catch, just in a market this feature wasn't
  designed for.
- OCR tolerant of handwritten invoices (MarketMan, meez) — **needs adaptation.** Both vendors claim
  handwritten support, but their training data is presumably English-language, Western-supplier-
  format invoices; an Indian kacha bill (often a small paper slip, sometimes in Hindi/regional
  script, with inconsistent structure) is a different OCR problem than a US supplier's printed
  invoice with a slightly messy handwritten total. The *concept* transfers; the *trained model*
  almost certainly does not without India-specific retraining — this is exactly the compliance-file
  warning about not assuming Western tooling generalizes.
- Hyperpure's catalog-replaces-fragmentation model — **transfers as a concept but is Zomato-
  specific infrastructure**, not something this codebase's target customer can adopt directly; it's
  relevant here only as evidence that *some* single-outlet Indian restaurants already have access
  to this kind of consolidated procurement, which sets a customer expectation this product doesn't
  need to build itself but could integrate against.

**H — Variance / food-cost control.**
- The WEPT four-cause framework — **transfers directly.** Waste, errors, portioning and theft are
  universal restaurant failure modes; nothing about the framework itself is US/EU-specific.
- Multi-site variance-masking prevention (Supy) — **does not apply** to a single-outlet product by
  definition; this is a multi-branch-specific ceiling item with no analogue for one restaurant.
- Automatic camera+scale waste capture (Winnow/Orbisk) — **needs substantial adaptation.** The
  hardware and subscription cost (quote-based, likely priced for a US/EU commercial kitchen budget)
  is a mismatch for a cash-constrained single Indian outlet; more fundamentally, the AI models are
  trained on largely Western food imagery (per Orbisk's own "800+ ingredients," Winnow's "1,000
  food items" — figures not stated as India-specific), so recognition accuracy on Indian dishes,
  gravies, and mixed-waste patterns (a thali's assorted leftovers, for instance) is unverified and
  plausibly much lower than the vendor-quoted 90% figure. The *idea* (automatic, no-logging waste
  capture) transfers; the specific product does not, without India-specific model retraining.

**K — CRM, loyalty, feedback, marketing.**
- RFM-triggered WhatsApp segmentation (Reelo) — **transfers well, and is arguably the single best
  fit of any ceiling item in this file to the stated India context.** WhatsApp is already the
  dominant customer-communication channel named in scope ("WhatsApp ordering"), and Reelo is
  India-built specifically around this. The multi-tenant messaging bug found in its complaints
  (wrong restaurant name sent to a customer) is a direct, concrete cautionary example for this
  codebase's own tenant-isolation invariant (CLAUDE.md invariant #1) — worth treating as a real-
  world instance of the exact bug class this product must never ship.

**L — Staff: attendance, shifts, payroll.**
- Five-modality attendance capture (SalaryBox) — **transfers directly and is already built for
  this market**; SalaryBox is an Indian product, and modalities like GPS/geofence explicitly serve
  mixed-literacy staff (no typed login needed, just a selfie or a QR scan) and cash-heavy, informal
  hiring norms (fraud prevention against "buddy punching" is named as the specific local pain
  point).
- Live labor-budget-vs-sales dashboard during scheduling (7shifts) — **needs adaptation.** It
  assumes an hourly, shift-based wage structure and a POS feeding live sales; a single-outlet
  Indian restaurant more often pays fixed monthly salaries with informal shift assignment, so the
  "labor cost vs. sales, live" framing needs to be rebuilt around a different staffing-cost model
  (monthly salary allocation, not hourly wage × hours scheduled) to produce a meaningful number.

**M — Reports, dashboards, analytics, forecasting, AI.**
- Tenzo's quantified 90-day/2-year data thresholds — **transfers as a warning, not a feature.**
  The number itself is a generic ML data-volume fact, not something to copy verbatim, but the
  *practice* of stating a minimum-data floor is exactly what this codebase's own "cold start is the
  central product risk" position (per the user's memory record) should adopt: never claim reliable
  forecasting before a stated volume of real transaction history exists, and say so to the user
  rather than silently producing a low-confidence number.
- API-delivered forecast consumed by other tools (Tenzo) — **does not apply** in the same form to
  a single-outlet product with no external labour-tool ecosystem to push into, but the *pattern*
  (separate the forecasting engine from the scheduling UI, so forecast quality can improve
  independently) is a valid architectural lesson regardless of market.

**N — Compliance (food safety, licences, audits).**
- IoT sensor breach → auto-generated corrective action (SafetyCulture) — **needs adaptation.**
  Wireless temperature sensors and gateways are real hardware costs and assume stable power and a
  local network gateway; a single Indian outlet with frequent power cuts needs the sensor/gateway
  combination to tolerate outages gracefully (battery-backed sensors, store-and-forward on
  reconnect) rather than assuming continuous connectivity — the underlying *checklist +
  corrective-action* software pattern transfers fine without any hardware at all, which is the more
  realistic entry point for this market.

**Q — Onboarding & setup effort.**
- meez's fully public pricing — **transfers directly** as a positioning lesson: a self-serve,
  no-sales-call price list lowers the trust/effort barrier for a first-time software buyer, which
  matters more, not less, in a market where the customer has never used software like this before.
- Camera+scale zero-training hardware setup (Orbisk/Winnow) — **needs adaptation.** "0 hrs
  training" assumes staff already understand what a waste-tracking system is watching for and why;
  a mixed-literacy staff with no prior exposure to being monitored by a camera may need explicit,
  in-person explanation regardless of how little the *software* requires them to do — the technical
  training burden is genuinely zero, but the change-management/trust burden is not.
<!-- INDIA_END -->

---

## Merged feature table

<!-- FEATURE_TABLE_START -->
| Area | Feature | Products that have it | Evidence tags | Source URLs |
|---|---|---|---|---|
| E | Recipe costing fails-with-named-reasons troubleshooting (missing cost/unit, duplicate name, missing qty/unit, missing equivalency) | meez | help | intercom.help/getmeez/en/articles/7204464-top-4-reasons-why-your-recipes-aren-t-costing |
| E | Labor cost (prep/cook/plate hourly rate) folded into per-dish prime cost | Apicbase | help | support.apicbase.com/help/food-cost-calculation |
| E | Unit-equivalency as an explicit, user-managed data object | meez | help | intercom.help/getmeez/en/articles/5344988-costing-your-recipes |
| E | AI recipe import (photo/format → structured recipe) | meez | pricing | getmeez.com/pricing |
| E | Per-serving cost normalization regardless of batch size | Apicbase | help | support.apicbase.com/help/food-cost-calculation |
| E | Target-margin solver in both directions (fixed price → target cost, or vice versa) | Apicbase | help | support.apicbase.com/help/food-cost-calculation |
| F | Perpetual (POS-linked, real-time) inventory depletion on sale | MarketMan, Supy | marketing | marketman.com/page/perpetual-inventory; supy.io/blog/learn-restaurant-stock-management-software |
| F | Parallel multi-counter counting with auto-merge | Supy | marketing/blog | supy.io/blog/learn-restaurant-stock-management-software |
| F | Counting explicitly engineered to survive an offline "dead zone" | Supy | blog | supy.io/blog/learn-restaurant-stock-count-offline |
| F | OCR invoice capture explicitly tolerant of handwritten bills | MarketMan, meez | marketing/help | marketman.com/page/restaurant-invoice-management-system; intercom.help/getmeez/en/articles/5344988-costing-your-recipes |
| F | Completed inventory count posts directly as the accounting GL journal entry | Restaurant365 | help | help.restaurant365.net/support/solutions/articles/12000075374 (via search summary) |
| F | Inter-branch stock transfer requires receiver acceptance before adjustment applies | Supy | marketing | supy.io/blog/learn-restaurant-stock-management-software |
| F | Stockable semi-finished/sub-recipe tracked as its own inventory item | Apicbase | help | support.apicbase.com/help/adding_semifinished_product_to_stock |
| G | AI-forecast-driven auto-drafted purchase orders from recipe + par + 14-day sales forecast | Supy | marketing | supy.io/blog/learn-restaurant-stock-management-software |
| G | Email-forwarded invoice ingestion (no photo step) | MarketMan (Enterprise) | pricing | marketman.com/pricing-for-restaurant-inventory-management-system |
| G | Vendor EDI integrations, tiered by plan | MarketMan | pricing | marketman.com/pricing-for-restaurant-inventory-management-system |
| G | Single QC'd farm-to-fork supply catalog replacing fragmented informal sourcing | Zomato Hyperpure | blog | cultinvestor.com/zomato-hyperpure-business-model |
| H | Named four-cause (WEPT) variance root-cause framework with an explicit drill-down sequence | Restaurant365 | help | docs.restaurant365.com/docs/actual-vs-theoretical-analysis-troubleshooting-variances |
| H | Variance shown at group/site/category/item granularity to prevent cross-site masking | Supy | blog | supy.io/blog/learn-theoretical-vs-actual-food-cost-variance |
| H | Three separately named variance reports at different grains (theoretical-vs-actual, summary, usage-w/-theo) | Restaurant365 | help | docs.restaurant365.com/docs/theoretical-vs-actual-report; radar.help.restaurant365.com (summary + usage-variance articles) |
| H | Fully automatic, no-logging waste capture by weight/item/cost via camera+scale | Winnow, Orbisk | marketing | winnowsolutions.com/product/food-waste-management-software; orbisk.com/product/how-it-works |
| H | Waste data broken down by ingredient, waste stream, AND serving stage, with a ranked fix-list | Orbisk | marketing | orbisk.com/product/how-it-works |
| K | RFM auto-segmentation driving per-segment WhatsApp campaign content, with per-campaign revenue attribution | Reelo | marketing | reelo.io/blog/restaurant-crm-with-whatsapp-marketing-the-complete-guide |
| K | Three selectable loyalty structures (points/visit/spend-based) | Reelo | marketing | reelo.io/blog/best-crm-for-restaurants-in-india-5-platforms-compared |
| L | Five interchangeable attendance-capture modalities (face, QR kiosk, geofence, field GPS, selfie) in one product | SalaryBox | marketing | salarybox.in/salarybox-attendance-management-how-ai-selfie-geofencing-and-smart-attendance-tracking-are-eliminating-buddy-punching-for-indian-businesses |
| L | IP-based (local office network) attendance for fixed-premises staff | EZHRM | marketing | ezhrm.in/ip-based-attendance |
| L | Live labor-cost-vs-sales-target dashboard during schedule building (not after) | 7shifts | help | kb.7shifts.com (Labor Budget Tool, via search summary) |
| L | Hourly-granularity labor/sales recommendation layer on top of a weekly budget | 7shifts | help | kb.7shifts.com (Optimal Labor Tool, via search summary) |
| L | Attendance-to-payroll reconciliation with zero manual register step | SalaryBox, EZHRM | marketing | salarybox.in (search summary); ezhrm.in/features |
| M | Stated, quantified minimum-data threshold for reliable AI forecasting (90 days / 2 years) | Tenzo | marketing | gotenzo.com/resources/insight/restaurant-sales-forecasting-a-comprehensive-guide |
| M | Forecast delivered via API into third-party labour tools (Deputy/Planday/RotaReady) rather than locked into one UI | Tenzo | marketing | gotenzo.com/resources/insight/ai-demand-forecasting-for-restaurants |
| M | GM approval gate before an AI forecast is acted on | Tenzo | marketing | gotenzo.com/resources/insight/ai-demand-forecasting-for-restaurants |
| N | Wireless IoT temperature sensor + gateway with configurable breach thresholds | SafetyCulture | help | help.safetyculture.com/000068 |
| N | Automatic corrective-action creation (assignee, priority, due date) on a sensor breach, with zero human noticing-the-problem step | SafetyCulture | help | help.safetyculture.com/000068 |
| N | Restaurant-zone-specific checklist library (walk-ins, dish pits, mop stations, ice machines named individually) | SafetyCulture | marketing | safetyculture.com/library/hospitality/food-safety-inspection-check-list-80wlikxzckvrwcqb |
| Q | Fully public, granular price list with zero "contact sales" gate below Enterprise | meez | pricing | getmeez.com/pricing |
| Q | Same-day, zero-training hardware install (no menu/recipe data entry required at all) | Orbisk, Winnow | marketing/help | orbisk.com/product/how-it-works; winnowsolutions.com/en/faq |
| Q | Vendor-assisted 24-48 hour go-live including POS integration done by the vendor | Reelo | marketing | (search-aggregated, reelo.io) |
| R | Per-location (not per-employee) SaaS pricing on the base scheduling product | 7shifts | pricing | costbench.com/software/employee-scheduling/7shifts (search summary) |
| R | Genuine no-time-limit free tier for a single location under a headcount cap | 7shifts (Comp, <30 staff) | pricing | costbench.com/software/employee-scheduling/7shifts (search summary) — *also in 01 (Restrofi's free tier)* |
| R | Combined flat-fee-or-per-user pricing, user's choice | SalaryBox | pricing | salarybox.in/pricing |
| R | Revenue-margin-embedded pricing (no software subscription at all — supplier margin is the fee) | Zomato Hyperpure | blog | cultinvestor.com/zomato-hyperpure-business-model |
<!-- FEATURE_TABLE_END -->

---

## Unusual or distinctive features

<!-- UNUSUAL_START -->
- **Two direct competitors litigated a patent over vision-based waste tracking at the Unified
  Patent Court.** Winnow Solutions sued Orbisk over camera+scale waste-recognition technology; the
  court found no infringement by Orbisk and partially revoked Winnow's patent (2025-08-13,
  ACT_36388/2024) [blog] (https://www.mlex.com/mlex/articles/2376515/upc-partially-revokes-winnow-patent-finds-no-infringement-by-orbisk).
  Neither product surveyed elsewhere in this research (across all three files) has a documented
  patent dispute with a direct competitor.
- **A restaurant CRM's automation bug sent customers messages branded with the *wrong* restaurant's
  name** — Reelo's reported "auto campaign" defect, where restaurant identity in an outbound
  WhatsApp message was swapped to a different tenant's name [review]
  (https://www.capterra.in/software/1050827/reelo, via search summary). This is a concrete,
  real-world instance of exactly the tenant-isolation bug class this codebase's own CLAUDE.md
  treats as its "#1 bug class" — worth keeping as a cautionary example, not just an abstract risk.
- **A category (AI waste cameras) with almost no independent customer review footprint at all** —
  neither Winnow nor Orbisk turned up a single individually-attributed customer review (star
  rating, named reviewer, specific quote) across Capterra, G2, or Trustpilot in this session; all
  available evidence was vendor marketing, a data-labeling partner's case study, or litigation
  coverage. This is a meaningfully thinner evidence base than every other category in this file.
- **A vendor whose own review-platform listing still carries an old product name.** SafetyCulture's
  Capterra page URL and product title still say "iAuditor" (its name before a rebrand) and, as of
  this session, also displays "Mitti (by SafetyCulture)" — two different historical/alternate names
  visible on one live listing [review] (https://www.capterra.com/p/141080/iAuditor/reviews/).
- **A quantified, stated minimum-data floor before AI forecasting is trusted** — Tenzo's 90-day
  minimum / 2-year-for-full-seasonality claim is the only place in this entire three-file research
  project (01, 02, and 03 combined) where a vendor states a specific data-volume threshold for its
  own forecasting confidence, rather than implying the AI works well from day one [marketing]
  (https://www.gotenzo.com/resources/insight/restaurant-sales-forecasting-a-comprehensive-guide/).
- **A software product whose entire cost structure is a supply-chain margin, not a subscription.**
  Zomato Hyperpure has no software "price" at all — the commercial model is baked into per-item
  markup, structurally different from every other product in this file (and in `01`/`02`), all of
  which are SaaS subscriptions [blog] (https://cultinvestor.com/zomato-hyperpure-business-model).
- **The same company that takes a commission on a restaurant's sales (as an aggregator) also
  positions itself to take a margin on that restaurant's costs (as its supplier)** — Zomato/
  Hyperpure's structural dual role, worth naming as a conflict-of-interest pattern distinct from
  anything else surveyed across all three research files [blog]
  (https://inc42.com/features/inside-zomatos-hyperpure-the-battle-to-control-indias-54-bn-restaurant-economy/).
<!-- UNUSUAL_END -->

---

## Sources

<!-- SOURCES_START -->
**MarketMan:** https://www.marketman.com/platform/restaurant-inventory-management-software ·
https://www.marketman.com/page/perpetual-inventory ·
https://www.marketman.com/page/restaurant-invoice-management-system ·
https://www.marketman.com/page/square-restaurant-inventory-management ·
https://www.marketman.com/pricing-for-restaurant-inventory-management-system ·
https://www.capterra.com/p/136439/Marketman-Restaurant-Inventory/pricing/ ·
https://www.capterra.com/p/136439/Marketman-Restaurant-Inventory/reviews/ ·
https://dishcost.com/blog/dishcost-vs-marketman · https://checkthat.ai/brands/marketman/reviews ·
https://www.getsauce.com/post/taking-stock-marketman-cloud-based-restaurant-inventory-management

**Supy:** https://supy.io/platform/restaurant-inventory-management-software ·
https://supy.io/supy-pricing · https://supy.io/blog/learn-restaurant-stock-management-software ·
https://supy.io/blog/learn-restaurant-stock-count-offline ·
https://supy.io/blog/learn-theoretical-vs-actual-food-cost-variance ·
https://www.g2.com/products/supy/reviews (403 to direct fetch; via search snippet)

**Restaurant365:** https://www.restaurant365.com/blog/closing-the-gap-between-actual-and-theoretical-food-costs/ ·
https://docs.restaurant365.com/docs/actual-vs-theoretical-analysis-troubleshooting-variances ·
https://docs.restaurant365.com/docs/theoretical-vs-actual-report ·
https://docs.restaurant365.com/food-variance-report ·
https://radar.help.restaurant365.com/support/solutions/articles/12000084049-summary-variance-report ·
https://radar.help.restaurant365.com/support/solutions/articles/12000084062-usage-variance-w-theo-usage- ·
https://help.restaurant365.net/support/solutions/articles/12000075374-inventory-counts-create-and-enter-an-inventory-count
(title/summary; direct fetch 404'd) ·
https://help.restaurant365.net/support/solutions/articles/12000075375-inventory-counts-review-and-approve-an-inventory-count
(via search summary) · https://docs.restaurant365.com/docs/mobile-inventory-counts-overview (via
search summary) · https://www.capterra.com/p/139768/Restaurant365/pricing/ ·
https://pricingnow.com/question/restaurant365-pricing/ ·
https://www.bbb.org/us/ca/irvine/profile/restaurant-management/restaurant365-1126-1000129633/complaints
(via search summary) · https://www.getapp.com/retail-consumer-services-software/a/restaurant365/
(via search summary) · https://capterra.com/p/139768/Restaurant365/reviews/ (via search summary)

**meez:** https://www.getmeez.com/pricing ·
https://intercom.help/getmeez/en/articles/5344988-costing-your-recipes ·
https://intercom.help/getmeez/en/articles/7204464-top-4-reasons-why-your-recipes-aren-t-costing ·
https://www.getapp.com/hospitality-travel-software/a/meez/reviews/ (via search summary) ·
https://eathealthy365.com/our-honest-meez-recipe-app-review/ (via search summary)

**Apicbase:** https://get.apicbase.com/food-costing-software/ ·
https://get.apicbase.com/food-cost-control/ ·
https://support.apicbase.com/help/food-cost-calculation ·
https://support.apicbase.com/help/adding_semifinished_product_to_stock (title/topic only) ·
https://www.g2.com/products/apicbase/reviews ·
https://capterra.com/p/171584/Apicbase-Restaurant-Management/reviews/ (via search summary)

**Winnow:** https://www.winnowsolutions.com/product/food-waste-management-software ·
https://www.winnowsolutions.com/en/faq · https://www.capterra.com/p/143157/The-Winnow-System/
(direct fetch — 0 reviews found) ·
https://www.mlex.com/mlex/articles/2376515/upc-partially-revokes-winnow-patent-finds-no-infringement-by-orbisk

**Orbisk:** https://orbisk.com/product/how-it-works/ ·
https://www.sama.com/case-studies/orbisk-is-using-accurate-ai-to-help-restaurants-reduce-food-waste-up-to-70 ·
pricing aggregator figure (unverified) via WebSearch, no stable URL retained

**SalaryBox:** https://salarybox.in/pricing/ ·
https://salarybox.in/salarybox-attendance-management-how-ai-selfie-geofencing-and-smart-attendance-tracking-are-eliminating-buddy-punching-for-indian-businesses/ ·
https://salarybox.in/blog/best-attendance-payroll-software-for-restaurants-qsrs-in-india-2026/ ·
https://www.techjockey.com/reviews/salarybox (via search summary); Google Play Store complaints via
search summary (no stable review-page URL retained)

**EZHRM:** https://ezhrm.in/ · https://ezhrm.in/attendance-management/ ·
https://ezhrm.in/ip-based-attendance/ · https://ezhrm.in/features/ ·
https://www.techjockey.com/detail/bharatbills-ezhrm-hr-software

**7shifts:** https://www.7shifts.com/ (via search summary) ·
https://kb.7shifts.com/hc/en-us/articles/4417514442771-The-Labor-Budget-Tool (403 to direct fetch;
via search summary) ·
https://kb.7shifts.com/hc/en-us/articles/4417514452115-The-Optimal-Labor-Tool (via search summary) ·
https://timeforge.com/industry-news/7shifts-simplifies-restaurant-labor-compliance-with-new-forecasting-features/
(via search summary) · https://costbench.com/software/employee-scheduling/7shifts/ (via search
summary) · https://www.workstream.us/blog/7shifts-pricing (via search summary) ·
https://www.capterra.com/p/123038/7shifts-Restaurant-Scheduling/reviews/ (via search summary)

**SafetyCulture:** https://safetyculture.com/library/hospitality/food-safety-inspection-check-list-80wlikxzckvrwcqb ·
https://safetyculture.com/library/hospitality/food-safety-self-inspection-restaurants-1jblenpqt63hmmop ·
https://help.safetyculture.com/000068 · https://help.safetyculture.com/001236 ·
https://help.safetyculture.com/003887 · https://help.safetyculture.com/003295 ·
https://safetyteamtech.com/blog/safetyculture-pricing (via search summary) ·
https://taqtics.co/reviews/safetyculture/ (via search summary) ·
https://www.capterra.com/p/141080/iAuditor/reviews/ (via search summary)

**Reelo:** https://reelo.io/ · https://reelo.io/pricing/ · https://reelo.io/loyalty ·
https://reelo.io/whatsapp-marketing ·
https://reelo.io/blog/restaurant-crm-with-whatsapp-marketing-the-complete-guide ·
https://reelo.io/blog/best-crm-for-restaurants-in-india-5-platforms-compared/ ·
https://www.capterra.in/software/1050827/reelo (via search summary) ·
https://www.techjockey.com/detail/reelocrm (via search summary)

**Zomato Hyperpure:** https://inc42.com/features/inside-zomatos-hyperpure-the-battle-to-control-indias-54-bn-restaurant-economy/ ·
https://managemententhusiast.com/hyperpure-by-zomato-revolutionizing-the-restaurant-supply-chain-in-india/ ·
https://cultinvestor.com/zomato-hyperpure/ · https://cultinvestor.com/zomato-hyperpure-business-model/ ·
Apple App Store review summary and Play Store listing via search (no stable review-page URL
retained)

**Tenzo:** https://www.gotenzo.com/product-predict/ ·
https://www.gotenzo.com/resources/insight/ai-demand-forecasting-for-restaurants/ ·
https://www.gotenzo.com/resources/insight/restaurant-sales-forecasting-a-comprehensive-guide/ ·
https://tenzo.zendesk.com/hc/en-gb/articles/360050700213-Forecasting-your-future-sales (403 to
direct fetch) · https://www.trustpilot.com/review/gotenzo.com (via search summary) ·
https://reviews.financesonline.com/p/tenzo/ (via search summary)

**Referenced for de-duplication only (not re-researched):** `docs/product/competitor-research/01-platforms.md`
· `docs/product/competitor-research/02-play-store-apps.md`
<!-- SOURCES_END -->
