# CLAUDE.md

Restaurant Management & Intelligence Platform. Multi-tenant SaaS for Indian restaurants.
**Process: `docs/sdlc.md`** — the module loop and Definition of Done. Modules: `docs/modules.md`.
Vision doc: `docs/product/vision.md`. Decisions: `docs/decisions/`.

Read before working on the matching area:
`docs/domain-model.md` (concepts) · `docs/schema.md` (tables, columns, indexes) ·
`docs/waste-model.md` · `docs/customer-experience.md` ·
`docs/onboarding-cold-start.md` · `docs/seed-data.md` · `docs/ui/conventions.md` ·
`docs/ui/design-system.md` (tokens, theming, components — and the `restaurant-ui` skill, which
is offered automatically to any session touching `frontend/`) ·
`docs/engineering-standards.md` · `docs/security.md` · `docs/observability.md` ·
`docs/testing-strategy.md`

**Read before ANY code change:** `docs/engineering-guardrails.md` (rules from the 2026-09-11
audit; extends the Definition of Done) and `docs/audit/remediation-plan.md` (open findings —
**M02 does not start until R1, R2 and R8a are ticked**; the plan's state table is the source of
truth). `docs/audit/external-review.md` records why the rest was deferred, what un-defers each, and
how external review works here — read it before filing or acting on new findings.

## Stack

- **Backend** — Python 3.13 (3.12+), FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2, PostgreSQL 16
- **Frontend** — React 18 + TypeScript, Vite, Tailwind, shadcn/ui, TanStack Query, React Router (Node 20+)
- **Mobile** — the React app is a PWA. No React Native in month 1. Waiter/kitchen screens are the same codebase at mobile breakpoints.
- **Realtime** — Server-Sent Events for the kitchen display. Not WebSockets, not polling.
- **Deploy** — Docker container + managed Postgres + S3-compatible object storage. Nothing cloud-proprietary. See ADR 0005.

## Layout

```
backend/    app/{api,models,schemas,services,repositories,core}  alembic/  tests/
frontend/   src/{shared,staff,guest}   # shared/ = api, theme, ui; staff|guest = ADR 0009 bundles
docs/       product/ decisions/ ui/ plan/
```

## Commands

```
make dev            # docker compose up: api, db, frontend
make test           # pytest + vitest
make lint           # ruff + mypy + eslint + tsc
make check          # the blocking gate: lint + test + docs/seed audits + dep audits
make migrate        # alembic upgrade head
make revision m="…" # alembic autogenerate
make seed           # demo restaurant with menu, recipes, stock, orders
```

Run `make check` before saying work is done — it is the blocking gate (lint + tests + audits).
`make lint` is the fast subset for use while working.

Never edit a migration that has been applied on staging — write a new one.

## Invariants — violating any of these is a bug, not a style choice

1. **Tenant isolation.** Every tenant-owned table has `restaurant_id NOT NULL`. Every query goes through a repository that takes the tenant scope. No raw SQL without an explicit `restaurant_id` filter. This is the #1 bug class in this product.
2. **Stock is a ledger.** `stock_movements` is append-only. Current stock is *derived* by summing movements. Never `UPDATE` a quantity in place. Corrections are new movements of type `adjustment`.
3. **Money is `NUMERIC(12,2)` / Python `Decimal`.** Never float. Never `round()` on a float. Currency is per-restaurant; INR today.
4. **Time is `timestamptz`, stored UTC.** Display and aggregate in the restaurant's timezone. A restaurant's business day is *not* midnight-to-midnight — use `restaurant.business_day_start` (typically 05:00 local). "Today's sales" for a place closing at 2am must include that 2am.
5. **Units are canonical.** Every ingredient has one base unit (`g`, `ml`, or `unit`). Convert at the boundary, store base units only.
6. **Settled orders are immutable.** No edits after settlement — voids and refunds are new rows. Everything price-, recipe- or stock-affecting writes an `audit_log` entry.
7. **Theoretical ≠ actual consumption.** Recipes give *theoretical* usage; physical counts give *actual*. Store both separately. The variance between them is the core product insight — never overwrite one with the other.

## Conventions

- Layering is `api → service → repository → model`. Routes contain no business logic; repositories contain no business rules.
- Pydantic schemas are the API contract; SQLAlchemy models never cross the API boundary.
- Enums live in `app/core/enums.py` and are mirrored in `frontend/src/shared/enums.ts`.
- Tests: every service gets a test; every endpoint gets a tenant-isolation test proving restaurant A cannot read restaurant B.
- Frontend data access is TanStack Query only — no `fetch` in components.
- Errors surface as `{code, message, details}`; `code` is a stable string the frontend switches on.

## Non-negotiable process rules

- Work the module loop in `docs/sdlc.md`. A module is done only when its Definition of Done is fully
  met, including the manual pass by the user.
- `make check` clean, zero warnings, before claiming anything is finished.
- Every bug gets a regression test written **before** the fix, and its failing output goes in the
  commit body.
- The Definition of Done in `docs/sdlc.md` is extended by `docs/engineering-guardrails.md`
  §Definition of Done addendum. Both lists must be true.
- Ideas that arrive mid-module go to `docs/backlog.md`. They never become scope.
- Docs are updated in the same PR as the code.

## Deliberately out of scope for month 1

Payment gateway integration, printer/hardware drivers, offline-first sync, GST e-invoicing filing, CCTV (vision doc §22), React Native, multi-branch rollups. Design so none of these are *blocked* later — build none of them now.
