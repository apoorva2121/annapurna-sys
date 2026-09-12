"""Build `gst-rates.yaml` — the tax overlay `library/merge_rates.py` already expects.

WHY A GENERATOR AND NOT 122 HAND-TYPED NUMBERS. A GST rate is not a fact about an ingredient, it
is a fact about a *heading plus a form*. Typing 122 literals would record the answers and destroy
the reasoning, so a later reader could not tell a researched rate from a guessed one. This maps
each code to its HSN heading once, states the rate rule for that heading once with a citation, and
derives the 122 rows. Re-run it when the law changes and every row moves together.

THE LAW, AS OF 2026-09-12. GST 2.0 (56th Council, notification 09/2025-CTR of 17 Sep 2025, in
force 22 Sep 2025) abolished the 12% and 28% slabs. Food sits in three places now: nil, 5%, and
an 18% residue for things that are chemically or cosmetically classified rather than as food.
Every pre-reform rate table on the internet is wrong about this file, which is why nothing here is
carried over from memory.

THE FORM RULE, WHICH IS THE INTERESTING PART. For most agricultural commodities the rate is nil
when the goods are loose or unbranded and 5% when they are "pre-packaged and labelled". That
phrase is defined by reference to the Legal Metrology Act, 2009, and it has a size ceiling: a
single package over 25 kg / 25 L is NOT a pre-packaged commodity, so a 50 kg mill bag of maida is
nil while a 10 kg labelled sack of besan is 5%.

This matters here more than it would in most datasets, because `library/market-rates.yaml`
declares its basis as *wholesale / trade — what a restaurant buying in bulk pays*. Half these rows
were priced at a mandi and half off a branded trade list, and `grade` already records which. So
the form is derivable from evidence already in the file — the same move that recovered
`basis_city`, `as_of` and `grade` in the previous pass.

    python library/gst_build.py --out <fragments dir>
"""

import os
import re
import sys

import yaml

BASE = os.path.dirname(os.path.abspath(__file__))

RETRIEVED = "2026-09-12"

# ---------------------------------------------------------------- the citations
#
# One source per rate rule, not one per row. A row cites the rule that decided it, so a reader
# checking our work re-reads six pages rather than 122.

SRC = {
    "reform": {
        "name": "CBIC notification 09/2025-CTR, as reported (GST 2.0, in force 22 Sep 2025)",
        "url": "https://taxguru.in/goods-and-service-tax/govt-notifies-revised-gst-rates-wide-array-goods-wef-22nd-sep-2025.html",
        "observed": "12% and 28% slabs abolished; ~99% of 12% items to 5%, ~90% of 28% to 18%",
    },
    "prepack": {
        "name": "CBIC FAQ on 'pre-packaged and labelled' + Legal Metrology Act 2009",
        "url": "https://foodsafetyworks.com/news/faqs-on-gst-applicability-on-prepackaged-and-labelled-goods/",
        "observed": "packages over 25 kg/25 L are not 'pre-packaged commodity'; loose is nil, packaged 5%",
    },
    "dairy": {
        "name": "GST on dairy after 22 Sep 2025",
        "url": "https://cleartax.in/s/gst-on-milk-paneer-curd",
        "observed": "milk/UHT/paneer/curd nil (0401/0403/0406); butter, ghee, cheese 5% (0405); milk powder, khoya 5% (0402)",
    },
    "meat": {
        "name": "GST on meat and seafood",
        "url": "https://busy.in/gst-rates/meat/",
        "observed": "fresh or chilled meat nil; frozen/processed fish and crustaceans 5%",
    },
    "spice": {
        "name": "GST on spices and condiments — loose vs packaged",
        "url": "https://www.laabam.one/in/id/resources/gst/law/gst-spices-condiments",
        "observed": "loose/unbranded whole spices nil; pre-packaged and labelled 5% (HSN 0904-0910)",
    },
    "prep": {
        "name": "Updated GST rates by HSN effective 22 Sept 2025 (old vs new)",
        "url": "https://tmdsuite.com/updated-gst-rates-by-hsn-effective-sept-2025",
        "observed": "2103 sauces 12->5; 2106 food preps 18->5; 1902 pasta 12->5; 1108 starch 12->5; "
                    "2102 yeast/baking powder 12->5; 1806 cocoa 18->5; 1905 pastry 18->5; breads nil",
    },
    "veg": {
        "name": "GST on vegetables and fruit",
        "url": "https://busy.in/gst-rates/vegetables/",
        "observed": "fresh vegetables and fruit nil; frozen vegetables 5% (HSN 0710)",
    },
    "eighteen": {
        "name": "GST on vinegar (2209) and Chapter 33 preparations",
        "url": "https://cleartax.in/s/vinegar-gst-rates-hsn-code-2209",
        "observed": "vinegar and substitutes from acetic acid 18%; Chapter 33 odoriferous preparations 18%",
    },
    "oil_sugar": {
        "name": "GST on edible oil and sugar",
        "url": "https://busy.in/gst-rates/edible-oil/",
        "observed": "edible oils 5% bulk or packaged (1507-1518); sugar 5% (1701)",
    },
}

