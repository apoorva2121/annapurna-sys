# M12 · Shifts — Module Spec

**Depends on** M01 (employees), M02 (dining areas). Completes two deliberately-deferred links in
M07 (`cash_session.shift_id`) and M09 (`wastage_event.shift_id`), and unblocks M17.
**Status** — spec written 2026-09-18, before any code, per `docs/sdlc.md` step 1.
Build log: `docs/plan/m12-build-log.md`.

Tables: `shift`, `shift_assignment`.
Endpoints: shift CRUD, assignment CRUD, clock in/out, "who is on now".
Screens: the roster, and the clock-in button.

---

## Why this module is two tables and still not trivial

`docs/modules.md` is blunt: *"deliberately minimal; leave, overtime and swaps are Phase 2. Exists
mainly so waste and performance can attribute to a shift."* That is true and it undersells one
thing, because this module is where **a roster stops being a sheet of paper and starts answering
questions the rest of the product asks**:

- *Who was on the floor when this happened?* — M09's `wastage_event.shift_id`, M07's
  `cash_session.shift_id`, both nullable columns waiting since their modules shipped.
- *Whose section is table 7 tonight?* — the owner's decision of 2026-09-14, recorded in
  `docs/modules.md` and in `backend/tests/test_waiter_assignment.py`: *"Auto-assignment waits for
  shifts (M12): without a roster nobody knows who is on the floor."* This module is the wait ending.
- *Is a 4-hour shift comparable to an 8-hour one?* — M17 normalises per hour worked, and
  `shift_assignment` is where the hours come from.

So the schema is small and the **semantics are the work**: what a shift means when it crosses
midnight, what a business date means when a shift does not, who may say that somebody was present,
and what the product may safely conclude from a roster that is half filled in.

---

## Research — what binds this module, checked 2026-09-18

**`docs/compliance-rules.md`: nothing in §A or §B binds this module.** Checked, not assumed. No
menu text, no restaurant identity, no tax, no price, no customer data. The finding is "no rule
applies".

**What deliberately is *not* claimed.** Indian labour law does govern hours, overtime, rest
intervals and wage registers — Shops & Establishments Acts are state law, and the four Labour Codes
are notified with staggered commencement. **This module makes no statutory claim of any kind.** It
is a roster and a clock, not a statutory attendance register, and it must never be described as
one. If a future module wants to produce a wage register, the rates, thresholds and commencement
dates get looked up from the instruments then, per CLAUDE.md's standing rule — none of them are
filled in from memory here, and none of them are needed to ship a roster. §C's precedent applies:
the absence of a duty is a finding worth recording.

**ADR 0004 (the business day)** is the load-bearing decision this module leans on hardest, and
§4 of CLAUDE.md's invariants states it: a restaurant's day is not midnight to midnight. A shift
from 18:00 to 02:00 belongs to **one** business date, and `business_day_start` (typically 05:00) is
what makes that expressible. `app/core/business_day.py` is the single implementation and this
module adds no second one.

**ADR 0011 / `docs/workload-fairness.md`** already decided the one thing that could have been
designed wrongly here: an assist is **derived** from an order taken outside the waiter's assigned
section, never logged. `shift_assignment.dining_area_id` is the column that makes it derivable, so
this module's job is to make sure that column is actually filled in by a screen people use.

---

## The decisions that matter

### 1 · A shift is a template; an assignment is a person on a date

`shift` holds `name`, `start_time`, `end_time` — "Morning 08:00–16:00", "Evening 16:00–00:30". It
has no date and belongs to nobody. `shift_assignment` puts a person on one, on one `business_date`,
optionally in one section.

This is why the roster is cheap to fill in: a week is 7 × (a handful of shifts) × (a handful of
people), and the screen's job is to make that a grid of taps rather than a form.

A shift is **deactivated, never deleted** (ADR 0008, master-data tier): assignments point at it
forever and a report on last quarter must still be able to name "Evening".

### 2 · A shift may cross midnight; a business date may not

`start_time > end_time` is legal and means the shift crosses midnight — the evening shift of a place
that closes at two. Three consequences, all tested:

- **The assignment's `business_date` is the anchor, and the clock is derived from it.** An Evening
  assignment on business date 2026-09-18 runs from 18:00 on the 18th to 00:30 on the 19th, in the
  restaurant's timezone. Nothing stores those two instants; `business_day.py` plus the shift's
  times produce them.
- **Two shifts may overlap** and nothing prevents it. Morning 08:00–16:00 and Evening 15:00–23:00
  overlap by an hour on purpose, because handover is real.
- **A shift may not be longer than 24 hours**, which is the only limit the check constraint can
  usefully assert, and it exists to catch a typo rather than to regulate anything.

