"""Validate the seed YAML: references resolve, no cycles, depth <= 3, food cost is sane."""
import sys, yaml
from decimal import Decimal as D

import os
BASE = os.path.dirname(os.path.abspath(__file__))

ing = {i["code"]: i for i in yaml.safe_load(open(os.path.join(BASE, "ingredients.yaml"), encoding="utf-8"))["ingredients"]}
preps = {p["code"]: p for p in yaml.safe_load(open(os.path.join(BASE, "preparations.yaml"), encoding="utf-8"))["preparations"]}
menu = yaml.safe_load(open(os.path.join(BASE, "menu.yaml"), encoding="utf-8"))
org  = yaml.safe_load(open(os.path.join(BASE, "organization.yaml"), encoding="utf-8"))
ops  = yaml.safe_load(open(os.path.join(BASE, "operations.yaml"), encoding="utf-8"))

errors = []

# --- reference integrity ---
for pc, p in preps.items():
    for ln in p["lines"]:
        if ln["ref"] not in ing and ln["ref"] not in preps:
            errors.append("prep %s -> unknown ref %s" % (pc, ln["ref"]))

for item in menu["items"]:
    for v in item["variants"]:
        for ln in v["recipe"]:
            if ln["ref"] not in ing and ln["ref"] not in preps:
                errors.append("%s/%s -> unknown ref %s" % (item["code"], v["code"], ln["ref"]))

cats = {c["code"] for c in menu["categories"]}
STATIONS = {"tandoor", "main_kitchen", "chinese", "cold", "bar"}
for item in menu["items"]:
    if item["category"] not in cats:
        errors.append("%s -> unknown category %s" % (item["code"], item["category"]))
    # schema.md: menu_item.food_type is NOT NULL and legally required in India
    if item.get("food_type") not in ("veg", "non_veg", "egg"):
        errors.append("%s -> missing/invalid food_type %r" % (item["code"], item.get("food_type")))
    if item.get("station") not in STATIONS:
        errors.append("%s -> unknown station %r" % (item["code"], item.get("station")))
for pc, p_ in preps.items():
    if p_.get("station") not in STATIONS:
        errors.append("prep %s -> unknown station %r" % (pc, p_.get("station")))

# --- prep unit cost, recursive, with cycle + depth detection ---
_cache = {}

def prep_unit_cost(code, stack=()):
    """Cost per 1 base unit of the preparation's yield."""
    if code in stack:
        errors.append("CYCLE: " + " -> ".join(stack + (code,)))
        return D(0)
    if len(stack) >= 3:
        errors.append("DEPTH>3: " + " -> ".join(stack + (code,)))
        return D(0)
    if code in _cache:
        return _cache[code]
    p = preps[code]
    total = D(0)
    for ln in p["lines"]:
        q = D(str(ln["qty"]))
        r = ln["ref"]
        if r in ing:
            # cost of raw purchased qty needed, accounting for trim loss
            yf = D(str(ing[r]["yield_factor"]))
            total += q / yf * D(str(ing[r]["price"]))
        else:
            total += q * prep_unit_cost(r, stack + (code,))
    unit = total / D(str(p["batch_yield"]))
    _cache[code] = unit
    return unit

def line_cost(ref, qty):
    q = D(str(qty))
    if ref in ing:
        return q / D(str(ing[ref]["yield_factor"])) * D(str(ing[ref]["price"]))
    return q * prep_unit_cost(ref)

# --- dish food cost ---
rows = []
for item in menu["items"]:
    for v in item["variants"]:
        cost = sum((line_cost(l["ref"], l["qty"]) for l in v["recipe"]), D(0))
        price = D(str(v["price"]))
        rows.append((item["code"] + "/" + v["code"], item["popularity"], price, cost, cost / price * 100))

# ---- organization.yaml: roles, permissions, employees ----
perm_codes = {p["code"] for p in org["permissions"]}
role_codes = {r["code"] for r in org["roles"]}
rest_codes = {r["code"] for r in org["restaurants"]}

for role in org["roles"]:
    if role["permissions"] == ["*"]:
        continue
    for entry in role["permissions"]:
        for code in [c.strip() for c in entry.split(",")]:
            if code not in perm_codes:
                errors.append("role %s -> unknown permission %s" % (role["code"], code))
    # ADR 0011: every role can see its own performance. Not configurable.
    if "performance.view.own" not in " ".join(role["permissions"]):
        errors.append("role %s missing performance.view.own (ADR 0011)" % role["code"])

