"""Assemble `library/market-rates.yaml` from per-category research fragments.

This is the LAST step of a price refresh, not something `make check` runs. The order is:

    1. research each category into a fragment YAML (`rates: [...]`, one file per category)
    2. python library/merge_rates.py --fragments <dir>
    3. python library/validate_rates.py --write-provenance

The fragments are working files and are not kept — every citation they carry survives into
`market-rates.yaml`, which is the artifact. What does not survive re-typing is this assembly step,
which is why it lives here rather than in a scratch directory.

Emits YAML by hand rather than via `yaml.dump`, because dump reflows the `sources` mappings into
multi-line blocks and loses the one-line-per-source shape the file is meant to be read in. See
`q()` for the quoting rule and the bug that motivated it.

    python library/merge_rates.py --fragments /path/to/fragments
"""

import os
import sys
import re
import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
if "--fragments" not in sys.argv:
    sys.exit("usage: python library/merge_rates.py --fragments <dir>")
SCRATCH = sys.argv[sys.argv.index("--fragments") + 1]
FRAGMENTS = (
    "rates-veg-oil.yaml",
    "rates-meat-dairy.yaml",
    "rates-spice.yaml",
    "rates-grain-bakery-sweet.yaml",
)
CATEGORY_ORDER = ["meat", "dairy", "veg", "grain", "spice", "oil", "bakery", "sweet"]

lib_text = open(os.path.join(BASE, "ingredients.yaml"), encoding="utf-8").read()
cat_of = dict(re.findall(r"\{code:\s*([A-Z0-9_]+),.*?category:\s*(\w+)\}", lib_text))
name_of = {c: n.strip() for c, n in re.findall(r"\{code:\s*([A-Z0-9_]+),\s*name:\s*([^,]+?),", lib_text)}

rows = {}
for frag in FRAGMENTS:
    path = os.path.join(SCRATCH, frag)
    if not os.path.exists(path):
        sys.exit("missing fragment: %s" % frag)
    for r in yaml.safe_load(open(path, encoding="utf-8"))["rates"]:
        if r["code"] in rows:
            sys.exit("duplicate code across fragments: %s" % r["code"])
        rows[r["code"]] = r

missing = sorted(set(cat_of) - set(rows))
extra = sorted(set(rows) - set(cat_of))
if missing or extra:
    sys.exit("coverage mismatch.\n  missing: %s\n  extra: %s" % (missing, extra))


def q(v):
    """Always double-quote a scalar destined for a YAML FLOW mapping.

    The first version of this quoted only on `:` `#` `"` `'` or newline — the block-context rules.
    Sources go out as flow mappings (`{name: x, observed: y}`), where `,` `{` `}` `[` `]` are ALSO
    terminators, and `observed` values look like:

        Amul - Butter Salted, 500 gm - 617.40/kg

    No colon, no hash, so it went out bare, and YAML ended the value at the first comma. Every
    `observed` field silently lost everything after it — the price. The data was never wrong; the
    writer was. Quoting unconditionally costs nothing and removes the whole class.
    """
    s = str(v)
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


HEADER = '''# Market rates — INR per base unit, PUNE baseline, researched 2026-09-12.
#
# What this file is for: `docs/onboarding-cold-start.md` promises that a restaurant's prices
# "bootstrap from a market-rate table by city, then correct on first real purchase". This is that
# table. It is the ONLY file in library/ that carries a price — `ingredients.yaml` deliberately has
# none, because a price is per-restaurant and these are only a starting point.
#
# Apply `city-index.yaml` to move off the Pune baseline:
#     effective = inr_per_base_unit * cities[city].multiplier
#
# BASIS: wholesale / trade rates — what a restaurant buying in bulk pays. NOT retail and NOT
# quick-commerce. The gap is not small: onion showed 56 INR/kg wholesale against 62-73 retail on
# the same page on the same day.
#
# `observed` holds the raw string exactly as the source published it, unit included. It is there so
# the conversion can be audited — the likeliest error in this whole dataset is an Indian mandi
# price quoted per QUINTAL (100 kg) read as per-kg, a 100x mistake that looks entirely plausible in
# a column of numbers. `library/validate_rates.py` cross-checks every shared code against
# `seed/ingredients.yaml`, whose hand-set prices pass the golden food-cost tests and which the
# research never saw.
#
# A CAVEAT THAT APPLIES TO THE WHOLE `veg` BLOCK: most of it comes from one Pune APMC wholesale
# page read on one day. That is a single daily snapshot of the most volatile category in the file,
# and it has already been caught being wrong once — the same page quoted mint at 7 INR/kg when
# every other source put bulk mint at 34-67, and the seed cross-check flagged it at 15.7x. Treat a
# single-sourced `veg` row as a point-in-time reading rather than a settled price. Onion is the
# other live example: 35 INR/kg on 6 Sep, 56 on 12 Sep, same page.
#
# TIERS — no row may claim more certainty than it has:
#   corroborated  two independent source NAMES agreeing within +/-25%
#   sourced       one citation, or two that disagreed — the note says which
#   estimated     no retrievable source; domain knowledge only, sources: []
# Two listings on one platform are ONE source: Hyperpure quoting six paneer brands is one opinion
# about paneer, not six.
#
# Regenerate provenance after editing:  python library/validate_rates.py --write-provenance

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
        out.append("    tier: %s" % r["tier"])
        srcs = r.get("sources") or []
        if srcs:
            out.append("    sources:")
            for s in srcs:
                out.append("      - {name: %s, url: %s, retrieved: %s, observed: %s}"
                           % (q(s["name"]), q(s["url"]), s["retrieved"], q(s["observed"])))
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
print("wrote %s — %d rates" % (dest, len(rows)))
print("  " + "  ".join("%s=%d" % (t, by_tier.get(t, 0))
                       for t in ("corroborated", "sourced", "estimated")))
