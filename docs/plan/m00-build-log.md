# M00 — Build Log

**Read this file first if you are resuming work with no memory of the conversation.**
It always states what is done, what is next, and the exact next action. Updated before and after
every chunk of work, and committed with that work.

Process: `docs/sdlc.md` · Spec: `docs/modules/M00-foundation-spec.md` · Tracker: `docs/checklist.md`

---

## Status

**Phase:** P3 · Implementation · module M00 Foundation
**Spec approved:** yes — 2026-09-08, by the user, in session `session_01JXrrCwg6RSAJrDYozVzRw5`
**Started:** 2026-09-08

## Decisions locked (do not re-litigate)

| Decision | Choice | Where it came from |
|---|---|---|
| Frontend bundles | **Staff bundle now, `src/guest/` seam left in `vite.config.ts`** so M10 adds a config entry, not a refactor | User, 2026-09-08 |
| Staging deploy | **Deferred to day 2.** M00 ships via Docker Compose + CI. Deploy is the first task of day 2 / start of M01 — the fallback the spec's risk table allows | User, 2026-09-08 |
| Quality gate | `make check` is the blocking superset; `make lint` stays the fast subset. CLAUDE.md's "run make lint" line gets corrected in this PR | `docs/engineering-standards.md` §7 |
| Build order | Backend before frontend *within* the module; both ship in the module (vertical slice) | `docs/sdlc.md` steps 3 and 5 |

## Chunks — tick only when committed

- [x] **A · Skeleton** — dirs, `pyproject.toml`, `package.json`, `Makefile`, `.gitattributes`, `.env.example`
- [x] **B1 · Backend core** — `config.py`, `logging.py` (+ redaction), `errors.py`, `db.py`, health routes, staff/guest route-tree seams
- [x] **B2 · Backend tests** — 23 tests, all passing, including the 7 the spec names + `assert_max_queries`
- [x] **B3 · Alembic** — async `env.py`, baseline `0001_baseline`, up→down→up green on real Postgres
- [x] **C · Frontend shell** — Vite multi-entry with the guest seam, Tailwind tokens, TanStack Query, api client, `/version` page, 3 tests
- [x] **D · Infra** — `docker-compose.yml`, both Dockerfiles, GitHub Actions CI, pre-commit + gitleaks
- [x] **E · Gate** — `make check` clean
- [x] **F · Adversarial review** — findings below, all fixed
- [x] **G · Manual script** — `docs/manual-tests/M00-foundation.md`
- [ ] **H · User manual pass** — *requires you; M00 is NOT done without it*

## Next action

> **You run `docs/manual-tests/M00-foundation.md`** (~20 min, local Docker Compose — 23 steps).
> Report failures as step number → expected → saw. After that: the day-2 staging deploy, then M01.

## Verified — commands actually run, output actually seen

| Check | Result |
|---|---|
| `ruff check` + `ruff format --check` | clean |
| `mypy app tests` (strict) | clean, 28 files |
| `pytest` | **34 passed**, **97% coverage** (floor of 95% enforced in the gate) |
| `eslint --max-warnings 0` | clean |
| `tsc --noEmit` | clean |
| `vitest` | **10 passed** |
| `vite build` | succeeds, 59.11 KB gzipped |
| `make check` | clean |
| `docker compose up` cold start | `db` healthy → `migrate` exits 0 → `api` healthy; `/ready` **200** with no manual step |
| request id end to end | same id in the `X-Request-Id` header, the error body, and the log line |
| `scripts/audit_docs.py` | 0 issues |

## Defects found and fixed during this module

Each was a real bug caught by a test or by review, not a style change:

1. **`request_id` missing from every 500 response.** The contextvar is reset as the exception
   unwinds the middleware, which is *before* Starlette's ServerErrorMiddleware runs the handler —
   so the one error the user is told to quote had no reference. Now carried on `request.state`.
2. **Validation errors returned 500 instead of 422.** `status.HTTP_422_UNPROCESSABLE_ENTITY` is
   deprecated in this Starlette version and `filterwarnings=error` turned the warning into a crash
   inside the error handler. The zero-warnings gate caught it.
3. **`+91 98765 43210` was not redacted.** The phone pattern assumed a 3-3-4 split and missed the
   common 5-5 form — an under-redaction, the dangerous direction.
4. **Log `route` was router-relative** (`/health`, not `/api/v1/health`), which renders a staff
   route and a guest route identically — the one distinction this product cannot blur (ADR 0009).
5. **Dockerfile stamped `BUILD_TIME`, Settings reads `BUILT_AT`** — `/version` would have reported
   "unknown" in every built image.
6. **CI exported a reachable `DATABASE_URL`** while conftest used `setdefault`, so the
   "database unreachable" test would pass locally and fail in CI. conftest is now authoritative and
   CI's redundant postgres service is gone.
7. **`grid-cols-[auto,1fr]`** emits invalid CSS (Tailwind arbitrary values need `_`, not `,`).
8. **4 moderate CVEs in react-router** — upgraded to v7 while nothing imports it yet.
9. **`make dev` produced a stack that was never ready.** Nothing applied the migration, so a cold
   start served `503 {"ready":false,...,"migrations_at_head":false}` — /ready doing its job while
   the stack was unusable. A one-shot `migrate` service now runs between db-healthy and api-start.
   Found only by actually running the containers, which no test does.
10. **`make migrate`, `revision` and `seed` ran on the host**, where `db` does not resolve and
    `backend/.env` does not exist — they would have failed the first time anyone used them. They
    now run inside the compose network.

## Blockers still open (do not silently work around)

- GitHub remote not configured (`git remote -v` empty) — CI cannot run until it is
- GitHub MCP auth failing: `Authorization header is badly formatted`
- Cloud accounts (Neon/GCP · Cloudflare · Sentry) — needed for the day-2 staging deploy
- Branch is `master`; project convention is `main`

## How to verify state without trusting this file

```
git log --oneline          # committed chunks
make check                 # if it passes, chunk E is genuinely met
cat docs/checklist.md      # module-level tracker
```