for emp in org["employees"]:
    if emp["role"] not in role_codes:
        errors.append("employee %s -> unknown role %s" % (emp["code"], emp["role"]))
    if emp["restaurant"] not in rest_codes:
        errors.append("employee %s -> unknown restaurant %s" % (emp["code"], emp["restaurant"]))

if len(org["organizations"]) < 2:
    errors.append("need >=2 organizations: tenant-isolation tests require a second tenant to fail against")

# ---- operations.yaml ----
area_codes = {a["code"] for a in ops["dining_areas"]}
for t in ops["restaurant_tables"]:
    if t["area"] not in area_codes:
        errors.append("table %s -> unknown dining area %s" % (t["code"], t["area"]))

seats = sum(t["seats"] for t in ops["restaurant_tables"])
if seats != 48:
    errors.append("seats total %d, docs/seed-data.md says 48" % seats)

defined_stations = {s_["code"] for s_ in ops["stations"]}
used_stations = {i["station"] for i in menu["items"]} | {p_["station"] for p_ in preps.values()}
for st in sorted(used_stations - defined_stations):
    errors.append("station %s used by menu/preparations but not defined in operations.yaml" % st)

cat_codes = {c["code"] for c in menu["categories"]}
grp_codes = {g["code"] for g in ops["modifier_groups"]}
for att in ops["modifier_attachments"]:
    for c in att["categories"]:
        if c not in cat_codes:
            errors.append("modifier attachment -> unknown category %s" % c)
    for g in att["groups"]:
        if g not in grp_codes:
            errors.append("modifier attachment -> unknown modifier group %s" % g)

STAGES = {"receiving", "storage", "prep", "service"}
for wr in ops["wastage_reasons"]:
    if wr["stage"] not in STAGES:
        errors.append("wastage reason %s -> unknown stage %s" % (wr["code"], wr["stage"]))

# ---- incentive scheme: ADR 0011 weight rule ----
w = ops["incentive_scheme"]["weights"]
if round(sum(w.values()), 4) != 1.0:
    errors.append("incentive weights sum to %s, expected 1.0" % round(sum(w.values()), 4))
if w["volume"] > w["accuracy"] + w["rating"]:
    errors.append("volume weight %s exceeds accuracy+rating %s -- ADR 0011: this pays people to rush"
                  % (w["volume"], w["accuracy"] + w["rating"]))

if errors:
    print("VALIDATION ERRORS:")
    for e in errors:
        print("  -", e)
    sys.exit(1)

print("References OK: %d ingredients, %d preparations, %d items, %d variants"
      % (len(ing), len(preps), len(menu["items"]), sum(len(i["variants"]) for i in menu["items"])))
print("Org OK: %d orgs, %d restaurants, %d permissions, %d roles, %d employees"
      % (len(org["organizations"]), len(org["restaurants"]), len(perm_codes),
         len(org["roles"]), len(org["employees"])))
print("Ops OK: %d tables/%d seats, %d suppliers, %d wastage reasons, %d modifier groups"
      % (len(ops["restaurant_tables"]), seats, len(ops["suppliers"]),
         len(ops["wastage_reasons"]), len(ops["modifier_groups"])))
print("\nPreparation unit costs (INR per base unit):")
for c in sorted(preps):
    print("  %-20s %8.4f  (batch %s %s = INR %.0f)"
          % (c, prep_unit_cost(c), preps[c]["batch_yield"], preps[c]["yield_unit"],
             prep_unit_cost(c) * D(str(preps[c]["batch_yield"]))))

print("\nDish food cost %, sorted worst first:")
for name, pop, price, cost, pct in sorted(rows, key=lambda r: -r[4]):
    flag = "  <== high" if pct > 40 else ""
    print("  %-30s pop%4d  price %6.0f  cost %6.2f  %5.1f%%%s" % (name, pop, price, cost, pct, flag))

# weighted food cost across the menu, by popularity (approximates the sales mix)
num = sum(r[1] * r[3] for r in rows)
den = sum(r[1] * r[2] for r in rows)
print("\nPopularity-weighted THEORETICAL food cost: %.1f%%" % (num / den * 100))
print("(docs/seed-data.md targets ~26%% theoretical; ~32%% actual after planted waste and drift)")
