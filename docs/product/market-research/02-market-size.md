# Market Size and Shape — Indian Restaurant Food-Service Sector

**Scope:** Size and shape of the Indian restaurant/food-service market — outlet counts, market
value, city concentration (with Pune detail), online-delivery penetration, technology adoption,
restaurant unit economics, and formal-registration counts — as inputs to a TAM/SAM/SOM sizing for
Restaurant OS, a single-outlet-first restaurant SaaS. This is step 2 of 3 in the market-research
sequence; step 1 (`01-company-metrics.md`) covers competitor company numbers and is not repeated
here beyond the "Summary table" / "Market share picture" sections read for context.

**Date of research:** 2026-09-13.

**Method:** Public-source web research (WebSearch where available, WebFetch against publisher
sites otherwise) against: NRAI India Food Services Report (press summaries — the report itself is
paywalled/member-only), Redseer, Technopak, Zomato/Eternal annual reports and investor materials,
Swiggy annual report / RHP-DRHP (SEBI) and shareholder letters, Invest India / IBEF, FSSAI,
NPCI (UPI data), Statista summaries, and business press (Economic Times, Inc42, YourStory, Business
Standard, Mint, moneycontrol). **Known constraint:** the previous research pass in this project
exhausted its WebSearch budget early; this pass plans combined/broad queries and prefers direct
WebFetch of publisher pages where a query would be redundant. Each figure below records which
method produced it.

**Label legend (mandatory on every figure):**
- **[primary]** — the publisher's own report/filing, read directly.
- **[summary]** — a press summary of a report that could not be read directly (e.g. NRAI report
  behind a paywall/membership, cited only via news coverage).
- **[vendor]** — a company's own marketing claim.
- **[estimate]** — a third-party estimate (Statista, research-firm blog, etc.) not itself a primary
  filing.
- **[conflict]** — sources disagree; all values are listed, never averaged.

**Caveat:** Many Indian food-service market numbers circulate as unattributed repeats of an
original NRAI/Redseer/Technopak figure — this file tries to trace each number to its earliest
identifiable source and says explicitly when it could not. Never fill a rate, threshold, or count
from memory — see `docs/compliance-rules.md`'s standing rule, which applies to research method
generally in this repo. Nothing here should be read as current beyond the cited article's own
publication date.

---

## 1. Restaurants in India — count, organised/unorganised, format split, growth

| Figure | Period | Label | Source |
|---|---|---|---|
| NRAI "represents 500,000+ Restaurants" | current (site copy, fetched 2026-09-13) | [primary] | nrai.org/NRAI_Food_Summit/About_Nrai.aspx |
| Food services sector to grow at **8.1% CAGR, 2024–2028** | 2024–2028 | [summary] | NRAI India Food Services Report (IFSR) 2024, as covered by Business Standard (2024-07-09), Hospitality Biz India (2024-07-12), BusinessLine "to grow 8% CAGR to ₹7.76-lakh crore by 2028" (2024-07-10) |
| A separate headline: "**NRAI projects 13% CAGR growth** for food services sector by FY28" | to FY28 | [conflict] | headline surfaced via Google News, 2024-07-10 — publisher not confirmed (link did not resolve). Likely refers to a narrower segment (e.g. the *organised* sub-sector, which press coverage elsewhere frames as growing faster than the informal/unorganised tail) rather than the whole industry's 8.1% figure — not confirmed, listed as a straight conflict per instructions |
| Restaurant industry employed **7.3 million people**, FY 2018–19 | 2018–19 | [summary] | NRAI, as covered by The Statesman, 2019-05-10 |
| Unorganised street food market sized at **$41 billion** | ~2020 | [estimate] | YourStory ("Can Swiggy and Zomato help India's $41B unorganised street food market go online?"), 2020-10-14 — original estimator not identified in this pass |
| India Cloud Kitchen Market to reach **USD 3,211.7 million by 2033**, 12.67% CAGR | to 2033 | [estimate] | openPR.com press-release aggregator, 2026-01-22 — low confidence; openPR syndicates vendor-commissioned market-research press releases, original research house not identified |
| Global (NOT India-specific) cloud kitchen market: **USD 248.10 billion by 2035** | to 2035 | [estimate] | precedenceresearch.com, 2022-03-28 — flagged explicitly as global scope, included only to show the India figure above is ~1,300x smaller and likely a narrow India-only estimate, not comparable |
| "25% of eateries closed in FY21 due to Covid" | FY21 (pandemic year) | [summary] | The Times of India ("Study" not named), 2021-10-26 — a pandemic-shock closure rate, not a baseline/steady-state failure rate (see §6) |
| Historical baseline: food services market projected to reach **over ₹5.5 lakh crore by 2022** | projection made 2017, target year 2022 | [summary] | FICCI-Technopak Report, as covered by DNA India and ET Retail, both 2017-11-14/15 — superseded by the 2024 NRAI figure below but included to show the trajectory |

