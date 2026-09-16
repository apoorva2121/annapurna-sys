# M01 · Identity, Roles & Permissions — Module Spec

**Status:** awaiting your approval (step 1 of the module loop, `docs/sdlc.md`)
**Estimate:** 3 days · **Depends on:** M00 · **Blocked by:** M00 manual pass; staging URL (see Risks)

## Scope

The first module with data, the first with routes, and the largest security surface in the product.
Everything after this inherits its decisions, so it is worth the three days.

Four things ship together:

1. **Authentication** — login, refresh, logout, password change, lockout.
2. **The employee record** — the business profile, which may or may not have a login attached.
3. **Roles and permissions** — a seeded catalogue, checked by permission string, never by role name.
4. **The four generic test suites** — tenant isolation, permission matrix, persona separation,
   route declaration. M00 had no routes to run them against; M01 is where they become real and
   start covering every module that follows, automatically.

Implements ADR 0003 (tenant scoping), ADR 0007 (auth split from employment), ADR 0008 (keys and
deactivation tiers), ADR 0009 (staff/guest personas).

## Not in scope

- **MFA.** `mfa_secret` exists as a column; no enrolment flow. `docs/security.md` A07 offers MFA to
  owner and admin "from day one" — that is a day-one *capability of the schema*, and the flow is
  backlogged rather than built now.
- **Customer authentication.** Guests get table tokens in M10. The guest route tree stays empty.
- **Password reset by email/SMS.** No transactional provider is wired yet (M14). An owner resets a
  staff password; a forgotten owner password is a support action in month 1. This is written down
  as a known gap, not discovered later.
- **`employee_permission_override`** — per-person grants. ADR 0007 defers it explicitly.
- **Restaurant and organization CRUD.** M02 owns settings; M01 creates them by seed only.

## Deliverables

### Migration — 9 tables

Exactly the nine in `docs/schema.md` §1: `organization`, `restaurant`, `user_account`,
`user_session`, `employee`, `role`, `permission`, `role_permission`, `employee_role_assignment`.

Plus the data the catalogue needs, seeded **by migration** so it is version-controlled and diffable
(ADR 0007):

- every `permission` row the codebase references
- the 9 system `role` templates (`organization_id IS NULL`, `is_system = true`)
- the `role_permission` rows binding them — **the table you fill in below**

`downgrade()` implemented and tested up→down→up on real Postgres.

### Backend — repository → service → API

**Core primitives every later module uses.** These are the real deliverable; the endpoints are
almost a side effect.

| Piece | Contract |
|---|---|
| `TenantScope` | `organization_id` + `restaurant_id`, resolved from the token, injected into every repository. There is no way to construct a repository without one. |
| `BaseRepository` | Applies the `restaurant_id` filter itself. A subclass cannot forget. Organization-level entities use an `OrgScopedRepository` — a separate class, so the difference is visible in review. |
| `require_permission("x.y")` | A FastAPI dependency that resolves the actor's effective permissions for the *current restaurant* and fails closed. Never compares a role name. |
| `current_actor` | The authenticated employee plus scope. Guest tokens are a different type and cannot satisfy it (ADR 0009). |
| `uuid7()` | Application-side id generation, per ADR 0008. |

**Endpoints** — all under `/api/v1/staff/`, except auth which sits at `/api/v1/auth/`:

```
POST   /auth/login              identifier + password    -> access token + refresh
POST   /auth/login/choose       second step when one password opens several organizations (B4)
POST   /auth/refresh            rotates the refresh token, revokes the old one
POST   /auth/logout             revokes the presented session
POST   /auth/password           own password change; revokes every other session
GET    /auth/me                 own profile, roles, effective permissions
GET    /auth/restaurants        branches beyond the 20 `/auth/me` embeds, cursor-paged (backlog-issues B3)

GET    /staff/employees         list, paginated, filterable by is_active
POST   /staff/employees         create (optionally with a login)
GET    /staff/employees/{id}
PATCH  /staff/employees/{id}
POST   /staff/employees/{id}/deactivate    revokes every session immediately
POST   /staff/employees/{id}/reactivate
POST   /staff/employees/{id}/roles         set role assignments for a restaurant

GET    /staff/roles             roles visible to this organization
GET    /staff/permissions       the catalogue, for the role-assignment UI
```

`GET /auth/me` is not in `docs/modules.md`. It is added because the frontend cannot render a
permission-aware navigation without it, and the alternative — the client inferring permissions from
a role name — is the exact anti-pattern ADR 0007 forbids.

