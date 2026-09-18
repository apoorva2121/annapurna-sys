# M16 · Hardening & Production — Build Log

Spec: `docs/modules/M16-hardening-spec.md` (revised 2026-09-19 after M17 and M18 shipped).
Checklist run: `docs/manual-tests/evidence/security-checklist-2026-09-19.md`.
Definition of done: `docs/checklist.md` P4–P6.

---

## State

| Chunk | What | State |
|---|---|---|
| A | The security checklist run in full; the headers it found missing, with tests | ✅ committed |
| B | The financial-year boundary test; the k6 script and its thresholds | ✅ committed |
| C | The owner's half, written as commands rather than instructions | ✅ committed (the restore runbook; the deploy and cost alerts remain) |
| — | The console session: load test, restore, cost alerts, deploy | **Owner's** |

Built on 2026-09-19, on `feat/m11-communication` after M18.

---

## What changed about this module before it started

The spec was written when M17 and M18 did not exist, and opened by saying M16 could not be what
`docs/modules.md` asks for. **Both shipped on 2026-09-19**, so the dependency is met and their
surfaces are in scope here like every other module's.

A second dependency replaced the first, and it is the one that actually shapes the module: **the
load test, the tested restore, the cost alerts and the production deploy all need a live GCP
console session**, which an autonomous session does not have. `docs/plan/r7-deploy-prep.md`
recorded the pipeline as built and rehearsed and blocked on exactly this.

So the module splits along that line, and the split is written down rather than discovered:
everything verifiable from the code and the test suites is done here; everything needing a console
is written as **the command to run and the output to expect**, and marked pending rather than
ticked. A checklist row ticked without being run is worse than a blank one.

---

## The checklist, and what running it in full actually found

Ten sections, 62 rows. The full record with evidence per row is in
`docs/manual-tests/evidence/security-checklist-2026-09-19.md`; the summary is that **most of it
was already true, and of the three things that were not, two are a document promising
something the code does not do and one is a number nobody wrote down at all.**

That pattern is worth naming, because it is the failure mode of a security posture written before
the software: a file that says "HSTS, CSP, X-Frame-Options" reads as a control and is a wish.

### Finding 1 · `docs/security.md` promises three headers the product does not send

> `docs/security.md:62` — *"TLS 1.2+ everywhere, HSTS, no mixed content."*
> `docs/security.md:91` — *"Strict CORS allow-list. CSP with no `unsafe-inline`.
> `X-Frame-Options: DENY`."*

The CORS allow-list is real (`app/main.py:187`). The other three were implemented nowhere.
`create_app` adds `CORSMiddleware` and `RequestContextMiddleware` and stops, and **there is no
reverse proxy that could be adding them instead** — ADR 0005 serves the built SPA from the API
itself (`app/core/spa.py`), so these headers are this application's responsibility and nobody
else's.

The consequence is concrete: the staff application could be framed. That is a clickjacking surface
on a product whose buttons void bills, reset passwords and grant roles.

### Finding 2 · The financial-year boundary was never crossed

`invoice.sequence` is gapless *per financial year* and India's runs April to March. Every existing
test settles bills inside one year, so the schema's constraint was proved and the **boundary** —
the only place the rule can actually be wrong — was not. `docs/checklist.md` P5 asks for exactly
this and it had never been done.

`tests/test_financial_year_boundary.py` now does it, and **it passes against the existing code**.
That is the honest result and it is still worth recording: the product was right and nobody had
checked, and *"we believe this works"* is a different claim from *"a test asserts this works"* —
only the second one survives the next refactor.

Writing it found one thing worth knowing. Pinning settlement's clock and not the order service's
opens a bill in September and settles it in March, which the product refuses with
`settlement.payment_time`. Correct behaviour, and exactly the kind of cross-service clock coupling
that would otherwise be discovered by a confusing test failure a year from now.

### Finding 3 · The recoverable window is six hours, and nobody had written that down

