# Annapurna — restaurant management and intelligence

Multi-tenant software for running an Indian restaurant: orders, kitchen screen,
billing, menu and recipes, stock, procurement, waste, staff shifts, customer
feedback, compliance alerts and owner analytics — connected through one data
model.

**The point of difference:** it shows the gap between what the food *should*
have cost, derived from your recipes, and what it *actually* cost, derived from
the stockroom ledger. Most restaurant software can tell you what you sold. Very
little of it can tell you where the margin went.

---

## The problem it was built for

Indian restaurants typically keep almost no records. That single fact drove the
architecture more than anything else:

- **It must be useful from day one with empty data.** A product that only
  becomes valuable after six months of diligent data entry will never be used,
  because the data entry never happens. Every screen is designed to be
  meaningful on an empty database.
- **Stock is an append-only ledger, never a mutable count.** You cannot ask a
  busy kitchen to keep a running total honest. You can ask it to record events.
  Current stock is then *derived*, so every number is explainable by the events
  behind it.
- **Multi-tenant from the first migration, not retrofitted.** The seed data
  contains two restaurants on purpose: every tenant-isolation test needs a
  second tenant to fail against, and a cross-tenant leak is the worst bug this
  product could ship.

## What is built

Nineteen modules, each with a written spec in `docs/modules/`:

| | Module | | Module |
|---|---|---|---|
| M00 | Foundation | M10 | Customers, feedback & guest app |
| M01 | Identity, roles & permissions | M11 | Communication & tasks |
| M02 | Restaurant setup | M12 | Shifts |
| M03 | Menu | M13 | Dashboards & reports |
| M04 | Stock items & recipes | M14 | Audit & notifications |
| M05 | Inventory ledger | M15 | Seed generator & demo |
| M06 | Procurement | M16 | Hardening & production |
| M07 | Orders / POS | M17 | Workload fairness & recognition |
| M08 | Kitchen / KOT | M18 | Compliance risk alarms |
| M09 | Waste | M19 | Owner analytics |

Worth calling out:

- **Kitchen display** with live order updates.
- **Dish cost versus actual cost** — the recipe-to-ledger variance.
- **A QR-code guest app**: the diner scans the code at the table, no install.
- **Nine role templates across 55 permissions**, so a cashier, a chef and an
  owner genuinely see different systems.
- **Compliance alarms** for FSSAI, GST and DPDP obligations.
- **Workload fairness** — shift allocation that can be audited for whether it is
  actually even.
- **Demo seeding** that produces a plausible restaurant in one command.

**Deliberately not built:** payment gateway, thermal printer drivers, offline
sync, multi-branch rollups. Those are real requirements for a commercial launch
and none of them are present.

## Scale

| | |
|---|---|
| Database tables | 80 |
| Alembic migrations | 58 |
| Screens | 62 |
| Module specs | 20 (M00–M19) |
| Backend test files | 125 |
| Frontend test files | 66 |
| Commits | 280 |

## Tech

Python 3.13 with FastAPI and PostgreSQL 16 on the back end; React 18 with
TypeScript on the front end; Docker Compose to run the lot; GitHub Actions for
checks. Async throughout — `config.py` refuses to boot on a synchronous database
driver, because a sync driver here blocks the event loop and shows up only as
unexplained latency.

## Run it

You need **Docker Desktop running**, and `make`. Everything else lives in
containers, so there is no Python or Node version to match on your machine.

```bash
git clone https://github.com/apoorva2121/annapurna-sys.git
cd annapurna-sys

make setup      # first time only: build images, install deps, run migrations
make dev        # database, API and web app
make seed       # fill in a demo restaurant you can click around
```

The web app comes up on <http://localhost:5173>, the API on
<http://localhost:8000> (`/docs` for the OpenAPI browser).

Other targets:

```bash
make test       # backend + frontend suites
make lint       # ruff + eslint
make check      # full quality gate: lint, tests, docs/guardrail/dependency audits
make down       # stop everything
make logs       # tail
```

> **Reading `make check`:** trust the **exit code**, not the last line of
> output. The audits print their own summaries after the test results, so a
> passing-looking final line can follow a real failure.

### Configuration

Copy `.env.example` to `.env`. For local development the defaults work as they
are.

Two rules are enforced in code rather than documented, and they are worth
understanding before you deploy anything:

- **`JWT_SECRET`** has a committed default so local development needs no setup.
  The app **refuses to boot** when `ENV` is anything but `local` and that
  default is still in place — because the default is in this public repository,
  and anyone who can read it could otherwise mint an owner token for any
  restaurant. Secrets under 32 bytes are also rejected.
- **`SEED_PASSWORD`** must differ from the password committed in
  `seed/organization.yaml`. That committed password is printed in the file's own
  header, so seeding with it outside local would hand an owner account to
  anyone who can read the source.

Both fail the boot rather than logging a warning, because a warning in
production is a thing nobody reads.

## Documentation

The written material is a substantial part of this project.

| Document | What it is |
|---|---|
| `project-docs/project-explanation.md` | **Start here if you are not a developer** — 16 chapters in plain language, plus spreadsheets listing every database table and every screen with who can see it |
| `docs/sdlc.md` | The process the build actually followed |
| `docs/modules.md` | All 20 module specs and their dependency order |
| `docs/domain-model.md`, `docs/schema.md` | The data model |
| `docs/decisions/` | Architecture decision records |
| `docs/security.md` | Threat model, tenant isolation, permissions |
| `docs/testing-strategy.md` | What is tested, and what deliberately is not |
| `docs/observability.md` | Logging, tracing, operational runbooks |
| `docs/deploy/` | Google Cloud staging and production runbooks |
| `docs/ui/conventions.md` | UI design system and conventions |
| `CLAUDE.md` | The working agreement used while building this with Claude Code |

## Status

**Paused since 2026-09-28.** Modules M00 through M19 are delivered. Two pieces
of M19 — the action queue and one scored forecast — are not started.

Not deployed anywhere. The GCP runbooks in `docs/deploy/` are written but have
never been executed against a live project.

The active branch when work stopped was `feat/m11-communication`. Several
feature branches are published here unmerged, which is deliberate: they are the
work in flight, not finished history.

## Licence

[MIT](LICENSE).

No restaurant's real data is in this repository. Everything in `seed/` is
synthetic, describing a fictional restaurant called "Spice Garden".
