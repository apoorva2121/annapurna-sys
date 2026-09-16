"""Assemble `library/market-rates.yaml` from research fragments, in layers.

This is the LAST step of a price refresh, not something `make check` runs:

    1. research into fragment YAMLs (`rates: [...]`), one file per category or per re-scrape bucket
    2. python library/merge_rates.py --fragments <dir>
    3. python library/validate_rates.py --write-provenance

**Layered on purpose — each concern has exactly one owner.** A price refresh does not re-research
everything; it re-researches what an audit flagged. So the merge composes:

    base      the last full research pass                 (rates-*.yaml)
    override  rows a re-scrape replaced outright          (rescrape-*.yaml)   by code
    overlay   fields added to rows nobody re-scraped      (backfill-*.yaml)   grade, basis_city
    overlay   tax, which is a legal lookup not a price    (gst-rates.yaml)    gst_rate, gst_hsn

Anything the layers do not supply is defaulted explicitly and visibly here rather than left absent,
because an absent field reads as "not applicable" and a defaulted one reads as "nobody has looked".
The two are very different and the validator treats them differently.

Emits YAML by hand rather than via `yaml.dump`, which reflows `sources` into multi-line blocks and
loses the one-line-per-source shape the file is meant to be read in. See `q()` for the quoting rule
and the bug that motivated it.

    python library/merge_rates.py --fragments /path/to/fragments
"""

import glob
import os
import re
import sys
from datetime import date

import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
if "--fragments" not in sys.argv:
    sys.exit("usage: python library/merge_rates.py --fragments <dir>")
SRC = sys.argv[sys.argv.index("--fragments") + 1]

CATEGORY_ORDER = ["meat", "dairy", "veg", "grain", "spice", "oil", "bakery", "sweet"]

lib_text = open(os.path.join(BASE, "ingredients.yaml"), encoding="utf-8").read()
cat_of = dict(re.findall(r"\{code:\s*([A-Z0-9_]+),.*?category:\s*(\w+)\}", lib_text))


