# M16 · Hardening & Production — Module Spec

**Depends on** M00–M18. **The dependency is now met** — see the revision note below.
**Status** — spec written 2026-09-19 before any code, per `docs/sdlc.md` step 1; **revised
2026-09-19** after M17 and M18 shipped. Build log: `docs/plan/m16-build-log.md`.

Tables: none. Endpoints: none new. Screens: none new.
Deliverables: a security checklist actually run, a load test, a **tested** restore, runbooks, cost
alerts, the DPDP flows verified, GST numbering verified across a financial-year boundary, and a
production deploy.

---

## Revision note · the dependency is now met, and a second one appeared

The first draft of this spec opened by saying M16 could not be what `docs/modules.md` describes,
because M17 and M18 did not exist — and proposed hardening M00–M15 with the gap named. **That is no
longer the situation.** M17 shipped on 2026-09-19 (five tables, seven routes, three screens) and
M18 the same day (two tables, six routes, two screens, ten rules). So the module can be what the
dependency graph asks for: the whole product, hardened once.

Two consequences, and the second is the one that matters:

**M17 and M18 are in scope for every section of the security checklist**, not named as gaps. Their
surfaces are exactly the kind the checklist is about — M17 holds what people are paid against, M18
holds what an owner would hand an inspector.

**A second, harder dependency replaced the first one: this module needs infrastructure access that
an autonomous session does not have.** The load test, the tested restore, the cost alerts and the
production deploy all require a live GCP console session; `docs/plan/r7-deploy-prep.md` and the
2026-09-18 staging note record that the pipeline was built and rehearsed and then blocked on
exactly this. So the module splits, and the split is stated here rather than discovered halfway:

| Part | Who |
|---|---|
| The security checklist's code- and config-inspectable rows | **Buildable now** — read the code, record the finding, fix with a regression test |
| The financial-year boundary test | **Buildable now** — it is a test, and M15's generator produces the pair |
| The k6 script, its thresholds and its runbook | **Writable now**, runnable only against staging |
| The load test run, the restore, the cost alerts, the deploy | **Owner's console.** Named, with the exact commands, not attempted |

A checklist row ticked without being run is worse than a blank one, so nothing in the second half
is marked done on the strength of having read the configuration that would produce it.

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

### 5 · DPDP is verified as three flows, and all three exist

Consent, export and erasure. **The first draft of this spec said export did not exist. It was
wrong** — `GET /staff/customers/{id}/export` has been there since M10, is audited, is per-customer
with no bulk version in any role, and returns the customer, their consent history and their order
history in one response. Written down because a spec that names a gap which is not there sends a
module looking for work, and because the correction is the kind that would otherwise be quietly
dropped.

So this module verifies three flows end to end rather than two and an apology. What it must not do
is tick 9.1–9.5 by reading the code: consent *not pre-ticked* and erasure *retaining the revenue*
are claims about what a person sees and what a total says, and those are run.

### 6 · Nothing in this module changes behaviour without a test

Hardening that alters what the product does is not hardening. Where a finding requires a code
change — a missing rate limit, a header, a permission — it lands with a regression test written
first, the way every other fix in this project has.

---

## Not in scope

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
11. **M17's and M18's surfaces are covered by sections 1, 2, 3 and 7 like every other module's**,
    rather than named as a gap. The first draft of this spec planned to defer them; they exist now,
    and deferring a module that shipped the same week would be a gap invented rather than found.
12. **Every item requiring a console session is written as the exact command to run**, with the
    expected output, rather than as an instruction to go and do it. A runbook step that says
    "configure cost alerts" is a step somebody performs differently each time.

---

## Chunks — three PRs against `feat/m16-hardening`

**A · The checklist and what it finds.** Run every section that can be run against the code and
the configuration — which, on inspection, is most of them. Fix what it finds, each with a
regression test written first. Ends with every row carrying a pass, a fail with a ticket, a stated
not-applicable, or **"requires a console session"** naming the command.

**B · What can be measured here.** The financial-year boundary test, the k6 script with its
thresholds expressed as the three existing budgets, and the restore runbook read line by line
against what the pipeline actually builds.

**C · The owner's half, prepared.** The deploy, `smoke-prod`, the cost alerts and the restore, each
written as the command to run and the output to expect, with `docs/checklist.md` marking them
pending a session rather than ticked. Ends with `make check` clean and the gate's runtime recorded.