`docs/observability.md` §7 records **RPO ≤ 5 minutes**, and Neon meets it easily — a restore point
can be almost any moment. What that number does not say, and what nothing in this project said, is
**how far back a restore can reach**.

The staging database is Neon (`docs/deploy/gcp-staging-runbook.md` §1), and Neon keeps *change
history* rather than backups. The history window defaults to **6 hours on the Free plan and 1 day
on paid plans**, configurable to 7 days on Launch and 30 on Scale (checked 2026-09-19).

**Nobody notices a bad settlement within six hours.** A restaurant that discovers on Monday that
Saturday's service was wrong has, on a free project, nothing to restore from — and would discover
that while looking for it. Raising the window before a real restaurant's data goes in is a finding
rather than a preference, and it is now the first thing `docs/runbooks/restore.md` says.

This also corrected an assumption in the checklist run: §10's rows were written expecting Cloud SQL,
which is the wrong product and the wrong mental model.

### Not findings, but recorded where somebody will look for them

**MFA does not exist.** Row 2.8 is marked N/A with the reason rather than skipped: the product goes
to a pilot restaurant without it, and that is a decision to make knowingly rather than discover.

**The rate limiter is in-process.** Two containers double an attacker's budget, and a restart
clears every counter. `app/core/rate_limit.py` says so in its docstring and `docs/backlog.md`
carries the fix and its trigger. It is repeated in the checklist record because a limitation
written only in a docstring is one nobody reads at the moment they need it.

**The DPDP export exists.** The spec's first draft expected row 9.3 to fail. It does not:
`GET /staff/customers/{id}/export` has been there since M10, audited, per-customer, with no bulk
version in any role. The spec is corrected. A spec that names a gap which is not there sends a
module looking for work.

---

## What the owner has to run, and why it is not ticked here

| Rows | What | Why not here |
|---|---|---|
| 10.1–10.5 | The history window, **an actual restore**, timed against the 1-hour RTO, following `docs/runbooks/restore.md` | Needs a live Neon session. The runbook is now written against Neon with real commands and **nobody has followed it**. 10.3 is the row most often skipped and most often regretted |
| 7.5 | `gitleaks` over history | The tool is not installed here, and a secret scan is its own run rather than a line in `make check` |
| 8.1 | Search *production* logs for a known test phone number | Needs production. The mechanism is verified: redaction sits on the log **handler**, so no call site can bypass it |
| 8.5 | Sentry PII scrubbing active before the first event | Verified against the Sentry project, not against the code that configures it |
| 9.1, 9.5, 6.3 | Consent not pre-ticked; the purge job running; a script tag rendered everywhere it appears | Three rows that are about what a person sees in a browser. The owner's manual pass |
| P4 | k6 at 3× peak against staging | `load/peak.js` is written with the three budgets as thresholds. Running it needs staging |
| P5 | Cost alerts at 50/80/100, and the production deploy | Console |

---

## The load test, written but not run

`load/peak.js`. Three scenarios rather than one blended pool, because the three budgets belong to
three people standing in three different places and a fast dashboard must not be allowed to hide a
slow till:

| Scenario | Budget | Asserted as |
|---|---|---|
| `kitchen` — 4 station displays polling every 2s | KDS 50 ms | `http_req_duration{budget:kds}: p(95)<50` |
| `till` — arrivals at 3× a dinner peak | settle 400 ms | `p(95)<400` |
| `owner` — Today, refreshed while the other two load the same database | dashboard 800 ms | `p(95)<800` |

**The load is expressed in covers, not requests per second.** `docs/seed-data.md` puts Spice Garden
at ~190 covers on a Friday-to-Sunday day with dinner the peak, so 3× peak is a number the owner can
check against their own restaurant. An arrival rate is not.

p(95) rather than the mean, because a mean hides the tail and the tail is the shift where somebody
stands at a till waiting for a receipt. And `http_req_failed: rate<0.01`, because a budget met by
failing fast is not a budget met.

---

## Runs

| Run | Result |
|---|---|
| `make check` (M18 gate) | — |
| Security checklist, code-verifiable rows | 62 rows: see the evidence file |
