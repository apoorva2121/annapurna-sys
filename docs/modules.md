# Modules

**18 modules.** Each is a vertical slice — schema, backend, frontend, tests, manual script — that
ends with something demonstrable on staging. None is "the backend for X" with a UI arriving later;
that pattern produces four weeks of invisible progress and then a bad week.

Per-module process and Definition of Done: `docs/sdlc.md`.
Format for each entry below:

> **Depends on** · **Tables** · **Endpoints** · **Screens** · **Rules that are easy to get wrong** ·
> **Tests beyond the standard suites** · **Est.**

The four generic suites (tenant isolation, permission matrix, persona separation, route declaration)
run against every module automatically and are not repeated per entry
(`docs/testing-strategy.md`).

---

## M00 · Foundation

No features. Everything else stands on it, so it is worth a full day.

- **Depends on** — nothing
- **Delivers** — repo layout, Docker Compose (api + db + web), Makefile, `uv`/npm setup, ruff +
  mypy + eslint + prettier + tsc configs, pre-commit hooks, pytest + vitest harness with
  testcontainers-Postgres, GitHub Actions CI, Alembic wired, `Settings` model that fails boot on bad
  config, structured JSON logging with `request_id` + PII redaction, the standard error envelope,
  `/health` `/ready` `/version`, Sentry, staging deploy pipeline
- **Rules** — `DEBUG=true` outside local must fail startup. The redaction filter is installed at the
  handler, so it cannot be bypassed. CI runs migration up→down→up against real Postgres.
- **Tests** — a log line containing a phone number comes out redacted; boot fails on missing config;
  the error envelope shape is asserted
- **Manual** — `M00`: staging URL loads, `/version` shows the right commit
- **Est.** 1 day

## M01 · Identity, Roles & Permissions

- **Depends on** — M00
- **Tables** — organization, restaurant, user_account, user_session, employee, role, permission,
  role_permission, employee_role_assignment, sign_in_choice (added by backlog-issues B4),
  login_attempt (B5)
- **Endpoints** — `POST /auth/login`, `/auth/login/choose`, `/auth/refresh`, `/auth/logout`, `/auth/password`;
  CRUD `/employees`; `GET /roles`, `/permissions`; `POST /employees/{id}/roles`
- **Screens** — login, staff list, employee create/edit, role assignment, own profile
- **Rules** — argon2id; refresh tokens stored hashed; identical error for unknown-email and
  wrong-password (no enumeration); deactivating an employee **revokes every session immediately**;
  permission catalogue seeded by migration; `require_permission()` never a role-name comparison
  (ADR 0007)
- **Tests** — lockout after 5 attempts; session revocation on deactivate, on password change, on role
  change; a route with no declared permission fails the build
- **Manual** — `docs/manual-tests/M01-identity.md` (already written)
- **Est.** 3 days

## M02 · Restaurant Setup

- **Depends on** — M01
- **Tables** — dining_area, restaurant_table, station, tax_group, tax_rate (`tax_rate` split
  out of `tax_group` by M03 chunk A, migration 0008 — see `docs/modules/M03-menu-spec.md` decision 1)
- **Endpoints** — CRUD for each; `PATCH /restaurant` (timezone, currency, business_day_start, GSTIN)
- **Screens** — restaurant settings, dining areas + tables (drag to reorder), stations, tax groups
- **Rules** — `business_day_start` defaults to 05:00 and is explained in the UI, because it is the
  setting owners misunderstand most (ADR 0004); tax groups are effective-dated, never edited in place
- **Tests** — business-date computation across the 05:00 boundary, including a 01:30 order landing on
  the previous business day
- **Est.** 2 days

## M03 · Menu

- **Depends on** — M02
- **Tables** — menu_category, menu_item, menu_item_variant, modifier_group, modifier,
  menu_item_modifier_group
- **Endpoints** — CRUD for categories/items/variants/modifiers; `GET /menu` (full tree, cached)
- **Screens** — menu manager (category → item → variant tree), variant pricing, modifier groups
- **Rules** — **price lives on the variant, never the item**; `food_type` is required (FSSAI);
  station routing set per item; deactivate, never delete — historical order lines point here forever
