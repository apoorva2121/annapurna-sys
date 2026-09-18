# Runbook · Database Restore

**Written 2026-09-19 (M16), against Neon — not against a hypothetical.** The staging database is
Neon Postgres in `ap-southeast-1` (`docs/deploy/gcp-staging-runbook.md` §1), so every command below
is a Neon command. If the database ever moves to Cloud SQL, this file is wrong and must be
rewritten rather than adapted.

Written to be followed at 9pm by somebody stressed. Numbered commands, no judgement calls, no
"investigate the issue".

> **Not yet followed end to end.** M16 could not run it: a restore needs a live Neon session, which
> an autonomous build session does not have. Row 10.3 of the security checklist is **not ticked**,
> and it is the one most often skipped and most often regretted. The first person to follow this
> should correct what is wrong here as they go — a runbook first read during an incident is a
> runbook written for the wrong reader.

---

## Read this before you need it · how far back you can actually go

Neon does not keep backups. It keeps **change history**, and a restore is a branch taken at a past
moment inside that window. So there are two different numbers and only one of them was written
down:

| | |
|---|---|
| **How recent a restore point can be** | Effectively continuous. `docs/observability.md` §7's RPO ≤ 5 minutes is comfortably met |
| **How far back you can go** | **The project's history window, and nothing beyond it.** Neon's default is **6 hours on the Free plan** and **1 day on paid plans**, configurable up to 7 days on Launch and 30 days on Scale (checked 2026-09-19) |

**The second number is the one that will hurt.** A restaurant that discovers on Monday that
Saturday's service was corrupted has, on a free project, nothing to restore from. Nobody notices a
bad settlement within six hours.

**Before a real restaurant's data goes in, raise the history window and record what it is.** Ten
days of history is less than the interval at which anybody reconciles a month, and the whole point
of writing this here rather than in a ticket is that the number is invisible until the moment it
is the only thing that matters.

---

## 1 · Decide which kind of restore this is

| Situation | Go to |
|---|---|
| Data is wrong and you know roughly when it went wrong | §2 — restore **beside** production |
| You need yesterday's data to answer a question, production is fine | §2 — same thing, and never cut over |
| The database is unreachable | This is not a restore. Check Neon status and the Cloud Run revision first |

**Never restore over a live database.** Restore beside it, verify, then switch. Neon makes this the
easy path, so there is no reason to take the other one.

---

## 2 · Restore beside production

You need the Neon CLI (`npm i -g neonctl`) and to be signed in (`neon auth`).

1. **Write down the moment you are restoring to, in UTC, RFC 3339.** Pick a time you are confident
   is *before* the problem — earlier is recoverable, later is not.

   ```
   2026-09-19T14:30:00Z
   ```

2. **Create a branch at that moment.** This does not touch production.

   ```bash
   neon branches create \
     --project-id <PROJECT_ID> \
     --name restore-2026-09-19 \
     --parent 2026-09-19T14:30:00Z
   ```

   `--parent` takes a branch, a timestamp or an LSN; a bare timestamp means *the default branch, at
   that moment*.

3. **Get its connection string.**

   ```bash
   neon connection-string restore-2026-09-19 \
     --project-id <PROJECT_ID> --database-name neondb --pooled
   ```

4. **Rewrite it for asyncpg** — the same three edits as the deploy runbook §1.7, and for the same
   reasons:

   - `postgresql://` → `postgresql+asyncpg://`
   - delete `?sslmode=require&channel_binding=require`
   - add `?ssl=require`

---

## 3 · Verify the restore before you trust it

Run these against the **restored branch**, and against production, and compare. A restore that
nobody checked is a second problem wearing the first one's clothes.

```sql
-- The four numbers that say whether a night of service is there.
SELECT count(*) FROM "order";
SELECT count(*) FROM invoice;
SELECT count(*) FROM stock_movement;
SELECT count(*) FROM payment;

-- The latest of each, which is what says *when* the copy stops.
SELECT max(business_date), max(created_at) FROM "order";
SELECT financial_year, max(sequence) FROM invoice GROUP BY financial_year;
SELECT max(occurred_at) FROM stock_movement;
```

**What you are looking for:**

- Counts on the restored branch are **lower or equal**, never higher. Higher means you restored
  from the wrong place.
- `max(sequence)` per financial year is contiguous from 1. A gap here is the one thing an
  assessment asks about (CGST Rules, Rule 46(b)).
- The latest order is *before* your chosen moment, and not much before. Much before means the
  timestamp was wrong or the history window did not reach.

Then open the application against the branch and look at one real thing — a settled bill from that
night, with its lines. Row counts can all be right while the data is unusable.

---

## 4 · Cut traffic over

Only after §3. This is the step that is hard to undo.

1. **Note the current `DATABASE_URL`** somewhere you can read it in ten seconds. This is the
   rollback.
2. Deploy the API with the restored branch's URL:

   ```bash
   gcloud run services update <SERVICE> \
     --region <REGION> \
     --update-env-vars DATABASE_URL='postgresql+asyncpg://…restore-branch…?ssl=require'
   ```
3. Run the smoke test: `python scripts/smoke_prod.py --base-url https://<host>`.
4. Sign in and settle one test bill. If the invoice number is not what §3 predicted, **roll back**.

**To roll back:** the same command with the URL from step 1. The old branch is untouched, because
nothing in this runbook wrote to it.

---

## 5 · Tell people

Before: *"The system will be unavailable for about N minutes while we restore data from
&lt;time&gt;. Anything entered after that time will need to be re-entered."*

After: *"We are back. Everything up to &lt;time&gt; is there. If you entered something between
&lt;time&gt; and now, please check it."*

Say the time in both. The restaurant's staff can work around a known gap and cannot work around a
vague one.

---

## 6 · Afterwards, the same day

- Write down **how long it took**, start to finish. `docs/observability.md` §7 sets RTO ≤ 1 hour and
  nobody knows whether that is true until somebody has done it.
- Write down **what in this file was wrong or confusing**, and fix it here.
- Delete the restore branch once you are certain (`neon branches delete <name>`), or it bills.

---

## Targets (from `docs/observability.md` §7)

- **RPO ≤ 5 minutes** · **RTO ≤ 1 hour**
- Restore tested **monthly**, into a scratch branch, result verified. Put it in the calendar.

## The rule that overrides everything above

Never restore over a live database. Restore beside it, verify, then switch.
