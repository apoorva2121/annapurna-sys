"""Emit the `seed_calibrated` tier of the library from seed/, in library format.

The calibrated tier is never retyped: this script prints it, and the blocks are pasted into
ingredients.yaml / preparations.yaml / dishes.yaml under their `# ==== seed_calibrated` markers.
validate.py then asserts that what was pasted is still identical to seed/. When seed/ changes, the
validator goes red and this is the way back to green.

    python library/from_seed.py ingredients
    python library/from_seed.py preparations
    python library/from_seed.py dishes
"""
import os
import sys

import yaml

SEED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed")


def _load(name):
    with open(os.path.join(SEED, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _num(v):
    return str(v)


def ingredients():
    for i in _load("ingredients.yaml")["ingredients"]:
        print("  - {code: %-14s name: %-22s base_unit: %-5s yield_factor: %.2f, shelf_life_days: %-4s "
              "storage: %-8s category: %s}"
              % (i["code"] + ",", i["name"] + ",", i["base_unit"] + ",", i["yield_factor"],
                 str(i["shelf_life_days"]) + ",", i["storage"] + ",", i["category"]))


def preparations():
    for p in _load("preparations.yaml")["preparations"]:
        print("  - code: %s" % p["code"])
        print("    name: %s" % p["name"])
        print("    station: %s" % p["station"])
        print("    batch_yield: %s" % _num(p["batch_yield"]))
        print("    yield_unit: %s" % p["yield_unit"])
        print("    shelf_life_hours: %s" % _num(p["shelf_life_hours"]))
        print("    prep_minutes: %s" % _num(p["prep_minutes"]))
        print("    confidence: seed_calibrated")
        print("    lines:")
        for ln in p["lines"]:
            print("      - {ref: %-16s qty: %-6s unit: %s}" % (ln["ref"] + ",", _num(ln["qty"]) + ",", ln["unit"]))
        print()


def dishes():
    for d in _load("menu.yaml")["items"]:
        print("  - code: %s" % d["code"])
        print("    name: %s" % d["name"])
        print("    category: %s" % d["category"])
        print("    food_type: %s" % d["food_type"])
        print("    station: %s" % d["station"])
        print("    confidence: seed_calibrated")
        print("    variants:")
        for v in d["variants"]:
            recipe = ", ".join("{ref: %s, qty: %s}" % (ln["ref"], _num(ln["qty"])) for ln in v["recipe"])
            print("      - {code: %s, name: %s, prep_minutes: %s," % (v["code"], v["name"], v["prep_minutes"]))
            print("         recipe: [%s]}" % recipe)
        print()


if __name__ == "__main__":
    {"ingredients": ingredients, "preparations": preparations, "dishes": dishes}[sys.argv[1]]()
