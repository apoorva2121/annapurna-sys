# Remediation Plan — M01-R · post-audit hardening

**Status: R1, R2 and R8a done. The gate is clear — M02 may start.**

Findings and rationale: `docs/audit/2026-09-11-findings.md`. Rules that came out of them:
`docs/engineering-guardrails.md`. This file is the *work*, in order, and it is
updated after every commit exactly like a build log — **it can be trusted about the past and not
about the future.**

**Re-cut 2026-09-11.** The original gate read "nothing starts until R1–R4 are ticked". That has been
narrowed to **R1, R2 and the lockfile** after a priority review — the reasoning, the deferral
triggers and the two contested recommendations are in `docs/audit/external-review.md` §4 and §5.
Nothing is cancelled; each deferred chunk has a named trigger that un-defers it.

**The gate now reads: M02 does not begin until R1 and R2 are ticked.** M02 must not be built on a
test harness that cannot see a rollback, nor on a seniority check that a branch manager can walk
around. R4 and R7 became one piece of work (an origin fix cannot be verified without deploying it),
and R3, R5, R6 and R9 wait for the conditions that make them matter.

---

## How to start a session on this plan

Paste this as the first message of a fresh Claude session (any model):

> Read `CLAUDE.md`, `docs/engineering-guardrails.md`, `docs/audit/remediation-plan.md` and
> `docs/audit/2026-09-11-findings.md`, then `git log --oneline -15` and `git status`.
> Report the state of the plan in one table. Then work the **next unticked chunk only**, following
> the module loop in `docs/sdlc.md`: write the regression test named in the chunk first, run it,
> paste the failing output, then fix, then `make check`, then tick the box and record the commit
> id in the state table, then commit with a conventional message that cites the finding ids
> (e.g. `fix(m01-r): P1-1 commit the failure counter before raising`). One chunk per commit.
> Do not start M02. Do not refactor anything the chunk does not name. Stop and ask when a
> decision in the chunk is marked **DECIDE**.

Rules of engagement for the session (the human enforces these):

1. **Test first, always.** The failing test output goes in the commit body. A fix without a
   failing test first is reverted.
2. **One chunk, one commit.** Never leave the working tree dirty at the end of a session.
3. **Tick only what is true.** `make check` clean is the precondition for every tick.
4. **Docs in the same commit.** If a chunk changes behaviour a doc describes, the doc changes too.
5. **Guardrail ids in commits.** A commit touching auth, permissions or sessions cites the `G-n`
   it satisfies, so `git log --grep G-4` answers "when did we enforce this".

---

## State

| Chunk | What | Findings | State | Commit |
|---|---|---|---|---|
| R1 | Transactions and the honest test harness | P1-1 | ☑ **done** — `api` opens one session per request; both halves of P1-1 have HTTP-level tests; `_handle_replay` commits its revocation. 270 tests, `make check` clean. **P1-9 (argon2) was removed from this chunk** and deferred to measured load or M08 | `b01a8b0` + `bf5ab60` |
| R2 | Seniority is organization-wide | P1-2, P1-6 | ☑ **done** — org-wide rank, guards on update/set_roles/reset, `may_reset_password`, `password_reset_required` (migration 0003), two-branch fixture (G-17). Also fixed a 404 on legitimately removing a last role | `5ee7b49` |
| R8a | Lockfile only — `uv lock`, frozen installs, pinned ruff | M9 | ☑ **done** — uv.lock (80 packages), ruff pinned to the pre-commit rev, image and CI install frozen, `tests/test_toolchain_pins.py` guards all four | `ee98f31` |
| — | **M02 may start here** — gate cleared | — | ✅ | — |
| R3 | Sentry and redaction | P1-4, M3 | ⏸ deferred → the deploy, or the day `SENTRY_DSN` is set. Interim: it stays unset | — |
| R4 | One origin; production smoke; headers | P1-3, M8 | ⏸ deferred → merged into R7; the code cannot be verified without deploying it | — |
| R5 | Lockout; plan and status enforcement; auth audit | P1-5, P1-10, M1, M5 | ⏸ deferred → a public URL exists. **Scope cut**: per-IP budget only, not the lockout redesign (external-review §5) | — |
| R6 | Identifiers, rotation grace, session binding | P1-7, P1-8, M2, M10 | ⏸ deferred → real staff on real WiFi. Normalisation may ride along with M02 | — |
| R7 | Bootstrap command; staging on GCP (now incl. R4) | M15, D6, P1-3, M8 | ⏸ deferred → its own session, human present for the console work | — |
| R8b | Layering, catalogue, docs drift | D1–D10, M12, X4 | ⏸ deferred. **M12 contested**: keep the YAML catalogue as forward design + a subset test, do not delete it (external-review §5). D8 file split: last or never | — |
| R9 | Guardrails become a gate | G-20 | ⏸ deferred → M05, or a second person joins | — |

