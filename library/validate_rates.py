"""Validate the market-rate table and the city index. Runs in `make check` (audit-docs).

`market-rates.yaml` is the only file in `library/` that carries a price, and it exists because
`docs/onboarding-cold-start.md` promises one: "Prices bootstrap from a market-rate table by city,
then correct on first real purchase." Everything here defends two properties of that table.

**Provenance.** A price with no retrievable source is a guess wearing a citation's clothes, and
that is worse than an obvious guess, because the guess gets corrected and the citation gets
believed. So the tier a row claims must be the tier its `sources` list can support:
`corroborated` needs two independent source NAMES, `sourced` needs one, and `estimated` must
carry none at all. The rule runs in that last direction too — an `estimated` row holding a URL is
an error, because it means somebody had a source and mislabelled it downward.

**Unit sanity.** The single most likely error in this dataset is an Indian mandi price quoted per
QUINTAL (100 kg) read as per-kg. That is a 100x error, and it looks entirely plausible sitting in
a column of numbers. Nothing in the YAML's shape catches it. What catches it is `seed/`: 61 of
these codes also appear there with a hand-set price that passes the golden ~26% food-cost tests,
so the seed file is an independent reality anchor that the research never saw. A researched price
more than SEED_ERROR_RATIO away from its seed twin fails the build.

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
# seller or city they come from (`indiamart-pune`, `indiamart-delhi`) rather than for the domain,
# which is simply the more accurate name — the `observed` string has to actually identify the two,
# or the row belongs at `sourced`. The rule stays mechanical on purpose: it counts names, and the
# naming carries the judgement where a human can see and argue with it.
MIN_SOURCES = {"corroborated": 2, "sourced": 1, "estimated": 0}

# Seed cross-check thresholds. The error threshold is derived from the *taxonomy of unit errors*
# rather than picked round, because that is the only thing it should be catching.
#
# Unit mistakes are large and quantised: quintal-as-kg is 100x, kg-as-g is 1000x, a 50 kg bag read
# as a kg is 50x, NECC's per-100-eggs is 100x, and a dozen read as a unit is 12x. The SMALLEST
# plausible unit error is therefore about 12x.
#
# Genuine content disagreements are much smaller and they are real: the 2026-09-12 research found
# bulk-trade masala running 2-5x under branded-retail masala for the same nominal spice, and which
# of those a restaurant actually buys is a question about the restaurant, not an error in either
# number. An earlier draft of this file failed the build at 5x and would have rejected a correct,
# well-sourced figure for exactly that reason.
#
# 10x sits in the empty gap between the two populations: above every observed content disagreement,
# below every possible unit error. Anything under it is a disagreement for a human to read in
# PRICE_PROVENANCE.md, not a reason to break the build — and note the asymmetry that matters, that
# `seed/` being the older number means a large gap is at least as likely to be seed's fault as the
# research's. A validator that forced the research to match seed would just be asserting seed is
# right, which is the one thing the cross-check is supposed to test.
SEED_ERROR_RATIO = D(10)
# WARN at 1.6x is calibrated on real data: just above the observed onion drift (researched 0.057 vs
# seed 0.038 = 1.47x, and onion was mid-spike) and just below spring onion (0.043 vs 0.080 =
# 1.86x), which genuinely is a stale seed value. The band separates "volatile but fine" from "look
# at this" on numbers that actually occurred.
SEED_WARN_RATIO = D("1.6")

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

for code, row in sorted(rates.items()):
    tier = row.get("tier")
    if tier not in TIERS:
        err("rate %s: tier %r is not one of %s" % (code, tier, ", ".join(TIERS)))
        continue

    price = row.get("inr_per_base_unit")
    if price is None:
        err("rate %s: no inr_per_base_unit" % code)
    elif not isinstance(price, (int, float)) or price <= 0:
        err("rate %s: inr_per_base_unit %r must be a positive number" % (code, price))

    sources = row.get("sources") or []
    names = {s.get("name") for s in sources}

    if len(names) < MIN_SOURCES[tier]:
        err("rate %s: tier `%s` needs %d distinct source name(s), has %d. Two listings on one "
            "platform are one source" % (code, tier, MIN_SOURCES[tier], len(names)))

    # The rule in the other direction. A row holding a real citation but labelled `estimated` means
    # the tier was set by hand and never revisited — the citation is the evidence it deserves more.
    if tier == "estimated" and sources:
        err("rate %s: tier `estimated` but carries %d source(s). Estimated means no citation — "
            "promote it to `sourced` or drop the sources" % (code, len(sources)))

    for i, s in enumerate(sources):
        where = "rate %s source[%d]" % (code, i)
        for field in ("name", "url", "retrieved", "observed"):
            if not s.get(field):
                err("%s: missing %s" % (where, field))
        if s.get("url") and not URL_RE.match(str(s["url"])):
            err("%s: url must be https — got %r" % (where, s["url"]))
        if s.get("retrieved") and not isinstance(s["retrieved"], date):
            err("%s: retrieved %r must be a YAML date, not a string" % (where, s["retrieved"]))
        # `observed` is the raw string as the source published it, unit included. It is what makes
        # the conversion auditable: without it nobody can tell 3500 INR/quintal from 3500 INR/kg.
        if s.get("observed") and not re.search(r"\d", str(s["observed"])):
            err("%s: observed %r carries no number" % (where, s["observed"]))

    if tier != "estimated" and not str(row.get("note", "")).strip() and len(names) >= 2:
        warn("rate %s: two sources and no note. Say how they compared" % code)

# ---------------------------------------------------------------- seed cross-check
#
# The part that earns its keep. seed/ingredients.yaml was priced by hand for Pune and its numbers
# pass the golden food-cost tests; the research never saw it. Agreement is evidence both are
# right. Disagreement means one of them is wrong, and that is worth knowing loudly.

crosschecked = []
for code in sorted(set(rates) & set(seed_ing)):
    seed_price = D(str(seed_ing[code]["price"]))
    got = D(str(rates[code]["inr_per_base_unit"]))
    if seed_price <= 0:
        continue
    ratio = got / seed_price
    crosschecked.append((code, seed_price, got, ratio))
    flipped = ratio if ratio >= 1 else 1 / ratio
    if flipped >= SEED_ERROR_RATIO:
        err("rate %s: %s vs seed %s is %.1fx apart. That is not market movement — check the unit "
            "(quintal = 100 kg, and a 50 kg bag is not a kg)" % (code, got, seed_price, flipped))
    elif flipped >= SEED_WARN_RATIO:
        warn("rate %s: %s vs seed %s (%.2fx). Either the market moved or the seed anchor is "
             "stale - worth a look" % (code, got, seed_price, flipped))

# ---------------------------------------------------------------- city index

meta = cities_doc["meta"]
cities = {c["code"]: c for c in cities_doc["cities"]}
baseline = meta.get("baseline_city")

if baseline not in cities:
    err("city-index: baseline_city %r is not in the cities list" % baseline)
elif D(str(cities[baseline]["multiplier"])) != D(1):
    err("city-index: baseline city %s must have multiplier 1.00, has %s"
        % (baseline, cities[baseline]["multiplier"]))

if not meta.get("unknown_city_multiplier"):
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


def _counts():
    return {t: sum(1 for r in rates.values() if r.get("tier") == t) for t in TIERS}


def provenance_text():
    total = len(rates)
    counts = _counts()
    lines = [
        "# Price provenance",
        "",
        "Generated by `library/validate_rates.py --write-provenance`. Do not edit by hand; the",
        "validator fails when this file is stale.",
        "",
        "The honest reading: `corroborated` rows were found in two independent places that agreed.",
        "`sourced` rows rest on one citation, or on two that disagreed — the note says which.",
        "`estimated` rows are domain knowledge with no retrievable source, and are marked so the",
        "onboarding flow can say as much to the restaurant.",
        "",
        "## Tiers — %d rates" % total,
        "",
        "| Tier | Count | Share |",
        "|---|---|---|",
    ]
    for t in TIERS:
        share = (D(counts[t]) / D(total) * 100).quantize(D("0.1")) if total else D(0)
        lines.append("| `%s` | %d | %s%% |" % (t, counts[t], share))
    lines += [
        "",
        "## Seed cross-check — %d shared codes" % len(crosschecked),
        "",
        "`seed/ingredients.yaml` prices were set by hand for Pune and pass the golden food-cost",
        "tests. The research never saw them, so agreement here is independent evidence. Ratios are",
        "researched / seed.",
        "",
        "| Code | Seed | Researched | Ratio |",
        "|---|---|---|---|",
    ]
    for code, seed_price, got, ratio in sorted(crosschecked, key=lambda r: -abs(r[3] - 1)):
        lines.append("| `%s` | %s | %s | %s |" % (code, seed_price, got, ratio.quantize(D("0.01"))))
    lines += [
        "",
        "## Cities — %d" % len(cities),
        "",
        "Multipliers against the %s baseline, derived by %s on %s."
        % (baseline, meta.get("basis"), meta.get("derived_on")),
        "An unlisted city falls back to %s." % meta.get("unknown_city_multiplier"),
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

counts = _counts()
print("Market rates OK: %d rates, %d cities, %d cross-checked against seed"
      % (len(rates), len(cities), len(crosschecked)))
print("  tiers         " + "  ".join("%s=%d" % (t, counts[t]) for t in TIERS))
