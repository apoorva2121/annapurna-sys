# M14 · Audit & Notifications — Manual Test

**Module:** M14 · **Built:** 2026-09-18 · **Gate:** `make check`. The runs and their results are in
`docs/plan/m14-build-log.md`.

Run `make seed` first, then `make dev`. Sign in with the seeded logins
`docs/manual-tests/M01-identity.md` names: **owner@spicegarden.test**,
**manager@spicegarden.test**, **accountant@spicegarden.test**, **chef@spicegarden.test** and
**waiter1@spicegarden.test**.

**Two things to know before you start.**

**The audit trail is not a statutory register**, and nothing in this product will describe it as
one. It is the restaurant's own record of who changed what. No Indian rule in
`docs/compliance-rules.md` requires it; the reason an owner wants it is a dispute or an inspection,
and it earns its place by being complete and readable rather than by being mandated.

**Every alert you see is computed the moment you open the screen.** Nothing is stored and nothing
is sent by a job — there is no job. So an alert disappears by itself when the thing it is about
stops being true, which is section D, and is the behaviour to test hardest.

---

## What I already ran, and what still wants you

| Section | State |
|---|---|
| **A · the trail** | Verified: who may open it, three filters, a sentence per row, and that reading it writes nothing |
| **B · the decorator** | Verified by a build-failing test: a mutating service method with no declaration fails the build. **B3 is yours** |
| **C · the centre** | Verified: each condition, who sees it, and the read/dismiss state. **C1 is the question** |
| **D · conditions resolve themselves** | Verified in tests; **worth doing by hand**, because it is the behaviour nobody expects |
| **E · who sees what** | Verified across roles. **E2 by hand** |
| **F · exploratory** | Not run. Yours |

Short of time? Do **C1**, then **D**, then the F charter.

---

## A · The trail

| # | Step | Expect |
|---|---|---|
| A1 | As **owner**, change a dish's price (M03), then open **Audit trail** | A row at the top: *"Owner Person repriced a dish — price … → …"*. A sentence, not a blob |
| A2 | Press **Show the values** on it | The before and after, field by field, underneath |
| A3 | Void a bill with a reason (M07), then reload the trail | The void is there, and the **reason you typed** is shown on its own line |
| A4 | Filter by **What kind of thing?** = `order` | Only the order rows. Clear it and everything comes back |
| A5 | Set **From** and **To** to today | Only today's |
| A6 | Reload the trail three times, then look at the trail again | **No rows about reading it.** Who looked at what is not recorded, deliberately |
| A7 | Correct somebody's attendance with a reason (M12), then look | The correction, with its reason. This is the row M17 depends on |

---

## B · The record nobody forgot to write

| # | Step | Expect |
|---|---|---|
| B1 | Adjust stock (M05), approve a waste log (M09), grant somebody a role (M01), close a till (M07) | All four are in the trail, each naming you |
| B2 | Change a line's quantity on an open bill (M07) | It is in the trail. **This one was invisible before M14** — the method took no actor at all, so nothing could record who did it |
| B3 | **The question.** Read a dozen rows | Is there anything you would expect to see and do not? The exemption list in `tests/test_audit_declarations.py` says why each unrecorded act is unrecorded; if you disagree with one, that is a change I should make |

---

## C · The centre

| # | Step | Expect |
|---|---|---|
| C1 | **The question.** As **owner**, open **Alerts** | Is every line something you would actually act on? Anything you would not is noise, and noise is how a notification centre dies. Tell me which to remove |
| C2 | Consume stock that was never received (M05 — sell a dish with no delivery recorded) | A **critical** alert: *"Stock was used that nobody recorded receiving"* |
| C3 | Press **Mark as read** | It stays on the list and stops counting as unread |
| C4 | Press **Dismiss** on one of two alerts of the same kind | Only that one goes. The other stays — dismissing paneer does not dismiss ghee |
| C5 | Read the line under the buttons | *"Dismissing hides this alert. It does not change what it is about."* If that is not clear enough, say so |
| C6 | Press **Go and deal with it** | The screen where that condition is actually fixed |
| C7 | As **owner** with nothing wrong, open Alerts | *"Nothing needs you right now"* in words, not a blank screen |

---

## D · Conditions resolve themselves — **the behaviour to test hardest**

| # | Step | Expect |
|---|---|---|
| D1 | Note an alert about negative stock | It is there |
| D2 | Record the delivery that was missing (M05) | **The alert is gone on the next load, without anybody dismissing it.** Nothing was marked done; the condition stopped being true |
| D3 | Submit a stock count (M05) as one person | An alert appears for whoever can approve it |
| D4 | Approve it as a second person | The alert goes |
| D5 | Resolve an open complaint (M10) | Its alert goes |
| D6 | Dismiss an alert, then make the condition go away and come back | It **returns**. A dismissal is remembered against that condition, not against the kind |

---

## E · Who sees what

| # | Step | Expect |
|---|---|---|
| E1 | As **manager**, look for the audit trail | It is **not in the navigation**, and the address refuses. The person who runs the floor is frequently the subject of the record |
| E2 | As **accountant**, open the audit trail | It works. Compare a money row against M13's sales report for the same day — they must agree |
| E3 | As **waiter1**, open Alerts | Only their own overdue tasks. No stock, no till, no complaints |
| E4 | As **chef**, open Alerts | Stock conditions, because a chef holds `stock.view`. No till and no complaints |
| E5 | As **manager@tandoorhouse.test**, open both screens | Their own restaurant only — never Spice Garden's |

---

## F · Exploratory charter — 20 minutes

**Charter:** *Do something the product should have recorded, and find out whether it did.*

Ideas: change a price and change it back; discount a bill and remove the discount; grant a role at
one restaurant and check it appears at that restaurant's trail and not the other's; deactivate
somebody and look for the sessions that were revoked; reset a password and confirm the trail says
it happened and **never** shows the password.

**The one thing that must never be there is a credential.** If you see anything resembling a
password, a hash or a token in an audit row, stop and tell me — that is the most serious defect
this module can have.