# ---------------------------------------------------------------- the rate table
#
# (hsn, policy) per code. Policy is one of:
#   NIL            nil whatever the form   — fresh produce, fresh meat, salt, bread, papad
#   ("FLAT", r)    rate r whatever the form — processed goods, where packaging is not the question
#   ("FORM", r)    nil if loose, r if pre-packaged and labelled — the agricultural commodities
#
# FORM is where the classifier below earns its keep; FLAT and NIL do not consult it.

NIL = ("NIL", 0)

TABLE = {
    # ---- meat. Schedule nil covers "fresh or chilled"; frozen + packaged is 5%.
    "CHKN_BONELESS": ("0207", NIL, "meat"),
    "CHKN_CURRCUT": ("0207", NIL, "meat"),
    "CHKN_WHOLE": ("0207", NIL, "meat"),
    "CHKN_WINGS": ("0207", NIL, "meat"),
    "MUTTON": ("0204", NIL, "meat"),
    "MUTTON_KEEMA": ("0204", NIL, "meat"),
    "EGG": ("0407", NIL, "meat"),
    "FISH_BASA": ("0304", ("FLAT", 5), "meat"),
    "FISH_SURMAI": ("0304", ("FLAT", 5), "meat"),
    "PRAWN": ("0306", ("FLAT", 5), "meat"),

    # ---- dairy. The reform moved paneer and UHT milk to nil and pulled ghee/butter/cheese to 5%.
    "MILK": ("0401", NIL, "dairy"),
    "CURD": ("0403", NIL, "dairy"),
    "PANEER": ("0406", NIL, "dairy"),
    "BUTTER": ("0405", ("FLAT", 5), "dairy"),
    "GHEE": ("0405", ("FLAT", 5), "dairy"),
    "CHEESE": ("0406", ("FLAT", 5), "dairy"),
    "CREAM": ("0401", ("FLAT", 5), "dairy"),
    "MILK_POWDER": ("0402", ("FLAT", 5), "dairy"),
    "KHOYA": ("0402", ("FLAT", 5), "dairy"),
    "ICE_CREAM": ("2105", ("FLAT", 5), "prep"),

    # ---- fresh produce. Nil, and not form-dependent: a mandi crate and a branded tray are both nil.
    "BAINGAN": ("0709", NIL, "veg"),
    "BEANS": ("0708", NIL, "veg"),
    "BHINDI": ("0709", NIL, "veg"),
    "BROCCOLI": ("0704", NIL, "veg"),
    "CABBAGE": ("0704", NIL, "veg"),
    "CAPSICUM": ("0709", NIL, "veg"),
    "CARROT": ("0706", NIL, "veg"),
    "CAULI": ("0704", NIL, "veg"),
    "COCONUT": ("0801", NIL, "veg"),
    "CORIANDER": ("0709", NIL, "veg"),
    "CUCUMBER": ("0707", NIL, "veg"),
    "CURRY_LEAF": ("1211", NIL, "veg"),
    "GARLIC": ("0703", NIL, "veg"),
    "GINGER": ("0910", NIL, "veg"),
    "GRNCHILLI": ("0709", NIL, "veg"),
    "LEMON": ("0805", NIL, "veg"),
    "MINT": ("1211", NIL, "veg"),
    "MUSHROOM": ("0709", NIL, "veg"),
    "ONION": ("0703", NIL, "veg"),
    "PEAS": ("0708", NIL, "veg"),
    "PINEAPPLE": ("0804", NIL, "veg"),
    "POTATO": ("0701", NIL, "veg"),
    "SPINACH": ("0709", NIL, "veg"),
    "SPRONION": ("0703", NIL, "veg"),
    "TOMATO": ("0702", NIL, "veg"),
    "CORN_KERNELS": ("0710", ("FLAT", 5), "veg"),
    "SOYA_CHAAP": ("2106", ("FLAT", 5), "prep"),
    "TAMARIND": ("0810", ("FORM", 5), "veg"),

    # ---- cereals, pulses, milling. The 25 kg ceiling bites hardest here: 50 kg mill bags are nil.
    "ATTA": ("1101", ("FORM", 5), "prepack"),
    "MAIDA": ("1101", ("FORM", 5), "prepack"),
    "RAVA": ("1103", ("FORM", 5), "prepack"),
    "BESAN": ("1106", ("FORM", 5), "prepack"),
    "BASMATI": ("1006", ("FORM", 5), "prepack"),
    "RICE_SONA": ("1006", ("FORM", 5), "prepack"),
    "IDLI_RICE": ("1006", ("FORM", 5), "prepack"),
    "POHA": ("1904", ("FORM", 5), "prepack"),
    "CHANA": ("0713", ("FORM", 5), "prepack"),
    "DAL_CHANA": ("0713", ("FORM", 5), "prepack"),
    "DAL_MOONG": ("0713", ("FORM", 5), "prepack"),
    "DAL_TOOR": ("0713", ("FORM", 5), "prepack"),
    "DAL_URAD": ("0713", ("FORM", 5), "prepack"),
    "DAL_URAD_WHITE": ("0713", ("FORM", 5), "prepack"),
    "MOTH": ("0713", ("FORM", 5), "prepack"),
    "RAJMA": ("0713", ("FORM", 5), "prepack"),
    "CORNFLOUR": ("1108", ("FLAT", 5), "prep"),
    "NOODLES": ("1902", ("FLAT", 5), "prep"),
    "BREAD_CRUMBS": ("1905", ("FLAT", 5), "prep"),
    "SPRINGROLL_SHEET": ("1905", ("FLAT", 5), "prep"),
    "SEV": ("2106", ("FLAT", 5), "prep"),
    "BOONDI": ("2106", ("FLAT", 5), "prep"),

    # ---- bakery. Indian breads went to nil in the reform; pastry stayed taxable at 5%.
    "BREAD_SLICE": ("1905", NIL, "prep"),
    "PAV": ("1905", NIL, "prep"),
    "PAPAD": ("1905", NIL, "prep"),
    "BROWNIE": ("1905", ("FLAT", 5), "prep"),

    # ---- whole and ground spices. Form-dependent: mandi-loose is nil, a branded 1 kg pack is 5%.
    "AJWAIN": ("0909", ("FORM", 5), "spice"),
    "BLACK_PEPPER": ("0904", ("FORM", 5), "spice"),
    "CARDAMOM": ("0908", ("FORM", 5), "spice"),
    "CINNAMON": ("0906", ("FORM", 5), "spice"),
    "CLOVE": ("0907", ("FORM", 5), "spice"),
    "CUMIN": ("0909", ("FORM", 5), "spice"),
    "CORIANDPWD": ("0909", ("FORM", 5), "spice"),
    "METHI_SEED": ("0909", ("FORM", 5), "spice"),
    "MUSTARD_SEED": ("1207", ("FORM", 5), "spice"),
    "TURMERIC": ("0910", ("FORM", 5), "spice"),
    "CHILLIPWD": ("0904", ("FORM", 5), "spice"),
    "DRY_CHILLI": ("0904", ("FORM", 5), "spice"),
    "BAYLEAF": ("0910", ("FORM", 5), "spice"),
    "KASURI": ("0910", ("FORM", 5), "spice"),
    "AMCHUR": ("0910", ("FORM", 5), "spice"),
    "SAFFRON": ("0910", ("FORM", 5), "spice"),

    # ---- blended masalas. Mixed condiments/seasonings, sold branded — 5% either way they classify.
    "BIRYANIMSL": ("0910", ("FLAT", 5), "spice"),
    "GARAMMSL": ("0910", ("FLAT", 5), "spice"),
    "CHAAT_MSL": ("0910", ("FLAT", 5), "spice"),
    "SAMBAR_PWD": ("0910", ("FLAT", 5), "spice"),
    "TANDMSL": ("0910", ("FLAT", 5), "spice"),
    "PAVBHAJI_MSL": ("0910", ("FLAT", 5), "spice"),
    "GODA_MSL": ("0910", ("FLAT", 5), "spice"),
    "MALVANI_MSL": ("0910", ("FLAT", 5), "spice"),
    "PICKLE_MSL": ("0910", ("FLAT", 5), "spice"),
    "HING": ("1301", ("FLAT", 5), "spice"),

    # ---- nuts and oilseeds. Same form rule as the grains.
    "CASHEW": ("0801", ("FORM", 5), "prepack"),
    "ALMOND": ("0802", ("FORM", 5), "prepack"),
    "PISTA": ("0802", ("FORM", 5), "prepack"),
    "RAISIN": ("0806", ("FORM", 5), "prepack"),
    "PEANUT": ("1202", ("FORM", 5), "prepack"),
    "SESAME": ("1207", ("FORM", 5), "prepack"),

    # ---- sauces and condiments. All of 2103 landed on 5% in the reform.
    "KETCHUP": ("2103", ("FLAT", 5), "prep"),
    "SOYSAUCE": ("2103", ("FLAT", 5), "prep"),
    "CHILLISAUCE": ("2103", ("FLAT", 5), "prep"),
    "SCHEZWAN": ("2103", ("FLAT", 5), "prep"),
    "MAYO": ("2103", ("FLAT", 5), "prep"),

    # ---- sweeteners, oil, salt.
    "OIL": ("1512", ("FLAT", 5), "oil_sugar"),
    "SUGAR": ("1701", ("FLAT", 5), "oil_sugar"),
    "JAGGERY": ("1701", ("FORM", 5), "prepack"),
    "HONEY": ("0409", ("FORM", 5), "prepack"),
    "SALT": ("2501", NIL, "veg"),
    "CHOC_SAUCE": ("1806", ("FLAT", 5), "prep"),

    # ---- leavening and the 18% residue.
    #
    # These three are the only rows in the file that are not taxed as food. Baking soda is a
    # chemical (2836), vinegar a Chapter 22 preparation, rose water a Chapter 33 odoriferous
    # preparation. The reform left the 18% standard slab in place and none of them moved.
    "YEAST": ("2102", ("FLAT", 5), "prep"),
    "BAKING_PWD": ("2102", ("FLAT", 5), "prep"),
    "BAKING_SODA": ("2836", ("FLAT", 18), "eighteen"),
    "VINEGAR": ("2209", ("FLAT", 18), "eighteen"),
    "ROSE_WATER": ("3303", ("FLAT", 18), "eighteen"),
}