Everything in "Deferred to modules" at the bottom is **not** part of M01-R; it is scheduled into
the module that owns the table.

---

## R1 · Transactions and the honest test harness  `P1-1 P1-9 M14`

**Why first:** the lockout and the replay revocation do not persist over HTTP, and the harness is
the reason nobody knows. Until the harness reproduces production transaction boundaries, no test
in this project can certify a failure path.

**Already done in `b01a8b0`:** the pending work is committed; `_record_failure` commits itself;
`tests/test_lockout_persistence.py` proves lockout durability through `fresh_database` (one real
database, one session per attempt). Keep both. What follows is the rest.

**Step 1 — make the harness honest by default** (`backend/tests/conftest.py`). `fresh_database`
is opt-in: a test has to know it needs it. The `api` fixture still yields one shared session to
every request, so every *other* failure path (replay revocation today; denial audit rows, throttle
counters and idempotency records tomorrow) will pass green while being rolled back. Replace the
shared-session override with one session per request, bound to the same connection and outer
transaction, so durability is the default and `fresh_database` is reserved for tests that need a
real `COMMIT` on disk:

```python
@pytest.fixture
async def db_connection(migrated_url: str) -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            yield connection
            if transaction.is_active:
                await transaction.rollback()
    finally:
        await engine.dispose()


def _factory(connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


@pytest.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    async with _factory(db_connection)() as session:
        yield session


@pytest.fixture
async def api(db_connection: AsyncConnection) -> AsyncIterator[FastAPI]:
    application = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        # A NEW session per request, closed when the request ends — exactly what
        # app.core.db.get_session does in production. Uncommitted work is rolled back to the
        # request's savepoint, so a handler that forgets to commit fails here, not in a restaurant.
        async with _factory(db_connection)() as session:
            yield session

    application.dependency_overrides[get_session] = _session_override
    yield application
    application.dependency_overrides.clear()
```

Expect a handful of existing endpoint tests to need `await db_session.refresh(obj)` or a re-query
after a request, because the test session's identity map no longer sees the request session's
writes automatically. That is correct behaviour; fix the tests, not the harness.

**Step 2 — regression tests first** (`backend/tests/test_review_regressions.py`, new class
`TestFailedRequestsPersistTheirBookkeeping`). The lockout test below now **passes** (it is the
HTTP-level twin of `test_lockout_persistence.py`; keep it — it is what the per-request harness
proves). The replay test must **fail** on the current code:

```python
async def test_five_wrong_passwords_over_http_lock_the_account(db_session, api_client):
    await _world(db_session, "owner")
    for _ in range(5):
        r = await api_client.post("/api/v1/auth/login",
                                  json={"identifier": "owner@spice-garden.test", "password": "wrong"})
        assert r.status_code == 401
    r = await api_client.post("/api/v1/auth/login",
                              json={"identifier": "owner@spice-garden.test", "password": PASSWORD})
    assert r.status_code == 429, "the failure counter was rolled back with the failed request"


async def test_a_replayed_refresh_cookie_kills_the_family_over_http(db_session, api_client):
    await _world(db_session, "owner")
    first = await api_client.post("/api/v1/auth/login",
                                  json={"identifier": "owner@spice-garden.test", "password": PASSWORD})
    old = first.cookies["restaurant_os_refresh"]
    second = await api_client.post("/api/v1/auth/refresh")                      # rotates
    new = second.cookies["restaurant_os_refresh"]
    replay = await api_client.post("/api/v1/auth/refresh", cookies={"restaurant_os_refresh": old})
    assert replay.status_code == 401
    legit = await api_client.post("/api/v1/auth/refresh", cookies={"restaurant_os_refresh": new})
    assert legit.status_code == 401, "the family revocation was rolled back with the 401"
```

**Step 3 — fix the remaining half** (`backend/app/services/auth.py`, `refresh()`). The lockout
commit is done; the replay revocation is still discarded with the 401. Same rule, same shape:

```python
if live is None:
    await self._handle_replay(token_hash)
    await self.session.commit()   # the revocation must persist even though we answer 401
    raise AppError("auth.session_invalid", "Please sign in again.", status_code=401)
```

**Step 4 — argon2 off the event loop** (`backend/app/core/security.py`), test first: a test that
runs `login` concurrently with a trivial coroutine and asserts the coroutine completes in < 50 ms.

```python
async def verify_password_async(password: str, stored_hash: str | None) -> bool:
    return await asyncio.to_thread(verify_password, password, stored_hash)

async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)
```

Use them in `AuthService` and `EmployeeService`; cache `PasswordHasher` with `lru_cache`.

**Done when:** both regression tests pass; `make check` clean; `docs/testing-strategy.md` gains a
paragraph "the harness opens one session per request" under *The shape*.

---

## R2 · Seniority is organization-wide  `P1-2 P1-6`

**Regression tests first** (`test_review_regressions.py`, class `TestSeniorityIsOrganizationWide`):

- `_world` gets a second restaurant `R2`. Owner is `owner` at R1 **and** `waiter` at R2. A
  `manager` exists at R2 only.
- As the R2 manager: `POST /staff/employees/{owner}/password` → **403**; `/deactivate` → 403;
  `/roles` with `[]` → 403; `PATCH /staff/employees/{owner}` → 403. All four fail today.
- A manager may not reset a peer manager's password (403), but an owner may reset another owner's.
- After an owner resets a waiter's password, the waiter's next login answers
  `auth.password_change_required` until they call `POST /auth/password`.

**Fix:**

```python
# app/repositories/access.py
async def most_senior_rank_anywhere(self, employee_id: uuid.UUID) -> int:
    """The person's seniority across the whole organization. Used for account-level actions:
    the password, the login and the employment are global even though roles are per branch."""
    rank = await self.session.scalar(
        select(func.min(Role.rank))
        .select_from(EmployeeRoleAssignment)
        .join(Role, Role.id == EmployeeRoleAssignment.role_id)
        .where(EmployeeRoleAssignment.employee_id == employee_id)
    )
    return MOST_JUNIOR_RANK if rank is None else int(rank)
```

```python
# app/services/employee.py
async def _rank_of(self, employee: Employee, actor: Actor) -> int:
    # Organization-wide, never branch-local (P1-2): a branch manager could otherwise reset the
    # password of anyone senior who also holds a junior role at that branch.
    return await self.access.most_senior_rank_anywhere(employee.id)
```

- Apply `_reject_if_more_senior` in `update_employee` and in `set_roles` (both directions).
- `reset_password` requires **strictly** more senior: `actor.rank < target_rank`, except when both
  are rank 0 (owner-on-owner). Put the rule in `permissions.py` as `may_reset_password()` beside
  `may_assign_rank()`, with its own docstring.
- Add `user_account.password_reset_required bool NOT NULL DEFAULT false` (new migration `0003`);
  set it in `reset_password`, clear it in `change_own_password`; `login()` answers a distinct
  code when it is set so the client can route to the change-password screen.

