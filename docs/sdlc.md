# Software Development Lifecycle

How this project is actually built. Two rhythms: **project phases** that run once, and a
**module loop** that repeats seventeen times. The module loop is what matters day to day.

Modules and their tasks: `docs/modules.md`.

---

# Part 1 — Project phases

## P0 · Discovery & requirements — ✅ done

Understanding the business before designing for it.

**Done:** vision document read and analysed; domain research on Indian restaurant operations
(base-driven kitchens, prep waste, the no-records reality); market and pricing anchored on food-cost
savings; scope decided (full Phase 1); stack, market and pilot access settled.

**Artefacts:** `docs/product/vision.md`, `docs/waste-model.md`, `docs/customer-experience.md`,
`docs/onboarding-cold-start.md`

**What discovery is never done proving:** that anyone will pay. That runs in parallel all the way
through — see *The non-code track* in `docs/plan/month-1.md`.

## P1 · Architecture & design — ✅ done

**Done:** 63-table schema with keys and indexes; 10 ADRs; UI conventions for four surfaces;
engineering standards; security threat model; observability and operations; testing strategy;
synthetic dataset authored and validated.

**Artefacts:** `docs/schema.md`, `docs/decisions/`, `docs/ui/conventions.md`,
`docs/engineering-standards.md`, `docs/security.md`, `docs/observability.md`,
`docs/testing-strategy.md`, `seed/`

**Exit criterion, already met:** the acceptance query in `docs/domain-model.md` is answerable from
the schema in single indexed hops.

## P2 · Planning — ✅ done (this document)

17 modules, dependency-ordered, each a vertical slice. Definition of Done agreed. Manual test format
agreed and demonstrated (`docs/manual-tests/M01-identity.md`).

## P3 · Implementation — next

The module loop below, seventeen times. Nothing else happens in this phase; new ideas become entries
in a backlog file, not scope creep.

**Gate to leave P3:** every module's Definition of Done met, including your manual pass.

## P4 · Integration & system testing

Cross-module journeys no single module owns, run at the end of each phase and again at the end:

- Order → KOT → stock consumption → cost freeze → waste → feedback → dashboard, with rupee figures
  checked against `seed/validate.py`
- All **14 planted signals** from `docs/seed-data.md` surfaced by the dashboards. If the analytics
  chain cannot find fourteen anomalies we deliberately planted, it will not find real ones.
- Full-day simulated service across all four personas
- Load test at 3× expected peak (k6)

## P5 · Deployment & release

Staging exists from **day one of P3**, not here. This phase is production: backups configured and a
**restore actually tested**, cost alerts armed, runbooks written, security checklist passed, DPDP
consent flows verified, GST invoice numbering verified across a financial-year boundary.

Release: tag, deploy, smoke test, watch for an hour. Never during service hours
(`docs/observability.md` §8).

## P6 · Operations & iteration

Monitoring, incident response, monthly restore test, post-mortems, and the first real restaurant
onboarding using `docs/onboarding-cold-start.md`.

---

# Part 2 — The module loop

This runs once per module, in order. **A step is not started until the previous one passes.**

### 1 · Spec — I write, you approve

A short spec at `docs/modules/` (one file per module, e.g. `M07-orders-spec.md`): scope, entities touched, endpoints, screens, edge cases,
acceptance criteria, and **the threat question — *what would an insider do with this?***

You approve before any code. This is the cheapest possible moment to change direction, and the
place where a wrong assumption costs minutes instead of days.

### 2 · Schema & migration
Alembic migration plus SQLAlchemy models, checked against `docs/schema.md`. Reversible, with
`downgrade()` implemented and tested. If reality demands a change to the schema doc, the doc is
updated in the same PR — the doc is never allowed to become stale.

### 3 · Backend — repository → service → API
In that order, tests written alongside rather than after. Layering rules from
`docs/engineering-standards.md` §1 are absolute.

### 4 · Automated tests — must be green
Unit, integration, query-count, plus the four generic suites. Specialist tests where the module
warrants them (property-based on money, golden tests on costing, concurrency on stock and orders).
See `docs/testing-strategy.md`.

### 5 · Frontend
Screens per `docs/ui/conventions.md`, for the right surface. Every mutation has explicit pending,
error and success states.

### 6 · Quality gate — automated, blocking
`make check`: ruff, mypy strict, eslint, tsc, prettier, full test suite, migration up→down→up,
query-count assertions, `pip-audit` + `npm audit`, secret scan. **Zero warnings.**

