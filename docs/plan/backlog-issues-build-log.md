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
| B4 | **Remediation R6** — global identifier uniqueness (**DECIDE D1**) · two stale tabs sign each other out · refresh-rotation grace window · `switch_restaurant` fabricates a session id · identifier normalisation | ☐ | — |
| B5 | **Remediation R5a** — lockout reveals whether an identifier exists (per-IP budget and progressive delay; G-15) | ☐ | — |
| B6 | Server-owned form state never reconciled · `parseAmount` not used by the tax screen · invoice screen does not show credited amounts · reset another employee's password from the UI | ☐ | — |
| B7 | No screen for discounts, comps or service charges (**DECIDE D2**) · cash taken while no till is open (**DECIDE D3**) | ☐ | — |
| B8 | `food_type` not in `app/core/enums.py` · allergen declaration not modelled · FSSAI licence has no expiry · calorie and serving-size fields | ☐ | — |
| B9 | Seed `PALAK_PANEER` has no spinach · menu seeder query per dish · receiving reads each stock item twice | ☐ | — |
| B10 | vitest 3 → 5 · ruff `DTZ` · `date_trunc` audit · `audit_docs.py` eliminated tables · shared business-day vectors · new-screen reachability test · migration 0005 reads the live catalogue · expired idempotency keys never swept | ☐ | — |
| B11 | Waiter screens not fully optimistic · `/design` gallery (**DECIDE D4**) | ☐ | — |
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