**Done when:** the six tests pass; `docs/modules/M01-identity-spec.md` threat table gains the row
"a branch manager takes over a senior person's account via a junior role at their branch";
`permissions.json` `_readme` explains the two rank rules.

---

## R3 · Sentry and redaction  `P1-4 M3`

**Tests first** (`backend/tests/test_logging.py`, `backend/tests/test_ops.py`):

- `extra={"new_password": "x", "login_identifier": "y", "authorization": "z"}` → all three
  `[redacted]` (fails today: exact-key match).
- `configure_sentry` passes `max_request_body_size="never"` and a `before_send`; calling that
  `before_send` with an event carrying `extra.new_password` and `request.data.identifier` returns
  them redacted.
- A refused `require_permission` and a refused `_reject_if_more_senior` each emit one
  `auth.denied` warning with `actor_id`, `route` and `code` (M3).

**Fix:**

- `logging.py`: `SENSITIVE_KEYS` becomes substring matching (`password`, `token`, `secret`,
  `authorization`, `cookie`, `identifier`, `phone`, `email`, `full_name`, `date_of_birth`, `gstin`,
  `address`, `mfa`).
- `main.py`:

```python
from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber
from app.core.logging import redact_value

def _scrub(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    for key in ("extra", "request", "breadcrumbs", "logentry", "contexts"):
        if key in event:
            event[key] = redact_value(key, event[key])
    return event

sentry_sdk.init(
    dsn=settings.sentry_dsn, environment=settings.env.value, release=settings.git_sha,
    send_default_pii=False,
    max_request_body_size="never",
    event_scrubber=EventScrubber(recursive=True, denylist=[*DEFAULT_DENYLIST,
        "new_password", "current_password", "initial_password", "identifier",
        "login_identifier", "phone", "email", "full_name", "date_of_birth", "gstin", "address"]),
    before_send=_scrub, before_breadcrumb=_scrub,
)
```

- Denial logging in `deps.require_permission` and `EmployeeService._reject_if_more_senior`.

**Done when:** tests pass; `docs/observability.md` §1 and §3 describe the sink rule (G-12);
`.env.example` says `SENTRY_DSN` may only be set after this chunk (it stays blank on staging until
then).

---

## R4 · One origin; production smoke; headers  `P1-3 M8`

**DECIDE (ask the human before coding):** which of the three origin strategies.
Recommended: **FastAPI serves the built SPA** — one Cloud Run service, one origin, cookies stay
`Lax`, zero CORS in production, lowest cost. The alternatives (nginx `/api/` proxy; Cloudflare
route) are documented in the findings file.

For the recommended option:

- `backend/Dockerfile` gains a `node:20-alpine` stage that runs `npm ci && npm run build` and
  copies `dist/` to `/app/static`; build context moves to the repository root
  (`context: .`, `dockerfile: backend/Dockerfile`) — which also lets the image contain `seed/`
  (backlog item) — update `docker-compose.yml`, `.dockerignore`, `ci.yml` accordingly.
- `main.py`: mount a static handler **after** the routers, only when `settings.static_dir` is set;
  non-`/api` paths fall back to `index.html`. `/api/*` never falls back.
- `Settings`: `static_dir: str | None = None`; validator that refuses `"*"` in `cors_origins`
  outside local.
