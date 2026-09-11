# Engineering Guardrails

**Read before any code change.** These are the rules the 2026-09-11 audit found were *written
down but not followed*, or *not written down at all*, in M00–M01. They extend
`docs/engineering-standards.md` and `docs/sdlc.md`; where they overlap, this file is the stricter
one and wins. Each rule says **why** (the finding it came from, in
`docs/audit/2026-09-11-findings.md`) and **how it is enforced** — because, in this project's own
words, *security that depends on a developer remembering is not a control.*

Status column: **enforced** = a test, grep or CI step fails when the rule is broken;
**manual** = review only, and the enforcement is an open item in `docs/audit/remediation-plan.md`.

| Id | Rule | Why | Enforced by | Status |
|---|---|---|---|---|
| G-1 | **A write that must survive a failed request is committed by the service before it raises.** Failure counters, revocations, denial audit rows. "The route commits on success" is not enough. | P1-1: lockout and replay revocation were rolled back with the 401 | lockout: `test_lockout_persistence.py` (`b01a8b0`); replay: HTTP-level regression test (R1) | half enforced → R1 |
| G-2 | **The test harness reproduces production transaction boundaries by default.** One session per request, closed when the request ends; `fresh_database` only for tests that need a real `COMMIT` on disk. Never a shared session across requests. | P1-1 was invisible to 262 tests because `conftest.py` yielded one open session to every request | `fresh_database` exists (opt-in, `b01a8b0`); `api` fixture still shared → per-request override (R1) | partial → R1 |
| G-3 | **Every security assertion has an HTTP-level test, not only a service-level one.** Lockout, replay, revocation, denial, tenant isolation. | service tests passed while the API behaved differently | DoD addendum item 2 | manual |
| G-4 | **Authority over a global resource is judged organization-wide.** Password, login, employment, deactivation: use the target's most senior role anywhere in the org. Branch-local rank governs branch-local resources only. | P1-2: a branch manager could take over an org admin's account | `most_senior_rank_anywhere()` + the two-branch regression tests (R2) | manual → R2 |
| G-5 | **Every endpoint that changes a person other than the actor passes the seniority guard.** No exceptions for "harmless" fields. | P1-6: `update_employee` had no guard | permission-matrix suite extended with a two-branch fixture (R2) | manual → R2 |
| G-6 | **CPU-bound work never runs on the event loop.** Argon2, image processing, PDF/CSV generation go through `asyncio.to_thread` or a worker. | P1-9: every login blocked the worker for 150–300 ms | `scripts/audit_guardrails.py` grep (R9) | manual → R9 |
| G-7 | **Docs describe what is built.** A control that is designed but not implemented is tagged `[planned: Mxx]`; a checklist item for a planned control is never ticked. | D5: security.md lists CSP, HSTS, MFA, rate limiting, lockfiles, RLS as present; none exist | `scripts/audit_guardrails.py` checks every control paragraph in `docs/security.md` carries a tag (R9) | manual → R9 |
| G-8 | **Layering, as written, is enforced:** a route calls exactly one service method; a service never writes `select(`/`update(`/`delete(` — it calls a repository method; a repository never decides policy. | D7: `auth.py` routes and `roles.py` call repositories; `EmployeeService` and `AuthService` build SQL | `scripts/audit_guardrails.py` grep (R9) | manual → R8/R9 |
| G-9 | **One source of truth per catalogue.** Permissions live in `backend/app/core/permissions.json` only. Any second copy is deleted or generated from the first. | M12: `seed/organization.yaml` carries a 47-permission catalogue the app never reads | R8 deletes it; `test_permission_seed.py` remains the drift guard | manual → R8 |
| G-10 | **Both languages are lock-filed and installed frozen.** `uv.lock` + `uv sync --frozen`; `package-lock.json` + `npm ci`. A version that is claimed to match another is asserted by a test. | M9: images and CI resolved fresh; the FastAPI 0.141 routing break came from exactly this | `backend/tests/test_toolchain_pins.py` — asserts the lockfile exists, is not older than `pyproject.toml`, that ruff is pinned exactly, and that the pin equals the pre-commit `rev`. CI and the image install frozen | **enforced** (R8a) |
| G-11 | **Security events are observable.** Every permission denial, refused escalation, lockout/throttle, replay and login failure emits a structured log line and, where it concerns a named account, an `audit_log` row. | M3, M5: nothing logged a denial; `docs/security.md` promised alerts on bursts of them | tests in R3/R5 | manual → R3/R5 |
| G-12 | **Every third-party sink gets the same redaction as the logs.** Sentry (and later e-mail/WhatsApp/analytics) is configured with `before_send` reusing `redact_value`, `max_request_body_size="never"`, and an extended scrubber. Redaction on the stdout handler protects only stdout. | P1-4: `logger.exception` reached Sentry unredacted; request bodies with `new_password` were attached by default | `scripts/audit_guardrails.py` checks `main.py` (R9); redaction tests (R3) | manual → R3 |
| G-13 | **Schema review checklist before any new table** — see §Schema review below. Capture what cannot be reconstructed later. | S1–S16: invoice, per-line KOT timestamps, modifier recipes, channel, consent, cash close were all missing | spec step 2 of the module loop; the checklist is answered in the module spec | manual |
| G-14 | **Production topology is decided and smoke-tested against the runtime images**, not the dev servers. `make smoke-prod` runs before any deploy. | P1-3: the runtime nginx image cannot reach the API; two-origin cookies were never designed | `make smoke-prod` exists and runs in CI (R4) | manual → R4 |
| G-15 | **No unauthenticated request may lock a named account.** Throttle by progressive delay and per-IP budget; a hard account lock is set only by a human. | P1-5: five wrong guesses locked the owner out for 15 minutes, from anywhere | tests in R5 | manual → R5 |
| G-16 | **Commit discipline.** No uncommitted work at the end of a session. Manual-test evidence lives in `docs/manual-tests/evidence/<module>/`. No personal or binary files at the repository root. | M14, D9 | `scripts/audit_guardrails.py` root-file check (R9); the session kickoff prompt ends with `git status` | manual → R9 |
| G-17 | **Anything touching identity is tested with a two-branch, two-organization fixture** (`owner` at R1 who is also a junior role at R2; a second org). Single-branch fixtures cannot see branch-vs-org bugs. | P1-2 passed every existing test | fixture in `tests/test_employee_endpoints.py` (R2); generic suites use it | manual → R2 |
| G-18 | **Identifiers are normalised at the boundary and uniqueness is a database constraint.** Lowercase e-mail, E.164 phone; a check-then-insert is never the only guard. | P1-7: two spellings of one phone were two logins; the global check was racy | migration + tests in R6 | manual → R6 |
| G-19 | **Refresh rotation tolerates retries.** A rotated token presented again inside the grace window returns the same successor; only a late replay is theft. Network retries are not attacks. | P1-8: a timed-out retry or a second tab signed everyone out | tests in R6 | manual → R6 |
| G-20 | **Every rule in this table gets a mechanical check in `make check`** or an explicit "manual" status with the item that will mechanise it. A rule nobody can grep for is a wish. | this whole table | `scripts/audit_guardrails.py` (R9) | manual → R9 |

