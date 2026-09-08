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
- [x] **B1 · Backend core** — `config.py`, `logging.py` (+ redaction), `errors.py`, `db.py`, health routes, staff/guest route-tree seams. ruff + mypy strict clean.
- [~] **B2 · Backend tests** — 22 tests written (the 7 the spec names, plus config/redaction edge cases) + `assert_max_queries`. **Run not yet confirmed green.**
- [x] **B3 · Alembic** — async `env.py`, baseline revision `0001_baseline`, roundtrip covered by `tests/test_database.py`
- [ ] **C · Frontend shell** — Vite multi-entry, Tailwind, shadcn, TanStack Query, api client, one page rendering `/version`
- [ ] **D · Infra** — `docker-compose.yml`, Dockerfiles, GitHub Actions CI, pre-commit + gitleaks
- [ ] **E · Gate** — `make check` clean, zero warnings
- [ ] **F · Adversarial review** — loop step 7, findings fixed before the user sees it
- [ ] **G · Manual script** — `docs/manual-tests/M00-foundation.md`
- [ ] **H · User manual pass** — *requires the user; the module is not done without it*

## Next action

> Confirm `pytest` is green (chunk B2), then wire the frontend shell and infra, then run the full
> `make check`. Two subagents were dispatched for chunk C (frontend shell) and chunk D (infra);
> their output lands in `frontend/src/**` and the Docker/CI files. If this session died before
> their work was committed, check `git status` — regenerate anything missing rather than assuming.

## Verified so far

| Check | Command | Result |
|---|---|---|
| Backend lint | `.venv/Scripts/python -m ruff check .` | passing |
| Backend format | `ruff format --check .` | passing |
| Backend types | `mypy app tests` (strict) | passing, 28 files |
| Backend tests | `pytest` | **pending — do not claim green until seen** |

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