The "which shift covers this moment" predicate is a pure function over the shift's times, the
restaurant's timezone and the moment — the same shape as `floor_rules.BusyWindow.covers`, which
already solved the crossing-midnight comparison and is the pattern this follows rather than
reinvents. It lives in `app/core/shift_window.py` and is unit-tested without a database, including
the 05:00 boundary that CLAUDE.md's invariant 4 names.

### 3 · You clock yourself in. A manager corrects, and never punches

Buddy punching is the oldest fraud in hospitality and the schema cannot prevent it; what the design
can do is refuse to make it convenient and make the alternative leave a mark.

- **`POST /shifts/assignments/{id}/clock-in` acts on the actor's own assignment, always.** There is
  no `employee_id` in the body. Clocking in somebody else is not a permission, it is not a flag, it
  is an endpoint that does not exist.
- **A manager may correct a time** through `PATCH /shifts/assignments/{id}`, which requires
  `shift.manage`, **requires a reason**, and writes an `audit_log` row with the old and new values.
  "Suresh's phone was dead" is a legitimate, recorded, attributable act. It is not the same act as
  clocking in, and the record must not make them look the same.
- **The audit row is written for every attendance correction**, which is the M14 decorator's
  eventual job and a hand-written call until then, in the one place it is made.

Clock-in is refused when the assignment is not the actor's, when it already has a `clock_in_at`,
when the assignment's business date is not today's, and when the employee is not active. Clock-out
is refused without a clock-in, and refused twice. Each refusal is its own message and its own
`issues.json` entry — a single "cannot clock in" would be the worst outcome, because a waiter with
a phone in one hand at the start of service will not debug it.

**A missed clock-out does not self-close.** It stays open and shows as open on the roster, because
a shift silently ended at a guessed time is a number M17 would later normalise against, and a
wrong denominator is worse than a missing one.

### 4 · `present` / `late` are derived at clock-in; `absent` / `leave` are said by a person

`status` is `scheduled | present | absent | late | leave`.

- Created as `scheduled`.
- Clock-in sets `present`, or `late` when `clock_in_at` is more than the restaurant's grace period
  after the shift's start. Grace lives in `restaurant.settings["shifts"]["late_after_minutes"]`,
  default **10**, read tolerantly and validated strictly on the way in — the pattern
  `floor_rules.py` established on 2026-09-13.
- `absent` and `leave` are set by a `shift.manage` holder. **Nothing in the background flips a
  status**: there is no job that marks people absent at 11pm. A person who never clocked in stays
  `scheduled`, and the roster renders that as "did not clock in", which is the truth. Storing an
  `absent` nobody asserted would put a disciplinary fact in the database with no author.

### 5 · One section per person per shift, and the rest is assists

`UQ (shift_id, employee_id, business_date)` means one row, so one `dining_area_id`. A waiter who
genuinely covers two small sections cannot be expressed, and that is the right trade:
**ADR 0011 already decided that an order taken outside your section is a derived assist**, so
covering someone else's area produces exactly the signal M17 wants, automatically, with nobody
logging anything. Adding a second row per person would make assists ambiguous, which is the one
thing the fairness feature cannot afford.

`dining_area_id` is nullable, because a chef, a cleaner and an accountant have no section.

### 6 · Auto-assigning an order to the section's waiter — what it may and may not do

The owner's 2026-09-14 decision, now buildable. The seam already exists:
`OrderService._opening_waiter` decides the waiter when an order is opened, and
`test_waiter_assignment.py` fixes its current behaviour.

**What changes:** when a dine-in order is opened on a table whose dining area has exactly one
waiter assigned in a shift covering that moment on that business date, and no waiter was chosen,
the order gets that waiter.

**Five rules, each a test:**

1. **It never overrides a person.** A waiter opening their own order is still its waiter; a manager
   who names a waiter gets the waiter they named. Auto-assignment only ever fills a blank.
2. **Ambiguity assigns nobody.** Zero waiters on that section → unassigned, as today. *Two or more*
   → unassigned, as today. The product does not guess who is serving table 7, because a wrong
   waiter is worse than none: it is somebody else's performance score (ADR 0011) and somebody
   else's name on an audit row.
3. **Only dine-in.** Takeaway and delivery have no table, no section and no waiter — unchanged.
4. **It is an audit row like any other**, written through the existing `_waiter_audit`, with the
   reason `roster`. A month later, "why is this Priya's order" has an answer.
5. **A restaurant with no roster loses nothing.** No assignments means no auto-assignment means
   today's behaviour exactly. This is why it needs no setting to turn off: an empty roster already
   is off, and a configuration flag for a feature that self-disables is a flag that will one day be
   wrong.

### 7 · The two nullable columns waiting since M07 and M09 become real

