# M02 · Restaurant Setup — Module Spec

**Status:** awaiting your approval (step 1 of the module loop, `docs/sdlc.md`)
**Estimate:** 3 days · **Depends on:** M01 (done) · **Gate:** R1, R2, R8a, R8b ticked — clear

## Scope

The floor, the kitchen stations, the tax rates and the settings that decide what a *day* means.
Four tables of master data that look like CRUD and are not, because two of them are the foundation
every later number rests on:

1. **`business_day_start`** — a restaurant closing at 2am must count that 2am against the day it
   was still serving. Every report in M13, every shift figure in M17 and the order generator in M15
   group on a `business_date` this module defines. Getting it wrong is not visible now and is
   expensive to unpick later.
2. **Effective-dated tax** — a GST rate change must not move a historical invoice. This is a legal
   requirement (`docs/decisions/0004-money-time-units.md`), not a preference, and the table has to
   make the wrong thing hard rather than rely on nobody editing a rate in place.

The rest — dining areas, tables, stations — is the physical world the waiter and kitchen surfaces
in M07 and M08 will draw. It is also the first module built on the design system, so it is where
the component library either earns its keep or does not.

## Not in scope

- **Reservations.** `restaurant_table.status` includes `reserved` with nothing able to set it. See
  open decision 3 — the honest options are a minimal reservation table or dropping the value.
- **Table merging.** One order, one table, until M07 (finding S9).
- **Printer or KDS assignment per station.** A station is a routing target; what it routes *to* is
  M08's problem.
- **Multi-branch rollups.** Out of scope for month 1 (CLAUDE.md).
- **Shifts and suppliers.** Present in `seed/operations.yaml` as P1 design; they belong to M06 and
  M17.

## Deliverables

### Migration — 4 tables (`docs/schema.md` §2)

`dining_area`, `restaurant_table`, `station`, `tax_group`, exactly as the schema doc specifies.
Plus two corrections the audit assigned to this module:

- **S13** — `restaurant.fssai_licence` becomes a real column. The M01 seed put it in
  `restaurant.settings` as a JSON key because no column existed; it prints on every bill, so it is
  not settings.
- **`restaurant.trial_ends_at`** is *not* added here — that is R5, deferred until there is a public
  URL.

`downgrade()` implemented and tested up→down→up, as always.

### The business-day helper — the part that matters

One function, one place, used by everything afterwards:

```python
def business_date_of(moment: datetime, timezone: str, day_starts_at: time) -> date
```

Converts a UTC instant to the restaurant's local time, then subtracts a day when the local time is
before `business_day_start`. `docs/decisions/0004-money-time-units.md` fixes the rule; this module
implements it and is where its tests live. **No caller may reimplement it**, and no report may group
on `date_trunc('day', created_at)`.

**M11** rides along: the frontend gets the matching helper, because
`NewEmployeeScreen.today()` currently uses the browser's UTC date and defaults "joined on" to
*yesterday* between 00:00 and 05:30 IST.

### Backend — repository → service → API

This is the first module to use `RestaurantScopedRepository`, the class M01 built and never called.
Everything here is restaurant-scoped rather than organization-scoped, and the split exists so a
reviewer can see which boundary a repository enforces from its declaration line.

```
GET    /restaurant                     the current restaurant's settings
PATCH  /restaurant                     timezone, currency, business_day_start, gstin, fssai_licence

GET    /setup/dining-areas             list, ordered by seq
POST   /setup/dining-areas             create
PATCH  /setup/dining-areas/{id}        rename, reorder, deactivate
GET    /setup/tables                   list, filterable by dining_area_id
POST   /setup/tables
PATCH  /setup/tables/{id}
GET    /setup/stations                 list, ordered by seq
POST   /setup/stations
PATCH  /setup/stations/{id}
GET    /setup/tax-groups               list, including superseded rows
POST   /setup/tax-groups               a rate *change* is a new row, never an edit
PATCH  /setup/tax-groups/{id}          name only; rate and dates are immutable once effective
```

