# Observability & Operations

Logging, metrics, errors, environments, backups and what to do at 9pm on a Saturday when the kitchen
display goes blank mid-service.

## 1 · Logging

**Structured JSON, one event per line.** Never `print`, never bare f-string logs — a log you cannot
filter is a log you will not read.

Every log line carries `request_id` automatically, via middleware. **`restaurant_id` and
`actor_id` arrive once a request is authenticated:** `current_actor` sets them for every line
written while the request is handled, and the middleware copies them onto the access line from
`request.state`, because the handler's context does not reach it. Unauthenticated lines — login,
health — carry neither.

*Until 2026-09-13 this paragraph said all three were attached automatically. The last two were
never set anywhere, so every line had been written with no tenant. `tests/test_logging_context.py`
now holds the paragraph to what it says.*

A line from an authenticated request looks like:

```json
{ "ts": "...", "level": "INFO", "msg": "order.settled",
  "request_id": "01J...", "restaurant_id": "...", "actor_id": "...",
  "route": "POST /api/v1/staff/orders/{id}/settle", "duration_ms": 212 }
```

- **`request_id`** is generated at the edge, returned in the response header, and threaded through
  every log line and error. When you report a bug, this one value finds everything.
- **`restaurant_id`** on every line makes per-tenant debugging a filter, not an investigation.

**Levels, used with discipline:**

| Level | Meaning | Example |
|---|---|---|
| `ERROR` | Something broke; a human should look | unhandled exception, payment write failed |
| `WARN` | Degraded but handled; a pattern would matter | idempotency replay, optimistic-lock conflict, slow query |
| `INFO` | Business events worth reconstructing | order settled, stock received, user login |
| `DEBUG` | Local only, never enabled in production | — |

If `ERROR` fires routinely it is not an error — fix the level or fix the code. An alert channel that
cries wolf gets muted, and then the real one is invisible.

**PII never reaches the logs.** A `RedactingFilter` scrubs `phone`, `email`, `full_name`,
`password`, `token`, `refresh_token`, `gstin`, `address` from every message and every structured
field, by key name and by pattern (Indian phone numbers, emails). It is applied at the handler, so it
cannot be bypassed by a new log call. A test asserts a log line containing a phone number comes out
redacted. Log the `customer_id`, never the phone.

## 2 · Metrics

**RED per endpoint** — Rate, Errors, Duration (p50/p95/p99), labelled by route and status. Alert when
p95 crosses the budget in `docs/engineering-standards.md` §3.

**Business metrics**, because the interesting failures are silent:
- orders settled per minute · KDS ticket age p95 · SSE connected clients
- stock movements written per settle (should be ≥ 1 — zero means the recipe chain broke)
- theoretical-vs-actual variance per day (a sudden jump means a data bug, not a theft spike)
- failed logins, permission denials, cross-tenant 403s

That third one is the canary for this product: if the number the whole business rests on moves for a
non-business reason, we want to know before the owner does.

## 3 · Errors

**Sentry** (free tier is sufficient at pilot scale), backend and frontend, with `request_id`,
`restaurant_id` and release version attached. PII scrubbing configured before the first event is
sent, not after.

Every unhandled exception returns the standard envelope with a generic message plus the
`request_id` — the user sees *"Something went wrong. Reference: 01J7X…"*, and never a stack trace.

**Errors are triaged, not accumulated.** A new error type gets an issue or a fix within the same
working day. An error list nobody reads is worse than none, because it looks like coverage.

## 4 · Health and readiness

- `GET /health` — process is alive. No dependencies. For the load balancer.
- `GET /ready` — database reachable, migrations at head. For deploy gating.
- `GET /version` — git SHA and build time. The first thing to check when staging behaves oddly.

## 5 · Environments

| | local | staging | production |
|---|---|---|---|
| Data | seeded demo | seeded demo | real |
| Secrets | `.env` (gitignored) | secret manager | secret manager |
| DEBUG | true | **false** | **false** |
| Migrations | manual | auto on deploy | manual, deliberate |
| Cost | ₹0 | ~₹800/mo | ~₹1,500/mo at pilot |

**Production data never enters staging or local.** If a production bug needs real data to reproduce,
it gets an anonymised extract with names and phones replaced — never a raw dump. This is both a DPDP
requirement and basic hygiene.

Configuration is environment variables validated by a Pydantic `Settings` model at startup. A
missing or malformed variable **fails the boot loudly** rather than defaulting to something unsafe.
`DEBUG=true` in a non-local environment is a startup assertion failure.

## 6 · Migrations

- One migration per PR, reversible, with `downgrade()` actually implemented and tested.
- **Never edit a migration that has run on staging.** Write a new one.
- Expand → migrate → contract for anything destructive: add the new column, backfill, switch reads,
  then drop the old one in a later release. Never add a `NOT NULL` column without a default to a
  populated table.
- CI runs `upgrade head` then `downgrade -1` then `upgrade head` against a real Postgres, so a
  broken downgrade fails the build rather than surfacing during an incident.
- Migrations that touch large tables state their expected lock behaviour in the PR.

## 7 · Backups and disaster recovery

The most important section here, and the one most projects skip. **A restaurant losing a day of
sales data is a business emergency; losing its recipe and stock history would end the relationship.**

- **Automated daily backups**, 30-day retention, encrypted.
- **Point-in-time recovery** enabled (Neon and Cloud SQL both provide it).
- **RPO ≤ 5 minutes. RTO ≤ 1 hour.**
- **Restore is tested monthly**, into a scratch database, and the result is checked. An untested
  backup is not a backup — it is a hope. Put the test in the calendar.
- Object storage (bills, waste photos, attachments) versioned with lifecycle rules.
- The restore runbook is written *before* it is needed, in `docs/runbooks/restore.md`, written so it
  can be followed while stressed.

## 8 · Incident response

**Severity:**

| | Meaning | Response |
|---|---|---|
| **SEV1** | Service down, or data loss/corruption, or a suspected breach | Immediate. Everything stops. |
| **SEV2** | A core flow broken (cannot settle orders, KDS blank) | Within the hour |
| **SEV3** | Degraded or cosmetic | Next working day |

Restaurants operate 12:00–15:30 and 19:00–23:30. **A deploy during dinner service is itself an
incident.** Deploy windows: 15:30–18:30, or before 11:00.

**Runbook:** acknowledge → assess severity → stabilise (roll back before diagnosing; a rollback is
always faster than a fix) → communicate to the restaurant in plain language → fix → **written
post-mortem for every SEV1 and SEV2, blameless, with one concrete prevention action.**

A breach follows the DPDP path in `docs/security.md`: contain, assess scope, notify the Data
Protection Board and affected persons within the statutory window, document everything.

## 9 · Cost guardrails

Cost optimisation is a stated goal, so it gets a control rather than good intentions:

- Billing alert at 50%, 80% and 100% of a monthly ceiling (start at ₹3,000/month total).
- Scale-to-zero on the API (Cloud Run), so an idle pilot costs nearly nothing (ADR 0005).
- Object storage lifecycle: waste photos and attachments to cold storage after 90 days.
- Log retention 30 days hot, then dropped. Log volume is the cost that silently grows.
- A monthly five-minute review of the bill against expectations. Surprises are usually bugs — a
  runaway retry loop shows up as a cloud invoice before it shows up as an error.
