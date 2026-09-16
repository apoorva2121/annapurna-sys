# Backlog issues — build log

**Rule, set by the owner on 2026-09-13:** every backlog *issue* is cleared before the next module
starts. Ideas stay in `docs/backlog.md` and are not part of this run.

**Scope, approved 2026-09-13 ("all five groups"):** the rows below, identified by title (row numbers
are the order of `docs/backlog.md`'s table on 2026-09-13 and will drift as rows close).

**How each fix is made** (CLAUDE.md, `docs/sdlc.md` step 10, `docs/engineering-guardrails.md`):
regression test first, its failing output pasted into the commit body; then the fix; then
`make check` with the exit code read directly; docs changed in the same commit; the backlog row
struck through with **CLOSED date (chunk)**; guardrail ids in commits touching auth, sessions, money
or stock. One chunk, one or more commits, clean tree at the end.

**Branch:** `fix/backlog-issues`, from `feat/m01-identity` at `a62fe6b` plus the plan commit.

**Resuming:** read this file's state table, then `git log --oneline -15`. Work the first chunk that
is not done. Stop at any row marked **DECIDE** that has no recorded answer.

---

## State

| Chunk | Rows (by title) | State | Commits |
|---|---|---|---|
| B0 | Plan approved; baseline `make check` green | ☑ **done** 2026-09-13 — `make check: clean`, exit 0 read directly; 988 backend and 250 frontend tests passed. Only warnings: market-rate freshness notes (informational) and the moderate vitest advisory (row "vitest 3 → 5", B10) | `2cdc974` |
| B1 | Validation errors say only "The request was not valid" · API does not uppercase a GSTIN | ☑ **done** 2026-09-13 — `make check` exit 0 read directly. The first full run found one old test treating a lowercase GSTIN as malformed; corrected to an HTTP test that it is stored in capitals | `3869aa3` |
| B2 | After a bill a table cannot be cleared · no screen asks for the bill or cancels an unsettled order | ☑ **done** 2026-09-13 — `make check` exit 0 read directly. Design choices stated to the owner: Mark ready behind `order.create`; busy mode behind a new `floor.manage` (owner, manager), off at the next business day | `fff7a1b` |
| B3 | `IntegrityError` unmapped → 500 · area deactivation races table creation · reordering two requests, not atomic · `MeResponse.restaurants` unbounded | ☑ **done** 2026-09-14 — `make check` exit 0 read directly; 1052 backend tests (coverage 97.01%) and 262 frontend tests passed. The run looked stalled at 41% and was not: the full backend suite took 24 minutes. The same commit carries the owner's `design-md/` review (UI skill, design system, strategy §1.6, two backlog ideas), because it shares `docs/backlog.md` | — |
| BW | Whoever opens an order is credited as its waiter; the waiter is shown nowhere and cannot change *(owner request 2026-09-14, built before B4 by decision D10)* | ☑ **done** 2026-09-14 — see the commit for the gate result | — |
| B4 | **Remediation R6** — global identifier uniqueness (**DECIDE D1**) · two stale tabs sign each other out · refresh-rotation grace window · `switch_restaurant` fabricates a session id · identifier normalisation | ☑ **done** 2026-09-14 — two commits: B4a (logins stored one way, unique per organization, the sign-in choice) and B4b (`sid` on the access token, the cross-tab refresh lock, R6 closed). **Accepted and recorded:** a login held in two organizations answers a little slower, one password check per account; wrong passwords across several accounts are counted from B5 (D1d) | see git log |
| B5 | **Remediation R5a** — lockout reveals whether an identifier exists (per-IP budget and progressive delay; G-15) | ☑ **done** 2026-09-14 — no automatic lock; a delay per login (hash of the login, 1s doubling to 30s from the third wrong password), 30 failures per network in ten minutes, a lock only by a person and checked after the password (D28). `login_attempt` rows are swept with idempotency keys in B10 | see git log |
| B6 | Server-owned form state never reconciled · `parseAmount` not used by the tax screen · invoice screen does not show credited amounts · reset another employee's password from the UI | ☑ **done** 2026-09-14 — settings re-seed from the save and carry `settings_version` (a stale save is a 409); `percentToFraction` on the tax screen; credited quantity and amount per dish on the invoice; a Set a new password section on the employee page | see git log |
| B7 | No screen for discounts, comps or service charges (**DECIDE D2**) · cash taken while no till is open (**DECIDE D3**) | ☑ **done** 2026-09-14 — discounts, comps and the service charge on the bill screen (D2); `GET /cash/outside-till` and its line on the till screen (D3) | see git log |
| B8 | `food_type` not in `app/core/enums.py` · allergen declaration not modelled · FSSAI licence has no expiry · calorie and serving-size fields | ☑ **done** 2026-09-14 — `FoodType` enum; allergen statement (text, no unverified list), calories and serving size; licence expiry with warnings. Calorie applicability flag and registry status to M18 | see git log |
| B9 | Seed `PALAK_PANEER` has no spinach · menu seeder query per dish · receiving reads each stock item twice | ☑ **done** 2026-09-16 — spinach in Palak Paneer, so the weighted menu food cost moves 25.6% → 25.7% and every live citation moves with it (the dated S15 measurements are left as history); the library's calibrated tier re-pasted and `PROVENANCE.md` regenerated; one link read per seeding rule; one stock item read per delivered line | see git log |
| B10 | vitest 3 → 5 · ruff `DTZ` · `date_trunc` audit · `audit_docs.py` eliminated tables · shared business-day vectors · new-screen reachability test · migration 0005 reads the live catalogue · expired idempotency keys never swept | ☐ | — |
| B11 | Waiter screens not fully optimistic · `/design` gallery (**DECIDE D4**) | ☐ | — |
| B12 | The owner's defect sheet (`issues .xlsx`, 2026-09-14): error codes on screen (issue catalogue) · address cannot be saved · tables cannot be deactivated · add-employee form · stock expiry and ungated pages · options screen editable by a waiter · receiver not shown · permission codes on the profile · till closer and adjuster. all sheet questions answered 2026-09-14 (D18–D27), plus three found in the owner's screenshot: impossible dish costs (investigate first), the Dish costs table layout, and a recipe that loses its confirmation when opened from Dish costs | ☐ | — |
| — | **Next module may start** | ☐ | — |

---

## Chunks

### B1 · Errors people can act on

- **Tests first:** posting a supplier with a lowercase GSTIN is accepted and stored uppercase; a
  422 envelope carries a per-field code and a plain-language message for every rule on the supplier,
  menu-category and station forms; a frontend test renders the field message under the field and a
  summary line instead of `request.invalid`; a backend test fails when a request schema field with a
  constraint has no plain-language message.
- **Fix:** plain-language rule text beside each constraint; `_validation_error` maps pydantic error
  types to stable codes (`field.pattern`, `field.too_long`, …); `errorProps` passes field messages to
  `Field`'s existing `error` slot across the 24 screens; GSTIN uppercased at the boundary everywhere
  it is accepted.

### B2 · A table's life after the bill (owner decisions recorded in the backlog row)

- **Tests first:** tapping a table being cleared does not open an order; Mark ready sets it free;
  a cleaning table past the restaurant's cleaning time is reported free by `GET /floor` and can be
  seated; inside a busy window, or with Busy mode on, settlement leaves the table free; cancelling an
  empty order frees its table; the cancel dialog requires a reason and shows dishes already sent.
- **Schema:** `restaurant_table.cleaning_since timestamptz NULL`; restaurant settings
  `table_cleaning_minutes` (default 5, NULL = manual only), busy windows in restaurant local time, and
  a manual busy-mode flag. The schema review checklist (G-13) is answered in
  `docs/modules/M07-orders-spec.md` before the migration.
- **Rule:** "free after N minutes" is derived at read time from `cleaning_since`; no background job.
- **Also:** Ask for the bill and Cancel order buttons on the order screen (the M07 row). Served stays
  with M08, where the dish is handed over.

### B3 · Races and 500s

- **Tests first:** two concurrent creates of the same dining-area name → one 201, one 409 (never 500);
  concurrent deactivate-area and add-table → no active table in an inactive area; reorder is one
  atomic request; `/auth/me` returns at most 20 restaurants and a cursor endpoint lists the rest.
- **Fix:** `IntegrityError` handler (23505 → 409, 23514 → 422, constraint name logged only);
  `DiningAreaRepository.get_for_update`; `POST /setup/dining-areas/reorder`; the capped list.

### B4 · Remediation R6 — identifiers and sessions

Follows `docs/audit/remediation-plan.md` §R6 as written, including its tests. **DECIDE D1** answers
its open question. On completion R6 is ticked there and G-18, G-19 move to enforced, which
`scripts/audit_guardrails.py` verifies.

### B5 · Remediation R5a — lockout without an enumeration oracle

Only the lockout half of §R5, per the scope cut in `docs/audit/external-review.md` §5: progressive
delay per identifier, per-IP budget, a hard lock only by a human; the same response for a known and
an unknown identifier. Plan and status enforcement stay in R5b, still deferred to a public URL.

### B6 · Screens that lie or are missing

- Settings forms re-seed from the PATCH response, then `restaurant.version` with a conditional PATCH
  so a concurrent edit is a visible 409.
- The tax screen parses the percentage with the string-only parser, never a float.
- The invoice response carries credited-so-far per line; the screen shows it.
- An owner or manager resets another employee's password from the employee page, behind the existing
  seniority guard (G-4, G-5).

### B7 · Comps, discounts, cash outside a till

Designed after **DECIDE D2** and **DECIDE D3** are answered. Comps are the insider-abuse control
(`docs/seed-data.md` signal 11), so the threat question is answered in writing before code.

### B8 · Compliance gaps in force

- `food_type` consolidated into `app/core/enums.py` and `shared/enums.ts`; behaviour unchanged.
- **Allergens:** the list of allergens and the display rule are taken from the FSS (Labelling and
  Display) Regulations, 2020 **as looked up and cited**, never from memory (`compliance-rules.md`
  rule 1). Empty means declared none; NULL means never asked.
- FSSAI licence expiry date and a warning where the bill is issued.
- Calorie and serving size, gated by a derived per-restaurant flag, never a global setting (§B1).

### B9 · Seed data and slow paths

Adding spinach to `PALAK_PANEER` moves golden figures cited in `docs/seed-data.md`,
`docs/modules.md` and `docs/plan/month-1.md`; `scripts/audit_docs.py` checks those numbers, so every
citation changes in the same commit and the library is regenerated from the seed.

### B10 · Tooling and guards

Each is small and independent. The idempotency sweep ships as a command
(`python -m app.jobs.sweep_idempotency`) runnable now and scheduled when R7 deploys. Migration 0005
is corrected by inlining its rows; no staging database exists yet, so CLAUDE.md's rule against editing
applied migrations is not engaged — recorded here because it is exactly the kind of exception that
must be written down.

### B11 · Waiter speed and the gallery

"Adding…" lines with no client-side price until the server prices them (invariant 3). Gallery per
**DECIDE D4**.

---

## Decisions

| Id | Question | Answer | Date |
|---|---|---|---|
| D1 | Identifier uniqueness: a global unique index now, or a per-organization login surface now | **Organisation picker on login now.** Identifiers go back to being unique per organization; no global index. Per §R6, the concurrent cross-organization create test is dropped because the ambiguity no longer exists, and the backlog rows "one person who works for two restaurant groups" and "global identifier uniqueness enforced by code" close with this chunk | 2026-09-13 |
| D2 | Comps: who may comp, how the reason is chosen, second approval above an amount | **Roles holding `order.discount` only (managers and above); reason chosen from a preset list with an optional note; no second approval.** The monthly comps-by-authoriser report is the check | 2026-09-13 |
| D3 | Cash taken with no till open | **Allowed, and shown on the cash-up screen** as "cash taken today outside any till" | 2026-09-13 |
| D4 | `/design` gallery: build now without screenshot tests, or at M08 | **Build now, with screenshot tests** — a pinned headless browser in CI for visual regression | 2026-09-13 |
| D1a | How D1's organisation choice appears on the sign-in screen | **Phone (or email) and password first; a "Which hotel?" choice only when the password is correct and the identifier belongs to more than one organization.** Owner first proposed the choice straight after the phone number; chose after-the-password once told that order reveals, to anyone holding a phone number, which businesses that person works at. The second step uses a single-use pass valid about 2 minutes, so the password is not resent. If the password matches only one of the accounts, sign-in goes straight in with no choice | 2026-09-14 |
| D1b | On the same device, is the last choice remembered | **Pre-selected, still shown** — one tap on Continue | 2026-09-14 |
| D1c | Moving between two different owners' organizations | **Sign out and sign in again.** A session never spans two organizations. Branches of one organization still switch in place (`POST /auth/switch`) | 2026-09-14 |
| D1d | What a wrong password counts against when an identifier belongs to two organizations (needed by B5) | **The identifier**, once per attempt, whichever organization | 2026-09-14 |
| D6 | A refresh token presented twice inside 60 s (§R6 grace window) | **No grace: any replay revokes the family, as today.** Owner chose this over a logged 60 s allowance, accepting that a network retry signs a person out everywhere. The cross-tab lock in `shared/api.ts` is still built, so two tabs on one device do not collide. §R6's grace-window test is replaced by one asserting the replay still revokes; `replaced_by_session_id` is not added; the backlog row "Refresh-rotation grace window" closes as declined by the owner, and G-19 is amended to say so | 2026-09-14 |
| D7 | Auto-assigning incoming orders to a waiter | **Wait for shifts (M12).** Only a roster knows who is on the floor; a round-robin or a manager's daily list now would be a small M12 built early | 2026-09-14 |
| D8 | Who may take over an order somebody is serving | **A manager (`order.assign`), with a reason.** A waiter claims only an unserved order: grabbing a busy table would take its credit | 2026-09-14 |
| D9 | Who is the waiter when someone other than a waiter opens an order | **Chosen at opening.** A waiter opening a table serves it; `order.assign` holders name the waiter or leave it unassigned; takeaway and delivery are counter orders | 2026-09-14 |
| D10 | When to build it | **Next, before B4.** It fixes a real defect and depends on nothing unbuilt | 2026-09-14 |
| D11 | Error codes on screen | **Never in the UI.** Each issue gets a number and a plain-language text; the list is a checked-in catalogue copied to a database table by migration, and a test fails the build when a raised code has none | 2026-09-14 |
| D12 | What a person sees on an error | **The text and the issue number** ("… (Issue 1042)"). A form mistake shows only its sentence under the field | 2026-09-14 |
| D13 | A till adjustment | **Both people recorded and shown** — who closed the till and who adjusted it, by name, employee code and role — for later audit | 2026-09-14 |
| D14 | Adding an employee | **A Finish button after roles** returns to the staff list with "Ravi Sharma added as Waiter"; editing someone later shows Back to staff | 2026-09-14 |
| D15 | An employee's name | **At least two letters**; digits and dots allowed | 2026-09-14 |
| D16 | May the person who closed a till adjust it | **The owner may**, marked "adjusted by the same person" on the till and in reports; everyone else needs a second person | 2026-09-14 |
| D17 | Staff without a login seeing their tasks | **Handled with the M11/M17 backlog row** "Staff without a login cannot see their own performance score" | 2026-09-14 |
| D18 | Till adjustment amount | **Two choices: Cash found (extra) / Cash missing** instead of a signed amount | 2026-09-14 |
| D19 | Employee code | **Filled in with the next free code, editable**; never a duplicate within one organization (the existing unique constraint) | 2026-09-14 |
| D20 | Forgotten password at sign-in | **A "Forgot password? Ask your manager" link now**; the manager's reset from the staff screen is already planned in B6 | 2026-09-14 |
| D21 | Add-employee help text | **Rewritten crisp and professional, shown to the owner before and after** | 2026-09-14 |
| D22 | "Fantastic theme files" | **The brand design upgrade already planned after the backlog** (warm modern Indian casual dining) | 2026-09-14 |
| D23 | Appearance in Profile and in Settings | **Keep both, with clearer labels**: Profile is this device only; Settings is the restaurant's default | 2026-09-14 |
| D24 | Stock screens | **A usage history per item** (sold, wasted, counted) beside deliveries; **What uses this** as a collapsible panel; **expiry shown in the item's own row** | 2026-09-14 |
| D25 | Bill-wait alarms | **Planned with M13's dashboards**: 3 minutes to the manager (and, as asked, the accountant — to be confirmed when M13 is specified), 7 minutes to the owner | 2026-09-14 |
| D26 | Attendance-based task allocation | **Later, with M11 (tasks) and M12 (shifts)**: owner to manager and accountant; manager to waiters and chef | 2026-09-14 |
| D27 | Credit notes | **Always viewable and printable from the browser now**; paying with store credit becomes its own feature later, with used/closed tracking and the new bill number logged; messaging waits for M11 | 2026-09-14 |
| D28 | The lockout: the build log's redesign, or only a per-network budget (external review §5) | **The redesign**, on the owner's standing instruction to follow recommendations. A per-network budget alone leaves "account locked" as an answer only a real login gets — the enumeration hole this chunk exists to close — and leaves five guesses able to lock a waiter out. So: a growing delay per login, a budget per network, a lock only by a person. It supersedes M01 open decision 3 (auto-unlock after 15 minutes). Trusting the proxy's forwarded address waits for R7 | 2026-09-14 |
