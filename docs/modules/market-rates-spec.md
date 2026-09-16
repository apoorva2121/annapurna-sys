# Market rates — real ingredient prices, and where they may be trusted

**Status:** built 2026-09-12. Not a numbered module — a data-layer dependency that M04's cost
engine and the onboarding flow both already assumed existed.

## Why this exists

Two files had already specified it, and neither had anything behind it:

- `docs/onboarding-cold-start.md` § Solving entry — *"**Prices** — bootstrap from a market-rate
  table by city, then correct on first real purchase. Wrong-but-close prices on day one beat empty
  fields, as long as they are visibly marked estimated."*
- `library/ingredients.yaml:6` — *"There is NO price column. Prices are per-restaurant and
  bootstrap from a market-rate table."*

The table did not exist. Every `stock_item.current_unit_cost` outside the seeded demo was a guess,
which matters because the day-1 commercial pitch in the same cold-start doc — *"here are the eleven
dishes on your menu that lose money on every plate"* — is computed **entirely** from ingredient
price, before the restaurant has recorded a single purchase. That sentence is the product's first
meeting. Saying it from unmarked guesses is how you lose the room.

## The two-layer split

The single most important decision here, and the one everything else follows from.

| | Layer 1 · market rates | Layer 2 · per-restaurant demo data |
|---|---|---|
| Scope | shared across all restaurants | one restaurant each |
| Origin | **researched** from published sources | **generated** |
| Bar | external truth, with citations | internal coherence |
| Files | `library/market-rates.yaml`, `library/city-index.yaml` | `seed/` |

Research only ever applies to Layer 1. There is no external source for a restaurant's floor plan,
staff roster or table layout — nobody publishes those — so asking a research agent for them would
produce invention wearing a citation. Layer 2 is generated, marked `is_demo: true`, and its bar is
that every recipe line references a stock item that exists at a station that exists.

## What a rate row is

```yaml
- code: ONION
  inr_per_base_unit: 0.057
  basis_city: PUNE
  tier: corroborated
  grade: "Onion, big / medium, unpeeled, market grade"
  gst_rate: 0
  gst_hsn: "0703"
  pack_tiers:
    - {qty_min: 5, unit: kg, inr: 290}
  sources:
    - {name: todaypricerates, url: "https://…", retrieved: 2026-09-12, as_of: 2026-09-12, city: PUNE, observed: "Onion Big wholesale 56 INR/Kg"}
    - {name: hyperpure,       url: "https://…", retrieved: 2026-09-12, as_of: 2026-09-12, city: PUNE, observed: "Onion (Medium Size) 5 kg — 290 INR"}
  note: "56 vs 58 INR/kg — 3.6% apart."
```

Five of these fields exist because a data audit on 2026-09-12 found their absence. Each closes a
measured defect rather than a theoretical one.

**`observed` — the load-bearing field.** The raw string exactly as published, unit included, beside
the converted value. Without it the conversion is unauditable, and the likeliest error here is an
Indian mandi price quoted **per quintal (100 kg)** read as per-kg — a 100× error that looks
entirely plausible in a column of numbers.

**`basis_city` — because the file was not all one city.** 29% of rows rested on non-Pune evidence
while the header declared a Pune baseline, so the city index was about to multiply a Delhi price by
a Delhi factor and count geography twice. Conversion is therefore a **ratio**:

```
effective = inr_per_base_unit × cities[target] / cities[basis_city]
```

`NATIONAL` is a legal basis and carries 1.00 — a nationwide modal price is a real thing to have
sourced, and it is not a city premium.

**`as_of` vs `retrieved` — because a fetch date is not a price date.** All 176 citations were
stamped with the day they were fetched, while 20 rested on evidence up to **seven months** old
(one row on a February listing). `as_of` is when the price was published; `retrieved` is when we
looked. Where a page carries no date, `as_of_defaulted: true` records that we only know the latter
— which is different from knowing the price is current, and the validator counts them separately.

**`grade` — because a price without a product form is ambiguous.** Cardamom ranges **1.68×** by pod
size alone (5 mm ₹2,100 → 9 mm ₹3,525); the row had picked a number with no record of which. Worse,
one row was priced off **cosmetic-grade** rose water for an ingredient people eat. Required and
non-empty on every row.