**Minimal seed** (`make seed`): **two organizations** — Spice Garden Hospitality (with the
restaurant Spice Garden) and Tandoor House (with the restaurant Tandoor House) — and the five
logins `docs/manual-tests/M01-identity.md` already names. The full seed generator remains M15.

> Corrected during implementation. This section originally read "one organization, two
> restaurants", which contradicts `docs/seed-data.md`: *"A second organization, Tandoor House,
> exists on purpose... every tenant-isolation test needs a second tenant to fail against."*
> seed-data.md is the authoritative P1 artefact and describes the stronger boundary, so it wins.
>
> Isolation is nevertheless enforced at **both** levels, because the threat table below names
> "a manager reads another branch's staff" as an attack in its own right: the organization is the
> hard tenant boundary, and within an organization an employee is visible only at a restaurant
> they are assigned to. A chain with two branches in one organization therefore does not leak
> staff between them, even though month 1 ships no multi-branch features.

### Frontend — staff bundle

Login · staff list · employee create/edit · role assignment · own profile.

- Access token in memory only, never `localStorage`; refresh token in an httpOnly cookie.
- A `<RequirePermission>` wrapper hides navigation the actor cannot use — **presentation only**.
  The server denies regardless; the UI just avoids showing doors that do not open.
- Every mutation has explicit pending, error and success states (`docs/ui/conventions.md`).
- A 401 triggers exactly one refresh attempt, then a redirect to login. Never a refresh loop.

## Acceptance criteria

1. A seeded owner logs in on staging and lands on a page that names their restaurant
2. Unknown identifier and wrong password return the **byte-identical** error — no enumeration
3. 5 failed attempts lock the account; the response says roughly how long
4. Deactivating an employee **revokes every session immediately** — the next request from that
   person's open tab fails, without them logging out
5. Changing a password revokes every other session but not the current one
6. A refresh token can be used exactly once; replaying it revokes the whole session family
7. Restaurant A's manager receives 404 for restaurant B's employee id — asserted for every
   registered staff route by the generic suite, not one hand-written test
8. Every registered route declares a permission; a route without one **fails the build**
9. A waiter's token gets 403 on `/staff/employees`, and the waiter UI never renders the link
10. An employee can be created with **no login at all** and still be referenced (ADR 0007)
11. No password, hash, or refresh token appears in any response body or any log line
12. `make check` clean, zero warnings; list endpoints pass `assert_max_queries`

## Threat question — *what would an insider do with this?*

The insider here is a real person on the payroll, which is what makes M01 different from M00.

