# M01 · Identity, Roles & Permissions — build log

**Resume from here.** If a session ended mid-module, read this file first, then
`git log --oneline` to see which chunks actually landed. This file is written after each chunk is
committed, so it can be trusted about the past and not about the future.

Spec: `docs/modules/M01-identity-spec.md` · Branch: `feat/m01-identity` (off `feat/m00-foundation`)

---

## State as of the last commit

| Chunk | State | Commit |
|---|---|---|
| A · permission catalogue, enums, drift guards | ✅ done | `5acc8ec` |
| B · 10 tables, migration, catalogue seeding | ✅ done | `da9c489` |
| C · argon2id + JWT primitives | ✅ done | `5fb20fb` |
| D · tenant-scoped repositories | ✅ done | `180b7c7` |
| E · seniority ladder (managers assign roles) | ✅ done | `03bfef4` |
| F · auth service: login, refresh, logout, password | ✅ done | `7468f9d` |
| G · API surface + the four generic suites | ✅ done | `15810e1` |
| H · `make seed` — two organizations, five logins | ✅ done | `823c3e5` |
| I · frontend: login, staff list, employee form, roles, profile | ✅ done | `3a11a35` |
| J · adversarial review, manual test script, `make check` | ✅ done | `d80e268` |

**252 backend tests · 97.2% coverage · 31 frontend tests · ruff, mypy, eslint, tsc clean.**

**Remaining before M01 can be called done: your manual pass** (`docs/manual-tests/M01-identity.md`,
~25 minutes). Everything else in the Definition of Done is met.

### What chunk H did

`make seed` loads `seed/organization.yaml` — the authoritative P1 artefact, already guarded by
`seed/validate.py` — instead of restating it in Python. Verified against the live stack, not only
the test suite: 2 organizations, 2 restaurants, 19 employees, 15 logins, 19 role assignments, and
**4 employees with no login at all** so ADR 0007 is visible in the demo.

Everything is get-or-create by natural key, on the keys the database already enforces as unique.

**Where the seed data lives, and why it is awkward.** The dataset is at the repository root; the
backend's Docker build context is `./backend`, so the image cannot contain it. Compose mounts
`./seed:/app/seed:ro` and the loader searches `SEED_DIR`, then `/app/seed`, then the working copy.
This is enough for local and for a staging box running the same compose file. **Packaging it into
the image belongs to M15** with the generator — noted in `docs/backlog.md`, not forgotten.

### What chunk I did

The staff bundle: login · staff list · employee create/edit · role assignment · own profile.

The access token lives in a module variable and nowhere else. The refresh token is never in
JavaScript at all — it is the httpOnly cookie the API already set, which is what lets a page reload
restore a session the previous tab's memory no longer holds. A 401 buys **exactly one** refresh and
one replay, single-flighted: refresh rotates the token, so three panels 401ing together would
otherwise send two replays, and the backend correctly reads a replayed refresh token as theft and
revokes the whole family. The user would be signed out for loading a page.

Verified in a real browser against the running stack, not only in vitest — the browser is where the
two defects below were plausible and the test suite was not going to find them.

### What chunk J did

**The manual script was rewritten**, which was expected: it was authored before the code as a
format demonstration and said its step values would be confirmed at ship. Steps C1/C4 expected a
waiter on a waiter screen and a chef on a kitchen screen (M07 and M08); step B6 expected duplicate
employee phone numbers to be refused, but `employee.phone` is deliberately not unique — only a
*login* identifier is. Every change is listed in a table at the bottom of that file so the
difference is auditable rather than quietly rewritten.

**Three defects found by the adversarial review** (step 7), each with a regression test written
first. They are listed with the others below — 11, 12 and 13.

---

## Decisions taken during implementation

These changed the approved spec and are worth re-reading before the manual pass.

1. **`audit_log` is created in M01**, not M14. M01 introduces role grants, deactivations and
   password resets — exactly what an insider would use. M14 still owns the decorator, the `/audit`
   endpoint and the viewer.
2. **Two organizations, not one.** `docs/seed-data.md` (the authoritative P1 artefact) says Tandoor
   House is a second organization; the M01 spec contradicted it. Spec corrected.
3. **Isolation is enforced at both levels.** Organization is the hard tenant boundary; within one
   organization an employee is visible only at a restaurant they are assigned to, because "a
   manager reads another branch's staff" is its own entry in the threat table. One deliberate
   exception: an employee with no assignment anywhere stays visible inside their organization, or
   the person a manager just created would be invisible to that manager.
4. **Managers hold `employee.role.assign`** (user decision), made safe by a **seniority ladder**
   in `permissions.json`: `owner 0 · admin 10 · manager 20 · chef/store_manager/accountant 30 ·
   waiter/kitchen_staff/cleaner 40`. Nobody grants a role senior to their own; nobody edits their
   own roles. Permissions alone cannot express this — in M01 a manager and an owner hold the same
   seven permissions.
5. **Owner notification is captured, not delivered.** Every assignment writes an `audit_log` row.
   Delivery is M14's deliverable (`docs/backlog.md`).
6. **Login resolves the identifier across organizations.** Safe because every failure is identical;
   an identifier matching two organizations is refused the same way. Backlogged.

---

## Defects found and fixed during this module

Each was a real bug, caught by a test or by running the thing — not a style change.

1. **`alembic/script.py.mako` had no `${imports}` hook.** Every autogenerated migration touching
   JSONB or INET referenced `postgresql.` without importing it. The M01 migration would have died
   with `NameError` on first run, and so would every migration in M02–M17. Fixed at the template.
2. **`ON CONFLICT (organization_id, code)` cannot fire for system roles** — NULL does not constrain
   in a UNIQUE, and the system templates are exactly the NULL rows. Re-running the seed would have
   silently doubled every role, and permission resolution would join whichever row it found. Fixed
   with a partial unique index.