**`gst_rate` / `gst_hsn` — because the quoted price is not the cost.** Zero rows carried any tax
treatment. India's standard restaurant rate is 5% **with no input tax credit**, so a restaurant on
it *bears* input GST rather than reclaiming it. Landed cost is `inr_per_base_unit × (1 +
gst_rate/100)`, and the error was 0–18% and systematic. Rates are restricted to the legal set
`{0, 5, 12, 18, 28}` — a rate is set by schedule, never interpolated.

`gst_rate: null` is a **warning, not an error**, and that is deliberate. The rate is a legal fact
that has to be looked up, and hard-failing the build on an unsourced lookup does not produce a
sourced one — it pressures whoever is unblocking the build into inventing a plausible number.
Recording the gap keeps it visible in `PRICE_PROVENANCE.md` without creating that incentive,
exactly as the `estimated` tier does for a price with no citation. **All 122 rows currently sit at
`null`**; sourcing them is the top outstanding item.

**`pack_tiers` — because bulk breaks were being discarded at parse time.** 18 rows had volume
pricing sitting in `observed` free text (`"₹571.9/kg for 5kg+, ₹583.9/kg for 3kg+"`) against a
schema with one scalar.

### Tiers

Mirrors `library/`'s existing `seed_calibrated` / `derived` / `estimated` model deliberately — one
integrity concept in this repo, not two.

| Tier | Earns it |
|---|---|
| `corroborated` | two **independent source names** agreeing within ±25% |
| `sourced` | one citation, **or** two that disagreed — the note says which |
| `estimated` | no retrievable source; domain knowledge only, `sources: []` |

Two listings on one platform are **one** source: Hyperpure quoting six paneer brands is one opinion
about paneer, not six. `validate_rates.py` enforces the rule in both directions — an `estimated`
row carrying a URL is an error, because it means somebody had a citation and mislabelled it
downward.

`estimated` is a permitted and expected outcome. Some ingredients (goda masala, khoya) have no
public price. An honest `estimated` beats a gap, and beats a fabricated citation by much more.

## Price basis: what a restaurant actually pays

Not retail, and not quick-commerce. The research targets **wholesale / trade** rates, because a
restaurant buying 50 kg of onions does not pay Blinkit prices. The spread is not small — onion
showed ₹56/kg wholesale against ₹62–73 retail on the same page, the same day.