- Security headers middleware (pure ASGI, not `BaseHTTPMiddleware`): `Strict-Transport-Security`
  outside local, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`,
  `Content-Security-Policy: frame-ancestors 'none'`, `Permissions-Policy` minimal.
- `scripts/smoke_prod.py` + `make smoke-prod`: build the runtime image, run it against the compose
  db, log in through it with the seeded owner, fetch `/staff/employees`, assert the SPA index is
  served at `/` and that `/api/v1/nothing` returns the JSON envelope (not `index.html`).

**Tests first:** a test that `GET /` returns HTML and `GET /api/v1/nothing-here` returns
`http.404` JSON when `static_dir` is set; a test that `Settings(cors_origins="*", env="staging")`
raises; a test that every response carries the four headers.

**Done when:** `make smoke-prod` passes; ADR 0005 gets an addendum "Serving topology: single
origin, SPA served by the API" with the date; `api.ts` comment about same-origin now points at
the mechanism that makes it true.

---

## R5 · Lockout redesign; plan and status enforcement; auth audit  `P1-5 P1-10 M1 M5`

**Tests first:**

- Five wrong passwords do **not** produce a 429 for the correct password; instead the sixth wrong
  attempt is delayed ≥ 2 s and the correct password still works (progressive delay, not a lock).
- 30 failed logins from one IP inside 10 minutes → 429 for that IP, other IPs unaffected.
- `current_actor` rejects an access token whose `user_account.status` is `suspended` (M1).
- Login/refresh/`current_actor` refuse when `organization.plan in ('suspended', 'cancelled')`;
  a `trial` past `trial_ends_at` answers `billing.trial_expired` (P1-10).
- Login success, login failure, lockout/throttle and replay each write an `audit_log` row with
  `actor_employee_id` null where appropriate and `ip_address` set (M5).

**Fix:**

- Migration `0003` (or `0004`): `login_attempt(id, ip inet, identifier_hash text, succeeded bool,
  attempted_at timestamptz)` with `IX (ip, attempted_at)` and `IX (identifier_hash, attempted_at)`;
  `organization.trial_ends_at timestamptz`.
- `AuthService`: replace `locked_until`-based hard lock with a delay computed from recent failures
  per identifier (`1s · 2^(n-3)` capped at 30 s, cleared on success); keep `locked_until` only for a
  human-set lock. Per-IP budget from `login_attempt`. Nightly sweep alongside idempotency keys.
- `Dockerfile` CMD: `--proxy-headers --forwarded-allow-ips='*'` (Cloud Run fronts everything);
  `_client_ip` reads what uvicorn resolved.
- `deps.require_entitlement("inventory")` dependency scaffold (no-op until a plan carries features);
  `_home_restaurant` and `current_actor` check the organization's plan.
- Auth events audited through one `AuthService._audit()` helper; `entity_type="user_account"`.

**Done when:** tests pass; `docs/security.md` A07 rewritten to describe the delay + IP budget that
now exists; `.env.example` documents the new knobs; `docs/backlog.md` lockout entry closed.

---

## R6 · Identifiers, rotation grace, session binding  `P1-7 P1-8 M2 M10`

**Tests first:**

- Creating a login with `"+91 98765 43210"` and then signing in with `"9876543210"` works
  (normalisation to E.164 at the boundary), and a second login with either spelling is a 409.
- Two concurrent `_create_login` calls with the same identifier in two organizations: exactly one
  succeeds; the other is a 409, never a 500 (M10 mapping; global unique index).
- Presenting a refresh token a second time **within 60 s** of its rotation returns the *same*
  successor and revokes nothing; presenting it after 60 s revokes the family (P1-8).
- Native client: `POST /auth/password` with the refresh token in the body keeps that session alive
  (M2: `sid` claim).

**Fix:**

- `schemas/identity.py`: a `normalise_identifier()` used by `LoginRequest` and
  `EmployeeCreateRequest.login_identifier` (lowercase email; digits-only phone → E.164 with `+91`
  default from the restaurant's country later, `+91` for now).
- **DECIDE (ask the human):** global unique indexes on `lower(email)` / normalised phone **now**,
  or the per-tenant login surface (org slug on the login form) **now** — `docs/backlog.md`
  (`b01a8b0`) declines the index because the surface makes it obsolete. Either closes the race
  and the cross-tenant 409-vs-201 oracle; carrying both open past M02 is the option to avoid.
  Drop the concurrent-create test if the surface is chosen (the ambiguity no longer exists).
- Migration: `user_session.replaced_by_session_id` (needed regardless).
- `AuthService.refresh`: grace-window logic; `_handle_replay` only outside the window.
- `security.issue_access_token(..., session_id=...)` → `sid`; `current_actor` fills
  `Actor.session_id`; `change_own_password` uses it.
- `EmployeeService._reject_duplicate_code` / `_create_login`: catch `IntegrityError` → 409.
- `api.ts`: `BroadcastChannel('auth')` lock around `refreshOnce()`.

**Done when:** tests pass; `docs/backlog.md` "two stale tabs" entry closed; the "one identifier,
two organizations" entry updated to say the global index now enforces it.

---

## R7 · Bootstrap command; staging on GCP  `M15 D6`

**Why now, not M16:** every module after this adds deploy surface; the M01 manual pass is written
for staging; the origin decision (R4) is only proven by deploying. Cost at pilot scale is ~₹0–1,500
per month. It has slipped three times.

**Precondition:** R1–R4 ticked. Do not put a login form on a public URL while P1-1/P1-2 are open.

**Step 1 — `python -m app.bootstrap`** (test first: creates exactly one org, one restaurant, one
owner with all owner roles; refuses if the slug exists; prints a generated 16-char password once
to stdout and never logs it; writes an `audit_log` row `organization.bootstrap` with no actor):

```
python -m app.bootstrap --org "Spice Garden Hospitality" --slug spice-garden \
  --restaurant "Spice Garden - Koregaon Park" --code SG_KOREGAON \
  --owner-name "Rajesh Mehta" --owner-email owner@example.com
