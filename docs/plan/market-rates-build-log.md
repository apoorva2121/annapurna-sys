# Market rates & the second tenant — build log

**Resume from here.** If a session ended mid-way, read this first, then `git log --oneline` to see
which chunks actually landed. Written after the work, so it can be trusted about the past and not
about the future.

Spec: `docs/modules/market-rates-spec.md`. Branch: `feat/m01-identity`.
Not a numbered module — a data-layer dependency that `docs/onboarding-cold-start.md` and
`library/ingredients.yaml` had both already specified and neither had built.

---

## State

| Chunk | What | State |
|---|---|---|
| A | `library/market-rates.yaml` — 122 researched prices with citations | ✅ done |
| B | `library/city-index.yaml` — 11 cities, empirically derived multipliers | ✅ done |
| C | `library/validate_rates.py` + `PRICE_PROVENANCE.md`, wired into `make check` | ✅ done |
| D | `stock_item.cost_source` — migration 0014, enum both sides, schema, docs | ✅ done |
| E | `seed/tandoor-house.yaml` + `seed/validate_tandoor_house.py` | ✅ data only |
| F | Loading Tandoor House into the database | ❌ **not started** |
| G | Audit remediation — schema v2 (`basis_city`, `as_of`, `grade`, `gst_rate`, `pack_tiers`) | ✅ done |
| H | Input GST — `gst_rate` + `gst_hsn` on all 122, post-GST-2.0 (`library/gst_build.py`) | ✅ done |

---

## Round 2 — the audit, and what it changed

An uncompromising data-quality audit was run against chunk A on 2026-09-12. It graded the dataset
**NEEDS RE-SCRAPE** and found six defects worth acting on. Every one was measured, not asserted:

| Finding | Measure | Fix |
|---|---|---|
| Geographic basis inconsistency | 29% of rows on non-Pune evidence in a Pune-baseline file | `basis_city` + ratio conversion |
| Staleness laundering | 20 rows stamped with a fetch date over evidence up to **7 months** old | `as_of` split from `retrieved` |
| Grade ambiguity | only 18% named a brand/grade; cardamom ranges **1.68×** by pod size | `grade` required |
| No landed-cost model | **zero** rows carried GST, delivery, MOQ or freight | `gst_rate` + `gst_hsn` |
| Volume tiers discarded | 18 rows had bulk breaks in free text, schema had one scalar | `pack_tiers[]` |
| One correctness defect | `ROSE_WATER` priced off **cosmetic-grade** stock for a food ingredient | re-scrape, food-grade only |

**The prioritisation was made data-driven rather than arbitrary.** The audit's action plan said
"second source for the 68 single-sourced rows". Exploding every library recipe to leaf ingredients
and weighting by cost contribution showed the top 30 ingredients carry **87.8%** of all dish cost,
and only **8** of those were single-sourced — so the real job was 8 rows, not 68. `OIL` alone is
**6.08%** of total dish cost and rested on one citation.

Re-scrape scope came out at **55 of 122 rows** (union of stale ∪ non-Pune ∪ high-impact-single ∪
grade-undecided), split into three disjoint buckets so no two workers touched the same row. The
other 67 were backfilled from evidence already in the file — their `observed` strings already named
the product form, it simply had nowhere to live.

**Threshold correction worth keeping.** The seed cross-check error bar moved 5× → 10×, derived from
the taxonomy of unit errors (quintal 100×, bag 50×, dozen 12× — the smallest possible is ~12×)
rather than picked round. At 5× it would have **failed the build on a correct, well-sourced
figure**: bulk-trade masala genuinely runs 2–5× under branded-retail masala, which is a question
about which product a restaurant buys, not an error in either number.

**One audit flag was my own false positive** — a regex reading `228314 INR/quintal` as a March-8314
date. Checked before reporting; discarded.

### Round 2 outcome — what actually landed

**All four research workers died on a shared session rate limit** before writing anything. None of
`rescrape-w1/w2/w3.yaml` or `gst-rates.yaml` exists. The session's WebSearch budget is also spent
(200/200) and does not reset with the rate limit, so re-dispatching them now would fail the same
way.

What that forced was a better division than the original plan had. **Three of the five audit
findings needed no new research at all** — the facts were already in the file, just with nowhere to
live:

- **`basis_city` for all 122** — read off each source's own text ("APMC Mumbai", "Pune, Sep 2026",
  "average across India"). 32 rows are now correctly on a non-Pune basis, and the city index
  divides by the right one instead of assuming Pune. The geography double-count is **fixed**, and
  it moved real numbers: `CINNAMON` normalises from 0.50 to 0.4386 once Mumbai's 1.14 is divided
  out, changing its seed ratio from 1.80x to 2.05x.
- **`as_of` for all 176 citations** — `merge_rates.py` now extracts the dates already quoted inside
  `observed` ("(20 May 2026)", "as of 09/09/2026", "September 10, 2026"). **52 real publication
  dates were recovered**; the remaining 124 are marked `as_of_defaulted` rather than assumed
  fresh. Staleness laundering is **fixed**, and it immediately surfaced what it was hiding:
  `CLOVE` 198 days old, `ROSE_WATER` 196, `AJWAIN` 115, `CORN_KERNELS` 103.
- **`grade` for all 122** — derived from the product names already in `observed`. **Fixed.**

**Still open, and honestly marked as such rather than papered over:**

| Gap | State |
|---|---|
| ~~GST / landed cost~~ | **closed 2026-09-12** — all 122 rows carry `gst_rate` and `gst_hsn`. See *Round 3* below |
| `ROSE_WATER` | still cosmetic-grade evidence for a food ingredient; `grade` now says so explicitly |
| 8 high-impact single-sourced rows | `OIL` (6.08% of all dish cost), `TOMATO`, `POTATO`, `CARROT`, `GINGER`, `MUSHROOM`, `CASHEW`, `CHILLIPWD` — each carries the finding in its `note` |
| 4 genuinely stale rows | dates are now honest; the prices are still February–June quotes |
| `SAFFRON` | its own evidence spans ₹330–550/g against a value of ₹220/g — recorded, unreconciled |

---

## Round 3 — input GST, and a tax reform that invalidated memory

The largest gap from round 2 is closed. All 122 rows carry `gst_rate` and `gst_hsn`, so landed
cost is computable for the first time: `inr_per_base_unit * (1 + gst_rate/100)`.

**The finding that matters most here is that recall was unusable.** GST 2.0 — 56th Council,
notification 09/2025-CTR of 17 Sep 2025, in force **22 Sep 2025** — abolished the 12% and 28%
slabs outright. Ghee, butter and cheese left 12%; sauces left 12%; ice cream left 18%; paneer and
UHT milk went to **nil**. Any rate filled in from pre-reform knowledge would have been wrong on
roughly a third of this file, and `validate_rates.py` would have passed it silently, because `12`
is still a member of its `GST_RATES` legal-value set. Every rate here was researched, and the
distribution table in `PRICE_PROVENANCE.md` now shows **12% = 0 and 28% = 0**, which is the
visible evidence that the reform was applied rather than a stale table copied.

**A rate is not a property of an ingredient — it is a property of a heading plus a form.** Under
GST most agricultural commodities are nil when loose or unbranded and 5% when "pre-packaged and
labelled", a phrase that borrows its definition from the Legal Metrology Act, 2009 — including a
**25 kg / 25 L ceiling** above which goods are not a pre-packaged commodity at all. So a 50 kg
mill bag of maida is nil while a 10 kg labelled sack of besan is 5%, which inverts the intuition
that buying bigger means paying more tax. This bites here because the file's declared basis is
*wholesale / trade*, and `grade` already recorded which form each row was priced in — so the
answer was derivable from evidence in the file, exactly as `basis_city`, `as_of` and `grade` were
in round 2. No new research was needed for the split, only for the rates themselves.

`library/gst_build.py` holds the derivation: 122 codes → HSN heading, 9 cited rate rules, and one
classifier that reads the form off `grade`. It is a generator rather than 122 hand-typed literals
because literals record answers and destroy reasoning — a later reader could not tell a researched
rate from a guessed one. Re-run it when the law next changes and every row moves together.

| Policy | Rows | Meaning |
|---|---|---|
| nil at the heading | 39 | fresh produce, fresh/chilled meat, eggs, salt, Indian breads, papad |
| flat-rated | 42 | processed goods where packaging is not the question — dairy fats, sauces, oil, sugar |
| form-dependent | 41 | the classifier decides: 10 read as loose/nil, 31 as pre-packaged |

Final distribution: **49 rows nil · 70 at 5% · 3 at 18%.** The three at 18% are the only rows in
the file not taxed as food — `BAKING_SODA` (2836, a chemical), `VINEGAR` (2209) and `ROSE_WATER`
(3303, a Chapter 33 odoriferous preparation). `ROSE_WATER` sitting outside the food slabs is
consistent with its still-unresolved cosmetic-grade sourcing rather than papering over it.

