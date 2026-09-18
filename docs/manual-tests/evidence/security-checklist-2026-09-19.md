# Security checklist · run of 2026-09-19

**Run by:** autonomous session, against `feat/m11-communication` at the M18 commit.
**Source:** `docs/manual-tests/security-checklist.md`. Module: M16 chunk A.

---

## How to read this

Every row carries one of four outcomes, and the fourth is the honest one:

| Mark | Means |
|---|---|
| **PASS** | Verified, with the evidence named. A test, a suite, or a line of code you can open |
| **FAIL** | Verified broken. Fixed in this module with a regression test, or ticketed |
| **N/A** | Does not apply, with the reason stated. Never a blank |
| **CONSOLE** | Requires a live GCP or Neon session, or a browser in front of a person. **Not attempted, not ticked** |

A checklist row ticked without being run is worse than a blank one, so nothing below is marked
PASS on the strength of having read the configuration that would produce it. Where a row's intent
is met more completely by a test suite than by the hand-check the row describes, that is said
rather than assumed — a suite that probes **every** route beats a person probing one.

**Scope note.** M17 (Workload & Fairness) and M18 (Compliance) shipped on 2026-09-19 and are in
scope here like every other module. An earlier draft of the M16 spec planned to defer them; they
exist, so they are covered.

---

## 1 · Tenant isolation 🔴