| Attack | Control |
|---|---|
| A manager reads another branch's staff, wages, or later their sales | `TenantScope` in the repository, enforced structurally; generic suite over every route |
| A departing employee keeps working sessions after being removed | Deactivate revokes all sessions in the same transaction — one action, not three (`docs/security.md` A07, attacker #4) |
| Someone escalates their own role | Role assignment requires `employee.role.assign`, which no operational role holds; every assignment writes an `audit_log` row with actor and before/after |
| **A branch manager takes over a senior person's account via a junior role that person holds at their branch** | Added after the 2026-09-11 audit (P1-2). Roles are per branch; a password, a login and an employment are not. Account-level authority is judged on `most_senior_rank_anywhere()` — the target's most senior role across the whole organization — so an admin who covers shifts as a waiter at branch B is still an admin to B's manager. Every identity test runs against a two-branch fixture (G-17), because a single-branch fixture cannot see this class of bug and did not |
| **A manager acts as a peer by resetting their password** | `may_reset_password()` requires *strictly* more senior, unlike `may_assign_rank()` which permits equal rank. Appointing a peer is not escalation; being one is. Two owners are the deliberate exception, or a locked-out owner has no recovery path at all |
| **Someone resets a password and keeps using it** | A reset sets `user_account.password_reset_required`; the next login answers `password_change_required` and the profile screen says plainly that whoever set it still knows it. The flag clears when the account's owner changes the password |
| Someone reads the staff list to harvest phone numbers | Permission-gated, and phone numbers are redacted from logs by the M00 filter — which is why that filter was built before any PII existed |
| A shared tablet left logged in | Out of scope and stated as such (`docs/security.md`): short access-token life limits it, nothing eliminates it |
| Credential stuffing from outside | argon2id, lockout with backoff, per-IP rate limit, identical failure messages |
| A stolen database dump yields live sessions | Refresh tokens stored hashed; a dump yields hashes, not sessions |

## Tests

| Test | Asserts |
|---|---|
| `test_login_enumeration` | unknown identifier and wrong password produce identical status, body and timing band |
| `test_lockout` | 5 failures lock; a correct password during lockout still fails |
| `test_refresh_rotation` | a replayed refresh token revokes the family and returns 401 |
| `test_deactivate_revokes_sessions` | an in-flight session dies on the next request |
| `test_password_change_revokes_others` | current session survives, others do not |
| `test_role_change_revokes` | a permission change takes effect without waiting for token expiry |
| `test_employee_without_login` | create, list and reference an employee with `user_account_id IS NULL` |
| **`test_tenant_isolation_all_routes`** | generic: enumerates every staff route, asserts 403/404 across tenants |
| **`test_permission_declared_all_routes`** | generic: a route with no declared permission fails the suite |
| **`test_persona_separation`** | generic: no guest token satisfies any staff dependency |
| `test_no_secrets_in_responses` | no hash, token or password field in any serialised schema |
| `test_query_counts` | employee list is O(1) queries regardless of page size |
| `test_migration_roundtrip` | up→down→up, including the seeded catalogue |

## Open decisions — I need your answer before I build

### 1 · Role to permission defaults

This is domain knowledge, not engineering. The uncontested rows are filled; **the contested ones are
marked `?`** because getting them wrong is either a security hole or a daily annoyance for a real
person. Once you settle them I turn this table into `app/core/permissions.py` and the seeding
migration — it is the single most consequential table in the module.

| Permission | owner | admin | manager | chef | store_mgr | waiter | accountant |
|---|---|---|---|---|---|---|---|
| `employee.view` | yes | yes | yes | ? | ? | no | ? |
| `employee.create` / `.edit` | yes | yes | ? | no | no | no | no |
| `employee.deactivate` | yes | yes | ? | no | no | no | no |
| `employee.role.assign` | yes | ? | no | no | no | no | no |
| `employee.password.reset` | yes | yes | ? | no | no | no | no |
| `role.view` | yes | yes | yes | no | no | no | no |

The two that actually matter:

- **Can a manager create staff and reset passwords?** Yes is how a restaurant really runs — the
  owner is not on site at 7am. No is safer. My recommendation: **yes to create and reset, no to
  role assignment**, so a manager can staff their shift but cannot promote themselves.
- **Should a chef see the staff list?** They run the kitchen and need to know who is on. My
  recommendation: **`employee.view` yes, everything else no.**

### 2 · What do staff log in with?

`user_account` allows email *or* phone (`CHECK (email IS NOT NULL OR phone IS NOT NULL)`), so the
schema does not force this — the UX does.

Many waiters and kitchen staff in an Indian restaurant do not have a working email address they
check. **Phone plus password** is the honest default, with email allowed for owner, admin and
accountant. It also matches the phone number already stored on `employee`.
Say if you would rather force email for everyone.

### 3 · Who unlocks a locked account, and after how long?

`docs/security.md` says lockout after 5 failures with exponential backoff. It does not say who can
clear it. My recommendation: **auto-unlock after 15 minutes**, plus owner and admin can clear it
instantly — because at 7pm on a Saturday, "wait fifteen minutes" means one fewer person taking
orders.

**Superseded 2026-09-14 (backlog-issues B5, owner decision D28).** There is no automatic lock any
more: a stranger could lock a waiter out with five guesses, and "locked" told them the login was real.
Wrong passwords make each next attempt for that login wait longer, a network that keeps failing is
refused for a while, and a lock is set only by a person — lifted by a password reset.

## Risks

| Risk | Mitigation |
|---|---|
| **The M01 manual script targets staging**, which does not exist yet | The day-2 deploy runs before M01 handover. If it slips, the script runs against local Compose and step A1's URL changes — same as M00 did. Say the word and I will not let this block the code. |
| Auth is the module where "almost right" is a breach | The generic suites are written **first**, before the endpoints, so a route is covered the moment it is registered rather than when someone remembers |
| Argon2 parameters too slow on the pilot's hardware | Tune cost against the real container, assert login stays under 400ms, keep the parameters in `Settings` rather than hardcoded |
| Scope creep into M02 settings screens | The seed creates the restaurant; the settings UI is M02. Anything tempting goes to `docs/backlog.md` |
| 3 days is optimistic for 9 tables, 15 endpoints and 4 generic suites | The suites are reusable infrastructure amortised over 17 modules. If it runs to 4 days, the plan absorbs it — `docs/plan/month-1.md` has M00–M05 at 17 of 20 days |

## What I need from you

1. **Approve this spec**, or tell me what to change
2. **Answer the three open decisions above** — decision 1 is the important one
3. Nothing else. With those, M01 goes to green without further input, up to your manual pass.
