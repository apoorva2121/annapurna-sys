# Competitor Research — Step 2: Google Play Restaurant Apps for India (cheap, quick-start apps)

**Scope:** Low-cost / quick-start restaurant billing-POS apps distributed primarily through the
Google Play Store, aimed at single-outlet Indian restaurants, cafés and small food businesses —
Vyapar "Table," Arow, Zobaze "Restaurant & Café Billing POS" (Restokeep), Namma Restaurant
(Nammabilling), Shopto (frihbi.app), and SOLO Restaurant App — plus four additional significant
Play Store players found during this pass: myBillBook, GoRestro, BillSarthi, and BoltBills.

**Date checked:** 2026-09-13.

**Method:** WebSearch + WebFetch. **Google Play Store listing pages themselves could not be read
directly** — every `WebFetch` attempt against a `play.google.com/store/apps/details...` URL in
this session returned either an `ECONNREFUSED` (for the AppBrain mirror domain, which appears
network-blocked from this environment) or a response truncated before any usable content ("content
truncated due to length" — Play Store's client-rendered pages front-load JS bundle text ahead of
the actual listing text, and the fetcher's length cap cuts it off first). **What worked instead:**
(1) WebSearch queries against Play Store URLs, which returned Google's own indexed
install/rating/date snippets for several apps (Zobaze, myBillBook, Vyapar Table) with real numbers;
(2) **Techjockey.com** review pages, which rendered full named reviewer quotes with star ratings
and dates (worked for "NammaBilling" — see caveat in that app's section — and gave a pricing anchor
for SOLO); (3) **Capterra** review pages via WebFetch, which worked for Vyapar's parent product;
(4) **SelectHub** and **SoftwareAdvice** review-aggregation pages, which worked for Zobaze; (5)
**Indus Appstore** (a rival Indian app store) listing pages, which worked for Shopto/frihbi but
returned an internally inconsistent rating (see that app's section). AppBrain and APKPure/apkcombo
— the two mirrors the brief specifically suggested — were **not accessible**: every direct fetch to
`appbrain.com` returned `ECONNREFUSED`, and `apkcombo.com`/`apkpure.net` fetches failed the same
way; all AppBrain-sourced numbers below are therefore taken from Google's search-snippet cache of
AppBrain pages (via WebSearch), not from a direct read of AppBrain, and are marked accordingly.
Vendor marketing sites (arow.pro/arowapp.com, gorestro.com, billsarthi.com, mybillbook.in,
solobilling.com, nammaworld.org) were fetched directly and worked normally.

**Caveat:** This is desk research from public sources only — no app was installed, no restaurant
data was entered, and no purchase was made. Several apps in this tier have **very thin or zero**
independent review coverage (SOLO: 3 verified ratings on one aggregator; Arow: one vendor
testimonial and nothing else; Shopto: "no reviews yet" on the one store that could be read). Where
that is the case, this file says so explicitly rather than padding with inferred sentiment. Per
`docs/compliance-rules.md`'s standing rule, no Indian rate, threshold or commencement date is
stated from memory anywhere in this file — GST/price figures below are all sourced and dated, or
marked "not found."

**A note on this market segment specifically:** at least one of the six required apps — Namma
Restaurant — turned out on inspection to be a **white-labeled deployment of a third-party SaaS
template** (Acnoo's "Restaurant App SaaS," sold on CodeCanyon) rather than a purpose-built product
from a dedicated restaurant-tech company. This is a structural feature of the cheap end of this
market worth carrying into Restaurant OS's competitive framing: a meaningful slice of "restaurant
apps" on Play Store are templated white-labels resold by small local resellers, not independently
engineered products — see "Unusual or distinctive features" below.

---

## 1. Table – Restaurant Billing App (Vyapar)

| | |
|---|---|
| Package | `in.android.restaurant_billing` |
| Developer | Vyapar (Simply Vyapar Apps Pvt Ltd) [listing] |
| Installs | ~200,000 downloads total, ~560/day over the trailing 30 days, per a Google-cached AppBrain snapshot [listing-via-search-cache] (https://www.appbrain.com/app/table-restaurant-billing-app/in.android.restaurant_billing, read via WebSearch snippet, direct fetch blocked) |
| Rating / review count | **Not found** — no source in this session surfaced a star rating or review count specific to this package |
| Last updated | Version 3.5.1, dated 14 May 2026 [listing-via-search-cache] (same AppBrain URL) |
| Price | Free to download; no in-app price found specific to the Table app. Vyapar's parent product (the general Vyapar GST billing app) is a separate paid/freemium product — **not verified whether Table shares that billing plan or is priced independently** [gap] |
| Web/desktop companion | Yes — a dedicated marketing site (https://vyapartable.com/, returned HTTP 403 to WebFetch in this session) and Vyapar's broader desktop app exist alongside the mobile app [marketing] (https://vyaparapp.in/pos-software/restaurant) |

**Strengths:** Backed by Vyapar, an established Indian GST-billing company with a much larger
install base on its flagship product than any single-purpose restaurant app in this file (see
myBillBook comparison below — Vyapar is myBillBook's most direct competitor in the "GST billing
app that also does restaurants" category) [marketing] (https://vyaparapp.in/pos-software/restaurant).

**Feature areas found:**
- **A.** GST-compliant billing, multiple tax rates, multi-payment mode (cash/card/UPI/wallet/QR),
  thermal invoice printing, WhatsApp/email invoice sharing [marketing] (https://vyaparapp.in/pos-software/restaurant).
- **B.** Table order-taking with kitchen transmission, dine-in/takeaway/delivery order types, order
  modification/cancellation [marketing] (same source).
- **D/E.** Online menu creation with visuals/descriptions, real-time menu updates, and — notably for
  this price tier — **"recipe standardization and cost tracking"** explicitly claimed on the
  feature page [marketing] (same source); not corroborated by any screenshot or review, so treated
  as a marketing claim only.
- **F.** Real-time stock tracking, ingredient usage monitoring, wastage identification [marketing]
  (same source).
- **M.** Sales trend analysis, item-wise P&L, customizable reports [marketing] (same source).
- **P.** Offline functionality with auto-sync, multi-device (mobile/tablet/PC) [marketing] (same
  source).
- Not found on the feature page: KOT/KDS terminology specifically (the page says "kitchen order
  transmission" without naming a KOT/KDS product), procurement/PO workflow, loyalty programs.

**What users complain about:** No reviews specific to the Table app were found. The following are
from Capterra reviews of Vyapar's flagship product (same company, different SKU) and are recorded
here **only as a signal about the vendor**, not as Table-specific evidence:
1. "NEVER BUY VYAPAR if you require serious accounting... support system is a nightmare!" — S P T,
   Techno Commercial Head, 1-star [review] (https://www.capterra.com/p/180579/Vyapar/reviews/).
2. "Data disappeared and the calculations did not match" during a yearly review — Ibrahim S.,
   1-star [review] (same URL).
3. "Once package renewed, they don't attend any issues... poor attention on service" — Hasif M.,
   1-star [review] (same URL).
4. A 3-star reviewer: "Customer service become too poor and they have data glitches" — Muhammed M.
   [review] (same URL).
General web search also surfaced (unattributed to a named reviewer) complaints of the app
"hang[ing] frequently" and "slow loading... after updates" for the Vyapar family generally [blog,
aggregated] (search-engine summary, no single primary source URL retrievable).

**What users praise:** From the same Vyapar-parent reviews: "Easy business management with
billing, GST, inventory all in one dashboard" — Arif A., 5-star [review] (same Capterra URL); "App
cut my accounting time by half... Billing and GST reminders are easy" — Simranjeet K., 5-star
[review] (same URL).

---

## 2. Arow Restaurant Billing App

| | |
|---|---|
| Package | `com.arowapp.arowapp` |
| Developer | Arow Labs [listing] (https://play.google.com/store/apps/dev?id=6541308544455972723) |
| Installs | 5,000+ [listing-via-search-cache] |
| Rating / review count | **Not found** |
| Last updated | **Not found** |
| Price | **Not found** — no dedicated pricing page located on either of the vendor's two marketing domains |
| Web/desktop companion | Ambiguous/degraded: **arow.pro now 301-redirects to a domain-parking/expired-domain listing page** (`expireddomains.com`) as observed in this session on 2026-09-13 [direct observation via WebFetch] — i.e. one of the vendor's two public marketing domains has lapsed. The second domain, arowapp.com, is live and hosts feature marketing [marketing] (https://www.arowapp.com/) |

**Strengths:** Broad Indian-language support claimed — English, Hindi, Telugu, Tamil, Kannada,
Malayalam, Marathi, Gujarati, Odia, Bengali, Punjabi — wider than any other app in this file
[marketing] (https://www.arow.pro/ description, indexed via WebSearch before the domain lapsed).
AI-assisted menu upload is also claimed [marketing] (https://www.arowapp.com/).

**Feature areas found:**
- **A.** "Print bills in 3 secs" positioning; no GST-specific claim found on either domain
  [marketing] (https://www.arowapp.com/).
- **B/C.** A waiter app for tableside order-taking, described as feeding a kitchen display; QR
  ordering pitched explicitly as a way to cut aggregator commission exposure [marketing] (same
  source).
- **F.** "Keep track of ingredient stocks, wastage, and inventory value" [marketing] (same source).
- **L.** "Monitor and manage your team from a single dashboard" [marketing] (same source) — no
  attendance/shift/payroll specificity found.
- **M.** Daily sales, expense details, net profit charts [marketing] (same source).
- **K.** Anonymous customer feedback via QR code [marketing] (same source) — a lightweight feedback
  loop not seen named elsewhere in this file's app set.
- Not found: GST/tax specifics, recipe costing, procurement, aggregator direct-integration detail,
  pricing.

**What users complain about:** No independent reviews were located for this app on any platform
searched (Play Store review content unreadable, no G2/Capterra/SoftwareSuggest listing found).
**Recorded as "not found,"** not as evidence of a clean record.

**What users praise:** Only one piece of feedback exists in public search results, and it is a
vendor-published testimonial, not an independent review: "Arow transformed my restaurant
operations, making billing and inventory management incredibly efficient and fast!" [marketing]
(https://www.arow.pro/, indexed copy).

---

## 3. Restaurant & Café Billing POS (Zobaze / "Restokeep")

| | |
|---|---|
| Package | `com.zobaze.restaurant.pos` |
| Developer | Zobaze Technologies Pvt Ltd, Telangana [review-aggregation] (https://www.softwaresuggest.com/zobaze-pos) |
| Installs | ~2,100/month recent pace; available on Play Store since January 2022 [listing-via-search-cache, AppBrain snapshot indexed by WebSearch] |
| Rating / review count | **4.65 / 5 on 830 ratings**, per the AppBrain snapshot specific to this package [listing-via-search-cache]. Note: a *different*, higher figure ("4.6 stars, 1.21K–28,000+ reviews, 100K–1M+ installs") surfaced in general search results but appears to describe Zobaze's **general-purpose POS app** (`com.zobaze.pos`), a sibling product, not this restaurant-specific package — the two are kept separate here to avoid conflating them |
| Last updated | 27 May 2025 [listing-via-search-cache] |
| Price | Free to download; **transitioned from a fully free model to paid access for some reports/features** — confirmed by multiple independent reviewers below, exact price not found |
| Web/desktop companion | Yes — "Z-Office" web back office [marketing] (https://zobaze.com/blog/restaurant-pos-billing-software) |

**Strengths:** The only app in this required group with a real (if modest) independent review base
(830 ratings) and a corroborated 4.6-star average across three separate sources (AppBrain,
SelectHub, SoftwareAdvice) — meaningfully more reviewed than Arow, Shopto, SOLO or Namma Restaurant.

**Feature areas found:**
- **A.** Table billing with receipt delivery via WhatsApp, Gmail, SMS [marketing] (https://zobaze.com/blog/restaurant-pos-billing-software).
- **C.** A named Kitchen Display System product exists as a separate Play Store app in the family
  (`com.zobaze.kds`) alongside in-app KDS-style order routing [marketing] (same source).
- **F.** Stock tracking with low-inventory alerts, daily stock in/out per outlet, item-level sales
  by time/date [marketing] (same source).
- **K.** Customer profile database, transaction history, due/balance tracking [marketing] (same
  source).
- **L.** Employee shift tracking tied to transactions; customizable roles (manager/partner/
  helper/custom); performance stats by average check and period [marketing] (same source).
- **M.** Real-time and historical sales reporting [marketing] (same source).
- **H (bug, not feature).** Independent reviewers confirm **tax is calculated on the pre-discount
  price rather than post-discount** — a compliance-relevant defect, not a marketing gap — repeated
  across two separate reviewers three years apart [review] (https://www.softwareadvice.com/retail/zobaze-pos-profile/reviews/).
- Not found: GST-specific compliance language, recipe/BOM costing, procurement, aggregator
  integration, formal onboarding process.

**What users complain about:**
1. "Transitioned from a free app to a paid model, requiring users to pay for certain reports and
   features" — a recurring theme across long-term users [review-aggregation] (https://www.selecthub.com/p/retail-pos-systems/zobaze-pos/).
2. Tax calculated on pre-discount price rather than post-discount — Sheng A. (2019) and repeated as
   an open issue by Eranga M. (2020/2022) [review] (https://www.softwareadvice.com/retail/zobaze-pos-profile/reviews/).
3. "UI needs improvement despite strong overall performance" — Jeevan D., 2020 [review] (same
   source).

**What users praise:**
1. "The placing order was very nice and clear and the new updated UI was stunning" — Eranga M.,
   5-star, April 2022 [review] (same source).
2. "It's a very powerful app for something that is free. It's super customizable and easy to use"
   — Sheng A., 5-star, October 2019 [review] (same source).
3. Offline functionality reliability during internet outages is repeatedly cited as a pro
   [review-aggregation] (https://www.selecthub.com/p/retail-pos-systems/zobaze-pos/).

---

## 4. Namma Restaurant (Nammabilling)

| | |
|---|---|
| Package | `com.acnoo.restaurant_app` |
| Developer/publisher | **Unclear on Play Store record itself** (unreadable), but the underlying software is Acnoo's "Restaurant App SaaS" template — a Flutter mobile app + Laravel admin panel product sold on CodeCanyon for resale/white-labeling [marketplace] (https://codecanyon.net/item/restaurant-app-saas-food-ordering-table-booking-app-with-laravel-admin-panel/58370658). A branded storefront for this exact product exists at nammaworld.org [marketing] (https://nammaworld.org/) |
| Installs / rating | **Not found** on any source reachable this session |
| Last updated | August 2026, per a Google-indexed Play Store snippet [listing-via-search-cache] |
| Price | (Per the nammaworld.org branded deployment specifically, which may or may not exactly match this Play Store listing's pricing) Free 7-day trial; Standard ₹7,999/year; Premium ₹9,999/year [pricing] (https://nammaworld.org/, checked 2026-09-13) |
| Web/desktop companion | Yes, by template architecture — Laravel web admin panel [marketplace] (same CodeCanyon URL) |

**Important naming-collision caveat:** this app must not be confused with two *unrelated* products
that share the "Namma" brand fragment: **"Namma Bill – GST Billing"** (`com.coderstudio.nammabilling`,
by Coderstudio) and **"Namma Billing GST Invoice App"** (`com.nammabilling.ip.namma_billing`, the
product at nammabilling.com). All three are distinct businesses. This file's group specifically
named `com.acnoo.restaurant_app` ("Namma Restaurant"), and only facts traceable to that package or
its Acnoo/nammaworld.org origin are reported in this section — review quotes for the *other* two
"Namma" products were deliberately excluded here to avoid misattribution (see "Unusual/distinctive
features" for why this collision itself is worth noting).

**Feature areas found (from the Acnoo template's own marketing, which nammaworld.org resells):**
- **A.** Custom invoice branding, VAT/tax tracking, multi-currency support [marketing]
  (https://nammaworld.org/).
- **B/C.** POS system, Kitchen Display, table management [marketing] (same source).
- **F.** Purchase tracking, stock management, item lists [marketing] (same source).
- **M.** Income/expense tracking, profit/loss reporting, "due list" management [marketing] (same
  source).
- **Q.** "100+ Languages" claimed, multi-currency — positioned for resale outside India too, unlike
  every other app in this file [marketing] (same source).
- **B.** "QR Code Table Booking" appears as a named tier feature in pricing copy [marketing] (same
  source).
- Not found: GST-specific (vs. generic VAT) language, recipes, procurement workflow beyond basic
  purchase tracking, aggregator integration, CRM/loyalty.

**What users complain about / praise:** **Not found.** No independent review of this specific
package or the nammaworld.org storefront was located on any platform searched (Play Store,
Capterra, G2, Trustpilot, Reddit). Recorded as a genuine coverage gap.

---

## 5. Shopto — Restaurant Billing App POS KOT (frihbi.app)

| | |
|---|---|
| Package | `frihbi.app` |
| Developer | Frihbi Inc. / "Shopto Inc." (both names appear across sources) [listing] |
| Installs | 10,000+ [listing-via-search-cache]; last updated 9 May 2026 [listing-via-search-cache] |
| Rating / review count | Indus Appstore (a rival Indian Android store, not Google Play) shows **"4.0 stars"** alongside a percentage rating distribution (73% five-star, 10% four-star, 4% three-star, 3% two-star, 10% one-star) but simultaneously states **"0 total ratings"** and "No reviews yet. Be the first one to review this app" [listing] (https://www.indusappstore.com/apps/business/shopto/frihbi.app/) — an internally inconsistent listing, flagged rather than resolved; treat the 4.0/distribution figures as unreliable |
| Price | **Not found** — no pricing tier located on shopto.app |
| Web/desktop companion | Yes — shopto.app includes a "commission-free online store" builder with AI-assisted product upload [marketing] (https://shopto.app/) |

**Strengths:** Combines POS/KOT with a direct-to-consumer online store (positioned against
aggregator commissions) and native QR ordering in one free-tier product [marketing] (https://shopto.app/).

**Feature areas found:**
- **A.** GST-compliant invoices; offline billing with automatic sync when back online [marketing]
  (https://shopto.app/).
- **B.** QR digital menu for customer self-ordering [marketing] (same source).
- **C.** KOT auto-generation plus a named KDS for live kitchen order management [marketing] (same
  source).
- **F.** Stock tracking with low-stock alerts and **explicit wastage monitoring and supplier
  management** named as features [marketing] (same source) — supplier/wastage tracking called out
  by name is unusual at this price tier.
- **K.** Built-in CRM that auto-saves customers, order history, loyalty features [marketing] (same
  source).
- **M.** Daily/weekly/monthly sales analytics, staff performance insights, best-seller reports
  [marketing] (same source).
- **P.** Bluetooth thermal printer support (2" and 3") [marketing] (same source).
- Not found: recipe/BOM costing, procurement (PO/GRN) workflow, aggregator (Swiggy/Zomato) direct
  integration.

**What users complain about / praise:** **Not found.** The one review-capable listing readable in
this session (Indus Appstore) explicitly states there are no reviews yet, and no Play Store,
Capterra, G2 or Reddit content was located for this app. Recorded as a genuine coverage gap, not as
evidence of user satisfaction.

---

## 6. SOLO Restaurant App

| | |
|---|---|
| Package | `mpos.billing.app` |
| Developer | A Rajkot, Gujarat-registered company (per app metadata: 8th Floor, The Spire, Ring Road, Rajkot 360007) [listing] |
| Installs / rating | **Not found** on Play Store directly; **Techjockey shows 4.1/5 "based on 3 verified ratings"** for the broader "Solo Billing" product line (80% would recommend) — this is an extremely thin sample and may cover the desktop/general SOLO product rather than this specific Android app [review] (https://www.techjockey.com/detail/solo-billing) |
| Last updated | **Not found** |
| Price | Two figures found and not fully reconciled: Techjockey lists "Starting Price: ₹8,000 (20% OFF from ₹10,000) excluding GST, yearly per outlet" [pricing] (https://www.techjockey.com/detail/solo-billing, checked 2026-09-13); a separate search-indexed snippet of solobilling.com's own pricing page states "starts at INR 10,000 per year/outlet" [pricing] (https://solobilling.com/pricing) — the two are consistent with a running 20%-off promotional price against a ₹10,000 list price, but this file does not treat that reconciliation as confirmed |
| Web/desktop companion | Yes — solobilling.com plus a separate "solo.admin" owner-monitoring companion app on Play Store [listing] (https://play.google.com/store/apps/details?id=com.solo.admin_android) |

**Strengths:** Direct Swiggy/Zomato order receipt into the same billing screen (avoiding a separate
tablet per aggregator) [marketing] (search-engine summary of mpos.billing.app listing); a separate
"owner app" for live remote monitoring of sales/expenses/revenue is a distinct SKU rather than a
tab bolted onto the main app.

**Feature areas found:**
- **A.** GST-ready invoices, custom logo, UPI QR code on bill, multiple payment modes [marketing]
  (Play Store listing description, indexed via WebSearch).
- **C.** Kitchen order printing described as numbered/sequential, plus **printing organized by food
  category to different kitchen areas** [marketing] (https://solobilling.com/).
- **D.** "Easy Menu Changes" including area-based pricing for different restaurant sections (e.g.
  AC vs. non-AC zone pricing) — a granular pricing feature not named elsewhere in this file
  [marketing] (same source).
- **F.** Raw material tracking, stock management, recipe management, food cost calculation, wastage
  monitoring, low-stock alerts all explicitly named [marketing] (mpos.billing.app listing summary,
  indexed via WebSearch) — if accurate, this is the most complete stated F/E feature set of any app
  in this required group, though entirely vendor-claimed and unverified by any review.
- **I.** Swiggy and Zomato "third-party integration" named directly [marketing] (https://solobilling.com/).
- **O.** "Remote Store Management" for owners across locations [marketing] (same source).
- Not found: explicit CRM/loyalty beyond "Offers & Promotions," procurement/PO workflow, offline
  mode.

**What users complain about / praise:** **Not found** as named, attributable review quotes for
this specific app. The Techjockey aggregate (4.1/5, n=3) is too thin to support any complaint or
praise pattern; recorded as a coverage gap.

---

## Extras: significant Play Store apps not on the original six-app list

**myBillBook** (`com.valorem.flobooks`) — included because it is, by a wide margin, **the largest
app in this entire research file by installs and review count**: 10 million+ downloads, 4.41/5
across 140,000 ratings, last updated 4 May 2026, on Play Store since February 2020 [listing-via-
search-cache, AppBrain snapshot indexed by WebSearch]. It is not restaurant-only — it is a
general GST billing app for MSMEs ("trusted by over 1 crore MSMEs") with a dedicated restaurant
vertical/landing page — but its restaurant feature set (table-wise/running bills, hold-resume,
digital QR menu, multi-outlet reporting) is real and documented [marketing]
(https://mybillbook.in/s/restaurant-billing-software/). Pricing starts at ₹199/month [marketing]
(same source, checked 2026-09-13). It explicitly lacks KOT/KDS and aggregator integration
[marketing] (same source) — the generalist-vs-purpose-built tradeoff is itself a finding (see
patterns section).
- Complaints: "customer service was extremely unresponsive and unhelpful," support "escaping from
  problems by citing temporary solutions" [review-aggregation] (search-engine summary of
  hostingcharges.in/reviews/my-billbook); a 1-star Play Store review describes buying a 2-year
  subscription only to find "custom invoice themes and advanced customization require additional
  payments as add-ons" [review] (search-engine summary of Play Store review content); a Shopify
  review describes being charged after canceling before auto-renewal with no refund response
  [review] (search-engine summary, February 2026); a specific 2026 complaint alleges Reverse Charge
  Mechanism (RCM) invoices are mishandled — treated as forward-charge at 0% and issued as a Bill of
  Supply instead of a Tax Invoice — a real GST-compliance defect if accurate, not independently
  verified against the GST rules themselves [review] (search-engine summary; primary review URL not
  independently re-fetched with quote intact).
- Praise: "users finding the customer support responsive and helpful," and users "appreciating the
  quick billing feature that allows them to generate invoices in less than a minute"
  [review-aggregation] (same hostingcharges.in summary).

**GoRestro** (`com.omt.gokitchen`) — included as a purpose-built, India-only restaurant billing app
with the **most granular, vendor-published annual INR pricing tiers found in this entire file**:
Silver ₹999/year (excludes inventory and cash register), Platinum ₹1,499/year (adds table
reservations, limited payment gateway), Gold ₹1,999/year (full feature set, marked "Popular")
[pricing] (https://gorestro.com/, checked 2026-09-13). No installs, rating, or independent review
of any kind was found for this app on any platform searched — Play Store unreadable, no
Capterra/G2/Trustpilot listing located. Recorded as a coverage gap, not evidence of quality either
way.
- Feature areas: KOT, real-time inventory, staff shift/performance tracking, table reservations
  with custom floor plans, QR contactless menu, payment gateway integration, and named hardware
  compatibility (barcode scanners, receipt printers, cash drawers) [marketing] (same source). Not
  found: recipes, procurement, CRM/loyalty, KDS by name, aggregator integration.

**BillSarthi** (`com.billsarthi`) — included because it is the only app in this file's full set
(required six plus extras) claiming **native reach across Android, iOS, Windows and Mac**
("Android, iPhone, Windows, Mac or Web") rather than an Android-only or Android+web product
[marketing] (https://billsarthi.com/product/bill-sarthi-restaurant-billing-app-android-version/).
Positions itself as "India's No. 1 Free Restaurant Billing Software" [marketing]
(https://billsarthi.com/restaurant-billing-software-pos/) with a genuine free tier for unlimited
receipts, upgrading for advanced features. A third-party site-ranking tracker (not an install
count) shows the Play Store page ranked #781,794 with a recent gain of 3,318 positions — a weak
popularity proxy, not installs or ratings [traffic-estimate] (https://chrome-stats.com/d/com.billsarthi).
No independent review was found.
- Feature areas: KOT + named KDS, table-wise order tracking, item variants/modifiers, low-stock
  alerts, wastage-reduction monitoring tied to sales, role-based staff access, WhatsApp invoice
  sharing, Bluetooth thermal printer support, offline mode [marketing] (https://billsarthi.com/restaurant-billing-software-pos/).
  Not found: recipes/BOM costing, procurement, CRM/loyalty, aggregator integration, native
  Windows/Mac feature parity detail (the claim exists on the marketing site but was not
  independently verified as a real native client vs. a web wrapper).

**BoltBills** (`com.prabalverma.boltbills`) — included as the clearest example in this research
pass of the segment's *newest, most stripped-down* end: a single-developer app (Prabal Verma) that
explicitly **dropped its own paid tier and is now "free for all users with no more paid service or
subscription"** [marketing] (search-engine summary of the app's own Play Store/App Store listing
copy, cross-checked against apps.apple.com/in/app/restaurant-pos-boltbills/id6739431073). This
zero-monetization positioning, one step past Restrofi's free *tier* (Restrofi still sells paid
tiers above it — see `01-platforms.md`), is worth tracking as a leading indicator of price pressure
at the bottom of this market. No installs, rating or independent review was found for this app on
any platform searched.
- Feature areas: table/floor management, dine-in/takeaway/delivery order modes, customizable menus
  with variants and kitchen notes, GST and non-GST receipt styles, daily sales reports by payment
  type and top items, KOT printing [marketing] (search-engine summary of the app's own listing
  copy). Not found: inventory, recipes, procurement, CRM/loyalty, offline mode (not confirmed
  either way).

---

## What users complain about (cross-app patterns already itemized above; consolidated here)

- **Zobaze:** paid-model transition after being free; tax calculated pre-discount not post-discount
  (a real compliance-adjacent bug); UI rough edges.
- **Vyapar (parent product, Table not independently reviewed):** support unresponsive after
  renewal; data glitches/mismatches; app hangs/slow after updates.
- **myBillBook:** unresponsive support; hidden add-on costs for features implied as included;
  charged after cancellation with no refund response; a specific alleged RCM/GST-handling defect.
- **Arow, Namma Restaurant, Shopto, SOLO, GoRestro, BillSarthi, BoltBills:** no independent review
  content was found at all — recorded honestly as coverage gaps rather than inferred from marketing
  tone. This absence is itself informative: unlike the platforms in `01-platforms.md` (which mostly
  have hundreds of Capterra/G2 reviews), most of this Play-Store tier is reviewed nowhere but the
  Play Store itself, which this session could not read directly.

## What users praise (cross-app patterns)

- **Speed/simplicity:** repeatedly the top praise where any review exists — "print bills in
  seconds," "generate invoices in less than a minute" (myBillBook), "very user-friendly... very
  fast" (aggregate summaries for the Namma-brand family generally, not attributable to the specific
  Acnoo package in scope here).
- **Offline reliability:** named explicitly as a pro for Zobaze; marketed as a core feature by
  Arow, Shopto, BillSarthi, Vyapar Table — offline-first is treated as table stakes at this price
  point, not a differentiator.
- **Free/cheap entry:** "It's a very powerful app for something that is free" (Zobaze reviewer);
  BoltBills' full move to $0; GoRestro's ₹999/year floor — price is a headline draw at this tier in
  a way it is not for the platforms in `01-platforms.md`.

## Patterns across Play Store apps

1. **Review coverage collapses below the "big 11" tier.** `01-platforms.md`'s products mostly carry
   hundreds of Capterra/G2 reviews; every app in this file except Zobaze (830 ratings) and myBillBook
   (140,000 ratings, but as a generalist billing app, not restaurant-specific) has close to zero
   independently readable review content. Restaurant owners choosing at this price point are
   flying blind on quality signals in a way owners choosing Petpooja/GoFrugal are not.
2. **Templated/white-label resale is real at this tier.** Namma Restaurant is a rebrand of a
   CodeCanyon SaaS template; this changes the competitive calculus — Restaurant OS is not only
   competing against companies, but against anyone who can license a $50–200 template and publish
   it under a new name in days.
3. **Offline mode and instant billing speed are assumed, not differentiators.** Every app in this
   file that publishes a feature list leads with speed and offline capability; this is the entry
   ticket for this segment, not a selling point Restaurant OS can win on alone.
4. **Price is a headline weapon, not a footnote.** GoRestro's ₹999/year and BoltBills' $0 sit far
   below anything in `01-platforms.md` (cheapest there was Restrofi's ₹499/month = ~₹6,000/year).
   This file's tier competes on annual, not monthly, INR figures, often under ₹2,000/year.
5. **"Free" is unstable.** Zobaze and (by report) myBillBook both moved features from free to paid
   after building a user base — the two complaint threads most consistently found across apps with
   any review history at all are (a) support unresponsiveness and (b) a monetization change that
   users experienced as a bait-and-switch. A small restaurant's tolerance for a pricing surprise is
   apparently very low — this is the likeliest single trigger for switching apps in this segment.
6. **GST correctness bugs surface even in "GST-ready" marketing.** Both Zobaze (discount/tax order
   of operations) and myBillBook (RCM handling, Bill of Supply vs. Tax Invoice) had specific,
   named tax-calculation defects reported by users — not just UX complaints. This is directly
   relevant to Restaurant OS's own compliance discipline: cheap competitors' GST claims should not
   be assumed correct just because they are marketed as "GST-compliant."
7. **Naming collisions and lookalike branding are common** ("Namma Bill," "Namma Billing," "Namma
   Restaurant" as three unrelated products; "SOLO Restaurant App" vs. "Solo by MYOB," "Solo Kiosk,"
   "Solo Gig App" as unrelated apps sharing a generic name) — a real due-diligence hazard for a
   restaurant owner searching Play Store by keyword, and a reminder that ASO-driven naming in this
   category tells a buyer little about who actually built the product.

---

## Merged feature table (rows not already in `01-platforms.md`, or noted as shared)

| Area | Feature | Apps that have it | Evidence tags | Source URLs |
|---|---|---|---|---|
| A | GST invoices with WhatsApp/email delivery | Vyapar Table, Shopto, BillSarthi | marketing | vyaparapp.in/pos-software/restaurant; shopto.app; billsarthi.com |
| A | Non-GST "simple bill" style alongside GST bill | BoltBills | marketing | (BoltBills own listing copy, indexed via WebSearch) |
| A | Area/zone-based differential pricing (e.g. AC vs. non-AC seating) | SOLO | marketing | solobilling.com |
| B | QR ordering marketed explicitly as an anti-aggregator-commission play | Arow, Shopto | marketing | arowapp.com; shopto.app — *also in 01 (DotPe/DineOpen's "escape commission" framing)* |
| B | Anonymous customer feedback via QR code | Arow | marketing | arowapp.com |
| C | Kitchen printing routed by food category to different physical stations | SOLO | marketing | solobilling.com |
| D | Recipe standardization *claimed* inside a general billing app's restaurant module | Vyapar Table, SOLO (unverified) | marketing | vyaparapp.in/pos-software/restaurant; (SOLO listing summary) |
| F | Supplier management named as a distinct feature at this price tier | Shopto | marketing | shopto.app |
| F | Recipe/food-cost calculation + wastage monitoring named together (unverified) | SOLO | marketing | (SOLO listing summary, WebSearch) |
| I | Direct receipt of Swiggy/Zomato orders into the same billing screen (no separate tablet) | SOLO | marketing | (SOLO listing summary, WebSearch) |
| K | Built-in CRM auto-saving every customer + order history at the free tier | Shopto | marketing | shopto.app |
| L | Named "owner app" as a separate SKU for remote monitoring (not a tab in the main app) | SOLO | marketing | solobilling.com; play.google.com/.../com.solo.admin_android |
| M | Generalist GST-billing app with a bolted-on restaurant vertical page (not a purpose-built product) | myBillBook, Vyapar Table | marketing | mybillbook.in/s/restaurant-billing-software; vyaparapp.in/pos-software/restaurant |
| P | Native multi-platform reach claimed: Android + iOS + Windows + Mac | BillSarthi | marketing | billsarthi.com |
| P | 100+ language / multi-currency positioning (non-India resale via white-label) | Namma Restaurant (Acnoo template) | marketing | nammaworld.org |
| Q | Templated/white-label SaaS product resold under a local brand name | Namma Restaurant | marketplace | codecanyon.net/item/restaurant-app-saas-food-ordering-table-booking-app-with-laravel-admin-panel/58370658; nammaworld.org |
| R | Sub-₹1,000/year entry tier (below even Restrofi's ₹499/month floor from 01) | GoRestro (Silver, ₹999/yr) | pricing | gorestro.com |
| R | Full move from paid to $0, no subscription at all | BoltBills | marketing | (BoltBills listing copy) |
| R | Tax computed on pre-discount price instead of post-discount (compliance-relevant defect) | Zobaze | review | softwareadvice.com/retail/zobaze-pos-profile/reviews |
| R | Alleged Reverse Charge Mechanism / invoice-type mishandling under GST | myBillBook | review | (search-engine summary; primary URL not independently re-fetched with quote intact) |

---

## Unusual or distinctive features

- **A restaurant app that turns out to be a resold CodeCanyon template.** Namma Restaurant
  (`com.acnoo.restaurant_app`) traces directly to Acnoo's "Restaurant App SaaS" marketplace product
  and a branded reseller storefront (nammaworld.org) — no other app surveyed in this file or in
  `01-platforms.md` was found to be a template resale rather than an in-house build [marketplace]
  (https://codecanyon.net/item/restaurant-app-saas-food-ordering-table-booking-app-with-laravel-admin-panel/58370658).
- **A domain that has actually expired.** One of Arow's two marketing domains, arow.pro,
  301-redirected to a domain-parking/expired-listing page as observed live in this session
  (2026-09-13) — a concrete signal of under-maintenance at this end of the market, not an inference.
- **A live listing with self-contradictory rating data.** Shopto's Indus Appstore page shows a
  4.0-star rating and a full percentage breakdown by star count while also stating "0 total
  ratings" and "No reviews yet" — flagged as unreliable rather than resolved.
- **Kitchen tickets routed by food category to different physical print stations** — SOLO's
  claimed feature, not found named this specifically anywhere in `01-platforms.md`'s products
  either (those describe KOT routing by station generically, not "printing organized by food
  category").
- **A dedicated, separate "owner monitoring" app SKU** (SOLO's `solo.admin`) rather than an
  "owner view" folded into the main app — the only example of this pattern found in either research
  file.
- **Full de-monetization.** BoltBills moving to "no more paid service or subscription" — the
  opposite trajectory from Zobaze's free-to-paid move, and further even than Restrofi's genuine
  free *tier* (Restrofi still sells paid tiers above it).

---

## Sources

Vyapar "Table": https://play.google.com/store/apps/details?id=in.android.restaurant_billing&hl=en_IN ·
https://www.appbrain.com/app/table-restaurant-billing-app/in.android.restaurant_billing (read via
WebSearch cache, direct fetch blocked) · https://vyaparapp.in/pos-software/restaurant ·
https://vyapartable.com/ (403 to WebFetch) · https://www.capterra.com/p/180579/Vyapar/reviews/

Arow: https://play.google.com/store/apps/details?id=com.arowapp.arowapp ·
https://www.arow.pro/ (now redirects to expireddomains.com, checked 2026-09-13) ·
https://www.arowapp.com/ · https://play.google.com/store/apps/dev?id=6541308544455972723

Zobaze: https://play.google.com/store/apps/details?id=com.zobaze.restaurant.pos ·
https://www.appbrain.com/app/restaurant-caf%C3%A9-billing-pos/com.zobaze.restaurant.pos (via
WebSearch cache) · https://zobaze.com/blog/restaurant-pos-billing-software ·
https://www.selecthub.com/p/retail-pos-systems/zobaze-pos/ ·
https://www.softwareadvice.com/retail/zobaze-pos-profile/reviews/ ·
https://www.softwaresuggest.com/zobaze-pos

Namma Restaurant: https://play.google.com/store/apps/details?id=com.acnoo.restaurant_app ·
https://nammaworld.org/ ·
https://codecanyon.net/item/restaurant-app-saas-food-ordering-table-booking-app-with-laravel-admin-panel/58370658 ·
(distinguished from, not sourced from: https://www.nammabilling.com/ and
https://play.google.com/store/apps/details?id=com.coderstudio.nammabilling and
https://play.google.com/store/apps/details?id=com.nammabilling.ip.namma_billing)

Shopto: https://play.google.com/store/apps/details?id=frihbi.app ·
https://www.indusappstore.com/apps/business/shopto/frihbi.app/ · https://shopto.app/

SOLO Restaurant App: https://play.google.com/store/apps/details?id=mpos.billing.app ·
https://www.techjockey.com/detail/solo-billing · https://solobilling.com/ ·
https://solobilling.com/pricing · https://play.google.com/store/apps/details?id=com.solo.admin_android

myBillBook: https://play.google.com/store/apps/details?id=com.valorem.flobooks ·
https://www.appbrain.com/app/mybillbook-invoice-billing-app/com.valorem.flobooks (via WebSearch
cache) · https://mybillbook.in/s/restaurant-billing-software/ ·
https://www.hostingcharges.in/reviews/my-billbook

GoRestro: https://play.google.com/store/apps/details?id=com.omt.gokitchen · https://gorestro.com/

BillSarthi: https://play.google.com/store/apps/details?id=com.billsarthi · https://billsarthi.com/ ·
https://billsarthi.com/restaurant-billing-software-pos/ ·
https://billsarthi.com/product/bill-sarthi-restaurant-billing-app-android-version/ ·
https://chrome-stats.com/d/com.billsarthi

BoltBills: https://play.google.com/store/apps/details?id=com.prabalverma.boltbills ·
https://apps.apple.com/in/app/restaurant-pos-boltbills/id6739431073

Referenced for de-duplication only: `docs/product/competitor-research/01-platforms.md`