- **Tests** — `GET /menu` in a bounded query count regardless of menu size (the N+1 trap for a
  three-level tree)
- **Est.** 3 days

## M04 · Stock Items & Recipes

The heart of the product. Everything commercially interesting depends on this being right.

- **Depends on** — M03
- **Tables** — stock_item, ingredient_profile, preparation_profile, recipe, recipe_line
- **Endpoints** — CRUD stock items; CRUD recipes with nesting; `GET /stock-items/{id}/used-by`;
  `POST /recipes/{id}/version`; `GET /menu-items/{id}/cost`
- **Screens** — ingredient master, preparation master, recipe editor (nesting made visually obvious),
  dish cost breakdown, "what uses this ingredient?"
- **Rules** — recipes nest to depth 3, enforced in the service **and** at save time (ADR 0006);
  changing a recipe creates a **new version**, never an edit; cost rollup is recursive and memoised
  per request; `yield_factor` applies to raw ingredients, not preparations
- **Tests** — **golden tests against `seed/validate.py` figures** (Butter Chicken Full = ₹126.70,
  makhani gravy = ₹0.1489/ml); cycle detection; depth-4 rejected; a recipe edit does not move any
  historical order's cost
- **Manual** — build a recipe by hand, confirm the cost matches a calculator
- **Est.** 4 days

## M05 · Inventory Ledger

- **Depends on** — M04
- **Tables** — stock_batch, stock_movement, stock_count, stock_count_line
- **Endpoints** — `POST /stock/receipts`, `/stock/production`, `/stock/adjustments`;
  `GET /stock/on-hand`, `/stock/expiring`; stock count create/submit/approve
- **Screens** — stock on hand, receive stock, produce a preparation batch, physical count entry,
  expiry and low-stock alerts
- **Rules** — **append-only ledger; on-hand is derived, never stored** (invariant 2); FEFO selects by
  `expiry_date` in SQL with `FOR UPDATE` (ADR 0010); `basis` is `theoretical` or `actual` and the two
  are never summed together (invariant 7); production writes consumption of inputs **and** production
  of output in one transaction
- **Tests** — concurrent consumption of one batch does not oversell; FEFO picks the right batch;
  on-hand equals the movement sum after 1,000 random operations (property-based)
- **Est.** 4 days

## M06 · Procurement `[1.5]`

- **Depends on** — M05
- **Tables** — supplier, purchase_order, purchase_order_line, goods_receipt, goods_receipt_line
- **Endpoints** — CRUD supplier and PO; `POST /purchase-orders/{id}/receive`;
  `GET /suppliers/{id}/variance`
- **Screens** — supplier list, PO create, **goods receipt with weighing** (the money screen),
  supplier variance report
- **Rules** — ordered / invoiced / received are **three separate numbers**, never collapsed
  (`docs/waste-model.md` §1); receipt creates stock batches with cost frozen; partial delivery leaves
  the PO partially open
- **Tests** — three-way variance arithmetic; a receipt without a PO (ad-hoc market purchase) still
  creates batches
- **Manual** — `docs/manual-tests/M06-procurement.md`. Its section C is the one that matters: the
  two inputs are labelled *"What the bill says"* and *"What the scale says"*, and whether a real
  store manager fills them with two different numbers is what decides if this module is worth
  anything
- **Est.** 3 days

## M07 · Orders / POS

Largest module. Split the PR.

- **Depends on** — M03, M05
- **Tables** — order, order_table, order_line, order_line_modifier, order_discount, order_charge,
  invoice, credit_note, credit_note_line, payment, idempotency_key, **cash_session, cash_count,
  cash_movement** (the till cash-up — see *Cash reconciliation* below). Designed in
  `docs/modules/M07-orders-spec.md`, built by migration 0019