```

**Step 2 — seed on staging without a committed password.** `_refuse_outside_local` becomes:
local → allowed with the YAML password; staging → allowed **only** when `SEED_PASSWORD` is set and
differs from the committed value (the seed uses it for every login); production → always refused.
Test both refusals and the staging path.

**Step 3 — GCP, in this order** (human does the console/billing parts):

1. Project + billing; budget alerts at ₹1,500 / ₹2,400 / ₹3,000 (`docs/observability.md` §9).
2. Postgres: **Neon** free tier (per ADR 0005) with the pooled connection string; enable PITR.
3. Artifact Registry repo `restaurant-os`; Secret Manager: `JWT_SECRET` (48-byte urlsafe),
   `DATABASE_URL`, `SEED_PASSWORD`. No `SENTRY_DSN` until R3 is ticked.
4. Workload Identity Federation for GitHub Actions (no JSON keys in the repo).
5. `.github/workflows/deploy-staging.yml` on push to `main`: build the image with
   `--build-arg GIT_SHA=$(git rev-parse HEAD) --build-arg BUILT_AT=$(date -u +%FT%TZ)`, push,
   run Cloud Run **Job** `migrate` (`python -m alembic upgrade head`) to completion, then deploy
   Cloud Run **service** `restaurant-os-api` with env `ENV=staging DEBUG=false LOG_LEVEL=INFO
   CORS_ORIGINS=<the origin> STATIC_DIR=/app/static`, secrets mounted as env, startup probe
   `GET /api/v1/ready`, liveness `GET /api/v1/health`, `min-instances=0` (becomes 1 at M08 for
   SSE), `max-instances=3`, 512 MiB, concurrency 40.
6. Cloud Run Job `seed` with `SEED_PASSWORD` from Secret Manager; run once.
7. Smoke: `scripts/smoke_prod.py --base https://<service>.run.app`; `/version` shows the commit.
8. Custom domain + HTTPS later; the `run.app` URL is fine for the manual pass.

**Done when:** `GET /api/v1/version` on the staging URL shows the deployed commit; the M01 manual
script's precondition names the staging URL; `docs/checklist.md` blocker rows for cloud accounts
are ticked; ADR 0005 gains "Deployed 2026-xx-xx: Cloud Run + Neon".

---

## R8 · Layering, lockfile, catalogue, docs drift  `D1–D10 M9 M12 X4`

