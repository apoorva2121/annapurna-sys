# Competitor Research — Step 1: All-in-One Indian Restaurant Platforms

**Scope:** All-in-one restaurant management platforms competing with Restaurant OS in the Indian
single-outlet/small-chain market: Petpooja, Posist/Restroworks, GoFrugal, Rista, PosBytz,
DineOpen, Recaho, Restrofi — plus UrbanPiper, LimeTray and DotPe (added; see "Extras" below).

**Date checked:** 2026-09-13.

**Method:** Public-source web research only (WebSearch + WebFetch against help centres, pricing
pages, product/feature pages, and review sites — G2, Capterra, SoftwareAdvice, GetApp, Google
Play). No accounts were created and no product was operated. Every claim below carries an
evidence tag: **[help]** (support/knowledge-base article), **[pricing]** (a vendor's own pricing
page), **[marketing]** (vendor site/blog, feature or landing pages), **[review]** (a named user
review on G2/Capterra/Play/Trustpilot/etc.), or **[blog]** (third-party comparison/listicle
content — least trusted, sometimes written by a competitor or an SEO agency working for one).
Where a figure could not be confirmed, this file says "not found" or "unknown" rather than
guessing — per `docs/compliance-rules.md`'s standing rule, no Indian rate, threshold or
commencement date is stated from memory anywhere in this file.

**Caveat:** This is desk research built entirely from public marketing pages, pricing pages, and
third-party review aggregators (several of which run pay-to-play or incentivized-review programs,
noted where relevant). It is **not** a hands-on trial of any product — no demo was booked, no
sandbox was used, and nothing here was verified by actually running a restaurant's data through
these systems. Vendor pricing pages for the Indian market are frequently absent (most quote
"contact sales"); where a dollar price appears it is often from a global/US-facing page or a
third-party estimate and may not reflect what an Indian restaurant is actually quoted. Review
counts on Capterra/G2 for the smaller players (Rista, PosBytz, Recaho, Restrofi) are thin (single
digits to low tens), so complaint patterns for those products are much less reliable than for
Petpooja, GoFrugal and Restroworks, which have hundreds of reviews.

