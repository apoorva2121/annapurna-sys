# Onboarding & Cold Start

**The constraint:** independent Indian restaurants keep almost no records. No recipe book, no
ingredient master, no purchase history in a spreadsheet. Purchases are in a paper notebook or a
supplier's WhatsApp message. Nobody knows their food cost percentage; if asked, they guess, and the
guess is usually 8–10 points low.

This is not a data-import inconvenience. It is the **central product risk**, and it has two
consequences that shape everything:

1. **There is no history to analyse on day one.** Every feature that assumes 90 days of data — the
   forecast, the demand model, menu engineering, supplier price comparison — is worthless at
   signup. If the product is empty and useless in month one, the restaurant churns in month two.
2. **Getting data in is the hardest part of the product.** Recipe entry for a 120-item menu is
   genuinely days of a chef's time, and the chef does not want to do it. **This kills more
   restaurant software deployments than any bug ever will.**

Both are solvable, and solving them well is more defensible than any analytics feature — because
competitors have the same problem and mostly ignore it.

## Solving entry: the starter recipe library

Ship a curated library of standard Indian recipes with typical quantities: ~200 dishes across North
Indian, Chinese-Indian, South Indian, tandoor, biryani and breads, plus ~30 standard preparations
(makhani gravy, yellow gravy, white gravy, birista, tandoori marinade, boiled rice, dal base).

Onboarding then becomes: **match, don't create.**

> "Your menu has Butter Chicken. Here's a standard recipe. Your portion looks larger than standard
> — adjust the chicken from 250 g to 300 g?"

The chef corrects rather than composes, which takes minutes instead of days and produces better data
because correcting is a task people will actually do. A 120-item menu should onboard in **under two
hours**, and that number is a product requirement, not an aspiration.

Every correction the chef makes also improves the library for the next restaurant. That compounds.

**Built 2026-09-12 — `library/`.** 223 dishes / 242 variants, 36 preparations, 122 ingredients, in
the same YAML shape as `seed/` so M04 needs one loader. Every entry carries a confidence tier
(`seed_calibrated` / `derived` / `estimated`) and `library/PROVENANCE.md` states the fractions
honestly — most of it is `estimated`, which is the correct state for content a chef corrects.
`library/validate.py` runs in `make check` and asserts the overlap with `seed/` is identical.
The onboarding flow must surface the tier: an `estimated` recipe is a proposal, not a default.

## Solving entry: everything else

- **Menu** — photograph the printed menu, extract items and prices with an LLM, chef confirms.
  Never make anyone type 120 dish names.
- **Ingredients** — derived automatically from the matched recipes. Nobody builds an ingredient
  master by hand.
- **Prices** — bootstrap from a market-rate table by city, then correct on first real purchase.
  Wrong-but-close prices on day one beat empty fields, as long as they are visibly marked estimated.
- **Opening stock** — one physical count, guided, on the top ~40 ingredients by value. Ignore the
  long tail; it's 5% of value and 60% of the effort.
- **Purchases** — photograph the supplier bill or forward the WhatsApp message; extract lines with
  an LLM; store manager confirms. This is the daily habit the whole system depends on, so it must
  take under a minute.

## Solving emptiness: value on day one, from zero history

Sequence the product so each stage delivers something before the next has data:

| From | Available | Delivers |
|---|---|---|
| **Day 1** | Menu + recipes + prices | Theoretical food cost and margin **per dish** — most owners have never seen this. Instantly reveals items sold at a loss. |
| **Week 1** | + orders | Real sales mix, actual revenue by dish, peak-hour patterns |
| **Week 2** | + waste logs | Prep over-production, measured for the first time. Usually the first real rupee saving. |
| **Week 4** | + stock counts | Theoretical vs actual variance — the leakage number |
| **Month 3** | + history | Forecasting, prep sheets, supplier price trends, menu engineering |

The day-1 row matters most commercially. "Here are the eleven dishes on your menu that lose money on
every plate" needs zero history, lands in the first meeting, and is usually true.

**Design rule:** no screen may be empty-and-useless at signup. Every analytics view either works
from static recipe data, or states plainly what it needs and when it will light up — a countdown,
not a blank. See the empty-state rule in `docs/ui/conventions.md`.

## Never trust "no data" as a starting assumption

Restaurants have more data than they think, in awkward places: the existing POS export, the paper
purchase notebook, supplier WhatsApp threads, Swiggy/Zomato dashboards, the Udhaar/khata app.
Onboarding should ask about each. A Swiggy export alone can backfill months of dish-level demand.

## What this means for the build

- The starter recipe library is **content work, not code**, and can be built in parallel with
  everything. Start it early; it is the long pole.
- Onboarding is a **first-class module**, not an admin afterthought. Budget real design time.
- Bill/menu photo extraction is an LLM call, not an ML project — cheap to build, and it removes the
  largest single reason deployments fail.
- Everything above is why the seeded demo data in `docs/seed-data.md` matters: it is how we build and
  demo all of this before a single real restaurant exists.
