# External review — protocol, and the standing reply to the 2026-09-11 audit

**Who this is for.** The next external reviewer, and the builder session that receives its findings.
It exists so a review does not start from zero every time: it records what the last one got right,
what was acted on, what was deliberately deferred and why, and what this project wants weighted
differently next time.

**Read this after** `docs/audit/2026-09-11-findings.md` and before writing new findings.

---

## 1 · The arrangement

An external reviewer (a fresh session, different model, no build log) reviews the codebase
**after each module's code is complete and before the human's manual pass.** That is the moment the
code is finished enough to judge and still cheap to change. Roughly every three to four days
through M02–M05, but the trigger is the module boundary, not the calendar — reviewing a half-built
module produces findings about code that is about to change anyway.

**What the reviewer gets:** the repository, `docs/security.md`, `docs/engineering-guardrails.md`,
this file, and the diff for the module. **Not** the build log — the point is a reader with no
inherited intent. `docs/engineering-guardrails.md` §6 of the AI-pairing protocol is where this
practice comes from.

**Why it is worth the cost.** On M01 the author reviewed the diff adversarially and found three
defects. An independent reviewer then found five more, including a cross-tenant account lockout any
trial account could trigger. A second audit then found three more, including one where the author
had fixed *half* of a bug and not noticed the other half. The pattern across all three rounds:

> Three of the five, and two of the three, were hidden behind something that **asserted** safety
> rather than provided it — a confident docstring on dead code, a flag named `is_demo`, a pair of
> methods that looked symmetric. Reading for intent is how those survive. A cold reader has no
> intent to read for.

---

## 2 · Verdict on the 2026-09-11 audit

**Quality: high. Kept, acted on, and the arrangement continues because of it.**

Three of its sharpest claims were verified against the source before any of this was accepted:

| Finding | Verified how | Verdict |
|---|---|---|
| P1-1b — replay revocation rolled back | `refresh()` calls `_handle_replay()` then raises; the only `commit()` in `auth.py` was the one added for the lockout | **True.** The author had found and fixed the lockout half of this bug independently and missed the replay half entirely. |
| P1-2 — branch-local seniority guards a global account | `_rank_of` resolves rank at `actor.restaurant_id` | **True.** Real cross-branch takeover. |
| P1-3 — the deployed app cannot sign in | `frontend/Dockerfile` nginx config has `location /assets/` and `location /`, no `/api/` | **True.** In the runtime image `fetch('/api/v1/…')` returns `index.html` with a 200. |

The most valuable *rule* the audit produced is **G-2** — the test harness must reproduce production
transaction boundaries. Until that is true, no security test in this project certifies anything, and
the defect it was derived from was invisible to 262 passing tests. **G-17** (two-branch, two-org
fixture) is the same insight applied to fixtures. Both are load-bearing and were adopted without
argument.

---

## 3 · Where this project agreed, and acted

| Chunk | Finding | Why it is being done now |
|---|---|---|
| R1 | P1-1, and the harness | Everything downstream inherits the harness. Fix once, or be wrong in seventeen modules. |
| R2 | P1-2, P1-6 | A live security hole, and it establishes the two-branch fixture every later identity test needs. |
| M9 (part of R8) | No lockfile | Unpinned dependencies already broke this project once — the FastAPI 0.141 routing break recorded in the M01 build log is exactly this class. |
| P1-4, mitigation only | Sentry PII | One line in `.env.example`: `SENTRY_DSN` stays unset until R3 lands. The finding is correct; the *exposure* is zero while the DSN is blank. |

---

## 4 · Where this project deferred, and the trigger that un-defers each

**Nothing here is rejected.** Each is real and each has a named trigger. This table is the record so
none of it is lost — it is the answer to "what did we decide not to do yet, and when does that
change?"

| Item | Deferred until | Reasoning |
|---|---|---|
| **R3** — Sentry scrubbing, redaction | The deploy, or the day `SENTRY_DSN` is set — whichever is first | The vulnerability requires a configured DSN. There is none, and there is no deployment. A one-line guard in `.env.example` buys the same safety today for a fraction of the cost. |
| **R4** — one origin, prod smoke, headers | Together with R7 | R4's code **cannot be verified without deploying it**. Splitting them means writing an origin fix nobody can prove. They are one piece of work. |
| **R5** — lockout redesign, plan enforcement | A public URL exists | Every threat here needs an attacker who can reach the service. Nobody can. When it lands, see §5 for the scope cut. |
| **R6** — identifier normalisation, rotation grace | Real staff on real restaurant WiFi | The rotation-grace bug bites when two tabs or a retried request race. Single-developer use never produces it. Normalisation is cheap and can ride along with M02 if convenient. |
| **R7** — staging on GCP | Its own session, with the human present | Half of it is console work a model cannot do: billing, Workload Identity, Secret Manager. Making M02 wait on infrastructure is how staging slips a fourth time. |
| **R9** — `audit_guardrails.py` as a gate | M05, or the day a second person joins | Tooling to mechanically enforce rules on a two-module codebase with one developer who is in the room. The value scales with team size and codebase age; both are currently near zero. The guardrails *document* is valuable now; mechanising it is premature. |
| **D8** — split `services/employee.py` (444 lines vs a 400 line rule) | Last, or never | Lowest value item in the plan, real churn risk across security-critical code. |
| **P1-9** — argon2 off the event loop | Measured load, or M08 | Needs concurrency to matter. Currently single-digit users, all of them the developer. Cheap when it comes; pointless now. |
| **P1-10** — `organization.plan` enforcement | Paying customers | There is no billing and no plan to enforce. |