3. **The test session fixture could not survive an `IntegrityError`,** so every test asserting the
   database rejects something died in teardown. Fixed with
   `join_transaction_mode="create_savepoint"`.
4. **PyJWT only warns on an HMAC key shorter than the hash output** (RFC 7518 §3.2), and nobody
   reads a warning in a production log. A short `JWT_SECRET` now fails the boot.
5. **The development JWT secret is committed to this repository** and would have shipped to
   staging, where anyone reading the source could mint an owner token. Now a boot failure.
6. **Validator ordering regression I introduced:** the new JWT check ran before the DEBUG check, so
   a staging boot with `DEBUG=true` reported the JWT secret instead of the more fundamental
   mistake. Caught by an M00 test.
7. **The decoy password hash was computed at import time,** making `app.services.auth` unimportable
   without full Settings and putting an argon2 hash on every process start. Now lazy.
8. **Coverage was not tracing code executed inside the ASGI application.** httpx's transport runs
   handlers under anyio and SQLAlchemy's async layer under greenlet, neither of which coverage
   follows by default. The employee service reported **47%** while 41 endpoint tests exercised it;
   with `concurrency = ["thread", "greenlet"]` it is **96% on the same tests**. Left alone this
   understates every future module's API coverage and pushes people towards service-level tests
   instead of the endpoint tests the Definition of Done asks for.
9. **FastAPI 0.141 no longer flattens included routers into `app.routes`,** so the obvious route
   enumerator returns nothing. All four generic suites are loops over routes — an empty enumerator
   makes every one of them pass while testing nothing, permanently and green.
   `tests/helpers/routes.py` handles both routing shapes and is paired with a meta-suite asserting
   it found the routes we know exist.
10. **Listing deactivated staff required `?is_active=`** (an empty string), which is a 422. A
    tri-state boolean is not expressible in a query string, so it worked from Python and would have
    been undiscoverable from the UI. Replaced with `include_inactive`.

11. **The staff list was an N+1.** Rendering a row needed that person's roles, and asked for them
    per row — measured at **7 queries for 3 people and 25 for 21**. `assert_max_queries` had
    existed since M00 and was pointed at nothing but itself, so acceptance criterion 12 and the
    Definition of Done's "no N+1" line were never actually claimed by any test. The new
    `tests/test_query_counts.py` asserts the *shape* — identical query count across page sizes —
    rather than a budget, because a budget of six passes for a page of five rows while still
    hiding a query per row. The batched lookup seeds every requested id with an empty list; a dict
    built only from the join's rows would silently drop anyone holding no role here, and that
    person is exactly the one a manager just created.
12. **Your own profile showed a blank employee code.** `/auth/login` answers with a credential and
    a summary; only `/auth/me` carries `employee_code`. Both ways into a session now read the
    profile. This one survived the whole build because a page reload repaired it, and developers
    reload constantly — the sort of defect that reaches a user precisely because it never reaches
    the person writing the code.
13. **The staff list stopped at fifty people and said nothing.** The endpoint pages and returns a
    cursor; the screen ignored it. A sixty-person restaurant would have shown fifty with nothing on
    screen to suggest otherwise — a silent failure, which engineering-standards §5 forbids, and
    invisible against demo data of nineteen.

### Two tests that were lying, found by mutation testing

Worth recording because the pattern will recur.

- **Cross-organization isolation.** Deleting the organization filter entirely left both explicit
  cross-org tests green: they were passing on the *branch* filter's side effect (another tenant's
  restaurant id never matches ours), not on the boundary they claimed to test. The one path relying
  on the organization filter alone is the login lookup, which had no test at all. Added.
- **The catalogue validators.** The tests asserted the shipped JSON was clean, which they would do
  just as happily if the validators were deleted. Added tests that feed them a bad catalogue.

The general rule: a passing test proves a property holds, not that *your code* is what makes it
hold. Where two defences overlap, only mutation testing says which one the test is watching.

---

## How to verify state without trusting this file

```
git log --oneline                      # which chunks actually landed
make dev                               # api, db, web — Docker Desktop must be running
make seed                              # idempotent; run it twice, nothing should double
cd backend && ./.venv/Scripts/python.exe -m pytest -q     # 252 tests, 97.2%
cd frontend && npx vitest run          # 31 tests
make check                             # the blocking gate
```

**If the whole backend suite errors at once**, check Docker Desktop is actually running before
suspecting the code — testcontainers needs the daemon, and 136 tests erroring on
`//./pipe/dockerDesktopLinuxEngine` is what its absence looks like.

**If the web app is blank after a dependency change**, restart the `web` container. Vite's
dep-optimizer can end up serving two copies of a library (`?v=<hash>` differing between them), and
the symptom is a React context that is set by one copy and read by the other — "No QueryClient set"
despite a provider being right there in the tree.

---

## What is left

The Definition of Done in `docs/sdlc.md` is met on every line **except the last human one**:

- [x] Every acceptance criterion in the spec
- [x] Migration reversible, up→down→up on real Postgres
- [x] `docs/schema.md` matches reality — all 10 tables, including the partial unique index
- [x] Unit, integration, four generic suites, query-count assertions, regression test per defect
- [x] `make check` clean, zero warnings
- [x] Permission declared on every route; tenant scoping through repositories only
- [x] Audit entries for every permission-affecting change
- [x] Manual script written
- [ ] **You have run it and every step passes** ← the only thing outstanding
- [ ] Exploratory charter done and findings triaged

Run `docs/manual-tests/M01-identity.md` (~25 min). Report failures as step number + expected + saw.
Every bug found there gets a regression test written **before** the fix.
