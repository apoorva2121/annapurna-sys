"""Validate `seed/tandoor-house.yaml` — the second tenant, composed from `library/`.

Its own file rather than a section of `seed/validate.py`, because it is the only dataset that
reads BOTH directories. `library/validate.py` reads `seed/` (to prove the shared codes match) and
nothing in `seed/` has ever read `library/`; putting this inside either one would invert that
direction and make the two validators mutually dependent. Here it just sits downstream of both.

What it checks, in rough order of how much it would hurt to get wrong:

  1. **Station coherence.** Tandoor House declares two stations and no `chinese`. Every dish on
     its menu must cook at a station it actually has. A menu item routed to a station that does
     not exist is invisible in the data and fatal on the kitchen display — M08 would render a
     ticket nobody is standing at.
  2. **Reference integrity.** Every `ref` is a real library dish; every `variant` exists on that
     dish. This is the whole point of composing from the library rather than retyping a menu.
  3. **Floor and tax.** Tables point at declared areas; `gst` values resolve to declared groups.
  4. **Food cost.** Costs the whole menu through `library/market-rates.yaml` and reports the
     popularity-weighted theoretical food cost. Tandoor House is *designed* to come out worse than
     Spice Garden's ~25.6% — it charges ~15% less for the same library recipes — so a figure that
     lands near Spice Garden's means the price list stopped being a contrast and the demo lost the
     thing it exists to show.
"""
import os
import sys
from decimal import Decimal as D

import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(BASE), "library")


def load(folder, name):
    with open(os.path.join(folder, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


th = load(BASE, "tandoor-house.yaml")
org = load(BASE, "organization.yaml")
lib_ing = {i["code"]: i for i in load(LIB, "ingredients.yaml")["ingredients"]}
lib_preps = {p["code"]: p for p in load(LIB, "preparations.yaml")["preparations"]}
lib_dishes = {d["code"]: d for d in load(LIB, "dishes.yaml")["items"]}

errors: list[str] = []


def err(msg):
    errors.append(msg)


# ---------------------------------------------------------------- tenancy

restaurants = {r["code"] for r in org["restaurants"]}
if th["meta"]["restaurant"] not in restaurants:
    err("meta.restaurant %r is not a restaurant in organization.yaml"
        % th["meta"]["restaurant"])

# ---------------------------------------------------------------- floor

areas = {a["code"] for a in th["dining_areas"]}
for t in th["restaurant_tables"]:
    if t["area"] not in areas:
        err("table %s -> unknown dining area %s" % (t["code"], t["area"]))

seats = sum(t["seats"] for t in th["restaurant_tables"])

# ---------------------------------------------------------------- tax

tax_rates = {int(D(str(g["rate"])) * 100): g["code"] for g in th["tax_groups"]}

# ---------------------------------------------------------------- menu

stations = {s["code"] for s in th["stations"]}
seen = set()

for row in th["menu"]:
    ref, variant = row["ref"], row["variant"]
    key = (ref, variant)
    if key in seen:
        err("menu %s/%s listed twice" % (ref, variant))
    seen.add(key)

    dish = lib_dishes.get(ref)
    if dish is None:
        err("menu %s -> no such dish in library/dishes.yaml" % ref)
        continue

    if not any(v["code"] == variant for v in dish["variants"]):
        err("menu %s -> dish has no variant %r (has: %s)"
            % (ref, variant, ", ".join(v["code"] for v in dish["variants"])))

    # Check 1 — the one that would hurt most.
    if dish["station"] not in stations:
        err("menu %s cooks at station %r, which Tandoor House does not have (has: %s). "
            "A ticket routed to a station nobody stands at is lost work"
            % (ref, dish["station"], ", ".join(sorted(stations))))

    if row.get("gst") not in tax_rates:
        err("menu %s/%s -> gst %r has no tax group (declared: %s)"
            % (ref, variant, row.get("gst"), ", ".join(str(r) for r in sorted(tax_rates))))

    if not isinstance(row.get("price"), int) or row["price"] <= 0:
        err("menu %s/%s -> price %r must be a positive integer (INR, GST-exclusive)"
            % (ref, variant, row.get("price")))

# ---------------------------------------------------------------- costing

rates_path = os.path.join(LIB, "market-rates.yaml")
rows = []
if os.path.exists(rates_path):
    rates = {r["code"]: D(str(r["inr_per_base_unit"]))
             for r in load(LIB, "market-rates.yaml")["rates"]}
    city = th["meta"].get("city", "PUNE")
    cities = {c["code"]: D(str(c["multiplier"]))
              for c in load(LIB, "city-index.yaml")["cities"]}
    mult = cities.get(city, D(str(load(LIB, "city-index.yaml")["meta"]["unknown_city_multiplier"])))

    _prep_cache: dict[str, D] = {}

    def unit_cost(ref, stack=()):
        """INR per base unit of `ref`, walking preparations recursively."""
        if ref in rates:
            return rates[ref] * mult
        if ref in _prep_cache:
            return _prep_cache[ref]
        prep = lib_preps.get(ref)
        if prep is None:
            err("costing: unknown ref %s" % ref)
            return D(0)
        if ref in stack:
            err("costing: preparation cycle at %s" % ref)
            return D(0)
        total = sum((unit_cost(ln["ref"], stack + (ref,)) * D(str(ln["qty"]))
                     for ln in prep["lines"]), D(0))
        cost = total / D(str(prep["batch_yield"]))
        _prep_cache[ref] = cost
        return cost

    for row in th["menu"]:
        dish = lib_dishes.get(row["ref"])
        if dish is None:
            continue
        variant = next((v for v in dish["variants"] if v["code"] == row["variant"]), None)
        if variant is None:
            continue
        cost = sum((unit_cost(ln["ref"]) * D(str(ln["qty"])) for ln in variant["recipe"]), D(0))
        price = D(str(row["price"]))
        rows.append((("%s/%s" % (row["ref"], row["variant"])), row.get("popularity", 0),
                     price, cost, cost / price * 100))

if errors:
    print("TANDOOR HOUSE VALIDATION ERRORS:")
    for e in errors:
        print("  -", e)
    sys.exit(1)

print("Tandoor House OK: %d menu rows, %d dishes, %d tables/%d seats, %d stations, %d areas"
      % (len(th["menu"]), len({r["ref"] for r in th["menu"]}),
         len(th["restaurant_tables"]), seats, len(stations), len(areas)))

if not rows:
    print("  costing skipped - library/market-rates.yaml not present yet")
else:
    print("\nTandoor House food cost %, sorted worst first:")
    for name, pop, price, cost, pct in sorted(rows, key=lambda r: -r[4]):
        flag = "  <== high" if pct > 40 else ""
        print("  %-30s pop%4d  price %6.0f  cost %6.2f  %5.1f%%%s"
              % (name, pop, price, cost, pct, flag))
    num = sum(r[1] * r[3] for r in rows)
    den = sum(r[1] * r[2] for r in rows)
    weighted = num / den * 100
    print("\nPopularity-weighted THEORETICAL food cost: %.1f%%" % weighted)
    print("(Spice Garden runs ~25.6%. Tandoor House is designed to be visibly worse - it charges")
    print(" ~15% less for the same library recipes. If these two converge, the contrast the second")
    print(" tenant exists to demonstrate has been priced away.)")
