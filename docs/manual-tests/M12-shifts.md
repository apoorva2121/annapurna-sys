# M12 · Shifts — Manual Test

**Module:** M12 · **Built:** 2026-09-18 · **Gate:** `make check`. The runs and their results are in
`docs/plan/m12-build-log.md`.

Run `make seed` first, then `make dev`. Sign in with the seeded logins that
`docs/manual-tests/M01-identity.md` names: **owner@spicegarden.test**,
**manager@spicegarden.test**, **kitchen1@spicegarden.test** and **waiter1@spicegarden.test**.
**manager@tandoorhouse.test** is the other tenant.

**The seed already has a roster**: two shifts (Morning 08:00–16:00, Evening 16:00–00:30), the last
three days clocked in, the next week scheduled, and each waiter on one section. One person
yesterday was rostered and never clocked in, so you can see that state without building it.

**Two things in this module are worth more than everything else**, and neither is a number:

- **Section C.** Clocking in has to be so fast that a waiter does it while walking in, one-handed,
  without thinking. If it is not, nobody clocks in, and every hour figure M17 ever produces is
  fiction.
- **Section E.** An order opened on a table now gets the waiter whose section it is. Whether that
  is *right more often than it is wrong* is a judgement only somebody who has run a floor can make.

**One thing will look wrong and is not.** A restaurant day runs 05:00 to 05:00 (ADR 0004). So a
shift entered as starting at **00:00 on Tuesday** is the small hours at the *end* of Tuesday — i.e.
midnight going into Wednesday. Every seeded shift avoids that boundary on purpose. If you create
one yourself and it appears on a day you did not expect, this is why; tell me if the wording on the
roster screen did not warn you clearly enough.

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · the roster** | Verified: crossing midnight, one person once per shift per day, a deactivated shift still naming itself. **A4 by hand** |
| **B · who is on now** | Verified across the midnight boundary. **B2 is the manager's real question** |
| **C · the clock** | Verified: five refusals, five sentences; you cannot clock anybody else in. **C1 is the one that matters and only you can do it** |
| **D · corrections** | Verified: a reason is required and an audit row is written with both values. **D3 by hand** |
| **E · the waiter the roster assigns** | Verified: one waiter assigns, two assign nobody, it never overrides a person. **E5 is the judgement** |
| **F · who may do what** | Verified by the permission matrix over every route. **F1 and F4 by hand** |
| **G · exploratory** | Not run. Yours |

Short of time? Do **C1**, then **E5**, then the G charter.

---

## A · The roster

| # | Step | Expect |
|---|---|---|
| A1 | As **manager**, open **Roster** | Two shifts, people on the next week, each waiter against a section |
| A2 | Look at yesterday | Most people **Present** with times. One person shows **Did not clock in** — not "Absent". Nobody asserted an absence, so the screen does not invent one |
| A3 | Put **waiter1** on the Evening shift for a day they are already on it | Refused: already on this shift that day |
| A4 | Put somebody on the Evening shift tomorrow, with a section | One row of taps — person, shift, section, day. **Could you fill a whole week this way without it becoming a chore?** If not, say what you would want instead |
| A5 | As **manager**, delete a *future* assignment, then try to delete one from yesterday | The future one goes. Yesterday's is refused: it is a record now, and the way to say somebody did not work is **Mark absent**, which has your name on it |

---

## B · Who is on now

| # | Step | Expect |
|---|---|---|
| B1 | As **manager**, open **Roster** and read **On now** | Whoever the current time falls inside a shift for, with their section |
| B2 | Compare it to what you would expect if you were standing in the restaurant | **Does it match?** If it is empty when it should not be, check the shift times against the clock and tell me both |
| B3 | If you can, look again after 00:30 (the Evening shift's end) | The evening people drop off. The shift that ends after midnight still belonged to the previous business day while it was running |

---

## C · The clock — **do this on a phone, standing up**

| # | Step | Expect |
|---|---|---|
| C1 | As **waiter1** on a phone, open **My shifts** and clock in. **Time it from opening the app.** | Under five seconds. Write down the number you actually got, whatever it is |
| C2 | Look at the status | **Present**, or **Late** if you are more than ten minutes past the start. You did not have to say which |
| C3 | Tap clock in again | *You are already clocked in.* Its own sentence, not a generic error |
| C4 | Clock out, then try again | *You are already clocked out* |
| C5 | Try to clock in to **tomorrow's** shift | Refused, and it says why: you can only clock in to a shift you are working now |
| C6 | As **kitchen1**, try to clock in using **waiter1**'s shift — ask me for the address if you want to try it properly | Refused. **There is no way to clock in another person**: the screen has no field for it and the server takes your own identity, whatever is sent |

---

## D · Corrections have an author

| # | Step | Expect |
|---|---|---|
| D1 | As **manager**, correct somebody's clock-in time without typing a reason | Refused. A reason is required |
| D2 | Do it again with "His phone was dead" | Saved. The status updates to Present or Late from the corrected time |
| D3 | **The point.** A correction is a manager asserting somebody else's attendance | It is recorded as *your* act, with the old value, the new value and your reason. When M14's audit screen ships you will be able to read it there; for now, ask me and I will show you the row |

---

## E · The waiter the roster assigns

This is the owner decision from 2026-09-14, finally buildable.

| # | Step | Expect |
|---|---|---|
| E1 | Check the roster: exactly **one** waiter is on the section your test table belongs to | If not, put one there for today |
| E2 | As **manager**, open an order on a table in that section, without naming a waiter | The order has that waiter on it. You did not choose them |
| E3 | As **waiter1**, open an order yourself on the same table | **You** are the waiter. Auto-assignment never overrides a person |
| E4 | Put a *second* waiter on the same section for today, then open another order as **manager** | **Nobody** is assigned. Two possible answers means no answer: a wrong waiter is somebody else's performance score |
| E5 | **The judgement.** Over a few orders, is the waiter it picks right more often than it is wrong? | Your answer. If it is wrong in a way that has a pattern, that pattern is the finding |
| E6 | Open a **takeaway** order | No waiter, as before. Nobody serves a counter order at a table |

---

## F · Who may do what

| # | Step | Expect |
|---|---|---|
| F1 | As **waiter1**, open **Roster** by address | You can read it: who is on, and your own shifts. A roster nobody can read is a noticeboard in a locked room |
| F2 | As **waiter1**, try to put somebody on a shift | Refused. Staffing is a manager's |
| F3 | As **kitchen1**, try to mark somebody absent | Refused |
| F4 | As **manager@tandoorhouse.test**, paste any Spice Garden shift or assignment address | Not found, every time |

---

## G · Exploratory charter — 15 minutes

**Charter:** *Roster a week the way you actually would for a real restaurant, then try to make the
roster and the floor disagree.*

Ideas: overlapping shifts that hand over at the same minute; somebody on two shifts in one day;
a shift crossing midnight on the day a person also works the morning; clock in, then have a manager
correct the same row; deactivate somebody who is rostered tomorrow; put the same person on two
sections; create a shift from 23:00 to 23:00.

Write down anything that surprised you. **Especially: anything about time that did not behave the
way a restaurant day behaves.** That is the invariant everything else in this product stands on,
and you are the person who knows what a restaurant day feels like.
