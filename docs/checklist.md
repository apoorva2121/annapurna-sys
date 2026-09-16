# Master Checklist

The live tracker. Process behind it: `docs/sdlc.md`. Module detail: `docs/modules.md`.

Marking rules — a box is ticked only when the thing is **actually true**, never when it is nearly
true. `[~]` means in progress. A module's box is ticked only when its full Definition of Done is
met, **including your manual pass**.

Last updated: 2026-09-16

---

## Phases

- [x] **P0 · Discovery & requirements**
- [x] **P1 · Architecture & design**
- [x] **P2 · Planning**
- [ ] **P3 · Implementation** — 0 / 18 modules complete (M00–M04 built; each waits on a manual pass)
- [ ] **P4 · Integration & system testing**
- [ ] **P5 · Deployment & release**
- [ ] **P6 · Operations & iteration**

## Blockers — nothing in P3 starts until these clear

- [x] **Docker Desktop installed and running** (hard blocker for M00) — Docker 29.7.2, Compose v5.5.1, verified 2026-09-08
- [ ] GitHub remote configured
- [ ] GitHub auth fixed (MCP currently fails: `Authorization header is badly formatted`)
- [ ] Cloud accounts: GCP **or** Neon · Cloudflare · Sentry *(needed by end of week 1)*

---

## P3 · Modules

Legend: **S**pec approved · **M**igration · **B**ackend · **T**ests green · **F**rontend ·
**G**ate (`make check`) · **R**eview (adversarial) · **X**manual script written · **U**ser pass · **D**one

| Module | Est | S | M | B | T | F | G | R | X | U | D |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M00 Foundation | 1d | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [ ] |
| M01 Identity, Roles & Permissions | 3d | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [x] | [ ] | [ ] |
| M02 Restaurant Setup | 2d | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [ ] | [ ] |
| M03 Menu | 4d | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [ ] | [ ] |
| M04 Stock Items & Recipes | 5d | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [ ] | [ ] |
| M05 Inventory Ledger | 4d | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x]† | [ ] |
| M06 Procurement `[1.5]` | 3d | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [ ] | [ ] |
| M07 Orders / POS | 7d | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| M08 Kitchen / KOT | 4d | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [x] | [~] | [ ] |
| M09 Waste | 2d | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| M10 Customers, Feedback & Guest App | 4d | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| M11 Communication & Tasks | 4d | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| M12 Shifts | 2d | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| M13 Dashboards & Reports | 5d | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| M14 Audit & Notifications | 3d | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| M15 Seed Generator & Demo | 3d | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| M17 Workload Fairness & Recognition | 5d | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| M18 Compliance Risk Alarms | 4d | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| M16 Hardening & Production | 4d | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |

‡ **M08's user pass is partial, not accepted.** The owner answered the one question no test
can reach — section B of `docs/manual-tests/M08-kitchen.md`, the two-metre readability: *"chef can
do it"* (2026-09-16). That closes the section this module lived or died by. Sections A, C, D, E, F,
G and the H charter are unrun, so the column is `[~]` rather than `[x]`: the mark means "you have
run it and every step passes", and this is one section of eight.

**Its `S` column is ticked by delegation, not by a spec review.** The owner's instruction was
"continue with m08, m09, run autonomously", which is approval to proceed without the per-module
sign-off `docs/sdlc.md` step 1 asks for. Recorded here rather than left to look like a review that
happened.

**One Definition-of-Done line is knowingly unmet even with `G` ticked:** "latency budgets met on
staging with seeded data". Staging does not exist — the cloud-account blocker above is still open —
so the KDS's 50 ms budget is measured at a median of 28 ms on a development laptop and verified
nowhere. `docs/plan/m08-build-log.md` has the numbers.

† **M05's user pass was *accepted*, not run.** The owner approved it on 2026-09-13 without
working through `docs/manual-tests/M05-inventory.md`, to unblock M07's settlement path. Recorded
this way rather than as a plain tick because the column means "you have run it and every step
passes", and a checklist that overstates what was checked is the exact failure this project spent
R9 building a gate against. The script stays valid and unrun; **section B2 in particular is still
open** — whether the negative-stock banner reads to a manager as information or as an error is a
judgement no test can make.

**67 days total.** Month 1 target: M00–M05 complete, M07 begun.

**M01's row is stale rather than accurate** — the module is built and its tests are in the suite,
but nobody has re-verified each column since, so the boxes are left as they were found rather than
ticked on inference. Marking rules above: a box is ticked only when the thing is actually true.

---

## Standing gates — re-checked every module, never assumed

- [ ] Tenant isolation suite passes across **every** registered staff route
- [ ] Permission matrix suite passes for every role × route
- [ ] Persona separation: no guest token reaches any staff route
- [ ] Every route declares a required permission (default-deny)
- [ ] Query-count assertions in place — no N+1
- [ ] `make check` clean, zero warnings
- [ ] No PII in logs (redaction test passes)
- [ ] Docs updated in the same PR as the code

---

## P4 · Integration & system testing

- [ ] Order → KOT → stock consumption → cost freeze → waste → feedback → dashboard, end to end
- [ ] Rupee figures match `seed/validate.py` exactly
- [ ] All **14 planted signals** surfaced by the dashboards
- [ ] Full-day simulated service, all four personas
- [ ] Load test at 3× expected peak (k6)
- [ ] Latency budgets met (KDS 50ms, settle 400ms, dashboard 800ms)

## P5 · Deployment & release

- [ ] `docs/manual-tests/security-checklist.md` — all 🔴 items pass
- [ ] Backups configured, **restore actually tested** into a scratch DB
- [ ] `docs/runbooks/restore.md` written and followed once
- [ ] Cost alerts armed (50 / 80 / 100%)
- [ ] DPDP consent + export + erasure flows verified
- [ ] GST invoice numbering verified across a financial-year boundary
- [ ] Production deploy, outside service hours

## P6 · Operations

- [ ] Monitoring and alerting live
- [ ] Monthly restore test in the calendar
- [ ] First real restaurant onboarded via `docs/onboarding-cold-start.md`

---

## Non-code track — parallel, blocks nothing

- [ ] Photo of the pilot restaurant's printed menu
- [ ] Ask them their food cost %, then *"how do you know?"* — write down the answer
- [x] Starter recipe library started (target ~200 dishes; `seed/` is the first 11) — `library/`, 223 dishes, 2026-09-12
- [ ] A chef reviews the library's `estimated` tier (`library/PROVENANCE.md`) — during pilot onboarding
- [ ] Pricing drafted (anchor: ~₹95,000/month gap on ₹15.5L revenue)
- [ ] Decide reward types for M17 (cash / leave / shift preference / recognition)
