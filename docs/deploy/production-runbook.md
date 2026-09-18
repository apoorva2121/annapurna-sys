# Production deploy — M16's half of it, as commands

**Not yet run.** This is the half of M16 that needs a console session, written as the command to
run and the output to expect rather than as an instruction to go and do it. `docs/checklist.md` P5
is not ticked until somebody has run it, and a runbook step that says *"configure cost alerts"* is
a step somebody performs differently each time.

Everything here is a **difference from staging**. `docs/deploy/gcp-staging-runbook.md` is the full
procedure and is not repeated; the pipeline it built is the pipeline this uses. Read it first if
you have not.

> **Do not start this until §1 is done.** Two of the four differences are things you cannot fix
> afterwards for data that has already been lost.

---

## 1 · The two settings that cannot wait until after the first service

### 1.1 · Raise Neon's history window · **this is the one that will bite**

Neon keeps **change history**, not backups, and the default window is **6 hours on the Free plan
and 1 day on paid plans** (checked 2026-09-19). That window is not the RPO — the RPO is fine. It is
**how far back a restore can reach**, and nobody notices a bad settlement within six hours.

A restaurant that discovers on Monday that Saturday's service was wrong, on a default project, has
nothing to restore from.

```bash
# Confirm what it currently is. Do not assume.
neon projects get <PROJECT_ID>
```

Raise it in the Neon console (**Settings → Storage → History retention**) to the maximum the plan
allows — 7 days on Launch, 30 on Scale. **Write the number you chose into
`docs/runbooks/restore.md`**, whose first section asks for it.

### 1.2 · `GCP_MIN_INSTANCES = 1`

The staging runbook §9 explains it and says the trigger out loud: *"`1` the day a real restaurant
runs the kitchen display on it."* This is that day.

Scale-to-zero kills the instance holding every open SSE stream. Clients reconnect and replay from a
revision cursor so no ticket is lost — but a display that blanks between rounds gets turned off by
the kitchen, and a kitchen display nobody looks at is worse than none.

Roughly **$10–12/month**. Set the repository variable before the first deploy, not after.

---

## 2 · The environment

| Variable | Staging | Production |
|---|---|---|
| `ENV` | `staging` | `production` |
| `DEBUG` | `false` | `false` — and the app **refuses to boot** otherwise (`config.py::_debug_is_local_only`), which is why this is a note rather than a check |
| `GCP_MIN_INSTANCES` | `0` | **`1`** — §1.2 |
| `SENTRY_DSN` | optional | set it. Checklist row 8.5 is verified against the Sentry project, not against the code |

---

## 3 · Cost alerts

The staging runbook §2.3 sets ₹3,000/month at 50/80/100%. Production's number is different and the
thresholds are not: `docs/observability.md` §9 fixes them at **50 / 80 / 100**, and
`docs/checklist.md` P5 asks for all three armed.

**Billing → Budgets & alerts → Create budget**, scoped to the production project only, email on
each threshold.

**Then fire one deliberately**, which is the part people skip: set a second, throwaway budget at an
amount you have already passed, confirm the email arrives, and delete it. An alert nobody has seen
arrive is an alert that is configured, not an alert that works.

---

## 4 · Deploy, outside service hours

`docs/checklist.md` P5: *"Production deploy, outside service hours."* For an Indian restaurant that
means **before 11:00 or after 23:30 IST** — not the middle of the afternoon, which feels quiet and
is when a kitchen is prepping.

The pipeline is the one R7 built. Actions → **Deploy** → **Run workflow**, or push to `main`.

The seven steps and what each proves are in the staging runbook §8. The one that matters most here
is step 5: **migrations run as a Cloud Run Job to completion *before* the service deploys**, so new
code never queries a column that does not exist yet.

```bash
# What makes it a check rather than a hope: without --expect-sha, a previous revision
# still serving traffic passes every assertion.
python scripts/smoke_prod.py --base-url https://<host> --expect-sha <SHA>
```

### Then create the owner account

Exactly as the staging runbook §8 does, with the real company's details.

**The generated password is printed once, to the job's logs, and is not recoverable** — it is
deliberately absent from the audit row. Copy it into a password manager and change it after signing
in.

---

## 5 · The checklist rows that only exist here

These are the rows `docs/manual-tests/evidence/security-checklist-2026-09-19.md` marks **CONSOLE**.
None of them is ticked, and §10 is a 🔴 stop.

| Row | Command / where |
|---|---|
| 7.5 | `gitleaks detect --source . --no-banner` over the full history, before the first deploy |
| 8.1 | Log Explorer: search for a known test phone number and email. Expect **zero hits** — redaction sits on the log handler, so a hit means the handler is not installed |
| 8.5 | Sentry → the project → confirm PII scrubbing is on **before** the first event, not after |
| 9.1 | Open the guest surface on a phone. The consent box is **not pre-ticked** |
| 9.5 | Confirm the retention purge job runs and respects its window |
| 10.1–10.5 | `docs/runbooks/restore.md`, followed exactly. **Time it.** RTO is 1 hour and nobody knows whether that is true |

**10.3 is the one most often skipped and most often regretted.** An untested backup is not a
backup, and on Neon it is not even a backup — it is a window that may have closed.

---

## 6 · The load test

`load/peak.js`, against the production host before the first restaurant is on it — or against
staging with M15's generated data, which is the safer order.

```bash
k6 run -e BASE_URL=https://<host> -e PASSWORD=<seed password> load/peak.js
```

It asserts the three budgets `docs/checklist.md` already names — KDS 50 ms, settle 400 ms,
dashboard 800 ms — as p(95) thresholds, plus `http_req_failed: rate<0.01`, because a budget met by
failing fast is not a budget met.

**A budget missed is a finding with its measurement attached, not a reason to raise the budget.**

---

## 7 · The four things a laptop cannot tell you

Staging runbook §10 lists them and they are still unchecked. Production is where they matter:

1. **SSE through a real proxy** for a whole service, with the reconnect at Cloud Run's 60-minute cap.
2. **The rate limiter counts per process** — with more than one instance, an attacker gets a
   multiple of the budget (`docs/backlog.md`).
3. **Concurrency 40 counts a held stream as a live request.** Six kitchen screens is six of the
   forty before a single order is taken.
4. **Timezones.** The container runs UTC and the restaurant does not. Place an order after midnight
   IST and check it books to the right business day (invariant 4, `business_day_start` 05:00).

---

## 8 · Afterwards

- Tick `docs/checklist.md` P5 and P6, or write the reason beside each that is not ticked.
- Fill in the sign-off at the foot of `docs/manual-tests/security-checklist.md` — date, who ran it,
  and whether every 🔴 passes. **If any 🔴 does not, the honest entry is "do not deploy", and it is
  worth more than a tick.**
- Record the restore's elapsed time and correct `docs/runbooks/restore.md` where it was wrong. A
  runbook first read during an incident is a runbook written for the wrong reader.