---

## 5 · Where this project disagreed, with reasoning

These are not deferrals. The recommendation itself is contested.

**P1-5 / R5 — do the per-IP budget, not the lockout redesign.**
The DoS is real: five guesses lock an owner out mid-service, from any IP. But replacing the hard
lock with progressive per-identifier delay reverses a decision the human already made and recorded
(M01 spec, open decision 3: auto-unlock after 15 minutes, owner and admin can clear instantly). A
per-IP budget closes the denial-of-service while keeping the semantics that were chosen
deliberately. The full redesign adds a table, a migration and a sweep job to solve a problem the
smaller fix already solves.

**M12 — do not delete the permissions block from `seed/organization.yaml`.**
The finding is right that two catalogues, one of them ignored, is a defect. But that YAML block is
the P1 design for all 47 permissions across M03–M17; `permissions.json` holds only M01's seven.
Deleting it discards design work that later modules need. Correct remedy: keep it, label it
explicitly as the forward design, and add a test asserting `permissions.json` is a subset of it.
Same drift closed, nothing lost.

---

## 6 · What this project wants weighted differently next time

This is the substantive note, and it is the one thing the 2026-09-11 audit got wrong at the level of
emphasis rather than fact.

**The audit spent 480 lines on engineering risk and ten on commercial risk.** Its final section
contains three observations worth more to the business than chunks R3–R9 combined:

- the prep-sheet loop — the feature the entire waste model exists to deliver — **has no module number**
- the dish-margin screen should be in M04, not M13
- M11 and M17 can move to Phase 2, returning ~7 days to the critical path

Those were footnotes. They should have been findings.

The context a reviewer needs in order to weight correctly:

1. **This product has no users, no deployment and no paying customer.** Threats requiring an
   attacker who can reach the service are real but not urgent. Say so explicitly when filing them.
2. **The stated top risks are scope creep and the timeline** (`docs/sdlc.md` risk table, both High)
   — not a breach. A large body of hardening work promoted to blocking status *is itself* the
   highest-likelihood risk materialising. The project rule is that ideas arriving mid-module go to
   the backlog and never become scope; findings deserve the same scrutiny before they are gated.
3. **Right now the product can log in and manage staff.** No restaurant in Pune pays for that. They
   pay for "your Chilli Paneer runs at 46% food cost" and "you over-produced ₹9,000 of makhani
   gravy last month" — figures that already exist in the seed and need M03–M05 to surface.

**What a maximally useful finding looks like here:**

- It distinguishes **a defect in shipped code** from **hardening against a threat that needs users**.
  Both are worth filing. They are not the same urgency and should not share a gate.
- It **costs the remedy**, not only the risk. "One line in `.env.example`" and "a new table, a
  migration and a nightly sweep" are different proposals even when they close the same finding.
- It says **what not to do**. A review that only adds work is easy to write and expensive to act on.
  The 2026-09-11 audit's deferral table ("Deferred to modules") was its best structural feature —
  more of that.
- It weighs **whether the module moves the product closer to something someone pays for**, and says
  so when the answer is no.

---

## 7 · Standing answers, so they are not re-litigated

| Question | Answer | Where it was decided |
|---|---|---|
| Scope | Full Phase 1, over a narrower recommendation | Decided by the human; do not re-open |
| Serving topology | FastAPI serves the built SPA — one origin, one Cloud Run service, cookies stay `Lax`, no CORS in production | R4 **DECIDE**, resolved 2026-09-11 |
| Identifier uniqueness | Application-level for now; a global unique index is declined because the proper fix is a per-tenant login surface, after which the index must come off again | `docs/backlog.md` |
| Lockout semantics | Hard lock, 15-minute auto-unlock, owner/admin clears instantly | M01 spec, open decision 3 |
| Manual pass vs staging | The DoD addendum requires staging. The local pass still runs first, because it is cheap and finds usability defects before remediation churns the code | Human's call, 2026-09-11 |