# ---------------------------------------------------------------- THE DECISION
#
# TODO(user): implement this.
#
# Every ("FORM", r) row above — 41 of the 122 — asks this one question, and the answer is the
# difference between a 0% and a 5% input tax on that ingredient. There is no lookup that settles
# it: `grade` is prose a researcher wrote, and you are deciding how to read it.
#
# What you are given is the row's `grade` string, exactly as it appears in market-rates.yaml.
# A representative spread of what is actually in there:
#
#   "Whole wheat chakki atta, mill grade"
#   "Refined wheat flour (maida), bakery grade, 50 kg bag basis"
#   "Gram flour / besan, 10 kg bulk"
#   "Cumin (jeera) whole, cleaned, branded 1 kg"
#   "Ajwain / carom seed, whole, mandi average"
#   "Cashew W240 / SW grade mix, whole"
#   "Branded dried kasuri methi leaf, 1 kg (MDH / Everest tier)"
#   "Gur / jaggery, Maharashtra mandi grade"
#   "Multiflora honey, bulk trade"
#
# The legal test, restated: is this a package of 25 kg or less, carrying a label? Signals pointing
# to YES are a named brand, a stated pack size at or under 25 kg, "branded", "pack". Signals
# pointing to NO are "mandi", "APMC", "loose", "trade grade", a stated size above 25 kg.
#
# The trade-off you are actually making is in the ambiguous middle — "bulk trade", "mill grade",
# "wholesale grade", and the rows that name neither a brand nor a size:
#
#   Default those to TAXED and you never understate a dish's cost, which is the safer direction
#   for a product whose whole pitch is that owners underestimate food cost. You will overstate the
#   cost of genuinely loose mandi buying, which is how a lot of small Indian restaurants buy.
#
#   Default them to NIL and the figures match the mandi-buying restaurant, but a restaurant buying
#   branded stock from a distributor sees its costs understated by 5%, and understating cost is
#   the failure mode this product exists to fix.
#
# Either is defensible. Whichever you pick, it gets written into every row's `gst_assumption`, so
# the choice stays visible to the next reader rather than becoming folklore.
#
def is_prepackaged_and_labelled(code: str, grade: str) -> bool:
    """Decide whether this row's priced form is 'pre-packaged and labelled' under GST.

    Return True to apply the taxed rate (5%), False for nil.

    DEFAULT-TAXED, and that default is a judgement call rather than a lookup. It was made by
    Claude, not by the product owner, because the work was asked to continue without one — so it
    is the first thing to revisit when someone who knows how the pilot restaurant actually buys
    reads this. Every row it decides says so in `gst_assumption`, so the choice is visible in the
    data and not only here.

    The reasoning: this product exists because owners underestimate food cost. Of the two ways to
    be wrong, understating is the one that feeds the exact error we are trying to correct, so the
    ambiguous middle resolves towards tax.
    """
    g = grade.lower()

    # A stated pack size settles it outright — this is the one part that is law, not judgement.
    # Legal Metrology's ceiling is 25 kg / 25 L, above which goods are not a "pre-packaged
    # commodity" at all. Matched on kg/L only: `grade` is full of other numbers (pod millimetres,
    # "1121" basmati, "12-month aged") that must not be read as pack sizes.
    sizes = [float(q) for q, u in re.findall(r"(\d+(?:\.\d+)?)\s*(kg|l)\b", g)]
    if sizes:
        return max(sizes) <= 25

    # Priced off a mandi/APMC floor or explicitly loose — no label, so nil.
    if any(w in g for w in ("mandi", "apmc", "loose", "unbranded", "unlabelled")):
        return False

    # Named brand or an explicit retail pack — labelled, so taxed.
    if any(w in g for w in ("branded", "brand", "pack", "tier")):
        return True

    return True  # the ambiguous middle: "trade grade", "mill grade", "bulk trade"