**Organised vs unorganised split:** no clean, sourced percentage split (e.g. "X% organised / Y% unorganised") was found in this pass. The $41B unorganised-street-food estimate above is the only unorganised-segment sizing found, and it is not on a common basis with any of the organised-segment figures in §2 (different base year, different methodology, estimator not identified) — **do not net these against each other**.

**Format split (QSR / casual dining / fine dining / cafés / cloud kitchens):** no sourced percentage breakdown by format was found. Only a cloud-kitchen-specific market-size estimate (above) surfaced; QSR, casual dining, fine dining and café shares of the total restaurant count or market value are a **gap** — see "Gaps" section.

**Growth rate note:** Every CAGR figure found (8.1%, 13%, and the historical 9% "to touch Rs 6 trillion by FY23" from a 2019 Business Standard headline) traces to the same family of NRAI/FICCI-Technopak-style reports whose full text is paywalled; only press-summary headlines were accessible. None could be independently verified against the underlying report.

---

## 2. Food-service market value

| Figure | Period/horizon | Label | Source |
|---|---|---|---|
| **₹5.69 lakh crore** current size (~$68B at ~₹83/$) | "current", as of report launch | [primary]/[summary] | NRAI IFSR 2024 — figure appears both on NRAI's own site (nrai.org, [primary]) and in press coverage of the report's 2024-07 launch (Business Standard, BusinessLine, Hospitality Biz India, all 2024-07-09/10/12) |
| → projected **₹7.76 lakh crore by 2028** (~$93B) | to 2028 | [summary] | same NRAI IFSR 2024 launch coverage, 2024-07 |
| FICCI-Technopak: **>₹5.5 lakh crore by 2022** | projection made 2017 | [summary] | DNA India, ET Retail, 2017-11 |
| **$79.65 billion by 2028** | to 2028 | [conflict] | The Indian Express, 2022-11-21, report/publisher of the underlying study not named in headline |
| **>$100 billion by 2028** | to 2028 | [conflict] | The News Minute, 2024-02-15 |
| **$144–152 billion by 2030** | to 2030 | [conflict] | Business Standard, 2025-01-30; also ET Retail, 2025-01-29 ("up to $152 billion by 2030") |
| **$150 billion by 2030**, "organised players driving growth" | to 2030 | [conflict] | BW Businessworld, 2026-07-10 |
| **$125 billion food market by 2030** | to 2030 | [conflict] | Swiggy–Kearney report, as covered by Business Standard, BusinessLine, entrepreneurindia.com, all 2025-11-27 — note this is described as "food market" not "food services market"; scope may differ from the others |
| **$50 billion by FY31**, with online share rising to 18% | to FY31 | [conflict] | The Economic Times, 2026-07-09 — roughly a third of the $125–152B figures for a similar horizon; likely a narrower segment (e.g. branded/chain-only, or a different report's methodology) but this repo could not confirm the scope difference in this pass |
| Food delivery market specifically: **>₹2 lakh crore by 2030** (~$24B) | to 2030 | [summary] | Bain–Swiggy report, as covered by The Economic Times, 2024-07-03 |

**[conflict] — no averaging performed.** Every one of the six market-value projections above ($79.65B/2028, $100B/2028, ₹7.76 lakh cr≈$93B/2028, $125B/2030, $144–152B/2030, $150B/2030, $50B/FY31) comes from a different report commissioned at a different time by a different sponsor (NRAI, unnamed studies, Swiggy–Kearney, and at least one unidentified source behind the $50B/FY31 ET headline). They are **not a time series of the same metric** — treat each as a distinct claim tied to its own report, not as evidence the market is "actually" any one of these sizes. The $50B/FY31 figure in particular looks like it may describe a materially narrower base than the others; this was not resolved.

**Organised share of the market:** not found as an explicit, separately-stated percentage (e.g. "X% organised") in any of the above. BW Businessworld's 2026-07 headline states organised players are "driving growth" toward the $150B/2030 figure but gives no organised/unorganised split number.

---

## 3. Top cities and Pune

All city-level figures below trace to press coverage of the same NRAI IFSR 2024 launch (July 2024) unless otherwise noted — this appears to be the only source that broke the national number down by city in the period researched.

| City | Figure | Period | Label | Source |
|---|---|---|---|---|
| Bengaluru | Organised food service sector valued at **₹26,475 crore** | 2024 (IFSR 2024) | [summary] | NRAI IFSR 2024, as covered by an outlet whose exact name did not resolve via the Google News link (headline: "NRAI Report: Bengaluru's Organized Food Service Sector Valued at ₹26,475 Crores"), 2024-07-15 |
| NCR (Delhi) | Food market size **₹42,000 crore** | 2024 (IFSR 2024) | [summary] | NRAI IFSR 2024, headline via Google News, publisher not resolved, 2024-07-10 |
| Chennai | Ranks **4th** nationally; market size **₹15,600 crore**; residents dine out **4.28 times/month**, spending **₹825/person** | 2024 (IFSR 2024) | [summary] | NRAI IFSR 2024, Hospitality Biz India, 2024-07-15 |
| Hyderabad | "Largest food services market in the country" (per an unnamed "Study") | 2024 | [summary] | The Times of India, 2024-07-12 — headline gives no ₹ figure |
| Hyderabad | "Food business... to rake in over **₹5 lakh crore** in 2024" (restaurants' association claim) | 2024 | [conflict] — **almost certainly a reporting error**. ₹5 lakh crore would be ~88% of the *entire national* ₹5.69 lakh crore IFSR 2024 figure for one city; near-certainly should read ₹5,000 crore or similar | The Hindu, 2024-07-11, attributed to "restaurants' association" (a local body, not NRAI directly) |
| Hyderabad | Restaurants' market share **>₹6,000 crore** (older, smaller, different year) | 2022 | [summary] | The New Indian Express, 2022-01-29 — not on the same basis as the 2024 figures above; included to show the ₹5 lakh crore claim is an outlier even against Hyderabad's own earlier reporting |
| Mumbai | Organised food service market **₹40,480 crore** | 2019 (IFSR 2019) | [summary] | NRAI IFSR '19, Food & Beverage News, 2019-06-14 — this is the *2019* edition of the report; no 2024-equivalent Mumbai figure was found in this pass (gap) |
| Goa | Ranks **12th** nationally; **15,000+ restaurants**; market size **₹1,940 crore** | 2024 (IFSR 2024) | [summary] | NRAI IFSR 2024, The Times of India, 2024-07-13 |
| Kolkata | Restaurant count reaches **38,838** | 2019 | [summary] | headline via Google News aggregation, publisher not resolved, dated 2019-07-03 (older civic/licensing-style count, not confirmed as NRAI-sourced) |

**Top-8-city ranking:** the full ranked list (1st through 8th, or 1st through 12th given Goa is stated as 12th) was not recovered — only individual city placements mentioned in passing (Chennai 4th, Goa 12th) surfaced. The complete ranking almost certainly exists in the full NRAI IFSR 2024 report, which is paywalled/membership-gated (see `docs`-style caveat in Method).

**Pune — the target market for Restaurant OS's first launch:**

**No Pune-specific market-size, restaurant-count, or Zomato/Swiggy-restaurant-count figure was found in this research pass**, despite multiple targeted searches (direct NRAI IFSR city-breakdown searches, Zomato/Swiggy Pune-specific searches, and general Pune-food-service searches). What *was* found:
- NRAI has an active **Pune Chapter** (hosted a "Building Better Kitchens" event, 2025-11-26, per hospitality.economictimes.indiatimes.com) [summary] — confirms organisational presence but gives no sizing figure.
- Pune was named (alongside Mumbai and Bengaluru) in 2026-03 coverage of a commercial-LPG-supply crisis threatening "massive job losses" in restaurants — NDTV Profit, 2026-03-10, and The Times of India reported "nearly 100 restaurants affected" in Pune specifically by the LPG shortage, 2026-03-11 [summary]. This is a crisis-response headcount ("100 restaurants affected"), not a total-market-size or total-outlet-count figure, and should not be used as a proxy for Pune's restaurant count.
- Swiggy launched a low-cost delivery app "Toing" in Pune (Business Standard, storyboard18.com, 2025-09-15/16) [summary] — confirms Pune as an active, competitively-targeted Swiggy market but gives no restaurant-partner count.
- Zomato's Pune city landing page (zomato.com/pune) exists as a consumer discovery page but does not publish a restaurant count.

**This is the single largest gap in this file relative to the brief** — see "Gaps" below for where Pune-specific data most plausibly exists (the full paywalled NRAI IFSR 2024 report, and Zomato/Swiggy internal city-level dashboards not publicly disclosed).

---

## 4. Online delivery — Zomato / Swiggy restaurant counts, delivery share, commission

| Figure | Period | Label | Source |
|---|---|---|---|
| Swiggy: **1.2 lakh (120,000) restaurant partners across 290 cities** | 2019 (Swiggy's 5-year mark) | [summary] | YourStory, "the five-year journey of Swiggy", 2019-08-08 — **the only Swiggy active-restaurant-partner count found in this pass, and it is 6+ years stale.** No 2024–2026 update to this specific metric was found despite repeated searches (Swiggy's FY25/FY26 quarterly disclosures and DRHP were not directly accessible — see Method/Gaps) |
| Swiggy service-area (cities, not restaurant count): "now in 500 Indian cities" (2019) → "over 700 Indian cities" (2025) → 10-min "Bolt" service in "400+ cities" (2024-12) → affordable range "175+ cities" (2025-07) | 2019–2025 | [summary]/[estimate] | Livemint 2019-10-07; Wikipedia (2025); hospitality.economictimes.indiatimes.com 2024-12-03 and 2025-07-02 — these are geographic footprint claims, not restaurant-partner counts |
| Swiggy quarterly GOV: **₹9,005 crore, Q4 FY26**, +22.6% YoY | Q4 FY26 (Jan–Mar 2026) | [summary] | medianama.com, 2026-05-11 |
| Swiggy target: **more than triple GOV to ₹2.5 lakh crore, and ₹10,000 crore EBITDA, by FY31** | to FY31 | [summary] | Fortune India, 2026-08-06 |
| Swiggy Q1 FY27 revenue **₹6,812 crore**, +37% YoY; net loss narrowed to **₹791 crore** | Q1 FY27 (Apr–Jun 2026) | [summary] | "Indian Startup News" aggregator, 2026-08-01 |
| Zomato (FY23): delivery + table reservations across **800+ Indian cities**; **647 million orders** delivered, valued at **₹263.1 billion** | FY23 | [summary] | Wikipedia, citing Financial Express |
| Zomato/Eternal active restaurant-partner count | — | **not found** | No figure for Zomato's current active restaurant-partner count was located in this pass — a gap; Eternal's investor-relations pages are JavaScript-rendered and could not be fetched as static HTML (see Method) |
| Delivery-specific market size: **>₹2 lakh crore (~$24B) by 2030** | to 2030 | [summary] | Bain–Swiggy report, The Economic Times, 2024-07-03 |
| Commission: Swiggy "corners claims of capping commission under 25%" | ~2019 | [summary] | Entrackr, headline dated via Google News ~2019-09-02 — implies a commission ceiling discourse around the 25% mark historically, but no verified current commission range (%) with a primary or reported source was found |
| Rapido entering food delivery "offering lower restaurant commissions" | 2025-06 | [summary] | NDTV, 2025-06-09 — confirms incumbent (Zomato/Swiggy) commissions are perceived by new entrants as a competitive opening, but gives no specific % |

**Share of restaurant revenue from delivery:** not found as a sourced percentage for the Indian market specifically. **Gap.**

**Average commission range as reported:** not found as a single, current, citable range (e.g. "18–30%"). Historical (2019) coverage references a ~25% ceiling under regulatory/restaurant-association pressure, but this is dated and pre-dates several years of commission-structure changes reported anecdotally (service fees, ad spend, etc. per the 01-company-metrics.md UrbanPiper/DotPe sections). **Do not cite a specific commission % without a fresher, dated source.**

---

## 5. Technology adoption — POS, inventory software, digital payments/UPI, restaurant-tech market size

| Figure | Period | Label | Source |
|---|---|---|---|
| "Dining out surges in India: **UPI payments jump 34%** as restaurants see record sales" | 2025 (YoY comparison implied) | [summary] | The Economic Times, 2025-10-24 — headline gives a growth rate, not an absolute share-of-restaurant-payments percentage |
| "**73% of MSMEs** report business growth via digital adoption, led by UPI and smartphones" | Survey, 2025 | [summary] | The Economic Times, 2025-06-28 — general MSME population, **not restaurant-specific**; included as the closest proxy found |
| "**Digital payments power 74%** of retail spends in top Indian cities" | 2025 | [summary] | Indian Retailer, 2025-10-04 — general retail, **not restaurant-specific** |
| UPI overall: "UPI Hits 200 Billion Transactions"; "UPI tops global real-time payments with **49% share**" | 2025–2026 | [summary] | The Eastern Herald, 2026-05-31; The Times of India, 2025-12-08 — national/macro UPI statistics, not restaurant-sector-specific |
| India Cloud Kitchen Market: **USD 3,211.7 million by 2033** (see §1) | to 2033 | [estimate] | openPR.com, 2026-01-22 |
| "Restaurant POS Terminal Market" size reports found (Future Market Insights, Straits Research, precedenceresearch.com) | various, to 2034/2035 | [estimate] | **All global-scope reports; none had an India-specific breakout figure accessible in this pass** |

**Share of restaurants using POS/billing software:** **not found.** No source gave a percentage of Indian restaurants using any POS/billing system, inventory software, or comparable technology-adoption metric. This is a significant gap directly relevant to Restaurant OS's addressable market — see "Gaps."

**Digital payments / UPI share of restaurant-specific payments:** not found as a restaurant-sector-specific percentage; only general-MSME (73%) and general-retail (74%) proxies were found, plus a 34% YoY growth-rate headline specific to "restaurants" but without a base or absolute-share number.

**Restaurant-tech market size estimates (India):** not found as a distinct, India-specific "restaurant software/tech market" sizing (as opposed to the global POS-terminal-market reports above, which are hardware/terminal-market sizings, not software/SaaS-market sizings, and are not India-specific). This is the competitive-context number this repo would most want and it is a **gap**.

---

## 6. Restaurant economics — cost structure, revenue per outlet, failure rates

| Figure | Period | Label | Source |
|---|---|---|---|
| "25% of eateries closed in FY21 due to Covid" | FY21 | [summary] | The Times of India, "Study" unnamed, 2021-10-26 — a **pandemic-shock** closure rate, explicitly not a baseline/steady-state failure rate |
| "50–60% of restaurants could shut in 2–3 days if commercial LPG supply isn't resumed" (NRAI president quote) | 2026-03 crisis | [summary] | The Indian Express, 2026-03-10 — a **crisis-scenario warning**, not an observed closure statistic |
| "LPG shortage forces around 40% of restaurants in Kerala to shut down" | 2026-03 crisis | [summary] | The Economic Times, 2026-03-13 — same caveat, state-specific crisis event |
| "High rentals eat into restaurants' margins" (no % given) | 2011 | [summary] | The Economic Times, 2011-09-07 — too old and non-quantified to use |

**Food cost %, rent %, staff cost %, net margin ranges for Indian restaurants:** **not found.** Every search for India-specific restaurant cost-structure benchmarks returned either (a) generic/global restaurant-finance content (Oracle NetSuite "restaurant benchmarks," Toast's US-focused blog posts, WSJ steak-dinner-margin pieces) with no India figures, or (b) India content about *menu prices* and *GST rates*, not *cost structure*. **This is a significant, clearly-flagged gap** — see "Gaps."

**Average revenue per outlet by format:** **not found** for India. No source broke down average annual revenue by QSR / casual dining / fine dining / café / cloud-kitchen format for the Indian market.

**Restaurant failure/closure rates (baseline, not crisis-driven):** **not found.** No source gave an India-specific "X% of restaurants close within Y years" baseline statistic of the kind common in US restaurant-industry commentary (e.g. Forbes' "no, most restaurants don't fail in the first year" genre, which is itself US-specific and not transferable). Every India-specific closure figure found in this pass was tied to a specific shock (Covid FY21, the 2026 LPG supply crisis) rather than a steady-state base rate — per the brief's instruction, these are reported above with their shock context rather than presented as baseline failure rates.

---

## 7. Registration counts — FSSAI, GST

| Figure | Period | Label | Source |
|---|---|---|---|
| "Only 1 out of 15 food businesses registered with FSSAI" | 2016 | [summary] | The Hindu, 2016-02-10 — directly on-point as a registration-compliance-rate figure, but **9+ years stale**; no equivalent recent figure was found to check whether this ratio has improved |
| FSSAI licensing regime overhaul: licences/registrations to move to **"perpetual validity," no renewals needed** | Reform announced/notified March 2026 | [primary-adjacent — government reform, reported] | The Economic Times, 2026-03-13; Livemint, 2026-06-17 ("in a fillip to ease of biz, India scraps food safety licence renewal norm"); Deccan Herald, 2026-03-13 | 

**Total FSSAI-registered/licensed food business operators (India-wide count):** **not found.** No current total-registration-count figure (e.g. "X crore/lakh FSSAI registrations") was located despite multiple targeted searches. This is a real, cited gap — see "Gaps" for where it most likely exists (FSSAI's own annual report, which was not directly fetchable as static content in this pass).

**GST-registered restaurants (India-wide count):** **not found.** No source gave a count of GST-registered restaurant/food-service establishments specifically (as distinct from GST-registered businesses generally). Extensive coverage exists of GST *rate* changes affecting restaurants (5% vs 18% dining rates, service-charge disputes, aggregator GST-collection rules from 2022 onward) but none of it publishes a registrant count. **Gap.**

---

## 8. Sizing inputs — standalone organised restaurants that plausibly buy software

No single source gives this number directly. The closest available proxies, none of them clean:

| Figure | Label | Source | Caveat |
|---|---|---|---|
| NRAI "represents 500,000+ Restaurants" | [primary]/[vendor] | nrai.org, current site copy | Ambiguous whether this means 500,000 dues-paying members or "the industry NRAI advocates for" as a whole (i.e. a total-market claim, not a membership roll). NRAI's own site does not clarify which. |
| Petpooja: **100,000+ cumulative clients** (India + UAE + South Africa + Canada) | [vendor] | `01-company-metrics.md` §1, Petpooja Series C announcement, 2025-09-29 | Per that file's own analysis, this is almost certainly a lifetime/cumulative-install claim (not active-paying, not India-only) — FY25 filed revenue (₹102.3 Cr) is incompatible with 100,000 *paying* clients at Petpooja's own disclosed pricing floor. Treat as an upper-bound install-base signal, not a count of currently-paying organised restaurants. |
| Restroworks: **25,000+ customers, 53+ countries** | [vendor] | `01-company-metrics.md` §2 | Skews enterprise/chain accounts (Taco Bell, Subway, Nando's named), not single-outlet standalone restaurants — the segment `01-platforms.md`/this file's brief cares about most is likely *under*-represented here, not over. |
| LimeTray: **4,500+ restaurants** | [vendor] | `01-company-metrics.md` §6 | Smallest of the three; ARPU/revenue arithmetic in that file is the only one of the three that comes out plausible against filed revenue, suggesting this claim is closer to an active-paying count than Petpooja's or Restroworks'. |

**Illustrative, not sourced, arithmetic:** if NRAI's 500,000 figure is read as a literal total-restaurant count, and the vendor-claimed install bases above (Petpooja 100,000 + Restroworks 25,000 + LimeTray 4,500 + the smaller vendors listed in `01-company-metrics.md`'s "group 12" tail, roughly 35,000–50,000 more combined) are treated as non-overlapping, cumulative claimed penetration would be on the order of **25–35% of all restaurants nationally already claim some POS/software vendor relationship** — this is a back-of-envelope **[derived]** figure built entirely on unverified vendor claims stacked on an ambiguous NRAI figure, not a sourced adoption rate. It should not be used as a citable statistic; it is included only to show the shape of the estimation problem the orchestrator will need to solve with wider error bars than usual.

---

## Sizing inputs table (for the orchestrator's TAM/SAM/SOM — not computed here)

| Input | Best available value | Source | Confidence |
|---|---|---|---|
| Total India food services market value (current) | ₹5.69 lakh crore (~$68B) | NRAI IFSR 2024 [primary/summary] | Medium — corroborated by NRAI's own site and multiple press outlets covering the same report launch, but full report unread |
| Total India food services market value (2028 projection) | ₹7.76 lakh crore (~$93B), 8.1% CAGR | NRAI IFSR 2024 [summary] | Medium — single-report projection; conflicts with other reports' 2028/2030 figures (see §2) |
| Total restaurants in India (claimed) | 500,000+ | NRAI [primary/vendor] | Low — ambiguous whether membership or total-industry claim; no independent corroboration found |
| Organised-restaurant software-vendor claimed install base (upper bound, likely overlapping/inflated) | ~130,000–175,000+ combined (Petpooja + Restroworks + LimeTray + smaller vendors) | `01-company-metrics.md` [vendor, multiple] | Low — vendor-claimed, cumulative not active, likely double-counted across vendors and against churned accounts |
| Pune-specific restaurant count or market value | **not found** | — | None — see §3 and Gaps |
| Delivery-platform restaurant reach (Swiggy) | 1.2 lakh restaurant partners, 290 cities | YourStory, 2019 [summary] | Very low — 6+ years stale, no update found |
| Delivery-platform restaurant reach (Zomato) | not found | — | None |
| Food delivery market value (2030 projection) | >₹2 lakh crore (~$24B) | Bain–Swiggy report via ET, 2024 [summary] | Medium |
| Share of restaurants using POS/billing software | **not found** | — | None — see §5 and Gaps |
| Restaurant cost structure (food/rent/staff cost %, net margin) | **not found (India-specific)** | — | None — see §6 and Gaps |
| FSSAI-registered food business operators (total count) | **not found** | — | None — see §7 and Gaps |

**Explicit note to the orchestrator:** several of the highest-value sizing inputs (Pune-specific data, POS-adoption %, cost-structure %, FSSAI total count) are gaps, not low numbers — do not treat their absence here as evidence they are small or zero.

---

## Gaps

Ranked roughly by how much they matter to Restaurant OS's Pune-first, single-outlet-organised-restaurant thesis:

1. **Pune-specific data (outlet count, market value, Zomato/Swiggy restaurant counts).** Nothing found despite repeated targeted searches. Most likely exists in: the full NRAI IFSR 2024 report (paywalled/membership-gated at nrai.org — "Book Your Copy" flow, not previewed), and in Zomato/Swiggy internal city-level analytics that are not publicly disclosed at city granularity outside occasional press one-offs (Bengaluru, NCR, Chennai, Hyderabad, Goa were disclosed; Pune was not, in what press coverage of the same report launch surfaced).
2. **Share of Indian restaurants using POS/billing software, or any restaurant-specific technology-adoption %.** Not found. Most likely exists in a Redseer/Technopak/NASSCOM-style restaurant-tech report, none of which was accessible in this pass (Redseer's own report listing page, fetched directly, showed no matching India food-service report at the time of fetch).
3. **India-specific restaurant cost structure** (food cost %, rent %, staff cost %, net margin ranges). Not found. Likely exists in the same paywalled NRAI IFSR report, or in a Technopak/CRISIL-style sector report not accessed here.
4. **FSSAI total registration/licence count.** Not found. Most likely exists in FSSAI's own annual report (fssai.gov.in), which was not directly fetchable as static content in this pass (JS-heavy site, and no annual-report PDF link was successfully resolved).
5. **GST-registered restaurant count.** Not found; likely not published as a restaurant-specific breakout anywhere (GST registration data is typically published by broader industry/turnover bands, not by sub-sector).
6. **Zomato's current active restaurant-partner count.** Not found. Eternal's investor-relations site (eternal.com/investor-relations) is JavaScript-rendered and could not be fetched as static HTML; the figure likely exists in Eternal's annual report or a specific quarterly investor presentation PDF not directly reached.
7. **Swiggy's current (2024–2026) active restaurant-partner count.** The only figure found (1.2 lakh, 2019) is stale. Likely exists in Swiggy's FY24 DRHP (filed with SEBI ahead of its November 2024 IPO) or subsequent annual report/shareholder letters, neither of which was directly fetchable in this pass (moments.swiggy.com/investors is JS-rendered; SEBI's own DRHP repository was not queried directly).
8. **Average commission range currently charged by Zomato/Swiggy.** Only a stale (~2019) reference to a ~25% ceiling discourse was found. Likely exists in recent restaurant-association commentary or a Redseer/RestKit-style commission-benchmarking report not accessed here.
9. **Full top-8 (or top-12) city ranking table from NRAI IFSR 2024.** Individual placements (Chennai 4th, Goa 12th) surfaced but not the full list — behind the same paywall as item 1.
10. **A sourced India-specific restaurant failure/closure baseline rate** (as opposed to shock-driven closures from Covid or the 2026 LPG crisis). Not found in any source consulted.

**Method-level constraint that shaped every gap above:** this session's WebSearch tool was exhausted (0 of 200 remaining) before this task began, per the brief's warning. All research after that point relied on WebFetch — against publisher sites directly (frequently blocked by JavaScript-rendering, e.g. Eternal's and Swiggy's investor-relations pages, or by 403s, e.g. medianama.com's search) and, as a substitute for search, Google News' RSS endpoint (`news.google.com/rss/search?q=...`), which reliably returned real headlines, publishers and dates but whose individual article links are JavaScript-redirect wrappers that WebFetch could not resolve to the underlying publisher URL. As a result, most [summary] citations in this file are sourced to a **headline, publisher name, and date** rather than to a directly-read article body or a working URL — this is weaker sourcing than the brief's ideal, and is flagged here rather than papered over. Bing and DuckDuckGo web search (attempted as substitutes) returned generic/navigational results not responsive to specific queries and a bot-CAPTCHA respectively, and were abandoned as unproductive.

---

## Sources

**Fetched directly (WebFetch, full or partial content read):**
- NRAI — https://nrai.org and https://nrai.org/NRAI_Food_Summit/About_Nrai.aspx (membership/industry-size claims) [primary]
- NRAI — https://nrai.org/BookYourCopy.aspx (IFSR report purchase page — no figures exposed) [primary, no data]
- IBEF — https://www.ibef.org/industry/food-processing and https://www.ibef.org/industry/services (checked, no restaurant/food-service-specific figures found)
- Invest India — https://www.investindia.gov.in/sector/food-processing (checked, no restaurant/food-service-specific figures found)
- Wikipedia — https://en.wikipedia.org/wiki/Zomato and https://en.wikipedia.org/wiki/Swiggy (revenue, city-coverage, Swiggy–Kearney $125B/2030 citation)

**Identified via Google News RSS (`news.google.com/rss/search`), headline + publisher + date used as citation; underlying article URLs did not resolve through WebFetch — see Gaps for this constraint:**
- Business Standard, BusinessLine, Hospitality Biz India — NRAI IFSR 2024 launch coverage, 2024-07-09/10/12/15
- The Times of India — Goa ranking, Hyderabad "largest market" headline, Covid closure-rate study, LPG-crisis Pune coverage, multiple FSSAI enforcement stories
- The Hindu — Hyderabad ₹5 lakh crore figure (2024-07-11), FSSAI licence-lifetime-validity reform (2026-04-06), "1 in 15" FSSAI registration figure (2016-02-10)
- The New Indian Express — Hyderabad 2022 figure
- Food & Beverage News — NRAI IFSR '19 Mumbai figure (2019-06-14), IFSR 2016 launch
- YourStory — Swiggy 2019 restaurant-partner count and unorganised-street-food $41B estimate
- The Economic Times — Bain–Swiggy delivery-market projection (2024-07-03), UPI/restaurant payments (2025-10-24), FSSAI perpetual-licence reform (2026-03-13), $50B/FY31 food-services projection (2026-07-09), 73% MSME digital-adoption survey (2025-06-28)
- Fortune India — Swiggy FY31 GOV/EBITDA target (2026-08-06)
- medianama.com — Swiggy Q4 FY26 GOV (2026-05-11)
- The Indian Express — $79.65B/2028 projection (2022-11-21), Pune LPG-crisis coverage (2026-03)
- The News Minute — >$100B/2028 projection (2024-02-15)
- BW Businessworld — $150B/2030 projection (2026-07-10)
- entrepreneurindia.com — Swiggy–Kearney $125B/2030 (2025-12-01)
- Indian Retailer — 74% digital-payments-of-retail-spend figure (2025-10-04)
- openPR.com — India Cloud Kitchen Market $3,211.7M/2033 estimate (2026-01-22)
- precedenceresearch.com — global cloud kitchen market $248.10B/2035 estimate (2022-03-28)
- Livemint, Deccan Herald, DD News, storyboard18.com — FSSAI 2026 licensing-reform coverage
- NDTV — Rapido lower-commission entry (2025-06-09); Entrackr — Swiggy ~25% commission-cap discourse (~2019)
- DNA India, ET Retail — FICCI-Technopak ₹5.5 lakh crore/2022 projection (2017-11)

**Attempted, blocked, or unproductive (recorded per Method):**
- WebSearch — exhausted (0/200 remaining) before this task began
- Bing web search via WebFetch — returned generic/navigational results not responsive to specific quoted queries
- DuckDuckGo (both `duckduckgo.com/html` and `lite.duckduckgo.com`) — CAPTCHA-blocked
- Google web search via WebFetch — returned an error/interstitial page
- Marginalia Search — returned help/policy page, not results
- eternal.com/investor-relations, moments.swiggy.com/investors — JavaScript-rendered, no static content retrievable
- medianama.com site search — HTTP 403
- chittorgarh.com (Swiggy IPO/DRHP aggregator) — HTTP 403
- redseer.com/reports — fetched; no matching India food-service report visible on the page at time of fetch
- statista.com topic page for India foodservice — URL did not resolve to the intended topic page
- npci.org.in UPI product-statistics page — JavaScript-rendered, no static figures retrievable