### 7 · My adversarial review
I review my own diff against the checklist in `docs/testing-strategy.md` Part 1 — tenant leakage,
permission placement, N+1, float money, naive datetimes, unbounded queries, trusted client prices,
PII in logs, leaky errors. Findings fixed **before** you see the module. Your time is for what I
cannot catch, not for tripping over what I could have.

### 8 · Manual test script — I write
`docs/manual-tests/MXX-<module>.md`, in the agreed format: preconditions, happy path, validation,
permissions, security probes, usability, exploratory charter.

### 9 · Your manual pass
20–40 minutes on staging. You report failures as step number + expected + saw.

### 10 · Fix and re-verify
I fix; you re-run **only the failed sections**. Every bug you find gets a regression test written
**before** the fix, so it stays fixed forever.

### 11 · Merge and deploy to staging
Squash merge, conventional commit, deploy, smoke test.

---

## Definition of Done

A module is done when **every** line is true. Not most.

**Function**
- [ ] Every acceptance criterion in the spec met
- [ ] Migration reversible; up→down→up passes on real Postgres
- [ ] `docs/schema.md` matches reality

**Tests**
- [ ] Unit test for every service method, including failure paths
- [ ] Integration test per endpoint: happy, validation, permission, not-found, conflict
- [ ] The four generic suites pass
- [ ] Query-count assertions on list and detail endpoints — no N+1
- [ ] 100% coverage on money, stock and permission paths
- [ ] Regression test for every bug found in this module

**Quality**
- [ ] `make check` clean, zero warnings
- [ ] Cyclomatic complexity ≤ 10; no function over 50 lines
- [ ] No abstraction introduced before its third occurrence
- [ ] Latency budgets met on staging with seeded data

**Security**
- [ ] Permission declared on every route; default-deny verified
- [ ] Tenant scoping through the repository layer only
- [ ] Client-supplied money never trusted
- [ ] Inputs validated with `extra="forbid"`
- [ ] No PII in logs; errors leak nothing internal

**Observability**
- [ ] Business events logged at INFO with `request_id` and `restaurant_id`
- [ ] Audit entries for anything price-, recipe-, stock- or permission-affecting

**Human**
- [ ] Manual script written
- [ ] **You have run it and every step passes**
- [ ] Exploratory charter done and findings triaged

---

## Working practices

**Branching** — `main` is always deployable. One branch per module (`feat/m07-orders`), squash
merged. Long modules split into several PRs against a module branch.

**Commits** — conventional (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`). One logical
change each.

**Pull requests** — under 400 lines of diff where possible. M07 and M13 will need splitting. PR body
states what changed, what to look at, and `EXPLAIN` output for any query over three joins.

**Code review** — I review my own diff adversarially at step 7. You review anything you want to
understand; you are never expected to review line by line, and the process does not assume you do.

**Backlog** — ideas that arrive mid-module go to `docs/backlog.md`. They do not become scope. This
is the single most important discipline for finishing anything with a vision document this large.

**Documentation** — updated in the same PR as the code. A doc updated "later" is a doc that is wrong.

---

## Risks, and what we do about them

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Scope creep from a 36-section vision doc** | **High** | Backlog file; module specs approved before code; explicit deferrals already written down |
| Timeline: ~57 days of work in a "1 month" frame | **High** | Stated plainly in `docs/modules.md`; month 1 scoped to M00–M05 + start of M07 from real arithmetic; each week ends deployable, so stopping early still leaves something real |
| No live pilot site to validate against | Medium | Synthetic data with 14 planted signals; menu photo from the contact; UAT the moment access exists |
| A tenant-isolation bug | Low / **catastrophic** | Four layers of control, generic tests over every endpoint, your manual probe D1 |
| Recipe data entry kills adoption | **High** | Starter recipe library (`docs/onboarding-cold-start.md`) — content work started early, in parallel |
| Solo-builder bus factor | Medium | Everything in git; ADRs record *why*; no undocumented tribal knowledge |
| Cloud cost surprise | Low | Billing alerts at 50/80/100%, scale-to-zero, monthly bill review |
| Burnout on an 11-week solo build | **Medium** | Modules are independently valuable; M11/M12/M14 are low-intensity fill weeks |

---

## What I need from you, and when

| When | What | Time |
|---|---|---|
| Before each module | Approve the spec | 10 min |
| After each module | Run the manual script | 20–40 min |
| Week 1 | Photo of the pilot restaurant's menu | 5 min |
| Week 1 | Ask them their food cost %, then how they know | 1 conversation |
| Ongoing | Say when something feels wrong, even vaguely | — |

That last row is worth the most. I can verify that the code does what it was told. Only you can tell
me it was told the wrong thing.
