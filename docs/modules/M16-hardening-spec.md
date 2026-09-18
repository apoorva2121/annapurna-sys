# M16 · Hardening & Production — Module Spec

**Depends on** M00–M15 **and, per `docs/modules.md`, M17 and M18 — which do not exist.**
**Status** — spec written 2026-09-19, before any code, per `docs/sdlc.md` step 1.
Build log: `docs/plan/m16-build-log.md`.

Tables: none. Endpoints: none new. Screens: none new.
Deliverables: a security checklist actually run, a load test, a **tested** restore, runbooks, cost
alerts, the DPDP flows verified, GST numbering verified across a financial-year boundary, and a
production deploy.

---

## The dependency this module cannot meet, and what is done about it

`docs/modules.md` gives M16 the dependency "M00–M15, M17, M18 (everything)", and that is right:
hardening is the last thing you do, because hardening something you are about to change twice is
work you will do again.

**M17 (Workload & Fairness) and M18 (Compliance Alarms) are not built.** So this module cannot be
what that line describes, and pretending otherwise would be the worst available outcome — a
checklist marked complete against a product that is not the product that ships.

**What this module does instead, stated so the owner can overrule it:** harden M00–M15 completely
and record, in the build log and in `docs/checklist.md`, that **M17 and M18 each require their own
pass of sections 1, 2, 3 and 7 of the security checklist before they go to production**. Every item
that is genuinely about the platform — backups, restore, cost alerts, deploy, rate limits, the load
test — is done once and holds. Every item that is about a *surface* is done for the surfaces that
exist, and the two that do not exist yet are named rather than assumed.

The alternative — wait — costs the pilot a working system for two modules that are, by the
dependency graph's own note, "the natural fill for any week where a critical-path module is
blocked". That is a worse trade than a named gap.

---

## Research — what binds this module

**`docs/manual-tests/security-checklist.md` already exists and has never been run in full.** It is
90 minutes and ten sections, with 🔴 stops. Running it *is* a deliverable, not preparation for one.

**`docs/checklist.md` P4–P6 is the definition of done for this module** and is more specific than
`docs/modules.md`: the latency budgets (KDS 50 ms, settle 400 ms, dashboard 800 ms), the 3× peak
load test, the restore into a scratch database, the cost alerts at 50/80/100%, and the financial-year
boundary.

**R7 already deployed staging** (`docs/plan/` and the memory of 2026-09-18): one origin, bootstrap,
`smoke-prod`, and the pipeline. So "production deploy" here is the second use of a path that has
been walked, not the first.

**`docs/compliance-rules.md` binds the DPDP and GST items**, and the first rule binds how they are
checked: never fill an Indian rate, threshold or commencement date from memory. Every compliance
item in this module cites its instrument or it is not done.

**`docs/audit/remediation-plan.md`'s state table is the source of truth** for what is still open
from the 2026-09-11 audit. This module does not re-derive it; it reads it and closes what is left.

---

## The decisions that matter

### 1 · Every checklist item is either passed, failed with a ticket, or **named as not applicable**

A checklist with blank rows is a checklist nobody ran. Three outcomes, and the third one carries a
sentence: *"2.8 MFA works for owner and admin — **not applicable**: MFA is not built; `user_account.
mfa_secret` exists and nothing writes it. Tracked as …"*

That is more honest than a tick, and more useful than a blank.

### 2 · The load test measures the budgets that already exist, and does not invent new ones

`docs/checklist.md` names three: KDS 50 ms, settle 400 ms, dashboard 800 ms. M13 measured the
dashboard at 16–32 ms on a laptop and said the product's budget is verified on staging; M08 made
the same split for the rail. **This module is where "verified on staging" stops being a promise.**

k6 against staging, on M15's generated data, at 3× the expected peak — which for Spice Garden's
~190 covers on a Saturday is roughly 570 covers of traffic, not an abstract number of requests per
second. A budget missed is a finding with its measurement attached, not a reason to raise the
budget.

### 3 · The restore is tested by restoring, into a database nobody minds losing

*"Backups configured"* is not a deliverable; **a restore that somebody performed and timed** is.
`docs/runbooks/restore.md` exists and has never been followed. This module follows it, records how
long it took and what was confusing, and fixes the runbook where it was wrong — because a runbook
first read during an incident is a runbook written for the wrong reader.

### 4 · The GST financial-year boundary is tested by crossing one

`invoice.sequence` is gapless *per financial year*, and India's runs April to March. The test is not
"read the code"; it is: settle a bill dated 31 March, settle another dated 1 April, and assert the
second is sequence 1 of the new year rather than the next number of the old one. M15's generator
can produce exactly that pair.

### 5 · DPDP is verified as three flows, and one of them is expected to fail

Consent, export and erasure. M10 built consent and erasure; **export does not exist**, and the
DPDP right to access is part of the same Act. This module verifies the two that exist, states
plainly that the third does not, and puts it where the owner will see it rather than inside a
checklist row.

### 6 · Nothing in this module changes behaviour without a test

Hardening that alters what the product does is not hardening. Where a finding requires a code
change — a missing rate limit, a header, a permission — it lands with a regression test written
first, the way every other fix in this project has.

---

## Not in scope

- **M17 and M18's own hardening.** Named above, and recorded in `docs/checklist.md` rather than
  left implicit.
- **A DPDP export flow.** It is a feature, not a hardening task, and building it inside a hardening
  module is how a hardening module stops being finishable.
- **MFA.** The column exists and nothing writes it; that is a module of its own.
- **A penetration test by a third party.** Worth doing before a second customer; it is a purchase,
  not a chunk.

---

## Acceptance criteria

1. Every row of `docs/manual-tests/security-checklist.md` carries a pass, a fail with a ticket, or
   a stated not-applicable. No blanks.
2. Every 🔴 row passes.
3. k6 runs at 3× peak against staging on generated data, and the three latency budgets are reported
   with their measurements — met or missed.
4. A restore into a scratch database is performed and timed, and `docs/runbooks/restore.md` is
   corrected where it was wrong.
5. Cost alerts are armed at 50/80/100% and one is fired deliberately to prove it arrives.
6. A bill dated 31 March and a bill dated 1 April produce sequence *n* of one financial year and
   sequence 1 of the next, asserted by a test.
7. Consent and erasure are verified end to end; the absence of export is recorded where the owner
   will read it.
8. `docs/checklist.md` P4–P6 is either ticked or carries a named reason.
9. The production deploy runs outside service hours, from the pipeline R7 built, with `smoke-prod`
   green afterwards.
10. `make check` clean, and the gate's own runtime recorded — it is now the slowest thing in the
    project and the build log should say so.

---

## Chunks — three PRs against `feat/m16-hardening`

**A · The checklist and what it finds.** Run all ten sections. Fix what it finds, each with a
regression test. Ends with every row filled in.

**B · The measurements.** k6 at 3× peak, the three budgets, the restore, the cost alerts, the
financial-year boundary test.

**C · Production.** The deploy, `smoke-prod`, the runbooks, and `docs/checklist.md` closed out with
M17 and M18's gaps named. Ends with `make check` clean.
