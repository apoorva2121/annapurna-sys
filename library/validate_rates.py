"""Validate the market-rate table and the city index. Runs in `make check` (audit-docs).

`market-rates.yaml` is the only file in `library/` that carries a price, and it exists because
`docs/onboarding-cold-start.md` promises one: "Prices bootstrap from a market-rate table by city,
then correct on first real purchase." Everything here defends four properties of that table, and
each rule exists because an audit found the absence of it.

**Provenance.** A price with no retrievable source is a guess wearing a citation's clothes, which
is worse than an obvious guess: the guess gets corrected and the citation gets believed. The tier a
row claims must be what its `sources` can support — in both directions, so an `estimated` row
holding a URL is an error too.

**Unit sanity.** The likeliest error is an Indian mandi price quoted per QUINTAL (100 kg) read as
per-kg — 100x, and it looks plausible in a column of numbers. `seed/ingredients.yaml` prices 61 of
these codes by hand, passes the golden food-cost tests, and never saw the research, so it is an
independent anchor. Comparison is made on Pune-normalised values, because a row's price is quoted
in its own `basis_city` and comparing a Mumbai price to a Pune anchor would measure geography.

**Freshness.** `as_of` (when the price was published) is a different fact from `retrieved` (when we
fetched it). Twenty rows once carried a fresh fetch date over evidence up to seven months old, so
staleness is now measured against `as_of` and a page that gave no date is marked, not quietly
filled.

**Product identity.** `grade` is required and non-empty. A price without a product form is
ambiguous — cardamom ranges 1.68x by pod size alone, and one row was briefly priced off COSMETIC
rose water for an ingredient people eat.

    python library/validate_rates.py                     # validate; fail if provenance is stale
    python library/validate_rates.py --write-provenance  # validate and rewrite PRICE_PROVENANCE.md
"""
import os
import re
import sys
from datetime import date
from decimal import Decimal as D

import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(os.path.dirname(BASE), "seed")

TIERS = ("corroborated", "sourced", "estimated")
# How many distinct source NAMES each tier requires. Two listings on one platform are one source:
# Hyperpure quoting six paneer brands is one opinion about paneer, not six, because Hyperpure sets
# all six prices.
#
# A MARKETPLACE is the exception, and the distinction is about who sets the price rather than what
# the domain is. IndiaMART is a directory of independent sellers, so a Pune mandi trader and a
# Delhi wholesaler quoting urad dal separately really are two quotes. Those are named for the
# seller or city (`indiamart-pune`, `indiamart-delhi`) rather than the domain, which is simply the
# more accurate name — the `observed` string has to actually identify the two, or the row belongs
# at `sourced`. The rule stays mechanical on purpose: it counts names, and the naming carries the
# judgement where a human can see and argue with it.
MIN_SOURCES = {"corroborated": 2, "sourced": 1, "estimated": 0}

# The only legal Indian GST rates. Never interpolate — a rate is set by schedule, not derived.
GST_RATES = {0, 5, 12, 18, 28}

# Seed cross-check thresholds. The error threshold is derived from the *taxonomy of unit errors*
# rather than picked round, because that is the only thing it should be catching.
#
# Unit mistakes are large and quantised: quintal-as-kg is 100x, kg-as-g is 1000x, a 50 kg bag read
# as a kg is 50x, NECC's per-100-eggs is 100x, a dozen read as a unit is 12x. The SMALLEST
# plausible unit error is therefore about 12x.
#
# Genuine content disagreements are much smaller and they are real: the research found bulk-trade
# masala running 2-5x under branded-retail masala for the same nominal spice, and which a
# restaurant buys is a question about the restaurant, not an error in either number. An earlier
# draft failed the build at 5x and would have rejected a correct, well-sourced figure.
#
# 10x sits in the empty gap between the two populations. Note the asymmetry that matters: `seed/`
# holds the OLDER number, so a large gap is at least as likely to be seed's fault. A validator that
# forced the research to match seed would only assert seed is right, which is the one thing the
# cross-check exists to test.
SEED_ERROR_RATIO = D(10)
SEED_WARN_RATIO = D("1.6")