**One decision was made by Claude and not by the product owner, and should be revisited.** The
ambiguous middle — `"bulk trade"`, `"mill grade"`, `"trade grade"`, rows naming neither a brand
nor a size — defaults to **taxed**. The reasoning: this product exists because owners underestimate
food cost, so of the two ways to be wrong, understating feeds the exact error the product corrects.
The owner was asked and the work was told to continue without an answer, so the default stands and
every row it decided says so in its own `gst_assumption`. Anyone who knows how the pilot restaurant
actually buys should overturn it in `is_prepackaged_and_labelled()`; it is a one-line change and a
re-run.

### RESUME HERE — state after round 3

**The tree is GREEN.** `make check` exits 0. Warnings dropped **20 → 18** as the
`122 of 122 rates have no gst_rate` warning cleared. Nothing is half-migrated.

**Research fragments live in a session-scoped scratchpad a new session cannot guess.** Round 2's
files are still on disk at:

```
C:\Users\apoor\AppData\Local\Temp\claude\C--dev-restaurant-os\c61da976-0d9e-4164-9739-dc90dd1f0713\scratchpad\
```

| File | Contents |
|---|---|
| `rates-*.yaml` (4) | base layer, 122 rows — the original research |
| `backfill-untouched.yaml` | 67 rows: `basis_city`, `grade`, 9 `pack_tiers` |
| `backfill-pending-rescrape.yaml` | 55 rows: same fields, plus the audit findings as `note_extra` |

They are only needed to *re-merge*, and `gst-rates.yaml` no longer needs to be among them —
`library/gst_build.py --out <dir>` regenerates it into any fragments directory on demand, which is
why it moved into the repo. `library/market-rates.yaml` is committed and complete, so losing the
scratchpad costs nothing except the ability to re-run the merge without re-deriving the backfills.

**Next actions, in value order** — all four need WebSearch:

1. **`ROSE_WATER`** — still cosmetic-grade evidence for a food ingredient. Correctness, not polish.
   Re-pricing it may also move it off 3303 and into a food heading, changing its 18%.
2. **Second source for the 8 high-impact single-sourced rows**: `OIL` (6.08% of all dish cost),
   `CASHEW`, `TOMATO`, `CHILLIPWD`, `POTATO`, `CARROT`, `MUSHROOM`, `GINGER`.
3. **Four genuinely stale prices**: `CLOVE` (198 days), `ROSE_WATER` (196), `AJWAIN` (115),
   `CORN_KERNELS` (103).
4. **`SAFFRON`** — its own evidence spans ₹330–550/g against a value of ₹220/g.

Then: `python library/gst_build.py --out <dir>` (only if a heading or the classifier changed) →
`python library/merge_rates.py --fragments <dir>` →
`python library/validate_rates.py --write-provenance` →
`python seed/validate_tandoor_house.py` → `make check > check.log 2>&1; echo $?` (**read the
number, not the tail**) → commit.

**Not blocked by search:** chunk F below, which is the honest next step for the tenant itself.

Re-scrape briefs are reconstructable from the defect tables above plus
`docs/modules/market-rates-spec.md` § What a rate row is, which carries the full v2 schema.

**E is data, not a seeded tenant.** The YAML is authored and validated in `make check`, but nothing
in `backend/app/seed/` reads it. See *What F involves* below — that is the honest next step.

---

## How the research was actually done

Three Sonnet 5 subagents researched in parallel by category (spice 44, meat+dairy 20,
grain+bakery+sweet 29); the main session did veg+oil (29) and the city basket. Opus 5 adjudicated.
Workers wrote YAML fragments to a scratchpad and returned only summaries, so 122 rows of citations
never entered the coordinating context.

**The adjudication pass is what made this worth doing**, and it caught three distinct classes of
problem that no amount of careful prompting prevented:

1. **Systematic product-form error.** Every seed-overlapping grain and spice came back *lower* than
   seed — 20 rows, all one direction. Random error scatters. The cause was raw commodity priced
   where the library item is a processed good: maize meal for `CORNFLOUR`, coriander seed for
   `CORIANDPWD`, turmeric finger for `TURMERIC`, and for `KASURI` a listing 4.8x under the real
   branded product. Both workers were sent back with specifics.