A new permission, `restaurant.configure`, already in the P1 design (`seed/organization.yaml`) and
held by owner and admin only. Managers run a shift; they do not change what a day means or what tax
is charged.

**Deletion follows ADR 0008:** master data is deactivated, never deleted. A table that hosted an
order last year must still resolve.

### Frontend — the setup bundle

Restaurant settings · dining areas and tables (drag to reorder) · stations · tax groups.

First real use of the design system, and it needs components that do not exist yet:
`Select`, `Dialog` (or `Sheet` on phones), `Table`, `Switch`, `Label`. Vendored from shadcn and
adapted to our tokens, per `.claude/skills/restaurant-ui/SKILL.md`.

**The `business_day_start` control gets a worked example under it**, not a tooltip — ADR 0004 calls
this the setting owners misunderstand most, and a label saying "05:00" teaches nobody. It should
read like: *"Set to 05:00, an order at 1:30am on Tuesday counts towards Monday's sales."*

**Theme settings, deferred here from the UI work:** the restaurant-wide default theme and the
festive schedule, since this is the module that owns restaurant settings. The per-device picker
already exists.

## Schema review checklist (guardrail G-13)

Answered for all four tables, as the guardrails require, because these are the questions whose
answers cannot be reconstructed later.

**1. What metric will someone want from this row in M13/M17, and which timestamp does it need?**
`dining_area` is the unit of the fairness story — `shift_assignment.dining_area_id` is what makes an
"assist" derivable in M17 without anyone remembering to log helping a colleague (ADR 0011). It
needs no timestamp of its own; the assignment carries it. `restaurant_table` will be asked for turn
time, which comes from `order`, not from here.

**2. Where did this row come from?** All four are entered by a human in this module, or seeded.
No external source, no importer. `station.code` is the exception worth noting: M08 will route KOTs
by it and `seed/menu.yaml` already references `tandoor`/`main_kitchen`/`chinese`, so the codes are
a contract with existing data rather than free text.

**3. Is this row a legal document?** **`tax_group` is the closest thing to one.** It is not an
invoice, but the rate it carries is copied onto every `order_line` at order time and an invoice
cites it. Hence effective dating and immutability-once-effective rather than an editable rate.

**4. Does a modifier / option / variant change consumption?** Not applicable — no recipes here.

**5. What does a human count at close?** Not in this module. Cash close is S5, scheduled for M07.

**6. Is the derived number O(N) forever?** No derived numbers here. `business_date` is denormalised
onto `order` at insert precisely so that reporting never recomputes it.

**7. Which tier of ADR 0008 deletion, and is `restaurant_id` on the row?** All four are master data
— deactivated, never deleted — and all four carry `restaurant_id NOT NULL`.

**8. What would an insider do with this row?** See below.

## Threat question — *what would an insider do with this?*

| Attack | Control |
|---|---|
| **A manager lowers the GST rate**, pockets the difference, and the books look consistent | `restaurant.configure` is owner/admin only. A rate is never edited: a change is a new effective-dated row, so the old rate stays visible beside the new one and the change has a date and an actor in `audit_log` |
| **Someone back-dates `effective_from`** so a new rate applies to invoices already issued | `effective_from` may not be earlier than today's business date. A correction to history is a support action with a written reason, not a form field |
| A manager shifts `business_day_start` to move takings between days — hiding a bad day, or moving covers into a period a bonus is measured on | Owner/admin only, audited with before/after, and the UI states the consequence in words before saving |
| Someone renames or deactivates a table mid-service, orphaning a live order | Deactivation is refused while the table has an open order (M07 enforces the open-order side; M02 leaves the check point) |
| A waiter reads another branch's floor plan to infer its size and takings | `RestaurantScopedRepository`, and the generic tenant-isolation suite covers every new route the moment it is registered |
| GSTIN or FSSAI edited to a supplier's number, so bills carry someone else's tax identity | Owner/admin only, audited. Format-validated, not merely non-empty |

