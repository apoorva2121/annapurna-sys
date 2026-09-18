# M12 · Shifts — Build Log

Spec: `docs/modules/M12-shifts-spec.md`. Manual script: `docs/manual-tests/M12-shifts.md`.

---

## State

| Chunk | What | State |
|---|---|---|
| A | Migrations 0044–0046, `shift_window.py`, models, repository, service, eleven endpoints, seed | ✅ committed |
| B | Auto-assignment in `_opening_waiter`, the two `shift_id` links, the two screens | ✅ committed |
| — | Manual pass | **Owner's** |

Built in one autonomous run on 2026-09-18, on `feat/m11-communication` alongside M11.

---

## The finding that matters most

**A shift starting at 00:00 on business date D is not the beginning of D.** A restaurant's day runs
05:00 to 05:00 (ADR 0004, CLAUDE.md invariant 4), so 00:00 is the small hours at the *end* of that
business day — midnight going into the next calendar day.

This is correct, and the first fixture written for `test_shifts.py` assumed the opposite. Three
tests failed for it:

```
FAILED tests/test_shifts.py::TestStaffingIt::test_an_assignment_that_has_started_cannot_be_deleted
FAILED tests/test_shifts.py::TestWhoIsOnNow::test_a_shift_covering_now_is_on_and_one_that_is_not_is_not
FAILED tests/test_shifts.py::TestTheRosterAssignsTheWaiter::test_one_waiter_on_the_section_gets_the_order
```

The fixtures were wrong, not the code. They now use 05:00–04:59, which *is* the business day
whatever the clock says when the suite runs, and the behaviour that caused the confusion has its
own test — `test_a_midnight_start_belongs_to_the_end_of_the_business_day` — plus a warning in the
manual script, because a person entering a midnight shift will meet exactly this.

**It is the kind of defect this product cannot detect from the inside.** A shift placed on the
wrong day looks entirely normal and surfaces months later as an M17 fairness score out by a night.
That is why `shift_window.py` is pure and why its tests sweep all 576 combinations of start and end
hour rather than three hand-picked ones.

---

## What was built, and the four decisions inside it

**You clock yourself in.** `clock_in` takes no employee id — not a check that could be forgotten
but a parameter that does not exist. Buddy punching is the oldest fraud in hospitality and the
schema cannot prevent it; what the design can do is refuse to make it convenient, and make the
alternative leave a mark. A manager crediting attendance goes through `correct`, which needs
`shift.manage`, needs a reason, and writes an audit row naming both values.

**`present` and `late` are derived at clock-in; `absent` and `leave` are said by a person.** Nothing
in the background flips a status. A check constraint refuses `present` on a row with no
`clock_in_at`, so a manager cannot assert attendance by hand and M17 cannot later count hours
nobody worked. Somebody who never clocked in stays `scheduled`, and the roster renders "did not
clock in" — the truth, where an `absent` nobody asserted would be a disciplinary fact with no
author.

**A missed clock-out stays open.** No job closes it at a guessed time, because M17 normalises per
hour worked and a wrong denominator is worse than a missing one.

**Ambiguity assigns nobody.** The owner's 2026-09-14 decision, built: an order opened on a table
whose section has exactly one rostered waiter gets that waiter, with an audit row whose reason is
`roster`. Two waiters or none assigns nobody, because a wrong waiter is somebody else's performance
score (ADR 0011) and somebody else's name on an audit row. It never overrides a person, never
touches takeaway, and a restaurant with no roster behaves exactly as before —
`test_waiter_assignment.py` passes **unedited**, which is acceptance criterion 11.

One rule the spec did not anticipate and the code needed: the roster says who is on the floor, not
who may take an order. A cleaner rostered to cover a room must not end up owning a bill, so the
candidate is checked against `order_takers` before it is used.

---

## The two columns that had been waiting

`cash_session.shift_id` (M07) and `wastage_event.shift_id` (M09) were created as bare columns with
a comment saying `shift` was M12's. Migration 0044 makes both real foreign keys and both are now
written from the actor's covering assignment.

**Nothing is backfilled.** Rows written before a roster existed have no shift and keep saying so:
attributing historical waste to a plausible shift nobody was on would manufacture attribution into
exactly the table whose value is that it is honest.

`dining_area` also gains `UNIQUE (id, restaurant_id)` — additive, and what lets `shift_assignment`
reference a section with the composite tenant key every other child in this schema uses.

---

## Deviations from the spec, each with its reason

| Spec said | Built | Why |
|---|---|---|
| Three screens: roster, clock, on-now | Two: **My shifts** and **Roster** (which opens with *On now*) | They are the same person at the same moment — is tonight covered, and is it covered right now. Two screens would mean checking one and forgetting the other |
| The order screen shows *why* a waiter was assigned | **Not built** | It needs the reason on the order response, which means either a column that exists for a tooltip or a per-order audit read. Deferred to M14, whose audit viewer makes it free. Backlogged with that trigger |
| Migrations 0038 | 0044–0046 | The tree was at 0043 after M11 |
| `shift.clock` permission | Not created | Clocking in declares `shift.view`; the service enforces that the row is the actor's own. A permission cannot express "your row, not his" |

---

## The research finding, recorded because absence is a result

**Indian labour law governs hours, overtime, rest intervals and wage registers** — Shops &
Establishments Acts are state law and the four Labour Codes are notified with staggered
commencement. **This module makes no statutory claim of any kind.** It is a roster and a clock, not
a statutory attendance register, and must never be described as one. If a future module produces a
wage register, its rates, thresholds and commencement dates get looked up from the instruments
then, per CLAUDE.md's standing rule — none are filled in from memory here, and none are needed to
ship a roster.

Nothing in `docs/compliance-rules.md` §A or §B binds this module. Checked, not assumed.

---

## The test files this module owes, and what each one holds

| File | What it holds |
|---|---|
| `test_shift_window.py` | The crossing-midnight arithmetic with no database: the 05:00 boundary both ways, an exclusive end so a handover has one answer, yesterday's evening shift still covering this morning, the tolerant grace read, and all 576 start/end combinations producing a forward span |
| `test_shifts.py` | Over HTTP: staffing, the five clock refusals, a correction's reason and its audit row, nobody asserting `present` by hand, every role in the catalogue reading the roster, who is on now, and the five auto-assignment rules |
| `test_waiter_assignment.py` | **Unedited.** M07's behaviour with no roster present, which is what "a restaurant with no roster loses nothing" means |
| `test_generic_suites.py` | Victim rows for `shift` and `shift_assignment` |