- **Layering (D7):** move `me`/`change_password` logic into `AuthService.profile()` /
  `change_own_password()`; add `EmployeeRepository.code_exists()`, `RoleRepository` (`for_org`,
  `system_roles`, `all_permissions`); replace the raw `select()`s in `EmployeeService` and
  `AuthService._employee_for` (introduce an `OrgScope` for the pre-restaurant login path). Routes
  end up calling exactly one service method each.
- **Size (D8):** split `services/employee.py` into `employee.py` and `role_assignment.py`.
- **Lockfile (M9):** `uv lock`; `uv sync --frozen` in the Dockerfile and CI; pin `ruff` in
  `pyproject.toml` to the pre-commit version; a test that the two agree.
- **Catalogue (M12):** delete the `permissions:`/`roles:` blocks from `seed/organization.yaml` and
  the checks that read them in `seed/validate.py`; `permissions.json` is the only catalogue.
- **`/ready` (X4):** compute the Alembic head once at boot.
- **Docs (D1–D6, D9):** `README.md` status; `frontend/src/lib/enums.ts` → `frontend/src/shared/enums.ts`
  in `CLAUDE.md`, ADR 0002, ADR 0008, `testing-strategy.md`; `sdlc.md` "63-table"; `checklist.md`
  brought current or deleted (decide); `security.md` controls tagged `[built: M01]` /
  `[planned: M16]` per G-7; move `Restaurant Management.docx` to `docs/product/source/`, remove
  `Apoorva-Tasks.xlsx` from the repo, move `issues/*.png` to `docs/manual-tests/evidence/M01/`.
- Extend `scripts/audit_docs.py` with the cross-reference checks above (schema count in sdlc.md;
  enum path).

**Done when:** `make check` clean; `scripts/audit_docs.py` reports 0 issues with the new checks.

---

## R9 · Guardrails become a gate  `G-20`

`scripts/audit_guardrails.py`, run by `make check` and CI, exit 1 on any hit:

| Rule | Check |
|---|---|
| G-1 | every `raise` after a flush in `app/services/auth.py` failure paths is preceded by `commit()` — implemented as: the two regression tests from R1 exist and are collected |
| G-6 | `grep` for `verify_password(` / `hash_password(` outside `security.py` and outside `asyncio.to_thread` |
| G-8 | `select(` appears in no file under `app/services/`; no `app.repositories` import in `app/api/` except `deps.py` |
| G-10 | `uv.lock` exists and is newer than `pyproject.toml` |
| G-12 | `main.py` passes `max_request_body_size="never"` and `before_send` |
| G-14 | `make smoke-prod` target exists |
| G-16 | no `*.xlsx`/`*.docx`/`*.png` at the repository root |
| G-7 | every control paragraph in `docs/security.md` carries `[built: …]` or `[planned: …]` |

Add the guardrails to the Definition of Done via `docs/engineering-guardrails.md` §Definition of
Done addendum (already written) and reference it from `docs/sdlc.md`.

**Done when:** the script runs green in CI and fails on a deliberately planted violation (test it
by temporarily adding a `select(` to a service, then reverting).

---

## Deferred to modules — not part of M01-R

| When | Items |
|---|---|
| M02 | S13 FSSAI column · S14 reservations decision · S12 `POST /auth/switch` · M11 timezone helper |
| M03 | S3 modifier recipes · S10 availability flags · X9 ETag on `/menu` |
| M04 | S11 org-level recipe library · S15 yield on weight only · X8 persisted `unit_cost` · day-1 dish-margin screen |
| M05 | X7 stock balance snapshot · S16 cache rule · prep-sheet thin slice (give it a module number) |
| M07 | S1 `invoice` · S4 channel fields + CSV import · S5 cash close · S6 tips · S7 charges · S9 table merge · PWA manifest + service worker + outbox |
| M08 | S2 `kot_ticket_line` timestamps · M4 pure-ASGI middleware · X6 SSE fan-out and `min-instances=1` · print-agent design note |
| M10 | S8 consent columns · M13 separate guest key · M7 field-level PII gating |
| M13 | X1 permission cache if measured · X10 partitioning |
| M16 | M6 key rotation · RLS · pen-test |