`cash_session.shift_id` and `wastage_event.shift_id` were created without foreign keys because
`shift` did not exist ("No foreign key: `shift` is M12's"). This module adds the constraints in a
**new** migration — never by editing the applied ones — and starts populating them:

- opening a cash session and logging waste both resolve *the actor's own covering assignment* at
  that moment, and write its `shift_id`;
- **nothing is backfilled.** Rows written before a roster existed have no shift and must keep
  saying so. Backfilling a plausible shift onto historical waste would manufacture attribution
  that nobody made, into exactly the table whose value is that it is honest.
- both stay nullable, because a restaurant may run without a roster and must still be able to log
  waste and open a till.

### 8 · Everyone reads the roster

**This module invents no permission code either.** The P1 design in `seed/organization.yaml`
contains exactly two, and they are the two this module needs:

| Permission | Who holds it | What it means here |
|---|---|---|
| `shift.view` | **every role** | read the roster, your own assignments, who is on now — and clock *yourself* in and out |
| `shift.manage` | owner, manager | create shifts, staff them, set a status, correct a time with a reason |

**There is no `shift.clock`.** Clocking in declares `shift.view`, and the service enforces that the
assignment is the actor's own. A permission cannot express "your row, not his"; the service can,
and decision 3 is what makes that the only control that matters.

**One deliberate widening of the P1 grant, and it is worth naming.** The design gives `shift.view`
to the manager. This module gives it to every role, for the same reason M11 leans on
`message.send`: a roster nobody can read is a noticeboard in a locked room, and the clock-in
button is useless to the person it exists for if a permission stands in front of it. The widening
is safe because **the permission opens the screen and the scope decides the content**: a front-line
role sees its own assignments and who is covering which section right now — which it can establish
by looking around the room — while the full roster with statuses and corrections stays behind
`shift.manage`. `seed/organization.yaml` records the amendment on the line itself, the way M07's
`cash.manage` and the floor's `floor.manage` are recorded.

`admin` is **not** granted `shift.manage`, following the design: the administrator is configuration
and people, not the running of a service.

---

## Not in scope

- **Leave, overtime, swaps, availability, shift-change requests** — Phase 2, stated in
  `docs/modules.md`. `leave` exists as a *status* somebody sets; there is no leave workflow.
- **Wage calculation, payroll, statutory registers** — see Research. Not a claim this product makes.
- **Geofencing or device-bound clock-in.** The real defence against buddy punching is that the
  action is authenticated as you and recorded; GPS on a phone in a basement kitchen is a support
  ticket generator.