## Acceptance criteria

1. An order placed at 01:30 local, with `business_day_start = 05:00`, reports a `business_date` of
   the **previous** day — asserted directly, and again through an endpoint
2. The same instant reports different business dates for two restaurants in different timezones
3. Changing a tax rate creates a second row; the first keeps its `effective_to` and remains readable
4. `effective_from` earlier than today is refused
5. A non-owner receives 403 on every `PATCH /restaurant` and every tax-group write
6. Deactivating a dining area does not delete it, and its tables remain resolvable
7. Dining areas and stations return in `seq` order, and reordering persists
8. Every new route declares a permission and passes the four generic suites unmodified
9. The settings screen explains `business_day_start` with a worked example, not a tooltip
10. `make check` clean; list endpoints pass `assert_max_queries`

## Tests

| Test | Asserts |
|---|---|
| `test_business_date_before_day_start` | 01:30 local lands on the previous business date |
| `test_business_date_after_day_start` | 05:01 local lands on the same date |
| `test_business_date_across_timezones` | one UTC instant, two restaurants, two answers |
| `test_business_date_is_not_date_trunc` | a case where naive `date_trunc` and the helper disagree — the bug this exists to prevent |
| `test_tax_rate_change_creates_a_row` | the superseded rate survives with its dates |
| `test_effective_from_cannot_predate_today` | back-dating refused |
| `test_tax_group_rate_is_immutable` | `PATCH` may rename, never reprice |
| `test_configure_requires_owner_or_admin` | manager refused on settings and tax |
| `test_deactivated_area_keeps_its_tables` | ADR 0008 tier behaviour |
| `test_seq_ordering_survives_reorder` | drag-to-reorder persists and is stable |
| generic suites | tenant isolation, permission matrix, persona separation, route declaration — unmodified, over the new routes |

## Open decisions — I need your answer before I build

**1 · Who may change `business_day_start` and the tax rates?**
My recommendation: **owner and admin only.** A manager staffing a shift has no reason to change
what a day means, and both settings move money. Say if you want managers to hold it.

**2 · May a tax rate ever be edited in place?**
My recommendation: **no, never** — a change is always a new row. The cost is that fixing a typo in
a rate entered five minutes ago also creates a row. I think that is the right trade: the alternative
is a field that silently rewrites history, and there is no way to tell the two cases apart in code.

**3 · `restaurant_table.status = 'reserved'` — keep it or drop it?** (finding S14)
It exists in the schema with nothing able to set it. Options: (a) drop the value until reservations
are real, (b) keep it and let a manager set it by hand, (c) build a minimal `reservation` table now.
My recommendation: **(b)** — a manager marking a table reserved for a walk-in booking is genuinely
how small restaurants work, it costs nothing, and it does not pretend to be a reservation system.

**4 · Does `POST /auth/switch` belong in this module?** (finding S12)
`_home_restaurant` currently picks a person's *first* restaurant, so someone working at two branches
cannot reach the second. It is small and it fits here. My recommendation: **yes, include it.**

## Risks

| Risk | Mitigation |
|---|---|
| **The business-day helper is subtly wrong and nothing notices for months** | It gets the highest-effort attention in the module, a test that deliberately contrasts it with naive `date_trunc`, and an external review after it lands. Every later module inherits it |
| Four screens on a design system with one component | The component work is real and is counted in the estimate. It is also the point: if the system does not hold here, better to learn it now than in M07 |
| The 2-day estimate in `docs/modules.md` predates the audit items and the design system | Stated as 3 days here. `docs/plan/month-1.md` has slack; if it runs longer the plan absorbs it |
| Scope creep from "while we are in settings…" | Theme scheduling is in because it was deferred here deliberately. Everything else that arrives goes to `docs/backlog.md` |

## What I need from you

1. **Approve this spec**, or tell me what to change
2. **Answer the four open decisions** — 2 and 3 are the ones with real consequences
3. Nothing else. With those, M02 runs to green without further input, up to your manual pass.
