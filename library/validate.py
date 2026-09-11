"""Validate the starter recipe library. Runs in `make check` (audit-docs).

Two kinds of rule live here, and the second matters more than the first.

Structural: references resolve, no cycles, nesting depth <= 3 (ADR 0006), units on preparation
lines match the referenced item's base unit, categories and stations are known, no price appears
anywhere (prices are per-restaurant), every entry carries a confidence tier.

Calibration: the tier a row claims must be the tier it earned. `seed_calibrated` may be claimed only
by a code that exists in seed/, and the library copy must be quantity-for-quantity identical to the
seed. Every seed preparation and dish must appear here with that tier, so the library is a strict
superset of the demo restaurant. `derived` must name a real template in `basis`. The tier fractions
are written to PROVENANCE.md, and a stale PROVENANCE.md fails the build.

    python library/validate.py                     # validate; fail if PROVENANCE.md is stale
    python library/validate.py --write-provenance  # validate and rewrite PROVENANCE.md
"""
import os
import sys
from decimal import Decimal as D

import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(os.path.dirname(BASE), "seed")


def _load(folder, name):
    with open(os.path.join(folder, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


lib_ing = {i["code"]: i for i in _load(BASE, "ingredients.yaml")["ingredients"]}
lib_preps_doc = _load(BASE, "preparations.yaml")
lib_preps = {p["code"]: p for p in lib_preps_doc["preparations"]}
lib_dishes_doc = _load(BASE, "dishes.yaml")
lib_dishes = {d["code"]: d for d in lib_dishes_doc["items"]}

seed_ing = {i["code"]: i for i in _load(SEED, "ingredients.yaml")["ingredients"]}
seed_preps = {p["code"]: p for p in _load(SEED, "preparations.yaml")["preparations"]}
seed_dishes = {d["code"]: d for d in _load(SEED, "menu.yaml")["items"]}

TIERS = ("seed_calibrated", "derived", "estimated")
STATIONS = {"tandoor", "main_kitchen", "chinese", "cold", "bar"}
BASE_UNITS = {"g", "ml", "unit"}
STORAGE = {"ambient", "chilled", "frozen"}
ING_CATEGORIES = {"meat", "dairy", "veg", "grain", "oil", "spice", "bakery", "sweet"}
FOOD_TYPES = {"veg", "non_veg", "egg"}
# Ingredient metadata that must agree with seed/ for the shared codes. Price is deliberately absent:
# the library has none, and validating that is a separate rule below.
ING_SHARED_FIELDS = ("name", "base_unit", "yield_factor", "shelf_life_days", "storage", "category")
PREP_SHARED_FIELDS = ("name", "station", "batch_yield", "yield_unit", "shelf_life_hours", "prep_minutes")
DISH_SHARED_FIELDS = ("name", "category", "food_type", "station")

errors: list[str] = []
warnings: list[str] = []


def err(msg):
    errors.append(msg)


def _dup_check(kind, seq):
    seen = set()
    for row in seq:
        if row["code"] in seen:
            err("%s %s: duplicate code" % (kind, row["code"]))
        seen.add(row["code"])


_dup_check("ingredient", _load(BASE, "ingredients.yaml")["ingredients"])
_dup_check("preparation", lib_preps_doc["preparations"])
_dup_check("dish", lib_dishes_doc["items"])

# ---------------------------------------------------------------- no prices, anywhere
for code, row in lib_ing.items():
    if "price" in row:
        err("ingredient %s: carries a price. Prices are per-restaurant; the library has none" % code)
for code, row in lib_preps.items():
    if "price" in row:
        err("preparation %s: carries a price" % code)
for code, row in lib_dishes.items():
    for v in row.get("variants", []):
        for k in ("price", "gst", "popularity"):
            if k in v or k in row:
                err("dish %s: carries %r. That is seed/ data, not library data" % (code, k))

# ---------------------------------------------------------------- ingredients
for code, row in lib_ing.items():
    if row.get("base_unit") not in BASE_UNITS:
        err("ingredient %s: base_unit %r not in %s" % (code, row.get("base_unit"), sorted(BASE_UNITS)))
    if row.get("storage") not in STORAGE:
        err("ingredient %s: storage %r" % (code, row.get("storage")))
    if row.get("category") not in ING_CATEGORIES:
        err("ingredient %s: category %r" % (code, row.get("category")))
    yf = row.get("yield_factor")
    if not isinstance(yf, (int, float)) or not 0 < yf <= 1:
        err("ingredient %s: yield_factor %r must be in (0, 1]" % (code, yf))
    if not isinstance(row.get("shelf_life_days"), int) or row["shelf_life_days"] <= 0:
        err("ingredient %s: shelf_life_days %r" % (code, row.get("shelf_life_days")))

for code, srow in seed_ing.items():
    lrow = lib_ing.get(code)
    if lrow is None:
        err("seed ingredient %s is missing from the library. The library must be a superset of seed/" % code)
        continue
    for f in ING_SHARED_FIELDS:
        if lrow.get(f) != srow.get(f):
            err("ingredient %s.%s: library %r != seed %r" % (code, f, lrow.get(f), srow.get(f)))


def base_unit_of(ref):
    if ref in lib_ing:
        return lib_ing[ref]["base_unit"]
    if ref in lib_preps:
        return lib_preps[ref]["yield_unit"]
    return None


# ---------------------------------------------------------------- preparations
consumers: dict[str, int] = {c: 0 for c in lib_preps}

for code, p in lib_preps.items():
    if p.get("station") not in STATIONS:
        err("preparation %s: station %r" % (code, p.get("station")))
    if p.get("yield_unit") not in BASE_UNITS:
        err("preparation %s: yield_unit %r" % (code, p.get("yield_unit")))
    if not p.get("lines"):
        err("preparation %s: no lines" % code)
    for f in ("batch_yield", "shelf_life_hours", "prep_minutes"):
        if not isinstance(p.get(f), (int, float)) or p[f] <= 0:
            err("preparation %s: %s %r" % (code, f, p.get(f)))
    for ln in p.get("lines", []):
        ref = ln.get("ref")
        if ref not in lib_ing and ref not in lib_preps:
            err("preparation %s -> unknown ref %r" % (code, ref))
            continue
        if ref in lib_preps:
            consumers[ref] += 1
        expected = base_unit_of(ref)
        if ln.get("unit") != expected:
            err("preparation %s line %s: unit %r but %s is in %s" % (code, ref, ln.get("unit"), ref, expected))
        if not isinstance(ln.get("qty"), (int, float)) or ln["qty"] <= 0:
            err("preparation %s line %s: qty %r" % (code, ref, ln.get("qty")))

# cycles and depth, mirroring seed/validate.py so both files agree on what "depth 3" means
_seen_ok: set[str] = set()


def walk(code, stack=()):
    if code in stack:
        err("CYCLE: " + " -> ".join(stack + (code,)))
        return
    if len(stack) >= 3:
        err("DEPTH>3: " + " -> ".join(stack + (code,)))
        return
    if code in _seen_ok:
        return
    for ln in lib_preps[code].get("lines", []):
        if ln.get("ref") in lib_preps:
            walk(ln["ref"], stack + (code,))
    _seen_ok.add(code)


for code in lib_preps:
    walk(code)

# ---------------------------------------------------------------- dishes
categories = {c["code"] for c in lib_dishes_doc["categories"]}

for code, d in lib_dishes.items():
    if d.get("category") not in categories:
        err("dish %s: unknown category %r" % (code, d.get("category")))
    if d.get("food_type") not in FOOD_TYPES:
        err("dish %s: food_type %r" % (code, d.get("food_type")))
    if d.get("station") not in STATIONS:
        err("dish %s: station %r" % (code, d.get("station")))
    variants = d.get("variants") or []
    if not variants:
        err("dish %s: no variants" % code)
    vcodes = [v.get("code") for v in variants]
    if len(set(vcodes)) != len(vcodes):
        err("dish %s: duplicate variant codes %s" % (code, vcodes))
    for v in variants:
        recipe = v.get("recipe") or []
        if len(recipe) < 2:
            err("dish %s/%s: a recipe needs at least two lines" % (code, v.get("code")))
        mass = D(0)
        counted = False  # a line in `unit` (papad, pav, egg) carries mass the g/ml sum cannot see
        for ln in recipe:
            ref = ln.get("ref")
            if ref not in lib_ing and ref not in lib_preps:
                err("dish %s/%s -> unknown ref %r" % (code, v.get("code"), ref))
                continue
            if ref in lib_preps:
                consumers[ref] += 1
            if not isinstance(ln.get("qty"), (int, float)) or ln["qty"] <= 0:
                err("dish %s/%s line %s: qty %r" % (code, v.get("code"), ref, ln.get("qty")))
                continue
            if base_unit_of(ref) in ("g", "ml"):
                mass += D(str(ln["qty"]))
            else:
                counted = True
        # A plate under 40 g or over 1.2 kg of g/ml lines is a typo (a missing zero, an extra one),
        # not a portion. Bread pieces sit at the bottom of the range; biryanis at the top. The floor
        # is waived when a counted line is present: a roasted papad is one papad and a gram of oil.
        if recipe and (mass > 1200 or (mass < 40 and not counted)):
            err("dish %s/%s: %s g/ml on the plate is not a plausible portion" % (code, v.get("code"), mass))
        if not isinstance(v.get("prep_minutes"), int) or v["prep_minutes"] <= 0:
            err("dish %s/%s: prep_minutes %r" % (code, v.get("code"), v.get("prep_minutes")))

for code, n in consumers.items():
    if n == 0:
        err("preparation %s feeds nothing. A preparation must feed at least one dish or preparation" % code)
    elif n == 1 and not lib_preps[code].get("single_consumer_ok"):
        warnings.append("preparation %s has a single consumer; inline it as a recipe line, or set "
                        "single_consumer_ok with a note saying why it is batch-made" % code)

# ---------------------------------------------------------------- confidence tiers


def _check_tier(kind, code, row, seed_rows, all_codes):
    tier = row.get("confidence")
    if tier not in TIERS:
        err("%s %s: confidence %r must be one of %s" % (kind, code, tier, TIERS))
        return
    if tier == "seed_calibrated" and code not in seed_rows:
        err("%s %s: claims seed_calibrated but is not in seed/. That tier is earned, not set" % (kind, code))
    if tier != "seed_calibrated" and code in seed_rows:
        err("%s %s: is in seed/ but claims %r. It must be seed_calibrated and identical" % (kind, code, tier))
    basis = row.get("basis")
    if tier == "derived":
        if not basis or basis not in all_codes:
            err("%s %s: derived must name an existing template in basis, got %r" % (kind, code, basis))
        elif basis == code:
            err("%s %s: derived from itself" % (kind, code))
    if tier == "seed_calibrated" and basis:
        err("%s %s: seed_calibrated rows have no basis; seed/ is the basis" % (kind, code))


for code, p in lib_preps.items():
    _check_tier("preparation", code, p, seed_preps, set(lib_preps))
for code, d in lib_dishes.items():
    _check_tier("dish", code, d, seed_dishes, set(lib_dishes))

# a derived row's template must be at least as trusted as itself: substitution into an estimated
# recipe yields another estimated recipe, whatever the author would like to call it
_rank = {t: i for i, t in enumerate(TIERS)}
for kind, rows in (("preparation", lib_preps), ("dish", lib_dishes)):
    for code, row in rows.items():
        b = row.get("basis")
        if row.get("confidence") == "derived" and b in rows:
            if _rank.get(rows[b].get("confidence"), 9) > _rank["derived"]:
                err("%s %s: derived from %s, which is only %r. Derivation cannot manufacture confidence"
                    % (kind, code, b, rows[b].get("confidence")))

# ---------------------------------------------------------------- drift: seed must be here, identical


def _lines_key(lines, with_unit):
    out = []
    for ln in lines:
        out.append((ln["ref"], D(str(ln["qty"])), ln.get("unit") if with_unit else None))
    return out


for code, sp in seed_preps.items():
    lp = lib_preps.get(code)
    if lp is None:
        err("seed preparation %s is missing from the library" % code)
        continue
    for f in PREP_SHARED_FIELDS:
        if lp.get(f) != sp.get(f):
            err("preparation %s.%s: library %r != seed %r" % (code, f, lp.get(f), sp.get(f)))
    if _lines_key(lp.get("lines", []), True) != _lines_key(sp["lines"], True):
        err("preparation %s: lines drift from seed/preparations.yaml" % code)

for code, sd in seed_dishes.items():
    ld = lib_dishes.get(code)
    if ld is None:
        err("seed dish %s is missing from the library" % code)
        continue
    for f in DISH_SHARED_FIELDS:
        if ld.get(f) != sd.get(f):
            err("dish %s.%s: library %r != seed %r" % (code, f, ld.get(f), sd.get(f)))
    sv = {v["code"]: v for v in sd["variants"]}
    lv = {v["code"]: v for v in ld.get("variants", [])}
    if set(sv) != set(lv):
        err("dish %s: variants %s != seed %s" % (code, sorted(lv), sorted(sv)))
        continue
    for vc, v in sv.items():
        if lv[vc].get("name") != v["name"] or lv[vc].get("prep_minutes") != v["prep_minutes"]:
            err("dish %s/%s: name/prep_minutes drift from seed" % (code, vc))
        if _lines_key(lv[vc].get("recipe", []), False) != _lines_key(v["recipe"], False):
            err("dish %s/%s: recipe drifts from seed/menu.yaml" % (code, vc))

# ---------------------------------------------------------------- provenance


def _fractions(rows):
    total = len(rows)
    counts = {t: sum(1 for r in rows if r.get("confidence") == t) for t in TIERS}
    return total, counts


def provenance_text():
    lines = [
        "# Provenance",
        "",
        "Generated by `library/validate.py --write-provenance`. Do not edit by hand; the validator",
        "fails when this file is stale.",
        "",
        "The honest reading: `seed_calibrated` rows have passed a golden food-cost test. `derived`",
        "rows borrow that structure by substitution. `estimated` rows are domain knowledge a chef",
        "has not confirmed. See README.md § Confidence.",
        "",
    ]
    for label, rows in (("Preparations", list(lib_preps.values())), ("Dishes", list(lib_dishes.values()))):
        total, counts = _fractions(rows)
        lines += ["## %s — %d" % (label, total), "", "| Tier | Count | Share |", "|---|---|---|"]
        for t in TIERS:
            share = (D(counts[t]) / D(total) * 100).quantize(D("0.1")) if total else D(0)
            lines.append("| `%s` | %d | %s%% |" % (t, counts[t], share))
        lines.append("")
    n_variants = sum(len(d.get("variants", [])) for d in lib_dishes.values())
    n_shared = sum(1 for c in lib_ing if c in seed_ing)
    lines += [
        "## Ingredients — %d" % len(lib_ing),
        "",
        "%d share a code with `seed/` and match its metadata field for field. The remaining %d are"
        % (n_shared, len(lib_ing) - n_shared),
        "estimated: `yield_factor`, `shelf_life_days` and `storage` await a chef.",
        "",
        "## Dish variants — %d" % n_variants,
        "",
        "Per-dish `basis` names the template each `derived` row was built from.",
        "",
    ]
    by_cat: dict[str, int] = {}
    for d in lib_dishes.values():
        by_cat[d.get("category")] = by_cat.get(d.get("category"), 0) + 1
    lines += ["## Dishes by category", "", "| Category | Dishes |", "|---|---|"]
    for c in lib_dishes_doc["categories"]:
        lines.append("| `%s` | %d |" % (c["code"], by_cat.get(c["code"], 0)))
    lines.append("")
    return "\n".join(lines)


if errors:
    print("LIBRARY VALIDATION ERRORS:")
    for e in errors:
        print("  -", e)
    sys.exit(1)

prov_path = os.path.join(BASE, "PROVENANCE.md")
text = provenance_text()
if "--write-provenance" in sys.argv:
    with open(prov_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("wrote PROVENANCE.md")
else:
    current = open(prov_path, encoding="utf-8").read() if os.path.exists(prov_path) else ""
    if current != text:
        print("LIBRARY VALIDATION ERRORS:")
        print("  - PROVENANCE.md is stale. Run: python library/validate.py --write-provenance")
        sys.exit(1)

for w in warnings:
    print("warning:", w)

n_variants = sum(len(d.get("variants", [])) for d in lib_dishes.values())
print("Library OK: %d ingredients, %d preparations, %d dishes, %d variants"
      % (len(lib_ing), len(lib_preps), len(lib_dishes), n_variants))
for label, rows in (("preparations", list(lib_preps.values())), ("dishes", list(lib_dishes.values()))):
    total, counts = _fractions(rows)
    print("  %-13s " % label + "  ".join("%s=%d" % (t, counts[t]) for t in TIERS))