def load(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def globbed(pattern):
    return sorted(glob.glob(os.path.join(SRC, pattern)))


# ---------------------------------------------------------------- layers

rows = {}
for path in globbed("rates-*.yaml"):
    for r in load(path)["rates"]:
        if r["code"] in rows:
            sys.exit("duplicate code across base fragments: %s" % r["code"])
        rows[r["code"]] = r

rescraped = set()
for path in globbed("rescrape-*.yaml"):
    for r in load(path)["rates"]:
        if r["code"] in rescraped:
            sys.exit("duplicate code across rescrape fragments: %s" % r["code"])
        rescraped.add(r["code"])
        rows[r["code"]] = r

backfilled = 0
for path in globbed("backfill-*.yaml"):
    for b in load(path)["rows"]:
        r = rows.get(b["code"])
        if r is None:
            sys.exit("backfill names unknown code: %s" % b["code"])
        if b["code"] in rescraped:
            sys.exit("backfill collides with a re-scraped row: %s" % b["code"])
        for k, v in b.items():
            if k == "code":
                continue
            # `note_extra` appends rather than replaces: the original note carries how the sources
            # compared, and an audit finding is an addition to that, not a correction of it.
            if k == "note_extra":
                r["note"] = (str(r.get("note") or "").strip() + " " + v).strip()
            else:
                r[k] = v
        backfilled += 1

gst_seen = 0
for path in globbed("gst-*.yaml"):
    for g in load(path)["gst"]:
        r = rows.get(g["code"])
        if r is None:
            sys.exit("gst names unknown code: %s" % g["code"])
        r["gst_rate"] = g["gst_rate"]
        r["gst_hsn"] = g.get("gst_hsn")
        r["gst_assumption"] = g.get("assumption")
        r["gst_source"] = g.get("source")
        gst_seen += 1

missing = sorted(set(cat_of) - set(rows))
extra = sorted(set(rows) - set(cat_of))
if missing or extra:
    sys.exit("coverage mismatch.\n  missing: %s\n  extra: %s" % (missing, extra))

# ---------------------------------------------------------------- explicit defaults
#
# A source written before `as_of`/`city` existed carries neither. Defaulting `as_of` to `retrieved`
# is the only honest choice available — it says "the page gave no date, so all we know is when we
# looked" — but it must be recorded as a default rather than silently filled, or a reader cannot
# tell a dated price from an undated one. `validate_rates.py` counts these.

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
_DATE_PATTERNS = (
    re.compile(rf"(\d{{1,2}})\s+({_MON})\s+(\d{{4}})", re.I),           # 20 May 2026
    re.compile(rf"({_MON})\s+(\d{{1,2}}),\s*(\d{{4}})", re.I),          # September 10, 2026
    re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"),                          # 09/09/2026
)
_MONTH_ONLY = re.compile(rf"({_MON})\s+(\d{{4}})", re.I)


def dates_in(text):
    """Every date stated inside an `observed` string, as (y, m, d) tuples.

    The dates are already there — "mandi rate of ajwain 11298 INR/quintal (20 May 2026)" — they
    simply had no field to live in, which is how 20 rows came to carry a fresh fetch date over
    months-old evidence. Reading them back out is transcription, not new sourcing.
    """
    found = []
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(text):
            a, b, c = m.groups()
            try:
                if pat is _DATE_PATTERNS[0]:
                    found.append(date(int(c), _MONTHS[b.lower()[:3]], int(a)))
                elif pat is _DATE_PATTERNS[1]:
                    found.append(date(int(c), _MONTHS[a.lower()[:3]], int(b)))
                else:
                    found.append(date(int(c), int(b), int(a)))
            except (ValueError, KeyError):
                pass
    if not found:
        # Month-only ("Sep 2026") resolves to the 1st. Conservative on purpose: it can only make a
        # price look older, and a price wrongly flagged stale gets checked while one wrongly
        # flagged fresh gets believed.
        for m in _MONTH_ONLY.finditer(text):
            try:
                found.append(date(int(m.group(2)), _MONTHS[m.group(1).lower()[:3]], 1))
            except (ValueError, KeyError):
                pass
    return found


defaulted_as_of = 0
extracted_as_of = 0
for code, r in rows.items():
    r.setdefault("basis_city", "PUNE")
    for s in r.get("sources") or []:
        if not s.get("as_of"):
            # Earliest date found, not latest. A source entry often quotes several listings; the
            # composite price is at best as fresh as its oldest component, so the earliest is the
            # defensible reading.
            found = [d for d in dates_in(str(s.get("observed", ""))) if d <= s["retrieved"]]
            if found:
                s["as_of"] = min(found)
                extracted_as_of += 1
            else:
                s["as_of"] = s["retrieved"]
                s["as_of_defaulted"] = True
                defaulted_as_of += 1
        s.setdefault("city", r["basis_city"])


def q(v):
    """Always double-quote a scalar destined for a YAML FLOW mapping.

    The first version quoted only on `:` `#` `"` `'` or newline — the block-context rules. Sources
    go out as flow mappings (`{name: x, observed: y}`), where `,` `{` `}` `[` `]` are ALSO
    terminators, and `observed` values look like:

        Amul - Butter Salted, 500 gm - 617.40/kg

    No colon, no hash, so it went out bare and YAML ended the value at the first comma. Every
    `observed` field silently lost everything after it, including the price. The data was never
    wrong; the writer was. Quoting unconditionally costs nothing and removes the whole class.
    """
    return '"%s"' % str(v).replace("\\", "\\\\").replace('"', '\\"')


HEADER = '''# Market rates — INR per base unit, PUNE baseline, researched 2026-09-12.
#
# `docs/onboarding-cold-start.md` promises a restaurant's prices "bootstrap from a market-rate
# table by city, then correct on first real purchase". This is that table. It is the ONLY file in
# library/ carrying a price — `ingredients.yaml` deliberately has none, because a price is
# per-restaurant and these are a starting point a chef corrects.
#
# EFFECTIVE PRICE. A row's value is the price level of its OWN `basis_city`, which is not always
# Pune. Converting to a target city is therefore a ratio, not a multiplication:
#
#     effective = inr_per_base_unit * cities[target].multiplier / cities[basis_city].multiplier
#
# Multiplying a Mumbai-sourced value by Mumbai's multiplier would apply geography twice. An audit
# found 29% of rows resting on non-Pune evidence in a file that declared a Pune baseline, and
# `basis_city` is what makes that arithmetic honest instead of silently wrong.
#
# BASIS: wholesale / trade — what a restaurant buying in bulk pays. NOT retail, NOT quick-commerce.
# The gap is not small: onion showed 56 INR/kg wholesale against 62-73 retail on one page one day.
#
# `observed` holds the raw string exactly as published, unit included, so the conversion can be
# audited. The likeliest error here is a mandi price quoted per QUINTAL (100 kg) read as per-kg —
# a 100x mistake that looks plausible in a column of numbers.
#
# `as_of` is when the PRICE was published; `retrieved` is when we fetched it. They are different
# fields because 20 rows once carried a fresh fetch date over evidence up to seven months old.
# Where a page gave no date, `as_of_defaulted: true` marks that we only know when we looked.
#
# `grade` names the product form the price is for — powder vs whole, peeled vs unpeeled, food vs
# cosmetic grade, pod size. A price without a grade is ambiguous: cardamom alone ranges 1.68x by
# pod size, and one row was briefly priced off COSMETIC rose water for a food ingredient.
#
# `gst_rate` / `gst_hsn` carry input tax. A restaurant on the 5% no-ITC scheme BEARS this, so the
# landed cost is `inr_per_base_unit * (1 + gst_rate/100)` — the quoted price is not the cost.
#
# TIERS — no row may claim more certainty than it has:
#   corroborated  two independent source NAMES agreeing within +/-25%
#   sourced       one citation, or two that disagreed — the note says which
#   estimated     no retrievable source; domain knowledge only, sources: []
# Two listings on one platform are ONE source. A marketplace of independent sellers (IndiaMART) is
# the exception and those are named for the seller or city, not the domain.
#
# A CAVEAT ON `veg`: much of it is a single daily snapshot of the most volatile category here, and
# that source has been wrong once — it quoted mint at 7 INR/kg where every other source said 34-67,
# caught by the seed cross-check at 15.7x. Onion is the live example: 35 INR/kg on 6 Sep, 56 on 12.
#
# Regenerate after editing:  python library/validate_rates.py --write-provenance

meta:
  currency: INR
  baseline_city: PUNE
  researched_on: 2026-09-12
  basis: wholesale
'''

out = [HEADER, "rates:"]
for cat in CATEGORY_ORDER:
    codes = sorted(c for c in rows if cat_of.get(c) == cat)
    if not codes:
        continue
    out.append("")
    out.append("  # ---------------------------------------------------------------- %s (%d)"
               % (cat, len(codes)))
    for code in codes:
        r = rows[code]
        out.append("")
        out.append("  - code: %s" % code)
        out.append("    inr_per_base_unit: %s" % r["inr_per_base_unit"])
        out.append("    basis_city: %s" % r["basis_city"])
        out.append("    tier: %s" % r["tier"])
        out.append("    grade: %s" % q(r.get("grade") or ""))
        gst = r.get("gst_rate")
        out.append("    gst_rate: %s" % ("null" if gst is None else gst))
        out.append("    gst_hsn: %s" % (q(r["gst_hsn"]) if r.get("gst_hsn") else "null"))
        if r.get("gst_assumption"):
            out.append("    gst_assumption: %s" % q(r["gst_assumption"]))
        if r.get("gst_source"):
            s = r["gst_source"]
            out.append("    gst_source: {name: %s, url: %s, retrieved: %s, observed: %s}"
                       % (q(s["name"]), q(s["url"]), s["retrieved"], q(s.get("observed", ""))))
        for t in r.get("pack_tiers") or []:
            if t is r["pack_tiers"][0]:
                out.append("    pack_tiers:")
            out.append("      - {qty_min: %s, unit: %s, inr: %s}"
                       % (t["qty_min"], t["unit"], t["inr"]))
        srcs = r.get("sources") or []
        if srcs:
            out.append("    sources:")
            for s in srcs:
                extra_flag = ", as_of_defaulted: true" if s.get("as_of_defaulted") else ""
                out.append("      - {name: %s, url: %s, retrieved: %s, as_of: %s, city: %s%s, "
                           "observed: %s}"
                           % (q(s["name"]), q(s["url"]), s["retrieved"], s["as_of"],
                              s.get("city", r["basis_city"]), extra_flag, q(s["observed"])))
        else:
            out.append("    sources: []")
        out.append("    note: %s" % q(str(r.get("note") or "")))

out.append("")
dest = os.path.join(BASE, "market-rates.yaml")
with open(dest, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(out))

by_tier = {}
for r in rows.values():
    by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + 1
non_pune = sum(1 for r in rows.values() if r["basis_city"] != "PUNE")
print("wrote %s - %d rates" % (dest, len(rows)))
print("  " + "  ".join("%s=%d" % (t, by_tier.get(t, 0))
                       for t in ("corroborated", "sourced", "estimated")))
print("  re-scraped=%d  backfilled=%d  gst=%d  non-Pune basis=%d"
      % (len(rescraped), backfilled, gst_seen, non_pune))
print("  as_of: %d extracted from observed text, %d defaulted to the fetch date"
      % (extracted_as_of, defaulted_as_of))