The best single source found is **Hyperpure** (Zomato's B2B restaurant-supply arm): its prices
*are* restaurant wholesale by construction, which is exactly the question being asked. Where
Hyperpure and mandi data diverge beyond the corroboration bar, the value follows Hyperpure and the
mandi figure is kept in `sources` anyway.

That divergence is systematic and explainable: mandi leafy-herb prices are farm-gate bulk lots for
crops that wilt in three days, while a restaurant buys cleaned 100–500 g packs daily. Coriander
showed 6× between the two. Both numbers are real; they answer different questions.

## The city index

`market-rates.yaml` is the **Pune baseline**. `city-index.yaml` carries per-city multipliers.

Derived empirically, not guessed: a 13-commodity basket priced in 11 cities from one source on one
day, multiplier = **median** of the per-commodity ratios against Pune. Median rather than mean
because leafy greens travel badly and blow out the mean — spinach ranged 2.10× across those cities
while potato ranged 1.32×. One commodity should not set a city's multiplier.

Result: Mumbai 1.14 (island city, everything trucked in) down to Lucknow 0.79 (major producing
state). A real 1.45× spread end to end.

**An unlisted city falls back to 1.00**, never to nothing. A new city must never block onboarding.

Known-wrong cases are recorded in `exceptions` rather than silently applied — coastal cities land
seafood locally, so the vegetable-derived multiplier pushes Mumbai prawn the wrong way. Flagged,
not fixed, because no seafood city-comparison data was gathered.

## The seed cross-check

The part that earns its keep. `seed/ingredients.yaml` holds 61 overlapping codes priced by hand for
Pune, and those prices pass the golden ~26% food-cost tests. **The research never saw them.** So
they are an independent reality anchor, free of charge.

`validate_rates.py` compares every shared code, **fails** the build at 10× and **warns** at 1.6×.

The error threshold is derived from the taxonomy of unit errors rather than picked round, because
that is the only thing it should catch. Unit mistakes are large and quantised — quintal-as-kg is
100×, kg-as-g is 1000×, a 50 kg bag read as a kg is 50×, NECC's per-100-eggs is 100×, a dozen read
as a unit is 12×. The smallest plausible one is about 12×.

Genuine content disagreements are far smaller and they are legitimate: this research found
bulk-trade masala running 2–5× under branded-retail masala for the same nominal spice, and which a
restaurant actually buys is a question about the restaurant, not an error in either number. **An
earlier draft of this validator failed at 5× and would have rejected a correct, well-sourced
figure.** 10× sits in the empty gap — above every observed disagreement, below every possible unit
error.

The asymmetry matters too: `seed/` holds the *older* number, so a large gap is at least as likely to
be seed's fault as the research's. A validator that forced the research to match seed would only be
asserting seed is right, which is the one thing the cross-check exists to test.

The warn threshold is calibrated on real data: onion came back at 1.47× seed (and was mid-spike),
spring onion at 1.86× (a genuinely stale seed value).

Comparison is made on **Pune-normalised** values (`value / cities[basis_city]`), because `seed/` is
Pune and a row may be quoted elsewhere. Comparing raw values would measure geography and call it
disagreement.

## Freshness

Measured on `as_of`, never on `retrieved`:

| Age vs `researched_on` | Result |
|---|---|
| ≥ 365 days | **error** — that is not a price |
| ≥ 90 days | warning — re-scrape before trusting |

90 days is roughly a season, and Indian produce and pulses move enough in a quarter that an older
quote describes a different market. A source that publishes no date is not *assumed* fresh — it is
marked `as_of_defaulted` and counted in `PRICE_PROVENANCE.md`, so "undated" and "current" never
look the same.

An `as_of` later than its own `retrieved` is an error: a price cannot be published after it was
fetched, and that ordering catches transcription slips no range check would.

Independent confirmations worth recording: refined oil researched at ₹134.67/L against seed's
`0.135` — an exact match. Paneer researched across six Pune brands at ₹278–385/kg against seed's
₹360. The seed anchor is sound.

## Schema change

One column, `stock_item.cost_source` (migration `0014`), values `market_rate` / `manual` /
`purchase`, plus a partial index on the un-confirmed rows.

This is what makes "visibly marked estimated" real rather than aspirational — `current_unit_cost`
was a bare NUMERIC, so a bootstrapped national average and a number off this restaurant's own
supplier bill were the same column with the same authority.

**The default is `market_rate`, the least confident value, on purpose.** A price whose provenance
nobody set is a price nobody vouched for. Defaulting to `manual` would claim a human typed it. The
first failure mode is a guess that gets believed; the second is a real price that gets
double-checked. The default fails toward honesty.

`cost_source` sits on `PricedStockItemResponse`, not the base schema — it is a statement *about*
the price, and a chef who is not shown rupees has no use for where the rupees came from.

## Volatility, and what a baseline should not capture

Onion was mid-spike during this research: ₹35/kg on 6 Sep 2026, ₹56 on 12 Sep, on the same source.
A single-day snapshot of a volatile commodity is a poor baseline — it enshrines a moment.

Not solved here. The row carries the observation in its `note` so the next refresh can decide
between a snapshot and a trailing median. Recorded rather than quietly wrong.

## Out of scope

- **Live refresh / scheduling.** This is a static dataset, versioned in the repo, refreshed by
  re-running the research. No runtime dependency on a government site staying up.
- **Orders, stock movements, waste.** Those tables do not exist yet (M05+).
- **Supplier price history and trends** — M06.
- **Applying the city `exceptions`** — recorded, not implemented.

## Maintenance

```
python library/validate_rates.py                     # runs in make check (audit-docs)
python library/validate_rates.py --write-provenance  # after editing rates or cities
```

`PRICE_PROVENANCE.md` is generated and a stale one fails the build, exactly as `PROVENANCE.md`
does for the recipe library.

To refresh the prices, the order is:

```
# 1. research each category into a fragment YAML (rates: [...]), one file per category
python library/merge_rates.py --fragments <dir>      # assemble market-rates.yaml
python library/validate_rates.py --write-provenance  # validate + regenerate provenance
```

Fragments are working files and are not kept — every citation survives into `market-rates.yaml`,
which is the artifact. `merge_rates.py` is in the repo because the assembly step is the part that
does not survive re-typing: it writes `sources` as YAML *flow* mappings, and quoting them correctly
is less obvious than it looks (an unquoted value ends at the first comma, which silently truncated
23 `observed` fields in the first run).

The city index is derived separately — see `city-index.yaml`'s header for the basket and method.
Re-derive it from one source on one day, or the multiplier measures the calendar instead of the
city.