- **Endpoints** — order create/get/list and `GET /floor`; line add/update/remove;
  `POST /orders/{id}/send`, `/served`, `/bill`, `/cancel`, `/split`, `/discounts`, `/charges`,
  `/settle` (payments travel inside it); `POST /invoices/{id}/cancel` and `/credit-notes`;
  `/cash/sessions` with close, payouts and adjustments; `/cash/outside-till` (decision D3)
- **Screens** — table map, order taking (waiter PWA, thumb-reachable), bill view, split bill,
  payment, void/refund
- **Rules** — **the server recomputes every price, tax and total; the client sends only what was
  ordered** (`docs/security.md` A04); GST stored per line as CGST/SGST at order time; `Idempotency-Key`
  required on settle and payment; `order.version` optimistic lock (ADR 0010); settled orders are
  immutable — void/refund are new rows; **invoice numbers are sequential per financial year with no
  gaps**, so a cancellation keeps its number (GST law); settlement posts theoretical consumption and
  freezes `theoretical_food_cost`
- **Tests** — double-submit with the same idempotency key charges once; concurrent settle → 409;
  tax arithmetic property-based (splits sum to total for any price × rate); a tampered client price
  is ignored; settle writes stock movements and an audit row atomically or not at all
- **Cash reconciliation** — `cash_session` opens with a declared float and closes with a counted
  amount; `cash_count` holds the denomination breakdown. **Expected cash is derived, never stored**:
  it is the sum of `payment` rows with method `cash` posted to the session (a refund is negative, and
  posts to the session in which it happens), plus the opening float, minus `cash_movement` payouts. The **variance is recorded, never corrected away** — this
  is invariant 7 pointed at the till rather than the stockroom, and the variance is the whole point.
  A closed session is immutable; a correction is a new `cash_movement` of type `adjustment`, with a reason and an
  `audit_log` entry. `shift_id` is nullable so M07 does not wait on M12.

  *Why this is here and not in Shifts:* expected cash comes from `payment` rows, so it belongs with
  the module that owns payment. Rationale in `docs/plan/analytics-harvest.md`.
- **Manual** — `docs/manual-tests/M07-orders.md`: split bills, a comp, a credit note with a refund,
  a deliberate short till, and rupee figures to check by hand
- **Est.** 7 days *(6 + 1 for the cash-up)*

## M08 · Kitchen / KOT

- **Depends on** — M07
- **Tables** — kot_ticket, kot_ticket_line
- **Endpoints** — `GET /kot/tickets` (by station), `PATCH /kot/tickets/{id}/status`,
  `GET /kot/stream` (SSE)
- **Screens** — KDS per station, ticket detail, remake request
- **Rules** — read at **two metres**: ≥20px base, ≥40px order numbers, no modals, no scrolling, colour
  never the only signal (`docs/ui/conventions.md`); all five timestamps captured; elapsed time always
  visible and counting; SSE reconnects with backoff and recovers missed tickets on reconnect
- **Tests** — ticket list under the **50 ms** budget with 200 open tickets; SSE delivers within 1 s;
  reconnect after a network drop loses nothing
- **Manual** — stand two metres from the screen and read it. Wear one glove.
- **Est.** 4 days

## M09 · Waste

- **Depends on** — M05
- **Tables** — wastage_reason, wastage_event
- **Endpoints** — CRUD reasons; `POST /wastage`; `GET /wastage/summary`
- **Screens** — **log waste in under 10 seconds** (item → preset quantity buttons → reason → photo →
  done), waste summary by stage/reason/shift
- **Rules** — every wastage_event writes a paired `stock_movement` in the same transaction, never one
  without the other; cost is computed, **never asked of the person logging**; rupee value shown
  *after* logging, never before (showing it first suppresses honest reporting —
  `docs/waste-model.md`); `staff_meal` and `complimentary` are separate types, not waste
- **Tests** — event and movement are atomic; cost matches the batch cost at that moment
- **Manual** — time yourself logging waste on a phone. Over 10 seconds is a fail.
- **Est.** 2 days

## M10 · Customers, Feedback & Guest App