| # | Outcome | Evidence |
|---|---|---|
| 1.1 | **PASS** | `tests/test_generic_suites.py` — 29 passed. Suite 1 walks every registered staff route |
| 1.2 | **PASS**, by something stronger | The row asks for one URL pasted by hand. Suite 1's `test_no_staff_route_exposes_another_tenants_resource` does it for **every path parameter on every route**, against a victim row owned by a second tenant. It refused this build twice while M17 and M18 were written |
| 1.3 | **PASS** | Same suite. Victim rows exist for order, employee, customer, recipe, stock batch, invoice and 20 more; `test_every_path_parameter_has_a_victim_row` fails the build if a new parameter has none, which is what makes 1.3 hold for routes nobody has written yet |
| 1.4 | **PASS** | No route in `app/api/` declares `restaurant_id` as a query parameter. The scope comes from the token (`Actor.scope`), never from the request |
| 1.5 | **PASS** | Three raw-SQL sites in `app/`, none of them a tenant read: `db.py:68` (`SELECT 1` health probe), `seed/generate.py:930,936` (`SET LOCAL session_replication_role`, around the generator's settled-bill insert). Every other query goes through a repository constructed with a `TenantScope` |

---

## 2 · Authentication 🔴

| # | Outcome | Evidence |
|---|---|---|
| 2.1 | **PASS** | `app/core/security.py` uses `argon2.PasswordHasher`; `app/core/config.py:74-76` sets time cost 3, 64 MiB, parallelism 4. No plaintext column exists — `user_account.password_hash` is the only credential field |
| 2.2 | **PASS** | `user_session.refresh_token_hash` and `sign_in_choice.token_hash` (`app/models/identity.py:98,164`) are hashes with a unique index; `auth.py` hashes on write and on lookup (`hash_refresh_token`) |
| 2.3 | **PASS** on the response, **CONSOLE** on the timing | Unknown identifier and wrong password both raise `auth.invalid_credentials` with an identical envelope. *Similar timing* under load is a measurement, not a code read, and belongs with the k6 run |
| 2.4 | **PASS** | `user_account.failed_attempts` and `locked_until` (`app/models/identity.py:71,74`), checked at `auth.py:316` and reset at `374`. `login_attempt` carries the backoff |
| 2.5 🔴 | **PASS** | `tests/test_auth_service.py:303,454` — a deactivated employee cannot log in and cannot refresh. The access token's ~15-minute life bounds the window |
| 2.6 | **PASS** | `app/services/employee.py:416` — *"Resetting someone else's password. Ends every session they have."* |
| 2.7 | **PASS** | `tests/test_auth_service.py:419,442` — a replayed rotated token kills the whole family; an expired session cannot be refreshed |
| 2.8 | **N/A** | **MFA is not built.** `user_account` has no MFA column and nothing writes one. It is a module of its own, named as out of scope in the M16 spec. This row is not a tick and not a blank: the product ships without MFA, and the owner should know that before the first real restaurant signs in |

---

## 3 · Authorisation

| # | Outcome | Evidence |
|---|---|---|
| 3.1 | **PASS** | Suite 4 (`test_generic_suites.py`) walks the routing table and fails on a route with no declared permission. It refused M17's routes twice and M18's once |
| 3.2 | **PASS** | Suite 2, every role × every route |
| 3.3 | **PASS** | No `== "owner"`, `== "manager"`, `== "waiter"` or `== "chef"` anywhere in `app/` outside the seed. Authorisation is by permission, never by role name (ADR 0007) |
| 3.4 | **PASS** | Suite 2 covers it; `order.void`, `order.comp` and `cost.view` are not in the waiter's grant |
| 3.5 | **PASS** | Suite 2. The chef's catalogue entry says it in words: *"A chef sees grams, not rupees"* |

---

## 4 · Guest surface 🔴

| # | Outcome | Evidence |
|---|---|---|
| 4.1 🔴 | **PASS** | Suite 3 (persona separation). ADR 0009 makes it structural — a guest token cannot produce an `Actor`, and staff and guest share no dependency chain |
| 4.2 | **PASS** | `test_generic_suites.py:320` — `test_no_guest_response_carries_a_forbidden_field` walks the guest response schemas rather than one response |
| 4.3 | **PASS** | Bill tokens are hashed at rest and die with the order; table slugs are 128-bit |
| 4.4 | **PASS** | `app/core/rate_limit.py` — declared on the route the way a permission is, with `RATE_LIMIT_MARKER` so suite 5 proves no guest route was registered without one. **Its limitation is documented and real**: the counter is in-process, so two containers double an attacker's budget. `docs/backlog.md` carries the fix and its trigger (the day a second instance is deployed) |
| 4.5 | **PASS** | Guest phone lookup answers identically for existing and non-existing numbers |
| 4.6 | **PASS** | Suite 3 plus the bill-token scoping |

---

## 5 · Money integrity 🔴

| # | Outcome | Evidence |
|---|---|---|
| 5.1 🔴 | **PASS** | Prices are never read from a request body. `OrderLine` prices come from `menu_item_variant`; `tests/test_settlement.py:278` settles a real printed bill to the paisa |
| 5.2 | **PASS** | Tax is computed from `tax_rate` on the line (`ck_order_line_gst_split`); discounts go through `order_discount` with an authoriser |
| 5.3 | **PASS** | `tests/test_settlement.py:392` — a double-tapped settle charges the table once. `tests/test_idempotency.py` covers the general mechanism, including a key too short to be unguessable |
| 5.4 | **PASS** | `tests/test_settlement.py:365,377` — a stale version cannot settle; a settled order cannot settle again. `tests/test_idempotency.py:203` races two taps against one key on a real database |
| 5.5 | **PASS** | `tests/test_orders_endpoints.py:813` — a discount *names its authoriser*; the column is NOT NULL |
| 5.6 | **PASS**, and it was unverified until now | Gaplessness per financial year was enforced and tested; **nothing had ever crossed a boundary**, which is the only place the rule can be wrong. `tests/test_financial_year_boundary.py` now settles 31 March and 1 April — and 01:30 on 1 April, where the business date and the calendar date disagree. It passes against the existing code: the gap was in the tests, not in the product. See §Findings 1 |
| 5.7 | **PASS** | One `float(` in `app/` and it is in a comment explaining why `str()` is used instead (`app/api/v1/staff/stock.py:237`). Money is `NUMERIC(12,2)`/`Decimal` throughout (invariant 3) |

---

## 6 · Input and uploads

| # | Outcome | Evidence |
|---|---|---|
| 6.1 | **PASS** | 39 of 41 schema modules declare `extra="forbid"`. The two that do not are `__init__.py` (no models) and `gstin.py` (a validator, not a request body). `tests/test_employee_endpoints.py:325` asserts the behaviour end to end |
| 6.2 | **PASS** | Every query is parameterised through SQLAlchemy; the three raw-SQL sites in §1.5 take no user input |
| 6.3 | **CONSOLE** | *"then view it everywhere it renders"* is a browser check. React escapes by default and the product uses no `dangerouslySetInnerHTML` — but the row asks somebody to look, and that is the owner's manual pass |
| 6.4 | **PASS** | `tests/test_attachments.py:91` — *"a jpeg is recognised and an executable calling itself one is not"*; `:95` a PNG offered as a JPEG is refused. Content, not extension |
| 6.5 | **PASS** | The size cap is enforced before the body is read |
| 6.6 | **PASS** with a caveat | Attachments are served with `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` and `Content-Security-Policy: sandbox; default-src 'none'` (`app/api/v1/staff/attachments.py:173-175`). **Not a separate origin** — ADR 0005 chose one origin deliberately. The three headers are what stands in for it, and they are on the response rather than on a proxy |

---

## 7 · Configuration and transport

| # | Outcome | Evidence |
|---|---|---|
| 7.1 🔴 | **PASS** | `app/core/config.py:146` — `_debug_is_local_only` refuses to construct `Settings` when `debug` is true outside `Environment.LOCAL`. The app cannot boot, rather than booting and warning |
| 7.2 | **FAIL → fixed** | No HSTS anywhere. `app/core/security_headers.py`, and only over TLS — a `max-age` on `localhost` pins a developer's browser for a year. See §Findings 2 |
| 7.3 | **FAIL → fixed** | No CSP and no `X-Frame-Options` on the application's own responses. `app/core/security_headers.py` sends both, plus `nosniff`, and never overwrites the stricter policy the attachment route sets on somebody else's bytes. See §Findings 2 |
| 7.4 | **PASS** | `app/main.py:187` — `allow_origins=settings.cors_origin_list`, an allow-list. No `*` |
| 7.5 🔴 | **CONSOLE** | `gitleaks` is not installed in this environment. `make check`'s dependency audits run, but a secret scan over history is a separate tool and a separate run |
| 7.6 | **PASS** | `make check` runs `pip-audit` and `npm audit`; the gate is green |
| 7.7 | **PASS** | `app/core/errors.py` — `{code, message, details, issue}` plus a `request_id`. No stack trace leaves the process (D11, D12) |

---

## 8 · Logging and audit

| # | Outcome | Evidence |
|---|---|---|
| 8.1 🔴 | **PASS** on the mechanism, **CONSOLE** on production logs | `app/core/logging.py` installs redaction **on the handler**, so no log call anywhere can bypass it, and its docstring records the near-miss it was hardened against (a UUID fragment that looked like a phone number). Searching *production* logs needs production |
| 8.2 | **PASS** | Same filter; `REDACTED` covers password, token and refresh values |
| 8.3 | **PASS** | `app/core/audit.py` plus `tests/test_audit_declarations.py`, an AST guard that fails the build when a service method that writes is not declared as audited. 7 module and 28 method exemptions, each with a written reason |
| 8.4 | **PASS** | No endpoint updates or deletes an `audit_log` row. `record()` is the only place one is constructed |
| 8.5 | **CONSOLE** | `sentry_sdk` is initialised (`app/main.py:158`) and the DSN is configuration. *Active before the first event* is verified against the Sentry project, not the code |

---

## 9 · DPDP and GST compliance 🔴

| # | Outcome | Evidence |
|---|---|---|
| 9.1 | **CONSOLE** | *"not pre-ticked"* is what a person sees. The owner's manual pass |
| 9.2 | **PASS** | `customer_consent` stores `notice_version`, `notice_language`, `source`, `captured_by` and `occurred_at` |
| 9.3 | **PASS** | **This row was expected to fail and does not.** `GET /staff/customers/{id}/export` exists (`app/api/v1/staff/customers.py:215`), is audited, is per-customer with no bulk version in any role, and returns the person, their consent history and their order history. The M16 spec's first draft said it did not exist; that was wrong and is corrected there |
| 9.4 🔴 | **PASS** | Erasure anonymises and keeps the order. `customer.erased_at` plus the retention of `order`; revenue totals do not move |
| 9.5 | **CONSOLE** | The purge job's window is configuration, and *"runs"* is an observation of a running system |
| 9.6 | **PASS** | `invoice` stores `supplier_gstin`, `fssai_licence`, `cgst_total`, `sgst_total` at settlement. **M18 now warns when any of them is absent or malformed** — `gst.gstin_missing` and `fssai.malformed`, both critical, both conditional on a bill having been issued. Veg/non-veg marks come from `menu_item.food_type`. What does *not* exist is a rendered document: `docs/compliance-rules.md` §D carries it as an M07 follow-up, and printing is out of scope for month 1 |
| 9.7 | **PASS** | A refund is a negative payment referencing a `credit_note` — the tax document. `docs/schema.md` eliminates a `refund` table for exactly this reason |

---

## 10 · Backup and recovery 🔴

Every row here needs a live console session. **None is ticked.**

**The database is Neon, not Cloud SQL** (`docs/deploy/gcp-staging-runbook.md` §1), which changes
what these rows even mean: Neon keeps **change history**, not backups, and a restore is a branch
taken at a past moment inside that window. `docs/runbooks/restore.md` is now written against it
with real commands.

**And the number that matters is not RPO.** `docs/observability.md` §7 records RPO ≤ 5 minutes,
which Neon meets easily. What was never written down is **how far back a restore can reach** —
the history window, which defaults to **6 hours on the Free plan and 1 day on paid plans**
(checked 2026-09-19). Nobody notices a bad settlement within six hours. Raising it before a real
restaurant's data goes in is a finding, not a preference.

| # | Outcome | What the owner must run |
|---|---|---|
| 10.1 | **CONSOLE** | Confirm the Neon project's history window and encryption at rest. **Neon keeps change history, not backups** — see `docs/runbooks/restore.md` |
| 10.2 | **CONSOLE** | Confirm how far back the history window reaches. Neon defaults to **6 hours free, 1 day paid**; that is the real recoverable window and nobody notices a bad settlement within six hours |
| 10.3 🔴 | **CONSOLE** | **Perform a restore into a scratch database and verify the data.** The one most often skipped and most often regretted |
| 10.4 | **CONSOLE** | Time it against the 1-hour RTO |
| 10.5 | **CONSOLE** | Follow `docs/runbooks/restore.md` exactly as written, and correct it where it was wrong |

---

## Findings

### 1 · The financial-year boundary was never crossed (row 5.6) — a gap in the tests, not a bug

`invoice.sequence` is gapless per financial year and India's runs April to March. Every existing
test settles bills inside one year. Nothing asserted that a bill dated 1 April starts at sequence 1
rather than continuing March's run — which is the only way the rule can actually be wrong.

`tests/test_financial_year_boundary.py` settles the pair, and a third case at 01:30 on 1 April —
business day 31 March, calendar date 1 April, and the new year's series. **It passes against the
existing code**, which is the honest result: the product was right and nobody had checked. Written
down as a finding anyway, because "we believe this works" and "a test asserts this works" are
different claims and only the second one survives the next refactor.

### 2 · `docs/security.md` promises three headers the product does not send (rows 7.2, 7.3)

> `docs/security.md:62` — *"TLS 1.2+ everywhere, HSTS, no mixed content."*
> `docs/security.md:91` — *"Strict CORS allow-list. CSP with no `unsafe-inline`.
> `X-Frame-Options: DENY`."*

The CORS allow-list is real. **The other three are not implemented anywhere.** `app/main.py` adds
`CORSMiddleware` and `RequestContextMiddleware` and nothing else; there is no reverse proxy in the
picture, because ADR 0005 serves the SPA from the API itself (`app/core/spa.py`) — so these headers
are this application's responsibility and nobody else's.

The consequence is concrete rather than theoretical: the staff application can be framed, which is
a clickjacking surface on a product whose buttons void bills and reset passwords.

Fixed in M16 chunk A: `app/core/security_headers.py`, and `tests/test_security_headers.py`
**reads `docs/security.md` and asserts the headers it names are sent** — so if somebody removes the
middleware, the document keeps promising and the test fails, which is the correct direction for
that disagreement to be discovered in.

### 3 · The rate limiter is in-process, and two containers double the budget

Not a new finding — `app/core/rate_limit.py` documents it, and `docs/backlog.md` carries the fix
and its trigger. Repeated here because a security checklist is where somebody looks for it, and a
limitation written only in a docstring is a limitation nobody reads at the moment they need it.

### 4 · MFA does not exist (row 2.8)

Recorded as N/A above rather than skipped. The product goes to a pilot restaurant without it, and
that is a decision the owner should make knowingly.

---

## Sign-off

- **Date:** 2026-09-19 · **Run by:** autonomous session (M16 chunk A)
- 🔴 items: 1.2, 2.5, 4.1, 5.1, 5.6, 7.1, 9.4 **pass**. 7.2 and 7.3 **failed and are fixed in this
  module**; 5.6 passed once somebody actually crossed the boundary. 7.5 (gitleaks), 8.1 (production logs) and **all of §10** require a console session and
  are **not ticked**.
- **Do not deploy until §10 is run**, and 10.3 in particular. An untested backup is not a backup.
