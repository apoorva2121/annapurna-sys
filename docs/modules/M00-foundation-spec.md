# M00 · Foundation — Module Spec

**Status:** awaiting your approval (step 1 of the module loop, `docs/sdlc.md`)
**Estimate:** 1 day · **Depends on:** nothing · **Blocked by:** Docker Desktop not installed

## Scope

No product features. This module is the ground every other module stands on: the repo, the
toolchain, the quality gates, the logging and error contracts, and a **working deploy to staging**.

Deploying on day one is deliberate. Deployment discovered in week four is a bad week; deployment
proven in hour six is a solved problem for the rest of the project.

## Not in scope

Any table, any endpoint that returns data, any screen with content. If it looks like a feature, it
belongs to M01.

## Deliverables

**Repo and toolchain**
```
backend/   app/{api,core,models,repositories,schemas,services}  alembic/  tests/
frontend/  src/{routes,components,features,lib,hooks}
scripts/   audit_docs.py  hook_validate.py          (exist)
seed/      *.yaml  validate.py                      (exist)
```
- `docker-compose.yml` — api, db (Postgres 16), web
- `Makefile` — `dev`, `test`, `lint`, `check`, `migrate`, `revision`, `seed`
- Python 3.13 + FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic v2; `pyproject.toml`, locked
- React 18 + TS + Vite + Tailwind + shadcn/ui + TanStack Query; locked
- ruff, mypy strict, eslint, prettier, tsc — configs per `docs/engineering-standards.md` §7
- pre-commit hooks (fast subset) + GitHub Actions CI (everything)

**Runtime contracts** — the pieces every later module depends on
- `Settings` (Pydantic) validated at startup; **boot fails loudly** on missing or bad config
- **`DEBUG=true` outside local fails the boot** — asserted, not documented
- Structured JSON logging: `request_id`, `restaurant_id`, `actor_id`, `route`, `duration_ms`
- `RedactingFilter` installed **at the handler**, so no future log call can bypass it
- Standard error envelope `{code, message, details}` + `request_id`, leaking nothing internal
- `/health`, `/ready` (db + migrations at head), `/version` (git SHA, build time)
- Sentry, backend and frontend, PII scrubbing configured **before the first event is sent**

**Test harness**
- pytest + pytest-asyncio + httpx + **testcontainers-Postgres** (real Postgres, never SQLite —
  we depend on `timestamptz`, `NUMERIC`, partial indexes, `jsonb`, `FOR UPDATE`)
- vitest + React Testing Library
- `assert_max_queries(n)` helper — the N+1 guard every later module uses
- CI runs migration `upgrade → downgrade → upgrade` against real Postgres

**Deploy**
- Dockerfile (multi-stage), staging pipeline, `/version` reachable on a real URL

## Acceptance criteria

1. `make dev` brings up api + db + web; the web app loads and reaches the API
2. `make check` passes clean, **zero warnings**
3. `/health`, `/ready`, `/version` all respond correctly
4. A log line containing a phone number comes out **redacted** — asserted by test
5. Boot **fails** with a missing required env var — asserted by test
6. Boot **fails** with `DEBUG=true` and `ENV=staging` — asserted by test
7. A deliberate exception returns the error envelope with a `request_id` and **no stack trace**
8. Migration up → down → up passes on real Postgres in CI
9. `scripts/audit_docs.py` and `seed/validate.py` run green in CI
10. **Staging URL live**, `/version` showing the right commit

## Threat question — *what would an insider do with this?*

Nothing yet; there is no data. The relevant risks are the ones this module makes structural for
every later module:

- **Secrets in the repo** → `.env` gitignored, `gitleaks` in pre-commit, secrets from the platform
  manager in staging
- **PII leaking into logs** → redaction at the handler, tested now, so it cannot be forgotten in M10
  when real customer phone numbers arrive
- **Debug mode in production** → startup assertion, not a checklist item
- **Errors leaking internals** → one envelope, applied globally, before any endpoint exists

Getting these in at M00 costs an hour. Retrofitting them after M10 means auditing every log call
and every error path in the codebase.

## Tests

| Test | Asserts |
|---|---|
| `test_redaction` | phone, email, password, token scrubbed from a log line |
| `test_settings_missing` | boot fails on missing required var |
| `test_settings_debug_in_staging` | boot fails on `DEBUG=true` outside local |
| `test_error_envelope` | shape is `{code, message, details}` + `request_id`, no traceback |
| `test_health_ready_version` | all three respond; `/ready` fails when db is down |
| `test_request_id_propagates` | id in response header appears in the log line |
| `test_migration_roundtrip` | up → down → up on real Postgres |

## Risks

| Risk | Mitigation |
|---|---|
| **Docker not installed** — hard blocker | You install Docker Desktop; everything else here is ready |
| testcontainers slow on Windows | Session-scoped container fixture; one start per test run |
| Staging deploy eats the day | Timebox to 3h; if it overruns, ship staging as step one of M01 rather than stretching M00 |

## What I need from you

1. **Approve this spec** (or tell me what to change)
2. **Install Docker Desktop** — the only hard blocker
3. Decide GCP + Neon vs Azure for staging — I recommend **GCP Cloud Run + Neon + Cloudflare**
   (ADR 0005), and I can defer this to day 2 if you would rather decide later

Once 1 and 2 are done I can complete M00 without further input.