First module with a guest surface — ADR 0009 applies in full.

- **Depends on** — M07
- **Tables** — customer, customer_preference, feedback, feedback_line, complaint
- **Endpoints** — staff: CRUD customer, `GET /customers/{id}/history`, complaint workflow, DPDP
  export + erasure. Guest: `GET /guest/menu`, `POST /guest/feedback`, `GET /guest/order/{token}`
- **Screens** — customer profile with preferences, complaint tracking; **guest PWA**: QR → menu →
  three-question feedback
- **Rules** — separate route tree, separate token type, separate response schemas (ADR 0009); table
  tokens short-lived and rotating; guest responses expose **no** cost, margin, recipe or employee
  name; phone-number consent is explicit and never pre-ticked (DPDP); erasure anonymises the customer
  and **keeps the order** — financial records must be retained; allergy preferences surface to the
  kitchen
- **Tests** — no guest token reaches any staff route; a guest response schema containing a cost field
  fails the build; erasure leaves revenue totals unchanged
- **Manual** — scan a real QR on a real phone; try staff URLs from the guest session
- **Est.** 4 days

## M11 · Communication & Tasks

- **Depends on** — M01
- **Tables** — conversation, conversation_participant, message, task, task_event, attachment
- **Endpoints** — conversation CRUD, `POST /messages`, `PATCH /conversations/{id}/read`,
  task CRUD + status transitions, attachment upload (presigned)
- **Screens** — conversation list, thread, promote-message-to-task, task board, task detail
- **Rules** — unread is a **watermark** (`last_read_message_id`), not per-message receipts
  (`docs/schema.md` "eliminated"); attachments validated by content type and size, stored with a
  generated key, served from a separate origin; a message promoted to a task keeps
  `source_message_id`
- **Tests** — unread counts correct in a group thread; upload rejects a disguised executable
- **Est.** 4 days

## M12 · Shifts

- **Depends on** — M01
- **Tables** — shift, shift_assignment
- **Endpoints** — shift CRUD, assignment CRUD, clock in/out
- **Screens** — shift roster, clock in/out
- **Rules** — deliberately minimal; leave, overtime and swaps are Phase 2. Exists mainly so waste and
  performance can attribute to a shift.
- **Planned here** *(owner decision 2026-09-14)* — auto-assigning an incoming order to the waiter
  whose section its table is in this shift. Waiting on this module because only a roster knows who
  is on the floor; claiming and moving orders already exist (M07 acceptance criterion 20).
- **Est.** 2 days

## M13 · Dashboards & Reports

Where the product finally shows its face.

- **Depends on** — M07, M05, M09
- **Tables** — none new (views only — these are **queries, not tables**, per `docs/schema.md`)
- **Endpoints** — `GET /dashboard/today`, `/reports/food-cost-variance`, `/reports/dish-performance`,
  `/reports/waste`, `/reports/sales`; CSV export
- **Screens** — manager today view, **theoretical vs actual food cost variance**, dish performance
  (the menu-engineering quadrant), waste breakdown by stage, owner summary
- **Rules** — every metric shows a comparison (vs yesterday / last week) — a number with no baseline
  is not information; every metric drills through to the rows behind it; aggregations bounded by
  `business_date` on an index-backed path; dashboard p95 under 800 ms
- **Tests** — **the acceptance query from `docs/domain-model.md`** returns correct figures on seeded
  data; all 14 planted signals from `docs/seed-data.md` are actually surfaced
- **Manual** — the most valuable script of the project: do the numbers mean anything to a restaurateur?
- **Est.** 5 days

## M14 · Audit & Notifications

- **Depends on** — M01
- **Tables** — audit_log, notification
- **Endpoints** — `GET /audit` (filter by entity, actor, date), `GET /notifications`, mark read
- **Screens** — audit trail viewer, notification centre
- **Rules** — audit written by a **service-layer decorator**, not by hand at each call site — hand-
  written audit calls get forgotten exactly where they matter; severity maps to the UI colour tokens;
  escalation tiers per vision doc §25 so notifications do not become noise
