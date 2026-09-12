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