**On the "missing major platform" question:** Zomato and Swiggy do **not** run their own
proprietary all-in-one restaurant management platform. Zomato operates a "POS developer platform"
/ "Restaurant Services Hub" through which third-party POS vendors (Petpooja, UrbanPiper, etc.)
integrate [blog] (https://inc42.com/buzz/zomatos-experimental-spree-continues-launches-developer-platform-for-pos-partners/),
and Swiggy's order flow reaches restaurants through partner POS systems such as Petpooja, inside
which Swiggy has built an embedded "Aggregator Centre" panel [marketing]
(https://blog.petpooja.com/poss/swiggy-now-inside-your-restaurant-order-management-system/). So
neither aggregator was added as a missing "platform" — they are channels the platforms below
integrate with (Feature Area I).

---

## 1. Petpooja

**Who it targets:** Independent restaurants, cafés and small-to-mid chains in India (and expansion
into Middle East, Canada, South Africa); positions itself as India's largest restaurant-tech
platform by restaurant count. Petpooja is also the low-level POS several aggregators (Swiggy) embed
into, i.e. it doubles as aggregator infrastructure, not just an end-customer product.

**Notable strengths:** Breadth of third-party integrations (150–200+ claimed), embedded Swiggy
"Aggregator Centre" panel inside the POS dashboard, and a large add-on family (Payroll, Purchase,
Invoice) sold as separate modules rather than one monolith.

**Pricing:** No public India price list [pricing gap — vendor does not publish India pricing].
Third-party estimates: Core plan ~$50/mo, Growth ~$95/mo, Scale ~$135/mo on a global pricing page
[pricing] (https://www.g2.com/products/petpooja-poss/pricing); Indian-market blog estimates put
plans at roughly ₹3,000–5,000/mo (basic), ₹5,000–8,000/mo (+inventory/CRM), ₹8,000–12,000/mo
(+multi-location/analytics) [blog] (https://www.dineopen.com/blog/petpooja-pricing-plans-2026.html) —
note this last source is a competitor's own blog, so treat the numbers as directional only. A
one-time onboarding/setup fee of roughly ₹5,000–15,000 is also commonly cited [blog]
(https://www.dineopen.com/blog/petpooja-pricing-plans-2026.html). No free trial is offered
[blog] (same source). Onboarding typically takes 1–3 days per restaurant, longer for multi-location
[blog] (same source; unverified against a primary source).

**Feature areas:**
- **A. Billing/GST** — Billing, KOT, discounts/coupons, split-by-table or merge-tables billing
  [marketing] (https://www.petpooja.com/poss). A separate product, "Petpooja Invoice," generates
  GST-compliant invoices with correct CGST/SGST/IGST split by HSN code, auto-creates e-invoices to
  the IRP when turnover crosses the e-invoicing threshold, covers e-way bills, and maintains a live
  GSTR-1 register [marketing] (https://blog.petpooja.com/finance-compliance/how-petpooja-invoice-work/).
  (Note: this file does not independently verify the ₹5 crore e-invoicing threshold cited in that
  blog post against the GST Council notification — Restaurant OS's own compliance file is the
  authority on that figure, not this vendor's marketing copy.)
- **B. Ordering & table service** — Captain Ordering app (digital menu replacing paper chits, KOT
  fired to the right station, edits logged with staff name/timestamp, works offline, AI-based
  upsell recommendations) [marketing] (https://blog.petpooja.com/industry-business-guides/petpooja-captain-ordering-reduces-order-errors/).
  QR "Scan & Order" for self-service dine-in tables, designed to run alongside captain ordering
  [marketing] (https://blog.petpooja.com/industry-business-guides/what-is-scan-and-order-qr-ordering-indian-restaurants/).
- **C. Kitchen** — KDS available as an add-on; KOT view in the online-order flow [marketing]
  (https://www.petpooja.com/poss).
- **D. Menu management** — Menu management software as a distinct module [marketing]
  (https://www.petpooja.com/poss/restaurant-menu-management-software).
- **F. Inventory** — Item-wise auto-deduction on sale, low-stock alerts, day-end inventory reports
  [marketing] (https://www.petpooja.com/poss); central-kitchen module to push semi-finished goods
  to outlets and track sales/inventory conversion per outlet [marketing]
  (https://blog.petpooja.com/poss/ultimate-guide-to-restaurant-inventory-management/); 20+
  inventory reports covering consumption, wastage and pilferage [marketing] (same source).
- **G. Procurement** — "Petpooja Purchase" module: scans/OCRs supplier invoices (including
  handwritten and multi-page PDFs), matches invoices to POs, and does live price comparison across
  connected suppliers (named examples: HyperPure, DMart, local vendors) with a "Best Match"
  auto-cheapest-vendor selector [marketing] (https://blog.petpooja.com/industry-business-guides/petpooja-purchase-manager-features-setup/).
- **H. Variance** — A "Consumption Report" explicitly compares theoretical vs. actual usage per
  the linked recipe card and quantifies the gap (their own worked example: 240 plates at 100g =
  24kg theoretical vs. 27kg actual = 3kg variance) [marketing]
  (https://blog.petpooja.com/glossary/consumption-report/).
- **I. Aggregators** — Direct Zomato/Swiggy integration; Swiggy's own partner portal is embedded
  via iframe inside the Petpooja dashboard ("Swiggy Aggregator Centre") letting restaurants run
  discounts, ads and complaint-handling without leaving the POS [marketing]
  (https://blog.petpooja.com/poss/swiggy-now-inside-your-restaurant-order-management-system/).
- **J. Payments & cash** — Maps each payment mode (cash/UPI/card) to a bank account; split
  payments (e.g. half cash, half UPI) land against one invoice automatically; a "Petpooja Finance"
  dashboard reconciles provider payouts against POS totals and flags transactions missing an
  invoice [marketing] (https://blog.petpooja.com/finance-compliance/card-vs-upi-why-restaurant-payment-reports-never-match/).
- **K. CRM/loyalty** — "Smart CRM," loyalty wallet/points programs [marketing]
  (https://www.petpooja.com/poss).
- **L. Staff** — A separate product, "Attendo" (formerly Petpooja Payroll): shift scheduling
  (including rotating/overnight shifts), fingerprint + geo-tagged mobile attendance, automatic
  late/early/overtime capture, payroll with PF/ESI statutory deduction automation, WhatsApp
  reporting [marketing] (https://blog.petpooja.com/people-payroll/petpooja-payroll-features/).
- **M. Reports/analytics** — 80+ business reports cited on the core POS page [marketing]
  (https://www.petpooja.com/poss); a separate blog claims 10+ inventory-specific reports
  [marketing] (https://blog.petpooja.com/glossary/inventory-management/) — the two figures are
  not reconciled across pages, so treat the exact count as approximate.
- **O. Multi-outlet** — Central-kitchen-to-outlet distribution model; one customer testimonial
  cites "100+ outlets" on the platform [marketing] (https://www.petpooja.com/poss).

**What users complain about:**
1. "Very bad. It's not worth to describe here comparing my 10 years of experience" — 1-star
   review citing poor customer service, staff not responding after advance payment was taken,
   and the company being "too busy with expansion to handle existing customer issues." — Shreyans
   S., restaurant owner [review] (https://www.capterra.com/p/172163/Petpooja-Restaurant-Management-Platform/reviews/).
2. "Order taking screen is not User friendly" — a co-founder review also citing time-consuming
   menu management, no live order tracking, and a poor "mark ready" flow. — Nazima S. [review]
   (same Capterra URL).
3. A reviewer rates Petpooja below UrbanPiper specifically on UI/UX simplicity — Dhanush T., GM
   [review] (same Capterra URL).
4. Even a 5-star reviewer flags the system going "a bit slow during peak hours, which can affect
   billing speed" and that "customer support response time needs improvement" — Ankit P. [review]
   (same Capterra URL).
5. On Google Play, users report "worst service from the customer-facing team" who "only call for
   subscriptions," and complaints that a recent app update removed the ability to see overall
   sales for previous days on the homepage [review]
   (https://play.google.com/store/apps/details?id=com.petpooja.billing&hl=en_IN).

---

## 2. Posist / Restroworks

**Who it targets:** Mid-size to large multi-outlet chains, cloud-kitchen operators and enterprise
F&B brands rather than single-location independents — the pricing and sales-led motion (no public
price list, "get an estimate") point at a heavier, more consultative sale than Petpooja/GoFrugal.
Rebranded from Posist to Restroworks on 10 April 2024 [blog]
(https://restauranttools.ai/tools/posist).

**Notable strengths:** Central-kitchen production/distribution coordination, machine-learning
demand forecasting tied to inventory, and multi-brand/multi-outlet menu control from one panel.

**Pricing:** Entirely quote-based. The vendor's own pricing page lists no numbers and instead
routes every visitor to "get an estimate" / "get a demo," explaining that cost depends on software
modules chosen (POS, Inventory, Kitchen Suite, Insights, CX Suite), restaurant size/terminal count,
and optional hardware [pricing] (https://www.restroworks.com/pricing/). **Unknown** — no
contact-sales price was disclosed anywhere found.

**Feature areas:**
- **E/F/H. Recipes, inventory, variance** — "Indent-based" purchasing where outlets raise stock
  requests centrally; stock transfer management between outlet and central kitchen; ML-based
  demand/stock forecasting; wastage control and "inventory variance tracking" cited by name
  [marketing] (https://www.restroworks.com/cloud-kitchen-software/).
- **F. Inventory (base kitchen model)** — Central kitchen coordinates production/stock
  distribution to multiple outlets, with stock tracked at both outlet and central-kitchen level
  [marketing] (https://www.restroworks.com/cloud-kitchen-software/).
- **M. Reports/forecasting** — Dedicated "Restaurant Forecasting Software" product using
  historical sales + seasonal trend data to forecast next-day consumption; 100+ report options
  described as customizable [marketing] (https://www.restroworks.com/restaurant-forecasting-software/).
- **O. Multi-outlet** — Multi-brand management from one panel with distinct tabs per brand;
  centralized menu control across regions/outlets with real-time sync [marketing]
  (https://www.restroworks.com/cloud-kitchen-software/).
- **Support model** — Offers in-person, live-online, webinar, documentation and video training,
  plus 24x7 support channels (email/phone/chat/knowledge base) [review-site aggregation, blog]
  (https://www.softwareworld.co/software/restroworks-reviews/). One user review characterizes
  onboarding as reaching "all necessary setup completed within 24 hours" while another says
  first-time admins need more guided setup time [blog, aggregating reviews]
  (https://zoftwarehub.com/products/restroworks-restaurant-pos/zoftware-analysis) — this is a
  secondary aggregation of reviews rather than a primary review page (the primary G2 reviews page
  returned HTTP 403 to automated fetch and could not be read directly).

**What users complain about:**
1. "Backend inventory monitoring is a bit tactful and requires lots of manual inputs which leads
   to errors" and the platform "is not beginner friendly" — paraphrased from a Capterra review
   [review] (https://www.capterra.com/p/142877/Restroworks/reviews/?page=15).
2. "Posist does not have all reports more than one month together" — a reporting-window
   limitation cited in a Capterra review [review] (same Capterra listing).
3. "Integration part needs to be upgraded" — cited as a recurring theme across reviews [review]
   (same Capterra listing).
4. "Syncing of inventory takes a little time as sometimes help from Posist is needed to rectify
   it" [review] (same Capterra listing).
5. Direct access to Restroworks' G2 reviews page was blocked (HTTP 403) during this research, so
   complaint coverage here relies on Capterra and a third-party aggregator rather than reading G2
   reviews first-hand — flagged as a research gap, not resolved by substituting other products'
   G2 pages.

---

## 3. GoFrugal (Restaurant POS / RPOS6 / ServQuick)

**Who it targets:** A long-established Indian retail-and-restaurant ERP vendor (also serves
pharmacy, apparel, distribution) — positions restaurant POS as one vertical of a broader ERP,
which shows up in its pricing (per-store/per-user tiers) and its cross-vertical support model.

**Notable strengths:** Direct GST e-filing integration, granular BOM-based recipe costing tied to
automatic inventory deduction, and long operating history giving it deep inventory/stock-control
tooling relative to newer entrants.

**Pricing:** Multiple inconsistent figures found across sources — a genuine "contact sales +
resold through partners" pricing model rather than one clean list. One estimate: $7/store/month
entry tier, with four packages (Cash Register, Starter, Standard, Professional) [blog]
(https://www.softwaresuggest.com/gofrugal-restaurant-pos). A different estimate: ~$49/mo basic,
~$99/mo standard, ~$299/mo premium [blog] (https://www.itqlick.com/gofrugal-pos/pricing) — the
same source warns "after implementation, add-ons, and annual hikes the real cost is often 3x
higher than the base pricing" [blog] (same source). A free trial is offered [blog] (same source).
Given the spread across sources, treat all these numbers as **unverified estimates**, not
GoFrugal's actual published price list (which was not found).

**Feature areas:**
- **A. Billing/GST** — "Automate GST calculations," invoices auto-calculate GST, and "Direct GST
  e-filing" producing reports formatted for tax-authority submission [marketing]
  (https://www.gofrugal.com/restaurant/features/).
- **C. Kitchen** — Merges KOTs where needed; automatically routes online orders to the correct
  kitchen station; production planning to reduce wait times [marketing] (same source).
- **D/E. Menu & recipe costing** — Bills of Materials (BOM) per menu item listing ingredients and
  quantities, with automatic inventory-level updates on BOM usage, and on-the-fly price
  adjustment as ingredient costs change [marketing] (same source).
- **F. Inventory** — Batch management with expiry-date tracking, daily stock audits, "stock
  discrepancy resolution" via a web dashboard, automated reordering [marketing] (same source).
- **G. Procurement** — Vendor database, PO generation with automated reorder notifications,
  "vendor performance analysis" tracking delivery times and pricing [marketing] (same source).
- **H. Variance/wastage** — Wastage tracking and analysis tied to the BOM/cost-analysis feature
  [marketing] (same source); "identify, track and analyze the sources of wastage" [blog]
  (search-engine summary of https://www.gofrugal.com/restaurant/features/restaurant-crm-software.html).
- **I. Aggregators** — Swiggy, Zomato, MagicPin, Dunzo support plus ONDC connectivity [marketing]
  (https://www.gofrugal.com/restaurant/features/) — notably, GoFrugal's own product videos show
  this Swiggy/Zomato integration is delivered *through UrbanPiper* as the connecting layer, not a
  direct GoFrugal-built integration [marketing/video]
  (https://www.owler.com/reports/gofrugal/gofrugal-posted-a-video-%22gofrugal-rpos6---swiggy-z/1532679867265) —
  i.e., UrbanPiper is infrastructure other POS vendors resell on top of, not only an end-customer
  product (relevant to why it was added as an "extra" below).
- **K. CRM/loyalty** — Personalized offers by customer history, points/birthday-coupon loyalty,
  time-based happy-hour promotions, SMS/WhatsApp campaigns, feedback-collection app [marketing]
  (https://www.gofrugal.com/restaurant/features/).
- **O. Multi-outlet** — Centralized control of menu/recipe masters across locations,
  inter-location stock transfers, single dashboard for all outlets [marketing] (same source).
- **Q. Onboarding** — GoFrugal states implementation in "just one day," with teams "fully
  operational" within three days of training, illustrated with a 22,000-SKU customer example
  [marketing] (https://www.gofrugal.com/support/assure-product-delivery.html) — a vendor claim,
  not independently verified.
- **Staff/HR (L)** — Not found on the features page fetched; GoFrugal's restaurant accounting
  page mentions payroll only in passing ("tracks... payroll") with no attendance/biometric detail
  surfaced [marketing] (https://www.gofrugal.com/restaurant/accounting-software/) — recorded as
  "not found" rather than assumed absent.

**What users complain about:**
1. "Customer service is very bad and all employees are cheater[s], once they take amount from
   customers after they are not responded" — 1-star review — Vijay T., proprietor [review]
   (https://www.capterra.com/p/71693/GoFrugal-POS-Software/reviews/).
2. "Very unhappy by their[e] selfies [sic] customer service while u buy the software... but later
   on if your bill print has some tiny problem... they will tell you please connect the hardware
   person that is not their job" — Sunil Singh R., founder [review] (same Capterra listing).
3. "Customer service and support is not getting on right time. None of our staff didn't get a[n]
   proper training" — Junaise A. [review] (same Capterra listing).
4. Training reportedly expires within 1–2 weeks or requires additional payment (cited as ~30% of
   software cost), and basic features like KOT printing reportedly carry additional charges —
   Gaurav G., restaurant owner, 2-star review [review] (same Capterra listing).
5. Multiple reports of the system running slow, including on high-spec hardware ("32GB RAM, 16GB
   graphics") and after periods of idling — Vijay J. and Ramesh R. [review] (same Capterra
   listing). Separately, a G2 reviewer says centralized-accounts functionality is lacking above
   10 outlets, with slow entry sync and slow report generation [review]
   (https://www.g2.com/sellers/gofrugal — summarized via search, not independently re-fetched).

---

## 4. Rista

**Who it targets:** Multi-outlet and multi-brand restaurant operators; owned by DotPe (acquired
24 September 2021 in an all-cash deal, continues operating as a standalone brand) [blog]
(https://inc42.com/buzz/retail-tech-startup-dotpe-acquires-rista-marks-foray-into-pos-space/).
This ownership link is relevant: Rista and DotPe likely share back-end payment/aggregator
infrastructure, though this was not independently confirmed beyond the acquisition report.

**Notable strengths:** Multi-brand invoicing from one system, tier-based configurable loyalty at
branch or business level, call-center-based reservations aimed at multi-outlet operators.

**Pricing:** **Unknown** — no public pricing found; multiple listing sites describe it as
custom-quoted with a trial available [blog] (https://www.capterra.com/p/10026711/Rista/).

**Feature areas:**
- **A. Billing** — Digital bills sent via WhatsApp; multi-brand invoices generated from a single
  system; partial-payment records for credit/running-tab orders [blog]
  (search-engine summary of Capterra/GetApp listings for Rista).
- **K. CRM/loyalty** — Customer segmentation; deals/discounts configurable at branch or business
  level; fully configurable tier-based loyalty [blog] (same source).
- **B. Ordering** — Queue management for walk-ins, real-time table-occupancy visibility,
  call-center-based reservations for multi-outlet businesses [blog] (same source).
- **O. Multi-outlet** — Explicit "multi-store management" to run several locations from one
  platform [blog] (same source).
- **I. Aggregators/payments** — Integrations named: Zomato, Swiggy, ONDC, RazorPay, PhonePe,
  Paytm, Tally, Magicpin [blog] (same source; not verified against Rista's own site).

**What users complain about:** Review volume is very thin. One Software Advice review is
described as broadly positive (fast billing, real-time inventory, "seamless" aggregator
integration) but notes the reviewer "look[s] forward to faster support response for critical
issues" as an explicit area for improvement [review]
(https://www.softwareadvice.com/product/525465-Rista/). No further independent negative reviews
were located — **recorded as a research gap**, not as evidence Rista has no complaints.

---

## 5. PosBytz

**Who it targets:** Cloud kitchens, cafés and multi-outlet F&B brands wanting a modular
pick-your-modules system (POS, online ordering, inventory, recipes, CRM, accounting, HR) rather
than one fixed bundle; also serves general retail, not restaurant-only.

**Notable strengths:** Explicit modular pricing/packaging, a 14-day full-feature free trial with
no credit card required, and native multi-platform clients (Windows, Android, iPad, web).

**Pricing:** Lite $39/month, Plus $69/month, Premium $199/month, plus a custom Enterprise tier
[pricing] (https://posbytz.com/en/pricing/). 14-day free trial, full feature access, no card
required [pricing] (same source). These are the vendor's own published numbers — the clearest
public pricing page found among the eight core products.

**Feature areas:**
- **B/I. Ordering** — Single-screen handling of dine-in, takeaway, delivery and online orders;
  branded online-ordering page plus aggregator integration [marketing]
  (https://posbytz.com/en/restaurant/restaurant-pos-software/).
- **F/E/K. Inventory, recipes, CRM** — Modules explicitly named: inventory, recipes, CRM,
  accounting, HR, sold à la carte [marketing] (https://posbytz.com/en/restaurant/).
- **M. Reports** — "Sales reports and analytics" as a core listed feature [marketing]
  (https://posbytz.com/en/pos/).

**What users complain about:** Review volume is very thin (Capterra shows a handful of reviews).
What was found: users describe the UI as "top-notch" and support as quick/responsive, with the
one negative note being "occasional glitches in the app" on SoftwareSuggest [review]
(https://www.softwaresuggest.com/posbytz/reviews). This is markedly less critical feedback than
Petpooja/GoFrugal, but the review count is too low (single digits) to treat this as representative
— **recorded as a research gap**, not as evidence PosBytz has fewer real problems.

---

## 6. DineOpen

**Who it targets:** Small independent restaurants in India price-sensitive enough to be steered by
"cheaper than Petpooja" positioning; also markets to US restaurants (comparison pages vs. Toast,
Square, Lightspeed), suggesting a broader/newer, less India-specific customer base than the other
seven.

**Notable strengths (self-reported):** An "AI voice assistant" answering calls/WhatsApp/web orders
in multiple Indian languages (Hindi, Tamil, Telugu, Marathi, Bengali, Kannada, Gujarati, English)
[marketing] (https://www.dineopen.com/for/restaurants) — the most AI-forward positioning of any
product in this set, though entirely vendor-claimed and not corroborated by any independent
review.

**Important caveat on this vendor specifically:** DineOpen's own blog is also the source for
several of the *other* products' pricing figures cited above (Petpooja pricing, "best POS"
comparison listicles) — i.e., DineOpen operates a comparison-content marketing funnel against its
own competitors. Every DineOpen-sourced claim about a *competitor* in this file is tagged [blog]
and should be weighted accordingly; claims about DineOpen itself below are [marketing]/[pricing]
from DineOpen's own site, which carries the same self-interest in the other direction.

**Pricing:** A flat $9.99/month global price with "no per-transaction cut" is advertised, alongside
an India-specific "Spark" plan from Rs 300/month claimed to include billing, KDS, QR ordering,
inventory, loyalty, AI voice ordering and analytics [pricing]
(https://www.dineopen.com/blog/petpooja-pricing-plans-2026.html — the pricing claim appears on
DineOpen's own comparison blog rather than a dedicated pricing page). 30-day free trial, no
contract, no installation fee claimed [marketing] (same source). Given Rs 300/month is far below
every other product surveyed (including much smaller/newer Restrofi at ₹499/month), this figure
should be treated with real skepticism pending a primary pricing page.

**Feature areas:**
- **K. AI/CRM** — AI voice ordering across the languages listed above; AI agent also "handles
  reservations and suggests add-ons automatically" [marketing] (https://www.dineopen.com/for/restaurants).
- **A/C/F. Billing, KDS, inventory** — Listed as included in the base Spark plan alongside QR
  ordering, loyalty and analytics [marketing] (https://www.dineopen.com/blog/petpooja-pricing-plans-2026.html).

**What users complain about:** No independent reviews (Play Store, G2, Capterra, Trustpilot) were
located for DineOpen during this research — its Capterra listing exists but returned no readable
review content, and general web search surfaced only DineOpen's own marketing/blog pages.
**Recorded as "not found."** Given how new and thinly independently reviewed this vendor appears
relative to the rest of the group, its self-reported "1000+ restaurants across 20+ countries"
scale claim [marketing] (https://www.dineopen.com/blog/petpooja-pricing-plans-2026.html) should be
treated as unverified marketing copy, not fact.

---

## 7. Recaho

**Who it targets:** Restaurants, cafés, cloud kitchens, food courts and multi-outlet chains; an
India-focused cloud restaurant-OS bundling billing, ordering, kitchen, inventory, CRM, accounting
and "AI-powered analytics."

**Notable strengths:** Free Kitchen-KOT app, Captain app and mobile POS app bundled at no extra
cost [marketing] (https://www.softwaresuggest.com/recaho).

**Pricing:** INR 12,000/year cited as a baseline, varying with customization, feature add-ons,
user count and deployment type; free trial available, no card required [blog]
(https://www.techjockey.com/detail/recaho-pos). This is a third-party estimate, not a figure taken
from Recaho's own pricing page (no such page was found).

**Feature areas:**
- **A/B/C. Billing, ordering, kitchen** — Online order placement, GST-aware billing, QR code
  platform, self-ordering, centralized menu management [marketing]
  (https://www.softwaresuggest.com/recaho).
- **F. Inventory** — "Top-notch inventory management" and "offline sync" cited as strengths in
  aggregated review summaries [review-aggregation] (https://www.softwaresuggest.com/recaho).
- **K. CRM/loyalty** — CRM and loyalty programs listed as core features [marketing] (same
  source).
- **M. Analytics** — "AI-powered analytics" claimed but not detailed beyond the label
  [marketing] (same source) — **treated as an unsubstantiated marketing claim**, no specifics
  found on what the "AI" does.

**What users complain about:** No specific, attributable negative review quotes were located
despite direct searching (Capterra, GetApp, SoftwareAdvice, G2, Techjockey, app-store listings all
returned only aggregate praise — "user-friendly," "fast/simple billing," "responsive year-round
support" — with no named reviewer or star-by-star breakdown surfaced) [blog/marketing-aggregation]
(https://www.softwaresuggest.com/recaho and https://www.techjockey.com/detail/recaho-pos).
**Recorded as "not found."** The claimed "7,500+ satisfied customers" figure [marketing]
(https://www.getapp.com/retail-consumer-services-software/a/recaho-pos/) is vendor-sourced and
unverified — it exceeds Petpooja-scale claims relative to Recaho's near-total absence from
independent review platforms, which is itself worth noting as a discrepancy.

---

## 8. Restrofi

**Who it targets:** Very small operators (1–5 outlets) in India wanting a zero-commission,
no-hardware, phone/tablet-only POS — explicitly pitched as a cheaper Petpooja alternative
[marketing] (https://restrofi.com/blog/restaurant-pos-alternatives-india). Live across 25 Indian
cities per the vendor [marketing] (https://restrofi.com/cities).

**Notable strengths:** A genuinely free tier (10 menu items, 1 location, basic QR ordering, no
card required) below even PosBytz's or Recaho's cheapest paid tier [pricing]
(https://www.restrofi.com/pricing), and a built-in "RestroAI" that reportedly answers plain-English
questions about sales data [marketing] (https://restrofi.com/).

**Pricing:** Free tier (10 items, 1 location); Starter ₹499/month (unlimited orders); Professional
₹1,499/month [pricing] (https://www.restrofi.com/pricing) — the clearest, most granular published
INR pricing of any product in this set, including a genuine no-cost tier.

**Feature areas:**
- **B. QR ordering** — Scan-to-order menus with real-time item-availability updates, no app
  required [marketing] (https://restrofi.com/).
- **C. Kitchen** — KDS routing orders live to stations, claimed to cut ticket times "up to 40%"
  [marketing] (same source) — vendor claim, no methodology disclosed for the 40% figure.
- **M. Analytics/AI** — "RestroAI" answering plain-English sales questions; sales analytics
  covering revenue trends, peak hours, top items, staff performance, payment breakdown
  [marketing] (same source).
- **A. GST billing** — Auto-generated GST-compliant bills, daily settlement reports [marketing]
  (same source).

**What users complain about:** No independent review-site presence (G2, Capterra, Trustpilot) was
found for Restrofi; a Google Play listing exists for its app but returned no readable review
content via search [marketing/gap] (https://play.google.com/store/apps/details?id=com.restrofi.app).
**Recorded as "not found."** As the newest and smallest of the eight core products by every
visible signal (city-list marketing page rather than a customer-count claim, no G2/Capterra
listing), complaint patterns simply could not be established — this is a genuine coverage gap,
not evidence of a clean track record.

---

## Extras: significant platforms not on the original list

**UrbanPiper** — included because it is the omnichannel-order-aggregation layer that *other*
platforms in this list (GoFrugal, confirmed above) resell on top of, in addition to being sold
directly to restaurants; it is infrastructure for the category, not just a competitor within it.
- Consolidates Swiggy/Zomato/Dunzo/UberEats into one dashboard; one-click menu updates across all
  aggregators; per-aggregator differential pricing on the same store/branch; "order replay" and
  proactive stock sync to avoid missed orders and cancellations; centralized reconciliation
  reporting against aggregators [marketing] (https://www.urbanpiper.com/hub).
- Complaint: "long delays in support response... impacts business due to unresolved issues and
  slow resolutions" [review] (G2, summarized via search: https://www.g2.com/products/urbanpiper/reviews?qs=pros-and-cons).
  Also flagged as weaker on analytics/reporting depth relative to competitors [blog]
  (search-engine summary, source not independently re-fetched).
- Pricing: **unknown** — custom, not publicly listed [blog] (https://www.saasworthy.com/product/urbanpiper/pricing).

**LimeTray** — included as one of the longest-standing Indian all-in-one restaurant tech vendors
(POS + online ordering + CRM + loyalty), pre-dating several products on the required list, and
frequently named in India-specific "best restaurant POS" comparisons.
- Fast billing, inventory tracking, real-time reporting; CRM/loyalty; employee and multi-outlet
  management [marketing] (https://limetray.com/blog/ere4u-restaurant-pos-features-pricing/).
- Pricing: Essentials $49/mo/outlet, Turbo $149/mo/outlet, Supercharger $199/mo/outlet, free trial
  [pricing] (https://www.getapp.com/retail-consumer-services-software/a/limetray-online-food-ordering-system/)
  — note this reads as a global/US-facing price list, not confirmed as LimeTray's Indian pricing.
- Complaints: "Customer support sometimes takes quite a long time to solve a ticket... a bit of a
  slow back end"; "lag sometimes occurs from the servers' end, which can be quite irritating"
  [review] (https://www.capterra.com/p/180145/Online-Ordering-for-Restaurants-Ace/reviews/) — the
  same search flagged that most available LimeTray reviews date from 2018–2020 and several were
  vendor-referred/incentivized, which materially weakens confidence in this feedback as current.

**DotPe** — included as the best-funded ($27.5M Series A from PayU, Info Edge Ventures, Google)
[blog] (https://www.prnewswire.com/in/news-releases/offline-to-online-merchant-platform-dotpe-secures-27-5-million-series-a-funding-from-payu-info-edge-ventures-and-google-835406994.html)
explicit "escape Zomato/Swiggy commission" play in the market, and because it now owns a POS
product (Rista, acquired 2021) rather than being purely a direct-ordering tool.
- QR catalogue discovery, dine-in/takeaway digital ordering, in-store ePOS, instant invoicing,
  personalized payment reminders via SMS/WhatsApp, Google Search/Shopping/Maps product listing
  integration [marketing] (search-engine summary of dotpe.in/services.html).
- Commission-per-order pricing model (contrasts with several competitors' flat-fee SaaS pricing)
  [blog] (https://billfeeds.com/blog/dotpe-vs-billfeeds.html) — **unknown** exact commission rate;
  not disclosed publicly.
- Complaint: reviewers note "limited marketing efforts from the company" as a gap alongside
  otherwise positive feedback on QR/payments/delivery/billing/inventory integration [blog]
  (search-engine summary; primary G2 DotPe reviews page not independently re-fetched with quotes).

*(A fourth extra was considered — Torqus, now owned by Dineout/Times Internet, combined base of
~10,000 restaurants across the Dineout/Torqus/inResto group [blog]
(https://www.bwdisrupt.com/article/dineout-acquires-torqus-a-restaurant-focussed-cloud-based-point-of-sale-pos-system-164597)
— but no material beyond company-history/M&A coverage was found, and it did not clear the bar of
"genuinely significant" relative to UrbanPiper/LimeTray/DotPe within this research pass, so it was
left out rather than included on thin evidence.)*

---

## Merged feature table

| Area | Feature | Products that have it | Evidence tags | Source URLs |
|---|---|---|---|---|
| A | GST-compliant billing (CGST/SGST/IGST by HSN) | Petpooja, GoFrugal, Restrofi, TMBill* | marketing | petpooja.com/poss; blog.petpooja.com/finance-compliance/how-petpooja-invoice-work; gofrugal.com/restaurant/features |
| A | Automated GST e-invoice generation to IRP | Petpooja | marketing | blog.petpooja.com/finance-compliance/how-petpooja-invoice-work |
| A | Direct GST e-filing / GSTR reports | GoFrugal, Petpooja (GSTR-1 register) | marketing | gofrugal.com/restaurant/features; blog.petpooja.com/finance-compliance/how-petpooja-invoice-work |
| A | Split-bill / merge-table billing | Petpooja | marketing | petpooja.com/poss |
| A | Payment-mode-to-bank-account mapping w/ auto reconciliation | Petpooja | marketing | blog.petpooja.com/finance-compliance/card-vs-upi-why-restaurant-payment-reports-never-match |
| B | Captain/waiter ordering app (offline-capable) | Petpooja, Recaho (free) | marketing | blog.petpooja.com/industry-business-guides/petpooja-captain-ordering-reduces-order-errors; softwaresuggest.com/recaho |
| B | QR / scan-to-order dine-in | Petpooja, Rista, PosBytz, DineOpen, Recaho, Restrofi | marketing | (per-product sections above) |
| B | Call-center-based multi-outlet reservations | Rista | blog | capterra.com/p/10026711/Rista |
| C | Kitchen Display System (KDS) | Petpooja (add-on), GoFrugal, Restrofi, DineOpen | marketing | (per-product sections above) |
| C | Automatic KOT routing to kitchen station | GoFrugal, Petpooja (captain app) | marketing | gofrugal.com/restaurant/features; blog.petpooja.com |
| D | Central/multi-outlet menu control with real-time sync | Restroworks, GoFrugal, Petpooja | marketing | restroworks.com/cloud-kitchen-software; gofrugal.com/restaurant/features |
| E | Recipe/BOM-based costing tied to auto inventory deduction | GoFrugal, Petpooja | marketing | gofrugal.com/restaurant/features; blog.petpooja.com/glossary/inventory-management |
| F | Item-wise auto stock deduction on sale | Petpooja, GoFrugal | marketing | petpooja.com/poss; gofrugal.com/restaurant/features |
| F | Batch/expiry-date tracked inventory | GoFrugal | marketing | gofrugal.com/restaurant/features |
| F | Central-kitchen-to-outlet stock distribution & tracking | Restroworks, Petpooja | marketing | restroworks.com/cloud-kitchen-software; blog.petpooja.com/poss/ultimate-guide-to-restaurant-inventory-management |
| F | Offline inventory sync | Recaho | review-aggregation | softwaresuggest.com/recaho |
| G | OCR/AI invoice scanning from supplier bills | Petpooja (Purchase) | marketing | blog.petpooja.com/industry-business-guides/petpooja-purchase-manager-features-setup |
| G | Cross-supplier live price comparison / cheapest-vendor auto-select | Petpooja (Purchase) | marketing | blog.petpooja.com/industry-business-guides/petpooja-purchase-manager-features-setup |
| G | Vendor performance analysis (delivery time, pricing) | GoFrugal | marketing | gofrugal.com/restaurant/features |
| H | Explicit theoretical-vs-actual consumption/variance report | Petpooja, Restroworks (ML-forecast tied variance) | marketing | blog.petpooja.com/glossary/consumption-report; restroworks.com/cloud-kitchen-software |
| H | Wastage tracking & analysis | GoFrugal, Petpooja | marketing | gofrugal.com/restaurant/features; blog.petpooja.com |
| I | Embedded aggregator control panel inside POS (not just order feed) | Petpooja (Swiggy Aggregator Centre) | marketing | blog.petpooja.com/poss/swiggy-now-inside-your-restaurant-order-management-system |
| I | Aggregator hub reselling to other POS vendors | UrbanPiper (used by GoFrugal) | marketing | urbanpiper.com/hub; owler.com (GoFrugal RPOS6 Swiggy/Zomato via UrbanPiper video) |
| I | ONDC connectivity | GoFrugal, Rista | marketing/blog | gofrugal.com/restaurant/features; capterra.com/p/10026711/Rista |
| I | Direct-ordering-website / escape-aggregator-commission play | DotPe, DineOpen | marketing/blog | dotpe.in/services; dineopen.com |
| J | UPI/card/cash payment-mode-level reconciliation dashboard | Petpooja (Finance) | marketing | blog.petpooja.com/finance-compliance/card-vs-upi-why-restaurant-payment-reports-never-match |
| J | Commission-per-order pricing model (vs SaaS flat fee) | DotPe | blog | billfeeds.com/blog/dotpe-vs-billfeeds |
| K | Tier-based configurable loyalty | Rista | blog | capterra.com/p/10026711/Rista |
| K | WhatsApp/SMS marketing campaigns | GoFrugal, Rista (WhatsApp digital bills) | marketing/blog | gofrugal.com/restaurant/features; capterra.com/p/10026711/Rista |
| L | Biometric + geo-tagged staff attendance | Petpooja (Attendo) | marketing | blog.petpooja.com/people-payroll/petpooja-payroll-features |
| L | Statutory payroll compliance (PF/ESI) automation | Petpooja (Attendo) | marketing | blog.petpooja.com/people-payroll/petpooja-payroll-features |
| M | AI-driven demand forecasting for inventory | Restroworks | marketing | restroworks.com/restaurant-forecasting-software |
| M | Natural-language / conversational analytics ("ask your data") | Restrofi (RestroAI) | marketing | restrofi.com |
| M | AI voice ordering (multi-Indian-language phone/WhatsApp agent) | DineOpen | marketing | dineopen.com/for/restaurants |
| O | Multi-brand management in one panel | Restroworks, Rista | marketing/blog | restroworks.com/cloud-kitchen-software; capterra.com/p/10026711/Rista |
| Q | Genuine free tier (no card required) | Restrofi | pricing | restrofi.com/pricing |
| R | Fully modular à-la-carte pricing (pick only needed modules) | PosBytz | marketing/pricing | posbytz.com/en/pricing |

*TMBill is mentioned only as a candidate "missing platform" check (see Extras discussion) and was
not researched to the same depth as the 11 products above; its GST/inventory/recipe/wastage claims
[marketing] (https://www.tmbill.com/products) are recorded in this table for completeness but were
not corroborated by a second source and TMBill itself was not written up as a full product
section — treat these as the least-verified entries in this table.

---

## Unusual or distinctive features (only one or two products do this)

- **Embedded aggregator control panel inside the POS itself** (not just an order feed) — Swiggy's
  full partner portal loaded via iframe inside Petpooja's dashboard, letting a restaurant run
  Swiggy ads/discounts/complaint-handling without a separate login [marketing]
  (https://blog.petpooja.com/poss/swiggy-now-inside-your-restaurant-order-management-system/).
  Only Petpooja was found doing this.
- **Cross-supplier live price comparison with an auto-cheapest-vendor cart** at the point of
  purchase — Petpooja Purchase comparing the same item's live price across HyperPure, DMart and
  local vendors and assembling the lowest-cost combination [marketing]
  (https://blog.petpooja.com/industry-business-guides/petpooja-purchase-manager-features-setup/).
  No other product in this set was found doing this.
- **AI voice ordering answering phone calls in regional Indian languages** — DineOpen's claimed
  differentiator, unmatched by any other product surveyed [marketing]
  (https://www.dineopen.com/for/restaurants) — flagged again here as vendor-claimed and
  independently unverified.
- **A genuinely free, no-card permanent tier** — Restrofi's free plan (10 items, 1 location) is
  the only true $0 tier found across all 11 products; everyone else's "free trial" is time-boxed
  [pricing] (https://www.restrofi.com/pricing).
- **POS-as-infrastructure resold by other POS vendors** — UrbanPiper is not just sold to
  restaurants directly; a competing all-in-one platform (GoFrugal) integrates Swiggy/Zomato
  *through* UrbanPiper rather than building its own aggregator connectors [marketing/video]
  (https://www.owler.com/reports/gofrugal/gofrugal-posted-a-video-%22gofrugal-rpos6---swiggy-z/1532679867265).
  This is a meaningfully different competitive position from every other product in this set.
- **Full modular unbundling with transparent per-module pricing** — PosBytz is the only one of
  the eight required products with a clean, vendor-published (not third-party-estimated) tiered
  price list [pricing] (https://posbytz.com/en/pricing/).

---

## Sources

Petpooja: https://www.petpooja.com/poss · https://blog.petpooja.com/finance-compliance/how-petpooja-invoice-work/ ·
https://blog.petpooja.com/finance-compliance/petpooja-invoice-features/ ·
https://blog.petpooja.com/industry-business-guides/petpooja-captain-ordering-reduces-order-errors/ ·
https://blog.petpooja.com/industry-business-guides/what-is-scan-and-order-qr-ordering-indian-restaurants/ ·
https://blog.petpooja.com/poss/ultimate-guide-to-restaurant-inventory-management/ ·
https://blog.petpooja.com/industry-business-guides/petpooja-purchase-manager-features-setup/ ·
https://blog.petpooja.com/glossary/consumption-report/ ·
https://blog.petpooja.com/poss/swiggy-now-inside-your-restaurant-order-management-system/ ·
https://blog.petpooja.com/finance-compliance/card-vs-upi-why-restaurant-payment-reports-never-match/ ·
https://blog.petpooja.com/people-payroll/petpooja-payroll-features/ ·
https://www.g2.com/products/petpooja-poss/pricing ·
https://www.dineopen.com/blog/petpooja-pricing-plans-2026.html ·
https://www.capterra.com/p/172163/Petpooja-Restaurant-Management-Platform/reviews/ ·
https://play.google.com/store/apps/details?id=com.petpooja.billing&hl=en_IN

Posist/Restroworks: https://www.restroworks.com/pricing/ · https://www.restroworks.com/cloud-kitchen-software/ ·
https://www.restroworks.com/restaurant-forecasting-software/ ·
https://www.capterra.com/p/142877/Restroworks/reviews/?page=15 ·
https://zoftwarehub.com/products/restroworks-restaurant-pos/zoftware-analysis ·
https://restauranttools.ai/tools/posist (rebrand date)

GoFrugal: https://www.gofrugal.com/restaurant/features/ · https://www.gofrugal.com/support/assure-product-delivery.html ·
https://www.gofrugal.com/restaurant/accounting-software/ ·
https://www.owler.com/reports/gofrugal/gofrugal-posted-a-video-%22gofrugal-rpos6---swiggy-z/1532679867265 ·
https://www.capterra.com/p/71693/GoFrugal-POS-Software/reviews/ ·
https://www.g2.com/sellers/gofrugal · https://www.itqlick.com/gofrugal-pos/pricing ·
https://www.softwaresuggest.com/gofrugal-restaurant-pos

Rista: https://www.capterra.com/p/10026711/Rista/ · https://www.softwareadvice.com/product/525465-Rista/ ·
https://inc42.com/buzz/retail-tech-startup-dotpe-acquires-rista-marks-foray-into-pos-space/

PosBytz: https://posbytz.com/en/pricing/ · https://posbytz.com/en/restaurant/restaurant-pos-software/ ·
https://posbytz.com/en/restaurant/ · https://www.softwaresuggest.com/posbytz/reviews

DineOpen: https://www.dineopen.com/for/restaurants · https://www.dineopen.com/blog/petpooja-pricing-plans-2026.html

Recaho: https://www.softwaresuggest.com/recaho · https://www.techjockey.com/detail/recaho-pos ·
https://www.getapp.com/retail-consumer-services-software/a/recaho-pos/

Restrofi: https://www.restrofi.com/pricing · https://restrofi.com/ · https://restrofi.com/cities ·
https://restrofi.com/blog/restaurant-pos-alternatives-india ·
https://play.google.com/store/apps/details?id=com.restrofi.app

UrbanPiper: https://www.urbanpiper.com/hub · https://www.g2.com/products/urbanpiper/reviews?qs=pros-and-cons ·
https://www.saasworthy.com/product/urbanpiper/pricing

LimeTray: https://limetray.com/blog/ere4u-restaurant-pos-features-pricing/ ·
https://www.getapp.com/retail-consumer-services-software/a/limetray-online-food-ordering-system/ ·
https://www.capterra.com/p/180145/Online-Ordering-for-Restaurants-Ace/reviews/

DotPe: https://www.prnewswire.com/in/news-releases/offline-to-online-merchant-platform-dotpe-secures-27-5-million-series-a-funding-from-payu-info-edge-ventures-and-google-835406994.html ·
https://billfeeds.com/blog/dotpe-vs-billfeeds.html · https://www.dotpe.in/services.html

Torqus (considered, not included): https://www.bwdisrupt.com/article/dineout-acquires-torqus-a-restaurant-focussed-cloud-based-point-of-sale-pos-system-164597

Zomato/Swiggy own-tools check: https://inc42.com/buzz/zomatos-experimental-spree-continues-launches-developer-platform-for-pos-partners/ ·
https://blog.petpooja.com/poss/swiggy-now-inside-your-restaurant-order-management-system/

TMBill (candidate, lightly researched): https://www.tmbill.com/products