- **Tests** — a price change, a recipe edit, a void and a stock adjustment each produce an audit row
  with correct before/after
- **Est.** 3 days

## M15 · Seed Generator & Demo

- **Depends on** — M04, M05, M07, M08, M09, M10
- **Delivers** — loader for `seed/*.yaml`; generator for 120 days of orders, KOTs, movements, waste,
  feedback; all **14 planted signals**; `make seed` / `make seed-small`
- **Rules** — deterministic (fixed seed); seeded orgs carry `is_demo=true` and are excluded from
  reporting; plausible-not-perfect (include a skipped waste log, two voided orders, missing feedback);
  batched inserts of 1,000
- **Tests** — same seed produces identical figures; blended food cost lands at the documented ~25.6%
  theoretical / ~32% actual
- **Est.** 3 days

## M17 · Workload Fairness & Recognition

The feature that answers "who is actually carrying the load, and how do I reward them fairly?"
Design and its risks: `docs/workload-fairness.md`. Decisions: ADR 0011.

- **Depends on** — M07, M12, M13
- **Tables** — incentive_scheme, performance_period, performance_score, performance_note,
  recognition_award (plus `shift_assignment.dining_area_id`)
- **Endpoints** — `GET /performance/me` (every role, always); `GET /performance/team`;
  `GET /performance/distribution` (the fairness view); scheme CRUD;
  `POST /performance/periods/{id}/publish`; note CRUD; `POST /recognition/awards`
- **Screens** — **workload distribution** (the primary screen — who handled what share, with section
  context), my performance (every employee), team performance (manager), scheme configuration
  (owner), award grant, recognition board
- **Rules** — live metrics are **queries**; publishing **freezes** them into `performance_score` and
  they are never recomputed (ADR 0011); only `controllable` metrics carry weight, `context` metrics
  carry zero; every metric normalised per hour worked or per cover; **volume weight ≤ accuracy +
  rating weight**, enforced on save; assists are **derived** from order vs assigned section, never
  logged; `performance.view.own` granted to every role and not removable; **no endpoint returns a
  bottom-ranked list**; awards are granted by a human, never triggered by a score
- **Tests** — weight validator rejects a volume-heavy scheme; a published period does not move when
  an underlying order is later voided (the freeze test); assists derive correctly when a waiter
  serves outside their section; normalisation makes a 4-hour and an 8-hour shift comparable; no
  serialiser can emit a bottom ranking
- **Manual** — the important one: does the distribution screen make an unfair roster *obvious*? Show
  it to someone who has managed staff.
- **Est.** 5 days

## M18 · Compliance Risk Alarms

The feature that tells an owner **"this decision puts your licence at risk"** before it does, and
keeps the record that proves they acted. Rules and their statutory basis: `docs/compliance-rules.md`.

Indian restaurants are shut down for paperwork far more often than for bad food, and the owner is
usually the last to know a licence lapsed. The product already holds every fact needed to see it
coming — licence dates, turnover, food types, tax rates, GSTIN. This module is the difference
between holding those facts and *acting* on them.

- **Depends on** — M02 (restaurant identity), M03 (menu), M14 (notifications). Richer once M07
  (turnover from real sales) and M10 (DPDP consent) exist.
- **Tables** — *indicative, pending the spec; deliberately not yet in `docs/schema.md`, because a
  table listed there is a designed table and these are not designed yet* — `compliance_rule` (the
  catalogue, seeded not user-authored), `compliance_finding` (open/resolved, per restaurant, with
  the evidence that raised it), `compliance_event` (append-only: raised, acknowledged, resolved,
  suppressed — and by whom)
- **Endpoints** — `GET /compliance/findings` (open, by severity); `GET /compliance/history`;
  `POST /compliance/findings/{id}/acknowledge`; `GET /compliance/export` (the inspection pack)
- **Screens** — a compliance card on the owner home that is **silent when nothing is wrong**; a
  findings list with what to do about each; an exportable record for an inspection