2. **A bug in the merge script, not the data.** The merge emitted `sources` as YAML *flow* mappings
   while quoting only for block context, so a comma inside `observed` truncated the value at write
   time — 23 fields silently lost their price. Found because a worker **refused** a correction,
   checked the file on disk, and demonstrated the premise was false. See *On coordination* below.
3. **A threshold that would have rejected correct data.** The seed cross-check first failed the
   build at 5x. The research then found bulk-trade masala genuinely running 2-5x under
   branded-retail masala — a real disagreement, not an error. Raised to 10x, which is now derived
   from the taxonomy of unit mistakes (quintal 100x, bag 50x, dozen 12x) rather than picked round.

## On coordination, and a real cost of it

All three workers treated mid-task `SendMessage` guidance as **untrusted**, and independently
verified before acting. Two reported the channel as a possible injection attempt: messages arrive
spliced in after a tool result rather than as a conversation turn, which is indistinguishable in
shape from a prompt-injection attempt.

That caution was correct twice and expensive once:

- It **caught the flow-mapping bug** — a worker refused to "fix" 16 fields, proved they were
  already correct on disk, and noted that the example figure in my message matched no source it
  had fetched. Complying would have overwritten cited data with a fabricated number.
- It correctly discounted relayed Hyperpure paneer figures that had moved intraday between my
  fetch and theirs.
- It cost round trips: one worker re-derived an entire re-check from scratch rather than trust the
  seven specifics it was handed, and reached broadly the same place.

**Lesson for the next time this pattern is used:** put verifiable anchors in the brief up front
(the seed cross-check, the unit table), not in follow-up messages. A worker can check a brief
against the world; it cannot check a mid-task assertion against anything, and is right not to try.

## Verification

- `make check` — the gate, run whole with its exit code read, not its tail.
- Backend 544 tests, 96.32% coverage · frontend 174 tests · ruff, mypy, eslint, tsc all clean.
- Five validators in `audit-docs`, all exit 0: `audit_docs`, `seed/validate`, `library/validate`,
  `library/validate_rates`, `seed/validate_tandoor_house`.
- 61 codes cross-checked against `seed/`: **0 errors, 41 clean, 20 warnings**, all warnings being
  documented content disagreements. Independent agreement worth recording — `OIL` 1.00x,
  `CHKN_BONELESS` 0.99x, `GRNCHILLI` 0.97x, `GHEE` 0.95x, `CREAM` 1.04x, `MUTTON` 1.05x.
- Tandoor House costs at **30.5%** theoretical against Spice Garden's 25.6% — the intended
  contrast, computed through the researched rates.

**Not verified:** migration 0014 has never been applied to a live database. Docker is not available
in this environment (see the local-env memory), so the migration is checked only for import and
revision chaining. `make migrate` on a real Postgres is an open risk.

## What F involves

Three parts that should land in one commit, because splitting them leaves the tree inconsistent:

1. Parameterise `backend/app/seed/{menu,setup,stock}.py` over a list of restaurants. They hold
   `_MENU_FILE`, `_OPERATIONS_FILE` and `_FOR_RESTAURANT` as module constants pinned to Spice
   Garden.
2. A library-composition path: resolve `{ref, variant}` into `recipe` / `recipe_line` rows from
   `library/dishes.yaml`, carrying the library `confidence` tier onto the row. This is the same
   mechanism `docs/onboarding-cold-start.md` describes for a real restaurant, so building it here
   is building the cold-start flow, not a seeding shortcut.
3. Tandoor House's staff. It has two employees and needs a chef, kitchen hands and waiters.
   Deliberately not added yet: **"19 employees" is asserted in `docs/seed-data.md`,
   `docs/manual-tests/M01-identity.md`, `docs/plan/m01-build-log.md`,
   `backend/app/seed/__main__.py` and two tests**, so the roster must move with the loader.

## Open questions for a human

- **Onion was mid-spike** during the research: 35 INR/kg on 6 Sep, 56 on 12 Sep, same source. A
  single-day snapshot of a volatile commodity enshrines a moment. Recorded in the row's note; the
  next refresh should decide between a snapshot and a trailing median.
- **20 seed warnings** are real disagreements, not errors, and several suggest `seed/` is the stale
  side rather than the research — `SPRONION` at 1.86x especially. Reconciling them changes the
  golden food-cost figure, so it is a deliberate decision and not a cleanup.
- **City `exceptions` are recorded, not applied.** Coastal seafood is the known-wrong case.