---

## Definition of Done — addendum

Added to the list in `docs/sdlc.md`. A module is done only when these are **also** true.

**Tests**
- [ ] Every failure path that writes (counter, revocation, audit) has an HTTP-level test proving
      the write survived the failed request (G-1, G-3)
- [ ] Identity-touching modules run their permission tests against the two-branch, two-org fixture
      (G-17)
- [ ] Any new long-running or CPU-bound call is shown, by test, not to block the loop (G-6)

**Security**
- [ ] Every denial and refused escalation the module introduces is logged and, where it names an
      account, audited (G-11)
- [ ] Any new external sink (e-mail, SMS, WhatsApp, analytics, error tracker) is wired through
      `redact_value` before the first event (G-12)
- [ ] Authority checks on global resources use organization-wide seniority (G-4, G-5)

**Schema**
- [ ] The schema review checklist below is answered in the module spec for every new table (G-13)

**Deploy**
- [ ] `make smoke-prod` passes against the runtime images (G-14)
- [ ] The module is on staging before the manual pass; the manual script names the staging URL

**Docs**
- [ ] Any control the module designs but does not build is tagged `[planned: Mxx]` (G-7)
- [ ] `docs/audit/remediation-plan.md` and `docs/checklist.md` reflect the true state (G-16)

---

## Schema review checklist (G-13)

Answer these in the module spec for every new table, in writing, even when the answer is "no".

1. **What metric will someone want from this row in M13/M17, and which timestamp does it need?**
   If a per-line duration will be asked for, the line carries the timestamps, not only the header
   (`kot_ticket_line` lesson, S2).
2. **Where did this row come from?** Channel, source, external reference, importer. Orders from
   aggregators, feedback from QR vs staff, stock from purchase vs opening count (S4).
3. **Is this row a legal document?** Invoices, credit notes, consent records get their own table,
   their own sequence and their own immutability rule; they are never a status on a parent (S1, S8).
4. **Does a modifier / option / variant change consumption?** Then it carries a recipe (S3).
5. **What does a human count at close?** Cash, stock, covers — the count needs a table with
   `expected` beside `counted` (S5, `stock_count_line`).
6. **Is the derived number O(N) forever?** Balances over a ledger get a snapshot table designed at
   the same time as the ledger (X7).
7. **Which tier of ADR 0008 deletion does it belong to**, and is `restaurant_id` on the row?
8. **What would an insider do with this row?** (already in the module loop — keep it.)

---

## Working with an AI pair — the protocol that makes the rules stick

These are for the human running the sessions. They cost nothing and they are why the rules above
will hold when the model changes.

1. **Start every session with the kickoff prompt** in `docs/audit/remediation-plan.md` (or the
   module's build log once M01-R is done). The first output of a session is a *state table*, not
   code. If the table is wrong, stop there.
2. **Ask for the failing test before the fix, and ask to see the output.** "Write the regression
   test, run it, paste the failure" is a single sentence and it is the difference between a fix
   and a claim.
3. **One chunk per commit; `git status` clean at the end.** If a session must end early, the last
   act is a commit with `wip:` in the message and a line in the build log saying what is half done.
4. **Ask for guardrail ids in commit messages** touching auth, permissions, sessions, money or
   stock. `git log --grep G-4` is how you audit later without reading diffs.
5. **Ask "what did you not build that the doc says exists?"** at the end of every module. The
   answer goes into the doc as `[planned: Mxx]` tags (G-7).
6. **Ask for a second reader.** The independent review of M01 found five holes the author had
   read past twice. Once per module: a fresh session, no build log, only the diff and
   `docs/security.md`, with the instruction "find what the author missed".
7. **Never approve a spec that has no threat question answered and no schema checklist answered.**
   Those two sections are where the expensive mistakes are cheapest.
8. **Keep the human gates.** Spec approval, `DECIDE` items, the manual pass. The model is fast and
   literal; the gates are where "it did what it was told" meets "it was told the wrong thing".