- **Rules**
  - **Four states, never conflated** — `in_force` · `notified_not_in_force` · `unsettled` ·
    `unverified`. **Only `in_force` may raise a blocking alarm.** A rule commencing in 2027 may
    inform, never block, and must say so in words.
  - **Every rule cites its instrument** — name, number, commencement date, and the date the
    citation was last checked. A rule with no check date is a rumour and does not ship.
  - **Severity is legal exposure, not annoyance** — `critical` (operating illegally right now),
    `warning` (will become so on a known date), `advisory` (good practice, no statutory basis).
  - **Never cry wolf.** A false alarm costs more than a missing one, because it teaches an owner to
    dismiss the card — the same reason the locked alert colours exist (`docs/ui/conventions.md`).
    A rule that cannot state its evidence does not fire.
  - **Explain and instruct.** A finding names what is wrong, what it risks, and the next action. It
    never renders a bare statute reference at a person who did not ask for one.
  - **The record is the product.** `compliance_event` is append-only; acknowledging is an event, not
    a status flip. The export is what an owner hands an inspector, so it must reconstruct *what was
    known when*, not merely what is true now.
  - **Suppression is allowed and logged.** An owner may dismiss a finding with a reason; that is a
    recorded decision, not a deletion. Advice ignored is still advice given.
  - **No legal advice.** The app states the rule, the fact, and the gap. It does not opine on
    consequences or quantify penalties.
- **Rules to seed first** (each already detectable from data the product holds)
  - FSSAI licence expired, or expiring within 30 days — **it prints on every bill**
  - FSSAI licence tier below what declared turnover requires (₹1.5 Cr / ₹50 Cr bands, w.e.f. 1 Apr 2026)
  - Menu item live with no allergen declaration *(blocked on that field existing — see backlog)*
  - Calorie declaration required (Central Licence **or** ≥10 outlets) and absent
  - GSTIN absent or malformed while bills are being issued
  - A tax group in use with no rate row effective today
  - A tax rate unchanged across a known statutory change date — the GST 2.0 case, where a correct
    configuration silently became wrong on 22 Sep 2025
- **Tests** — a rule in `notified_not_in_force` cannot raise a `critical`; every seeded rule carries
  an instrument and a checked-on date; acknowledging appends rather than overwrites; the export
  reconstructs a past state; a resolved finding does not re-raise on the same evidence; the owner
  home renders **nothing** when there are no findings
- **Manual** — show the findings list to a restaurant owner who has been inspected. The question is
  not "is it accurate" but **"would you have known this without us?"**
- **Est.** 4 days

## M16 · Hardening & Production

- **Depends on** — M00–M15, M17, M18 (everything)
- **Delivers** — full security checklist pass, load test (k6), backup + **tested restore**, runbooks,
  cost alerts, production deploy, DPDP consent flows verified, GST invoice numbering verified across
  a financial-year boundary
- **Est.** 4 days

---

## Dependency order

```
M00 → M01 → M02 → M03 → M04 → M05 → M07 → M08 → M13 → M16
                    │      │      └→ M09 ──┘        ↑
                    │      └→ M06                   │
                    │                               │
                    ├→ M11  ├→ M12  ├→ M10 ─────────┤
                    └→ M14 ─────────────────────────┘
```

M11, M12 and M14 have only an M01 dependency — they are the natural fill for any week where a
critical-path module is blocked. M17 sits late because it consumes almost everything: orders, KOT
timestamps, feedback, shifts and the dashboard query layer.

**Total ≈ 67 working days** — roughly twelve and a half weeks of focused solo work, not four.
(57 before M17 Workload Fairness was added at 5 days.)

Month 1 (20 working days) covers **M00–M05 complete and M07 begun**: 1+3+2+3+4+4 = 17 days, leaving
3 for the start of Orders. See `docs/plan/month-1.md`, which derives its weeks from these estimates
rather than from optimism. Everything after that is real work that follows, and knowing it now is
better than discovering it in week four.