# Freshness, measured on `as_of`. 90 days is roughly a season: Indian produce and pulses move
# enough in a quarter that an older quote is a different market. A year is not a price at all.
STALE_WARN_DAYS = 90
STALE_ERROR_DAYS = 365

errors: list[str] = []
warnings: list[str] = []


def ascii_safe(text):
    """Messages quote `observed`, which carries rupee signs straight off the source pages.

    Windows consoles default to cp1252 and raise UnicodeEncodeError on U+20B9, so printing a
    finding would crash the validator *instead of reporting it* — the failure mode where the tool
    that exists to catch problems is taken out by the problem it caught. `scripts/audit_docs.py`
    solves it the same way.
    """
    return str(text).encode("ascii", "replace").decode()


def err(msg):
    errors.append(ascii_safe(msg))


def warn(msg):
    warnings.append(ascii_safe(msg))


def _load(folder, name):
    with open(os.path.join(folder, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


lib_ing = {i["code"]: i for i in _load(BASE, "ingredients.yaml")["ingredients"]}
seed_ing = {i["code"]: i for i in _load(SEED, "ingredients.yaml")["ingredients"]}
rates_doc = _load(BASE, "market-rates.yaml")
rates = {r["code"]: r for r in rates_doc["rates"]}
cities_doc = _load(BASE, "city-index.yaml")
meta = rates_doc["meta"]
cities = {c["code"]: c for c in cities_doc["cities"]}
researched_on = meta["researched_on"]

# `NATIONAL` is a legal basis: a nationwide modal price is a real thing to have sourced. It carries
# multiplier 1.00, the same as the baseline, because a national average is not a city premium.
BASIS_CITIES = set(cities) | {"NATIONAL"}


def multiplier(city):
    return D(str(cities[city]["multiplier"])) if city in cities else D(1)


# ---------------------------------------------------------------- coverage

_dupes = [r["code"] for r in rates_doc["rates"]]
for code in {c for c in _dupes if _dupes.count(c) > 1}:
    err("rate %s: duplicate code" % code)

for code in sorted(set(lib_ing) - set(rates)):
    err("ingredient %s: has no market rate. Every library ingredient needs one, or onboarding "
        "hands the restaurant an empty price field" % code)

for code in sorted(set(rates) - set(lib_ing)):
    err("rate %s: no such ingredient in library/ingredients.yaml" % code)

# ---------------------------------------------------------------- each row

URL_RE = re.compile(r"^https://")
HSN_RE = re.compile(r"^\d{4,8}$")
stale_rows = []
gst_missing: list[str] = []

for code, row in sorted(rates.items()):
    tier = row.get("tier")
    if tier not in TIERS:
        err("rate %s: tier %r is not one of %s" % (code, tier, ", ".join(TIERS)))
        continue

    price = row.get("inr_per_base_unit")
    if not isinstance(price, (int, float)) or price <= 0:
        err("rate %s: inr_per_base_unit %r must be a positive number" % (code, price))

    basis = row.get("basis_city")
    if basis not in BASIS_CITIES:
        err("rate %s: basis_city %r is not a city in city-index.yaml (or NATIONAL)"
            % (code, basis))

    # A price whose product form nobody stated cannot be checked, reproduced, or corrected by a
    # chef. This is the cheapest rule here and it closes the widest class of ambiguity.
    if not str(row.get("grade") or "").strip():
        err("rate %s: grade is required and must say what product form the price is for "
            "(powder vs whole, peeled vs unpeeled, food vs cosmetic grade)" % code)

    # `gst_rate: null` is a WARNING, not an error, and the distinction is deliberate. A restaurant
    # on the 5% no-ITC scheme bears input GST, so a price without it is not a landed cost — but the
    # rate is a legal fact that must be looked up, and a validator that hard-fails on an unsourced
    # lookup only tempts whoever is unblocking the build to invent one. Recording the gap keeps it
    # visible in PRICE_PROVENANCE.md without creating that pressure, exactly as `estimated` does
    # for a price with no citation.
    gst = row.get("gst_rate")
    if gst is None:
        gst_missing.append(code)
    elif gst not in GST_RATES:
        err("rate %s: gst_rate %r is not a legal Indian rate %s"
            % (code, gst, sorted(GST_RATES)))
    hsn = row.get("gst_hsn")
    if hsn is not None and not HSN_RE.match(str(hsn)):
        err("rate %s: gst_hsn %r must be 4-8 digits as a quoted string" % (code, hsn))

    tiers_list = row.get("pack_tiers") or []
    last = None
    for t in tiers_list:
        if not isinstance(t.get("qty_min"), (int, float)) or t["qty_min"] <= 0:
            err("rate %s: pack_tier qty_min %r must be positive" % (code, t.get("qty_min")))
        if not isinstance(t.get("inr"), (int, float)) or t["inr"] <= 0:
            err("rate %s: pack_tier inr %r must be positive" % (code, t.get("inr")))
        if last is not None and t.get("qty_min", 0) <= last:
            err("rate %s: pack_tiers must ascend by qty_min" % code)
        last = t.get("qty_min", 0)

    sources = row.get("sources") or []
    names = {s.get("name") for s in sources}

    if len(names) < MIN_SOURCES[tier]:
        err("rate %s: tier `%s` needs %d distinct source name(s), has %d. Two listings on one "
            "platform are one source" % (code, tier, MIN_SOURCES[tier], len(names)))

    # The rule in the other direction. A row holding a real citation but labelled `estimated` means
    # the tier was set by hand and never revisited — the citation is evidence it deserves more.
    if tier == "estimated" and sources:
        err("rate %s: tier `estimated` but carries %d source(s). Estimated means no citation — "
            "promote it to `sourced` or drop the sources" % (code, len(sources)))

    for i, s in enumerate(sources):
        where = "rate %s source[%d]" % (code, i)
        for field in ("name", "url", "retrieved", "as_of", "observed"):
            if not s.get(field):
                err("%s: missing %s" % (where, field))
        if s.get("url") and not URL_RE.match(str(s["url"])):
            err("%s: url must be https - got %r" % (where, s["url"]))
        for field in ("retrieved", "as_of"):
            if s.get(field) and not isinstance(s[field], date):
                err("%s: %s %r must be a YAML date, not a string" % (where, field, s[field]))
        if isinstance(s.get("as_of"), date) and isinstance(s.get("retrieved"), date):
            if s["as_of"] > s["retrieved"]:
                err("%s: as_of %s is after retrieved %s - a price cannot be published after it "
                    "was fetched" % (where, s["as_of"], s["retrieved"]))
            age = (researched_on - s["as_of"]).days
            if age >= STALE_ERROR_DAYS:
                err("%s: as_of %s is %d days before the research date. That is not a current "
                    "price" % (where, s["as_of"], age))
            elif age >= STALE_WARN_DAYS:
                stale_rows.append((code, s["as_of"], age))
        if s.get("city") and s["city"] not in BASIS_CITIES:
            err("%s: city %r is not in city-index.yaml (or NATIONAL)" % (where, s["city"]))
        # `observed` is the raw string as published, unit included. It is what makes the conversion
        # auditable: without it nobody can tell 3500 INR/quintal from 3500 INR/kg.
        if s.get("observed") and not re.search(r"\d", str(s["observed"])):
            err("%s: observed %r carries no number" % (where, s["observed"]))

    if tier != "estimated" and not str(row.get("note", "")).strip() and len(names) >= 2:
        warn("rate %s: two sources and no note. Say how they compared" % code)

for code, as_of, age in sorted(stale_rows, key=lambda r: -r[2]):
    warn("rate %s: priced as_of %s, %d days before the research date - re-scrape before trusting"
         % (code, as_of, age))

if gst_missing:
    warn("%d of %d rates have no gst_rate, so their landed cost is unknown: %s"
         % (len(gst_missing), len(rates), ", ".join(sorted(gst_missing)[:8])
            + (" ..." if len(gst_missing) > 8 else "")))

# ---------------------------------------------------------------- seed cross-check
#
# The part that earns its keep. Compared on PUNE-NORMALISED values: a row's price is quoted in its
# own basis_city, and `seed/` is Pune, so comparing raw values would measure geography rather than
# agreement.

crosschecked = []
for code in sorted(set(rates) & set(seed_ing)):
    seed_price = D(str(seed_ing[code]["price"]))
    row = rates[code]
    if seed_price <= 0 or not isinstance(row.get("inr_per_base_unit"), (int, float)):
        continue
    got = D(str(row["inr_per_base_unit"])) / multiplier(row.get("basis_city", "PUNE"))
    ratio = got / seed_price
    crosschecked.append((code, seed_price, got, ratio))
    flipped = ratio if ratio >= 1 else 1 / ratio
    if flipped >= SEED_ERROR_RATIO:
        err("rate %s: %s (Pune-normalised) vs seed %s is %.1fx apart. That is not market movement "
            "- check the unit (quintal = 100 kg, and a 50 kg bag is not a kg)"
            % (code, got.quantize(D("0.0001")), seed_price, flipped))
    elif flipped >= SEED_WARN_RATIO:
        warn("rate %s: %s vs seed %s (%.2fx). Either the market moved or the seed anchor is "
             "stale - worth a look" % (code, got.quantize(D("0.0001")), seed_price, flipped))

# ---------------------------------------------------------------- city index

baseline = cities_doc["meta"].get("baseline_city")
if baseline not in cities:
    err("city-index: baseline_city %r is not in the cities list" % baseline)
elif D(str(cities[baseline]["multiplier"])) != D(1):
    err("city-index: baseline city %s must have multiplier 1.00, has %s"
        % (baseline, cities[baseline]["multiplier"]))

if not cities_doc["meta"].get("unknown_city_multiplier"):
    err("city-index: meta.unknown_city_multiplier is required. A city nobody researched must fall "
        "back to the baseline, never to nothing")

for code, c in sorted(cities.items()):
    m = c.get("multiplier")
    if not isinstance(m, (int, float)) or m <= 0:
        err("city %s: multiplier %r must be a positive number" % (code, m))
    elif not D("0.5") <= D(str(m)) <= D(2):
        err("city %s: multiplier %s is outside 0.5-2.0. Indian metro-to-tier-2 food spread does "
            "not reach that; suspect the derivation" % (code, m))

for i, ex in enumerate(cities_doc.get("exceptions") or []):
    if ex.get("code") not in lib_ing:
        err("city-index exception[%d]: %r is not a library ingredient" % (i, ex.get("code")))
    for city in ex.get("applies_to") or []:
        if city not in cities:
            err("city-index exception[%d]: unknown city %r" % (i, city))

# ---------------------------------------------------------------- provenance


def _counts(field, keys):
    return {k: sum(1 for r in rates.values() if r.get(field) == k) for k in keys}


def provenance_text():
    total = len(rates)
    counts = _counts("tier", TIERS)
    gst_counts = _counts("gst_rate", sorted(GST_RATES))
    n_defaulted = sum(1 for r in rates.values()
                      for s in (r.get("sources") or []) if s.get("as_of_defaulted"))
    n_sources = sum(len(r.get("sources") or []) for r in rates.values())
    non_pune = sorted(c for c, r in rates.items() if r.get("basis_city") != "PUNE")
    lines = [
        "# Price provenance",
        "",
        "Generated by `library/validate_rates.py --write-provenance`. Do not edit by hand; the",
        "validator fails when this file is stale.",
        "",
        "The honest reading: `corroborated` rows were found in two independent places that agreed.",
        "`sourced` rows rest on one citation, or on two that disagreed - the note says which.",
        "`estimated` rows are domain knowledge with no retrievable source, and are marked so the",
        "onboarding flow can say as much to the restaurant.",
        "",
        "## Tiers - %d rates" % total,
        "",
        "| Tier | Count | Share |",
        "|---|---|---|",
    ]
    for t in TIERS:
        share = (D(counts[t]) / D(total) * 100).quantize(D("0.1")) if total else D(0)
        lines.append("| `%s` | %d | %s%% |" % (t, counts[t], share))
    lines += [
        "",
        "## Input GST",
        "",
        "A restaurant on the 5% no-ITC scheme bears input GST, so landed cost is",
        "`inr_per_base_unit * (1 + gst_rate/100)` and the quoted price is not the cost.",
        "",
        "| Rate | Count |",
        "|---|---|",
    ]
    for k in sorted(GST_RATES):
        lines.append("| %d%% | %d |" % (k, gst_counts[k]))
    lines += [
        "",
        "## Freshness",
        "",
        "`as_of` is when the price was published; `retrieved` is when it was fetched.",
        "",
        "- %d source citations across %d rates" % (n_sources, total),
        "- %d carry no published date and fall back to the fetch date (`as_of_defaulted`)"
        % n_defaulted,
        "- %d are more than %d days older than the research date" % (len(stale_rows),
                                                                    STALE_WARN_DAYS),
        "",
        "## Price basis",
        "",
        "A row's value is quoted in its own `basis_city`. Converting to a target city is a ratio:",
        "`value * cities[target] / cities[basis_city]` - multiplying a Mumbai value by Mumbai's",
        "multiplier would apply geography twice.",
        "",
        "- %d of %d rows are priced on a non-Pune basis%s"
        % (len(non_pune), total, (": " + ", ".join("`%s`" % c for c in non_pune))
           if non_pune else ""),
        "",
        "## Seed cross-check - %d shared codes" % len(crosschecked),
        "",
        "`seed/ingredients.yaml` prices were set by hand for Pune and pass the golden food-cost",
        "tests. The research never saw them, so agreement here is independent evidence. Values are",
        "Pune-normalised; ratios are researched / seed.",
        "",
        "| Code | Seed | Researched (Pune) | Ratio |",
        "|---|---|---|---|",
    ]
    for code, seed_price, got, ratio in sorted(crosschecked, key=lambda r: -abs(r[3] - 1)):
        lines.append("| `%s` | %s | %s | %s |"
                     % (code, seed_price, got.quantize(D("0.0001")), ratio.quantize(D("0.01"))))
    lines += [
        "",
        "## Cities - %d" % len(cities),
        "",
        "Multipliers against the %s baseline, derived by %s on %s."
        % (baseline, cities_doc["meta"].get("basis"), cities_doc["meta"].get("derived_on")),
        "An unlisted city falls back to %s." % cities_doc["meta"].get("unknown_city_multiplier"),
        "",
        "| City | Multiplier |",
        "|---|---|",
    ]
    for code, c in sorted(cities.items(), key=lambda kv: -kv[1]["multiplier"]):
        lines.append("| `%s` | %s |" % (code, c["multiplier"]))
    lines.append("")
    return "\n".join(lines)


if errors:
    print("MARKET RATE VALIDATION ERRORS:")
    for e in errors:
        print("  -", e)
    sys.exit(1)

prov_path = os.path.join(BASE, "PRICE_PROVENANCE.md")
text = provenance_text()
if "--write-provenance" in sys.argv:
    with open(prov_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("wrote PRICE_PROVENANCE.md")
else:
    current = open(prov_path, encoding="utf-8").read() if os.path.exists(prov_path) else ""
    if current != text:
        print("MARKET RATE VALIDATION ERRORS:")
        print("  - PRICE_PROVENANCE.md is stale. Run: "
              "python library/validate_rates.py --write-provenance")
        sys.exit(1)

for w in warnings:
    print("warning:", w)

counts = _counts("tier", TIERS)
print("Market rates OK: %d rates, %d cities, %d cross-checked against seed"
      % (len(rates), len(cities), len(crosschecked)))
print("  tiers         " + "  ".join("%s=%d" % (t, counts[t]) for t in TIERS))