- **A background job that closes forgotten shifts or marks absences.** Decisions 3 and 4.
- **Shift-scoped conversations** (M11's matching non-goal).
- **Auto-assignment for takeaway or delivery**, or any assignment by load-balancing. "Fewest open
  orders" is a scheduling algorithm pretending to be a fairness feature, and M17 is where fairness
  is actually designed.

---

## Deliverables

### Migrations — three

`0044_m12_shifts`: `shift`, `shift_assignment`, their checks and indexes, and the two foreign keys
onto `cash_session.shift_id` and `wastage_event.shift_id` — added here rather than by editing the
applied migrations that created those columns. `downgrade()` drops the constraints first, then the
tables. Up→down→up on real Postgres.

`0045_m12_permissions`: `shift.view` and `shift.manage` into `permission`, with their grants.

`0046_m12_issues`: the issue rows for the clock-in refusals of decision 3.

### Backend

- `app/core/enums.py` — `ShiftAssignmentStatus`, mirrored into `frontend/src/shared/enums.ts`.
- `app/core/permissions.py` and `permissions.json` — the two P1 codes and their grants.
- `app/core/shift_window.py` — the pure crossing-midnight predicate and the shift's instants for a
  business date. No database, no I/O.
- `app/models/shifts.py`, `app/repositories/shifts.py`, `app/services/shifts.py`.
- `app/schemas/shifts.py` — `extra="forbid"` throughout.
- `OrderService._opening_waiter` gains the roster lookup of decision 6.
- `CashService` and `WastageService` resolve and write `shift_id`.
- Seed: two shifts and a week of assignments with sections, so the demo restaurant has a roster and
  auto-assignment is visible without anyone configuring it.

### Endpoints

```
GET    /shifts                                shift.view    the templates
POST   /shifts                                shift.manage
PATCH  /shifts/{id}                           shift.manage  name, times, is_active
GET    /shifts/roster                         shift.view    a date range, assignments with people
POST   /shifts/assignments                    shift.manage  person + shift + date + section
PATCH  /shifts/assignments/{id}               shift.manage  section, status, corrected times + reason
DELETE /shifts/assignments/{id}               shift.manage  before it starts; after, it is a record
GET    /shifts/me                             shift.view    my assignments, today first
POST   /shifts/assignments/{id}/clock-in      shift.view    own only, enforced in the service
POST   /shifts/assignments/{id}/clock-out     shift.view    own only, enforced in the service
GET    /shifts/on-now                         shift.view    who is on, by section — the floor's question
```

### Frontend (staff bundle)

- **Roster** — a week grid, days across and shifts down, each cell the people on it with their
  section. Filling a week is taps, not forms. Overlapping shifts are visible as overlapping.
- **Clock in / out** — one large button on the staff home, thumb-reachable
  (`docs/ui/conventions.md`), showing the shift, the section and the elapsed time once running.
  This is the screen a waiter uses at 11am with one hand.
- **On now** — who is covering which section right now; the manager's glance, and the screen that
  makes a wrong roster obvious before service rather than after.
- The order screen shows *why* a waiter was assigned when it came from the roster, because an
  unexplained name on an order is how people stop trusting a feature.

---

## Threat question — *what would an insider do with this?*

**Clock in a colleague who is not here.** The endpoint takes no employee id, so this is not
possible through the API at all. A manager crediting attendance does it through a corrective
`PATCH` with a reason and an audit row.

**Clock in early and leave, or fix their own times later.** Clock-in stamps server time; a
correction needs `shift.manage`, which a waiter does not hold, plus a reason, plus an audit row.

**Edit the roster after the fact to change who was responsible.** Assignments are mutable by design
(a roster changes) so the defence is the record: every `PATCH` to an assignment writes an audit row
with before and after. M17's published periods are frozen (ADR 0011) precisely so that editing a
roster afterwards cannot move a score that was already published.

**Put themselves on the busiest section every night.** Real, and not a security control — it is a
management problem, and M17's distribution screen is the product's answer to it. Worth naming here
so it is not mistaken for something this module should be policing.

**Get credited for orders they did not take**, by assigning themselves the section. Auto-assignment
only ever fills a blank and only when exactly one waiter covers the section; the audit row says
`roster`; and M17 derives assists from the same data, so the discrepancy surfaces rather than hides.

**Delete an assignment to erase attendance.** `DELETE` is refused once the shift has started — at
that point it is a record, and the way to say somebody did not work is `absent`, which has an
author.

---

## Acceptance criteria

1. A shift from 18:00 to 00:30 on business date D covers 23:59 on D and 00:15 on D+1, and does not
   cover 00:15 on D — asserted against a restaurant whose `business_day_start` is 05:00.
2. Creating an assignment for the same person, shift and date twice is a 409, not a second row.
3. Clock-in stamps server time and sets `present`; eleven minutes after start with a 10-minute
   grace sets `late`; the grace is read from restaurant settings and falls back to 10 when the
   settings are absent or malformed.
4. Clocking in on somebody else's assignment is impossible — there is no field for it, and the
   attempt to use another assignment's id is a 403.
5. Clock-in twice, clock-out without clock-in, and clock-out twice are each their own refusal with
   its own message and issue number.
6. A shift that ends without a clock-out stays open, and no background process closes it.
7. A manager's correction requires a reason and writes an audit row with old and new values; the
   same correction without a reason is a 422.
8. Opening a dine-in order on a table in a section with exactly one rostered waiter assigns that
   waiter, with an audit row whose reason is `roster`.
9. The same order with two waiters on the section, or none, is unassigned — and a waiter opening
   their own order is still the waiter, roster or not.
10. A takeaway order gets no waiter from the roster.
11. A restaurant with no assignments behaves exactly as before: `test_waiter_assignment.py` passes
    unedited.
12. Opening a cash session and logging waste while rostered write the covering `shift_id`; doing
    either with no roster writes `NULL` and succeeds.
13. No historical row gains a `shift_id` from the migration.
14. Every role, including `cleaner`, can open the roster and clock itself in; a role without
    `shift.manage` sees its own assignments and who is on now, and not the corrections.
    No permission code outside the P1 design ships.
15. `DELETE` on an assignment whose shift has started is refused.
16. Deactivating a shift keeps every assignment readable and its name renderable.
17. Query counts on the roster and `on-now` are bounded regardless of how many people are on.
18. Generic suites 1–5 pass, with victim rows for both tables.

---

## Chunks — two PRs against `feat/m12-shifts`

**A · Schema, the window, the roster.** Migrations 0044–0046, models, `shift_window.py` with its
table-driven unit tests, repository, service, all eleven endpoints, permissions, seed, and
`test_shifts_schema.py` / `test_shift_window.py` / `test_shifts_endpoints.py`.

**B · The links, and the screens.** Auto-assignment in `_opening_waiter` with its five tests, the
`shift_id` writes in cash and waste, the roster / clock / on-now screens, and the manual script.
Ends with `make check` clean.