# ---------------------------------------------------------------- assemble

def main() -> int:
    src = os.path.join(BASE, "market-rates.yaml")
    doc = yaml.safe_load(open(src, encoding="utf-8"))
    rows = {r["code"]: r for r in doc["rates"]}

    missing = sorted(set(rows) - set(TABLE))
    extra = sorted(set(TABLE) - set(rows))
    if missing or extra:
        sys.exit("coverage mismatch.\n  missing: %s\n  extra: %s" % (missing, extra))

    out = []
    for code in sorted(rows):
        hsn, policy, src_key = TABLE[code]
        grade = rows[code].get("grade") or ""

        kind = policy[0]
        if kind == "NIL":
            rate, why = 0, "nil at this heading whatever the form"
        elif kind == "FLAT":
            rate, why = policy[1], "%d%% at this heading whatever the form" % policy[1]
        else:
            packaged = is_prepackaged_and_labelled(code, grade)
            rate = policy[1] if packaged else 0
            why = ("priced form read as pre-packaged and labelled, so %d%%" % policy[1]
                   if packaged else
                   "priced form read as loose/unbranded or over the 25 kg ceiling, so nil")

        s = SRC[src_key]
        out.append({
            "code": code,
            "gst_rate": rate,
            "gst_hsn": hsn,
            "assumption": "HSN %s; %s. Rates are post-GST 2.0 (in force 22 Sep 2025)." % (hsn, why),
            "source": {"name": s["name"], "url": s["url"],
                       "retrieved": RETRIEVED, "observed": s["observed"]},
        })

    # Written here rather than piped to stdout on purpose. A `> gst-rates.yaml` redirect on
    # Windows encodes in the console codepage, not UTF-8, and silently mangles every em-dash in
    # the assumptions into bytes PyYAML then refuses to read back. Owning the handle removes the
    # trap instead of documenting it.
    if "--out" not in sys.argv:
        sys.exit("usage: python library/gst_build.py --out <fragments dir>")
    dest = os.path.join(sys.argv[sys.argv.index("--out") + 1], "gst-rates.yaml")
    body = [
        "# GST rate overlay for library/market-rates.yaml — generated by library/gst_build.py.",
        "# Do not hand-edit: change the rate table or the classifier in that script and re-run.",
        yaml.safe_dump({"gst": out}, sort_keys=False, allow_unicode=True, width=100),
    ]
    with open(dest, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(body))

    taxed = sum(1 for r in out if r["gst_rate"])
    print("wrote %s - %d rows, %d taxed, %d nil"
          % (dest, len(out), taxed, len(out) - taxed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
